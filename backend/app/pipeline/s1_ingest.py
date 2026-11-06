"""Stage 1 — INGEST (team A)

YouTube URL -> Transcript (timed segments + local mp4).

Uses yt-dlp for both the video and the auto-captions. If captions are missing,
fall back to Whisper (not wired; add it here if a demo podcast has no captions).
"""

from __future__ import annotations

import json
import subprocess

from ..config import WORK_DIR, use_fixture
from ..contracts import Segment, Transcript
from ..fixtures import load


def run(url: str) -> Transcript:
    if use_fixture("ingest"):
        return load("transcript", Transcript)

    out_dir = WORK_DIR / "ingest"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. metadata + captions (json3 format gives word-level timing)
    info = json.loads(
        subprocess.check_output(["yt-dlp", "-j", "--no-warnings", url], text=True)
    )
    video_id = info["id"]
    subprocess.run(
        [
            "yt-dlp", "--no-warnings",
            "--write-auto-sub", "--write-sub", "--sub-lang", "en", "--sub-format", "json3",
            "--skip-download", "-o", str(out_dir / "%(id)s"), url,
        ],
        check=True,
    )
    # 2. video (720p is plenty for a 9:16 crop)
    video_path = out_dir / f"{video_id}.mp4"
    if not video_path.exists():
        subprocess.run(
            ["yt-dlp", "--no-warnings", "-f", "bv*[height<=720]+ba/b[height<=720]",
             "--merge-output-format", "mp4", "-o", str(video_path), url],
            check=True,
        )

    sub_file = next(out_dir.glob(f"{video_id}*.json3"), None)
    if sub_file is None:
        raise RuntimeError("no English captions found; add a Whisper fallback here")
    segments = _parse_json3(json.loads(sub_file.read_text()))

    return Transcript(
        source_url=url,
        title=info.get("title", ""),
        duration=float(info.get("duration") or 0),
        video_path=str(video_path),
        segments=segments,
    )


def _parse_json3(data: dict) -> list[Segment]:
    """YouTube json3 -> ~one Segment per caption event. Merge tiny events."""
    segs: list[Segment] = []
    for ev in data.get("events", []):
        text = "".join(s.get("utf8", "") for s in ev.get("segs", [])).replace("\n", " ").strip()
        if not text or "tStartMs" not in ev:
            continue
        start = ev["tStartMs"] / 1000
        end = start + ev.get("dDurationMs", 2000) / 1000
        if segs and start - segs[-1].end < 0.3 and len(segs[-1].text) < 160:
            segs[-1] = Segment(start=segs[-1].start, end=end, text=f"{segs[-1].text} {text}")
        else:
            segs.append(Segment(start=start, end=end, text=text))
    return segs
