"""align.locate and the stage-5 realignment it drives. No ffmpeg or API credentials."""
from __future__ import annotations

import unittest

from app.align import locate, words
from app.contracts import Segment
from app.pipeline.s5_direct import _align

SEGS = [
    Segment(start=0, end=2, text="the profession will collapse if we stop hiring juniors"),   # intro teaser
    Segment(start=2, end=4, text="welcome to the show"),
    Segment(start=60, end=62, text="today is a release day"),
    Segment(start=62, end=64, text="I think the software engineering profession"),
    Segment(start=64, end=66, text="will collapse if we don't keep hiring"),
    Segment(start=66, end=68, text="early in career developers"),
    Segment(start=68, end=70, text="where are the seniors going to come from"),
    Segment(start=70, end=72, text="nurses have a preceptor model"),
    Segment(start=100, end=102, text="something else entirely"),
    Segment(start=110, end=112, text="the software engineering profession will collapse if we don't keep hiring early in career developers"),
]


class LocateTests(unittest.TestCase):
    def test_words_drop_stopwords_and_fold_plurals(self):
        self.assertEqual(words("Where are the seniors coming from?"), ["senior", "coming"])
        self.assertEqual(words("This guy's class"), ["guy", "class"])

    def test_finds_the_run_closest_to_near(self):
        hook = "The software engineering profession will collapse if we don't keep hiring early in career developers."
        self.assertEqual(locate(SEGS, hook, near=55), (62.0, 68.0))
        self.assertEqual(locate(SEGS, hook, near=100), (62.0, 68.0))   # similar distance: earlier run wins
        self.assertEqual(locate(SEGS, hook, near=200), (110.0, 112.0))  # far closer run wins
        self.assertEqual(locate(SEGS, "profession will collapse hiring juniors", near=0), (0.0, 2.0))

    def test_bounds_and_misses(self):
        self.assertEqual(locate(SEGS, "nurse preceptor model", lo=62), (70.0, 72.0))
        self.assertIsNone(locate(SEGS, "nurse preceptor model", hi=60))
        self.assertIsNone(locate(SEGS, "completely unrelated words here"))
        self.assertIsNone(locate(SEGS, "the and of"))


class RealignTests(unittest.TestCase):
    def test_clip_opens_on_hook_and_covers_lines(self):
        hook = "The software engineering profession will collapse if we don't keep hiring early in career developers."
        start, end = _align(SEGS, 0.0, 70.0, hook, ["WHERE ARE SENIORS COMING FROM?", "NURSE PRECEPTOR MODEL"], 200.0)
        self.assertEqual(start, 62.0)
        self.assertGreaterEqual(end, 72.0)

    def test_setup_line_just_before_hook_opens_clip(self):
        start, _ = _align(SEGS, 0.0, 70.0, "will collapse if we don't keep hiring early in career developers",
                          ["TODAY IS A RELEASE DAY"], 200.0)
        self.assertEqual(start, 60.0)

    def test_unlocatable_hook_keeps_model_span(self):
        self.assertEqual(_align(SEGS, 60.0, 72.0, "nothing like this is said", [], 200.0), (60.0, 72.0))


if __name__ == "__main__":
    unittest.main()
