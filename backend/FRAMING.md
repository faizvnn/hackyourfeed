# Smart interview framing

Both stage-6 engines share source analysis, reframing and output checks from
`app/framing.py`. `RENDER_FRAMING=smart` is the default. It produces full-screen
9:16 video regardless of the old layout setting; `RENDER_FRAMING=static` restores
the previous manual `RENDER_LAYOUT` behavior for comparison.

## Behavior

1. Sample the actual source passage at 4 fps with the bundled YuNet face detector.
2. Reset tracking at visual cuts or large face-position jumps. Hold a missing
   track for at most 0.5 seconds within a shot, never across a detected cut.
3. Follow one face, smoothing movement while keeping the face inside the crop.
   Two separated faces of comparable size use stacked panels filling the canvas.
   This preserves both participants; it does not claim to identify the speaker.
4. Decode uniformly timed frames through FFmpeg and apply the temporal crop plan.
   Original audio is taken directly from the requested interval. Crop positions
   interpolate only inside the same shot and layout, never across camera cuts.
5. Choose caption bands with the least overlap with projected face boxes.
6. Detect faces in the final, captioned MP4 and compare with the source plan.

The detector model (232 KB) and its MIT license are included in `app/assets`.
No model download, API key or GPU is needed. Install `requirements-render.txt`
or run the project's usual `uv sync` to install OpenCV headless.

## Quality result and frontend contract

A clip's `framing` object contains `status` (passed/needs_review), sampled/source/
retained face-frame counts, retention rate, maximum lost-face and unverified-source
durations, warnings, and a method description.

A clip passes when at least 95% of eligible source-face samples are retained and
verified in the output, no consecutive lost-face interval exceeds one second,
and no unverified source interval exceeds one second. A target face must retain
at least 80% of its source box; output detections must overlap its projected box.
These are measured sampling criteria, not a guarantee for every decoded frame.
Missing source detections and missing output faces also count toward one continuous
unverified interval, so alternating misses cannot hide a prolonged visibility gap.

Passed clips have `render_url`. Review clips have `render_preview_url` and keep
their local `render_path` for inspection, but do not receive the UI's ready/download
action. The frontend labels them for review and displays warnings. All-review
jobs finish with inspectable results rather than presenting those clips as ready.
Actual encode or analysis failures still set `render_error` in the adaptive engine.

Legacy fixtures with no quality fields remain compatible. YouTube iframe previews
are explicitly labeled; a missing MP4 is not presented as a rendered clip.
YouTube/video playback errors display a message instead of captions alone.

## Outputs and evaluation

Alongside each smart-rendered clip:
- `*.framing.json`: clip-relative times, shot IDs, source detections and crops.
- `*.quality.json`: post-render measures and warnings.

Run from `backend/`:

```sh
python -m unittest discover -s tests -v
python scripts/evaluate_framing.py --source video.mp4 --end 15 --transcript transcript.json --job-id interview-check
```

The comparison writes before/after MP4s, `comparison.json` and a contact sheet
under `work/renders/interview-check-after/`. Transcript times must use the original
video timeline. The evaluation never calls Oriane or an LLM. `--framing static`
on `python -m app.render_cli` is available for manual regression comparisons.

## Limits

Face detection may miss profiles, small faces, occlusions, screen shares and
low-light shots. No face does not mean no person: uncertain passages are reviewed
instead of automatically approved. Shot and tracking rules are heuristics. Fast
cuts between samples can be missed. Screen recordings/b-roll are not automatically
classified, so they may be flagged even when intentionally present. More than two
faces selects the two largest comparable detections. There is no audiovisual
active-speaker model.

Smart framing adds CPU work and an intermediate video encode. Static mode remains
available for comparisons. Backend processes need a restart to load the new code;
changing an environment variable alone does not update a running job.
