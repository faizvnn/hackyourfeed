# Stage 6 (experimental) — adaptive clip rendering

> **Status: behind a flag.** This engine lives in `app/pipeline/s6_render_adaptive.py`
> and only runs when `RENDER_ENGINE=adaptive` is set in `backend/.env`. The default
> (`RENDER_ENGINE=classic`) is the Pillow-overlay render in `app/pipeline/s6_render.py`.
> `python -m app.render_cli` always uses this engine, flag or not, so you can test it
> in isolation. It needs ffmpeg built with libass (`ffmpeg -filters | grep ass`); the
> homebrew build on at least one team Mac lacks it, so point `FFMPEG_BIN`/`FFPROBE_BIN`
> in `backend/.env` at a build that has it (e.g. `/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg`).
> The engine checks for the `ass` filter at start and fails with that hint; the
> integration tests skip instead.
>
> Not yet wired: the stage 3→4→5 caption-style plumbing described under
> "Contract with stages 1 and 5" (OCR observations, `Playbook.caption_style`,
> `Clip.render_style`) was not merged into the team's current stages 3-5 or prompts.
> The contract fields exist, so the adaptive engine runs with `CaptionStyle` defaults
> until those stages fill them in.

This module turns the existing stage-1 `Transcript` and stage-5 `ClipSet` into
vertical, captioned MP4 files. No Oriane, GMI inference, or Compound key is needed.
It uses Python 3.11+, FFmpeg with `libass` and `libx264`, and FFprobe.

## Run it independently

From `backend/`, install `python -m pip install -r requirements-render.txt` and
ensure `ffmpeg` and `ffprobe` are on PATH. The default fonts are Arial on Windows
and DejaVu Sans on Linux. Install `fonts-dejavu-core` on Debian/Ubuntu.

```sh
python -m app.render_cli --demo
```

On this Windows checkout the prepared virtual environment is at `../.venv`:

```powershell
..\.venv\Scripts\python.exe -m app.render_cli --demo
```

This generates **synthetic color bars and a tone**, with explicitly labeled test
captions, rather than pretending to transcribe podcast speech. Three MP4s, ASS
and SRT files, and `clips_rendered.json` are saved in `work/renders/render-demo/`.
The input examples are saved in `work/render-demo/transcript.json` and `clips.json`.

To use the actual outputs of the other teammates:

```sh
python -m app.render_cli --transcript path/to/transcript.json --clips path/to/clips.json --job-id podcast-01
```

`--video path/to/source.mp4` overrides `transcript.video_path`. A relative video
path inside the transcript JSON is resolved against that JSON's parent folder.
The CLI's `--video` is resolved against the working directory. Do not combine
`--demo` with real inputs. Do not include `render` in `USE_FIXTURES` for real runs.

## Contract with stages 1 and 5

Caption style is now connected through the whole data pipeline:

```text
Stage 3: Oriane text observations + geometry + reference IDs + performance
    -> Stage 4: Playbook.caption_style (recommendation + evidence IDs)
    -> Stage 5: Clip.render_style + emphasis_keywords + publication caption
    -> Stage 6: original speech subtitles rendered with that clip's plan
```

Stage 3 preserves sampled frame OCR text, relative vertical center/height, timestamp,
publication time, and reference IDs. Stage 4 sends these to its existing LLM call.
OCR may describe subtitles, logos, or titles; the prompt requires this distinction.
Geometry/casing/text length can inform recommendations, but color, font family,
animation and retention are not measured by this payload. They must not be claimed
as observed facts. Source IDs are checked against the actual supplied records.

`CaptionStyle` is optional in legacy payloads. An example stage-5 clip addition is:

```json
{
  "render_style": {
    "words_per_group": 2,
    "max_chars_per_group": 20,
    "letter_case": "original",
    "font_size": 50,
    "position": "lower",
    "highlight_color": "cyan",
    "emphasis": "keywords",
    "animation": "none",
    "hook_seconds": 1.5,
    "evidence_video_ids": [],
    "evidence_basis": "fallback",
    "rationale": "Illustrative plan only; no live references fetched for this example."
  },
  "emphasis_keywords": ["Google", "research"]
}
```

Stage 5 inherits the playbook plan, may adapt the bounded settings for each passage,
and filters keyword emphasis to actual words in that passage. Reference provenance
cannot be invented by stage 5. Missing/invalid styles and unavailable evidence use
the readable fallback. Stage 6 interprets typed options rather than executing LLM
formatting commands. Full-screen 9:16 remains fixed, as requested. The publication
`caption` follows `caption_formula`; speech subtitle text always comes from the
original transcript. Speaking pace does not cause audio to be accelerated.

The three required prompt files are included in `app/prompts/`. No extra LLM call
was added. Tests use fixture Oriane data and mocked LLM responses to verify the
handoff, plus actual FFmpeg output with a custom plan. Real Oriane/GMI integration
still requires the team's credentials and has not been validated here. Plans are
testable editorial recommendations, not guaranteed performance predictions.

The pipeline invocation already in `app/jobs.py` stays exactly the same:

```python
job.status = "render"
job.clips = s6_render.run(job.id, job.transcript, job.clips)
```

- Stage 1 must deliver an existing local `video_path` accessible by this process.
  `segments` have `{start, end, text}` with absolute seconds in the original video.
  Each segment may also include `words: [{start, end, text}]` on that same timeline
  for precise word-by-word emphasis. This is optional and backward compatible.
  Rendering validates ranges against FFprobe's media duration, not transcript metadata.
- Stage 5 delivers `ClipSet` from `app/contracts.py` (the object with a `clips` list).
  Clip `start` and `end` use the same absolute timeline. `hook_rewrite` is displayed
  for two seconds by default (or the clip plan's `hook_seconds`); it never replaces the speaker's audio. `caption` is publication
  copy, not subtitles. `on_screen_lines` is reserved until the team supplies timing
  and placement rules; this version renders only the hook and transcript captions.
- Stage 6 mutates each existing clip with `render_path`, `render_url`, or the new
  nullable `render_error`. Other clip metadata is preserved. Paths remain local;
  URLs use `PUBLIC_BASE_URL` and the existing `/renders` FastAPI mount.
- The job runner already exposes the same clip objects during rendering. The UI
  may show each clip once `render_url` is set and show `render_error` for failed
  items. A partially successful job finishes with the successful clips available;
  if every clip fails, the stage raises and the existing runner marks the job error.
- Each invocation needs its own job ID. Render files publish only after FFprobe
  checks the output. A JSON manifest is written after processing all clips.

Set `PUBLIC_BASE_URL` to the backend's reachable HTTPS origin when connecting
Lovable. `localhost` is only appropriate when the browser is on the same machine.
The existing `app.main` already serves MP4 files and supports byte-range requests.
Running that full API requires its other dependencies (`fastapi`, `uvicorn`,
`openai`, `httpx`, `yt-dlp`) and the other stages' prompts/configuration; the render
requirements file and Dockerfile deliberately package only this teammate's module.

## Presets and limitations

Output: 720×1280, 30 fps, H.264/yuv420p, AAC audio when present, MP4 faststart.
`RENDER_LAYOUT=crop` is the default and fills the entire frame with a centered crop,
with no background bands. `RENDER_LAYOUT=blur` remains an optional layout that
preserves the full original frame over a blurred background. `--layout crop` overrides
the environment for CLI calls. There is no automatic active-speaker tracking.
`--crop-center-x 0.625` (or `RENDER_CROP_CENTER_X=0.625`) centers the crop at 62.5%
of the source width when the speaker sits to the right; the default is 0.5.

Captions use bold uppercase text, black outlines, groups of up to three words,
yellow emphasis on the active word, and a subtle entrance pop. Text sits above
the bottom controls. Precise highlighting uses `Segment.words` when available.
With phrase-only input, intra-phrase word durations are approximate (weighted by
character count), not forced alignment; estimates are never written back as word
timestamps. Use the optional local transcription below when precision is needed.
No speech is rewritten and no extra LLM call is required. Overlapping windows are
trimmed to avoid stacked captions. Long hooks wrap to at most three lines and
truncate with an ellipsis. Transcript captions are not truncated. For rolling
YouTube captions, stage 1 remains responsible for deduplicating words.

### Optional transcription when YouTube captions are blocked

```sh
python -m pip install -r requirements-transcribe.txt
python -m app.render_cli --transcript input/transcript.json --clips input/clips.json --job-id podcast-captioned --transcribe
```

`--transcribe` transcribes the existing local video using faster-whisper on CPU,
replaces the supplied segments with speech-derived text and word times, and saves
`work/transcripts/<job-id>.json`. The default multilingual `base` model downloads
on first use to `work/models/`; `--whisper-model` changes it. No API token or
cloud transcription service is needed. Machine transcription may need correction.
This adapter is opt-in; the stage-6 pipeline function continues to accept the
transcript produced by stage 1. The minimal Dockerfile does not install ASR;
install `requirements-transcribe.txt` in the team's image to enable that option.

Options: `RENDER_FONT_NAME`, `RENDER_TIMEOUT_SECONDS` (default 300 per FFmpeg run),
`FFMPEG_BIN`, `FFPROBE_BIN`, `WORK_DIR`. See the repo-root `.env.example` for renderer settings.
The library also accepts an optional `RenderOptions` object for dimensions and fps.
There is no verified headless Compound integration; its adapter is deliberately
inactive and rendering never depends on it.

## GMI/Linux handoff

The simplest integration is to install FFmpeg/fonts in the team's backend image
and include this module in the same process and filesystem as stage 1. No GPU is
required for the default CPU encoder. API inference credits do not themselves
provision this machine.

A standalone renderer container is provided (build from `backend/`):

```sh
docker build -f Dockerfile.render -t hackyourfeed-render .
docker run --rm -v "${PWD}/work:/app/work" hackyourfeed-render
```

This container runs the synthetic demo; it does not launch the full API. For real
inputs, mount their folder and override the command with `python -m app.render_cli`
and the flags above. Mount a persistent work directory to retain MP4s. With the
current in-memory job store, keep the full API on a single worker without reload.

## Verify

```sh
python -m unittest discover -s tests -v
```

Tests exercise real FFmpeg rendering for landscape footage with audio, portrait
footage without audio, paths containing spaces/apostrophes, partial failures, actual
media bounds, and caption boundary/formatting cases. Integration tests skip when
FFmpeg/FFprobe is absent. Inspect the MP4s visually and listen to real speech after
connecting a real stage-1 transcript; synthetic tones cannot verify speech alignment.

## Validation in this checkout

All 17 tests passed on Windows; rendering integration tests use real FFmpeg. The synthetic three-clip demo
was rendered and visually inspected. The existing FastAPI mount returned HTTP 206
and the correct Content-Range for a 1024-byte MP4 range request.

For the supplied YouTube video `NKZsH8PBhKY`, a 15-second sample of original time
60–75 seconds downloaded successfully. Three five-second vertical test clips were
rendered with original audio and title-derived hook text, under
`work/renders/podcast-test/`. These are technical tests, not LLM/trend selections.
YouTube subtitle download returned HTTP 429. The initial real-footage tests had no
speech subtitles; the fullscreen revision uses local Whisper transcription with
word timestamps, uppercase captions, and animated yellow word emphasis. It is
saved in `work/renders/podcast-fullscreen/`. Their fixture timestamps are relative to the downloaded sample,
not the full original video. `work/` media is intentionally ignored by Git.

Docker/GMI execution has not been validated in this local environment. The Dockerfile
is a deployment handoff; an actual GMI instance and its public backend URL remain
the responsibility of the team's deployment integration.
