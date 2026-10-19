"""kaisetsu の構成を DaVinci Resolve に取り込めるタイムライン（FCPXML）として書き出す。

完成 mp4 とは別に、編集可能な素材一式を作る:

    V1  スライド / タイトルカード（静止画。同じスライドが続く区間は 1 クリップにまとめる）
    V2  四国めたん（全尺の透過 ProRes 4444。完成動画と同じ位置に配置済み）
    V3  ずんだもん（同上）
    A1  セリフ音声（セリフごとのクリップ）
    A2  BGM（任意）
    字幕は通しの subtitles.srt を別ファイルで出す（DaVinci の字幕トラックに読み込む）

キャラは FCPXML の変形指定に頼らず、1920x1080 の透過キャンバス上に配置済みの動画として
書き出す（取り込み側の解釈差で位置がずれないように）。DaVinci 上で位置は後から動かせる。
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Tuple

from vvlipsync.fcpxml import build_fcpxml, fcpxml_time  # noqa: F401  (kaisetsu からも使う)


@dataclass
class Segment:
    bg_png: str
    speaker: str
    label: str
    text: str
    seg_dir: str
    n_frames: int
    head: float
    tail: float
    audio: str
    audio_seconds: float
    subtitle: bool = True
    show_characters: bool = True


@dataclass
class Placement:
    start: int  # タイムライン上の開始フレーム
    head: int   # セリフ前の「間」
    body: int   # セリフ（キャラ連番の枚数）
    tail: int   # セリフ後の「間」

    @property
    def total(self) -> int:
        return self.head + self.body + self.tail

    @property
    def voice_start(self) -> int:
        return self.start + self.head


def place(segments: List[Segment], fps: float) -> List[Placement]:
    """各セグメントを [間][セリフ][間] としてフレーム単位で隙間なく並べる。"""
    out, cur = [], 0
    for s in segments:
        p = Placement(cur, round(s.head * fps), s.n_frames, round(s.tail * fps))
        out.append(p)
        cur += p.total
    return out


def _frames_in(d: str) -> List[str]:
    return sorted(os.path.join(d, f) for f in os.listdir(d) if f.endswith(".png"))


def character_frames(segments: List[Segment], placements: List[Placement], name: str,
                     blank: str) -> List[str]:
    """キャラ 1 人分の全尺フレーム列（PNG パス）を返す。

    喋っている区間は話者連番、それ以外は聞き手連番、キャラ非表示（章扉）は blank。
    「間」は完成動画と同じく最初/最後のフレームを保持する。"""
    out: List[str] = []
    for s, p in zip(segments, placements):
        if not s.show_characters:
            out += [blank] * p.total
            continue
        sub = "frames" if s.speaker == name else f"listener_{name}"
        frames = _frames_in(os.path.join(s.seg_dir, sub))[: p.body]
        out += [frames[0]] * p.head + frames + [frames[-1]] * p.tail
    return out


def slide_runs(segments: List[Segment], placements: List[Placement]) -> List[Tuple[str, int, int]]:
    """(背景画像, 開始フレーム, 長さ) — 同じ画像が続く区間は 1 つにまとめる。"""
    runs: List[List] = []
    for s, p in zip(segments, placements):
        if runs and runs[-1][0] == s.bg_png:
            runs[-1][2] += p.total
        else:
            runs.append([s.bg_png, p.start, p.total])
    return [tuple(r) for r in runs]


def subtitle_entries(segments: List[Segment], placements: List[Placement],
                     fps: float) -> List[Tuple[float, float, str]]:
    """通しタイムラインの字幕（秒）。セリフの区間だけ、完成動画と同じ「話者「本文」」形式。"""
    return [(p.voice_start / fps, (p.voice_start + p.body) / fps, f"{s.label}「{s.text}」")
            for s, p in zip(segments, placements) if s.subtitle]


# ---- 素材の書き出し（ffmpeg / Pillow を使う。build から呼ぶ） ----

def write_character_mov(frames: List[str], out_path: str, fps: float, size: Tuple[int, int],
                        char_height: int, x: int, y: int) -> None:
    """フレーム列を、W×H の透過キャンバス上 (x, y) に高さ char_height で置いた ProRes 4444 にする。"""
    work = out_path + ".seq"
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work)
    for i, src in enumerate(frames):
        dst = os.path.join(work, f"{i:06d}.png")
        try:
            os.link(src, dst)
        except OSError:
            shutil.copyfile(src, dst)
    W, H = size
    # 立ち絵は画面外にはみ出す配置（端に寄せ・足元を切る）なので、余白を足して置いてから切り出す
    m = char_height
    vf = (f"format=rgba,scale=-1:{char_height}:flags=lanczos,"
          f"pad={W + 2 * m}:{H + 2 * m}:{x + m}:{y + m}:color=0x00000000,"
          f"crop={W}:{H}:{m}:{m}")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-framerate", str(fps), "-i", os.path.join(work, "%06d.png"),
             "-vf", vf, "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le",
             "-vendor", "apl0", "-r", str(fps), out_path],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def write_srt(entries, path: str) -> None:
    from vvlipsync.render import write_srt as _w
    _w(entries, path)


def wav_info(path: str) -> Tuple[float, int, int]:
    import wave
    with wave.open(path) as w:
        return w.getnframes() / w.getframerate(), w.getframerate(), w.getnchannels()


def write_bgm_wav(src: str, out_path: str, seconds: float) -> None:
    """BGM（mp3/mp4）をループして全尺ぶんの wav にする（音量は FCPXML 側で下げる）。"""
    subprocess.run(
        ["ffmpeg", "-y", "-stream_loop", "-1", "-i", src, "-t", f"{seconds:.3f}",
         "-vn", "-ac", "2", "-ar", "48000", "-c:a", "pcm_s16le", out_path],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
