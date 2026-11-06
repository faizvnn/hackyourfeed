# Steps 2–3: pulling Oriane clips and reverse-engineering them

What we know as of Nov 6 (before any key was in `.env`). Two probe scripts exist; neither has run for real yet.

## What Oriane already gives us (no video download needed)

`projection=full` on `POST /rest/contents/search` returns, per video:

- `media[0].transcriptChunks[{startSeconds,endSeconds,text}]` → spoken hook, words-per-second, where the "beats" are
- `media[0].onScreenText[]` and `media[0].frames[{timestampSeconds,url,onScreenTextRegions[{text,polygon}]}]` → caption text, *where on screen* it sits, how often it changes
- `duration`, `caption`, `hashtags`, `viewsRatePerFollowers`, `popularComments`

So **subject, hook, pacing and caption style come straight from the JSON**. Only the cut rhythm, zooms, b-roll and music need the actual video.

There is **no video URL** in the response. We build it from `platformId`:
TikTok `tiktok.com/@handle/video/{id}`, YouTube `youtube.com/shorts/{id}`, Instagram `instagram.com/reel/{id}/` (Instagram often needs cookies in yt-dlp; expect TikTok/YouTube to work).

```bash
uv run python scripts/probe_oriane.py founder startup --limit 5 --download 2
```

Saves the raw response to `backend/work/oriane/raw_*.json` and the mp4s to `backend/work/oriane/videos/`.

## Which model watches the clip

| Route | Model | Video input | Cost for one 45 s short | Notes |
|---|---|---|---|---|
| **GMI (our credits)** | `google/gemini-3.1-flash-lite-preview`, `google/gemini-3-flash-preview` | yes, `video_url` part in chat completions (GMI's own quickstart shows it) | cents | Same OpenAI client as `llm.py`. Untested whether a `data:` base64 URL is accepted; the probe falls back to 1 fps frames if not. |
| GMI | `MiniMaxAI/MiniMax-M2.1/2.5/2.7` | **no, text only** | – | Use for the text stages (2, 4, 5), not for watching video. |
| MiniMax direct | `MiniMax-M3.1-Flash` | yes (`video_url`, ≤50 MB, fps 0.2–5) | ~$0.003 at $0.15/M in | Needs a separate MiniMax key. No audio. |
| Gemini direct | `gemini-2.5-flash-lite` | yes, inline ≤20 MB; ~100 tok/s of video **including audio** | free tier / $0.10/M | Needs an AI Studio key. Audio means it can hear the hook and pauses. |

Gemini is the one that hears audio, which matters for "when to cut" (pauses, emphasis). MiniMax M3.1 and frame-mode are vision only.

```bash
uv run python scripts/analyze_clip.py work/oriane/videos/<id>.mp4 --provider gmi
uv run python scripts/analyze_clip.py work/oriane/videos/<id>.mp4 --provider gemini   # if a GEMINI_API_KEY is set
```

Output is an *edit spec* JSON (subject, format, captions, on-screen text with timestamps, edit timeline of cuts/zooms, pacing, ordered editor instructions) saved to `backend/work/analysis/`. That spec is what stage 5/6 would feed to an ffmpeg/LLM editor.

## Suggested shape for stage 4

1. Stage 3 pulls ~50 videos with `projection=full` (already planned).
2. Pick the top 3–5 by `viewsRatePerFollowers`, download them, run `analyze_clip` once each (cents total).
3. Playbook prompt gets the 50 compact text records **plus** the 3–5 edit specs. The specs are what make "copy their format and editing" real rather than caption-only.
