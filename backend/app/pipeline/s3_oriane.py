"""Stage 3 — TREND PULL (team B)

Understanding -> ViralSet. Three Oriane searches (topic / niche / general),
unioned and reduced to the compact ViralVideo shape.

API reference: docs/oriane-openapi.json  (POST /rest/contents/search)
"""

from __future__ import annotations

from datetime import date, timedelta
import math

import httpx

from ..config import ORIANE_API_KEY, ORIANE_AUTH_HEADER, ORIANE_BASE_URL, use_fixture
from ..contracts import TextObservation, Understanding, ViralSet, ViralVideo
from ..fixtures import load

DAYS_BACK = 14
PER_QUERY = 50
MIN_VIEWS = 50_000

SHORT_FORM = [
    {"platform": "tiktok", "type": "video"},
    {"platform": "instagram", "type": "reel"},
    {"platform": "youtube", "type": "short"},
]


def run(u: Understanding) -> ViralSet:
    if use_fixture("trends"):
        return load("viral", ViralSet)

    seen: dict[str, ViralVideo] = {}
    plans = [
        ("topic", {"transcript": _fuzzy(u.keyword_sets.topic)}),
        ("niche", {"transcript": _fuzzy(u.keyword_sets.niche), "hashtags": _fuzzy(u.keyword_sets.niche)}),
        ("general", {"caption": _fuzzy(u.keyword_sets.general), "hashtags": _fuzzy(u.keyword_sets.general)}),
    ]
    for granularity, text_filters in plans:
        if not any(text_filters.values()):
            continue
        for item in search(text_filters):
            vid = to_viral(item, granularity)
            seen.setdefault(vid.id, vid)
    return ViralSet(videos=list(seen.values()))


def search(text_filters: dict, limit: int = PER_QUERY) -> list[dict]:
    """One /rest/contents/search call. text_filters: {field: filter-object}."""
    if not ORIANE_API_KEY:
        raise RuntimeError("set ORIANE_API_KEY in .env (or add 'trends' to USE_FIXTURES)")

    # Text fields are OR-ed between each other via a nested query group so that
    # a hit in either transcript or hashtags qualifies.
    body = {
        "operator": "and",
        "filters": {
            "publishedAt": {"after": (date.today() - timedelta(days=DAYS_BACK)).isoformat()},
            "viewsCount": {"min": MIN_VIEWS},
            "transcriptLanguage": {"includes": ["en"]},
            "platformType": {"includes": SHORT_FORM},
        },
        "queries": [{"operator": "or", "filters": {k: v for k, v in text_filters.items() if v}}],
    }
    params = {
        "sort": "viewsRatePerFollowers,viewsCount",
        "limit": limit,
        "projection": "full",
    }
    r = httpx.post(
        f"{ORIANE_BASE_URL}/rest/contents/search",
        params=params,
        json=body,
        headers={ORIANE_AUTH_HEADER: ORIANE_API_KEY},
        timeout=60,
    )
    r.raise_for_status()
    payload = r.json()
    # Wrapper shape not fully documented; handle {data: [...]} and bare list.
    return payload.get("data", payload) if isinstance(payload, dict) else payload


def to_viral(item: dict, granularity: str) -> ViralVideo:
    media = (item.get("media") or [{}])[0]
    chunks = media.get("transcriptChunks") or []
    transcript = media.get("transcript") or ""
    duration = float(media.get("duration") or 0)
    words = len(transcript.split())
    return ViralVideo(
        id=item["id"],
        platform=item["platform"],
        handle=item.get("profileHandle", ""),
        thumbnail_url=item.get("thumbnailMediaUrl", ""),
        views=int(item.get("viewsCount") or 0),
        likes=int(item.get("likesCount") or 0),
        followers=int(item.get("profileFollowersCount") or 0),
        views_rate_per_followers=float(item.get("viewsRatePerFollowers") or 0),
        duration=duration,
        hook_text=" ".join(c["text"] for c in chunks if c.get("startSeconds", 0) < 3) or transcript[:200],
        transcript=transcript[:1500],
        on_screen_text=[t for t in (media.get("onScreenText") or []) if t][:10],
        caption=(item.get("caption") or "")[:300],
        hashtags=item.get("hashtags") or [],
        words_per_second=round(words / duration, 2) if duration else 0,
        granularity=granularity,  # type: ignore[arg-type]
        published_at=item.get("publishedAt") or "",
        text_observations=_text_observations(media.get("frames") or []),
    )


def _text_observations(frames: list[dict]) -> list[TextObservation]:
    """Keep compact, measured OCR geometry; not font/color/animation guesses."""
    observations = []
    # Sample across the full clip and cap prompt size.
    stride = max(1, len(frames) // 8)
    for frame in frames[::stride][:8]:
        for region in (frame.get("onScreenTextRegions") or [])[:3]:
            text = region.get("text") or ""
            polygon = region.get("polygon") or []
            try:
                ys = [float(p["y"]) for p in polygon]
                timestamp = float(frame.get("timestampSeconds") or 0)
                if (not text.strip() or len(ys) < 3 or not math.isfinite(timestamp)
                        or timestamp < 0 or not all(math.isfinite(y) and 0 <= y <= 1 for y in ys)):
                    continue
                observations.append(TextObservation(text=text[:200], timestamp_seconds=timestamp,
                    center_y=(max(ys) + min(ys)) / 2, height=max(ys) - min(ys)))
            except (KeyError, TypeError, ValueError):
                continue
    return observations


def _fuzzy(values: list[str]) -> dict | None:
    return {"includesFuzzy": {"values": values, "operator": "or"}} if values else None
