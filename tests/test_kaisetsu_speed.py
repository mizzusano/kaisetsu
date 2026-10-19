"""kaisetsu の話速（VOICEVOX speedScale）のテスト。"""

import tempfile
import unittest
from unittest import mock

from kaisetsu import build


class _Stop(Exception):
    pass


class TestSpeed(unittest.TestCase):
    def _argv(self, **kw):
        with tempfile.TemporaryDirectory() as d:
            com = dict(out_dir=d, assets_root="assets", fps=30.0, size=(1920, 1080),
                       char_by_name={c["name"]: c for c in build.CHARACTERS}, clock=[0.0])
            com.update(kw)
            with mock.patch.object(build, "vvmain", side_effect=_Stop) as vv:
                with self.assertRaises(_Stop):
                    build._render_segment(0, "bg.png", "metan", "通常", "やあ",
                                          head=0.2, tail=0.3, **com)
            return vv.call_args[0][0]

    def test_default_is_a_little_faster_than_voicevox_default(self):
        self.assertGreater(build.DEFAULT_SPEED, 1.0)
        self.assertLessEqual(build.DEFAULT_SPEED, 1.3)
        argv = self._argv()
        self.assertEqual(argv[argv.index("--speed") + 1], str(build.DEFAULT_SPEED))

    def test_speed_is_passed_to_vvlipsync(self):
        argv = self._argv(speed=1.3)
        self.assertEqual(argv[argv.index("--speed") + 1], "1.3")


if __name__ == "__main__":
    unittest.main()
