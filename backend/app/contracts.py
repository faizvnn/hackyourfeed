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
