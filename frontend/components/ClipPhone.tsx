"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { Clip, Word } from "@/lib/types";

import { clock } from "@/lib/time";
export { clock };

type YTPlayer = { playVideo(): void; pauseVideo(): void; seekTo(s: number, a: boolean): void; getCurrentTime(): number; destroy(): void };
type YTNamespace = { Player: new (el: HTMLElement, opts: unknown) => YTPlayer };

let ytLoad: Promise<YTNamespace> | null = null;
function loadYouTube(): Promise<YTNamespace> {
  if (ytLoad) return ytLoad;
  ytLoad = new Promise((resolve) => {
    const w = window as unknown as { YT?: YTNamespace; onYouTubeIframeAPIReady?: () => void };
    if (w.YT?.Player) return resolve(w.YT);
    const prev = w.onYouTubeIframeAPIReady;
    w.onYouTubeIframeAPIReady = () => { prev?.(); resolve(w.YT!); };
    const s = document.createElement("script");
    s.src = "https://www.youtube.com/iframe_api";
    document.head.appendChild(s);
  });
  return ytLoad;
}

// Split the clip's real words into short caption bursts, the way clippers burn them in.
function bursts(words: Word[]): Word[][] {
  const clean = words.map((w) => ({ ...w, text: w.text.replace(/^>>\s*/, "").trim() })).filter((w) => w.text && w.text !== ">>");
  const out: Word[][] = [];
  let cur: Word[] = [];
  for (const w of clean) {
    cur.push(w);
    if (cur.length >= 4 || /[.,!?;:]$/.test(w.text)) { out.push(cur); cur = []; }
  }
  if (cur.length) out.push(cur);
  return out;
}

export default function ClipPhone({ clip, youtubeId, thumbnail, channel }: { clip: Clip; youtubeId?: string; thumbnail?: string; channel?: string }) {
  const host = useRef<HTMLDivElement>(null);
  const player = useRef<YTPlayer | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "playing" | "paused">("idle");
  const [now, setNow] = useState(clip.start);
  const groups = useMemo(() => bursts(clip.transcript ?? []), [clip.transcript]);
  const len = clip.end - clip.start;

  useEffect(() => {
    const stop = (e: Event) => { if ((e as CustomEvent).detail !== clip.id && player.current) { player.current.pauseVideo(); setState((s) => (s === "playing" ? "paused" : s)); } };
    window.addEventListener("clip-play", stop);
    return () => { window.removeEventListener("clip-play", stop); player.current?.destroy(); };
  }, [clip.id]);

  useEffect(() => {
    if (state !== "playing") return;
    const iv = setInterval(() => {
      const t = player.current?.getCurrentTime() ?? clip.start;
      if (t >= clip.end) { player.current?.seekTo(clip.start, true); setNow(clip.start); } else setNow(t);
    }, 100);
    return () => clearInterval(iv);
  }, [state, clip.start, clip.end]);

  async function toggle() {
    window.dispatchEvent(new CustomEvent("clip-play", { detail: clip.id }));
    if (state === "playing") { player.current?.pauseVideo(); setState("paused"); return; }
    if (player.current) { player.current.playVideo(); setState("playing"); return; }
    if (!youtubeId || !host.current) return;
    setState("loading");
    const YT = await loadYouTube();
    const el = document.createElement("div");
    host.current.appendChild(el);
    player.current = new YT.Player(el, {
      videoId: youtubeId,
      playerVars: { start: Math.floor(clip.start), autoplay: 1, controls: 0, rel: 0, playsinline: 1, disablekb: 1, iv_load_policy: 3, modestbranding: 1 },
      events: {
        onReady: (e: { target: YTPlayer }) => e.target.playVideo(),
        onStateChange: (e: { data: number }) => { if (e.data === 1) setState("playing"); if (e.data === 2) setState("paused"); },
      },
    });
  }

  if (clip.video_url) {
    return (
      <div className="phone-wrap">
        <div className="phone">
          <video src={clip.video_url} poster={thumbnail} controls playsInline preload="metadata" />
        </div>
      </div>
    );
  }

  const live = state === "playing" || state === "paused";
  const gi = live ? Math.max(0, groups.findIndex((g, i) => now < (groups[i + 1]?.[0].t ?? Infinity))) : 0;
  const group = groups[gi] ?? [];
  const lines = clip.on_screen_lines?.length ? clip.on_screen_lines : [clip.hook_rewrite];

  return (
    <div className="phone-wrap">
      <div className="phone">
        <div className="phone-stage">
          <div className="phone-media">
            {thumbnail && <img src={thumbnail} alt="" style={{ opacity: live ? 0 : 1, transition: "opacity .3s" }} />}
            <div ref={host} style={{ pointerEvents: "none" }} />
          </div>
        </div>
        <div className="phone-top">
          {lines.map((l, i) => (
            <div key={i}><span className={`phone-line${i === lines.length - 1 ? " hot" : ""}`}>{l}</span></div>
          ))}
        </div>
        <div className="phone-sub" aria-live="off">
          {group.map((w, i) => (
            <span key={i} className={live && now >= w.t && (group[i + 1] ? now < group[i + 1].t : true) ? "now" : ""}>{w.text} </span>
          ))}
        </div>
        {channel && <div className="phone-handle">from {channel}</div>}
        <div className="phone-time">{live ? `${clock(now - clip.start)} / ${clock(len)}` : clock(len)}</div>
        <button className="phone-play" onClick={toggle} aria-label={state === "playing" ? "Pause clip" : "Play clip"}>
          {state !== "playing" && (
            <span>{state === "loading" ? <i className="spin" style={{ borderColor: "rgba(255,255,255,.35)", borderTopColor: "#fff" }} /> : <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 4.5v15l13-7.5z" /></svg>}</span>
          )}
        </button>
      </div>
    </div>
  );
}
