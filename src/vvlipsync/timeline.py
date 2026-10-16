"""audio_query から口パクのタイミング（母音の区間）を取り出す。

VOICEVOX の audio_query は各モーラの母音(vowel)と長さ(秒)を持つので、
forced alignment や LAB ファイルは不要。母音 → 口形にマップするだけでよい。
クエリ内の各長さは speedScale で割ると実時間になる。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

# VOICEVOX の母音表記のうち、口を開く 5 種。それ以外（N, cl, pau）は閉じ扱い。
VOWELS = {"a", "i", "u", "e", "o"}


@dataclass
class Segment:
    start: float  # 秒
    end: float  # 秒
    shape: str  # 'a','i','u','e','o','closed'


def vowel_to_shape(vowel: str) -> str:
    v = (vowel or "").lower()
    return v if v in VOWELS else "closed"


def query_segments(query: dict, speed: float = 1.0) -> Tuple[List[Segment], float]:
    """1 行分のクエリから (口形区間のリスト, 行全体の秒数) を返す。

    返す区間は行頭を 0 秒とした相対時刻。pre/post の無音や pause は区間を作らず、
    描画側でデフォルト（閉じ）に倒す。"""
    segs: List[Segment] = []
    t = query.get("prePhonemeLength", 0.0) / speed

    for ap in query.get("accent_phrases", []):
        for mora in ap.get("moras", []):
            dur = mora.get("vowel_length", 0.0)
            consonant_length = mora.get("consonant_length")
            if consonant_length:
                # 子音区間も直後の母音の口形に含める（短いので近似で十分）
                dur += consonant_length
            dur /= speed
            segs.append(Segment(t, t + dur, vowel_to_shape(mora.get("vowel"))))
            t += dur
        pause = ap.get("pause_mora")
        if pause:
            dur = pause.get("vowel_length", 0.0) / speed
            # 句読点ポーズは閉じ。区間は作らず時間だけ進める。
            t += dur

    t += query.get("postPhonemeLength", 0.0) / speed
    return segs, t


def pause_starts(query: dict, speed: float = 1.0) -> List[float]:
    """1 行分のクエリから、句読点ポーズの開始時刻（行頭からの秒）を返す。
    ポーズの切り替え（身振り）をこのタイミングに合わせる。"""
    starts: List[float] = []
    t = query.get("prePhonemeLength", 0.0) / speed
    for ap in query.get("accent_phrases", []):
        for mora in ap.get("moras", []):
            t += (mora.get("vowel_length", 0.0) + (mora.get("consonant_length") or 0.0)) / speed
        pause = ap.get("pause_mora")
        if pause:
            starts.append(t)
            t += pause.get("vowel_length", 0.0) / speed
    return starts


def pose_intervals(start: float, end: float, switch_times: List[float],
                   n_poses: int) -> List[Tuple[float, float, int]]:
    """[start, end) を switch_times で区切り、ポーズ番号 0,1,…,n_poses-1 を順に巡回して割り当てる。"""
    if n_poses <= 1:
        return [(start, end, 0)]
    cuts = [t for t in sorted(switch_times) if start < t < end]
    bounds = [start] + cuts + [end]
    return [(bounds[k], bounds[k + 1], k % n_poses) for k in range(len(bounds) - 1)]
