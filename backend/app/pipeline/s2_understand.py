"""Stage 2 — UNDERSTAND (team A)

In:  Transcript
Out: Understanding  (niche, keyword sets for Oriane, topic map)

This stage does NOT pick clips. It runs before we know what is viral, so it
only describes the episode and produces search terms. Stage 5 picks clips
with the playbook in hand.

How:
- The transcript is thinned into ~30s blocks, each prefixed with its start
  second, and capped at THIN_BUDGET chars (a 2h episode still fits).
- One LLM call fills prompts/understand.md.
- Output is cleaned before validation: keywords lowercased/deduped/short,
  handles stripped of '@', topic_map clamped to the episode and sorted.
"""

from __future__ import annotations

import json

from .. import llm
from ..config import use_fixture
from ..contracts import KeywordSets, TopicSection, Transcript, Understanding
from ..fixtures import load

BLOCK_SEC = 30
THIN_BUDGET = 60_000  # chars of transcript sent to the model


def run(transcript: Transcript) -> Understanding:
    if use_fixture("understand"):
        return load("understanding", Understanding)
    return understand(transcript)


def understand(t: Transcript) -> Understanding:
    duration = t.duration or (t.segments[-1].end if t.segments else 0)
    thinned = thin(t)
    print(f"[understand] {len(t.segments)} segments -> {len(thinned)} chars to LLM")

    raw: dict | None = None
    last_err: Exception | None = None
    for _ in range(2):  # one retry on broken JSON
        try:
            raw = llm.complete_json("understand", title=t.title or "(untitled)",
                                    duration_min=str(round(duration / 60)), transcript=thinned)
            break
        except (ValueError, json.JSONDecodeError) as e:
            last_err = e
    if raw is None:
        raise RuntimeError(f"understand: LLM never returned valid JSON: {last_err}")

    u = clean(raw, duration)
    print(f"[understand] niche={u.niche!r} keywords={len(u.keyword_sets.niche)}/"
          f"{len(u.keyword_sets.topic)}/{len(u.keyword_sets.entity)} topic_map={len(u.topic_map)}")
    return u


# --------------------------------------------------------------------------- thinning
def thin(t: Transcript) -> str:
    """'[123] text text...' lines, one per ~BLOCK_SEC. If the episode is long,
    each block's text is truncated evenly so the whole thing fits THIN_BUDGET."""
    blocks: list[tuple[float, str]] = []
    cur: list[str] = []
    cur_start: float | None = None
    for s in t.segments:
        if cur_start is None:
            cur_start = s.start
        cur.append(s.text)
        if s.end - cur_start >= BLOCK_SEC:
            blocks.append((cur_start, " ".join(cur)))
            cur, cur_start = [], None
    if cur and cur_start is not None:
        blocks.append((cur_start, " ".join(cur)))

    for tag in ("[music]", "[Music]", "[applause]", "[Applause]", "[laughter]", "[Laughter]", ">>"):
        blocks = [(st, txt.replace(tag, "")) for st, txt in blocks]

    total = sum(len(txt) for _, txt in blocks)
    cap = THIN_BUDGET // max(len(blocks), 1) if total > THIN_BUDGET else None
    lines = []
    for st, txt in blocks:
        txt = " ".join(txt.split())
        if cap and len(txt) > cap:
            txt = txt[:cap].rsplit(" ", 1)[0] + " …"
        lines.append(f"[{int(st)}] {txt}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- cleaning
def _terms(xs, max_words: int = 4, limit: int = 10) -> list[str]:
    out: list[str] = []
    for x in xs or []:
        s = " ".join(str(x).lstrip("#").replace("_", " ").split()).strip(" .,'\"").lower()
        if s and len(s.split()) <= max_words and s not in out:
            out.append(s)
    return out[:limit]


def clean(raw: dict, duration: float) -> Understanding:
    ks = raw.get("keyword_sets") or {}
    entity = []
    for x in ks.get("entity") or []:  # keep names' original casing
        s = " ".join(str(x).lstrip("@#").split())
        if s and s.lower() not in [e.lower() for e in entity]:
            entity.append(s)

    handles = []
    for h in raw.get("competitor_handles") or []:
        h = h.get("handle", "") if isinstance(h, dict) else str(h)
        h = h.strip().lstrip("@").strip()
        if h and " " not in h and h not in handles:
            handles.append(h)

    sections: list[TopicSection] = []
    for sec in raw.get("topic_map") or []:
        try:
            st = max(0.0, min(float(sec["start"]), duration))
            en = max(0.0, min(float(sec["end"]), duration))
            topic = str(sec["topic"]).strip()
        except (KeyError, TypeError, ValueError):
            continue
        if en > st and topic:
            sections.append(TopicSection(start=round(st, 1), end=round(en, 1), topic=topic))
    sections.sort(key=lambda s: s.start)

    return Understanding(
        niche=str(raw.get("niche") or "").strip() or "podcast",
        summary=str(raw.get("summary") or "").strip(),
        topics=[str(x).strip() for x in raw.get("topics") or [] if str(x).strip()],
        competitor_handles=handles,
        keyword_sets=KeywordSets(
            niche=_terms(ks.get("niche"), max_words=2),
            topic=_terms(ks.get("topic"), max_words=4),
            entity=entity[:8],
        ),
        topic_map=sections,
    )
