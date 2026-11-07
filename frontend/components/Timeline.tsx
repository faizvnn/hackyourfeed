import type { Clip } from "@/lib/types";
import { clock } from "@/lib/time";

type Props = {
  duration: number;
  chapters?: { start: number; title: string }[];
  candidates?: { start: number; end: number }[];
  clips?: Clip[];
  scanning?: boolean;
};

// The whole video as one editing track: chapters, every possible moment, and the clips cut out of it.
export default function Timeline({ duration, chapters = [], candidates = [], clips = [], scanning }: Props) {
  const pct = (s: number) => `${Math.min(100, Math.max(0, (s / duration) * 100))}%`;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => clock(f * duration));
  return (
    <div className="tl">
      <div className="tl-track">
        {chapters.map((c, i) => (
          <div key={i} className="tl-chapter" style={{ left: pct(c.start), width: `calc(${pct((chapters[i + 1]?.start ?? duration) - c.start)})` }} title={c.title}>
            {c.title}
          </div>
        ))}
        {candidates.map((c, i) => (
          <div key={i} className="tl-cand pop" style={{ left: pct(c.start), width: `max(3px, ${pct(c.end - c.start)})`, animationDelay: `${i * 40}ms` }} />
        ))}
        {clips.map((c, i) => (
          <a key={c.id} href={`#${c.id}`} className="tl-clip" style={{ left: pct(c.start), width: pct(c.end - c.start), animationDelay: `${i * 160}ms` }} aria-label={`Clip ${i + 1}, ${clock(c.start)} to ${clock(c.end)}`}>
            {i + 1}
          </a>
        ))}
        {scanning && <div className="tl-head" />}
      </div>
      <div className="tl-ruler" aria-hidden="true">
        {ticks.map((t, i) => <span key={i}>{t}</span>)}
      </div>
    </div>
  );
}
