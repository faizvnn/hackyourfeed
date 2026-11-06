# Stages 3–4: pulling Oriane clips and reverse-engineering them

Verified Nov 6 with real keys. Two probe scripts in `backend/scripts/`; raw outputs under `backend/work/`.

## Status (Nov 6, evening)

Both stages are implemented and have run for real; `fixtures/viral.json` (55 videos) and `fixtures/playbook.json` (4 patterns)
are real output, not hand-written.

```bash
# in backend/.env: USE_FIXTURES=ingest,understand,direct,render   (i.e. drop trends,playbook)
make stage N=3 SAVE=1     # 3 parallel Oriane searches (entity/topic/niche), union, dedupe, sort by vrpf; ~25 s
make stage N=4 SAVE=1     # 55 compact records (+ any work/analysis/<id>.gmi.json edit specs) → playbook; ~4 s
```

- `s3_oriane.py` widens the window from 30 to 120 days if fewer than 30 videos come back, and saves the raw
  results to `work/oriane/stage3_*.json`.
- `s4_playbook.py` only *reads* edit specs that `analyze_clip.py` already produced; it never downloads or analyzes
  video in the pipeline (too slow for a job). Run `analyze_clip.py` on the top few ids beforehand if you want
  editing detail in the playbook.
- **Biggest quality lever is stage 2.** The fixture `understanding.json` has niche keywords like `startup`, `VC`,
  `founder`; exact-matching those pulls eyebrow trivia and prayer vigils alongside founder clips. The playbook
  prompt tells the model to ignore off-topic videos, but 3–5 word spoken phrases per set would fix it at the source.
- Entity search is skipped when `keyword_sets.entity` is empty (it is in the fixture).

### GMI model for the text stages

Tested with the real 43k-char playbook prompt:

| Model | Result |
|---|---|
| **`google/gemini-3.5-flash-lite`** | **4 s, valid JSON, 5 patterns.** Same model that works for video. Use this. |
| `google/gemini-3.5-flash` | Fine on a 1-line prompt, but **400 "Invalid Endpoint name …:rawPredict"** on the long one. GMI routes big requests to a backend where that id is invalid. |
| `MiniMaxAI/MiniMax-M2.7` | 44 s, valid JSON in code fences (`extract_json` tolerates), 6 patterns. Fallback. |
| `Qwen/Qwen3.8-Flash` | 524 gateway timeout after 125 s. |
| `google/gemini-3-flash-preview` | 503, retries exhausted. |


## Oriane (stage 3) — what works

- **Auth:** `Authorization: Bearer <ORIANE_API_KEY>` (`x-api-key` → 401). HTTP 206 is a normal paginated page.
- **Text match:** use `includesExactly` with 3–5 word phrases people literally say ("as a founder", "raise money", "my cofounder"),
  `operator: "or"`. `includesFuzzy` with single words matched 320k videos of garbage.
- **Floors:** `transcriptLanguage: en`, `profileFollowersCount.min: 1000`, `viewsCount.min: 50000`. Without them,
  sorting by `viewsRatePerFollowers` surfaces random one-hit accounts.
- **Remaining noise is literal:** "raise money" also matches GoFundMe pleas. More, longer phrases beat fewer, shorter ones.
  Stage 2 should emit phrases, not nouns.
- **No video URL in the response.** Build it: TikTok `tiktok.com/@handle/video/{platformId}`, Instagram
  `instagram.com/reel/{platformId}/`, YouTube `youtube.com/shorts/{platformId}`. yt-dlp downloaded 5/5 Instagram reels;
  one TikTok came back "IP address is blocked" (post-specific); YouTube untested.
- **Already in the JSON (no download needed):** `media[0].transcriptChunks[{startSeconds,endSeconds,text}]`,
  `media[0].onScreenText[]`, `media[0].frames[{timestampSeconds,url,onScreenTextRegions[{text,polygon}]}]`, `duration`.
  That covers hook, pacing (words/sec) and caption text + screen position. Only cuts/zooms/b-roll/music need the video.

```bash
cd backend && uv run python scripts/probe_oriane.py "as a founder" "raise money" "my cofounder" --limit 10 --download 3
```

## Watching the clip (stage 4 input) — what works on GMI

Gemini on GMI **does** process video with audio, but only from Google Cloud Storage. GMI's Upload API gives us that for free.

| Route | Result |
|---|---|
| **GMI Upload API → `gs://` URI → chat completions `video_url` (`google/gemini-3.5-flash-lite`)** | **Works, with audio.** Upload-url + PUT (<1 s), then ~3.6 s, ~5.5k input tokens for a 60 s clip (~90 tok/s). Heard the real hook verbatim. |
| Gemini-native `:generateContent` with `inlineData` base64 | Works for small files (0.6 MB: 2 s, 1,838 tokens, VIDEO+AUDIO counted); **hangs** on a 5.6 MB file. Not worth it; use the upload. |
| chat completions `video_url` with base64 data URL | Silently dropped (model answers blind). Same for `MiniMaxAI/MiniMax-M3`. |
| chat completions / native with an https URL (incl. the Upload API's public URL, YouTube) | 400 "HTTP links are not supported for requests restricted by VPCSC". |
| `--frames`: 24 JPEGs at 1 fps + Oriane timed transcript | Works, ~27k tokens, no audio. Fallback only. |

Upload API (same key): `POST https://console.gmicloud.ai/api/v1/ie/requestqueue/apikey/upload-url {"file_type":"mp4"}` →
`PUT` bytes to `upload_url` → turn `public_url` (`https://storage.googleapis.com/<bucket>/<path>`) into `gs://<bucket>/<path>`.

```bash
cd backend && uv run python scripts/analyze_clip.py work/oriane/videos/<id>.mp4 --provider gmi
```

Output: `backend/work/analysis/<id>.gmi.json` → `{subject, format, captions, on_screen_text[], edit_timeline[], pacing, instructions_for_editor[]}`.

## High-res vision: `--hires --fps 3` (verified)

`--hires` switches to GMI's Gemini-native `:generateContent` (same gs:// upload) so we can set `mediaResolution`
and `videoMetadata.fps`, which chat completions can't. Same 60 s clip, `google/gemini-3.5-flash-lite`:

| Run | Tokens in | Time | What changed |
|---|---|---|---|
| default (chat completions, low res, 1 fps) | 6.3k | 6.9 s | 9 timeline events, 6 on-screen texts, timestamps on whole seconds |
| `--hires --fps 3` | 49.9k (47.5k video, 1.5k audio) | 12.8 s | 10 events with sub-second times (title card at 5.6 s, b-roll at 4.3 s), 9 on-screen texts incl. small ones ("Verified badge", "I need to move"), caption look described with shadow detail |

About 8x the tokens, still well under a cent per clip. Use `--hires` for the 3–5 clips we actually copy from, default for the rest.
Gemini describes effects by family (zoom, flash, speed ramp) rather than exact parameters; fine for an editing agent.

## Deterministic pitch check: `scripts/pitch_probe.py` (verified on 4 clips)

ffmpeg → 16 kHz mono → autocorrelation f0 per 40 ms → median per second → flag runs ≥ 2 s above 320 Hz (chipmunk /
sped-up) or below 75 Hz (pitched-down). numpy only, ~1 s per clip, no API.

```bash
cd backend && uv run python scripts/pitch_probe.py work/oriane/videos/<id>.mp4
```

Results: two plain talking-head clips → no flags (correct). A Street Fighter ad with shouted game lines → 3 "high" runs
(real audio, but shouting, not an edit). One podcast clip → two 2 s "high" windows, unverified.
Lessons baked in: a relative-to-clip-median rule flagged the second speaker in two-person clips, so thresholds are
absolute; 1 s spikes are laughs/music hits/sfx, so runs must last ≥ 2 s; f0 pinned at the 500 Hz ceiling is music.

**It cannot tell a shout from a pitch effect.** So effects need two independent yeses (decided Nov 6, high bar on purpose:
missing a real effect beats inventing one):
1. `pitch_probe.py` flags a window (strict: ≥ 3 s, > 350 Hz or < 70 Hz).
2. Gemini, told to leave `voice_fx` empty unless unmistakable, reports an overlapping window.
`analyze_clip.py` does the intersection (`gate_voice_fx`): `voice_fx` = agreed only; `voice_fx_model` / `voice_fx_probe` kept for debugging.
No `<id>.pitch.json` → no effects kept. Verified: shouting ad → probe 1 window, Gemini 0, kept 0. Two talking clips → 0/0/0.
Output: `backend/work/analysis/<id>.pitch.json` → `{clip_median_f0, voice_fx[{start,end,kind,f0}], timeline[]}`.

## Prompt priorities (current)

Subject first: `key_claim`, `structure` (setup → tension → payoff), `quotable_lines[{t,text}]`, `audience`, then format and
captions, then effects with "only what you clearly saw, do not guess zooms or sfx". On a 73 s two-person sketch Gemini
returned a one-sentence claim, the structure, two timestamped quotes and 8 timeline events (cuts/speaker switches/text only).

Caveat for the tech-interview target: the clips tested so far came from the "founder" keyword pull and were a Meta ad,
a Street Fighter ad and a Hindi comedy sketch. Stage 3's phrase lists decide whether we learn from tech interviews or from
whatever matches the words; test again on the real pull before trusting the playbook.

## Suggested shape for stage 4

1. Stage 3 pulls ~50 videos with `projection=full` (three phrase sets, union, dedupe).
2. Take the top 3–5 by `viewsRatePerFollowers` that pass the floors, download, run `analyze_clip` (video via gs://, cents each).
3. Playbook prompt gets the 50 compact text records **plus** the 3–5 edit specs. The specs are what make
   "copy their format and editing" real rather than caption-only.
