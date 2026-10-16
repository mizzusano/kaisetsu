"""kaisetsu の中間 PNG の後始末と、途中からの再開のテスト。"""

import os
import tempfile
import unittest
import wave
from unittest import mock

from kaisetsu import build


def _wav(path, seconds=0.5, rate=24000):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\0\0" * int(seconds * rate))


def _common(out_dir, render_clip=True, keep_frames=False):
    return dict(out_dir=out_dir, assets_root="assets", fps=30.0, size=(1920, 1080),
                char_by_name={c["name"]: c for c in build.CHARACTERS}, clock=[0.0],
                render_clip=render_clip, keep_frames=keep_frames)


class TestDropFrames(unittest.TestCase):
    def test_removes_png_dirs_but_keeps_audio(self):
        with tempfile.TemporaryDirectory() as d:
            for sub in ("frames", "listener_metan", "listener_zundamon"):
                os.makedirs(os.path.join(d, sub))
                open(os.path.join(d, sub, "00000.png"), "wb").close()
            _wav(os.path.join(d, "audio.wav"))
            build._drop_frames(d)
            self.assertEqual(sorted(os.listdir(d)), ["audio.wav"])


class TestDoneMarker(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(build._load_done(d))
            build._mark_done(d, n_frames=42)
            self.assertEqual(build._load_done(d), {"n_frames": 42})


class TestResume(unittest.TestCase):
    def _done_segment(self, out_dir, idx=0):
        seg = os.path.join(out_dir, f"seg_{idx:03d}")
        os.makedirs(seg)
        _wav(os.path.join(seg, "audio.wav"), seconds=0.5)
        build._mark_done(seg, n_frames=15)
        open(os.path.join(out_dir, f"clip_{idx:03d}.mp4"), "wb").close()
        return seg

    def test_finished_segment_is_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            self._done_segment(d)
            com = _common(d)
            with mock.patch.object(build, "vvmain") as vv, \
                    mock.patch.object(build, "compose_line") as cl:
                clip, info = build._render_segment(0, "bg.png", "metan", "通常", "やあ",
                                                   head=0.2, tail=0.3, **com)
            vv.assert_not_called()
            cl.assert_not_called()
            self.assertEqual(clip, os.path.join(d, "clip_000.mp4"))
            self.assertEqual(info.n_frames, 15)
            # 通し時刻は再開時も同じだけ進む（呼吸の位相がずれない）
            self.assertAlmostEqual(com["clock"][0], 0.2 + 0.5 + 0.3)

    def test_not_skipped_when_frames_are_needed_but_gone(self):
        # タイムライン書き出し（keep_frames）には PNG が要るので、消えていたら作り直す
        with tempfile.TemporaryDirectory() as d:
            self._done_segment(d)
            with mock.patch.object(build, "vvmain", side_effect=RuntimeError("rendered")):
                with self.assertRaises(RuntimeError):
                    build._render_segment(0, "bg.png", "metan", "通常", "やあ", head=0.2,
                                          tail=0.3, **_common(d, keep_frames=True))

    def test_clip_without_marker_is_rebuilt(self):
        # 書きかけで止まったクリップ（印が無い）は信用しない
        with tempfile.TemporaryDirectory() as d:
            seg = self._done_segment(d)
            os.remove(os.path.join(seg, build.DONE_MARKER))
            with mock.patch.object(build, "vvmain", side_effect=RuntimeError("rendered")):
                with self.assertRaises(RuntimeError):
                    build._render_segment(0, "bg.png", "metan", "通常", "やあ", head=0.2,
                                          tail=0.3, **_common(d))


if __name__ == "__main__":
    unittest.main()
