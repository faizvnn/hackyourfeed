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
    words: list[WordTiming] = Field(default_factory=list)  # optional precise caption timing (adaptive render)


class Transcript(BaseModel):
    source_url: str
    title: str = ""
    duration: float = 0
    video_path: str | None = None  # local mp4, needed by stage 6
    segments: list[Segment]


# ---------------------------------------------------------------- stage 2 ---
# Stage 2 does NOT pick clips. It only describes the episode and produces the
# search terms for Oriane; clip selection happens in stage 5, once the playbook
# says what is actually going viral.
class TopicSection(BaseModel):
    start: float
    end: float
    topic: str


class KeywordSets(BaseModel):
    niche: list[str] = Field(default_factory=list)   # broad:    "startup", "VC", "founder"
    topic: list[str] = Field(default_factory=list)   # specific: "founder burnout", "seed round"
    entity: list[str] = Field(default_factory=list)  # guest / company / product names


class Reference(BaseModel):
    """A show or famous person this episode resembles; stage 3 searches Oriane for their viral clips."""

    kind: Literal["show", "person"]
    name: str                                            # "All-In Podcast", "Sam Altman"
    aliases: list[str] = Field(default_factory=list)     # other ways people write/say it: "All-In with Chamath"
    hashtags: list[str] = Field(default_factory=list)    # without '#': "allinpod"
    handles: list[str] = Field(default_factory=list)     # IG / TikTok accounts, without '@'


class Understanding(BaseModel):
    niche: str
    summary: str
    topics: list[str]
    category: str = ""                                            # one of categories.CATEGORIES; stage 3 falls back to it
    references: list[Reference] = Field(default_factory=list)     # host show, guest, 3-5 comparable shows / people
    competitor_handles: list[str] = Field(default_factory=list)   # podcast / clip accounts whose shorts are the target format
    keyword_sets: KeywordSets
    topic_map: list[TopicSection] = Field(default_factory=list)  # where each topic is discussed


# ---------------------------------------------------------------- stage 3 ---
class TextObservation(BaseModel):
    """Sampled OCR geometry from an Oriane frame (adaptive render playbook input)."""

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
    granularity: Literal["niche", "topic", "entity"] = "niche"  # which stage-3 search found it: accounts / topic phrases / guest names
    matched: list[str] = Field(default_factory=list)            # every stage-3 search that matched (Oriane matchedQueries)
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
    """Bounded caption directions for the adaptive render (RENDER_ENGINE=adaptive).

    Stage 4/5 do not fill this yet; the adaptive render falls back to the defaults.
    """

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
    caption_style: CaptionStyle | None = None  # adaptive render only


# ---------------------------------------------------------------- stage 5 ---
class FramingQuality(BaseModel):
    status: Literal["passed", "needs_review"]
    sampled_frames: int
    source_face_frames: int
    retained_face_frames: int
    retention_rate: float
    max_lost_face_seconds: float
    max_unverified_seconds: float
    max_unverified_output_seconds: float = 0
    warnings: list[str] = Field(default_factory=list)
    method: str


class Clip(BaseModel):
    start: float
    end: float
    score: int
    title: str
    hook_rewrite: str                # spoken / first on-screen line
    on_screen_lines: list[str]
    caption: str
    matched_pattern: str
    reason: str
    render_style: CaptionStyle | None = None  # adaptive render only; None = defaults
    emphasis_keywords: list[str] = Field(default_factory=list, max_length=20)
    render_path: str | None = None   # filled by stage 6
    render_url: str | None = None
    render_error: str | None = None  # adaptive render: per-clip failure, other clips stay usable
    render_preview_url: str | None = None  # inspectable output withheld from ready/download state
    framing: FramingQuality | None = None


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
