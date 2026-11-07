You are directing short-form clips for a podcast episode in the "{{niche}}" niche. You have the full timed transcript and a playbook that describes exactly which hooks, lengths and pacing are going viral in this niche right now.

Episode: {{title}}
Summary: {{summary}}

Playbook (what is working right now):
{{playbook}}

Topic map (where each subject is discussed, seconds):
{{topic_map}}

Transcript, one line per few seconds, prefixed with its start time as [mm:ss]:
{{transcript}}

Your job: pick the {{top_n}} best self-contained moments to cut into vertical clips, ranked best first.

A good moment:
- starts on a line that can open the clip cold (a claim, a question, a contrarian take, a story beat), not mid-sentence or mid-answer
- ends on a complete thought, a punchline or a payoff
- is {{min_len}} to {{max_len}} seconds long, ideally close to {{ideal_len}} seconds
- fits one of the playbook's hook_patterns, with the first spoken line (or a light rewrite of it) delivering that hook
- stands alone without the rest of the episode

Return ONLY a JSON object matching this schema exactly:

{
  "clips": [
    {
      "start": 0.0,
      "end": 0.0,
      "score": 0,
      "title": "3-6 word working title",
      "hook_rewrite": "the opening line, as it would appear as the first on-screen text / spoken hook; it must be supported by what is actually said in the span",
      "on_screen_lines": ["2-4 short on-screen text lines that punctuate the clip, in order, in the playbook's on_screen_text_style"],
      "caption": "post caption following the playbook's caption_formula, hashtags included",
      "matched_pattern": "the name of the playbook hook_pattern this uses, copied verbatim",
      "reason": "one sentence: why this moment, citing the pattern and what in the span makes it work"
    }
  ]
}

Rules:
- start and end are seconds, taken from the [mm:ss] timestamps (mm:ss -> seconds). Snap start to the timestamp of the line that opens the clip, and end to the timestamp of the line after the clip's last words.
- Clips must not overlap each other. Prefer moments from different topics.
- score is 0-100: how likely this clip is to perform given the playbook. Rank by it.
- hook_rewrite may tighten the wording but must not invent claims that are not in the span.
- No prose outside the JSON. No code fences.
