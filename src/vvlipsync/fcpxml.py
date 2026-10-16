"""DaVinci Resolve などに取り込めるタイムライン（FCPXML 1.9）の生成。

vvlipsync 単体（キャラ 1 人＋音声）と kaisetsu（スライド＋キャラ 2 人＋セリフ＋BGM）で共通に使う。
時間はすべてフレーム数で受け取り、fps の有理数表記（"45/30s" など）で書き出す。
"""

from __future__ import annotations

import math
import os
from fractions import Fraction
from typing import List, Optional, Tuple
from urllib.parse import quote
from xml.sax.saxutils import quoteattr


def _fps_fraction(fps: float) -> Fraction:
    r = round(fps)
    if abs(fps - r) > 1e-6 and abs(fps - r * 1000 / 1001) < 1e-2:
        return Fraction(r * 1000, 1001)  # 29.97 / 59.94 などの NTSC レート
    return Fraction(fps).limit_denominator(1001)


def fcpxml_time(frames: int, fps: float) -> str:
    if frames == 0:
        return "0s"
    f = _fps_fraction(fps)
    return f"{frames * f.denominator}/{f.numerator}s"


def _src(path: str) -> str:
    return "file://" + quote(os.path.abspath(path))


def build_fcpxml(name: str, fps: float, size: Tuple[int, int], total: int,
                 slides: List[Tuple[str, int, int]],
                 characters: List[Tuple[str, str, int]],
                 voices: List[Tuple[str, int, int, int, int]],
                 bgm: Optional[Tuple[str, int, int, int, float]] = None) -> str:
    """FCPXML 1.9 を文字列で返す。

    slides: (画像, 開始, 長さ)  characters: (表示名, 動画, レーン[, (幅, 高さ)])
    voices: (wav, 開始, 長さ, サンプルレート, ch)  bgm: (wav, 長さ, サンプルレート, ch, 音量倍率)
    時間はすべてフレーム数。クリップはすべて全尺の gap に接続し、lane でトラックを分ける。"""
    t = lambda n: fcpxml_time(n, fps)  # noqa: E731
    W, H = size
    res = [f'<format id="r1" name="FFVideoFormat{H}p{round(fps)}" frameDuration="{t(1)}" '
           f'width="{W}" height="{H}"/>',
           f'<format id="r2" name="FFVideoFormatRateUndefined" width="{W}" height="{H}"/>']
    clips = []
    ids = {}

    def asset(path, attrs):
        if path not in ids:
            ids[path] = f"a{len(ids) + 1}"
            res.append(f'<asset id="{ids[path]}" name={quoteattr(os.path.basename(path))} '
                       f'src={quoteattr(_src(path))} start="0s" {attrs}/>')
        return ids[path]

    for png, start, dur in slides:
        ref = asset(png, 'duration="0s" hasVideo="1" format="r2"')
        clips.append(f'<video ref="{ref}" lane="1" offset="{t(start)}" duration="{t(dur)}" '
                     f'start="0s" name={quoteattr(os.path.basename(png))}/>')
    for label, mov, lane, *rest in characters:
        fmt = "r1"
        if rest and tuple(rest[0]) != (W, H):
            # タイムラインと違うサイズの素材（立ち絵の元サイズなど）は専用の format を持たせる
            fmt = f"r{len(res) + 1}"
            mw, mh = rest[0]
            res.append(f'<format id="{fmt}" name="FFVideoFormat{mh}p{round(fps)}" '
                       f'frameDuration="{t(1)}" width="{mw}" height="{mh}"/>')
        ref = asset(mov, f'duration="{t(total)}" hasVideo="1" format="{fmt}"')
        clips.append(f'<asset-clip ref="{ref}" lane="{lane}" offset="0s" duration="{t(total)}" '
                     f'start="0s" name={quoteattr(label)}/>')
    for wav, start, dur, rate, ch in voices:
        ref = asset(wav, f'duration="{t(dur)}" hasAudio="1" audioSources="1" '
                         f'audioChannels="{ch}" audioRate="{rate}"')
        clips.append(f'<asset-clip ref="{ref}" lane="-1" offset="{t(start)}" duration="{t(dur)}" '
                     f'start="0s" name={quoteattr(os.path.basename(os.path.dirname(wav)))}/>')
    if bgm:
        wav, dur, rate, ch, vol = bgm
        ref = asset(wav, f'duration="{t(dur)}" hasAudio="1" audioSources="1" '
                         f'audioChannels="{ch}" audioRate="{rate}"')
        db = 20 * math.log10(vol) if vol > 0 else -96.0
        clips.append(f'<asset-clip ref="{ref}" lane="-2" offset="0s" duration="{t(dur)}" '
                     f'start="0s" name="BGM"><adjust-volume amount="{db:.1f}dB"/></asset-clip>')

    body = "\n".join("          " + c for c in clips)
    resources = "\n".join("    " + r for r in res)
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.9">
  <resources>
{resources}
  </resources>
  <library>
    <event name={quoteattr(name)}>
      <project name={quoteattr(name)}>
        <sequence format="r1" duration="{t(total)}" tcStart="0s" tcFormat="NDF" audioLayout="stereo" audioRate="48k">
          <spine>
            <gap name="Gap" offset="0s" duration="{t(total)}" start="0s">
{body}
            </gap>
          </spine>
        </sequence>
      </project>
    </event>
  </library>
</fcpxml>
'''


def single_character_fcpxml(name: str, fps: float, size: Tuple[int, int], total: int, *,
                            mov: str, mov_size: Tuple[int, int], wav: str, wav_frames: int,
                            audio_rate: int, audio_channels: int) -> str:
    """vvlipsync 単体用: V1=キャラの透過動画（元サイズのまま）、A1=音声。字幕は subtitles.srt を別に読む。"""
    return build_fcpxml(name, fps, size, total, slides=[],
                        characters=[(name, mov, 1, mov_size)],
                        voices=[(wav, 0, min(wav_frames, total), audio_rate, audio_channels)])
