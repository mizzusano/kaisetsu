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


# 字幕: 横いっぱいの半透明の帯に、太字の白文字＋話者色の縁取り（話者名・「」は出さない）
SUBTITLE_BAND_H = 200
SUBTITLE_FONT_SIZE = 62
SUBTITLE_SIDE = 120  # 字幕文字の左右の余白
SPEAKER_COLORS = {"zundamon": (46, 125, 50), "metan": (194, 54, 132)}
_NO_LINE_START = "、。，．！？」』）】…ー"


def wrap_subtitle(text: str, max_width: int, font=None) -> List[str]:
    """字幕を折り返す。句読点などが行頭に来ないよう前の行へ寄せる（行頭禁則）。"""
    from PIL import Image, ImageDraw
    from .slides import FONT_BOLD, _font, _wrap

    font = font or _font(FONT_BOLD, SUBTITLE_FONT_SIZE)
    lines = _wrap(ImageDraw.Draw(Image.new("RGB", (8, 8))), text, font, max_width)
    for i in range(1, len(lines)):
        while lines[i] and lines[i][0] in _NO_LINE_START:
            lines[i - 1] += lines[i][0]
            lines[i] = lines[i][1:]
    return [ln for ln in lines if ln]


def render_subtitle(text: str, out_path: str, size=(1920, 1080),
                    color=(60, 60, 60)) -> None:
    """字幕を全画面サイズの透過 PNG として描く。color は話者の縁取り色。"""
    from PIL import Image, ImageDraw
    from .slides import FONT_BOLD, _font

    W, H = size
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, H - SUBTITLE_BAND_H, W, H], fill=(255, 255, 255, 110))
    font = _font(FONT_BOLD, SUBTITLE_FONT_SIZE)
    lines = wrap_subtitle(text, W - 2 * SUBTITLE_SIDE, font)
    line_h = round(SUBTITLE_FONT_SIZE * 1.26)
    y = H - SUBTITLE_BAND_H + (SUBTITLE_BAND_H - line_h * len(lines)) // 2 - 4
    for ln in lines:
        x = (W - d.textlength(ln, font=font)) / 2
        # 外側に白の細い縁、内側に話者色の太い縁
        d.text((x, y), ln, font=font, fill="white", stroke_width=10, stroke_fill="white")
        d.text((x, y), ln, font=font, fill="white", stroke_width=7, stroke_fill=tuple(color))
        y += line_h
    img.save(out_path)


# 立ち絵: 画面端に寄せ、下を画面外に出して靴を描かない
CHAR_EDGE = -40   # 画面端からの距離（負 = 少しはみ出す）
CHAR_CUT = 0.16   # 立ち絵の下何割を画面外に出すか


def _char_size(height: int):
    w = round(CHAR_NATIVE[0] * height / CHAR_NATIVE[1])
    return w, height


def slot_positions(size, char_height: int):
    """左・右スロットの立ち絵左上座標 [(x, y), (x, y)]。完成動画とタイムラインで共通。"""
    W, H = size
    cw, ch = _char_size(char_height)
    y = H - round(ch * (1 - CHAR_CUT))
    return [(CHAR_EDGE, y), (W - cw - CHAR_EDGE, y)]


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
    pos = slot_positions(size, char_height)  # 左・右

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
        fc.append(f"{prev}[s{i}]overlay=x={pos[i][0]}:y={pos[i][1]}:shortest=0{out}")
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


def _video_seconds(path: str) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=duration", "-of", "csv=p=0", path],
                         check=True, capture_output=True, text=True).stdout
    return float(out.strip().rstrip(","))


def concat_clips(clips: List[str], out_path: str, sample_rate: int = 48000) -> None:
    """同一エンコード設定のクリップを、音声と映像がずれないように連結する。

    各クリップは AAC の都合で音声が映像より少し長いので、そのまま -c copy で連結すると
    映像のタイムスタンプに隙間ができ、隙間を無視する再生環境では後半ほど口パクと声がずれる。
    そこで映像はクリップごとの映像の尺で隙間なく繋ぎ（再エンコードなし）、音声は各クリップを
    映像の尺ぴったりに切り詰めた PCM を繋いでから 1 回だけ AAC にする。"""
    import wave

    ffmpeg = _ffmpeg()
    work = out_path + ".concat"
    os.makedirs(work, exist_ok=True)
    try:
        listfile = os.path.join(work, "list.txt")
        wav_out = os.path.join(work, "audio.wav")
        video_only = os.path.join(work, "video.mp4")
        with open(listfile, "w", encoding="utf-8") as f, wave.open(wav_out, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            for i, c in enumerate(clips):
                sec = _video_seconds(c)
                f.write(f"file '{os.path.abspath(c)}'\nduration {sec:.6f}\n")
                n = round(sec * sample_rate)
                pcm = subprocess.run(
                    [ffmpeg, "-v", "error", "-i", c, "-vn", "-ac", "2", "-ar", str(sample_rate),
                     "-af", "apad", "-f", "s16le", "-t", f"{sec:.6f}", "-"],
                    check=True, capture_output=True).stdout
                w.writeframes(pcm[: n * 4].ljust(n * 4, b"\0"))
        subprocess.run(
            [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", listfile, "-map", "0:v",
             "-c", "copy", video_only],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(
            [ffmpeg, "-y", "-i", video_only, "-i", wav_out, "-map", "0:v", "-map", "1:a",
             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", out_path],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        shutil.rmtree(work, ignore_errors=True)
