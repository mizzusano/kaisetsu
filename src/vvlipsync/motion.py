"""立ち絵の体の動き（ふわふわ呼吸＋感情ごとのモーション）。

各フレームの変形を Transform（平行移動・拡縮・回転）として求め、足元を支点に
立ち絵全体へアフィン変換をかける。移動量は身長（キャンバス高さ）比なので、
立ち絵の解像度によらず同じ見え方になる。

- 呼吸は通し時刻 t_global で決める（行・クリップが切り替わっても位相が跳ねない）
- 感情モーションは行頭からの時刻 t_line で決める（驚きのジャンプなどを行頭に合わせる）
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Optional, Tuple

BREATH_PERIOD = 3.2  # 秒
BREATH_AMP = 0.008  # 縦の伸び縮み（身長比）

# 感情名 → モーションの種類。emotions.json のプリセットに "motion" を書けば差し替えられる。
MOTION_BY_EMOTION = {
    "通常": "idle",
    "喜び": "bounce",
    "怒り": "shake",
    "悲しみ": "droop",
    "驚き": "jump",
    "照れ": "sway",
}


@dataclass(frozen=True)
class Transform:
    dx: float = 0.0  # 身長比。+ で右
    dy: float = 0.0  # 身長比。+ で下
    sx: float = 1.0
    sy: float = 1.0
    rot: float = 0.0  # 度。+ で頭が画面右へ傾く


def _breath(t_global: float, period: float = BREATH_PERIOD, amp: float = BREATH_AMP) -> float:
    return amp * math.sin(2 * math.pi * t_global / period)


def _squash(sy_delta: float) -> Tuple[float, float]:
    # 縦に伸びたら少し細く（体積を保つ感じ）
    return 1.0 - 0.4 * sy_delta, 1.0 + sy_delta


def motion_at(emotion: Optional[str], t_line: float, t_global: float,
              kind: Optional[str] = None) -> Transform:
    kind = kind or MOTION_BY_EMOTION.get(emotion or "", "idle")

    if kind == "bounce":
        # ぴょんぴょん: |sin| で地面から跳ねる。着地の瞬間に少し潰れる
        hop = abs(math.sin(math.pi * t_line / 0.42))
        sx, sy = _squash(_breath(t_global) + 0.012 * (hop - 0.5))
        return Transform(dy=-0.018 * hop, sx=sx, sy=sy)

    if kind == "jump":
        # 行頭で 1 回跳び上がり、着地の潰れを減衰振動で戻す
        T = 0.35
        if t_line < T:
            x = t_line / T
            dy = -0.035 * 4 * x * (1 - x)
            squash = 0.0
        else:
            dy = 0.0
            u = t_line - T
            squash = -0.02 * math.exp(-u / 0.12) * math.cos(2 * math.pi * u / 0.3)
        sx, sy = _squash(_breath(t_global) + squash)
        return Transform(dy=dy, sx=sx, sy=sy)

    if kind == "shake":
        # 行頭でぷるぷる震えて、その後は小さく小刻みに
        burst = 0.007 * math.exp(-t_line / 0.35) * math.sin(2 * math.pi * 14 * t_line)
        tremble = 0.0012 * math.sin(2 * math.pi * 9 * t_line)
        sx, sy = _squash(_breath(t_global))
        return Transform(dx=burst + tremble, sx=sx, sy=sy)

    if kind == "droop":
        # しょんぼり: 少し縮んで、ゆっくり深いため息の呼吸
        b = _breath(t_global, period=4.6, amp=0.006)
        sx, sy = _squash(b - 0.012)
        rot = 0.4 * math.sin(2 * math.pi * t_global / 6.0)
        return Transform(dy=0.003 + 0.002 * math.sin(2 * math.pi * t_global / 4.6) ** 2,
                         sx=sx, sy=sy, rot=rot)

    if kind == "sway":
        # もじもじ: 足元を支点に左右にくねくね
        rot = 1.3 * math.sin(2 * math.pi * t_line / 1.6)
        sx, sy = _squash(_breath(t_global))
        return Transform(sx=sx, sy=sy, rot=rot)

    sx, sy = _squash(_breath(t_global))
    return Transform(sx=sx, sy=sy)


def affine_coeffs(tf: Transform, size: Tuple[int, int],
                  anchor: Tuple[float, float]) -> Tuple[float, ...]:
    """PIL の Image.transform(AFFINE) に渡す係数（出力座標 → 入力座標の逆写像）を返す。

    順方向は  p' = anchor + d + R(rot) · S(sx, sy) · (p - anchor)。"""
    H = size[1]
    ax, ay = anchor
    dx, dy = tf.dx * H, tf.dy * H
    th = math.radians(tf.rot)
    c, s = math.cos(th), math.sin(th)
    # 逆: p = anchor + S^-1 · R(-rot) · (p' - anchor - d)
    a, b = c / tf.sx, s / tf.sx
    d, e = -s / tf.sy, c / tf.sy
    ox, oy = ax + dx, ay + dy
    return (a, b, ax - a * ox - b * oy,
            d, e, ay - d * ox - e * oy)


def is_identity(tf: Transform) -> bool:
    return tf == Transform()


def apply_transform(img, tf: Transform, anchor: Tuple[float, float]):
    """立ち絵(RGBA)に Transform をかける。キャンバスサイズは保つ。"""
    if is_identity(tf):
        return img
    from PIL import Image
    return img.transform(img.size, Image.AFFINE, affine_coeffs(tf, img.size, anchor),
                         resample=Image.BICUBIC)


def feet_anchor(img) -> Tuple[float, float]:
    """足元（不透明部分の下端中央）を返す。体の動きの支点にする。"""
    bbox = img.getchannel("A").getbbox()
    if not bbox:
        return img.size[0] / 2, img.size[1]
    return (bbox[0] + bbox[2]) / 2, bbox[3]


def fit_headroom(transforms, top: float, anchor: Tuple[float, float],
                 size: Tuple[int, int], margin: float = 2.0):
    """頭上の余白（top = 不透明部分の上端 y）を超えて跳ねないよう、上向きの移動だけを一様に縮める。

    頭打ちで平らにせず全フレーム同じ比率で縮めるので、跳ねの形は保たれる。"""
    H = size[1]
    height = anchor[1] - top
    room = top - margin
    k = 1.0
    for tf in transforms:
        if tf.dy >= 0:
            continue
        rise = -tf.dy * H
        allowed = room - height * (tf.sy - 1.0)  # 伸びの分を差し引いた残り
        if rise > allowed:
            k = min(k, max(0.0, allowed) / rise)
    if k >= 1.0:
        return list(transforms)
    return [replace(tf, dy=tf.dy * k) if tf.dy < 0 else tf for tf in transforms]
