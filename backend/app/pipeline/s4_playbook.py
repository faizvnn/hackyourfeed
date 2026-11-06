"""Stage 4 — PLAYBOOK (team B)

ViralSet -> Playbook. One LLM call over the compact viral records.
Prompt lives in prompts/playbook.md.
"""

from __future__ import annotations

from ..config import use_fixture
from ..contracts import Playbook, ViralSet
from ..fixtures import load
from ..llm import complete_json

MAX_VIDEOS = 60


def run(viral: ViralSet) -> Playbook:
    if use_fixture("playbook"):
        return load("playbook", Playbook)

    top = sorted(viral.videos, key=lambda v: v.views_rate_per_followers, reverse=True)[:MAX_VIDEOS]
    records = [
        {
            "hook": v.hook_text,
            "on_screen": v.on_screen_text,
            "caption": v.caption,
            "duration_s": v.duration,
            "wps": v.words_per_second,
            "views": v.views,
            "views_per_follower_pct": v.views_rate_per_followers,
            "level": v.granularity,
        }
        for v in top
    ]
    data = complete_json("playbook", videos=records, count=len(records))
    return Playbook.model_validate(data)
