"""Stage 6 — RENDER (team C)

In:  job id, Transcript (video_path), ClipSet
Out: ClipSet with render_path / render_url filled in

Floor implementation: ffmpeg cut + 9:16 + burned hook + on-screen lines + captions.
Files go under RENDER_DIR/<job_id>/clip_<n>.mp4 and are served at
{PUBLIC_BASE_URL}/renders/<job_id>/clip_<n>.mp4 by main.py.

How:
- The homebrew ffmpeg has no drawtext/subtitles filters, so every piece of
  text is rasterised with Pillow into a transparent PNG and composited with
  ffmpeg's `overlay` filter, timed with enable='between(t,a,b)'.
- Layout "fit" (default): the landscape frame sits in the middle of a 1080x1920
  canvas over a blurred, darkened copy of itself. Hook on top, on-screen lines
  under the video, captions at the bottom. Layout "crop" centre-crops to 9:16.
- Captions come from the transcript segments inside the clip, one PNG each.
- The hook stays up for the whole clip as its title; on_screen_lines are shown
  one after another across the clip after the first HOOK_SOLO_SEC seconds.

Env knobs (optional):
  RENDER_LAYOUT=fit|crop     default fit
  RENDER_FONT=/path/to.ttf   default: first of FONT_CANDIDATES that exists
  RENDER_NO_CAPTIONS=1       skip the per-segment captions
  RENDER_PRESET=veryfast     x264 preset
  RENDER_CRF=22              x264 quality (lower is better)

Ceiling (TODO): hand the cut clip to Compound.mov for its own editing.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from ..config import PUBLIC_BASE_URL, RENDER_DIR, WORK_DIR, use_fixture
from ..contracts import Clip, ClipSet, Segment, Transcript
from ..fixtures import load

W, H = 1080, 1920
HOOK_SOLO_SEC = 3.0        # on_screen_lines start after the hook had the screen to itself
TEXT_MAX_W = W - 120       # text column width
FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def run(job_id: str, t: Transcript, clips: ClipSet) -> ClipSet:
    if use_fixture("render"):
        return load("clips_rendered", ClipSet)
    return render(job_id, t, clips)


def render(job_id: str, t: Transcript, clips: ClipSet) -> ClipSet:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not on PATH (brew install ffmpeg)")
    video = locate_video(t)
    out_dir = RENDER_DIR / job_id
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[render] {len(clips.clips)} clips from {video} -> {out_dir}")

    for i, clip in enumerate(clips.clips, 1):
        name = f"clip_{i}.mp4"
        path = render_clip(video, t, clip, out_dir / name, out_dir / f"clip_{i}_overlays")
        clip.render_path = str(path)
        clip.render_url = f"{PUBLIC_BASE_URL.rstrip('/')}/renders/{job_id}/{name}"
        print(f"[render] {name}: {clip.start:.1f}-{clip.end:.1f}s  {path.stat().st_size // 1024} KB")
    return clips


# --------------------------------------------------------------------------- inputs
def locate_video(t: Transcript) -> Path:
    """transcript.video_path if it exists, else the ingest cache for this video id."""
    if t.video_path and Path(t.video_path).exists():
        return Path(t.video_path)
    m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/)([\w-]{11})", t.source_url or "")
    if m:
        cached = WORK_DIR / "ingest" / m.group(1) / "video.mp4"
        if cached.exists():
            return cached
    raise FileNotFoundError(
        f"no mp4 for this transcript (video_path={t.video_path!r}); run stage 1 without INGEST_NO_VIDEO")


def clean_text(text: str) -> str:
    """Drop caption noise: [music], [applause], speaker-change markers."""
    return " ".join(re.sub(r"\[[^\]]*\]|>>", " ", text).split())


def captions_for(t: Transcript, clip: Clip) -> list[tuple[float, float, str]]:
    """(start, end, text) relative to the clip, for every segment inside it."""
    out = []
    for s in t.segments:
        if s.end <= clip.start or s.start >= clip.end:
            continue
        text = clean_text(s.text)
        if not text:
            continue
        a = max(0.0, s.start - clip.start)
        b = min(clip.end, s.end) - clip.start
        if b - a >= 0.15:
            out.append((round(a, 3), round(b, 3), text))
    return out


# --------------------------------------------------------------------------- text -> png
def font_path() -> str | None:
    env = os.getenv("RENDER_FONT")
    if env and Path(env).exists():
        return env
    return next((p for p in FONT_CANDIDATES if Path(p).exists()), None)


def _font(size: int):
    from PIL import ImageFont

    path = font_path()
    if path:
        return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def text_png(text: str, path: Path, size: int, fill: str, max_lines: int, upper: bool = False) -> tuple[int, int]:
    """Rasterise `text` (centred, white-on-black-stroke style) to a transparent PNG.
    Shrinks the font until it fits in max_lines. Returns (width, height)."""
    from PIL import Image, ImageDraw

    if upper:
        text = text.upper()
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    while True:
        font = _font(size)
        lines = _wrap(probe, text, font, TEXT_MAX_W)
        if len(lines) <= max_lines or size <= 28:
            break
        size -= 6
    stroke = max(3, size // 12)
    line_h = int(size * 1.25)
    width = TEXT_MAX_W + 2 * stroke
    height = line_h * len(lines) + 2 * stroke
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        x = width // 2
        y = stroke + i * line_h + line_h // 2
        draw.text((x, y), line, font=font, fill=fill, anchor="mm",
                  stroke_width=stroke, stroke_fill="black")
    img.save(path)
    return width, height


# --------------------------------------------------------------------------- ffmpeg
def _base_filter(layout: str) -> str:
    if layout == "crop":
        return f"[0:v]crop=ih*{W}/{H}:ih,scale={W}:{H},setsar=1[base]"
    return (
        "[0:v]split=2[bg][fg];"
        f"[bg]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=24:4,eq=brightness=-0.12[bgb];"
        f"[fg]scale={W}:-2[fgs];"
        "[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1[base]"
    )


def render_clip(video: Path, t: Transcript, clip: Clip, out: Path, work: Path) -> Path:
    work.mkdir(parents=True, exist_ok=True)
    dur = clip.end - clip.start
    layout = os.getenv("RENDER_LAYOUT", "fit")

    # (png path, y, show from, show to)
    overlays: list[tuple[Path, int, float, float]] = []

    hook_png = work / "hook.png"
    _, h = text_png(clip.hook_rewrite, hook_png, size=78, fill="white", max_lines=4, upper=True)
    overlays.append((hook_png, max(60, 430 - h // 2), 0.0, dur))

    lines = [ln for ln in clip.on_screen_lines if ln.strip()]
    if lines and dur > HOOK_SOLO_SEC + 1:
        span = (dur - HOOK_SOLO_SEC) / len(lines)
        for i, line in enumerate(lines):
            png = work / f"line_{i}.png"
            text_png(line, png, size=64, fill="#FFE600", max_lines=2, upper=True)
            a = HOOK_SOLO_SEC + i * span
            overlays.append((png, 1300, round(a, 3), round(a + span, 3)))

    if os.getenv("RENDER_NO_CAPTIONS", "") not in ("1", "true", "yes"):
        for i, (a, b, text) in enumerate(captions_for(t, clip)):
            png = work / f"cap_{i}.png"
            text_png(text, png, size=56, fill="white", max_lines=3)
            overlays.append((png, 1500, a, b))

    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-ss", f"{clip.start:.3f}", "-t", f"{dur:.3f}", "-i", str(video)]
    for png, _, _, _ in overlays:
        cmd += ["-i", str(png)]

    parts = [_base_filter(layout)]
    prev = "base"
    for n, (_, y, a, b) in enumerate(overlays, 1):
        label = f"v{n}"
        parts.append(f"[{prev}][{n}:v]overlay=(W-w)/2:{y}:enable='between(t,{a},{b})'[{label}]")
        prev = label
    cmd += ["-filter_complex", ";".join(parts), "-map", f"[{prev}]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", os.getenv("RENDER_PRESET", "veryfast"),
            "-crf", os.getenv("RENDER_CRF", "22"), "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)]

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not out.exists():
        raise RuntimeError(f"ffmpeg failed for {out.name}: {r.stderr.strip()[-800:]}")
    shutil.rmtree(work, ignore_errors=True)  # the PNGs are baked in; don't serve them next to the mp4
    return out
