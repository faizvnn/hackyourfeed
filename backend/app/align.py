"""Find where a line of text is spoken in a transcript.

Stage 5 uses it to open each clip where its hook is actually said (the model's
[mm:ss] -> seconds arithmetic is unreliable, so its span often misses the very
lines it quotes). Stage 6 uses it to put each on-screen line up when its words
are spoken instead of spreading the lines evenly across the clip.
"""

from __future__ import annotations

import re

from .contracts import Segment

WINDOW_SEC = 12.0        # a hook or on-screen line is spoken within this many seconds
NEAR_BUCKET_SEC = 45.0   # runs this close to `near` count as equally near; the earlier one then wins
LEAD_IN_SEC = 15.0       # an on-screen line said this shortly before the hook (the setup question) opens the clip
STOP = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "at", "for", "with", "is", "are", "was",
    "were", "be", "it", "its", "this", "that", "these", "those", "i", "you", "we", "they", "he", "she", "my",
    "your", "our", "not", "do", "does", "did", "will", "would", "can", "could", "just", "so", "if", "then",
    "than", "as", "from", "by", "about", "into", "have", "has", "had", "what", "which", "who", "how", "when",
    "where", "why", "there", "here", "all", "any", "some", "very", "really", "like", "um", "uh", "yeah",
}


def words(text: str) -> list[str]:
    """Content words, lowercased, light plural folding (seniors -> senior, words -> word)."""
    out = []
    for w in re.findall(r"[a-z0-9']+", text.lower()):
        w = re.sub(r"'s$", "", w.strip("'"))
        if len(w) < 3 or w in STOP:
            continue
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.append(w)
    return out


def locate(segs: list[Segment], text: str, *, lo: float = 0.0, hi: float = float("inf"),
           near: float | None = None, min_cover: float = 0.5) -> tuple[float, float] | None:
    """(start, end) of the shortest run of consecutive segments, starting inside [lo, hi), that
    contains at least `min_cover` of `text`'s content words. None if nowhere does. Among equally
    good runs, one far closer to `near` (the model's own guess, or the previous line) wins, so a
    phrase repeated in an intro teaser does not hijack the body; between runs at a similar
    distance the earlier one wins, so a hook that sums up a story opens at the story's start."""
    want = words(text)
    if not want:
        return None
    wanted = set(want)
    cands = [s for s in segs if lo <= s.start < hi]
    have = [set(words(s.text)) for s in cands]
    best: tuple[tuple[float, float], tuple[float, float]] | None = None
    for i, s in enumerate(cands):
        if not have[i] & wanted:
            continue  # a run starts on the first segment that says part of the text
        seen: set[str] = set()
        cover, end = 0.0, s.end
        for j in range(i, len(cands)):
            if cands[j].end - s.start > WINDOW_SEC:
                break
            seen |= have[j]
            c = sum(w in seen for w in want) / len(want)
            if c > cover:
                cover, end = c, cands[j].end
        if cover < min_cover:
            continue
        dist = abs(s.start - near) if near is not None else 0.0
        key = (cover, -(dist // NEAR_BUCKET_SEC), -s.start)
        if best is None or key > best[0]:
            best = (key, (s.start, end))
    return best[1] if best else None
