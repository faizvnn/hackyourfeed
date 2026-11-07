"""Adaptive render (s6_render_adaptive): real FFmpeg checks plus subtitle regression tests. No API credentials."""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.contracts import CaptionStyle, Clip, ClipSet, Segment, Transcript, WordTiming
from app.pipeline import s6_render_adaptive as renderer
from app.render_subtitles import _ass_text, _caption_groups, _stamp, make_ass, to_srt


def clip(**changes) -> Clip:
    data = dict(start=1, end=2.5, score=90, title="Test", hook_rewrite="¿Qué cambia? It's 50%: fácil",
                on_screen_lines=[], caption="Publication caption", matched_pattern="test", reason="test")
    return Clip(**(data | changes))


class SubtitleTests(unittest.TestCase):
    def test_intersection_rebase_and_overlap(self):
        t = Transcript(source_url="test", segments=[
            Segment(start=0, end=1.5, text="<i>Antes &amp; ahora</i>"),
            Segment(start=1.4, end=3, text="Después"),
            Segment(start=3, end=4, text="Outside"),
        ])
        srt = to_srt(t, clip())
        self.assertIn("00:00:00,000 --> 00:00:00,400", srt)
        self.assertIn("00:00:00,400 --> 00:00:01,500", srt)
        self.assertIn("Antes & ahora", srt)
        self.assertNotIn("Outside", srt)

    def test_rounding_carries_into_next_minute(self):
        self.assertEqual(_stamp(59.9999), "00:01:00,000")
        self.assertEqual(_stamp(59.9999, ass=True), "0:01:00.00")

    def test_ass_text_cannot_inject_styles(self):
        text = _ass_text(r"{\pos(0,0)} don't: 50%", width=80)
        self.assertNotIn("{", text)
        self.assertNotIn(r"\pos", text)
        self.assertIn("don't: 50%", text)

    def test_hook_has_two_second_limit(self):
        t = Transcript(source_url="test", segments=[])
        ass = make_ass(t, clip(start=0, end=3), renderer.RenderOptions())
        self.assertIn("0:00:00.00,0:00:02.00,Hook", ass)

    def test_invalid_options(self):
        for settings in [renderer.RenderOptions(layout="invalid"), renderer.RenderOptions(width=719),
                         renderer.RenderOptions(crop_center_x=1.1),
                         renderer.RenderOptions(timeout=float("nan")), renderer.RenderOptions(font="x\nStyle: x")]:
            with self.assertRaises(ValueError):
                settings.validate()

    def test_real_word_times_drive_highlighting(self):
        t = Transcript(source_url="test", segments=[Segment(start=0, end=4, text="This is precise",
            words=[WordTiming(start=0.5, end=0.8, text="This"),
                   WordTiming(start=1.2, end=1.5, text="is"),
                   WordTiming(start=1.5, end=2, text="precise")])])
        c = clip(start=0, end=4)
        words = [w for group in _caption_groups(t, c) for w in group]
        self.assertEqual(words[0], (0.5, 0.8, "THIS"))
        ass = make_ass(t, c, renderer.RenderOptions())
        self.assertIn("0:00:00.50,0:00:01.20,Caption", ass)
        self.assertIn(r"{\c&H0000E8FF&}THIS", ass)

    def test_short_caption_groups_preserve_words_and_clip_bounds(self):
        t = Transcript(source_url="test", segments=[Segment(start=0, end=6,
            text="one two three four five six seven eight nine ten")])
        groups = _caption_groups(t, clip(start=0, end=6))
        self.assertTrue(all(1 <= len(g) <= 3 for g in groups))
        self.assertEqual(" ".join(w[2] for g in groups for w in g), t.segments[0].text.upper())
        self.assertTrue(all(0 <= a < b <= 6.001 for g in groups for a, b, _ in g))


@unittest.skipUnless(shutil.which(renderer.RenderOptions().ffmpeg) and shutil.which(renderer.RenderOptions().ffprobe)
                     and renderer.has_libass(renderer.RenderOptions().ffmpeg),
                     "FFmpeg with libass required (set FFMPEG_BIN/FFPROBE_BIN)")
class RenderIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="clip render's ")
        cls.root = Path(cls.temp.name)
        cls.source = cls.root / "source video's.mp4"
        renderer._execute([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
            "testsrc2=size=640x360:rate=30", "-f", "lavfi", "-i", "sine=frequency=440",
            "-t", "4", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(cls.source),
        ], timeout=30)
        cls.silent = cls.root / "silent-portrait.mp4"
        renderer._execute([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
            "testsrc2=size=180x320:rate=30", "-t", "3", "-c:v", "libx264", str(cls.silent),
        ], timeout=30)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.patches = [patch.object(renderer, "RENDER_DIR", self.root / "renders"),
                        patch.object(renderer, "PUBLIC_BASE_URL", "https://example.test/"),
                        patch.object(renderer, "use_fixture", return_value=False)]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        self.t = Transcript(source_url="test", video_path=str(self.source), duration=999,
                            segments=[Segment(start=0.5, end=3, text="Generación automática: acentos y símbolos.")])

    def test_blur_with_audio_and_public_result(self):
        c = renderer.run("audio", self.t, ClipSet(clips=[clip()]),
                         options=renderer.RenderOptions(layout="blur")).clips[0]
        media = renderer.probe(Path(c.render_path), renderer.RenderOptions())
        self.assertEqual((media["video"]["width"], media["video"]["height"]), (720, 1280))
        self.assertEqual(media["video"]["codec_name"], "h264")
        self.assertEqual(media["video"]["pix_fmt"], "yuv420p")
        self.assertTrue(media["audio"])
        self.assertAlmostEqual(media["duration"], 1.5, delta=0.1)
        self.assertEqual(c.render_url, "https://example.test/renders/audio/clip0.mp4")
        self.assertIsNone(c.render_error)

    def test_crop_silent_portrait_source(self):
        self.t.video_path = str(self.silent)
        c = renderer.run("silent", self.t, ClipSet(clips=[clip()]),
                         options=renderer.RenderOptions(layout="crop")).clips[0]
        self.assertFalse(renderer.probe(Path(c.render_path), renderer.RenderOptions())["audio"])

    def test_custom_clip_caption_plan_renders(self):
        style = CaptionStyle(words_per_group=2, letter_case="original", font_size=46,
                             position="middle", highlight_color="cyan", emphasis="keywords",
                             animation="none", hook_seconds=0)
        c = renderer.run("planned", self.t, ClipSet(clips=[clip(render_style=style,
                             emphasis_keywords=["automática"])] )).clips[0]
        self.assertTrue(Path(c.render_path).is_file())
        ass = (Path(c.render_path).parent / "clip0.ass").read_text(encoding="utf-8")
        self.assertIn(",46,", ass)
        self.assertNotIn(",Hook,,", ass)
        self.assertNotIn(r"\fscx94", ass)

    def test_partial_failure_preserves_success(self):
        result = renderer.run("partial", self.t, ClipSet(clips=[clip(start=-1), clip()]))
        self.assertIsNotNone(result.clips[0].render_error)
        self.assertIsNone(result.clips[0].render_url)
        self.assertTrue(Path(result.clips[1].render_path).is_file())

    def test_invalid_duration_uses_media_not_transcript(self):
        c = clip(start=3, end=5)
        with self.assertRaisesRegex(RuntimeError, "No clips rendered"):
            renderer.run("invalid", self.t, ClipSet(clips=[c]))
        self.assertIsNotNone(c.render_error)

    def test_job_id_cannot_escape_render_directory(self):
        with self.assertRaisesRegex(ValueError, "job_id"):
            renderer.run("../escape", self.t, ClipSet(clips=[clip()]))


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which(renderer.RenderOptions().ffprobe)
                     and renderer.has_libass(renderer.RenderOptions().ffmpeg),
                     "ffmpeg on PATH plus a libass build (FFMPEG_BIN) required")
class MixedEngineTests(RenderIntegrationTests):
    """RENDER_ENGINE=adaptive,classic: both engines write clip_<n>.mp4 into one job folder."""

    def setUp(self):
        super().setUp()
        from app.pipeline import s6_render as classic
        self.classic = classic
        for p in [patch.object(classic, "RENDER_DIR", self.root / "renders"),
                  patch.object(classic, "PUBLIC_BASE_URL", "https://example.test/"),
                  patch.object(classic, "use_fixture", return_value=False),
                  patch.object(classic, "engine_plan", lambda n: ["adaptive", "classic"][:n])]:
            p.start()
            self.addCleanup(p.stop)

    def test_run_dispatches_per_clip(self):
        clips = ClipSet(clips=[clip(), clip(start=0.2, end=2.2, on_screen_lines=["ACENTOS"])])
        out = self.classic.run("mixed", self.t, clips).clips
        self.assertEqual([c.render_url for c in out],
                         ["https://example.test/renders/mixed/clip_1.mp4",
                          "https://example.test/renders/mixed/clip_2.mp4"])
        self.assertEqual([c.render_error for c in out], [None, None])
        sizes = [renderer.probe(Path(c.render_path), renderer.RenderOptions())["video"] for c in out]
        self.assertEqual((sizes[0]["width"], sizes[0]["height"]), (720, 1280))   # adaptive preset
        self.assertEqual((sizes[1]["width"], sizes[1]["height"]), (1080, 1920))  # classic canvas
        self.assertTrue((self.root / "renders/mixed/clip_1.ass").exists())
        self.assertFalse((self.root / "renders/mixed/clip_2_overlays").exists())
        self.assertTrue((self.root / "renders/mixed/clips_rendered.json").exists())

    def test_failed_clip_keeps_the_rest(self):
        clips = ClipSet(clips=[clip(start=3, end=9), clip()])
        out = self.classic.run("mixed-partial", self.t, clips).clips
        self.assertIn("adaptive: Invalid clip range", out[0].render_error)
        self.assertIsNone(out[0].render_path)
        self.assertIsNone(out[1].render_error)
        self.assertTrue(Path(out[1].render_path).exists())

    def test_rejects_unknown_engine(self):
        with patch.object(self.classic, "engine_plan", lambda n: ["classic", "compound"]):
            with self.assertRaises(ValueError):
                self.classic.run("bad", self.t, ClipSet(clips=[clip(), clip()]))

    # the inherited adaptive-only tests already ran in RenderIntegrationTests
    for _name in ("test_blur_with_audio_and_public_result", "test_crop_silent_portrait_source",
                  "test_custom_clip_caption_plan_renders", "test_partial_failure_preserves_success",
                  "test_invalid_duration_uses_media_not_transcript", "test_job_id_cannot_escape_render_directory"):
        locals()[_name] = None
    del _name
