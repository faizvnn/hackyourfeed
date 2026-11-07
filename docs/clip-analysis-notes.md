# Stages 3–4: pulling Oriane clips and reverse-engineering them

Verified Nov 6 with real keys. Two probe scripts in `backend/scripts/`; raw outputs under `backend/work/`.

## Status (Nov 6, night): stage 3 re-queried around *interview clips*, not keywords

```bash
# in backend/.env: USE_FIXTURES=ingest,understand,direct,render   (drop trends,playbook)
make stage N=3 SAVE=1     # 5 Oriane searches + a second hop + a Gemini relevance pass; ~2-3 min, IG reels + TikTok, last 30 days
make stage N=4 SAVE=1     # compact records (+ any work/analysis/<id>.gmi.json edit specs) → playbook; ranked by views
```

What the live probes showed (`scripts/probe_queries.py`, raw under `work/oriane/probe_queries_*.json`):

| Query form | Result (30 days, sort viewsCount) |
|---|---|
| topic / niche phrases spoken in transcript (old way) | Gemini launch news, sketches, vlogs, a GoFundMe. 0-20 hits, mostly off-format |
| a person's name spoken in transcript or on screen | commentary ABOUT the person (rants, SNL), never interviews with them |
| a person's name in caption, alone | news and memes (Tesla Roadster, "Zuckerberg roasted") |
| name in caption/on-screen **AND poster bio says podcast/interview/clips** | interview clips (myfirstmilpod, impaulsive, lexfridman, sourcerypod) |
| `profileHandle` in a list of podcast / clip accounts | the lane's actual viral clips: @steven, @wealth, @garyvee, @hormozi at 5-60M views/month |
| podcast hashtags (`hashtags` exactMatch "podcast") | 0 results; `includesExactly` on hashtags is what works (sibling probe) |
| `profileBio` fuzzy "podcast" to discover accounts | celebrities with a podcast; useless without a lane word, and still noisy with one |

So no single Oriane query returns "viral interview clips in this lane". `s3_oriane.py` now does:

1. **Wide net, in parallel, any poster** (`build_plan`): `entity` (guest + reference people's names in caption / on-screen
   AND poster bio or caption says podcast), `shows` (reference shows' aliases + hashtags), `accounts` (reference handles +
   stage-2 `competitor_handles` + `categories.py` seed), `topic`, `podcast` (podcast word in caption AND a niche phrase spoken).
2. **Second hop** (`peer_handles`): the podcast/clip accounts that posted the entity / show hits → their own top posts of the
   month. That is how accounts get discovered per episode instead of hardcoded; the category list is only a floor.
3. **Relevance pass** (`prompts/relevance.md`, Gemini Flash Lite via GMI, 40 records per call): keep/drop by FORMAT only
   (interview / talking-head / panel vs news, ads, skits, TV scenes, demos, commentary about a person) and a separate
   `on_niche` flag. Tested on 20 @wealth/@steven/@garyvee clips: kept the interviews, dropped Shark Tank scenes, a
   physics demo and a Kung Fu Panda quote. Earlier versions that let topic decide dropped real interviews (8/231 kept).
4. **Rank by views** across every source, ≤ 5 per handle, top 60. `ViralVideo.matched` lists which leaves matched plus
   `on_niche` / `adjacent`.

Contract additions: `Understanding.category`, `Understanding.references[{kind: show|person, name, aliases, hashtags,
handles}]`, `ViralVideo.matched`. **Stage 2 does not emit `references` yet**; until it does, stage 3 runs on
`competitor_handles` + `keyword_sets.entity` + the category seed, so the set is on-format but mostly adjacent-lane
(fixture run: 7 on-niche of 33 kept). Topic phrases have matched ~0 videos in every run; they are filler.

Oriane API facts (verified): nested `queries` need their own `operator` and nest at most two levels (`QUERY_DEPTH_EXCEEDED`
beyond that); results carry `matchedQueries` with the leaf names; `limit` max 100; YouTube shorts dropped on Oriane's advice.

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
