You are filtering short-form videos that a keyword search pulled for a podcast editor working in the niche "{{niche}}". They want to study how viral interview clips are made, so they can cut their own episode the same way.

The episode they are cutting: {{summary}}

Two separate judgments per record:

1. keep or drop, decided by FORMAT ONLY, not by topic:
   KEEP = a clip of an interview, podcast, panel or talking-head conversation: one or two people talking to camera or to each other, on any subject. The poster does not matter (the show's own account, a fan page, a clip aggregator or a news account all count).
   DROP = everything else: news or product-launch explainers, ads and sponsored posts, vlogs, skits and comedy bits, TV-show scenes, movie or speech quote montages, science demos, tutorials and screen recordings, reaction or commentary videos ABOUT a person rather than with them.

2. on_niche: true only when the clip's subject matter belongs to "{{niche}}" (or the episode above) itself; false for everything else, including adjacent lanes. Never let this affect keep/drop.

Each record: id, handle, bio (poster's profile bio), caption, hook (first spoken line), transcript (start), duration (s), views.

Return ONLY a JSON object, no prose, no code fences:
{"keep": [{"id": "<id>", "format": "interview | talking_head | panel", "on_niche": false, "why": "<= 8 words"}]}

records:
{{records}}
