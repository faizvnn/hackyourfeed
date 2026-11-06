"""Stage 1 — INGEST (team A)

In:  YouTube URL
Out: Transcript  (timed segments + local mp4 path; stage 6 needs the mp4)

Notes:
- yt-dlp can give both the mp4 and auto-captions (`--write-auto-sub --sub-format json3`).
- Save downloads under WORK_DIR / "ingest".
"""

from __future__ import annotations

from ..config import use_fixture
from ..contracts import Transcript
from ..fixtures import load


def run(url: str) -> Transcript:
    if use_fixture("ingest"):
        return load("transcript", Transcript)
    raise NotImplementedError("team A")
