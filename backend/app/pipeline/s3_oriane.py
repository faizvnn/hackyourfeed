"""Stage 3 — TREND PULL (team B)

In:  Understanding  (keyword_sets.niche / .topic / .entity → one search each)
Out: ViralSet  (compact ViralVideo records, deduped by id, sorted by views_rate_per_followers)

Verified against the live API on Nov 6 (details: docs/clip-analysis-notes.md):
- POST {ORIANE_BASE_URL}/rest/contents/search?sort=viewsRatePerFollowers,viewsCount&limit=N&projection=full
- Auth: `Authorization: Bearer <ORIANE_API_KEY>`. HTTP 206 is a normal paginated page.
- Text match: transcript.includesExactly with phrases people literally say, operator "or".
  includesFuzzy on single words matched 320k videos of garbage.
- Floors: transcriptLanguage en, profileFollowersCount >= 1000, viewsCount >= 50000; without them the
  viewsRatePerFollowers sort surfaces random one-hit accounts.
- `full` results carry media[0].transcriptChunks[{startSeconds,endSeconds,text}] (first chunk = spoken hook),
  media[0].onScreenText[], media[0].duration, thumbnailMediaUrl, hashtags, likesCount.
- No video URL in the response. Build it from platformId when a later stage needs the mp4.
"""

from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from ..config import ORIANE_API_KEY, ORIANE_AUTH_HEADER, ORIANE_BASE_URL, WORK_DIR, use_fixture
from ..contracts import Understanding, ViralSet, ViralVideo
from ..fixtures import load

DAYS = 30                 # publishedAt window; widened to WIDEN_DAYS when the pull is thin
WIDEN_DAYS = 120
LIMIT_PER_SEARCH = 50
MIN_VIDEOS = 30           # README done-when; triggers the widen
MIN_FOLLOWERS = 1000
MIN_VIEWS = 50_000
TRANSCRIPT_CHARS = 1500
TIMEOUT_S = 90            # observed executionTime up to ~20 s per search

PLATFORMS = [
    {"platform": "tiktok", "type": "video"},
    {"platform": "instagram", "type": "reel"},
    {"platform": "youtube", "type": "short"},
]


def run(u: Understanding) -> ViralSet:
    if use_fixture("trends"):
        return load("viral", ViralSet)
    if not ORIANE_API_KEY:
        raise RuntimeError("set ORIANE_API_KEY in .env (or add 'trends' to USE_FIXTURES)")

    videos = _pull(u, DAYS)
    if len(videos) < MIN_VIDEOS:
        print(f"stage 3: {len(videos)} videos in {DAYS} days, widening to {WIDEN_DAYS}", file=sys.stderr)
        videos = _pull(u, WIDEN_DAYS)
    return ViralSet(videos=videos)


# ----------------------------------------------------------------- search ---
def _pull(u: Understanding, days: int) -> list[ViralVideo]:
    # Most specific first so a video matched by several sets keeps the most specific granularity.
    plan = [(g, phrases) for g, phrases in (("entity", u.keyword_sets.entity),
                                            ("topic", u.keyword_sets.topic),
                                            ("niche", u.keyword_sets.niche)) if phrases]
    if not plan:
        raise ValueError("Understanding has no keyword_sets to search Oriane with")

    with ThreadPoolExecutor(max_workers=len(plan)) as ex:
        pages = list(ex.map(lambda gp: (gp[0], search(gp[1], days=days)), plan))

    seen: dict[str, ViralVideo] = {}
    raw_dump: dict[str, list] = {}
    for granularity, data in pages:
        results = _results(data)
        raw_dump[granularity] = results
        for r in results:
            if r.get("id") in seen:
                continue
            v = compact(r, granularity)
            if v is not None:
                seen[v.id] = v

    _save_raw(raw_dump, days)
    videos = sorted(seen.values(), key=lambda v: v.views_rate_per_followers, reverse=True)
    print(f"stage 3: {len(videos)} unique videos from {len(plan)} searches ({days} days)", file=sys.stderr)
    return videos


def search(phrases: list[str], *, days: int = DAYS, limit: int = LIMIT_PER_SEARCH,
           min_followers: int = MIN_FOLLOWERS, min_views: int = MIN_VIEWS, lang: str = "en") -> dict:
    """One Oriane search; returns the raw JSON body."""
    after = time.strftime("%Y-%m-%d", time.gmtime(time.time() - days * 86400))
    body = {
        "operator": "and",
        "filters": {
            "platformType": {"includes": PLATFORMS},
            "publishedAt": {"after": after},
            "transcript": {"includesExactly": {"values": phrases, "operator": "or"}},
            "transcriptLanguage": {"includes": [lang]},
            "profileFollowersCount": {"min": min_followers},
            "viewsCount": {"min": min_views},
        },
    }
    params = {"sort": "viewsRatePerFollowers,viewsCount", "limit": limit, "projection": "full"}
    token = f"Bearer {ORIANE_API_KEY}" if ORIANE_AUTH_HEADER.lower() == "authorization" else ORIANE_API_KEY
    r = httpx.post(f"{ORIANE_BASE_URL}/rest/contents/search", params=params, json=body,
                   headers={ORIANE_AUTH_HEADER: token}, timeout=TIMEOUT_S)
    if r.status_code >= 400:
        raise RuntimeError(f"Oriane HTTP {r.status_code} for {phrases}: {r.text[:500]}")
    return r.json()


def _results(data: dict) -> list[dict]:
    d = data.get("data") or {}
    return (d.get("results") if isinstance(d, dict) else d) or []


# ---------------------------------------------------------------- compact ---
def compact(r: dict, granularity: str) -> ViralVideo | None:
    platform = r.get("platform")
    if platform not in ("instagram", "tiktok", "youtube"):
        return None
    media = (r.get("media") or [{}])[0]
    chunks = media.get("transcriptChunks") or []
    transcript = media.get("transcript") or " ".join(c.get("text", "") for c in chunks)
    duration = float(media.get("duration") or 0)
    words = len(transcript.split())
    hook = (chunks[0].get("text") if chunks else "") or _first_sentence(transcript)
    return ViralVideo(
        id=r.get("id", ""),
        platform=platform,
        handle=r.get("profileHandle") or "",
        thumbnail_url=r.get("thumbnailMediaUrl") or "",
        views=int(r.get("viewsCount") or 0),
        likes=int(r.get("likesCount") or 0),
        followers=int(r.get("profileFollowersCount") or 0),
        views_rate_per_followers=round(float(r.get("viewsRatePerFollowers") or 0), 1),
        duration=duration,
        hook_text=hook.strip(),
        transcript=transcript[:TRANSCRIPT_CHARS],
        on_screen_text=[t for t in (media.get("onScreenText") or []) if _is_text(t)][:8],
        caption=(r.get("caption") or "")[:300],
        hashtags=[h.lstrip("#") for h in (r.get("hashtags") or [])][:10],
        words_per_second=round(words / duration, 2) if duration else 0,
        granularity=granularity,  # type: ignore[arg-type]
    )


def platform_url(v: ViralVideo, platform_id: str) -> str:
    """Oriane returns no video URL; build the public one for yt-dlp (needs the raw platformId)."""
    return {
        "tiktok": f"https://www.tiktok.com/@{v.handle}/video/{platform_id}",
        "instagram": f"https://www.instagram.com/reel/{platform_id}/",
        "youtube": f"https://www.youtube.com/shorts/{platform_id}",
    }[v.platform]


def _first_sentence(text: str) -> str:
    for sep in (". ", "? ", "! "):
        if sep in text:
            return text.split(sep, 1)[0] + sep.strip()
    return text[:120]


def _is_text(t: str) -> bool:
    """Drop OCR noise like '#06\\n#10' or single characters; keep real on-screen lines."""
    t = t.strip()
    return len(t) >= 3 and any(ch.isalpha() for ch in t) and "\n" not in t


def _save_raw(raw: dict[str, list], days: int) -> None:
    try:
        out = WORK_DIR / "oriane"
        out.mkdir(parents=True, exist_ok=True)
        (out / f"stage3_{days}d_{int(time.time())}.json").write_text(json.dumps(raw))
    except OSError as e:  # noqa: BLE001 - debugging aid only
        print(f"stage 3: could not save raw results: {e}", file=sys.stderr)
