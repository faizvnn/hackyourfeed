"""Shared JSON contracts between pipeline stages.

Every stage takes one of these in and returns one of these out. If you need a
new field, add it here first so the other teams see it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------- stage 1 ---
class WordTiming(BaseModel):
    start: float
    end: float
    text: str


class Segment(BaseModel):
    start: float
    end: float
    text: str
    words: list[WordTiming] = Field(default_factory=list)  # optional precise caption timing


class Transcript(BaseModel):
    source_url: str
    title: str = ""
    duration: float = 0
    video_path: str | None = None  # local mp4, needed by stage 6
    segments: list[Segment]


# ---------------------------------------------------------------- stage 2 ---
class Moment(BaseModel):
    start: float
    end: float
    summary: str
    why: str


class KeywordSets(BaseModel):
    topic: list[str] = Field(default_factory=list)    # "founder burnout", "seed round"
    niche: list[str] = Field(default_factory=list)    # "startup", "VC", "founder"
    general: list[str] = Field(default_factory=list)  # "podcast", "podcastclips"


class Understanding(BaseModel):
    niche: str
    summary: str
    topics: list[str]
    competitor_handles: list[str] = Field(default_factory=list)
    keyword_sets: KeywordSets
    candidate_moments: list[Moment]


# ---------------------------------------------------------------- stage 3 ---
class TextObservation(BaseModel):
    text: str
    timestamp_seconds: float = Field(ge=0)
    center_y: float = Field(ge=0, le=1)
    height: float = Field(ge=0, le=1)


class ViralVideo(BaseModel):
    """A compact view of one Oriane result, enough for the playbook prompt."""

    id: str
    platform: Literal["instagram", "tiktok", "youtube"]
    handle: str
    thumbnail_url: str = ""
    views: int = 0
    likes: int = 0
    followers: int = 0
    views_rate_per_followers: float = 0
    duration: float = 0
    hook_text: str = ""              # first transcript chunk
    transcript: str = ""
    on_screen_text: list[str] = Field(default_factory=list)
    caption: str = ""
    hashtags: list[str] = Field(default_factory=list)
    words_per_second: float = 0
    granularity: Literal["topic", "niche", "general"] = "niche"
    published_at: str = ""
    text_observations: list[TextObservation] = Field(default_factory=list)


class ViralSet(BaseModel):
    videos: list[ViralVideo]


# ---------------------------------------------------------------- stage 4 ---
class HookPattern(BaseModel):
    name: str
    description: str
    examples: list[str]
    avg_views: int = 0


class CaptionStyle(BaseModel):
    """Bounded rendering directions, with provenance separate from visual choices."""
    words_per_group: int = Field(default=3, ge=1, le=6)
    max_chars_per_group: int = Field(default=23, ge=12, le=36)
    letter_case: Literal["uppercase", "original"] = "uppercase"
    font_size: int = Field(default=58, ge=40, le=68)  # in 720x1280 design coordinates
    position: Literal["lower", "middle"] = "lower"
    highlight_color: Literal["yellow", "lime", "cyan", "white"] = "yellow"
    emphasis: Literal["active_word", "keywords", "none"] = "active_word"
    animation: Literal["pop", "none"] = "pop"
    hook_seconds: float = Field(default=2, ge=0, le=3, allow_inf_nan=False)
    evidence_video_ids: list[str] = Field(default_factory=list, max_length=10)
    evidence_basis: Literal["ocr_samples", "text_only", "fallback"] = "fallback"
    rationale: str = "Readable fallback; no reference-backed caption plan supplied."


class Playbook(BaseModel):
    hook_patterns: list[HookPattern]
    on_screen_text_style: str
    ideal_duration_s: float
    pacing_wps: float  # words per second
    caption_formula: str
    takeaways: list[str] = Field(default_factory=list)
    caption_style: CaptionStyle | None = None


# ---------------------------------------------------------------- stage 5 ---
class Clip(BaseModel):
    start: float
    end: float
    score: int
    title: str
    hook_rewrite: str                # on-screen hook; rendering preserves original audio
    on_screen_lines: list[str]
    caption: str
    matched_pattern: str
    reason: str
    render_style: CaptionStyle | None = None  # stage 4 recommendation adapted by stage 5
    emphasis_keywords: list[str] = Field(default_factory=list, max_length=20)
    render_path: str | None = None   # filled by stage 6
    render_url: str | None = None
    render_error: str | None = None  # individual render failure; other clips remain usable


class ClipSet(BaseModel):
    clips: list[Clip]


# ------------------------------------------------------------------- job ---
Stage = Literal[
    "queued", "ingest", "understand", "trends", "playbook", "direct", "render", "done", "error"
]


class Job(BaseModel):
    id: str
    url: str
    status: Stage = "queued"
    error: str | None = None
    transcript: Transcript | None = None
    understanding: Understanding | None = None
    viral: ViralSet | None = None
    playbook: Playbook | None = None
    clips: ClipSet | None = None
