"""クリップ連結で音声と映像がずれないことのテスト（要 ffmpeg）。

各クリップは AAC の都合で音声が映像より少し長い。そのまま -c copy で連結すると
映像のタイムスタンプに隙間ができ、隙間を無視して再生する環境では後半ほど口パクと声がずれる。
"""

import os
import shutil
import subprocess
import tempfile
import unittest

from kaisetsu.compose import concat_clips


def _probe(path, stream, entry):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", stream, "-show_entries",
                          entry, "-of", "csv=p=0", path], capture_output=True, text=True).stdout
    return [float(x.rstrip(",")) for x in out.split() if x.rstrip(",")]


def _clip(path, seconds, audio_extra, freq):
    """映像 seconds 秒（30fps）＋ 映像より audio_extra 秒長い音声のクリップを作る。"""
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y",
         "-f", "lavfi", "-i", f"color=c=gray:s=64x36:r=30:d={seconds}",
         "-f", "lavfi", "-i", f"sine=frequency={freq}:sample_rate=24000:duration={seconds + audio_extra}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", path],
        check=True)


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg が必要")
class TestConcatSync(unittest.TestCase):
    def test_no_video_gaps_and_audio_matches_video(self):
        with tempfile.TemporaryDirectory() as d:
            clips = []
            for i, sec in enumerate([1.0, 2.0, 1.5, 1.0, 2.5]):
                p = os.path.join(d, f"clip_{i}.mp4")
                _clip(p, sec, audio_extra=0.03, freq=300 + 100 * i)
                clips.append(p)
            out = os.path.join(d, "video.mp4")
            concat_clips(clips, out)

            pts = sorted(_probe(out, "v:0", "packet=pts_time"))
            gaps = [b - a for a, b in zip(pts, pts[1:]) if b - a > 1.5 / 30]
            self.assertEqual(gaps, [], "映像のタイムスタンプに隙間がある")
            self.assertEqual(len(pts), 30 * 8)  # 映像は全フレームそのまま

            v = _probe(out, "v:0", "stream=duration")[0]
            a = _probe(out, "a:0", "stream=duration")[0]
            self.assertAlmostEqual(v, 8.0, delta=1 / 30)
            self.assertAlmostEqual(a, v, delta=0.05)  # 音声も映像の尺に揃う（累積でずれない）


if __name__ == "__main__":
    unittest.main()
