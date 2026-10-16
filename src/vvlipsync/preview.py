"""確認用プレビュー動画の生成。

透過 PNG 連番（口パク）を base 立ち絵の上に重ね、音声と合わせて 1 本の mp4 にする。
合成は ffmpeg の overlay で行うので、フレーム数によらず速い。DaVinci に持ち込む前の
チェック用であり、最終成果物ではない（成果物は frames/ + audio.wav + subtitles.srt）。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import wave
from glob import glob


def _ffmpeg_bin() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        sys.exit("ffmpeg が見つからない。`brew install ffmpeg` などで入れてからプレビューを生成する。")
    return exe


def _canvas_size(png_path: str):
    # 依存を増やさないよう PNG ヘッダ(IHDR)から幅・高さを読む
    with open(png_path, "rb") as f:
        f.read(16)  # 8バイトシグネチャ + 4バイト長さ + "IHDR"
        w = int.from_bytes(f.read(4), "big")
        h = int.from_bytes(f.read(4), "big")
    return w, h


def compile_preview(
    frames_dir: str,
    audio_path: str,
    out_path: str,
    fps: float,
    base: str = "",
    bg: str = "white",
    digits: int = 5,
) -> None:
    ffmpeg = _ffmpeg_bin()

    frame_files = sorted(glob(os.path.join(frames_dir, "*.png")))
    if not frame_files:
        sys.exit(f"フレーム PNG が無い: {frames_dir}")
    w, h = _canvas_size(base if base else frame_files[0])
    pattern = os.path.join(frames_dir, f"%0{digits}d.png")

    # 入力を組み立てる: [0] 背景色, ([1] base), 続いて 口連番, 音声
    args = [ffmpeg, "-y", "-f", "lavfi", "-i", f"color=c={bg}:s={w}x{h}:r={fps}"]
    idx = 1
    if base:
        args += ["-loop", "1", "-i", base]
        base_idx = idx
        idx += 1
    args += ["-framerate", str(fps), "-start_number", "0", "-i", pattern]
    mouth_idx = idx
    idx += 1
    args += ["-i", audio_path]
    audio_idx = idx

    # 背景 → (base) → 口 の順に重ね、口連番の尺で打ち切る
    if base:
        fc = (
            f"[0:v][{base_idx}:v]overlay=shortest=1[b];"
            f"[b][{mouth_idx}:v]overlay=shortest=1,format=yuv420p[v]"
        )
    else:
        fc = f"[0:v][{mouth_idx}:v]overlay=shortest=1,format=yuv420p[v]"

    args += [
        "-filter_complex", fc,
        "-map", "[v]", "-map", f"{audio_idx}:a",
        "-c:v", "libx264", "-c:a", "aac",
        "-r", str(fps), "-shortest", out_path,
    ]

    subprocess.run(args, check=True)
    print(f"プレビュー動画: {out_path}")


# 透過動画の書き出し設定（拡張子ごと）。
#   .mov  = ProRes 4444（DaVinci / Premiere / Final Cut で透過のまま扱える。容量は大きい）
#   .webm = VP9 アルファ（ブラウザ・OBS 向け。軽い）
ALPHA_CODECS = {
    ".mov": ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le",
             "-vendor", "apl0", "-c:a", "pcm_s16le"],
    ".webm": ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", "30",
              "-row-mt", "1", "-c:a", "libopus"],
}


def alpha_video_args(ffmpeg: str, frames_dir: str, audio_path: str, out_path: str,
                     fps: float, digits: int = 5) -> list:
    """透過 PNG 連番＋音声から、アルファ付き動画を作る ffmpeg 引数を返す。"""
    ext = os.path.splitext(out_path)[1].lower()
    if ext not in ALPHA_CODECS:
        raise ValueError(f"透過動画は {' / '.join(ALPHA_CODECS)} のみ対応: {out_path}")
    return [
        ffmpeg, "-y",
        "-framerate", str(fps), "-start_number", "0",
        "-i", os.path.join(frames_dir, f"%0{digits}d.png"),
        "-i", audio_path,
        "-map", "0:v", "-map", "1:a",
        *ALPHA_CODECS[ext],
        "-shortest", out_path,
    ]


def compile_alpha_video(frames_dir: str, audio_path: str, out_path: str, fps: float) -> None:
    args = alpha_video_args(_ffmpeg_bin(), frames_dir, audio_path, out_path, fps)
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"透過動画: {out_path}")


def _audio_duration(path: str) -> float:
    with wave.open(path) as w:
        return w.getnframes() / w.getframerate()


def main(argv=None) -> int:
    import argparse

    p = argparse.ArgumentParser(
        prog="vvlipsync-preview",
        description="frames/ + audio.wav を base 立ち絵に重ねて確認用 mp4 を作る",
    )
    p.add_argument("out_dir", help="vvlipsync の出力ディレクトリ（frames/ と audio.wav を含む）")
    p.add_argument("-b", "--base", default="", help="背景に敷く立ち絵 base.png")
    p.add_argument("--bg", default="white", help="背景色 (既定: white、例: green, black, #00FF00)")
    p.add_argument("--fps", type=float, default=30.0, help="フレームレート (既定: 30)")
    p.add_argument("-o", "--out", default="", help="出力 mp4（既定: out_dir/preview.mp4）")
    args = p.parse_args(argv)

    frames_dir = os.path.join(args.out_dir, "frames")
    audio_path = os.path.join(args.out_dir, "audio.wav")
    out_path = args.out or os.path.join(args.out_dir, "preview.mp4")
    compile_preview(frames_dir, audio_path, out_path, args.fps, base=args.base, bg=args.bg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
