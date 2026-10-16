"""体の動き（呼吸＋感情ごとのモーション）のテスト。"""

import math
import unittest

from vvlipsync.motion import (
    MOTION_BY_EMOTION,
    Transform,
    affine_coeffs,
    fit_headroom,
    motion_at,
)


def _sample(emotion, dur=2.0, fps=60, t_global0=0.0, kind=None):
    n = int(dur * fps)
    return [motion_at(emotion, i / fps, t_global0 + i / fps, kind=kind) for i in range(n)]


class TestBreathing(unittest.TestCase):
    def test_idle_is_gentle_vertical_breathing(self):
        tfs = _sample("通常", dur=4.0)
        sys_ = [tf.sy for tf in tfs]
        # 縦に伸び縮みする（ふわふわ呼吸）が、振幅は控えめ
        self.assertGreater(max(sys_) - min(sys_), 0.005)
        self.assertLess(max(abs(s - 1.0) for s in sys_), 0.02)
        # 足元は動かない（平行移動・回転なし）
        for tf in tfs:
            self.assertEqual(tf.dx, 0.0)
            self.assertEqual(tf.dy, 0.0)
            self.assertEqual(tf.rot, 0.0)

    def test_breathing_follows_global_clock(self):
        # 行が切り替わっても呼吸の位相は通し時刻で決まる（クリップ境界で跳ねない）
        a = motion_at("通常", t_line=0.0, t_global=5.3)
        b = motion_at("通常", t_line=2.1, t_global=5.3)
        self.assertAlmostEqual(a.sy, b.sy)

    def test_every_emotion_breathes(self):
        for emo in MOTION_BY_EMOTION:
            sys_ = [tf.sy for tf in _sample(emo, dur=5.0)]
            self.assertGreater(max(sys_) - min(sys_), 0.003, emo)

    def test_unknown_emotion_falls_back_to_idle(self):
        self.assertEqual(motion_at("謎", 0.7, 3.2), motion_at("通常", 0.7, 3.2))
        self.assertEqual(motion_at(None, 0.7, 3.2), motion_at("通常", 0.7, 3.2))


class TestEmotionMotions(unittest.TestCase):
    def test_joy_hops(self):
        dys = [tf.dy for tf in _sample("喜び", dur=2.0)]
        self.assertTrue(all(dy <= 1e-9 for dy in dys))  # 上にしか跳ねない（地面より下に沈まない）
        self.assertLess(min(dys), -0.01)  # 身長の 1% 以上は跳ねる
        # 何度も跳ねる（着地 = ほぼ 0 に戻る瞬間が複数ある）
        landings = sum(1 for a, b in zip(dys, dys[1:]) if a < -0.002 <= b)
        self.assertGreaterEqual(landings, 2)

    def test_surprise_jumps_at_line_start_then_settles(self):
        peak = min(motion_at("驚き", t / 100, t / 100).dy for t in range(0, 50))
        self.assertLess(peak, -0.02)
        late = motion_at("驚き", 1.5, 1.5)
        self.assertAlmostEqual(late.dy, 0.0, places=3)

    def test_anger_shakes_then_calms(self):
        early = max(abs(motion_at("怒り", t / 200, t / 200).dx) for t in range(0, 40))
        late = max(abs(motion_at("怒り", 2 + t / 200, 2 + t / 200).dx) for t in range(0, 40))
        self.assertGreater(early, 0.003)
        self.assertLess(late, early / 2)

    def test_sadness_slumps(self):
        tfs = _sample("悲しみ", dur=4.0)
        self.assertTrue(all(tf.sy < 1.0 for tf in tfs))  # しょんぼり縮む
        self.assertTrue(all(tf.dy >= 0.0 for tf in tfs))  # 跳ねない

    def test_shy_sways(self):
        rots = [tf.rot for tf in _sample("照れ", dur=3.0)]
        self.assertGreater(max(rots), 0.5)
        self.assertLess(min(rots), -0.5)
        self.assertLess(max(abs(r) for r in rots), 3.0)

    def test_kind_overrides_emotion_mapping(self):
        # プリセットの "motion" で動きの種類を差し替えられる
        self.assertEqual(motion_at("通常", 0.3, 0.3, kind="bounce"),
                         motion_at("喜び", 0.3, 0.3))


class TestAffine(unittest.TestCase):
    def _forward(self, coeffs, x, y):
        a, b, c, d, e, f = coeffs
        return a * x + b * y + c, d * x + e * y + f

    def test_identity(self):
        co = affine_coeffs(Transform(), (100, 200), (50, 200))
        for got, want in zip(co, (1, 0, 0, 0, 1, 0)):
            self.assertAlmostEqual(got, want)

    def test_anchor_stays_put_under_scale_and_rotation(self):
        # PIL の AFFINE は「出力座標 → 入力座標」の写像。足元(anchor)は動かない
        anchor = (50.0, 180.0)
        co = affine_coeffs(Transform(sx=0.98, sy=1.02, rot=2.0), (100, 200), anchor)
        x, y = self._forward(co, *anchor)
        self.assertAlmostEqual(x, anchor[0])
        self.assertAlmostEqual(y, anchor[1])

    def test_translation_in_height_units(self):
        # dy は身長(キャンバス高さ)比。-0.1 → 20px 上に描かれる＝出力(50,80)は入力(50,100)
        co = affine_coeffs(Transform(dy=-0.1), (100, 200), (50, 200))
        x, y = self._forward(co, 50, 80)
        self.assertAlmostEqual(x, 50)
        self.assertAlmostEqual(y, 100)

    def test_positive_rotation_tilts_head_right(self):
        # rot>0 は頭が画面右へ傾く。頭頂の出力位置を入力に戻すと左にある
        anchor = (50.0, 200.0)
        tf = Transform(rot=5.0)
        co = affine_coeffs(tf, (100, 200), anchor)
        hx = 50 + 100 * math.sin(math.radians(5.0))  # 回転後の頭頂 x
        hy = 200 - 100 * math.cos(math.radians(5.0))
        x, y = self._forward(co, hx, hy)
        self.assertAlmostEqual(x, 50, places=4)
        self.assertAlmostEqual(y, 100, places=4)


class TestFitHeadroom(unittest.TestCase):
    # キャンバス高さ 1000、頭頂 y=20（余白 20px）、足元 y=980
    SIZE = (500, 1000)
    TOP = 20
    ANCHOR = (250.0, 980.0)

    def _top_after(self, tf):
        return self.ANCHOR[1] - (self.ANCHOR[1] - self.TOP) * tf.sy + tf.dy * self.SIZE[1]

    def test_scales_down_jumps_to_stay_inside_canvas(self):
        tfs = [Transform(dy=-0.05), Transform(dy=-0.02, sy=1.01), Transform(dy=0.01)]
        got = fit_headroom(tfs, self.TOP, self.ANCHOR, self.SIZE)
        for tf in got:
            self.assertGreaterEqual(self._top_after(tf), 0.0)
        # 一様に縮めるので、跳ねの大小関係は保たれる（頭打ちで平らにならない）
        self.assertLess(got[0].dy, got[1].dy)
        self.assertLess(got[0].dy, 0)
        # 下向き・伸び縮みには手を付けない
        self.assertEqual(got[2], tfs[2])
        self.assertEqual(got[1].sy, 1.01)

    def test_untouched_when_there_is_room(self):
        tfs = [Transform(dy=-0.01), Transform(sy=1.005)]
        self.assertEqual(fit_headroom(tfs, 200, self.ANCHOR, self.SIZE), tfs)


if __name__ == "__main__":
    unittest.main()
