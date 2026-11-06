"""Caption planning handoff: Oriane -> playbook -> clip -> actual ASS output."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from app.contracts import CaptionStyle, ClipSet, Playbook, Segment, Transcript, Understanding, ViralSet
from app.pipeline import s3_oriane, s4_playbook, s5_direct, s6_render
from app.render_subtitles import _caption_groups, make_ass
from app.llm import load_prompt


def viral():
    return s3_oriane.to_viral({
        "id": "real-reference", "platform": "youtube", "profileHandle": "creator",
        "viewsCount": 200000, "viewsRatePerFollowers": 900,
        "publishedAt": "2026-11-06T10:00:00Z", "media": [{
            "duration": 30, "transcript": "Google research changes how we build AI",
            "onScreenText": ["Google research"], "frames": [{
                "timestampSeconds": 1.5, "onScreenTextRegions": [{
                    "text": "Google research", "polygon": [
                        {"x": 0.2, "y": 0.65}, {"x": 0.8, "y": 0.65},
                        {"x": 0.8, "y": 0.75}, {"x": 0.2, "y": 0.75},
                    ]}]}]}]}, "topic")


def playbook_data(style=None):
    return dict(hook_patterns=[], on_screen_text_style="Short original-case OCR text",
                ideal_duration_s=30, pacing_wps=2, caption_formula="Describe the actual claim",
                caption_style=style)


def directed_clip():
    return dict(start=0, end=3, score=80, title="Research", hook_rewrite="Research at Google",
                on_screen_lines=[], caption="Accurate publication caption", matched_pattern="standalone",
                reason="Source-grounded test", render_style={"emphasis": "keywords"},
                emphasis_keywords=["Google", "INVENTED"])


class CaptionPipelineTests(unittest.TestCase):
    def test_ocr_geometry_and_provenance_reach_renderer(self):
        v = viral()
        self.assertAlmostEqual(v.text_observations[0].center_y, .7)
        planned = CaptionStyle(words_per_group=2, letter_case="original", font_size=46,
            highlight_color="cyan", animation="none", evidence_video_ids=[v.id, "invented"],
            rationale="Short OCR labels suggest compact groups; cyan is a readability choice.")
        with patch.object(s4_playbook, "use_fixture", return_value=False), patch.object(
            s4_playbook, "complete_json", return_value=playbook_data(planned.model_dump())) as llm:
            pb = s4_playbook.run(ViralSet(videos=[v]))
        self.assertEqual(llm.call_count, 1)
        self.assertEqual(llm.call_args.kwargs["videos"][0]["id"], v.id)
        self.assertIn("text_observations", llm.call_args.kwargs["videos"][0])
        self.assertEqual(pb.caption_style.evidence_video_ids, [v.id])
        self.assertEqual(pb.caption_style.evidence_basis, "ocr_samples")
        t = Transcript(source_url="test", segments=[Segment(start=0, end=3, text="Google research changes AI")])
        u = Understanding(niche="AI", summary="AI research", topics=["AI"],
                          keyword_sets={}, candidate_moments=[])
        with patch.object(s5_direct, "use_fixture", return_value=False), patch.object(
            s5_direct, "complete_json", return_value={"clips": [directed_clip()]}) as direct:
            c = s5_direct.run(t, u, pb).clips[0]
        self.assertEqual(direct.call_count, 1)
        self.assertEqual(c.render_style.words_per_group, 2)
        self.assertEqual(c.emphasis_keywords, ["Google"])
        self.assertEqual(c.render_style.evidence_video_ids, [v.id])
        groups = _caption_groups(t, c)
        self.assertTrue(all(len(g) <= 2 for g in groups))
        self.assertEqual(groups[0][0][2], "Google")
        ass = make_ass(t, c, s6_render.RenderOptions())
        self.assertIn(f"Style: Caption,{s6_render.RenderOptions().font},46,", ass)
        self.assertIn(r"{\c&H00FFE060&}Google", ass)
        self.assertNotIn(r"\fscx94", ass)

    def test_unverifiable_or_invalid_style_falls_back(self):
        for raw in [{"evidence_video_ids": ["invented"], "font_size": 46},
                    {"evidence_video_ids": ["real-reference"], "font_size": 5000}]:
            with patch.object(s4_playbook, "use_fixture", return_value=False), patch.object(
                s4_playbook, "complete_json", return_value=playbook_data(raw)):
                pb = s4_playbook.run(ViralSet(videos=[viral()]))
            self.assertEqual(pb.caption_style.evidence_basis, "fallback")
            self.assertEqual(pb.caption_style.font_size, 58)

    def test_empty_reference_set_needs_no_llm(self):
        with patch.object(s4_playbook, "use_fixture", return_value=False), patch.object(
            s4_playbook, "complete_json") as llm:
            pb = s4_playbook.run(ViralSet(videos=[]))
        llm.assert_not_called()
        self.assertEqual(pb.caption_style.evidence_basis, "fallback")

    def test_legacy_inputs_and_complete_prompts(self):
        pb = Playbook.model_validate(playbook_data())
        self.assertIsNone(pb.caption_style)
        for name in ["understand", "playbook", "direct"]:
            self.assertIn("JSON", load_prompt(name))


if __name__ == "__main__":
    unittest.main()
