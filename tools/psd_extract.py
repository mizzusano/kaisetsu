"""PSDTool 形式の立ち絵 PSD から、vvlipsync 用の素材を書き出す。

- 母音6種の口を、フルキャンバスの透過 PNG として書き出す（口が正しい位置に配置済み）
- 口以外の静止背景（base.png）も書き出す

依存: psd-tools, Pillow
    pip install psd-tools

使い方:
    python tools/psd_extract.py PSDパス -o 出力dir [--map マッピングJSON]

マッピング JSON の例（母音 -> 口レイヤー名。'*' などの接頭辞は無視して部分一致でOK）:
    {
      "mouth_group": "口",
      "mouths": {
        "a": "ほあー", "i": "んへー", "u": "ゆ",
        "e": "はへえ", "o": "お", "closed": "んー"
      }
    }
"""

from __future__ import annotations

import argparse
import json
import sys

from PIL import Image
from psd_tools import PSDImage

# ずんだもん立ち絵素材2.3 向けの既定マッピング
DEFAULT_MAP = {
    "mouth_group": "口",
    "mouths": {
        "a": "ほあー",
        "i": "んへー",
        "u": "ゆ",
        "e": "はへえ",
        "o": "お",
        "closed": "んー",
    },
}


def find_group(psd, name):
    # 接頭辞を除いた完全一致を優先（'目' が '枝豆'/'目セット' に誤マッチしないように）
    for layer in psd.descendants():
        if layer.is_group() and _strip(layer.name) == name:
            return layer
    for layer in psd.descendants():
        if layer.is_group() and name in layer.name:
            return layer
    sys.exit(f"グループが見つからない: {name!r}")


def _strip(s):
    return s.lstrip("*!").strip()


def find_layer(group, name):
    # PSDTool の接頭辞(*,!)を除いた完全一致を最優先。なければ部分一致。
    for layer in group:
        if _strip(layer.name) == name:
            return layer
    for layer in group:
        if name in layer.name:
            return layer
    sys.exit(f"口レイヤーが見つからない: {name!r}（グループ {group.name!r} 内）")


def full_canvas(layer, size):
    """レイヤー単体を、可視性を無視して実ピクセルで取り出し、
    PSD 全体サイズの透過キャンバスに正しい位置で配置する。"""
    img = layer.topil()
    if img is None:
        sys.exit(f"レイヤーにピクセルがない: {layer.name!r}")
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    canvas.alpha_composite(img.convert("RGBA"), (layer.left, layer.top))
    return canvas


def set_exclusive(group, chosen: str) -> None:
    """グループ直下で chosen のレイヤーだけ表示、他は非表示にする（PSDTool のラジオ相当）。"""
    for layer in group:
        layer.visible = (_strip(layer.name) == chosen)


def render_emotion_base(psd_path, size, mouth_group_name, groups, preset, out_path):
    """プリセットに従って 目/眉/顔色/記号 を切り替え、口を消した立ち絵を書き出す。
    PSD を読み直すことで他プリセットの状態を引きずらない。"""
    psd = PSDImage.open(psd_path)
    find_group(psd, mouth_group_name).visible = False  # 口は base に含めない
    for key, group_name in groups.items():
        if key == "口" or key not in preset:
            continue
        set_exclusive(find_group(psd, group_name), preset[key])
    psd.composite().save(out_path)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="立ち絵 PSD から vvlipsync 用素材を書き出す")
    p.add_argument("psd", help="PSD ファイルパス")
    p.add_argument("-o", "--out", required=True, help="出力ディレクトリ")
    p.add_argument("--map", default="", help="口マッピング JSON（省略時はずんだもん既定）")
    p.add_argument("--emotions", default="", help="感情プリセット JSON。指定すると base_<感情>.png を生成")
    args = p.parse_args(argv)

    mapping = DEFAULT_MAP
    if args.map:
        with open(args.map, encoding="utf-8") as f:
            mapping = json.load(f)

    import os
    os.makedirs(args.out, exist_ok=True)

    psd = PSDImage.open(args.psd)
    size = psd.size
    mouth_group_name = mapping["mouth_group"]
    group = find_group(psd, mouth_group_name)

    # 1) 母音6種の口を full-canvas 透過 PNG で書き出し
    for vowel, layer_name in mapping["mouths"].items():
        layer = find_layer(group, layer_name)
        out = os.path.join(args.out, f"{vowel}.png")
        full_canvas(layer, size).save(out)
        w, h = layer.bbox[2] - layer.bbox[0], layer.bbox[3] - layer.bbox[1]
        print(f"  {vowel:6s} <- {layer.name:12s} {w}x{h}  -> {out}")

    # 2) 口グループを隠した静止背景（PSD 既定の表情）
    group.visible = False
    psd.composite().save(os.path.join(args.out, "base.png"))
    print(f"  base   <- 口以外の合成（PSD既定の表情） -> base.png")

    # 3) 感情プリセットごとの base_<感情>.png
    if args.emotions:
        with open(args.emotions, encoding="utf-8") as f:
            cfg = json.load(f)
        groups = cfg["groups"]
        for name, preset in cfg["presets"].items():
            out = os.path.join(args.out, f"base_{name}.png")
            render_emotion_base(args.psd, size, mouth_group_name, groups, preset, out)
            face = " / ".join(f"{k}={preset[k]}" for k in ("目", "眉", "顔色", "記号") if k in preset)
            print(f"  base_{name}  voice={preset.get('voice','-')}  {face}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
