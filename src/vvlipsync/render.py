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


def _base_for(base_paths: dict, key):
    """base キー（(感情, ポーズ) または 感情）から base 画像パスを引く。
    ポーズ差分が無ければポーズ 0、感情別が無ければ base.png にフォールバックする。"""
    if key in base_paths and base_paths[key]:
        return base_paths[key]
    if isinstance(key, tuple) and base_paths.get((key[0], 0)):
        return base_paths[(key[0], 0)]
    return base_paths.get(None)


def _need_pillow():
    try:
        from PIL import Image, ImageOps
        return Image, ImageOps
    except ImportError:
        sys.exit("base 合成 / 反転 / モーションには Pillow が必要。`pip install Pillow` を実行する。")


def write_frames(frame_specs, mouth_paths: dict, base_paths: dict, out_dir: str,
                 digits: int = 5, flip: bool = False, transforms=None) -> None:
    """各フレームを書き出す。frame_specs は (base キー, 口形) のリスト。

    - base キー（(感情, ポーズ) など）に対応する base 画像があれば「base ＋ 口」を合成
      （表情つき全身キャラ連番）。
    - base が無ければ口 PNG をそのまま使う（合成しないので Pillow 不要）。
    - transforms（フレームごとの motion.Transform）があれば、足元を支点に体を動かす。
      base が無い（口だけ）の場合は位置がずれるので動かさない。
    - flip=True なら左右反転（動画の右端/左端配置でキャラを内向きにするため）。反転には Pillow が要る。
    動かさない場合、同じ (base キー, 口形) のフレームは 1 回だけ実体を作り、残りはハードリンクで使い回す。"""
    os.makedirs(out_dir, exist_ok=True)
    has_base = any(v for v in base_paths.values())
    if transforms is not None and has_base:
        _write_moving_frames(frame_specs, mouth_paths, base_paths, out_dir, digits, flip, transforms)
        return

    pil = None  # (Image, ImageOps)
    cache = {}  # (base キー, shape) -> 最初に実体を書いたフレームのパス
    for i, (key, shape) in enumerate(frame_specs):
        dst = os.path.join(out_dir, f"{i:0{digits}d}.png")
        if (key, shape) in cache:
            _link_or_copy(cache[(key, shape)], dst)
            continue

        base_path = _base_for(base_paths, key)
        if base_path or flip:
            if pil is None:
                pil = _need_pillow()
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
        cache[(key, shape)] = dst


def _write_moving_frames(frame_specs, mouth_paths, base_paths, out_dir, digits, flip, transforms):
    from .motion import feet_anchor, fit_headroom

    Image, _ = _need_pillow()
    # 支点はポーズによらず共通（腕を挙げても足元の位置は変わらないように）
    anchor_src = base_paths.get(None) or next(v for v in base_paths.values() if v)
    with Image.open(anchor_src) as im:
        im = im.convert("RGBA")
        anchor = feet_anchor(im)
        size = im.size
    # 頭上の余白が少ない立ち絵（めたん等）は、跳ねても頭が切れないよう上向きの動きを縮める
    top = size[1]
    for p in {_base_for(base_paths, key) for key, _ in frame_specs}:
        with Image.open(p) as im:
            bbox = im.convert("RGBA").getchannel("A").getbbox()
        if bbox:
            top = min(top, bbox[1])
    transforms = fit_headroom(transforms, top, anchor, size)

    jobs = [(os.path.join(out_dir, f"{i:0{digits}d}.png"), _base_for(base_paths, key),
             mouth_paths[shape], tf)
            for i, ((key, shape), tf) in enumerate(zip(frame_specs, transforms))]

    # 1 フレームずつ変形・PNG 圧縮するので重い。コア数でチャンク分割して並列に書く
    workers = max(1, min(os.cpu_count() or 1, 8, len(jobs) // 30 or 1))
    chunks = [jobs[k::workers] for k in range(workers)]
    if workers == 1:
        _render_moving_chunk(chunks[0], anchor, flip)
        return
    from concurrent.futures import ProcessPoolExecutor
    from concurrent.futures.process import BrokenProcessPool
    try:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for f in [ex.submit(_render_moving_chunk, c, anchor, flip) for c in chunks]:
                f.result()
    except BrokenProcessPool:
        # 呼び出し元の __main__ が再 import できない環境（stdin 実行など）では逐次で書く
        _render_moving_chunk(jobs, anchor, flip)


def _render_moving_chunk(jobs, anchor, flip) -> None:
    from .motion import apply_transform

    Image, ImageOps = _need_pillow()
    images = {}  # path -> Image
    composed = {}  # (base path, mouth path) -> 動かす前の合成済み立ち絵

    def load(path):
        if path not in images:
            images[path] = Image.open(path).convert("RGBA")
        return images[path]

    for dst, base_path, mouth_path, tf in jobs:
        ck = (base_path, mouth_path)
        if ck not in composed:
            img = load(base_path).copy()
            img.alpha_composite(load(mouth_path))
            composed[ck] = img
        out = apply_transform(composed[ck], tf, anchor)
        if flip:
            out = ImageOps.mirror(out)
        if os.path.lexists(dst):
            os.remove(dst)
        out.save(dst, compress_level=1)


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
