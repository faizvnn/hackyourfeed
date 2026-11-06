"""Probe: send one short to a multimodal model and get back an *edit spec* another AI can follow.

    uv run python scripts/analyze_clip.py work/oriane/videos/<id>.mp4 --provider gemini
    uv run python scripts/analyze_clip.py clip.mp4 --provider minimax
    uv run python scripts/analyze_clip.py clip.mp4 --provider gmi --model Qwen/Qwen3-VL-...   # tries video, falls back to frames
    uv run python scripts/analyze_clip.py clip.mp4 --provider gmi --frames                     # force frame mode (needs ffmpeg)

Providers / keys (backend/.env):
  gemini   GEMINI_API_KEY   default model gemini-2.5-flash-lite (free tier, ~100 tok/s of video incl. audio)
  minimax  MINIMAX_API_KEY  default model MiniMax-M3.1-Flash  ($0.15/M in), video via data: URL <= 50 MB
  gmi      GMI_API_KEY      default google/gemini-3.1-flash-lite-preview (GMI's Gemini quickstart shows `video_url`
                            parts; google/gemini-3-flash-preview is the stronger one). MiniMax on GMI (M2.x) is
                            text-only. If a model rejects `video_url`, falls back to 1 fps frames as images (no audio).

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

PROMPT = """You are a short-form video editor reverse-engineering a viral podcast clip so another AI can
re-create its STYLE on different footage. Watch the whole clip. Be concrete and timestamp everything (seconds).

Return ONLY a JSON object:
{
 "subject": {"topic": "", "speaker_setup": "single talking head | two-person podcast | b-roll heavy | screen recording",
             "spoken_hook": "first sentence spoken", "why_it_hooks": ""},
 "format": {"aspect": "9:16", "duration_s": 0, "framing": "how speakers are cropped/placed", "background": ""},
 "captions": {"present": true, "style": "word-by-word | phrase | sentence", "position": "", "look": "font feel, color, highlight, case",
              "animation": ""},
 "on_screen_text": [{"t": 0.0, "text": "", "role": "hook | emphasis | label"}],
 "edit_timeline": [{"t": 0.0, "event": "cut | zoom_in | zoom_out | speaker_switch | b_roll | text_overlay | sfx | music_hit", "note": ""}],
 "pacing": {"cuts_per_10s": 0, "silence_trimmed": true, "music": "none | low bed | beat-synced", "energy": "calm | medium | high"},
 "instructions_for_editor": ["ordered imperative steps an ffmpeg/LLM editor could apply to a raw 2-camera podcast recording"]
}"""

DEFAULT_MODEL = {"gemini": "gemini-2.5-flash-lite", "minimax": "MiniMax-M3.1-Flash",
                 "gmi": GMI_MODEL or "google/gemini-3.1-flash-lite-preview"}
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


def video_content(path: Path, fps: float) -> list[dict]:
    return [
        {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{b64(path)}", "fps": fps}},
        {"type": "text", "text": PROMPT},
    ]


def frames_content(path: Path, fps: float, max_frames: int = 24) -> list[dict]:
    """1 fps JPEG frames as images, each labelled with its timestamp. Needs ffmpeg. No audio."""
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
    content.append({"type": "text", "text": PROMPT + "\n(You cannot hear audio: infer spoken_hook from captions on screen.)"})
    return content


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
        else:
            try:
                text, usage = run_openai_compat(GMI_BASE_URL, GMI_API_KEY, model, video_content(path, fps))
            except Exception as e:  # noqa: BLE001
                print(f"video_url rejected ({str(e)[:200]}); falling back to frames", file=sys.stderr)
                mode = "frames"
                text, usage = run_openai_compat(GMI_BASE_URL, GMI_API_KEY, model, frames_content(path, fps))
    else:
        sys.exit("--provider gemini|minimax|gmi")

    secs = time.time() - t0
    try:
        spec = extract_json(text)
    except Exception:  # noqa: BLE001
        print("could not parse JSON; raw output:\n", text[:3000])
        raise
    price = PRICE_IN_PER_M[provider]
    cost = f"~${(usage['in'] or 0) * price / 1e6:.4f} input" if price and usage.get("in") else "n/a"
    print(json.dumps(spec, indent=1))
    print(f"\n[{provider}/{model} {mode}] {secs:.1f}s  tokens in={usage['in']} out={usage['out']}  cost {cost}", file=sys.stderr)
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"{path.stem}.{provider}.json"
    out.write_text(json.dumps({"provider": provider, "model": model, "mode": mode, "usage": usage, "seconds": secs, "spec": spec}, indent=1))
    print(f"saved -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
