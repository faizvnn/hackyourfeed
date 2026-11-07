"""Deterministic pitch check: flags the extreme "chipmunk" / "deep voice" edits in a clip. No ML, no API.

    uv run python scripts/pitch_probe.py work/oriane/videos/<id>.mp4            # prints per-second pitch + flags
    uv run python scripts/pitch_probe.py clip.mp4 --hop 0.5                     # finer timeline

How: ffmpeg -> 16 kHz mono PCM -> 40 ms frames -> normalized autocorrelation f0 (60-500 Hz), voiced when the
autocorrelation peak is strong and the frame has energy -> median f0 per hop. Flags:
  high   median f0 > 350 Hz   (sped-up / chipmunk voice)
  low    median f0 < 70 Hz    (pitched-down voice)
  Absolute thresholds on purpose: a relative-to-clip rule flagged the second speaker in two-person clips.
  and the run must last >= 3 s; short spikes are laughs / music hits / sfx (seen on real clips), not voice edits.
Needs ffmpeg + numpy. Output JSON saved to work/analysis/<clip>.pitch.json; merge it into the edit spec as
"voice_fx": [{start,end,kind,f0}] so the editor agent knows where the funny-voice moments are.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import WORK_DIR  # noqa: E402

SR = 16000
FRAME, STEP = int(0.040 * SR), int(0.010 * SR)   # 40 ms frames, 10 ms step
F_MIN, F_MAX = 60.0, 500.0
HIGH_HZ, LOW_HZ = 350.0, 70.0   # deliberately strict: missing a real effect beats inventing one
F_CAP = 495.0                    # f0 at the search ceiling = music/noise, treated as unvoiced
MIN_EVENT_S = 3.0  # shorter spikes are laughs, music hits or sfx, not a pitch-shifted voice


def load_audio(path: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
                         check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def frame_f0(x: np.ndarray) -> tuple[float, float]:
    """(f0_hz, periodicity 0..1) for one frame via normalized autocorrelation; f0=0 when unvoiced."""
    x = x - x.mean()
    e = float(np.dot(x, x))
    if e < 1e-4:
        return 0.0, 0.0
    ac = np.correlate(x, x, "full")[len(x) - 1:] / e
    lo, hi = int(SR / F_MAX), int(SR / F_MIN)
    seg = ac[lo:hi]
    k = int(np.argmax(seg))
    peak = float(seg[k])
    if peak < 0.55:
        return 0.0, peak
    lag = lo + k
    # parabolic refinement of the peak
    if 0 < k < len(seg) - 1:
        a, b, c = seg[k - 1], seg[k], seg[k + 1]
        lag += 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else 0
    return SR / lag, peak


def analyze(path: Path, hop_s: float) -> dict:
    x = load_audio(path)
    n = (len(x) - FRAME) // STEP
    f0 = np.zeros(n)
    for i in range(n):
        f0[i], _ = frame_f0(x[i * STEP:i * STEP + FRAME])
    times = np.arange(n) * STEP / SR
    f0[f0 >= F_CAP] = 0.0
    voiced = f0[f0 > 0]
    clip_median = float(np.median(voiced)) if len(voiced) else 0.0

    rows = []
    t = 0.0
    dur = len(x) / SR
    while t < dur:
        m = (times >= t) & (times < t + hop_s) & (f0 > 0)
        seg = f0[m]
        if len(seg) >= 5:  # at least 50 ms voiced
            med = float(np.median(seg))
            kind = "high" if med > HIGH_HZ else "low" if med < LOW_HZ else "normal"
            rows.append({"t": round(t, 2), "f0": round(med, 1), "voiced": round(len(seg) / max(1, m.sum() or 1), 2), "kind": kind})
        else:
            rows.append({"t": round(t, 2), "f0": None, "voiced": 0.0, "kind": "silence"})
        t += hop_s

    # merge consecutive flagged hops into events
    events, cur = [], None
    for r in rows:
        if r["kind"] in ("high", "low"):
            if cur and cur["kind"] == r["kind"] and abs(cur["end"] - r["t"]) < 1e-6:
                cur["end"] = round(r["t"] + hop_s, 2); cur["f0s"].append(r["f0"])
            else:
                cur = {"start": r["t"], "end": round(r["t"] + hop_s, 2), "kind": r["kind"], "f0s": [r["f0"]]}
                events.append(cur)
        else:
            cur = None
    for e in events:
        e["f0"] = round(float(np.median(e.pop("f0s"))), 1)
    events = [e for e in events if e["end"] - e["start"] >= MIN_EVENT_S - 1e-6]
    return {"duration_s": round(dur, 2), "clip_median_f0": round(clip_median, 1), "hop_s": hop_s,
            "voice_fx": events, "timeline": rows}


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit(__doc__)
    hop = float(sys.argv[sys.argv.index("--hop") + 1]) if "--hop" in sys.argv else 1.0
    path = Path(args[0])
    res = analyze(path, hop)
    print(f"{path.name}: {res['duration_s']}s, clip median f0 {res['clip_median_f0']} Hz")
    bar = "".join({"high": "▲", "low": "▼", "normal": "·", "silence": " "}[r["kind"]] for r in res["timeline"])
    print(f"timeline ({hop}s/char): [{bar}]")
    for r in res["timeline"]:
        if r["f0"] is not None:
            print(f"  {r['t']:6.1f}s  {r['f0']:6.1f} Hz  {r['kind']}")
    print("voice_fx:", json.dumps(res["voice_fx"]))
    out = WORK_DIR / "analysis" / f"{path.stem}.pitch.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1))
    print(f"saved -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
