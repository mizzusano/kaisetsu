"""字幕（表記）と読み上げ（読み）の書き分け。

台本のセリフ text は字幕に出す表記（英字・算用数字で読みやすく）。VOICEVOX には読みを渡す:
  - 台本トップの "readings": {"表記": "読み"} で、表記を読みに置き換える（長い語から優先）
  - セリフ個別の "yomi" があればそれをそのまま使う（辞書では表せない読みの時）
"""

from __future__ import annotations

from typing import Dict


def apply_readings(text: str, readings: Dict[str, str]) -> str:
    """readings の表記を読みに置き換える。長い表記から順に当て、置き換えた部分は再置換しない。"""
    if not readings:
        return text
    keys = sorted((k for k in readings if k), key=len, reverse=True)
    out, i = [], 0
    while i < len(text):
        for k in keys:
            if text.startswith(k, i):
                out.append(readings[k])
                i += len(k)
                break
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def line_reading(line: dict, readings: Dict[str, str]) -> str:
    """セリフ（dialogue の 1 要素）の読み。yomi があれば優先、無ければ辞書で置き換える。"""
    if line.get("yomi"):
        return line["yomi"]
    return apply_readings(line["text"], readings)
