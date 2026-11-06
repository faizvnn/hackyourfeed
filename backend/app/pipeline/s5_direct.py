"""Stage 5 — SCORE + DIRECT (team C)

In:  Transcript (full), Understanding (niche, topic_map), Playbook
Out: ClipSet  (top 3 clips with start/end, hook rewrite, on-screen lines, caption)

This is where clips get picked. The LLM scans the whole transcript knowing
the exact hooks, length and pacing that are performing right now, instead of
scoring moments that were chosen blind in stage 2.

Notes:
- `llm.complete_json("direct", ...)` fills prompts/direct.md.
- Pass the transcript as "[mm:ss] text" lines so start/end come back grounded.
  A 45-min episode is ~10k tokens; a 2h one needs thinning or a per-topic pass
  using understanding.topic_map.
"""

from __future__ import annotations

from ..config import use_fixture
from ..contracts import ClipSet, Playbook, Transcript, Understanding
from ..fixtures import load


def run(t: Transcript, u: Understanding, pb: Playbook) -> ClipSet:
    if use_fixture("direct"):
        return load("clips", ClipSet)
    raise NotImplementedError("team C")
