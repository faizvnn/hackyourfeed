"""Probe: one real Oriane search, saved raw, summarised, optionally downloaded.

    uv run python scripts/probe_oriane.py founder startup            # 5 results, last 30 days
    uv run python scripts/probe_oriane.py founder startup --limit 10 --days 14
    uv run python scripts/probe_oriane.py founder startup --download 3 # also yt-dlp the top 3 to work/oriane/videos/

Keywords are matched fuzzily against the transcript (operator "or").
Raw response -> backend/work/oriane/raw_<ts>.json so stage 3/4 can look at the real shape.
Needs ORIANE_API_KEY in backend/.env. Oriane returns no video URL, so we build the
platform URL from platformId and let yt-dlp fetch it (TikTok/YouTube work, Instagram may need cookies).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import ORIANE_API_KEY, ORIANE_AUTH_HEADER, ORIANE_BASE_URL, WORK_DIR  # noqa: E402

OUT = WORK_DIR / "oriane"


def platform_url(r: dict) -> str:
    pid, handle = r.get("platformId", ""), r.get("profileHandle", "")
    return {
        "tiktok": f"https://www.tiktok.com/@{handle}/video/{pid}",
        "instagram": f"https://www.instagram.com/reel/{pid}/",
        "youtube": f"https://www.youtube.com/shorts/{pid}",
    }.get(r.get("platform", ""), "")


def search(keywords: list[str], limit: int, days: int) -> dict:
    if not ORIANE_API_KEY:
        raise SystemExit("set ORIANE_API_KEY in backend/.env")
    after = time.strftime("%Y-%m-%d", time.gmtime(time.time() - days * 86400))
    body = {
        "operator": "and",
        "filters": {
            "platformType": {"includes": [
                {"platform": "tiktok", "type": "video"},
                {"platform": "instagram", "type": "reel"},
                {"platform": "youtube", "type": "short"},
            ]},
            "publishedAt": {"after": after},
            "transcript": {"includesFuzzy": {"values": keywords, "operator": "or"}},
        },
    }
    params = {"sort": "viewsRatePerFollowers,viewsCount", "limit": limit, "projection": "full"}
    r = httpx.post(f"{ORIANE_BASE_URL}/rest/contents/search", params=params, json=body,
                   headers={ORIANE_AUTH_HEADER: ORIANE_API_KEY}, timeout=60)
    print(f"HTTP {r.status_code}", file=sys.stderr)
    if r.status_code >= 400:
        print(r.text[:2000], file=sys.stderr)
        raise SystemExit(1)
    return r.json()


def compact(r: dict) -> dict:
    media = (r.get("media") or [{}])[0]
    chunks = media.get("transcriptChunks") or []
    frames = media.get("frames") or []
    words = sum(len(c.get("text", "").split()) for c in chunks)
    dur = media.get("duration") or 0
    return {
        "id": r.get("id"), "platform": r.get("platform"), "handle": r.get("profileHandle"),
        "url": platform_url(r), "views": r.get("viewsCount"), "followers": r.get("profileFollowersCount"),
        "vrpf": r.get("viewsRatePerFollowers"), "duration": dur, "wps": round(words / dur, 2) if dur else None,
        "n_chunks": len(chunks), "n_frames": len(frames),
        "hook": chunks[0].get("text") if chunks else None,
        "on_screen": (media.get("onScreenText") or [])[:5],
        "caption": (r.get("caption") or "")[:120],
    }


def download(items: list[dict], n: int) -> None:
    import yt_dlp  # in the venv

    vdir = OUT / "videos"
    vdir.mkdir(parents=True, exist_ok=True)
    for it in items[:n]:
        if not it["url"]:
            continue
        print(f"\n>> {it['platform']} {it['url']}", file=sys.stderr)
        opts = {"outtmpl": str(vdir / f"{it['id']}.%(ext)s"), "format": "mp4/best", "quiet": True, "no_warnings": True}
        try:
            with yt_dlp.YoutubeDL(opts) as y:
                y.download([it["url"]])
            print(f"   ok -> {vdir}/{it['id']}.mp4", file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            print(f"   FAILED: {str(e)[:200]}", file=sys.stderr)


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flag = lambda k, d: int(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else d  # noqa: E731
    limit, days, dl = flag("--limit", 5), flag("--days", 30), flag("--download", 0)
    if not args:
        raise SystemExit(__doc__)

    data = search(args, limit, days)
    OUT.mkdir(parents=True, exist_ok=True)
    raw = OUT / f"raw_{int(time.time())}.json"
    raw.write_text(json.dumps(data, indent=1))
    print(f"raw -> {raw}", file=sys.stderr)

    print("metadata:", json.dumps(data.get("metadata"), indent=1)[:600])
    results = (data.get("data") or {}).get("results") or data.get("data") or []
    if results and isinstance(results, list):
        print("top-level keys on a result:", sorted(results[0].keys()))
        media = (results[0].get("media") or [{}])[0]
        print("media keys:", sorted(media.keys()))
    items = [compact(r) for r in results]
    print(json.dumps(items, indent=1))
    if dl:
        download(items, dl)


if __name__ == "__main__":
    main()
