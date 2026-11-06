"""Shared JSON contracts between pipeline stages.

Every stage takes one of these in and returns one of these out. If you need a
new field, add it here first so the other teams see it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------- stage 1 ---
class Segment(BaseModel):
    start: float
    end: float
    text: str


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


class ViralSet(BaseModel):
    videos: list[ViralVideo]


# ---------------------------------------------------------------- stage 4 ---
class HookPattern(BaseModel):
    name: str
    description: str
    examples: list[str]
    avg_views: int = 0


class Playbook(BaseModel):
    hook_patterns: list[HookPattern]
    on_screen_text_style: str
    ideal_duration_s: float
    pacing_wps: float  # words per second
    caption_formula: str
    takeaways: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- stage 5 ---
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
    render_path: str | None = None   # filled by stage 6
    render_url: str | None = None


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
