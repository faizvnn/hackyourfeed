"""Optional offline-ASR adapter for videos without downloadable captions."""
from __future__ import annotations

from pathlib import Path

from .config import WORK_DIR
from .contracts import Segment, Transcript, WordTiming


def transcribe(t: Transcript, *, model_name: str = "base") -> Transcript:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("Install requirements-transcribe.txt to use --transcribe") from exc
    if not t.video_path or not Path(t.video_path).is_file():
        raise ValueError("Transcription needs an existing video_path")
    model = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=4,
                         download_root=str((WORK_DIR / "models").resolve()))
    segments, _ = model.transcribe(t.video_path, word_timestamps=True, beam_size=5,
                                   condition_on_previous_text=False)
    t.segments = [Segment(
        start=s.start, end=s.end, text=s.text.strip(),
        words=[WordTiming(start=w.start, end=w.end, text=w.word.strip())
               for w in (s.words or []) if w.word.strip() and w.end > w.start],
    ) for s in segments if s.text.strip()]
    if not t.segments:
        raise RuntimeError("No speech detected; no captions were generated")
    return t
