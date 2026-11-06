"""Stage 2 — UNDERSTAND (team A)

In:  Transcript
Out: Understanding  (niche, keyword sets for Oriane, topic map)

This stage does NOT pick clips. It runs before we know what is viral, so it
only describes the episode and produces search terms. Stage 5 picks clips
with the playbook in hand.

Notes:
- `llm.complete_json("understand", ...)` fills prompts/understand.md and returns a dict.
- Three keyword granularities: niche (broad), topic (specific to this episode),
  entity (guest / company / product names).
- Keywords are the only thing Oriane sees (keyword search, not semantic),
  so they should be words people literally say in short-form videos.
- topic_map = which minutes cover which topic; stage 5 uses it to navigate.
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
