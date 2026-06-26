"""VOICEVOX ENGINE の HTTP API クライアント（標準ライブラリのみ）。"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request


class VoicevoxClient:
    def __init__(self, host: str = "http://localhost:50021", timeout: float = 60.0):
        self.host = host.rstrip("/")
        self.timeout = timeout

    def _post(self, path, params=None, data=None) -> bytes:
        url = self.host + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        body = None
        headers = {}
        if data is not None:
            body = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return resp.read()

    def speakers(self) -> list:
        """話者（キャラ＋スタイル）一覧を取得する。感情名→IDの解決に使う。"""
        with urllib.request.urlopen(self.host + "/speakers", timeout=self.timeout) as resp:
            return json.loads(resp.read())

    def audio_query(self, text: str, speaker: int) -> dict:
        """テキストから音声合成用クエリを生成する。
        返り値にモーラ単位の母音とその長さ（秒）が含まれ、これが口パクの元データになる。"""
        raw = self._post("/audio_query", params={"text": text, "speaker": speaker})
        return json.loads(raw)

    def synthesis(self, query: dict, speaker: int) -> bytes:
        """クエリから wav バイト列を合成する。"""
        return self._post("/synthesis", params={"speaker": speaker}, data=query)
