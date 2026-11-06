"""Stage 6 — RENDER (team C)

In:  job id, Transcript (video_path), ClipSet
Out: ClipSet with render_path / render_url filled in

Notes:
- Write files under RENDER_DIR / job_id; they are served at
  {PUBLIC_BASE_URL}/renders/{job_id}/<file> by main.py.
- Floor: ffmpeg cut + 9:16 crop + burned hook text + captions.
  Ceiling: Compound.mov, if it accepts source footage.
"""

from __future__ import annotations

from ..config import use_fixture
from ..contracts import ClipSet, Transcript
from ..fixtures import load


def run(job_id: str, t: Transcript, clips: ClipSet) -> ClipSet:
    if use_fixture("render"):
        return load("clips_rendered", ClipSet)
    raise NotImplementedError("team C")
