"""Stage 4 — PLAYBOOK (team B)

In:  ViralSet
Out: Playbook  (hook patterns, on-screen text style, duration, pacing, caption formula)

Notes:
- `llm.complete_json("playbook", ...)` fills prompts/playbook.md.
- Reduce each video to a compact record (hook, on_screen, caption, duration,
  wps, views, views_rate_per_followers) before prompting; ~60 videos fits.
"""

from __future__ import annotations

from ..config import use_fixture
from ..contracts import Playbook, ViralSet
from ..fixtures import load


def run(viral: ViralSet) -> Playbook:
    if use_fixture("playbook"):
        return load("playbook", Playbook)
    raise NotImplementedError("team B")
