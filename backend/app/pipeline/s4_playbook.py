"""Stage 4 — PLAYBOOK (team B)

ViralSet -> Playbook. One LLM call over the compact viral records.
Prompt lives in prompts/playbook.md.
"""

from __future__ import annotations

from ..config import use_fixture
from ..contracts import CaptionStyle, Playbook, ViralSet
from ..fixtures import load
from ..llm import complete_json

MAX_VIDEOS = 60


def run(viral: ViralSet) -> Playbook:
    if use_fixture("playbook"):
        return load("playbook", Playbook)

    top = sorted(viral.videos, key=lambda v: v.views_rate_per_followers, reverse=True)[:MAX_VIDEOS]
    if not top:
        return Playbook(hook_patterns=[], on_screen_text_style="No recent reference data",
                        ideal_duration_s=45, pacing_wps=0, caption_formula="Describe the clip accurately.",
                        caption_style=CaptionStyle())
    records = [
        {
            "id": v.id,
            "platform": v.platform,
            "published_at": v.published_at,
            "hook": v.hook_text,
            "on_screen": v.on_screen_text,
            "caption": v.caption,
            "duration_s": v.duration,
            "wps": v.words_per_second,
            "views": v.views,
            "views_per_follower_pct": v.views_rate_per_followers,
            "level": v.granularity,
            "text_observations": [o.model_dump() for o in v.text_observations],
        }
        for v in top
    ]
    data = complete_json("playbook", videos=records, count=len(records))
    # Caption customization is optional: malformed LLM style output falls back.
    raw_style = data.pop("caption_style", None)
    try:
        style = CaptionStyle.model_validate(raw_style) if raw_style else CaptionStyle()
    except ValueError:
        style = CaptionStyle()
    available = {v.id: v for v in top}
    style.evidence_video_ids = [i for i in dict.fromkeys(style.evidence_video_ids) if i in available]
    if not style.evidence_video_ids:
        style = CaptionStyle()
    else:
        style.evidence_basis = ("ocr_samples" if any(available[i].text_observations
                                for i in style.evidence_video_ids) else "text_only")
    return Playbook.model_validate({**data, "caption_style": style})
