import "./landing.css";
import ClipPhone from "./ClipPhone";
import Timeline from "./Timeline";
import { clock } from "@/lib/time";
import type { Job, Viral } from "@/lib/types";

const multiple = (v: Viral) => Math.round((v.views_rate_per_followers ?? 0) / 100);
const views = (n: number) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${Math.round(n / 1e3)}K` : String(n));

const STEPS = [
  { name: "Download", line: "Pulls your video and its captions from YouTube." },
  { name: "Read", line: "Finds the niche and the 15 to 20 strongest moments." },
  { name: "Study", line: "Oriane finds the shorts breaking out in that niche." },
  { name: "Playbook", line: "Learns their hooks, on-screen text, length and pace." },
  { name: "Score", line: "Rates every moment against the playbook. Top 3 win." },
  { name: "Render", line: "Cuts vertical Shorts with the hook and captions burned in." },
];

function LinkField({ id }: { id: string }) {
  return (
    <form className="field" action="/app" method="get">
      <input id={id} name="url" type="url" inputMode="url" required placeholder="Paste YouTube video link here" aria-label="YouTube video link" />
      <button className="btn" type="submit">Try now</button>
    </form>
  );
}

export default function Landing({ job }: { job: Job }) {
  const video = job.video!;
  const clips = job.clips ?? [];
  const viral = job.viral ?? [];
  const pb = job.playbook!;
  const featured = pb.hook_patterns.find((p) => p.name === clips[0]?.pattern) ?? pb.hook_patterns[0];
  const proof = (featured.example_ids ?? []).map((id) => viral.find((v) => v.id === id)).filter((v): v is Viral => Boolean(v));
  const others = pb.hook_patterns.filter((p) => p !== featured);
  const len = Array.isArray(pb.ideal_length_seconds) ? `${pb.ideal_length_seconds[0]} to ${pb.ideal_length_seconds[1]}` : String(pb.ideal_length_seconds ?? "");
  const minutes = Math.round(video.duration / 60);
  const fan = clips.length === 3 ? [clips[1], clips[0], clips[2]] : clips; // best clip in the middle

  return (
    <div className="l-page">
      <div className="wrap">
        <nav className="bar">
          <a className="mark" href="/"><span className="mark-cut"><i /></span>clipy</a>
          <a className="btn line small" href="/app">Open clipy</a>
        </nav>
      </div>

      <header className="wrap l-hero">
        <div className="l-hero-copy">
          <h1 className="headline h-xl">Be number #1 in your niche</h1>
          <p className="lede">Paste your YouTube video and we do the rest.</p>
          <LinkField id="hero-link" />
        </div>
        <div className="l-fan" aria-label="Three real clips clipy cut from one video">
          {fan.map((c) => (
            <div key={c.id} id={c.id} className="l-fan-phone">
              <ClipPhone clip={c} youtubeId={video.youtube_id} thumbnail={video.thumbnail} channel={video.channel} />
            </div>
          ))}
        </div>
      </header>

      <section className="wrap l-proof">
        <div className="l-proof-head">
          <h2 className="headline h-l">One video in. Three clips out.</h2>
          <p className="lede">Those clips are real. We gave clipy a {minutes} minute video from {video.channel} and it picked these three moments, each opening the way the breakout shorts in its niche do.</p>
        </div>
        <div>
          <Timeline duration={video.duration} chapters={video.chapters} candidates={job.candidates} clips={clips} />
          <p className="l-proof-cap">The whole video. Grey marks are the {job.candidates?.length ?? 0} moments it weighed. The three it cut are numbered.</p>
        </div>
        <ol className="l-cuts">
          {clips.map((c, i) => (
            <li key={c.id} className="l-cut">
              <span className="l-cut-score num">{c.score}</span>
              <div className="l-cut-body">
                <p className="l-cut-meta">Clip {i + 1}, {clock(c.start)} to {clock(c.end)}{c.pattern ? <span className="chip">Opens like: {c.pattern}</span> : null}</p>
                <h3 className="l-cut-hook">{c.hook_rewrite}</h3>
                {c.reason && <p className="l-cut-reason">{c.reason}</p>}
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="wrap l-learn">
        <div className="l-learn-head">
          <h2 className="headline h-l">It learns from what&apos;s already winning.</h2>
          <p className="lede">Before cutting anything, clipy studies the shorts in your niche that pulled far more views than their creator has followers. When a small account breaks out, the hook did the work. For this video it studied {viral.length} of them.</p>
        </div>
        <div className="l-pattern">
          <div className="l-pattern-text">
            <p className="l-pattern-name">Top hook in this niche: <b>{featured.name}</b></p>
            <p className="l-pattern-template">{featured.template}</p>
            {featured.why && <p className="l-pattern-why">{featured.why}</p>}
          </div>
          <div className="l-pattern-proof">
            {proof.map((v) => (
              <a key={v.id} className="thumb" href={v.url} target="_blank" rel="noopener noreferrer" aria-label={`@${v.handle}, ${views(v.views)} views`}>
                <img src={v.thumbnail} alt="" />
                <span className="thumb-x">{multiple(v)}x followers</span>
              </a>
            ))}
          </div>
        </div>
        <dl className="l-specs">
          <div><dt>Also working</dt><dd>{others.map((p) => p.name).join(", ")}</dd></div>
          <div><dt>Ideal length</dt><dd>{len} seconds</dd></div>
          <div><dt>Pacing</dt><dd>{pb.pacing_wpm} words a minute. This video talks at {job.transcript_stats?.wpm}.</dd></div>
          <div><dt>Captions</dt><dd>{pb.caption_formula}</dd></div>
        </dl>
      </section>

      <section className="wrap l-how">
        <h2 className="headline h-l">Six steps from video to Shorts.</h2>
        <ol className="l-steps">
          {STEPS.map((s, i) => (
            <li key={s.name} className="l-step">
              <span className="l-step-n">{i + 1}</span>
              <span className="l-step-name">{s.name}</span>
              <span className="l-step-line">{s.line}</span>
            </li>
          ))}
        </ol>
      </section>

      <section className="wrap l-who">
        <div className="l-who-a">
          <h3 className="headline h-m">For creators</h3>
          <p>Every long video you post already has Shorts in it. clipy finds them for you.</p>
          <p>Each clip opens the way your niche&apos;s breakout videos open right now.</p>
          <p>Each one comes with the reason it was picked and a caption ready to paste.</p>
        </div>
        <div className="l-who-b">
          <h3 className="headline h-m">For clippers</h3>
          <p>You get paid per view, so a clip that flops is time you don&apos;t get back.</p>
          <p>Start every video knowing which openings are winning in that niche.</p>
          <p>Three ready clips per video, scored against real breakouts.</p>
        </div>
      </section>

      <section className="wrap l-close">
        <h2 className="headline h-l">Your next video already has three Shorts in it.</h2>
        <LinkField id="close-link" />
      </section>

      <div className="wrap">
        <footer className="foot">
          <span>Viral data from Oriane. Clips are cut from your video&apos;s own words.</span>
          <span>Built at Hack the Feed, November 2026.</span>
        </footer>
      </div>
    </div>
  );
}
