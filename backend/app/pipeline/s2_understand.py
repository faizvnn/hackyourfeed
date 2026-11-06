"""Stage 2 — UNDERSTAND (team A)

Transcript -> Understanding (niche, keyword sets for Oriane, candidate moments).

One LLM call over the transcript. The keyword sets are the ONLY thing Oriane
sees, so the prompt (prompts/understand.md) matters more than this code.
"""

from __future__ import annotations

from ..config import use_fixture
from ..contracts import Transcript, Understanding
from ..fixtures import load
from ..llm import complete_json

MAX_CHARS = 60_000  # ~15k tokens; a 2h podcast is ~100k chars, so we thin it


def run(transcript: Transcript) -> Understanding:
    if use_fixture("understand"):
        return load("understanding", Understanding)

    data = complete_json(
        "understand",
        title=transcript.title,
        duration_min=round(transcript.duration / 60),
        transcript=_format(transcript),
    )
    return Understanding.model_validate(data)


def _format(t: Transcript) -> str:
    """'[mm:ss] text' lines, dropped evenly if the transcript is too long."""
    lines = [f"[{int(s.start // 60):02d}:{int(s.start % 60):02d}] {s.text}" for s in t.segments]
    text = "\n".join(lines)
    if len(text) <= MAX_CHARS:
        return text
    keep_every = len(text) // MAX_CHARS + 1
    return "\n".join(lines[::keep_every])
