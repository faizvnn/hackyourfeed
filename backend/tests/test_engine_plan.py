import unittest

from app.config import engine_plan


class EnginePlanTests(unittest.TestCase):
    def test_single_engine_covers_every_clip(self):
        self.assertEqual(engine_plan(3, "classic"), ["classic"] * 3)
        self.assertEqual(engine_plan(3, "Adaptive"), ["adaptive"] * 3)

    def test_list_assigns_per_clip_and_repeats_the_last(self):
        self.assertEqual(engine_plan(3, "adaptive,adaptive,classic"), ["adaptive", "adaptive", "classic"])
        self.assertEqual(engine_plan(5, "adaptive, classic"), ["adaptive"] + ["classic"] * 4)
        self.assertEqual(engine_plan(1, "adaptive,adaptive,classic"), ["adaptive"])

    def test_blank_means_classic(self):
        self.assertEqual(engine_plan(2, ""), ["classic", "classic"])
        self.assertEqual(engine_plan(0, "adaptive"), [])


if __name__ == "__main__":
    unittest.main()
