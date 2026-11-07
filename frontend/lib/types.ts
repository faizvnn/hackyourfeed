// What the page reads from GET /jobs/{id}. Every field after `stage` is optional,
// so the backend can fill them in as each stage finishes. Full contract: API.md.

export type StageKey = "ingest" | "understand" | "trends" | "playbook" | "score" | "render" | "done" | "error";

export type Word = { t: number; text: string }; // t = seconds into the episode

export type Viral = {
  id: string;
  platform: string;
  handle: string;
  url: string;
  thumbnail: string;
  hook?: string; // spoken in the first seconds
  on_screen_text?: string;
  caption?: string;
  duration?: number | null;
  views: number;
  followers?: number;
  views_rate_per_followers?: number; // Oriane's percent, 300 = 3x
  published_at?: string;
};

export type HookPattern = { name: string; template: string; why?: string; example_ids?: string[] };

export type Playbook = {
  hook_patterns: HookPattern[];
  on_screen_text_style?: string;
  ideal_length_seconds?: [number, number] | number;
  pacing_wpm?: number;
  caption_formula?: string;
};

export type Clip = {
  id: string;
  start: number;
  end: number;
  score: number;
  pattern?: string;
  hook_rewrite: string;
  on_screen_lines?: string[];
  caption?: string;
  reason?: string;
  video_url?: string | null; // the rendered 9:16 mp4
  preview_url?: string | null; // rendered but awaiting framing review
  render_error?: string | null;
  framing?: { status: "passed" | "needs_review"; retention_rate: number; warnings: string[] } | null;
  transcript?: Word[];
};

export type Job = {
  id: string;
  stage: StageKey;
  error?: string | null;
  sample?: boolean; // true when the page's stand-in served saved data instead of the real backend
  video?: { url: string; youtube_id?: string; title: string; channel?: string; duration: number; thumbnail?: string; chapters?: { start: number; title: string }[] };
  transcript_stats?: { segments?: number; words?: number; wpm?: number };
  niche?: string;
  keywords?: { topic?: string[]; niche?: string[]; general?: string[] };
  candidates?: { start: number; end: number; why?: string }[];
  viral?: Viral[];
  viral_window_days?: number;
  playbook?: Playbook;
  clips?: Clip[];
};
