"""Stage 6 — RENDER (team C)

(Transcript, ClipSet) -> ClipSet with render_path/render_url filled in.

Floor: ffmpeg cut + 9:16 center crop + burned hook line (first 2.5 s) + captions.
Ceiling: hand the cut to Compound.mov for polish (see compound_polish()).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..config import PUBLIC_BASE_URL, RENDER_DIR, use_fixture
from ..contracts import Clip, ClipSet, Transcript
from ..fixtures import load

FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"  # change on Linux (GMI box)


def run(job_id: str, t: Transcript, clips: ClipSet) -> ClipSet:
    if use_fixture("render"):
        return load("clips_rendered", ClipSet)
    if not t.video_path:
        raise RuntimeError("transcript has no video_path; stage 1 must download the mp4")

    out_dir = RENDER_DIR / job_id
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, clip in enumerate(clips.clips):
        srt = out_dir / f"clip{i}.srt"
        srt.write_text(to_srt(t, clip))
        out = out_dir / f"clip{i}.mp4"
        ffmpeg_cut(Path(t.video_path), clip, srt, out)
        clip.render_path = str(out)
        clip.render_url = f"{PUBLIC_BASE_URL}/renders/{job_id}/clip{i}.mp4"
    return clips


def ffmpeg_cut(src: Path, clip: Clip, srt: Path, out: Path) -> None:
    hook = clip.hook_rewrite.replace("'", "\\'").replace(":", "\\:")
    vf = ",".join(
        [
            "crop=ih*9/16:ih",                      # center crop to 9:16
            "scale=1080:1920",
            f"drawtext=fontfile='{FONT}':text='{hook}':fontsize=64:fontcolor=white:"
            "borderw=4:bordercolor=black:x=(w-text_w)/2:y=h*0.18:enable='lt(t,2.5)'",
            f"subtitles='{srt}':force_style='Fontsize=18,Alignment=2,MarginV=160,Outline=2,Bold=1'",
        ]
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-ss", str(clip.start), "-to", str(clip.end), "-i", str(src),
            "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac",
            str(out),
        ],
        check=True,
        capture_output=True,
    )


def to_srt(t: Transcript, clip: Clip) -> str:
    """Transcript segments inside the clip, re-based to t=0."""
    lines, n = [], 1
    for s in t.segments:
        if s.end <= clip.start or s.start >= clip.end:
            continue
        a, b = max(s.start, clip.start) - clip.start, min(s.end, clip.end) - clip.start
        lines.append(f"{n}\n{_ts(a)} --> {_ts(b)}\n{s.text}\n")
        n += 1
    return "\n".join(lines)


def _ts(sec: float) -> str:
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}".replace(".", ",")


def compound_polish(clip_path: Path, clip: Clip) -> str | None:
    """TODO(team C): upload the cut to Compound.mov and return a URL.
    Check whether Compound takes source footage; if it only generates from
    prompts, use clip.hook_rewrite + clip.on_screen_lines to make an intro card."""
    return None
