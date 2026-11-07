"""Stage 4 — PLAYBOOK (team B)

In:  ViralSet
Out: Playbook  (hook patterns, on-screen text style, duration, pacing, caption formula)

- Reduces each ViralVideo to a compact record and prompts prompts/playbook.md through
  `llm.complete_json("playbook", ...)`. Top MAX_VIDEOS by views go in.
- If `scripts/analyze_clip.py` has already produced an edit spec for any of these videos
  (work/analysis/<id>.gmi.json), it is passed as `edit_specs` so the playbook can describe
  the editing (captions, cuts, zooms), not just the words. Nothing is downloaded here.
"""

from __future__ import annotations

import json
import statistics
import sys

from .. import llm
from ..config import WORK_DIR, use_fixture
from ..contracts import HookPattern, Playbook, ViralSet, ViralVideo
from ..fixtures import load

MAX_VIDEOS = 60
MAX_EDIT_SPECS = 5
MIN_PATTERNS, MAX_PATTERNS = 4, 6


def run(viral: ViralSet) -> Playbook:
    if use_fixture("playbook"):
        return load("playbook", Playbook)
    if not viral.videos:
        raise ValueError("stage 4 got an empty ViralSet")

    top = sorted(viral.videos, key=lambda v: v.views, reverse=True)[:MAX_VIDEOS]
    records = [compact(v) for v in top]
    specs = edit_specs(top)
    print(f"stage 4: prompting with {len(records)} videos, {len(specs)} edit specs", file=sys.stderr)

    out = llm.complete_json("playbook", videos=records, count=len(records), edit_specs=specs or "(none)")
    return _coerce(out, top)


# ---------------------------------------------------------------- helpers ---
def compact(v: ViralVideo) -> dict:
    return {
        "id": v.id,
        "hook": v.hook_text,
        "on_screen": v.on_screen_text[:5],
        "caption": v.caption[:160],
        "hashtags": v.hashtags[:6],
        "duration": v.duration,
        "wps": v.words_per_second,
        "views": v.views,
        "vrpf": v.views_rate_per_followers,
        "platform": v.platform,
        "handle": v.handle,
        "granularity": v.granularity,
    }


def edit_specs(videos: list[ViralVideo]) -> list[dict]:
    """Edit specs produced earlier by scripts/analyze_clip.py --provider gmi, matched by video id."""
    found = []
    for v in videos:
        p = WORK_DIR / "analysis" / f"{v.id}.gmi.json"
        if p.exists():
            try:
                spec = json.loads(p.read_text()).get("spec") or {}
            except (OSError, ValueError):
                continue
            if spec:
                found.append({"id": v.id, "hook": v.hook_text, **spec})
        if len(found) >= MAX_EDIT_SPECS:
            break
    return found


def _coerce(out: dict, videos: list[ViralVideo]) -> Playbook:
    """Fill gaps the model may leave so the result always validates."""
    by_hook = {v.hook_text.strip().lower(): v for v in videos}
    patterns = []
    for p in out.get("hook_patterns") or []:
        examples = [e for e in (p.get("examples") or []) if isinstance(e, str) and e.strip()]
        views = [by_hook[e.strip().lower()].views for e in examples if e.strip().lower() in by_hook]
        avg = int(p.get("avg_views") or 0) or (int(statistics.mean(views)) if views else 0)
        patterns.append(HookPattern(name=str(p.get("name", "")).strip() or "untitled",
                                    description=str(p.get("description", "")).strip(),
                                    examples=examples, avg_views=avg))
    patterns = patterns[:MAX_PATTERNS]
    if len(patterns) < MIN_PATTERNS:
        print(f"stage 4: model returned {len(patterns)} patterns (want {MIN_PATTERNS}-{MAX_PATTERNS})", file=sys.stderr)

    third = max(3, len(videos) // 3)
    top = videos[:third]
    durations = [v.duration for v in top if v.duration]
    wps = [v.words_per_second for v in top if v.words_per_second]

    return Playbook(
        hook_patterns=patterns,
        on_screen_text_style=str(out.get("on_screen_text_style", "")).strip(),
        ideal_duration_s=float(out.get("ideal_duration_s") or (statistics.median(durations) if durations else 0)),
        pacing_wps=float(out.get("pacing_wps") or (statistics.median(wps) if wps else 0)),
        caption_formula=str(out.get("caption_formula", "")).strip(),
        takeaways=[str(t) for t in (out.get("takeaways") or [])][:6],
    )
