"""Stage 6 (experimental): adaptive libass captions, full-screen 9:16 crop.

Enabled with RENDER_ENGINE=adaptive (see config.py); s6_render.run() dispatches
here. Off by default, the classic Pillow-overlay render in s6_render.py stays
the production path until this one is judged better. Needs ffmpeg built with
libass (`ass` filter) and ffprobe. See backend/RENDER.md.

Same signature as the classic run(job_id, Transcript, ClipSet). Results fill
render_path/render_url; individual failures fill render_error without
discarding successful clips.

prepare() + render_clip() are the per-clip building blocks; s6_render.render_mixed
uses them when RENDER_ENGINE assigns engines per clip (adaptive,adaptive,classic).
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ..config import PUBLIC_BASE_URL, RENDER_DIR, use_fixture
from ..contracts import Clip, ClipSet, Transcript
from ..fixtures import load
from ..render_subtitles import make_ass, to_srt

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RenderOptions:
    width: int = 720
    height: int = 1280
    fps: int = 30
    layout: str = "crop"
    crop_center_x: float = 0.5  # normalized center in the original frame
    font: str = "Arial" if os.name == "nt" else "DejaVu Sans"
    hook_seconds: float = 2.0
    timeout: float = 300
    # Honour FFMPEG_BIN/FFPROBE_BIN even when options are built directly (tests, library use), so a
    # libass-capable build configured in .env is used instead of whatever `ffmpeg` is on PATH.
    ffmpeg: str = field(default_factory=lambda: os.getenv("FFMPEG_BIN", "ffmpeg"))
    ffprobe: str = field(default_factory=lambda: os.getenv("FFPROBE_BIN", "ffprobe"))

    @classmethod
    def from_env(cls) -> RenderOptions:
        return cls(
            layout=os.getenv("RENDER_LAYOUT", "crop"),
            crop_center_x=float(os.getenv("RENDER_CROP_CENTER_X", "0.5")),
            font=os.getenv("RENDER_FONT_NAME", cls.font),
            ffmpeg=os.getenv("FFMPEG_BIN", "ffmpeg"),
            ffprobe=os.getenv("FFPROBE_BIN", "ffprobe"),
            timeout=float(os.getenv("RENDER_TIMEOUT_SECONDS", "300")),
        )

    def validate(self) -> None:
        if self.layout not in {"blur", "crop"}:
            raise ValueError("RENDER_LAYOUT must be blur or crop")
        if not math.isfinite(self.crop_center_x) or not 0 <= self.crop_center_x <= 1:
            raise ValueError("crop_center_x must be between 0 and 1")
        if (self.width <= 0 or self.height <= 0 or self.width % 2 or self.height % 2
                or self.width * 16 != self.height * 9):
            raise ValueError("render dimensions must be positive, even and 9:16")
        if self.fps <= 0 or not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError("fps and timeout must be positive")
        if not math.isfinite(self.hook_seconds) or self.hook_seconds < 0:
            raise ValueError("hook_seconds must be finite and nonnegative")
        if any(c in self.font for c in ",\r\n"):
            raise ValueError("font must be a font family, not an ASS style expression")


def _execute(args: list[str], *, timeout: float, cwd: Path | None = None) -> str:
    try:
        return subprocess.run(
            args, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, check=True,
        ).stdout
    except FileNotFoundError as exc:
        raise RuntimeError(f"Executable not found: {args[0]}. Install FFmpeg and FFprobe.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{Path(args[0]).name} exceeded {timeout:g}s") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"{Path(args[0]).name} failed: {(exc.stderr or '')[-1800:]}") from exc


def has_libass(ffmpeg: str = "ffmpeg") -> bool:
    """True when this ffmpeg build has the libass `ass` filter the captions need."""
    try:
        r = subprocess.run([ffmpeg, "-hide_banner", "-h", "filter=ass"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.stdout.lstrip().startswith("Filter ass")


def probe(path: Path, options: RenderOptions) -> dict:
    data = json.loads(_execute([
        options.ffprobe, "-v", "error", "-show_format", "-show_streams",
        "-of", "json", str(path.resolve()),
    ], timeout=30))
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if not video:
        raise ValueError(f"No video stream in {path.name}")
    duration = float(data.get("format", {}).get("duration") or video.get("duration") or 0)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError(f"Cannot determine duration of {path.name}")
    return {"duration": duration, "video": video,
            "audio": any(s.get("codec_type") == "audio" for s in data["streams"])}


@dataclass(frozen=True)
class Source:
    """A validated source video plus everything a single clip render needs."""
    job_id: str
    transcript: Transcript
    path: Path
    info: dict
    options: RenderOptions


def prepare(job_id: str, t: Transcript, video: Path | None = None, *,
            options: RenderOptions | None = None) -> Source:
    """Validate the job, the options, the ffmpeg build and the source video once per job.
    `video` overrides transcript.video_path (the mixed-engine path passes the ingest cache)."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", job_id):
        raise ValueError("job_id must contain only letters, numbers, underscores or hyphens")
    src = video if video is not None else Path(t.video_path or "")
    if not str(src) or not src.is_file():
        raise ValueError("stage 1 must provide an existing local video_path")
    options = options or RenderOptions.from_env()
    options.validate()
    if not has_libass(options.ffmpeg):
        raise RuntimeError(
            f"{options.ffmpeg} has no libass ('ass' filter), which the adaptive captions need. Point FFMPEG_BIN "
            "(and FFPROBE_BIN) at a build that has it, e.g. brew install ffmpeg-full -> "
            "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg, or set RENDER_ENGINE=classic.")
    src = src.resolve()
    return Source(job_id, t, src, probe(src, options), options)


def render_clip(source: Source, clip: Clip, out: Path) -> None:
    """Render one clip to `out` (its .ass/.srt land next to it). Raises on any failure;
    the caller decides whether that fails the job or just this clip."""
    options = source.options
    if (not math.isfinite(clip.start) or not math.isfinite(clip.end)
            or clip.start < 0 or clip.end <= clip.start
            or clip.end > source.info["duration"] + 0.05):
        raise ValueError(f"Invalid clip range {clip.start}..{clip.end}; video is {source.info['duration']:.2f}s")
    out.parent.mkdir(parents=True, exist_ok=True)
    ass = out.with_suffix(".ass")
    ass.write_text(make_ass(source.transcript, clip, options), encoding="utf-8")
    out.with_suffix(".srt").write_text(to_srt(source.transcript, clip), encoding="utf-8")
    temporary = out.with_name(out.stem + ".partial.mp4")
    ffmpeg_cut(source.path, clip, ass, temporary, options=options)
    rendered = probe(temporary, options)
    video = rendered["video"]
    if (video["width"], video["height"]) != (options.width, options.height):
        raise RuntimeError("Rendered dimensions do not match the preset")
    if source.info["audio"] and not rendered["audio"]:
        raise RuntimeError("Rendered clip lost its audio stream")
    if abs(rendered["duration"] - (clip.end - clip.start)) > 0.25:
        raise RuntimeError("Rendered duration does not match the requested interval")
    temporary.replace(out)


def run(job_id: str, t: Transcript, clips: ClipSet, *, options: RenderOptions | None = None) -> ClipSet:
    if use_fixture("render"):
        return load("clips_rendered", ClipSet)
    if not clips.clips:
        raise ValueError("stage 5 returned no clips")
    source = prepare(job_id, t, options=options)
    out_dir = (RENDER_DIR / job_id).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    for i, clip in enumerate(clips.clips):
        clip.render_path = clip.render_url = clip.render_error = None
        try:
            out = out_dir / f"clip{i}.mp4"
            render_clip(source, clip, out)
            clip.render_path = str(out)
            clip.render_url = f"{PUBLIC_BASE_URL.rstrip('/')}/renders/{job_id}/clip{i}.mp4"
        except (ValueError, RuntimeError, OSError) as exc:
            clip.render_error = str(exc)
            log.warning("Render failed for job %s clip %s: %s", job_id, i, exc)
    (out_dir / "clips_rendered.json").write_text(clips.model_dump_json(indent=2), encoding="utf-8")
    if not any(c.render_path for c in clips.clips):
        raise RuntimeError(f"No clips rendered: {clips.clips[0].render_error}")
    return clips


def ffmpeg_cut(src: Path, clip: Clip, subtitles: Path, out: Path, *, options: RenderOptions) -> None:
    w, h = options.width, options.height
    if options.layout == "blur":
        graph = (
            f"[0:v]setpts=PTS-STARTPTS,split=2[bg][fg];"
            f"[bg]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
            "gblur=sigma=20,eq=brightness=-0.15[background];"
            f"[fg]scale={w}:{h}:force_original_aspect_ratio=decrease[foreground];"
            "[background][foreground]overlay=(W-w)/2:(H-h)/2:shortest=1[framed];"
        )
    else:
        center = options.crop_center_x
        graph = (f"[0:v]setpts=PTS-STARTPTS,scale={w}:{h}:force_original_aspect_ratio=increase,"
                 f"crop={w}:{h}:x='max(0,min(iw-ow,iw*{center}-ow/2))'[framed];")
    # Named option: a build without libass then fails with "No such filter: 'ass'" instead of the
    # misleading "No option name near '<file>'" the positional form produces.
    graph += f"[framed]setsar=1,ass=filename={subtitles.name},fps={options.fps},format=yuv420p[v]"
    _execute([
        options.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-ss", str(clip.start), "-i", str(src.resolve()), "-t", str(clip.end - clip.start),
        "-filter_complex", graph, "-map", "[v]", "-map", "0:a:0?",
        "-af", "asetpts=PTS-STARTPTS", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "23", "-c:a", "aac", "-b:a", "128k", "-ac", "2",
        "-movflags", "+faststart", str(out.resolve()),
    ], cwd=subtitles.parent.resolve(), timeout=options.timeout)


def compound_polish(clip_path: Path, clip: Clip) -> str | None:
    """Optional future adapter; a headless Compound API has not been verified."""
    return None
