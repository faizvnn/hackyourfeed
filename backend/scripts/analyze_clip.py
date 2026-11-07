"""Probe: send one short to a multimodal model and get back an *edit spec* another AI can follow.

    uv run python scripts/analyze_clip.py work/oriane/videos/<id>.mp4 --provider gemini
    uv run python scripts/analyze_clip.py clip.mp4 --provider minimax
    uv run python scripts/analyze_clip.py clip.mp4 --provider gmi --model Qwen/Qwen3-VL-...   # tries video, falls back to frames
    uv run python scripts/analyze_clip.py clip.mp4 --provider gmi --frames                     # force frame mode (needs ffmpeg)
    uv run python scripts/analyze_clip.py clip.mp4 --provider gmi --hires --fps 3              # Gemini-native: high media res, 3 fps

--hires uses GMI's Gemini-native `:generateContent` endpoint (same gs:// upload) with mediaResolution HIGH
(258 tok/frame instead of 66) and a custom fps, so small captions and sub-second zooms/flashes are visible.

Providers / keys (backend/.env):
  gemini   GEMINI_API_KEY   default model gemini-2.5-flash-lite (free tier, ~100 tok/s of video incl. audio)
  minimax  MINIMAX_API_KEY  default model MiniMax-M3.1-Flash  ($0.15/M in), video via data: URL <= 50 MB
  gmi      GMI_API_KEY      default google/gemini-3.5-flash-lite. Verified path: upload the mp4 through GMI's Upload
                            API (storage.googleapis.com), pass it as a gs:// `video_url`; Gemini then sees video AND
                            audio (~90 tok/s). base64 and https URLs are rejected by GMI's backend. --frames sends
                            1 fps JPEGs instead (no audio; Oriane transcript injected if available).

Output: JSON edit spec printed + saved to work/analysis/<clip>.<provider>.json, with token usage.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import GMI_API_KEY, GMI_BASE_URL, GMI_MODEL, WORK_DIR  # noqa: E402
from app.llm import extract_json  # noqa: E402

PROMPT = """You are a short-form video editor reverse-engineering a viral clip so another AI can re-create its STYLE
on a different podcast interview. Watch and listen to the whole clip. Timestamp everything in seconds.

Priorities, in order:
1. SUBJECT. What is said matters most: the claim, how the argument is built, the lines worth quoting. Be specific.
2. FORMAT and CAPTIONS. How it is framed and captioned.
3. EFFECTS. Only list an effect you are certain of. Missing one is fine; inventing one is not. When unsure, leave it out.

Return ONLY a JSON object:
{
 "subject": {"topic": "", "key_claim": "the one-sentence point the clip makes",
             "structure": "how it builds, e.g. setup -> tension -> payoff, or question -> answer",
             "spoken_hook": "first sentence spoken", "why_it_hooks": "",
             "quotable_lines": [{"t": 0.0, "text": ""}],
             "speaker_setup": "single talking head | two-person podcast | b-roll heavy | screen recording",
             "audience": "who this is for"},
 "format": {"aspect": "9:16", "duration_s": 0, "framing": "how speakers are cropped/placed", "background": ""},
 "captions": {"present": true, "style": "word-by-word | phrase | sentence", "position": "", "look": "font feel, color, highlight, case",
              "animation": ""},
 "on_screen_text": [{"t": 0.0, "text": "", "role": "hook | emphasis | label"}],
 "edit_timeline": [{"t": 0.0, "event": "cut | zoom_in | zoom_out | speaker_switch | b_roll | text_overlay | sfx | music_hit", "note": ""}],
 "pacing": {"cuts_per_10s": 0, "silence_trimmed": true, "music": "none | low bed | beat-synced", "energy": "calm | medium | high"},
 "voice_fx": [{"start": 0.0, "end": 0.0, "kind": "pitch_up | pitch_down | sped_up | slowed | robot | echo"}],
 "instructions_for_editor": ["ordered imperative steps an ffmpeg/LLM editor could apply to a raw 2-camera podcast recording"]
}
voice_fx: leave [] unless the voice is unmistakably processed for 3+ seconds. Laughs, shouts, sfx and music are not voice_fx.
edit_timeline: cuts, speaker switches and text overlays you clearly saw. Do not guess zooms or sfx."""

DEFAULT_MODEL = {"gemini": "gemini-2.5-flash-lite", "minimax": "MiniMax-M3.1-Flash",
                 "gmi": GMI_MODEL or "google/gemini-3.5-flash-lite"}
PRICE_IN_PER_M = {"gemini": 0.10, "minimax": 0.15, "gmi": None}  # USD, rough list prices
OUT = WORK_DIR / "analysis"


def b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


# ---------------------------------------------------------------- gemini ---
def run_gemini(path: Path, model: str) -> tuple[str, dict]:
    key = os.getenv("GEMINI_API_KEY") or sys.exit("set GEMINI_API_KEY (free at aistudio.google.com)")
    body = {
        "contents": [{"parts": [
            {"inline_data": {"mime_type": "video/mp4", "data": b64(path)}},
            {"text": PROMPT},
        ]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
    }
    r = httpx.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                   params={"key": key}, json=body, timeout=300)
    if r.status_code >= 400:
        sys.exit(f"gemini HTTP {r.status_code}: {r.text[:800]}")
    d = r.json()
    text = "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"])
    u = d.get("usageMetadata", {})
    return text, {"in": u.get("promptTokenCount"), "out": u.get("candidatesTokenCount")}


# ------------------------------------------------ openai-compatible (minimax/gmi) ---
def run_openai_compat(base_url: str, key: str, model: str, content: list[dict]) -> tuple[str, dict]:
    from openai import OpenAI

    c = OpenAI(base_url=base_url, api_key=key)
    resp = c.chat.completions.create(model=model, temperature=0.2, max_tokens=4000,
                                     messages=[{"role": "user", "content": content}])
    u = resp.usage
    return resp.choices[0].message.content or "", {"in": u.prompt_tokens if u else None, "out": u.completion_tokens if u else None}


def gmi_upload(path: Path) -> str:
    """Upload through GMI's Upload API and return the gs:// URI (Gemini on GMI rejects https links)."""
    h = {"Authorization": f"Bearer {GMI_API_KEY}"}
    r = httpx.post("https://console.gmicloud.ai/api/v1/ie/requestqueue/apikey/upload-url", headers=h,
                   json={"file_type": "mp4"}, timeout=60)
    r.raise_for_status()
    up, pub = r.json()["upload_url"], r.json()["public_url"]
    httpx.put(up, content=path.read_bytes(), headers={"Content-Type": "video/mp4"}, timeout=300).raise_for_status()
    return "gs://" + pub.split("https://storage.googleapis.com/", 1)[1]


def run_gmi_native(path: Path, model: str, fps: float, hires: bool) -> tuple[str, dict]:
    """Gemini-native request through GMI: lets us set mediaResolution and fps, which chat completions can't."""
    gs = gmi_upload(path)
    print(f"uploaded -> {gs}", file=sys.stderr)
    body = {
        "contents": [{"role": "user", "parts": [
            {"fileData": {"mimeType": "video/mp4", "fileUri": gs}, "videoMetadata": {"fps": fps}},
            {"text": oriane_transcript(path) + PROMPT},
        ]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json",
                             "mediaResolution": "MEDIA_RESOLUTION_HIGH" if hires else "MEDIA_RESOLUTION_LOW"},
    }
    name = model.split("/", 1)[-1]
    r = httpx.post(f"{GMI_BASE_URL}/models/{name}:generateContent", json=body,
                   headers={"Authorization": f"Bearer {GMI_API_KEY}"}, timeout=600)
    if r.status_code >= 400:
        sys.exit(f"gmi native HTTP {r.status_code}: {r.text[:800]}")
    d = r.json()
    text = "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"])
    u = d.get("usageMetadata", {})
    return text, {"in": u.get("promptTokenCount"), "out": u.get("candidatesTokenCount"),
                  "modalities": u.get("promptTokensDetails")}


def gs_video_content(path: Path) -> list[dict]:
    gs = gmi_upload(path)
    print(f"uploaded -> {gs}", file=sys.stderr)
    return [{"type": "video_url", "video_url": {"url": gs}}, {"type": "text", "text": oriane_transcript(path) + PROMPT}]


def video_content(path: Path, fps: float) -> list[dict]:
    return [
        {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{b64(path)}", "fps": fps}},
        {"type": "text", "text": PROMPT},
    ]


def oriane_transcript(path: Path) -> str:
    """If work/oriane/raw_*.json holds this clip (by id in the filename), return its timed transcript + on-screen text."""
    cid = path.stem
    for raw in sorted((WORK_DIR / "oriane").glob("raw_*.json"), reverse=True):
        data = json.loads(raw.read_text())
        for r in (data.get("data") or {}).get("results") or []:
            if r.get("id") == cid:
                m = (r.get("media") or [{}])[0]
                lines = [f"[{c['startSeconds']:.1f}-{c['endSeconds']:.1f}s] {c['text']}" for c in m.get("transcriptChunks") or []]
                return ("Timed transcript (from Oriane):\n" + "\n".join(lines)
                        + "\nOn-screen text detected: " + json.dumps((m.get("onScreenText") or [])[:15]) + "\n")
    return ""


def frames_content(path: Path, fps: float, max_frames: int = 24) -> list[dict]:
    """1 fps JPEG frames as images, each labelled with its timestamp. Needs ffmpeg. No audio, so the Oriane
    timed transcript is injected when the clip came from probe_oriane.py."""
    tmp = Path(tempfile.mkdtemp(prefix="frames_"))
    subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-vf", f"fps={fps},scale=360:-2",
                    "-q:v", "6", str(tmp / "f_%04d.jpg")], check=True)
    files = sorted(tmp.glob("f_*.jpg"))
    step = max(1, len(files) // max_frames)
    files = files[::step][:max_frames]
    content: list[dict] = [{"type": "text", "text": f"{len(files)} frames sampled at {fps} fps from the clip (no audio). "
                                                        "Timestamp precedes each frame."}]
    for i, f in enumerate(files):
        content.append({"type": "text", "text": f"t={i * step / fps:.1f}s"})
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64(f)}"}})
    tr = oriane_transcript(path)
    content.append({"type": "text", "text": tr + PROMPT + ("" if tr else "\n(You cannot hear audio: infer spoken_hook from captions on screen.)")})
    print(f"frames={len(files)} transcript={'yes' if tr else 'no'}", file=sys.stderr)
    return content


def gate_voice_fx(spec: dict, path: Path) -> dict:
    """High bar: keep a model voice_fx only if scripts/pitch_probe.py flagged an overlapping window for this clip.
    If no pitch.json exists for the clip, keep nothing (run pitch_probe first to enable effects)."""
    model_fx = spec.get("voice_fx") or []
    spec["voice_fx_model"] = model_fx
    pj = OUT / f"{path.stem}.pitch.json"
    probe = json.loads(pj.read_text())["voice_fx"] if pj.exists() else []
    spec["voice_fx_probe"] = probe
    kept = [m for m in model_fx if any(m["start"] < p["end"] and p["start"] < m["end"] for p in probe)]
    spec["voice_fx"] = kept
    print(f"voice_fx: model={len(model_fx)} probe={len(probe)} agreed={len(kept)}"
          + ("" if pj.exists() else " (no pitch.json -> none kept)"), file=sys.stderr)
    return spec


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opt = lambda k, d=None: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d  # noqa: E731
    if not args:
        raise SystemExit(__doc__)
    path = Path(args[0])
    provider = opt("--provider", "gemini")
    model = opt("--model", DEFAULT_MODEL[provider])
    fps = float(opt("--fps", "1"))
    size_mb = path.stat().st_size / 1e6
    print(f"{path.name}: {size_mb:.1f} MB -> {provider} / {model}", file=sys.stderr)

    t0 = time.time()
    mode = "video"
    if provider == "gemini":
        text, usage = run_gemini(path, model)
    elif provider == "minimax":
        key = os.getenv("MINIMAX_API_KEY") or sys.exit("set MINIMAX_API_KEY")
        text, usage = run_openai_compat("https://api.minimax.io/v1", key, model, video_content(path, fps))
    elif provider == "gmi":
        if not GMI_API_KEY or not model:
            sys.exit("set GMI_API_KEY and GMI_MODEL (or --model)")
        if "--frames" in sys.argv:
            mode = "frames"
            text, usage = run_openai_compat(GMI_BASE_URL, GMI_API_KEY, model, frames_content(path, fps))
        elif "--hires" in sys.argv or "--fps" in sys.argv:
            hires = "--hires" in sys.argv
            mode = f"native({'high' if hires else 'low'}res,{fps}fps)"
            text, usage = run_gmi_native(path, model, fps, hires)
        else:
            mode = "video(gs)"
            text, usage = run_openai_compat(GMI_BASE_URL, GMI_API_KEY, model, gs_video_content(path))
    else:
        sys.exit("--provider gemini|minimax|gmi")

    secs = time.time() - t0
    try:
        spec = extract_json(text)
    except Exception:  # noqa: BLE001
        print("could not parse JSON; raw output:\n", text[:3000])
        raise
    spec = gate_voice_fx(spec, path)
    price = PRICE_IN_PER_M[provider]
    cost = f"~${(usage['in'] or 0) * price / 1e6:.4f} input" if price and usage.get("in") else "n/a"
    print(json.dumps(spec, indent=1))
    print(f"\n[{provider}/{model} {mode}] {secs:.1f}s  tokens in={usage['in']} out={usage['out']}  cost {cost}", file=sys.stderr)
    OUT.mkdir(parents=True, exist_ok=True)
    tag = provider + ("-hires" if "--hires" in sys.argv else "") + ("-frames" if "--frames" in sys.argv else "")
    out = OUT / f"{path.stem}.{tag}.json"
    out.write_text(json.dumps({"provider": provider, "model": model, "mode": mode, "usage": usage, "seconds": secs, "spec": spec}, indent=1))
    print(f"saved -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
