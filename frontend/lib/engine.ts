import sampleRun from "@/data/job.json";
import type { Job, StageKey } from "./types";

// When BACKEND_URL is set (server only, never sent to the browser), the page talks to the team's FastAPI box.
// Without it, a stand-in replays one saved real run so the page can be built and demoed offline.
export const backendUrl = () => process.env.BACKEND_URL?.replace(/\/+$/, "") || "";

export const SAMPLE_YOUTUBE_ID = "x_5JijpzprU";

export function youtubeId(url: string): string | null {
  const m = url.trim().match(/(?:youtube\.com\/(?:watch\?(?:.*&)?v=|shorts\/|live\/|embed\/)|youtu\.be\/)([\w-]{11})/i);
  return m ? m[1] : null;
}

type Run = { started: number };
const g = globalThis as unknown as { __runs?: Map<string, Run> };
const runs = (g.__runs ??= new Map());

export function startSample(): string {
  const id = "sample-" + Date.now().toString(36);
  runs.set(id, { started: Date.now() });
  return id;
}

const savedJob = (): Job => sampleRun as unknown as Job;

// Seconds at which each stage of the saved run finishes when replayed (about 15s in all).
const replay: [StageKey, number][] = [["ingest", 2.2], ["understand", 5.2], ["trends", 7.6], ["playbook", 10.2], ["score", 12.6], ["render", 15]];

export function readSample(id: string): Job | null {
  const run = runs.get(id);
  if (!run) return null;
  const t = (Date.now() - run.started) / 1000;
  const s = savedJob();
  const passed = (k: StageKey) => t >= replay.find(([key]) => key === k)![1];
  const current = replay.find(([, at]) => t < at)?.[0] ?? "done";
  const job: Job = { id, stage: current, sample: true };
  if (passed("ingest")) Object.assign(job, { video: s.video, transcript_stats: s.transcript_stats });
  if (passed("understand")) Object.assign(job, { niche: s.niche, keywords: s.keywords, candidates: s.candidates });
  if (passed("trends")) Object.assign(job, { viral: s.viral, viral_window_days: s.viral_window_days });
  if (passed("playbook")) job.playbook = s.playbook;
  if (passed("score")) job.clips = s.clips;
  return job;
}
