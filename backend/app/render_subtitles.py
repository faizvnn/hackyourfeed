"""Phrase captions and hook text, without an external subtitle dependency."""
from __future__ import annotations

import html
import math
import re
import textwrap
from typing import TYPE_CHECKING

from .contracts import CaptionStyle, Clip, Transcript

if TYPE_CHECKING:
    from .pipeline.s6_render_adaptive import RenderOptions


def _clean(text: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]*>", "", text)).split())


def _events(t: Transcript, clip: Clip) -> list[tuple[float, float, str]]:
    events = []
    for segment in sorted(t.segments, key=lambda s: s.start):
        if not math.isfinite(segment.start) or not math.isfinite(segment.end):
            continue
        a = max(segment.start, clip.start) - clip.start
        b = min(segment.end, clip.end) - clip.start
        text = _clean(segment.text)
        if b > a and text:
            if events and events[-1][1] > a:
                old_a, _, old_text = events.pop()
                if a > old_a:
                    events.append((old_a, a, old_text))
            events.append((a, b, text))
    return events


def _stamp(seconds: float, *, ass: bool = False) -> str:
    precision = 100 if ass else 1000
    ticks = max(0, round(seconds * precision))
    whole, fraction = divmod(ticks, precision)
    minutes, sec = divmod(whole, 60)
    hours, minute = divmod(minutes, 60)
    return (f"{hours}:{minute:02d}:{sec:02d}.{fraction:02d}" if ass
            else f"{hours:02d}:{minute:02d}:{sec:02d},{fraction:03d}")


def to_srt(t: Transcript, clip: Clip) -> str:
    return "\n\n".join(
        f"{i}\n{_stamp(a)} --> {_stamp(b)}\n{text}"
        for i, (a, b, text) in enumerate(_events(t, clip), 1)
    ) + "\n"


def _ass_text(text: str, *, width: int, max_lines: int | None = None) -> str:
    # Neutralize ASS override tags and escapes from upstream/LLM text.
    text = _clean(text).replace("\\", "＼").replace("{", "｛").replace("}", "｝")
    lines = textwrap.wrap(text, width=width, break_long_words=True, break_on_hyphens=False)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(" .") + "…"
    return r"\N".join(lines)


def _caption_groups(t: Transcript, clip: Clip) -> list[list[tuple[float, float, str]]]:
    """Use precise word times when supplied; otherwise estimate within phrase times.

    The estimate is only a display fallback, not word alignment or ASR output.
    No words are written back into the transcript when timings are estimated.
    """
    style = clip.render_style or CaptionStyle()
    tokens = []
    for segment in sorted(t.segments, key=lambda s: s.start):
        if segment.end <= clip.start or segment.start >= clip.end:
            continue
        if segment.words:
            source = [(w.start, w.end, _clean(w.text)) for w in segment.words]
        else:
            words = _clean(segment.text).split()
            total = sum(len(w) + 1 for w in words)
            duration = segment.end - segment.start
            source, cursor = [], segment.start
            for word in words:
                end = cursor + duration * (len(word) + 1) / total
                source.append((cursor, end, word))
                cursor = end
        for start, end, word in source:
            if not math.isfinite(start) or not math.isfinite(end) or not word:
                continue
            a, b = max(start, clip.start) - clip.start, min(end, clip.end) - clip.start
            if b > a:
                tokens.append((a, b, word.upper() if style.letter_case == "uppercase" else word))
    tokens.sort(key=lambda w: w[0])
    # Normalize overlapping caption windows without losing adjacent words.
    normalized = []
    for a, b, word in tokens:
        if normalized and a < normalized[-1][1]:
            old_a, _, old_word = normalized.pop()
            if a > old_a:
                normalized.append((old_a, a, old_word))
        normalized.append((a, b, word))
    groups, group = [], []
    for token in normalized:
        a, _, word = token
        length = sum(len(w[2]) + 1 for w in group) + len(word)
        if group and (len(group) >= style.words_per_group or length > style.max_chars_per_group
                      or a - group[-1][1] > 0.45):
            groups.append(group)
            group = []
        group.append(token)
    if group:
        groups.append(group)
    return groups


def _highlighted_text(group: list[tuple[float, float, str]], active: int,
                      style: CaptionStyle | None = None, keywords: list[str] | None = None) -> str:
    style = style or CaptionStyle()
    color = {"yellow": "&H0000E8FF&", "lime": "&H0050FFB5&",
             "cyan": "&H00FFE060&", "white": "&H00FFFFFF&"}[style.highlight_color]
    keywords = {k.casefold() for k in (keywords or [])}
    parts, line_length = [], 0
    for i, (_, _, word) in enumerate(group):
        escaped = _ass_text(word, width=max(18, len(word)))
        separator = " " if line_length else ""
        if line_length and line_length + len(word) + 1 > 18:
            separator, line_length = r"\N", 0
        keyword = re.sub(r"^\W+|\W+$", "", word).casefold() in keywords
        if ((style.emphasis == "active_word" and i == active)
                or (style.emphasis == "keywords" and keyword)):
            escaped = "{\\c" + color + "}" + escaped + r"{\c&H00FFFFFF&}"
        parts.append(separator + escaped)
        line_length += len(word) + 1
    return "".join(parts)


def make_ass(t: Transcript, clip: Clip, options: RenderOptions, *, framing_plan=None) -> str:
    style = clip.render_style or CaptionStyle(hook_seconds=options.hook_seconds)
    caption_margin = 285 if style.position == "lower" else 470
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 720
PlayResY: 1280
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Hook,{options.font},44,&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,4,1,8,60,60,120,1
Style: Caption,{options.font},{style.font_size},&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,5,2,2,65,65,{caption_margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    if clip.hook_rewrite.strip() and style.hook_seconds > 0:
        hook = _ass_text(clip.hook_rewrite, width=23, max_lines=3)
        end = _stamp(min(style.hook_seconds, clip.end - clip.start), ass=True)
        lines.append(f"Dialogue: 1,0:00:00.00,{end},Hook,,0,0,0,,{hook}\n")
    for group in _caption_groups(t, clip):
        for i, (a, b, _) in enumerate(group):
            # Keep a group visible across tiny word gaps. The next word switches emphasis.
            end = group[i + 1][0] if i + 1 < len(group) else b
            if round(a * 100) >= round(end * 100):
                continue
            body = _highlighted_text(group, i, style, clip.emphasis_keywords)
            if framing_plan is not None:
                y = round(framing_plan.caption_y(a)*1280)
                body = rf"{{\an2\pos(360,{y})}}" + body
            longest = max(len(w[2]) for w in group)
            if longest > 18:
                body = rf"{{\fs{max(18, int(style.font_size * 18 / longest))}}}" + body
            if i == 0 and style.animation == "pop":
                # A subtle 80ms pop, clipped to this event, with no additional video margins.
                pop = min(80, max(1, round((end - a) * 1000)))
                body = rf"{{\fscx94\fscy94\t(0,{pop},\fscx100\fscy100)}}" + body
            lines.append(f"Dialogue: 0,{_stamp(a, ass=True)},{_stamp(end, ass=True)},Caption,,0,0,0,,{body}\n")
    return "".join(lines)
