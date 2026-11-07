"""Stage 3 — TREND PULL (team B)

In:  Understanding  (category / competitor_handles / keyword_sets)
Out: ViralSet  (compact ViralVideo records, IG reels + TikTok, last 30 days, most-viewed first)

Wide net, then a relevance pass, then rank by views (probed live on Nov 6, see docs/clip-analysis-notes.md):
  1. Parallel Oriane searches, any poster, each a different way of saying "viral interview clip like this episode":
       entity    names of the guest and of the reference people (Understanding.references, kind=person; stage-2
                 keyword_sets.entity; category canon as fallback) in caption or on-screen text AND the poster's bio
                 or caption says podcast / interview / clips. Name alone = news and memes about the person.
       shows     reference shows' aliases in transcript or caption, or their hashtags (precise, low volume)
       accounts  profileHandle in {reference handles + competitor_handles + the category's podcast/clip accounts}
                 (a seed for the lane's format, capped per handle; not an assumption that official accounts are best)
       topic     exact spoken phrases from stage 2 in the transcript (has matched ~0 so far; filler)
       podcast   podcast word in the caption AND a niche/topic phrase in the transcript
     then a second hop:
       peers     the podcast/clip accounts (bio says so) that posted the entity / shows results (fan pages,
                 aggregators, the shows) -> their own most-viewed posts of the month. Accounts that cover the
                 guest's peers would cover this guest. This is how accounts get discovered instead of hardcoded.
     Every leaf alone is noisy (news, ads, skits, commentary ABOUT a person), which is why step 2 exists.
  2. Relevance pass: prompts/relevance.md asks the LLM, per compact record (+ poster bio), whether it is an
     interview / talking-head clip in this niche or an adjacent lane (format matters more than exact topic for
     a playbook); `matched` gets "on_niche" or "adjacent". Skipped with a warning when GMI is not configured.
  3. Survivors sorted by views across all sources, capped per handle, top MAX_VIDEOS.
Granularity on each record = the search that found it first (accounts -> "niche"); `matched` lists all of them.

API notes: POST {ORIANE_BASE_URL}/rest/contents/search?sort=viewsCount&limit=100&projection=full,
`Authorization: Bearer`, HTTP 206 = paginated page. Nested `queries` need their own `operator` and nest at most
two levels; results then carry `matchedQueries` (leaf names). No video URL in the response: build it from
platformId (platform_url).
TODO (needs stage 2): a "show" leaf = comparable shows' aliases in transcript/caption + their hashtags
(e.g. "All-In Podcast" / #allinpod); precise but low volume, so additive. Stage 2 should emit guest, host show
and 3-5 comparable shows/people with aliases, hashtags and handles; categories.py is the fallback.
"""

from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from .. import categories, llm
from ..config import GMI_API_KEY, GMI_MODEL, ORIANE_API_KEY, ORIANE_AUTH_HEADER, ORIANE_BASE_URL, WORK_DIR, use_fixture
from ..contracts import Understanding, ViralSet, ViralVideo
from ..fixtures import load

DAYS = 30                 # last 30 days only; no widening
LIMIT_PER_SEARCH = 100    # API max
MAX_VIDEOS = 60
MAX_PER_HANDLE = 5        # @wealth alone can fill a page
RELEVANCE_BATCH = 40      # records per relevance prompt
MIN_VIDEOS = 30           # README done-when; warns only
MIN_FOLLOWERS = 1000
MIN_VIEWS = 50_000
TRANSCRIPT_CHARS = 1500
TIMEOUT_S = 150           # the account search over ~25 handles took ~35 s live

PLATFORMS = [             # YouTube shorts dropped: Oriane's own advice, their coverage is weak
    {"platform": "tiktok", "type": "video"},
    {"platform": "instagram", "type": "reel"},
]
PODCAST_WORDS = ["podcast", "interview", "episode", "pod", "ep", "conversation", "sat down with"]
PODCAST_BIO_WORDS = ["podcast", "interview", "clips", "conversations"]   # sibling probe: bio beats caption for guest names
GRANULARITY = {"accounts": "niche", "peers": "niche", "entity": "entity", "shows": "entity", "topic": "topic", "podcast": "niche"}
PEER_HANDLES = 20         # second hop: how many posters of entity/show hits to pull from


def run(u: Understanding) -> ViralSet:
    if use_fixture("trends"):
        return load("viral", ViralSet)
    if not ORIANE_API_KEY:
        raise RuntimeError("set ORIANE_API_KEY in .env (or add 'trends' to USE_FIXTURES)")

    category = categories.pick(u)
    plan = build_plan(u, category)
    print(f"stage 3: category={category}, searches={list(plan)}", file=sys.stderr)

    with ThreadPoolExecutor(max_workers=len(plan)) as ex:
        pages = dict(zip(plan, ex.map(lambda b: search(b), plan.values())))
    peers = peer_handles(pages, exclude=_handles_in(plan))
    if peers:
        pages["peers"] = search(body(profileHandle={"exactMatch": {"values": peers, "operator": "or"}}))
        print(f"stage 3: second hop over {len(peers)} peer accounts -> {len(pages['peers'])} results", file=sys.stderr)
    _save_raw(pages)

    candidates, bios = merge(pages)
    print(f"stage 3: {len(candidates)} candidates: " + ", ".join(f"{k}={len(v)}" for k, v in pages.items()), file=sys.stderr)
    kept = relevant(candidates, bios, u)
    videos = rank(kept)
    if len(videos) < MIN_VIDEOS:
        print(f"stage 3: only {len(videos)} videos (want >= {MIN_VIDEOS})", file=sys.stderr)
    print(f"stage 3: {len(videos)} videos from {len(plan)} searches ({DAYS} days)", file=sys.stderr)
    return ViralSet(videos=videos)


# ------------------------------------------------------------------- plan ---
def build_plan(u: Understanding, category: str) -> dict[str, dict]:
    """Search name -> request body (first hop)."""
    plan: dict[str, dict] = {}
    people = [r for r in u.references if r.kind == "person"]
    shows = [r for r in u.references if r.kind == "show"]

    names = _dedupe([*(a for r in people for a in (r.name, *r.aliases)), *u.keyword_sets.entity,
                     *([] if u.references else categories.CATEGORIES[category]["names"])], min_len=4)
    if names:
        plan["entity"] = body(queries=[
            {"operator": "or", "queries": [
                {"name": "caption", "operator": "and", "filters": {"caption": {"includesExactly": {"values": names, "operator": "or"}}}},
                {"name": "onscreen", "operator": "and", "filters": {"onScreenText": {"includesExactly": {"values": names, "operator": "or"}}}},
            ]},
            {"operator": "or", "queries": [   # poster is a podcast / clip account, or the caption says so
                {"name": "podbio", "operator": "and", "filters": {"profileBio": {"includesFuzzy": {"values": PODCAST_BIO_WORDS, "operator": "or"}}}},
                {"name": "podcaption", "operator": "and", "filters": {"caption": {"includesFuzzy": {"values": PODCAST_WORDS, "operator": "or"}}}},
            ]},
        ])

    aliases = _dedupe([a for r in shows for a in (r.name, *r.aliases)], min_len=4)
    tags = _dedupe([t.lstrip("#").lower() for r in shows for t in r.hashtags], min_len=3)
    leaves = []
    if aliases:
        leaves += [{"name": "show:transcript", "operator": "and", "filters": {"transcript": {"includesExactly": {"values": aliases, "operator": "or"}}}},
                   {"name": "show:caption", "operator": "and", "filters": {"caption": {"includesExactly": {"values": aliases, "operator": "or"}}}}]
    if tags:
        leaves.append({"name": "show:hashtags", "operator": "and", "filters": {"hashtags": {"includesExactly": {"values": tags, "operator": "or"}}}})
    if leaves:
        plan["shows"] = body(queries=[{"operator": "or", "queries": leaves}])

    # Episode-specific accounts first (reference handles, stage-2 competitor_handles), then the category seed.
    # The seed is a floor so a sparse stage 2 still yields the lane's clip format; MAX_PER_HANDLE keeps it from dominating.
    handles = _dedupe([h.lstrip("@").lower() for r in u.references for h in r.handles] + categories.handles(u, category))
    if handles:
        plan["accounts"] = body(profileHandle={"exactMatch": {"values": handles, "operator": "or"}})

    phrases = [p for p in u.keyword_sets.topic if len(p.split()) >= 2]
    if phrases:
        plan["topic"] = body(transcript={"includesExactly": {"values": phrases, "operator": "or"}})
    spoken = [p for p in [*u.keyword_sets.topic, *u.keyword_sets.niche] if len(p.split()) >= 2]
    if spoken:
        plan["podcast"] = body(caption={"includesFuzzy": {"values": PODCAST_WORDS, "operator": "or"}},
                               transcript={"includesExactly": {"values": spoken, "operator": "or"}})
    if not plan:
        raise ValueError("Understanding gives stage 3 nothing to search with (no references, handles, names or phrases)")
    return plan


def peer_handles(pages: dict[str, list[dict]], exclude: set[str]) -> list[str]:
    """Posters of the entity / shows hits whose bio says podcast / clips (matchedQueries has "podbio") or that
    matched a show leaf, most frequent first (ties by views), minus accounts already searched. Posters that only
    matched by caption are skipped: that is how @f1 and news desks sneaked in as "peers"."""
    score: dict[str, list[int]] = {}
    for name in ("entity", "shows"):
        for r in pages.get(name) or []:
            h = (r.get("profileHandle") or "").lower()
            mq = r.get("matchedQueries") or []
            if not ("podbio" in mq or any(m.startswith("show:") for m in mq)):
                continue
            if h and h not in exclude:
                score.setdefault(h, [0, 0])
                score[h][0] += 1
                score[h][1] = max(score[h][1], int(r.get("viewsCount") or 0))
    return sorted(score, key=lambda h: (score[h][0], score[h][1]), reverse=True)[:PEER_HANDLES]


def _handles_in(plan: dict[str, dict]) -> set[str]:
    f = (plan.get("accounts") or {}).get("filters") or {}
    return {h.lower() for h in ((f.get("profileHandle") or {}).get("exactMatch") or {}).get("values", [])}


def _dedupe(items: list[str], *, min_len: int = 1) -> list[str]:
    seen: dict[str, None] = {}
    for it in items:
        it = it.strip()
        if len(it) >= min_len:
            seen.setdefault(it)
    return list(seen)


def body(queries: list[dict] | None = None, **filters: dict) -> dict:
    after = time.strftime("%Y-%m-%d", time.gmtime(time.time() - DAYS * 86400))
    b = {"operator": "and", "filters": {
        "platformType": {"includes": PLATFORMS},
        "publishedAt": {"after": after},
        "transcriptLanguage": {"includes": ["en"]},
        "profileFollowersCount": {"min": MIN_FOLLOWERS},
        "viewsCount": {"min": MIN_VIEWS},
        **filters,
    }}
    if queries:
        b["queries"] = queries
    return b


def search(b: dict, *, limit: int = LIMIT_PER_SEARCH) -> list[dict]:
    """One Oriane content search; returns the result list."""
    params = {"sort": "viewsCount", "limit": limit, "projection": "full"}
    token = f"Bearer {ORIANE_API_KEY}" if ORIANE_AUTH_HEADER.lower() == "authorization" else ORIANE_API_KEY
    r = httpx.post(f"{ORIANE_BASE_URL}/rest/contents/search", params=params, json=b,
                   headers={ORIANE_AUTH_HEADER: token}, timeout=TIMEOUT_S)
    if r.status_code >= 400:
        raise RuntimeError(f"Oriane HTTP {r.status_code}: {r.text[:500]}")
    d = r.json().get("data") or {}
    return (d.get("results") if isinstance(d, dict) else d) or []


# ------------------------------------------------------------------ merge ---
def merge(pages: dict[str, list[dict]]) -> tuple[list[ViralVideo], dict[str, str]]:
    """Union of all searches, deduped by id and by hook text (the same clip is often posted to both IG and
    TikTok: keep the more-viewed copy). Returns the candidates plus id -> poster bio for the relevance pass."""
    out: list[ViralVideo] = []
    bios: dict[str, str] = {}
    seen_id: set[str] = set()
    by_hook: dict[str, int] = {}   # hook -> index in out
    for name, results in pages.items():
        for r in results:
            v = compact(r, GRANULARITY[name])
            if v is None or v.id in seen_id:
                continue
            seen_id.add(v.id)
            bios[v.id] = (r.get("profileBio") or "")[:160]
            key = v.hook_text.lower()[:80]
            if key and key in by_hook:
                j = by_hook[key]
                if v.views > out[j].views:
                    out[j] = v.model_copy(update={"matched": sorted(set(out[j].matched) | set(v.matched))})
                    bios[out[j].id] = bios[v.id]
                else:
                    out[j].matched = sorted(set(out[j].matched) | set(v.matched))
                continue
            if key:
                by_hook[key] = len(out)
            out.append(v)
    return out, bios


def relevant(candidates: list[ViralVideo], bios: dict[str, str], u: Understanding) -> list[ViralVideo]:
    """LLM pass over compact records: keep interview / talking-head clips in this niche, any poster."""
    if not candidates:
        return []
    if not (GMI_API_KEY and GMI_MODEL):
        print("stage 3: GMI not configured, skipping the relevance pass (expect news/ads in the set)", file=sys.stderr)
        return candidates
    batches = [candidates[i:i + RELEVANCE_BATCH] for i in range(0, len(candidates), RELEVANCE_BATCH)]

    def judge(batch: list[ViralVideo]) -> dict[str, str]:
        records = [{"id": v.id, "handle": v.handle, "bio": bios.get(v.id, ""), "caption": v.caption[:160],
                    "hook": v.hook_text[:160], "transcript": v.transcript[:240], "duration": v.duration, "views": v.views}
                   for v in batch]
        try:
            out = llm.complete_json("relevance", niche=u.niche, summary=u.summary[:600], records=records)
        except Exception as e:  # noqa: BLE001 - keep the batch rather than lose it
            print(f"stage 3: relevance batch failed ({e}); keeping it unfiltered", file=sys.stderr)
            return {v.id: "unjudged" for v in batch}
        return {k["id"]: ("on_niche" if k.get("on_niche") else "adjacent")
                for k in out.get("keep") or [] if isinstance(k, dict) and k.get("id")}

    with ThreadPoolExecutor(max_workers=min(4, len(batches))) as ex:
        verdicts: dict[str, str] = {}
        for d in ex.map(judge, batches):
            verdicts.update(d)
    kept = []
    for v in candidates:
        if v.id in verdicts:
            v.matched = sorted({*v.matched, verdicts[v.id]})
            kept.append(v)
    on = sum("on_niche" in v.matched for v in kept)
    print(f"stage 3: relevance kept {len(kept)}/{len(candidates)} ({on} on-niche, {len(kept) - on} adjacent lane)", file=sys.stderr)
    return kept


def rank(videos: list[ViralVideo]) -> list[ViralVideo]:
    """Most-viewed first across every source; no account gets more than MAX_PER_HANDLE slots."""
    out: list[ViralVideo] = []
    per_handle: dict[str, int] = {}
    for v in sorted(videos, key=lambda v: v.views, reverse=True):
        if per_handle.get(v.handle, 0) >= MAX_PER_HANDLE:
            continue
        per_handle[v.handle] = per_handle.get(v.handle, 0) + 1
        out.append(v)
        if len(out) >= MAX_VIDEOS:
            break
    return out


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
        matched=[granularity, *(m for m in (r.get("matchedQueries") or []) if m)],
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


def _save_raw(pages: dict[str, list]) -> None:
    try:
        out = WORK_DIR / "oriane"
        out.mkdir(parents=True, exist_ok=True)
        (out / f"stage3_{int(time.time())}.json").write_text(json.dumps(pages))
    except OSError as e:  # noqa: BLE001 - debugging aid only
        print(f"stage 3: could not save raw results: {e}", file=sys.stderr)
