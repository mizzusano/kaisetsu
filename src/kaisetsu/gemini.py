"""Gemini REST を叩いて markdown → 解説台本(JSON) を生成する（依存なし）。"""

from __future__ import annotations

import json
import os
import urllib.request

from .schema import EMOTIONS, SCRIPT_SCHEMA

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

PROMPT = """あなたは難しい技術文章を、ずんだもんと四国めたんの掛け合い解説動画の台本にする構成作家です。
入力の markdown を読み、視聴者が直感的に理解できるよう噛み砕いて、スライド単位の台本を作ってください。

# 役割
- 四国めたん = 解説役。落ち着いた優しい先生口調（「〜だわ」「〜かしら」「〜のよ」）。
- ずんだもん = 聞き役。素朴な疑問・相槌・たまにボケ（「〜のだ」「〜なのだ」「〜なのだ？」）。

# ルール
- 各スライド: heading 1つ ＋ bullets 3〜5個（画面に出す要約。各15〜40字、簡潔に）＋ dialogue 4〜8行。
- 掛け合いは「ずんだもんが疑問 → めたんが解説 → ずんだもんが理解/驚き」を基本に自然に展開する。
- 難しい用語は噛み砕き、身近な具体例やたとえを入れる。
- emotion は各セリフの内容に合うものを次から選ぶ: {emotions}
- スライド数は内容量に応じて 3〜8 枚程度。冒頭に導入、末尾にまとめを入れる。

# 入力 markdown
---
{md}
---
"""


MD_PROMPT = """次の文章を、解説動画の元ネタとして使いやすいように、日本語の構造化 markdown に整理してください。

# ルール
- 見出し（#, ##）で話題を区切り、要点は箇条書き（-）にまとめる。
- 原文にない情報を足したり、事実を捏造したりしない。原文の内容を保ったまま整理する。
- 冗長な表現は簡潔にしてよいが、重要な情報は落とさない。
- 出力は markdown 本文のみ（前置き・説明・コードフェンスで囲まない）。

# 元の文章
---
{text}
---
"""


def _post(model: str, body: dict, api_key: str = "") -> dict:
    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise SystemExit("GEMINI_API_KEY が未設定。.env に書く。")
    url = API.format(model=model) + "?key=" + key
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read())


def _text_of(data: dict) -> str:
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise SystemExit(f"Gemini 応答を解釈できない: {json.dumps(data, ensure_ascii=False)[:500]}")


def text_to_markdown(text: str, model: str = "gemini-2.5-flash", api_key: str = "") -> str:
    """生の文章を、解説の元ネタにしやすい構造化 markdown に整理する。"""
    body = {
        "contents": [{"parts": [{"text": MD_PROMPT.format(text=text)}]}],
        "generationConfig": {"temperature": 0.4},
    }
    return _text_of(_post(model, body, api_key)).strip()


def generate_script(md: str, model: str = "gemini-2.5-flash", api_key: str = "") -> dict:
    body = {
        "contents": [{"parts": [{"text": PROMPT.format(md=md, emotions="、".join(EMOTIONS))}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": SCRIPT_SCHEMA,
            "temperature": 0.7,
        },
    }
    return json.loads(_text_of(_post(model, body, api_key)))
