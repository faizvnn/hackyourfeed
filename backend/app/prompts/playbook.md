You are reverse-engineering what is going viral right now in one short-form niche so a podcast editor can copy the format.

Below are {{count}} short-form videos (Instagram Reels / TikTok) from the last 30 days, sorted by `views`. Most come from the podcast and clip accounts that dominate this niche (`granularity` niche = pulled from those accounts, entity = a named guest, topic = a spoken phrase). `views` is the ranking signal; `vrpf` (views as % of the account's followers) is a secondary hint that a clip travelled beyond its own audience.

Each record: hook (first spoken line), on_screen (text detected on screen, OCR, may be noisy), caption, hashtags, duration (s), wps (spoken words per second), views, vrpf, platform, handle, granularity.

Some videos may also come with an `edit_specs` entry: a frame-by-frame breakdown of how the video was edited (captions style, cuts, zooms, on-screen text timing). When present, use it to describe editing concretely.

Ignore videos that are obviously off-topic for the niche (ads, GoFundMe pleas, unrelated vlogs that merely say the keyword) when inferring patterns, but still consider their hooks if the hook technique itself is transferable.

Your job: find the 4–6 hook patterns that recur across the most-viewed videos, and the shared format rules.

Return ONLY a JSON object matching this schema exactly:

{
  "hook_patterns": [
    {
      "name": "short memorable label, 2-4 words",
      "description": "one or two sentences: the technique, what the first line does and what the second line does",
      "examples": ["verbatim hooks from the records that use it, 1-3"],
      "avg_views": 0
    }
  ],
  "on_screen_text_style": "how the top videos use on-screen text: length, timing, case, position, relation to the spoken hook",
  "ideal_duration_s": 0,
  "pacing_wps": 0,
  "caption_formula": "a template for the post caption: tone, length, emoji or not, how many hashtags, which kinds",
  "takeaways": ["3-5 one-line rules an editor should follow for this niche"]
}

Rules:
- 4 to 6 hook_patterns, ordered by how strongly they correlate with high views.
- examples must be copied verbatim from the `hook` fields, never invented.
- avg_views is the integer mean of `views` for the example videos.
- ideal_duration_s and pacing_wps are numbers derived from the top third of videos by views (median is fine).
- Be specific to these records. "Use a strong hook" is not a pattern; "Negate a common belief in the first 3 words" is.
- No prose outside the JSON. No code fences.

videos:
{{videos}}

edit_specs:
{{edit_specs}}
