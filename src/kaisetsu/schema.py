"""解説動画の台本データ構造と、Gemini に渡す JSON スキーマ。

台本 = スライドの配列。各スライドは「表示する見出し＋本文」と、その内容を
ずんだもん・めたんが説明する掛け合い（行の配列）を持つ。
"""

from __future__ import annotations

# 登場キャラ（話者名）。Gemini にもこの2値だけ使わせる。
SPEAKERS = ["zundamon", "metan"]

# 感情名（assets/*/emotions.json と一致させる）
EMOTIONS = ["通常", "喜び", "怒り", "悲しみ", "驚き", "照れ"]

# Gemini structured output 用 JSON スキーマ（responseSchema）
SCRIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "動画全体のタイトル"},
        "slides": {
            "type": "array",
            "description": "スライド（説明の単位）の配列。元の文章を噛み砕いて構成する。",
            "items": {
                "type": "object",
                "properties": {
                    "heading": {"type": "string", "description": "スライドの見出し（短く）"},
                    "bullets": {
                        "type": "array",
                        "description": "スライドに表示する箇条書き（各15〜40字程度、3〜5個）",
                        "items": {"type": "string"},
                    },
                    "dialogue": {
                        "type": "array",
                        "description": "このスライドの内容を説明する掛け合い。めたんが解説役、ずんだもんが聞き役（相槌や素朴な疑問）。",
                        "items": {
                            "type": "object",
                            "properties": {
                                "speaker": {"type": "string", "enum": SPEAKERS},
                                "emotion": {"type": "string", "enum": EMOTIONS},
                                "text": {"type": "string", "description": "セリフ。ずんだもんは語尾『〜のだ/なのだ』、めたんは『〜だわ/かしら』口調。"},
                            },
                            "required": ["speaker", "emotion", "text"],
                        },
                    },
                },
                "required": ["heading", "bullets", "dialogue"],
            },
        },
    },
    "required": ["title", "slides"],
}
