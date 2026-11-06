TODO (team C). Input vars: {{niche}}, {{playbook}}, {{topic_map}}, {{transcript}} ("[mm:ss] text" lines), {{top_n}}.
Scan the full transcript for moments that fit the playbook's hook_patterns, ideal_duration_s and pacing.
Must return JSON matching contracts.ClipSet:
clips[{start, end, score, title, hook_rewrite, on_screen_lines[], caption, matched_pattern, reason}].
Hook must be supported by what is actually said in that span.
