"""Stage 1 — INGEST (team A)

In:  YouTube URL
Out: Transcript  (timed segments + local mp4 path; stage 6 needs the mp4)

yt-dlp downloads the mp4 (<=1080p) and the English captions as json3 into
WORK_DIR/ingest/<video_id>/. Human captions are preferred over auto ones.
Results are cached per video id, so re-running is instant. Two jobs for the
same video at once would both download into the same folder and race on the
.part files, so the download runs under a per-video lock and the second job
just picks up the cache.

Env knobs (optional):
  INGEST_NO_VIDEO=1            captions only (fast, for iterating on stage 2)
  YTDLP_COOKIES_BROWSER=chrome if YouTube says "sign in to confirm you're not a bot"
"""

from __future__ import annotations

import json
import os
import threading
from collections import defaultdict
from pathlib import Path

from ..config import WORK_DIR, use_fixture
from ..contracts import Segment, Transcript
from ..fixtures import load


def run(url: str) -> Transcript:
    if use_fixture("ingest"):
        return load("transcript", Transcript)
    return ingest(url)


# --------------------------------------------------------------------------- yt-dlp
def _ydl_base() -> dict:
    opts: dict = {"quiet": True, "no_warnings": True}
    browser = os.getenv("YTDLP_COOKIES_BROWSER")
    if browser:
        opts["cookiesfrombrowser"] = (browser,)
    return opts


def _pick_lang(info: dict) -> tuple[str | None, bool]:
    """Prefer human English subs, then auto English. Returns (lang, is_auto)."""
    manual = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}
    for lang in ("en", "en-US", "en-GB"):
        if lang in manual:
            return lang, False
    for lang in manual:
        if lang.startswith("en"):
            return lang, False
    for lang in ("en-orig", "en"):  # en-orig = original ASR, not a machine translation
        if lang in auto:
            return lang, True
    return None, False


_locks: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)
_locks_guard = threading.Lock()


def _lock_for(video_id: str) -> threading.Lock:
    with _locks_guard:
        return _locks[video_id]


def ingest(url: str) -> Transcript:
    import yt_dlp

    want_video = os.getenv("INGEST_NO_VIDEO", "") not in ("1", "true", "yes")

    with yt_dlp.YoutubeDL(_ydl_base()) as ydl:
        info = ydl.extract_info(url, download=False)

    out = WORK_DIR / "ingest" / info["id"]
    out.mkdir(parents=True, exist_ok=True)
    cache = out / "transcript.json"
    video_path = out / "video.mp4"

    def cached() -> Transcript | None:
        if cache.exists() and (not want_video or video_path.exists()):
            t = Transcript.model_validate_json(cache.read_text())
            if video_path.exists():
                t.video_path = str(video_path.resolve())
            return t
        return None

    if (t := cached()) is not None:
        print(f"[ingest] cached: {cache}")
        return t

    lock = _lock_for(info["id"])
    if not lock.acquire(blocking=False):
        print(f"[ingest] another job is downloading {info['id']}; waiting")
        lock.acquire()
    try:
        if (t := cached()) is not None:  # the other job finished while we waited
            print(f"[ingest] cached: {cache}")
            return t
        return _download(url, info, out, want_video)
    finally:
        lock.release()


def _download(url: str, info: dict, out: Path, want_video: bool) -> Transcript:
    import yt_dlp

    cache = out / "transcript.json"
    video_path = out / "video.mp4"
    lang, is_auto = _pick_lang(info)
    opts = {
        **_ydl_base(),
        "outtmpl": str(out / "video.%(ext)s"),
        "skip_download": not want_video,
        "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
        "merge_output_format": "mp4",
    }
    if lang:
        opts.update({"writesubtitles": not is_auto, "writeautomaticsub": is_auto,
                     "subtitleslangs": [lang], "subtitlesformat": "json3"})
    print(f"[ingest] {info.get('title')!r} ({info.get('duration')}s) captions={lang} auto={is_auto} video={want_video}")
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])

    subs = sorted(out.glob("video.*.json3"))
    if not subs:
        raise RuntimeError("no English captions on this video; pick another podcast")
    segments = parse_json3(subs[0])
    if not segments:
        raise RuntimeError(f"captions file was empty: {subs[0]}")

    t = Transcript(
        source_url=url,
        title=info.get("title") or "",
        duration=float(info.get("duration") or segments[-1].end),
        video_path=str(video_path.resolve()) if video_path.exists() else None,
        segments=segments,
    )
    cache.write_text(t.model_dump_json(indent=1))
    print(f"[ingest] {len(segments)} segments -> {cache}")
    return t


# --------------------------------------------------------------------------- captions
def parse_json3(path: Path) -> list[Segment]:
    """YouTube json3 captions -> timed segments. Drops newline-only events and
    clamps the overlap auto-captions have (line N stays up while N+1 starts)."""
    events = json.loads(Path(path).read_text(encoding="utf-8")).get("events", [])
    segs: list[Segment] = []
    for ev in events:
        parts = [s.get("utf8", "") for s in ev.get("segs") or []]
        text = " ".join("".join(parts).split())
        if not text:
            continue
        start = ev.get("tStartMs", 0) / 1000
        end = start + ev.get("dDurationMs", 0) / 1000
        segs.append(Segment(start=round(start, 3), end=round(end, 3), text=text))

    segs.sort(key=lambda s: s.start)
    for a, b in zip(segs, segs[1:]):
        if b.start > a.start:
            a.end = min(a.end, b.start)
    return segs
