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
                 size=(1920, 1080), body_margin=(130, 130)) -> int:
    """body_margin=(左, 右) は本文（箇条書き）の左右マージン。
    左右下に立ち絵が入るので、その幅に合わせて中央カラムに収める。
    箇条書きの下端 y を返す（字幕帯にかかっていないかの確認用）。"""
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
    return y - 32


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


# ---- 台本に定義した画像（図・スクショ）を出すスライド ----
#
# 台本のスライドに次のように書く（いずれも任意）:
#   "images": {"fig": {"src": "images/fig.png", "caption": "説明", "credit": "出典"}}
#   "image": "fig"                  ← スライド冒頭に出す画像（省略時は箇条書き）
#   dialogue[i].image: "fig" / null ← そのセリフから表示を切り替える（null で箇条書きへ戻る）
# 切り替えを書かないセリフは、直前の表示をそのまま引き継ぐ。

def line_visuals(slide: dict) -> List:
    """セリフごとに表示する画像キー（None = 箇条書き）を返す。"""
    images = slide.get("images") or {}
    cur = slide.get("image")
    if cur is not None and cur not in images:
        raise ValueError(f"スライド「{slide.get('heading', '')}」: 未定義の画像 {cur!r}")
    out = []
    for dl in slide.get("dialogue", []):
        if "image" in dl:
            cur = dl["image"]
            if cur is not None and cur not in images:
                raise ValueError(f"セリフ「{dl.get('text', '')}」: 未定義の画像 {cur!r}")
        out.append(cur)
    return out


def resolve_images(slide: dict, base_dir: str) -> dict:
    """images の src を台本ファイルのディレクトリ基準の絶対パスにする（存在確認つき）。"""
    out = {}
    for key, spec in (slide.get("images") or {}).items():
        src = spec["src"]
        path = src if os.path.isabs(src) else os.path.join(base_dir, src)
        if not os.path.isfile(path):
            raise FileNotFoundError(f"画像 {key!r} が見つからない: {path}")
        out[key] = dict(spec, src=path)
    return out


CAPTION_TEXT = (90, 98, 112)


def render_image_slide(heading: str, src: str, out_path: str, size=(1920, 1080),
                       caption: str = "", credit: str = "", crop=None,
                       side_margin: int = 400, bottom: int = 260) -> tuple:
    """ヘッダー帯＋キャプション＋画像（アスペクト比を保って中央に収める）の 1 枚を描く。

    キャプションはヘッダー直下に置く（下は字幕帯なので空けておく）。
    crop=(x0, y0, x1, y1) を渡すと元画像のその範囲だけを出す（表の一部を拡大したい時）。
    side_margin は左右の立ち絵ぶんの余白、bottom は字幕帯ぶんの下余白。
    描いた画像の矩形 (x0, y0, x1, y1) を返す。"""
    from PIL import Image, ImageDraw
    W, H = size
    img = Image.new("RGB", size, BG)
    d = ImageDraw.Draw(img)

    band_h = 170
    d.rectangle([0, 0, W, band_h], fill=HEADER)
    hf = _font(FONT_BOLD, 72)
    hlines = _wrap(d, heading, hf, W - 160)
    hy = (band_h - len(hlines) * 84) // 2
    for ln in hlines:
        d.text((80, hy), ln, font=hf, fill=HEADER_TEXT)
        hy += 84

    top = band_h + 24
    if caption:
        cf = _font(FONT_BOLD, 38)
        ln = _wrap(d, caption, cf, W - 240)[0]
        d.text(((W - d.textlength(ln, font=cf)) // 2, top), ln, font=cf, fill=BODY_TEXT)
        top += 66
    pad = 10
    credit_h = 30 if credit else 0
    max_w = W - 2 * side_margin
    max_h = H - bottom - credit_h - top - pad
    with Image.open(src) as im:
        pic = im.convert("RGBA")
    if crop:
        pic = pic.crop(tuple(crop))
    scale = min(max_w / pic.width, max_h / pic.height)
    w, h = max(1, round(pic.width * scale)), max(1, round(pic.height * scale))
    pic = pic.resize((w, h), Image.LANCZOS)
    x0, y0 = (W - w) // 2, top + pad + (max_h - h) // 2
    # 白いカードに薄い影をつけて載せる（暗いスクショも背景から浮かせる）
    d.rounded_rectangle([x0 - pad + 6, y0 - pad + 8, x0 + w + pad + 6, y0 + h + pad + 8],
                        radius=14, fill=(222, 226, 233))
    d.rounded_rectangle([x0 - pad, y0 - pad, x0 + w + pad, y0 + h + pad], radius=14,
                        fill=(255, 255, 255), outline=(210, 216, 225), width=2)
    img.paste(pic, (x0, y0), pic)
    if credit:
        sf = _font(FONT_REG, 24)
        d.text((x0 + w - d.textlength(credit, font=sf), y0 + h + pad + 4), credit,
               font=sf, fill=CAPTION_TEXT)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    img.save(out_path)
    return (x0, y0, x0 + w, y0 + h)
