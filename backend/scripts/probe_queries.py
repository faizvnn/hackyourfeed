"""Probe: which Oriane query form surfaces viral *interview clips* of a named person (or a category of people)?

    uv run python scripts/probe_queries.py "Sam Altman" --mention sama --host dwarkesh
    uv run python scripts/probe_queries.py "Elon Musk" "Mark Zuckerberg" --limit 8 --days 60

Runs one search per variant, IG reels + TikTok only, sorted by viewsCount, and prints the top hits side by side:
  transcript   name spoken in the clip (includesExactly)          -> commentary ABOUT the person, often
  caption      name in the post caption (includesFuzzy)            -> clip accounts label the guest here
  onscreen     name in OCR'd on-screen text (includesFuzzy)        -> clip accounts put the guest name on screen
  mention      post @mentions the person's handle (--mention)
  host         clip posted by the interviewer's own account (--host, fuzzy on profileHandle)
  nested       one request with named sub-queries (caption | onscreen | transcript) -> matchedQueries per result
Raw bodies -> backend/work/oriane/probe_queries_<ts>.json
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import ORIANE_API_KEY, ORIANE_BASE_URL, WORK_DIR  # noqa: E402

PLATFORMS = [{"platform": "tiktok", "type": "video"}, {"platform": "instagram", "type": "reel"}]
BASE = {"transcriptLanguage": {"includes": ["en"]}, "profileFollowersCount": {"min": 1000}, "viewsCount": {"min": 50000}}


def post(body: dict, limit: int) -> dict:
    r = httpx.post(f"{ORIANE_BASE_URL}/rest/contents/search", params={"sort": "viewsCount", "limit": limit, "projection": "full"},
                   json=body, headers={"Authorization": f"Bearer {ORIANE_API_KEY}"}, timeout=120)
    if r.status_code >= 400:
        print(f"  HTTP {r.status_code}: {r.text[:300]}", file=sys.stderr)
        return {}
    return r.json()


def filters(days: int, **extra: dict) -> dict:
    after = time.strftime("%Y-%m-%d", time.gmtime(time.time() - days * 86400))
    return {"platformType": {"includes": PLATFORMS}, "publishedAt": {"after": after}, **BASE, **extra}


def variants(names: list[str], days: int, mention: str | None, host: str | None) -> dict[str, dict]:
    v = {
        "transcript": {"operator": "and", "filters": filters(days, transcript={"includesExactly": {"values": names, "operator": "or"}})},
        "caption": {"operator": "and", "filters": filters(days, caption={"includesFuzzy": {"values": names, "operator": "or"}})},
        "onscreen": {"operator": "and", "filters": filters(days, onScreenText={"includesFuzzy": {"values": names, "operator": "or"}})},
    }
    if mention:
        v["mention"] = {"operator": "and", "filters": filters(days, mentionHandles={"exactMatch": {"values": [mention]}})}
    if host:
        v["host"] = {"operator": "and", "filters": filters(days, profileHandle={"includesFuzzy": {"values": [host]}})}
    # Clip accounts label the guest in the caption / lower-third, but the guest rarely says their own name on camera.
    # Commentary ABOUT the person nearly always does. So: name in caption/on-screen AND name NOT spoken.
    not_spoken = {"excludesExactly": {"values": names, "operator": "and"}}
    v["caption_notspoken"] = {"operator": "and", "filters": filters(days, caption={"includesFuzzy": {"values": names, "operator": "or"}}, transcript=not_spoken)}
    v["onscreen_notspoken"] = {"operator": "and", "filters": filters(days, onScreenText={"includesFuzzy": {"values": names, "operator": "or"}}, transcript=not_spoken)}
    v["nested"] = {"operator": "and", "filters": filters(days), "queries": [{
        "operator": "or", "queries": [
            {"name": "caption", "operator": "and", "filters": {"caption": {"includesFuzzy": {"values": names, "operator": "or"}}}},
            {"name": "onscreen", "operator": "and", "filters": {"onScreenText": {"includesFuzzy": {"values": names, "operator": "or"}}}},
            {"name": "transcript", "operator": "and", "filters": {"transcript": {"includesExactly": {"values": names, "operator": "or"}}}},
        ]}]}
    return v


def row(r: dict) -> str:
    m = (r.get("media") or [{}])[0]
    ch = m.get("transcriptChunks") or []
    hook = (ch[0].get("text") if ch else "")[:60]
    mq = ",".join(r.get("matchedQueries") or [])
    return (f"  {r.get('platform','')[:2]} {int(r.get('viewsCount') or 0)/1e6:5.1f}M  {int(m.get('duration') or 0):3d}s  "
            f"@{(r.get('profileHandle') or '')[:18]:<18} {mq:<22} | {(r.get('caption') or '')[:55]!r} | {hook!r}")


def main() -> None:
    argv = sys.argv[1:]
    opt = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d  # noqa: E731
    names = [a for i, a in enumerate(argv) if not a.startswith("--") and not (i > 0 and argv[i - 1].startswith("--"))]
    if not names or not ORIANE_API_KEY:
        raise SystemExit(__doc__ if names else "set ORIANE_API_KEY in backend/.env")
    limit, days = int(opt("--limit", 8)), int(opt("--days", 30))
    out = {}
    for label, body in variants(names, days, opt("--mention"), opt("--host")).items():
        t0 = time.time()
        data = post(body, limit)
        res = ((data.get("data") or {}).get("results")) or []
        total = (data.get("metadata") or {}).get("totalCount") or (data.get("metadata") or {}).get("total")
        print(f"\n== {label}: {len(res)} shown, total={total}, {time.time() - t0:.1f}s")
        for r in res:
            print(row(r))
        out[label] = {"body": body, "results": res, "metadata": data.get("metadata")}
    p = WORK_DIR / "oriane" / f"probe_queries_{int(time.time())}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out))
    print(f"\nraw -> {p}", file=sys.stderr)


if __name__ == "__main__":
    main()
