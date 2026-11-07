import type { Job, StageKey, Word } from "./types";

// Shapes from backend/app/contracts.py (only the fields the page reads).
type Segment = { start: number; end: number; text: string };
type BJob = {
  id: string;
  url: string;
  status: string;
  error?: string | null;
  transcript?: { title?: string; duration?: number; segments?: Segment[] } | null;
  understanding?: {
    niche?: string;
    topics?: string[];
    keyword_sets?: { niche?: string[]; topic?: string[]; entity?: string[] };
    topic_map?: { start: number; end: number; topic: string }[];
  } | null;
  viral?: { videos?: { id: string; platform: string; handle: string; thumbnail_url?: string; views?: number; followers?: number; views_rate_per_followers?: number; duration?: number; hook_text?: string; on_screen_text?: string[]; caption?: string }[] } | null;
  playbook?: { hook_patterns?: { name: string; description?: string; examples?: string[] }[]; on_screen_text_style?: string; ideal_duration_s?: number; pacing_wps?: number; caption_formula?: string } | null;
  clips?: { clips?: { start: number; end: number; score: number; title?: string; hook_rewrite: string; on_screen_lines?: string[]; caption?: string; matched_pattern?: string; reason?: string; render_url?: string | null; render_preview_url?: string | null; render_error?: string | null; framing?: { status: "passed" | "needs_review"; retention_rate: number; warnings: string[] } | null }[] } | null;
};

const STAGES: Record<string, StageKey> = {
  queued: "ingest", ingest: "ingest", understand: "understand", trends: "trends",
  playbook: "playbook", direct: "score", render: "render", done: "done", error: "error",
};

const youtubeId = (url: string) => url.match(/(?:v=|youtu\.be\/|shorts\/|live\/|embed\/)([\w-]{11})/)?.[1];

const profileUrl = (platform: string, handle: string) =>
  platform === "tiktok" ? `https://www.tiktok.com/@${handle}` : platform === "instagram" ? `https://www.instagram.com/${handle}/` : `https://www.youtube.com/@${handle}`;

// Spread each caption segment's words evenly across its time, so the preview can show word-by-word captions.
function words(segments: Segment[], start: number, end: number): Word[] {
  const out: Word[] = [];
  for (const s of segments) {
    if (s.end <= start || s.start >= end) continue;
    const parts = s.text.split(/\s+/).filter(Boolean);
    const step = (s.end - s.start) / Math.max(1, parts.length);
    parts.forEach((text, i) => {
      const t = s.start + i * step;
      if (t >= start && t < end) out.push({ t: +t.toFixed(2), text });
    });
  }
  return out;
}

// Turn the team backend's GET /jobs/{id} reply into what the page reads.
export function fromBackend(raw: BJob, base: string): Job {
  const vid = youtubeId(raw.url ?? "");
  const segs = raw.transcript?.segments ?? [];
  const wordCount = segs.reduce((n, s) => n + s.text.split(/\s+/).filter(Boolean).length, 0);
  const duration = raw.transcript?.duration ?? 0;
  const u = raw.understanding;
  const pb = raw.playbook;
  const abs = (url?: string | null) => (url ? new URL(url, base + "/").toString() : null);

  return {
    id: raw.id,
    stage: STAGES[raw.status] ?? "ingest",
    error: raw.error ?? null,
    video: raw.transcript
      ? {
          url: raw.url,
          youtube_id: vid,
          title: raw.transcript.title || "Your video",
          duration,
          thumbnail: vid ? `https://i.ytimg.com/vi/${vid}/hqdefault.jpg` : undefined,
          chapters: (u?.topic_map ?? []).map((t) => ({ start: t.start, title: t.topic })),
        }
      : undefined,
    transcript_stats: raw.transcript ? { segments: segs.length, words: wordCount, wpm: duration ? Math.round(wordCount / (duration / 60)) : undefined } : undefined,
    niche: u?.niche,
    keywords: u ? { topic: u.keyword_sets?.topic, niche: u.keyword_sets?.niche, general: u.keyword_sets?.entity } : undefined,
    viral: raw.viral?.videos
      ? raw.viral.videos.map((v) => ({
          id: v.id,
          platform: v.platform,
          handle: v.handle,
          url: profileUrl(v.platform, v.handle),
          thumbnail: v.thumbnail_url ?? "",
          hook: v.hook_text,
          on_screen_text: v.on_screen_text?.join(" / "),
          caption: v.caption,
          duration: v.duration,
          views: v.views ?? 0,
          followers: v.followers,
          views_rate_per_followers: v.views_rate_per_followers,
        }))
      : undefined,
    playbook: pb
      ? {
          hook_patterns: (pb.hook_patterns ?? []).map((p) => ({ name: p.name, template: p.examples?.[0] ?? "", why: p.description })),
          on_screen_text_style: pb.on_screen_text_style,
          ideal_length_seconds: pb.ideal_duration_s,
          pacing_wpm: pb.pacing_wps ? Math.round(pb.pacing_wps * 60) : undefined,
          caption_formula: pb.caption_formula,
        }
      : undefined,
    clips: raw.clips?.clips
      ? raw.clips.clips.map((c, i) => ({
          id: `clip_${i + 1}`,
          start: c.start,
          end: c.end,
          score: c.score,
          pattern: c.matched_pattern,
          hook_rewrite: c.hook_rewrite || c.title || "",
          on_screen_lines: c.on_screen_lines,
          caption: c.caption,
          reason: c.reason,
          video_url: abs(c.render_url),
          preview_url: abs(c.render_preview_url),
          render_error: c.render_error,
          framing: c.framing,
          transcript: words(segs, c.start, c.end),
        }))
      : undefined,
  };
}
