"""Stage 3 — TREND PULL (team B)

In:  Understanding  (use keyword_sets.topic / .niche / .general)
Out: ViralSet  (compact ViralVideo records, deduped by id)

Oriane notes (full spec: docs/oriane-openapi.json):
- POST https://connect.oriane.xyz/rest/contents/search
  query: sort=viewsRatePerFollowers,viewsCount  limit=50  projection=full
  body:  {"operator": "and", "filters": {...}, "queries": [...]}
- Text filters: transcript / caption / hashtags / onScreenText
    {"includesFuzzy": {"values": [...], "operator": "or"}}
- Ranges: publishedAt {after, before}, viewsCount {min, max}
- platformType includes: tiktok/video, instagram/reel, youtube/short
- `full` results carry media[0].transcriptChunks[{startSeconds,endSeconds,text}]
  and media[0].onScreenText — the first chunk (<3 s) is the spoken hook.
- Auth header name is not in the spec; config.ORIANE_AUTH_HEADER defaults to x-api-key.
"""

from __future__ import annotations

from ..config import use_fixture
from ..contracts import Understanding, ViralSet
from ..fixtures import load


def run(u: Understanding) -> ViralSet:
    if use_fixture("trends"):
        return load("viral", ViralSet)
    raise NotImplementedError("team B")
