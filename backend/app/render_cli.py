"""Standalone runner for the experimental adaptive render: python -m app.render_cli --demo.

Always uses s6_render_adaptive regardless of RENDER_ENGINE.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import replace
from pathlib import Path

from .config import WORK_DIR
from .contracts import Clip, ClipSet, Segment, Transcript
from .pipeline.s6_render_adaptive import RenderOptions, _execute, run


def demo_input(options: RenderOptions) -> tuple[Transcript, ClipSet]:
    """Explicitly synthetic media to verify rendering without YouTube or API keys."""
    folder = (WORK_DIR / "render-demo").resolve()
    folder.mkdir(parents=True, exist_ok=True)
    video = folder / "source.mp4"
    _execute([
        options.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=960x540:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
        "-t", "8", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(video),
    ], timeout=options.timeout)
    transcript = Transcript(
        source_url="synthetic://render-smoke-test", title="Synthetic renderer demo (not podcast footage)",
        duration=8, video_path=str(video), segments=[
            Segment(start=0, end=2, text="Prueba sintética: estos subtítulos no son una transcripción de audio."),
            Segment(start=2, end=4, text="El render conserva el encuadre y adapta el video a formato vertical."),
            Segment(start=4, end=6, text="Admite acentos: generación, edición y sincronización."),
            Segment(start=6, end=8, text="El resultado está listo para reproducir y descargar desde la web."),
        ],
    )
    clips = ClipSet(clips=[Clip(
        start=start, end=end, score=0, title=f"Synthetic demo {i + 1}",
        hook_rewrite=hook, on_screen_lines=[], caption="Synthetic render test; not a real podcast.",
        matched_pattern="smoke-test", reason="Verify stage 6 independently of the other stages.",
    ) for i, (start, end, hook) in enumerate([
        (0, 3, "Tu podcast, en formato vertical"),
        (2, 5, "Hook + subtítulos sincronizados"),
        (4, 8, "Tres clips listos para compartir"),
    ])])
    (folder / "transcript.json").write_text(transcript.model_dump_json(indent=2), encoding="utf-8")
    (folder / "clips.json").write_text(clips.model_dump_json(indent=2), encoding="utf-8")
    return transcript, clips


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="Generate labeled synthetic test footage")
    parser.add_argument("--transcript", type=Path, help="Stage 1 Transcript JSON")
    parser.add_argument("--clips", type=Path, help="Stage 5 ClipSet JSON")
    parser.add_argument("--video", type=Path, help="Override transcript.video_path")
    parser.add_argument("--job-id", default="render-demo")
    parser.add_argument("--layout", choices=["blur", "crop"])
    parser.add_argument("--framing", choices=["smart", "static"], help="Face-guided framing or legacy fixed crop")
    parser.add_argument("--crop-center-x", type=float, help="Horizontal center in source frame, 0..1")
    parser.add_argument("--transcribe", action="store_true", help="Generate precise word times using local Whisper")
    parser.add_argument("--whisper-model", default="base", help="Local ASR model; downloaded on first use")
    args = parser.parse_args()
    if args.demo and (args.transcript or args.clips or args.video or args.transcribe):
        parser.error("--demo cannot be combined with real inputs or --transcribe")
    if not args.demo and not (args.transcript and args.clips):
        parser.error("provide --demo, or both --transcript and --clips")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", args.job_id):
        parser.error("job-id must contain only letters, numbers, underscores or hyphens")
    options = RenderOptions.from_env()
    if args.layout:
        options = replace(options, layout=args.layout)
    if args.framing:
        options = replace(options, framing=args.framing)
    if args.crop_center_x is not None:
        options = replace(options, crop_center_x=args.crop_center_x)
    options.validate()
    if args.demo:
        transcript, clips = demo_input(options)
    else:
        transcript = Transcript.model_validate_json(args.transcript.read_text(encoding="utf-8-sig"))
        clips = ClipSet.model_validate_json(args.clips.read_text(encoding="utf-8-sig"))
        if args.video:
            transcript.video_path = str(args.video.resolve())
        elif transcript.video_path and not Path(transcript.video_path).is_absolute():
            transcript.video_path = str((args.transcript.resolve().parent / transcript.video_path).resolve())
    if args.transcribe:
        from .transcribe_local import transcribe
        transcript = transcribe(transcript, model_name=args.whisper_model)
        saved = WORK_DIR / "transcripts" / f"{args.job_id}.json"
        saved.parent.mkdir(parents=True, exist_ok=True)
        saved.write_text(transcript.model_dump_json(indent=2), encoding="utf-8")
    result = run(args.job_id, transcript, clips, options=options)
    # ASCII JSON also works in Windows terminals with legacy encodings.
    print(json.dumps(result.model_dump(), indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
