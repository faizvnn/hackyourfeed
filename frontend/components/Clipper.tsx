"use client";

import { useEffect, useState, type FormEvent } from "react";
import "./app.css";
import ClipPhone from "./ClipPhone";
import Timeline from "./Timeline";
import { clock } from "@/lib/time";
import type { Clip, Job, StageKey, Viral } from "@/lib/types";

const STEPS: { key: StageKey; label: string; running: string }[] = [
  { key: "ingest", label: "Download", running: "Downloading your video and its captions" },
  { key: "understand", label: "Read", running: "Reading the transcript for its best moments" },
  { key: "trends", label: "Study", running: "Finding the shorts breaking out in your niche" },
  { key: "playbook", label: "Playbook", running: "Working out how they hook and caption" },
  { key: "score", label: "Score", running: "Scoring every moment against the playbook" },
  { key: "render", label: "Render", running: "Cutting vertical clips with captions" },
];

const ERRORS: Record<string, string> = {
  empty: "Paste a YouTube video link first.",
  bad_link: "That isn't a YouTube link. Try one like youtube.com/watch?v=...",
  engine_offline: "clipy's engine isn't connected yet. Try again in a few minutes.",
  engine_failed: "clipy isn't responding. Try again in a minute.",
  engine_unreachable: "clipy isn't responding. Try again in a minute.",
  not_found: "That run expired. Paste the link again.",
};

const multiple = (v: Viral) => Math.round((v.views_rate_per_followers ?? 0) / 100);

function stepState(i: number, job: Job | null): "waiting" | "running" | "done" | "failed" {
  if (!job) return i === 0 ? "running" : "waiting";
  if (job.stage === "done") return "done";
  if (job.stage === "error") {
    const reached = [job.video, job.candidates, job.viral, job.playbook, job.clips].findIndex((x) => !x);
    const at = reached === -1 ? 5 : reached;
    return i < at ? "done" : i === at ? "failed" : "waiting";
  }
  const now = STEPS.findIndex((s) => s.key === job.stage);
  return i < now ? "done" : i === now ? "running" : "waiting";
}

export default function Clipper() {
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);

  async function start(link: string) {
    const value = link.trim();
    setError(null);
    if (!value) return setError(ERRORS.empty);
    setStarting(true);
    try {
      const r = await fetch("/api/jobs", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ url: value }) });
      const data = (await r.json().catch(() => ({}))) as { id?: string; error?: string };
      if (!r.ok || !data.id) return setError(ERRORS[data.error ?? "engine_unreachable"] ?? ERRORS.engine_unreachable);
      setJob(null);
      setJobId(data.id);
    } catch {
      setError(ERRORS.engine_unreachable);
    } finally {
      setStarting(false);
    }
  }

  // The landing page sends people here with ?url=... so the run starts by itself.
  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("url");
    if (q) {
      setUrl(q);
      start(q);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!jobId) return;
    let alive = true;
    let misses = 0;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const r = await fetch(`/api/jobs/${jobId}`, { cache: "no-store" });
        const data = (await r.json()) as Job & { error?: string };
        if (!alive) return;
        if (!r.ok) {
          if (r.status === 404) return reset(ERRORS.not_found);
          throw new Error(data.error);
        }
        misses = 0;
        setJob(data);
        if (data.stage === "done" || data.stage === "error") return;
      } catch {
        if (++misses >= 5) return reset(ERRORS.engine_unreachable);
      }
      timer = setTimeout(tick, 1200);
    };
    tick();
    return () => { alive = false; clearTimeout(timer); };
  }, [jobId]);

  function reset(message: string | null = null) {
    setJobId(null);
    setJob(null);
    setError(message);
    window.history.replaceState(null, "", "/app");
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    start(url);
  }

  const running = Boolean(jobId);
  const done = job?.stage === "done";
  const failed = job?.stage === "error";
  const current = STEPS.find((s, i) => stepState(i, job) === "running");

  return (
    <div className="p-page">
      <div className="wrap">
        <nav className="bar">
          <a className="mark" href="/"><span className="mark-cut"><i /></span>clipy</a>
          <span className="bar-note">Viral data from <b>Oriane</b></span>
        </nav>
      </div>

      <main className="wrap p-main">
        <form className="field p-field" onSubmit={submit}>
          <input
            type="url"
            inputMode="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="Paste YouTube video link here"
            aria-label="YouTube video link"
            aria-invalid={Boolean(error)}
            readOnly={running && !done && !failed}
          />
          {running && !done && !failed ? (
            <button className="btn dark" type="button" onClick={() => reset()}>Stop</button>
          ) : (
            <button className="btn" type="submit" disabled={starting}>{starting ? "Starting" : "Try now"}</button>
          )}
        </form>
        {error && <p className="field-error" role="alert">{error}</p>}

        {!running && (
          <section className="p-empty" aria-label="Your clips">
            <div className="p-empty-phones" aria-hidden="true"><i /><i /><i /></div>
            <p>Your three clips show up here.</p>
          </section>
        )}

        {running && (
          <>
            <section className="p-video">
              {job?.video?.thumbnail ? <img className="p-video-img pop" src={job.video.thumbnail} alt="" /> : <div className="p-video-img" />}
              <div className="p-video-text">
                <h1 className="p-video-title">{job?.video?.title ?? "Opening your video"}</h1>
                <p className="p-video-meta">
                  {job?.video ? <span>{job.video.channel}, {clock(job.video.duration)}</span> : null}
                  {job?.niche && <span className="chip">{job.niche}</span>}
                  {job?.sample && <span className="p-sample">Sample run</span>}
                </p>
              </div>
            </section>

            <ol className="p-steps" aria-label="Progress">
              {STEPS.map((s, i) => {
                const st = stepState(i, job);
                return (
                  <li key={s.key} className={`p-step is-${st}`}>
                    <span className="p-step-dot" aria-hidden="true">
                      {st === "running" ? <i className="spin" /> : st === "done" ? <svg viewBox="0 0 20 20" width="20" height="20"><circle cx="10" cy="10" r="10" fill="currentColor" /><path d="M5.5 10.5l3 3 6-6.5" stroke="#fff" strokeWidth="2.4" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg> : st === "failed" ? <svg viewBox="0 0 20 20" width="20" height="20"><circle cx="10" cy="10" r="10" fill="currentColor" /><path d="M6.5 6.5l7 7m0-7l-7 7" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" /></svg> : <i className="p-ring" />}
                    </span>
                    <span className="p-step-label">{s.label}</span>
                  </li>
                );
              })}
            </ol>
            {!done && !failed && current && <p className="p-now" aria-live="polite">{current.running}</p>}
            {failed && (
              <div className="p-fail" role="alert">
                <p>{job?.error || "This video didn't make it through."}</p>
                <button className="btn dark small" onClick={() => reset()}>Try another video</button>
              </div>
            )}

            {job?.video && (
              <Timeline duration={job.video.duration} chapters={job.video.chapters} candidates={job.candidates} clips={done ? job.clips : undefined} scanning={!done && !failed} />
            )}

            {done && job && <Results job={job} />}
          </>
        )}
      </main>

      <div className="wrap p-foot">
        <footer className="foot">
          <span>Viral data from Oriane. Clips are cut from your video&apos;s own words.</span>
          <a href="/">About clipy</a>
        </footer>
      </div>
    </div>
  );
}

function Results({ job }: { job: Job }) {
  const clips = job.clips ?? [];
  const viral = job.viral ?? [];
  const video = job.video!;
  if (!clips.length) {
    return <p className="p-none">No moment in this video opens strong enough to clip. Try another video.</p>;
  }
  return (
    <section className="p-results">
      <div className="p-clips">
        {clips.map((c, i) => <ClipCard key={c.id} clip={c} index={i} video={video} />)}
      </div>
      {viral.length > 0 && (
        <div className="p-basis">
          <p>Picked using {viral.length} breakout shorts{job.niche ? ` in ${job.niche}` : ""}{job.viral_window_days ? ` from the last ${job.viral_window_days} days` : ""}.</p>
          {viral.some((v) => v.thumbnail) && <div className="p-basis-row">
            {viral.filter((v) => v.thumbnail).slice(0, 10).map((v) => (
              <a key={v.id} className="thumb" href={v.url} target="_blank" rel="noopener noreferrer" aria-label={`@${v.handle}, ${multiple(v)}x their followers in views`}>
                <img src={v.thumbnail} alt="" />
              </a>
            ))}
          </div>}
        </div>
      )}
    </section>
  );
}

function ClipCard({ clip, index, video }: { clip: Clip; index: number; video: NonNullable<Job["video"]> }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    if (!clip.caption) return;
    try {
      await navigator.clipboard.writeText(clip.caption);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  }
  return (
    <article id={clip.id} className="p-clip pop" style={{ animationDelay: `${index * 120}ms` }}>
      <ClipPhone clip={clip} youtubeId={video.youtube_id} thumbnail={video.thumbnail} channel={video.channel} />
      <div className="p-clip-head">
        <span className="num">{clip.score}</span>
        <span className="p-clip-of">fit score{clip.pattern ? <><br />{clip.pattern}</> : null}</span>
      </div>
      <h2 className="p-clip-hook">{clip.hook_rewrite}</h2>
      <p className="p-clip-time">{clock(clip.start)} to {clock(clip.end)}, {Math.round(clip.end - clip.start)} seconds</p>
      {clip.reason && <p className="p-clip-reason">{clip.reason}</p>}
      <div className="p-clip-actions">
        {clip.video_url ? (
          <a className="btn small" href={clip.video_url} download>Download</a>
        ) : video.youtube_id ? (
          <a className="btn small" href={`https://www.youtube.com/watch?v=${video.youtube_id}&t=${Math.floor(clip.start)}s`} target="_blank" rel="noopener noreferrer">Open on YouTube</a>
        ) : null}
        {clip.caption && <button className="btn line small" onClick={copy}>{copied ? "Copied" : "Copy caption"}</button>}
      </div>
    </article>
  );
}
