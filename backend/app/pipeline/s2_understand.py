"""Stage 2 — UNDERSTAND (team A)

In:  Transcript
Out: Understanding  (niche, keyword sets for Oriane, 15-20 candidate moments)

Notes:
- `llm.complete_json("understand", ...)` fills prompts/understand.md and returns a dict.
- The keyword sets are the only thing Oriane sees (keyword search, not semantic),
  so they should be words people literally say in short-form videos.
- A 2h transcript is ~100k chars; thin it before prompting.
"""

from __future__ import annotations

from ..config import use_fixture
from ..contracts import Transcript, Understanding
from ..fixtures import load


def run(transcript: Transcript) -> Understanding:
    if use_fixture("understand"):
        return load("understanding", Understanding)
    raise NotImplementedError("team A")
