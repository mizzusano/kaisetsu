"""台本に定義した画像をスライドに出すためのテスト。"""

import os
import tempfile
import unittest

from kaisetsu.slides import line_visuals, render_image_slide, resolve_images


def _slide(**kw):
    base = dict(heading="見出し", bullets=["a"], dialogue=[
        {"speaker": "metan", "emotion": "通常", "text": "1"},
        {"speaker": "zundamon", "emotion": "通常", "text": "2"},
        {"speaker": "metan", "emotion": "通常", "text": "3"},
    ])
    base.update(kw)
    return base


class TestLineVisuals(unittest.TestCase):
    def test_no_images_means_bullets_everywhere(self):
        self.assertEqual(line_visuals(_slide()), [None, None, None])

    def test_slide_default_image(self):
        s = _slide(images={"fig": {"src": "a.png"}}, image="fig")
        self.assertEqual(line_visuals(s), ["fig", "fig", "fig"])

    def test_line_switch_is_sticky_and_null_returns_to_bullets(self):
        s = _slide(images={"a": {"src": "a.png"}, "b": {"src": "b.png"}})
        s["dialogue"][1]["image"] = "a"
        self.assertEqual(line_visuals(s), [None, "a", "a"])
        s["dialogue"][2]["image"] = None
        self.assertEqual(line_visuals(s), [None, "a", None])
        s["dialogue"][2]["image"] = "b"
        self.assertEqual(line_visuals(s), [None, "a", "b"])

    def test_unknown_key_is_an_error(self):
        s = _slide(images={"a": {"src": "a.png"}}, image="zzz")
        with self.assertRaises(ValueError):
            line_visuals(s)
        s = _slide()
        s["dialogue"][0]["image"] = "a"
        with self.assertRaises(ValueError):
            line_visuals(s)


class TestResolveImages(unittest.TestCase):
    def test_src_is_relative_to_script_dir(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "images"))
            open(os.path.join(d, "images", "x.png"), "wb").close()
            got = resolve_images(_slide(images={"x": {"src": "images/x.png", "caption": "図"}}), d)
            self.assertEqual(got["x"]["src"], os.path.join(d, "images", "x.png"))
            self.assertEqual(got["x"]["caption"], "図")

    def test_missing_file_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):
                resolve_images(_slide(images={"x": {"src": "nope.png"}}), d)


class TestRenderImageSlide(unittest.TestCase):
    def test_fits_image_inside_center_area_keeping_aspect(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "wide.png")
            Image.new("RGB", (2000, 500), (255, 0, 0)).save(src)
            out = os.path.join(d, "slide.png")
            box = render_image_slide("見出し", src, out, size=(1920, 1080),
                                     caption="キャプション", credit="出典: どこか")
            with Image.open(out) as im:
                self.assertEqual(im.size, (1920, 1080))
                x0, y0, x1, y1 = box
                # アスペクト比を保つ（4:1）
                self.assertAlmostEqual((x1 - x0) / (y1 - y0), 4.0, delta=0.05)
                # ヘッダー帯の下、字幕帯の上に収まり、左右中央
                self.assertGreaterEqual(y0, 170)
                self.assertLessEqual(y1, 1080 - 200)
                self.assertAlmostEqual((x0 + x1) / 2, 960, delta=2)
                # 実際に画像が描かれている
                self.assertEqual(im.getpixel(((x0 + x1) // 2, (y0 + y1) // 2))[:3], (255, 0, 0))

    def test_image_stays_above_subtitle_band(self):
        # 2 行の字幕帯（上端 y=852）に画像・出典がかからない
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "sq.png")
            Image.new("RGB", (1000, 1000), (0, 255, 0)).save(src)
            x0, y0, x1, y1 = render_image_slide("見出し", src, os.path.join(d, "s.png"),
                                                caption="キャプション", credit="出典")
            self.assertLessEqual(y1, 852 - 30)

    def test_crop_shows_only_the_region(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "two.png")
            im = Image.new("RGB", (1000, 1000), (255, 0, 0))
            im.paste((0, 0, 255), (0, 500, 1000, 1000))  # 下半分は青
            im.save(src)
            out = os.path.join(d, "s.png")
            x0, y0, x1, y1 = render_image_slide("見出し", src, out, crop=(0, 500, 1000, 1000))
            self.assertAlmostEqual((x1 - x0) / (y1 - y0), 2.0, delta=0.05)
            with Image.open(out) as got:
                self.assertEqual(got.getpixel(((x0 + x1) // 2, y0 + 5))[:3], (0, 0, 255))

    def test_tall_image_is_limited_by_height(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "tall.png")
            Image.new("RGB", (500, 2000), (0, 0, 255)).save(src)
            box = render_image_slide("見出し", src, os.path.join(d, "s.png"), size=(1920, 1080))
            x0, y0, x1, y1 = box
            self.assertAlmostEqual((y1 - y0) / (x1 - x0), 4.0, delta=0.05)
            self.assertLessEqual(y1, 1080 - 200)



class TestBulletOverflow(unittest.TestCase):
    def test_render_slide_reports_text_bottom(self):
        from kaisetsu.slides import render_slide
        with tempfile.TemporaryDirectory() as d:
            short = render_slide("見出し", ["短い", "短い"], os.path.join(d, "a.png"),
                                 body_margin=(506, 506))
            long = render_slide("見出し", ["とても長い箇条書きの文がここに入って何行にも折り返される"] * 6,
                                os.path.join(d, "b.png"), body_margin=(506, 506))
            self.assertLess(short, 852)   # 字幕帯より上で収まる
            self.assertGreater(long, 852)  # はみ出しを検出できる


if __name__ == "__main__":
    unittest.main()
