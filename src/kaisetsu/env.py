""".env から環境変数を読む薄いローダ（依存なし）。"""

from __future__ import annotations

import os


def load_env(path: str = ".env") -> None:
    """KEY=VALUE 形式の .env を os.environ に流し込む（既存の環境変数は上書きしない）。"""
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def require(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise SystemExit(f"環境変数 {name} が未設定。.env に {name}=... を書く。")
    return val
