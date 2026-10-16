"""句読点でのポーズ切り替えと、ポーズ別 base 画像の解決のテスト。"""

import os
import tempfile
import unittest

from vvlipsync.cli import _build_base_paths
from vvlipsync.timeline import pause_starts, pose_intervals


def _mora(v, vl=0.1, c=None):
    m = {"vowel": v, "vowel_length": vl}
    if c:
        m["consonant_length"] = c
    return m


QUERY = {
    "prePhonemeLength": 0.1,
    "postPhonemeLength": 0.1,
    "accent_phrases": [
        {"moras": [_mora("a"), _mora("i")], "pause_mora": {"vowel": "pau", "vowel_length": 0.3}},
        {"moras": [_mora("u", c=0.05)], "pause_mora": {"vowel": "pau", "vowel_length": 0.2}},
        {"moras": [_mora("e")], "pause_mora": None},
    ],
}


class TestPauseStarts(unittest.TestCase):
    def test_returns_pause_start_times_relative_to_line(self):
        got = pause_starts(QUERY)
        # 0.1(pre) + 0.2 → 1つ目の pause 開始 0.3、その後 0.3 進んで 0.6 + 0.15 = 0.75
        self.assertEqual(len(got), 2)
        self.assertAlmostEqual(got[0], 0.3)
        self.assertAlmostEqual(got[1], 0.75)

    def test_speed_scales_times(self):
        got = pause_starts(QUERY, speed=2.0)
        self.assertAlmostEqual(got[0], 0.15)
        self.assertAlmostEqual(got[1], 0.375)

    def test_no_pause(self):
        q = {"accent_phrases": [{"moras": [_mora("a")]}]}
        self.assertEqual(pause_starts(q), [])


class TestPoseIntervals(unittest.TestCase):
    def test_single_pose_covers_whole_line(self):
        self.assertEqual(pose_intervals(1.0, 3.0, [1.5, 2.0], 1), [(1.0, 3.0, 0)])

    def test_switches_pose_at_each_pause_and_cycles(self):
        got = pose_intervals(1.0, 3.0, [1.5, 2.0, 2.5], 2)
        self.assertEqual(got, [(1.0, 1.5, 0), (1.5, 2.0, 1), (2.0, 2.5, 0), (2.5, 3.0, 1)])

    def test_ignores_pause_outside_line(self):
        got = pose_intervals(1.0, 3.0, [0.5, 3.0, 3.5], 3)
        self.assertEqual(got, [(1.0, 3.0, 0)])


class TestBuildBasePaths(unittest.TestCase):
    def test_pose_variants_are_keyed_by_emotion_and_index(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ("base.png", "base_喜び.png", "base_喜び_p1.png", "base_喜び_p2.png",
                         "base_通常.png"):
                open(os.path.join(d, name), "wb").close()
            paths = _build_base_paths(d, {"喜び", "通常", "怒り"})
            self.assertEqual(paths[("喜び", 0)], os.path.join(d, "base_喜び.png"))
            self.assertEqual(paths[("喜び", 1)], os.path.join(d, "base_喜び_p1.png"))
            self.assertEqual(paths[("喜び", 2)], os.path.join(d, "base_喜び_p2.png"))
            self.assertEqual(paths[("通常", 0)], os.path.join(d, "base_通常.png"))
            self.assertNotIn(("通常", 1), paths)
            self.assertIsNone(paths[("怒り", 0)])  # 無い感情は base.png にフォールバックさせる
            self.assertEqual(paths[None], os.path.join(d, "base.png"))


if __name__ == "__main__":
    unittest.main()
