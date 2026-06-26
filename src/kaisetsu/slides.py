"""スライド画像のレンダリング（PIL）。見出し＋箇条書きを 1 枚の PNG にする。"""

from __future__ import annotations

import os
from typing import List

# macOS 標準の日本語フォント
FONT_BOLD = "/System/Library/Fonts/ヒラギノ角ゴシック W7.ttc"
FONT_REG = "/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc"

BG = (250, 251, 253)
HEADER = (64, 132, 196)
HEADER_TEXT = (255, 255, 255)
BODY_TEXT = (40, 48, 60)
ACCENT = (64, 132, 196)


def _font(path: str, size: int):
    from PIL import ImageFont
    return ImageFont.truetype(path, size, index=0)


def _wrap(draw, text: str, font, max_width: int) -> List[str]:
    """日本語向けに文字単位で折り返す。"""
    lines, cur = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        trial = cur + ch
        if draw.textlength(trial, font=font) > max_width and cur:
            lines.append(cur)
            cur = ch
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def render_slide(heading: str, bullets: List[str], out_path: str,
                 size=(1920, 1080), body_margin=(130, 130)) -> None:
    """body_margin=(左, 右) は本文（箇条書き）の左右マージン。
    左右下に立ち絵が入るので、その幅に合わせて中央カラムに収める。"""
    from PIL import Image, ImageDraw
    W, H = size
    ml, mr = body_margin
    img = Image.new("RGB", size, BG)
    d = ImageDraw.Draw(img)

    # ヘッダー帯（上端・全幅。立ち絵は下なので干渉しない）
    band_h = 170
    d.rectangle([0, 0, W, band_h], fill=HEADER)
    hf = _font(FONT_BOLD, 72)
    hlines = _wrap(d, heading, hf, W - 160)
    hy = (band_h - len(hlines) * 84) // 2
    for ln in hlines:
        d.text((80, hy), ln, font=hf, fill=HEADER_TEXT)
        hy += 84

    # 箇条書き（キャラの間の中央カラム）
    bf = _font(FONT_REG, 58)
    x0, y = ml, band_h + 70
    text_w = W - ml - mr - 50
    for b in bullets:
        wrapped = _wrap(d, b, bf, text_w)
        d.ellipse([x0, y + 22, x0 + 22, y + 44], fill=ACCENT)
        ty = y
        for ln in wrapped:
            d.text((x0 + 46, ty), ln, font=bf, fill=BODY_TEXT)
            ty += 74
        y = ty + 32

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    img.save(out_path)


def render_title_card(heading: str, out_path: str, size=(1920, 1080),
                      index: int = 0, label: str = "") -> None:
    """段落切り替え用のタイトルカード。見出しを大きく中央に出す。"""
    from PIL import Image, ImageDraw
    W, H = size
    img = Image.new("RGB", size, HEADER)
    d = ImageDraw.Draw(img)

    # 章ラベル（例: 「1」）
    nf = _font(FONT_BOLD, 64)
    tag = label or (f"#{index}" if index else "")
    if tag:
        d.text((W // 2 - d.textlength(tag, font=nf) // 2, H // 2 - 200), tag,
               font=nf, fill=(210, 228, 245))

    # 見出し（中央・大きく・全幅近く）
    hf = _font(FONT_BOLD, 110)
    lines = _wrap(d, heading, hf, W - 240)
    total_h = len(lines) * 130
    ty = (H - total_h) // 2 - 20
    for ln in lines:
        w = d.textlength(ln, font=hf)
        d.text(((W - w) // 2, ty), ln, font=hf, fill=(255, 255, 255))
        ty += 130

    # 下線アクセント
    d.rectangle([W // 2 - 120, ty + 24, W // 2 + 120, ty + 34], fill=(255, 255, 255))

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    img.save(out_path)
