"""字幕（横いっぱいの半透明帯＋話者色の縁取り）と立ち絵の配置のテスト。"""

import os
import tempfile
import unittest

from kaisetsu import build
from kaisetsu.compose import (SPEAKER_COLORS, SUBTITLE_BAND_H, _char_size, render_subtitle,
                              slot_positions, wrap_subtitle)

SIZE = (1920, 1080)


class TestWrapSubtitle(unittest.TestCase):
    def test_no_line_starts_with_punctuation(self):
        text = "下にデータやロジックがあって、その上に意思決定が乗っているのだ。" * 2
        for width in range(900, 1700, 37):
            lines = wrap_subtitle(text, width)
            self.assertEqual("".join(lines), text)
            for ln in lines[1:]:
                self.assertNotIn(ln[0], "、。！？」』）…ー", (width, lines))

    def test_short_text_is_one_line(self):
        self.assertEqual(wrap_subtitle("やったーなのだ！", 1680), ["やったーなのだ！"])


class TestRenderSubtitle(unittest.TestCase):
    def _render(self, text="九月の実績よ。", color=SPEAKER_COLORS["metan"]):
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "sub.png")
            render_subtitle(text, out, SIZE, color=color)
            with Image.open(out) as im:
                return im.convert("RGBA").copy()

    def test_band_spans_full_width_and_is_translucent(self):
        im = self._render()
        W, H = SIZE
        top = H - SUBTITLE_BAND_H
        for x in (2, W // 2, W - 3):
            a = im.getpixel((x, top + 5))[3]
            self.assertGreater(a, 0, x)     # 帯がある
            self.assertLess(a, 200, x)      # 透けている
        self.assertEqual(im.getpixel((W // 2, top - 5))[3], 0)  # 帯の上は透明

    def test_outline_uses_speaker_color(self):
        for name, color in SPEAKER_COLORS.items():
            im = self._render(color=color)
            band = im.crop((0, SIZE[1] - SUBTITLE_BAND_H, SIZE[0], SIZE[1]))
            near = sum(1 for p in band.getdata()
                       if p[3] == 255 and all(abs(p[i] - color[i]) < 12 for i in range(3)))
            self.assertGreater(near, 500, name)


class TestCharacterLayout(unittest.TestCase):
    def test_characters_hug_the_edges_and_feet_are_off_screen(self):
        W, H = SIZE
        cw, ch = _char_size(build.CHAR_HEIGHT)
        (lx, ly), (rx, ry) = slot_positions(SIZE, build.CHAR_HEIGHT)
        self.assertLessEqual(lx, 0)             # 左は画面端からはみ出すくらいに寄せる
        self.assertGreaterEqual(rx + cw, W)     # 右も同様
        self.assertGreater(ly + ch, H + 0.1 * ch)  # 下 1 割以上が画面外（靴を描かない）
        self.assertEqual(ly, ry)
        self.assertGreater(build.CHAR_HEIGHT, 780)  # 以前より大きく見せる

    def test_bullets_must_stay_above_the_band(self):
        self.assertEqual(build.SUBTITLE_TOP, SIZE[1] - SUBTITLE_BAND_H)



class TestTimelineMovOverflow(unittest.TestCase):
    def test_character_sticking_out_of_canvas_is_cropped(self):
        import shutil
        import subprocess
        if not shutil.which("ffmpeg"):
            self.skipTest("ffmpeg が必要")
        from PIL import Image
        from kaisetsu.timeline import write_character_mov
        with tempfile.TemporaryDirectory() as d:
            frames = []
            for i in range(3):
                p = os.path.join(d, f"f{i}.png")
                Image.new("RGBA", (40, 60), (255, 0, 0, 255)).save(p)
                frames.append(p)
            out = os.path.join(d, "c.mov")
            # 左に 10px、下に 30px はみ出す配置
            write_character_mov(frames, out, 30.0, (100, 80), char_height=60, x=-10, y=50)
            wh = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                 "-show_entries", "stream=width,height", "-of", "csv=p=0", out],
                                capture_output=True, text=True).stdout.strip()
            self.assertEqual(wh, "100,80")


if __name__ == "__main__":
    unittest.main()
