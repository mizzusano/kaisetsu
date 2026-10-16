"""kaisetsu CLI: markdown を ずんだもん×めたん の解説動画にする。

    kaisetsu 入力.md -o out/                 # Gemini で台本生成 → 動画
    kaisetsu --script 台本.json -o out/       # 台本を直接指定（Gemini なし）
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .build import build_video
from .env import load_env


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="kaisetsu",
        description="markdown を ずんだもん×めたん の掛け合い解説動画にする",
    )
    p.add_argument("input", nargs="?",
                   help="入力ファイル。.md はそのまま、それ以外のテキストは markdown に整理してから使う")
    p.add_argument("-t", "--text", help="文章を直接指定（markdown に整理してから動画化する）")
    p.add_argument("-o", "--out", default="build_out", help="出力ディレクトリ (既定: build_out)")
    p.add_argument("--assets-root", default="assets",
                   help="キャラ素材のルート（zundamon/ metan/ を含む。既定: assets）")
    p.add_argument("--script", help="台本 JSON を直接指定（Gemini を使わずに合成だけ行う）")
    p.add_argument("--model", default="gemini-2.5-flash", help="Gemini モデル")
    p.add_argument("--fps", type=float, default=30.0, help="フレームレート")
    p.add_argument("--bgm", default="", help="BGM ファイル（mp3 または mp4）。動画全体に小音量でミックス")
    p.add_argument("--bgm-volume", type=float, default=0.18, help="BGM の音量倍率 (既定: 0.18)")
    p.add_argument("--no-title-call", action="store_true",
                   help="段落（スライド）頭のタイトルコールを入れない")
    p.add_argument("--announcer", default="zundamon", choices=["zundamon", "metan"],
                   help="タイトルコールを読む話者 (既定: zundamon)")
    p.add_argument("--timeline", action="store_true",
                   help="DaVinci 取り込み用のタイムライン（timeline/timeline.fcpxml ＋素材）も書き出す")
    p.add_argument("--timeline-only", action="store_true",
                   help="タイムラインだけ書き出す（完成 mp4 の合成を省く）")
    args = p.parse_args(argv)

    if args.bgm and not os.path.isfile(args.bgm):
        sys.exit(f"BGM ファイルが見つからない: {args.bgm}")

    load_env()

    os.makedirs(args.out, exist_ok=True)

    if args.script:
        with open(args.script, encoding="utf-8") as f:
            script = json.load(f)
    else:
        from .gemini import generate_script, text_to_markdown

        # 入力 markdown を用意する。
        # - .md ファイル → そのまま
        # - それ以外のテキストファイル / --text → Gemini で markdown に整理（orchestration）
        if args.text is not None:
            raw, is_md = args.text, False
        elif args.input:
            with open(args.input, encoding="utf-8") as f:
                raw = f.read()
            is_md = args.input.lower().endswith((".md", ".markdown"))
        else:
            sys.exit("入力（ファイル / --text / --script）のいずれかを指定する")

        if is_md:
            md = raw
        else:
            print(f"Gemini ({args.model}) で文章を markdown に整理中…")
            md = text_to_markdown(raw, model=args.model)
            with open(os.path.join(args.out, "source.md"), "w", encoding="utf-8") as f:
                f.write(md)

        print(f"Gemini ({args.model}) で台本生成中…")
        script = generate_script(md, model=args.model)
    with open(os.path.join(args.out, "script.json"), "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)

    n_lines = sum(len(s.get("dialogue", [])) for s in script["slides"])
    print(f"台本: {script.get('title','(無題)')} / {len(script['slides'])} スライド / {n_lines} セリフ")

    final = build_video(script, args.out, args.assets_root, fps=args.fps,
                        bgm=args.bgm, bgm_volume=args.bgm_volume,
                        title_call=not args.no_title_call, announcer=args.announcer,
                        timeline=args.timeline or args.timeline_only,
                        video=not args.timeline_only,
                        base_dir=os.path.dirname(os.path.abspath(args.script)) if args.script else ".")
    print(f"完成: {final}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
