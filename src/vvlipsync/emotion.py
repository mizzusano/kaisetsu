"""感情（VOICEVOX のスタイル）を名前で解決する。

VOICEVOX では「キャラクター × スタイル（ノーマル / あまあま / なみだめ …）」の
組み合わせがそれぞれ数値の speaker ID を持つ。この「スタイル名」が実質の感情なので、
ベースの話者ID から同一キャラの別スタイルIDへ引き直すことで感情指定を実現する。
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple


class EmotionResolver:
    def __init__(self, speakers_json: list):
        # style_id -> キャラ名 / キャラ名 -> {スタイル名: style_id}
        self.id_to_char: Dict[int, str] = {}
        self.char_styles: Dict[str, Dict[str, int]] = {}
        for sp in speakers_json:
            cname = sp["name"]
            self.char_styles.setdefault(cname, {})
            for st in sp.get("styles", []):
                self.id_to_char[st["id"]] = cname
                self.char_styles[cname][st["name"]] = st["id"]

    def resolve(self, base_speaker: int, emotion: Optional[str]) -> int:
        """ベース話者IDと感情名から、実際に使う speaker ID を返す。"""
        if not emotion:
            return base_speaker
        cname = self.id_to_char.get(base_speaker)
        if cname is None:
            raise KeyError(f"話者ID {base_speaker} はエンジンに存在しない")
        styles = self.char_styles[cname]
        if emotion not in styles:
            avail = "、".join(styles.keys())
            raise KeyError(f"{cname} に感情『{emotion}』が無い。利用可能: {avail}")
        return styles[emotion]

    def describe(self, base_speaker: int) -> Tuple[str, list]:
        """話者IDのキャラ名と利用可能な感情名一覧を返す。"""
        cname = self.id_to_char.get(base_speaker, "?")
        return cname, list(self.char_styles.get(cname, {}).keys())


def format_catalog(speakers_json: list) -> str:
    lines = []
    for sp in speakers_json:
        styles = "、".join(f"{st['name']}={st['id']}" for st in sp.get("styles", []))
        lines.append(f"{sp['name']}: {styles}")
    return "\n".join(lines)
