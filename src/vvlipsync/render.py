"""口形区間 → 透過 PNG 連番 / 連結 wav / SRT 字幕 への書き出し。"""

from __future__ import annotations

import io
import os
import shutil
import sys
import wave
from typing import List, Tuple

from .timeline import Segment


def shapes_per_frame(segments: List[Segment], total_frames: int, fps: float) -> List[str]:
    """各フレーム（中央時刻でサンプリング）に割り当てる口形を返す。"""
    segs = sorted(segments, key=lambda s: s.start)
    result: List[str] = []
    j = 0
    for i in range(total_frames):
        t = (i + 0.5) / fps
        while j < len(segs) and segs[j].end <= t:
            j += 1
        if j < len(segs) and segs[j].start <= t < segs[j].end:
            result.append(segs[j].shape)
        else:
            result.append("closed")
    return result


def values_per_frame(intervals, total_frames: int, fps: float, default):
    """(start, end, value) の区間列から、各フレームの value を返す（口形と同じ要領）。"""
    segs = sorted(intervals, key=lambda x: x[0])
    result = []
    j = 0
    for i in range(total_frames):
        t = (i + 0.5) / fps
        while j < len(segs) and segs[j][1] <= t:
            j += 1
        if j < len(segs) and segs[j][0] <= t < segs[j][1]:
            result.append(segs[j][2])
        else:
            result.append(default)
    return result


def _link_or_copy(src: str, dst: str) -> None:
    if os.path.lexists(dst):
        os.remove(dst)
    try:
        os.link(src, dst)
    except OSError:
        shutil.copyfile(src, dst)


def write_frames(frame_specs, mouth_paths: dict, base_paths: dict, out_dir: str,
                 digits: int = 5, flip: bool = False) -> None:
    """各フレームを書き出す。frame_specs は (感情, 口形) のリスト。

    - 感情に対応する base 画像があれば「base ＋ 口」を合成（表情つき全身キャラ連番）。
    - base が無ければ口 PNG をそのまま使う（合成しないので Pillow 不要）。
    - flip=True なら左右反転（動画の右端/左端配置でキャラを内向きにするため）。反転には Pillow が要る。
    同じ (感情, 口形) のフレームは 1 回だけ実体を作り、残りはハードリンクで使い回す。"""
    os.makedirs(out_dir, exist_ok=True)
    pil = None  # (Image, ImageOps)
    cache = {}  # (emotion, shape) -> 最初に実体を書いたフレームのパス
    for i, (emotion, shape) in enumerate(frame_specs):
        dst = os.path.join(out_dir, f"{i:0{digits}d}.png")
        key = (emotion, shape)
        if key in cache:
            _link_or_copy(cache[key], dst)
            continue

        base_path = base_paths.get(emotion) or base_paths.get(None)
        if base_path or flip:
            if pil is None:
                try:
                    from PIL import Image, ImageOps
                    pil = (Image, ImageOps)
                except ImportError:
                    sys.exit("base 合成 / 反転には Pillow が必要。`pip install Pillow` を実行する。")
            Image, ImageOps = pil
            if os.path.lexists(dst):
                os.remove(dst)
            if base_path:
                img = Image.open(base_path).convert("RGBA").copy()
                img.alpha_composite(Image.open(mouth_paths[shape]).convert("RGBA"))
            else:
                img = Image.open(mouth_paths[shape]).convert("RGBA")
            if flip:
                img = ImageOps.mirror(img)
            img.save(dst)
        else:
            _link_or_copy(mouth_paths[shape], dst)
        cache[key] = dst


def build_audio(items: List[Tuple[float, bytes, float]], out_path: str) -> None:
    """各行を (行頭ギャップ秒, wav バイト列, 行の秒数) として受け取り、1 本の wav に連結する。

    各行は「行の秒数」ぴったりに合わせて無音パディング/トリムするので、
    音声の総尺が PNG 連番のタイムラインと一致する。"""
    if not items:
        raise ValueError("no audio items")

    with wave.open(io.BytesIO(items[0][1])) as w0:
        nchannels = w0.getnchannels()
        sampwidth = w0.getsampwidth()
        framerate = w0.getframerate()

    frame_size = sampwidth * nchannels
    silence = b"\x00" * frame_size

    with wave.open(out_path, "wb") as out:
        out.setnchannels(nchannels)
        out.setsampwidth(sampwidth)
        out.setframerate(framerate)

        for gap_before, wav_bytes, total in items:
            if gap_before > 0:
                out.writeframes(silence * round(gap_before * framerate))

            with wave.open(io.BytesIO(wav_bytes)) as w:
                if (w.getframerate(), w.getsampwidth(), w.getnchannels()) != (
                    framerate, sampwidth, nchannels,
                ):
                    raise ValueError("wav format mismatch between lines")
                n = w.getnframes()
                frames = w.readframes(n)

            target = round(total * framerate)
            if n >= target:
                out.writeframes(frames[: target * frame_size])
            else:
                out.writeframes(frames)
                out.writeframes(silence * (target - n))


def _fmt_ts(sec: float) -> str:
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(entries: List[Tuple[float, float, str]], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for i, (start, end, text) in enumerate(entries, 1):
            f.write(f"{i}\n{_fmt_ts(start)} --> {_fmt_ts(end)}\n{text}\n\n")
