"""透過動画（アルファ付き mov / webm）の ffmpeg 引数のテスト。"""

import unittest

from vvlipsync.preview import alpha_video_args


def _after(args, flag):
    return args[args.index(flag) + 1]


class TestAlphaVideoArgs(unittest.TestCase):
    def test_mov_is_prores_4444_with_alpha(self):
        args = alpha_video_args("ffmpeg", "out/frames", "out/audio.wav", "out/character.mov", 30.0)
        self.assertEqual(_after(args, "-c:v"), "prores_ks")
        self.assertEqual(_after(args, "-profile:v"), "4444")
        self.assertEqual(_after(args, "-pix_fmt"), "yuva444p10le")
        self.assertEqual(_after(args, "-c:a"), "pcm_s16le")  # DaVinci で扱いやすい非圧縮音声
        self.assertEqual(args[-1], "out/character.mov")

    def test_webm_is_vp9_with_alpha(self):
        args = alpha_video_args("ffmpeg", "out/frames", "out/audio.wav", "out/character.webm", 30.0)
        self.assertEqual(_after(args, "-c:v"), "libvpx-vp9")
        self.assertEqual(_after(args, "-pix_fmt"), "yuva420p")
        self.assertEqual(_after(args, "-c:a"), "libopus")
        self.assertEqual(args[-1], "out/character.webm")

    def test_reads_png_sequence_and_audio(self):
        args = alpha_video_args("ffmpeg", "out/frames", "out/audio.wav", "out/character.mov", 24.0)
        inputs = [args[i + 1] for i, a in enumerate(args) if a == "-i"]
        self.assertEqual(inputs, ["out/frames/%05d.png", "out/audio.wav"])
        self.assertEqual(_after(args, "-framerate"), "24.0")
        self.assertIn("-shortest", args)

    def test_unknown_extension_is_rejected(self):
        with self.assertRaises(ValueError):
            alpha_video_args("ffmpeg", "f", "a.wav", "out/character.mp4", 30.0)


if __name__ == "__main__":
    unittest.main()
