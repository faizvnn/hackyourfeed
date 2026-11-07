"""Stage 5 — SCORE + DIRECT (team C)

In:  Transcript (full), Understanding (niche, topic_map), Playbook
Out: ClipSet  (top TOP_N clips with start/end, hook rewrite, on-screen lines, caption)

This is where clips get picked. The LLM scans the whole transcript knowing
the exact hooks, length and pacing that are performing right now, instead of
scoring moments that were chosen blind in stage 2.

How:
- Segments are merged into "[mm:ss] text" lines of ~LINE_SEC seconds so the
  model can quote grounded timestamps. If the episode is longer than BUDGET
  chars it is split into chunks and each chunk is directed separately; the
  candidates are then pooled.
- One LLM call per chunk fills prompts/direct.md, asking for CANDIDATES clips.
- Output is cleaned before validation: the span is realigned to open where
  the hook is actually spoken (the model's [mm:ss] arithmetic is unreliable
  and its start/end often miss the lines it quotes), times snapped to segment
  boundaries, lengths bounded by MIN_LEN..MAX_LEN, overlaps resolved by score,
  pattern names matched back to the playbook. The top TOP_N by score are returned.

Env knobs (optional):
  DIRECT_TOP_N=3     how many clips to return
"""

from __future__ import annotations

import json
import os
import re

from .. import llm
from ..align import LEAD_IN_SEC, locate
from ..config import use_fixture
from ..contracts import Clip, ClipSet, Playbook, Segment, Transcript, Understanding
from ..fixtures import load

TOP_N = int(os.getenv("DIRECT_TOP_N", "3"))
CANDIDATES = 6          # ask for more than we keep, so bad ones can be dropped
LINE_SEC = 6            # seconds of speech per transcript line sent to the model
BUDGET = 80_000         # chars of transcript per LLM call
MIN_LEN, MAX_LEN = 15.0, 90.0


def run(t: Transcript, u: Understanding, pb: Playbook) -> ClipSet:
    if use_fixture("direct"):
        return load("clips", ClipSet)
    return direct(t, u, pb)


def direct(t: Transcript, u: Understanding, pb: Playbook) -> ClipSet:
    if not t.segments:
        raise ValueError("stage 5 got a transcript with no segments")
    duration = t.duration or t.segments[-1].end
    ideal = pb.ideal_duration_s if MIN_LEN <= pb.ideal_duration_s <= MAX_LEN else 45.0

    chunks = chunk(lines(t))
    print(f"[direct] {len(t.segments)} segments -> {len(chunks)} chunk(s) to LLM")

    raw_clips: list[dict] = []
    for i, text in enumerate(chunks, 1):
        out = _ask(text, t, u, pb, ideal)
        got = out.get("clips") or []
        print(f"[direct] chunk {i}/{len(chunks)}: {len(got)} candidates")
        raw_clips.extend(c for c in got if isinstance(c, dict))

    clips = clean(raw_clips, t, pb, duration)
    if not clips:
        raise RuntimeError("direct: model returned no usable clips")
    if len(clips) < TOP_N:
        print(f"[direct] only {len(clips)} usable clips (want {TOP_N})")
    for c in clips:
        print(f"[direct] {c.score:3d}  {_mmss(c.start)}-{_mmss(c.end)}  {c.title!r}  <{c.matched_pattern}>")
    return ClipSet(clips=clips)


def _ask(transcript: str, t: Transcript, u: Understanding, pb: Playbook, ideal: float) -> dict:
    last_err: Exception | None = None
    for _ in range(2):  # one retry on broken JSON
        try:
            return llm.complete_json(
                "direct",
                niche=u.niche,
                title=t.title or "(untitled)",
                summary=u.summary,
                playbook=pb.model_dump(),
                topic_map=[s.model_dump() for s in u.topic_map],
                transcript=transcript,
                top_n=str(CANDIDATES),
                min_len=str(int(MIN_LEN)),
                max_len=str(int(MAX_LEN)),
                ideal_len=str(int(ideal)),
            )
        except (ValueError, json.JSONDecodeError) as e:
            last_err = e
    raise RuntimeError(f"direct: LLM never returned valid JSON: {last_err}")


# --------------------------------------------------------------------------- transcript -> text
def _mmss(sec: float) -> str:
    sec = max(0, int(sec))
    return f"{sec // 60:02d}:{sec % 60:02d}"


def lines(t: Transcript) -> list[str]:
    """'[mm:ss] text' lines, each covering ~LINE_SEC seconds of speech."""
    out: list[str] = []
    cur: list[str] = []
    cur_start: float | None = None
    for s in t.segments:
        text = " ".join(re.sub(r"\[[^\]]*\]|>>", " ", s.text).split())  # drop [Music], [Applause], >>
        if not text:
            continue
        if cur_start is None:
            cur_start = s.start
        cur.append(text)
        if s.end - cur_start >= LINE_SEC:
            out.append(f"[{_mmss(cur_start)}] {' '.join(cur)}")
            cur, cur_start = [], None
    if cur and cur_start is not None:
        out.append(f"[{_mmss(cur_start)}] {' '.join(cur)}")
    return out


def chunk(ls: list[str]) -> list[str]:
    """Split lines into chunks of at most BUDGET chars (an episode under BUDGET is one chunk)."""
    chunks: list[list[str]] = [[]]
    size = 0
    for line in ls:
        if size + len(line) > BUDGET and chunks[-1]:
            chunks.append([])
            size = 0
        chunks[-1].append(line)
        size += len(line) + 1
    return ["\n".join(c) for c in chunks if c]


# --------------------------------------------------------------------------- cleaning
def _snap_start(segs: list[Segment], x: float) -> float:
    """Start of the segment that contains x; if x falls in a gap, the next segment's start."""
    for s in segs:
        if s.end > x:
            return s.start
    return segs[-1].start


def _snap_end(segs: list[Segment], x: float) -> float:
    """End of the segment that contains x; if x falls in a gap, the previous segment's end."""
    prev_end: float | None = None
    for s in segs:
        if s.start > x:
            break
        if x <= s.end:
            return s.end
        prev_end = s.end
    return prev_end if prev_end is not None else segs[0].end


def _align(segs: list[Segment], start: float, end: float, hook: str, lines: list[str],
           duration: float) -> tuple[float, float]:
    """Open the clip where `hook` is actually spoken (or on the on-screen line said just before
    it, usually the setup question) and make sure the other lines fall inside it, keeping the
    model's chosen length. The model's span is kept when the hook cannot be found at all."""
    hook_at = locate(segs, hook, near=start)
    if hook_at is None:
        return start, end
    new_start, last = hook_at
    for line in lines:
        at = locate(segs, line, lo=hook_at[0] - LEAD_IN_SEC, hi=hook_at[0] + MAX_LEN, near=hook_at[0])
        if at:
            new_start, last = min(new_start, at[0]), max(last, at[1])
    new_end = min(max(last + 3.0, new_start + (end - start)), new_start + MAX_LEN, duration)
    if abs(new_start - start) >= 1.0 or abs(new_end - end) >= 1.0:
        print(f"[direct] realign {_mmss(start)}-{_mmss(end)} -> {_mmss(new_start)}-{_mmss(new_end)}: {hook[:50]!r}")
    return new_start, new_end


def _pattern(name: str, pb: Playbook) -> str:
    n = " ".join(str(name).split()).strip()
    low = n.lower()
    for p in pb.hook_patterns:
        if p.name.lower() == low:
            return p.name
    for p in pb.hook_patterns:
        if low and (low in p.name.lower() or p.name.lower() in low):
            return p.name
    return n or (pb.hook_patterns[0].name if pb.hook_patterns else "")


def _strs(xs, limit: int) -> list[str]:
    out = []
    for x in xs or []:
        s = " ".join(str(x).split()).strip()
        if s and s not in out:
            out.append(s)
    return out[:limit]


def clean(raw: list[dict], t: Transcript, pb: Playbook, duration: float) -> list[Clip]:
    segs = t.segments
    cands: list[Clip] = []
    for c in raw:
        try:
            start = float(c["start"])
            end = float(c["end"])
            hook = " ".join(str(c.get("hook_rewrite", "")).split()).strip()
        except (KeyError, TypeError, ValueError):
            continue
        if not hook:
            continue
        lines = _strs(c.get("on_screen_lines"), 5)
        start, end = _align(segs, max(0.0, min(start, duration)), max(0.0, min(end, duration)), hook, lines, duration)
        start = _snap_start(segs, start)
        end = _snap_end(segs, end)
        if end - start > MAX_LEN:
            end = _snap_end(segs, start + MAX_LEN)
            if end - start > MAX_LEN + 5:  # a single huge segment; hard cut
                end = start + MAX_LEN
        if end - start < MIN_LEN:
            print(f"[direct] drop {_mmss(start)}-{_mmss(end)}: too short")
            continue
        try:
            score = int(round(float(c.get("score") or 0)))
        except (TypeError, ValueError):
            score = 0
        cands.append(Clip(
            start=round(start, 3),
            end=round(end, 3),
            score=max(0, min(100, score)),
            title=" ".join(str(c.get("title") or "").split()).strip() or hook[:40],
            hook_rewrite=hook,
            on_screen_lines=lines,
            caption=" ".join(str(c.get("caption") or "").split()).strip(),
            matched_pattern=_pattern(c.get("matched_pattern") or "", pb),
            reason=" ".join(str(c.get("reason") or "").split()).strip(),
        ))

    # resolve overlaps: best score wins, then keep the top N
    cands.sort(key=lambda c: c.score, reverse=True)
    kept: list[Clip] = []
    for c in cands:
        if any(c.start < k.end and k.start < c.end for k in kept):
            continue
        kept.append(c)
        if len(kept) >= TOP_N:
            break
    return kept
