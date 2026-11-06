"""Stage 5 — SCORE + DIRECT (team C)

(Transcript, Understanding, Playbook) -> ClipSet (top 3 with hook rewrites).

One LLM call: every candidate moment vs. every playbook pattern. The prompt
gets the exact transcript text of each moment so the hook rewrite is grounded.
"""

from __future__ import annotations

from ..config import use_fixture
import re

from ..contracts import CaptionStyle, ClipSet, Playbook, Transcript, Understanding
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
    # Preserve the stage-4 style if stage 5 omits it or suggests invalid settings.
    for record in data.get("clips", []):
        base = pb.caption_style or CaptionStyle()
        raw = record.get("render_style")
        try:
            style = CaptionStyle.model_validate({**base.model_dump(), **raw}) if isinstance(raw, dict) else base.model_copy(deep=True)
        except ValueError:
            style = base.model_copy(deep=True)
        # Stage 5 cannot invent evidence or promote text-only evidence to visual measurements.
        style.evidence_video_ids = list(base.evidence_video_ids)
        style.evidence_basis = base.evidence_basis
        record["render_style"] = style.model_dump()
        text = text_between(t, record["start"], record["end"])
        vocabulary = set(re.findall(r"\w+", text.casefold()))
        keywords = record.get("emphasis_keywords")
        keywords = keywords if isinstance(keywords, list) else []
        record["emphasis_keywords"] = list(dict.fromkeys(
            k for k in keywords if isinstance(k, str) and k.casefold() in vocabulary
        ))[:20]
    clips = ClipSet.model_validate(data)
    clips.clips = sorted(clips.clips, key=lambda c: c.score, reverse=True)[:TOP_N]
    return clips


def text_between(t: Transcript, start: float, end: float) -> str:
    return " ".join(s.text for s in t.segments if s.end > start and s.start < end)
