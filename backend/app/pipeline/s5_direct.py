"""Stage 5 — SCORE + DIRECT (team C)

(Transcript, Understanding, Playbook) -> ClipSet (top 3 with hook rewrites).

One LLM call: every candidate moment vs. every playbook pattern. The prompt
gets the exact transcript text of each moment so the hook rewrite is grounded.
"""

from __future__ import annotations

from ..config import use_fixture
from ..contracts import ClipSet, Playbook, Transcript, Understanding
from ..fixtures import load
from ..llm import complete_json

TOP_N = 3


def run(t: Transcript, u: Understanding, pb: Playbook) -> ClipSet:
    if use_fixture("direct"):
        return load("clips", ClipSet)

    moments = [
        {
            "start": m.start,
            "end": m.end,
            "summary": m.summary,
            "why": m.why,
            "text": text_between(t, m.start, m.end),
        }
        for m in u.candidate_moments
    ]
    data = complete_json(
        "direct",
        niche=u.niche,
        playbook=pb.model_dump(),
        moments=moments,
        top_n=TOP_N,
    )
    clips = ClipSet.model_validate(data)
    clips.clips = sorted(clips.clips, key=lambda c: c.score, reverse=True)[:TOP_N]
    return clips


def text_between(t: Transcript, start: float, end: float) -> str:
    return " ".join(s.text for s in t.segments if s.end > start and s.start < end)
