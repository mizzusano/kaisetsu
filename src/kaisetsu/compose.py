"""ffmpeg による動画合成。

1 セリフ = 1 クリップ:  スライド背景 ＋ 話者(口パク連番) ＋ 聞き手(静止) ＋ 字幕 ＋ 音声
全クリップを連結して最終 mp4 にする。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import List

# 立ち絵の元キャンバス比（psd_extract 出力）。高さ基準でスケールする。
CHAR_NATIVE = (1082, 1650)


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        sys.exit("ffmpeg が無い。`brew install ffmpeg`。")
    return exe


def render_subtitle(text: str, out_path: str, size=(1920, 1080)) -> None:
    """字幕を全画面サイズの透過 PNG として描く（下部に半透明帯＋白文字）。"""
    from PIL import Image, ImageDraw
    from .slides import FONT_BOLD, _font, _wrap

    W, H = size
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    font = _font(FONT_BOLD, 52)
    lines = _wrap(d, text, font, W - 360)
    line_h = 66
    box_h = line_h * len(lines) + 48
    box_top = H - box_h - 48
    d.rounded_rectangle([180, box_top, W - 180, box_top + box_h], radius=24,
                        fill=(0, 0, 0, 175))
    y = box_top + 24
    for ln in lines:
        w = d.textlength(ln, font=font)
        d.text(((W - w) // 2, y), ln, font=font, fill=(255, 255, 255, 255))
        y += line_h
    img.save(out_path)


def _char_size(height: int):
    w = round(CHAR_NATIVE[0] * height / CHAR_NATIVE[1])
    return w, height


def compose_line(slide_png: str, slots: List[dict], subtitle_png: str,
                 audio_path: str, out_path: str, fps: float,
                 size=(1920, 1080), char_height: int = 780,
                 head: float = 0.0, tail: float = 0.0) -> None:
    """slots: 左→右の順。各 slot = {kind:'seq'|'img', path, flip:bool}。
    kind='seq' は口パク連番（%05d.png のあるディレクトリ）、'img' は静止立ち絵。
    subtitle_png='' なら字幕を重ねない。head/tail はセリフ前後の「間」(秒)。
    その間は最初/最後のフレームを保持し、無音にする（テンポ調整・話者は口を閉じたまま）。"""
    ffmpeg = _ffmpeg()
    W, H = size
    cw, ch = _char_size(char_height)
    y = H - ch
    xs = [60, W - cw - 60]  # 左・右

    args = [ffmpeg, "-y", "-loop", "1", "-i", slide_png]  # input 0: スライド
    for slot in slots:
        if slot["kind"] == "seq":
            args += ["-framerate", str(fps), "-start_number", "0",
                     "-i", os.path.join(slot["path"], "%05d.png")]
        else:
            args += ["-loop", "1", "-i", slot["path"]]
    use_sub = bool(subtitle_png)
    if use_sub:
        args += ["-loop", "1", "-i", subtitle_png]
    args += ["-i", audio_path]

    sub_idx = 1 + len(slots) if use_sub else None
    audio_idx = (sub_idx + 1) if use_sub else (1 + len(slots))

    fc = []
    for i, slot in enumerate(slots):
        chain = f"[{i + 1}:v]scale=-1:{ch}"
        if slot["kind"] == "img" and slot.get("flip"):
            chain += ",hflip"
        chain += f"[s{i}]"
        fc.append(chain)

    prev = "[0:v]"
    for i in range(len(slots)):
        out = f"[b{i}]"
        fc.append(f"{prev}[s{i}]overlay=x={xs[i]}:y={y}:shortest=0{out}")
        prev = out
    if use_sub:
        fc.append(f"{prev}[{sub_idx}:v]overlay=0:0[vov]")
    else:
        fc.append(f"{prev}null[vov]")

    # テンポ: 前後にフレーム保持の「間」を足す
    vtail = "[vov]"
    if head or tail:
        vtail = (f"[vov]tpad=start_duration={head}:stop_duration={tail}"
                 f":start_mode=clone:stop_mode=clone[vp];[vp]")
    fc.append(f"{vtail}format=yuv420p[v]")

    amap = f"{audio_idx}:a"
    if head or tail:
        fc.append(f"[{audio_idx}:a]adelay={int(head * 1000)}:all=1,"
                  f"apad=pad_dur={tail}[a]")
        amap = "[a]"

    args += [
        "-filter_complex", ";".join(fc),
        "-map", "[v]", "-map", amap,
        "-c:v", "libx264", "-c:a", "aac", "-r", str(fps), "-shortest", out_path,
    ]
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def add_bgm(video_in: str, bgm_path: str, out_path: str, volume: float = 0.18) -> None:
    """動画に BGM（mp3/mp4）を小音量でミックスする。
    BGM はループ（短い場合）、動画の音声尺で打ち切り。セリフ音量はそのまま保つ。"""
    ffmpeg = _ffmpeg()
    fc = (f"[1:a]volume={volume}[bg];"
          f"[0:a][bg]amix=inputs=2:duration=first:normalize=0[a]")
    args = [
        ffmpeg, "-y", "-i", video_in,
        "-stream_loop", "-1", "-i", bgm_path,  # BGM を無限ループ入力
        "-filter_complex", fc,
        "-map", "0:v", "-map", "[a]",
        "-c:v", "copy", "-c:a", "aac", "-shortest", out_path,
    ]
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def concat_clips(clips: List[str], out_path: str) -> None:
    """同一エンコード設定のクリップを連結する。"""
    ffmpeg = _ffmpeg()
    listfile = out_path + ".concat.txt"
    with open(listfile, "w", encoding="utf-8") as f:
        for c in clips:
            f.write(f"file '{os.path.abspath(c)}'\n")
    subprocess.run(
        [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", listfile,
         "-c", "copy", out_path],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    os.remove(listfile)
