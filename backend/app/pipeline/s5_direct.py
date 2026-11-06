"""Stage 5 — SCORE + DIRECT (team C)

In:  Transcript, Understanding (candidate_moments), Playbook
Out: ClipSet  (top 3 clips with start/end, hook rewrite, on-screen lines, caption)

Notes:
- `llm.complete_json("direct", ...)` fills prompts/direct.md.
- Give the prompt the exact transcript text of each candidate moment so the
  hook rewrite is grounded in what was said.
"""

from __future__ import annotations

from ..config import use_fixture
from ..contracts import ClipSet, Playbook, Transcript, Understanding
from ..fixtures import load


def run(t: Transcript, u: Understanding, pb: Playbook) -> ClipSet:
    if use_fixture("direct"):
        return load("clips", ClipSet)
    raise NotImplementedError("team C")
