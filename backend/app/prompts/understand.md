You are analyzing a podcast episode so we can find what is going viral on TikTok / Instagram Reels / YouTube Shorts in its niche. You are NOT picking clips. You only describe the episode and produce search terms.

Episode: {{title}}
Length: {{duration_min}} minutes

Transcript (each line starts with [seconds from start]):
{{transcript}}

Return ONE JSON object with exactly this shape:
{
  "niche": "short broad label, e.g. 'tech careers', 'startups', 'personal finance'",
  "summary": "2 sentences: who is talking and what the episode is about",
  "topics": ["5-8 specific topics discussed, in order"],
  "competitor_handles": ["0-4 TikTok/Instagram handles (no @) that post short clips in this niche. Only accounts you are sure exist. Empty list is fine."],
  "keyword_sets": {
    "niche":  ["5-8 broad terms, 1-2 words each, that thousands of short videos in this niche literally SAY out loud"],
    "topic":  ["5-8 phrases, 1-4 words, specific to THIS episode's main topics, still common enough that other creators say them"],
    "entity": ["0-6 proper names: guest, host, companies, products, tools mentioned"]
  },
  "topic_map": [
    {"start": 0, "end": 180, "topic": "short label of what is discussed in this stretch"}
  ]
}

Rules for keywords (these go into a KEYWORD search over spoken transcripts of short videos, not a semantic search):
- Use words people actually say on camera ("software engineer", "ai coding", "get a job"), not jargon only this guest uses.
- No invented phrases, product codenames, or terms that only appear in this episode. If a phrase would match fewer than ~50 videos on TikTok, drop it.
- Lowercase for niche and topic. No '#'. No duplicates across the three sets.

Rules for topic_map:
- Cover the whole episode from 0 to the end, in order, no gaps, no overlaps.
- 6-15 sections, each 1-6 minutes. Use the [seconds] timestamps from the transcript for start/end.
- Label each section with what is actually said there (e.g. "why juniors should learn fundamentals"), not a generic "discussion".

JSON only.
