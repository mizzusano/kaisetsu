"""字幕（表記）と読み上げ（読み）の書き分けのテスト。"""

import tempfile
import unittest
from unittest import mock

from kaisetsu import build
from kaisetsu.reading import apply_readings, line_reading


class TestReadings(unittest.TestCase):
    R = {"LLM": "エルエルエム", "Palantir": "パランティア", "GPT-6 Luna": "ジーピーティーシックスルナ",
         "GPT": "ジーピーティー"}

    def test_replaces_words(self):
        self.assertEqual(apply_readings("Palantir の LLM", self.R), "パランティア の エルエルエム")

    def test_longest_match_first(self):
        self.assertEqual(apply_readings("親を GPT-6 Luna へ。GPT も", self.R),
                         "親を ジーピーティーシックスルナ へ。ジーピーティー も")

    def test_no_readings_keeps_text(self):
        self.assertEqual(apply_readings("36.8億トークン", {}), "36.8億トークン")

    def test_line_yomi_overrides_dictionary(self):
        self.assertEqual(line_reading({"text": "Palantir", "yomi": "パランティアさん"}, self.R),
                         "パランティアさん")
        self.assertEqual(line_reading({"text": "Palantir"}, self.R), "パランティア")


class _Stop(Exception):
    pass


class TestSegmentUsesReadingForVoiceOnly(unittest.TestCase):
    def test_vvlipsync_gets_reading_and_subtitle_keeps_text(self):
        with tempfile.TemporaryDirectory() as d:
            com = dict(out_dir=d, assets_root="assets", fps=30.0, size=(1920, 1080),
                       char_by_name={c["name"]: c for c in build.CHARACTERS}, clock=[0.0])
            with mock.patch.object(build, "vvmain", side_effect=_Stop) as vv:
                with self.assertRaises(_Stop):
                    build._render_segment(0, "bg.png", "metan", "通常", "Palantir の話",
                                          yomi="パランティアの話", head=0.2, tail=0.3, **com)
            argv = vv.call_args[0][0]
            self.assertEqual(argv[argv.index("-t") + 1], "パランティアの話")


if __name__ == "__main__":
    unittest.main()
