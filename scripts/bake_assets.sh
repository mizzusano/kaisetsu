#!/usr/bin/env bash
#
# 立ち絵 PSD から vvlipsync / kaisetsu 用の素材（口6種・base・感情別 base）を
# 確定論的に再生成する。
#
# 立ち絵 PSD は著作物のためこのリポジトリには含めない。各自ダウンロードして配置すること:
#   - ずんだもん立ち絵素材2.3     （作: 坂本アヒル）
#   - 四国めたん立ち絵素材2.1     （作: 坂本アヒル）
# 利用は各素材の readme / 公式ガイドラインに従う。
#
# 使い方:
#   mise run bake                       # 既定パス（assets/*.psd）から再生成
#   ZUNDA_PSD=/path/zunda.psd METAN_PSD=/path/metan.psd mise run bake
#   bash scripts/bake_assets.sh         # mise 無しでも可（venv 有効化済みなら）
#
# リポジトリに含まれるのは設定 JSON（mouth_map.json / emotions.json）のみ。
# 生成される PNG は .gitignore 済みでコミットされない。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python}"

ZUNDA_PSD="${ZUNDA_PSD:-$ROOT/tmp/ずんだもん立ち絵素材2.3.psd}"
METAN_PSD="${METAN_PSD:-$ROOT/tmp/四国めたん立ち絵素材2.1.psd}"

bake() {  # <psd> <out_dir>
  local psd="$1" out="$2"
  if [ ! -f "$psd" ]; then
    echo "PSD が見つからない: $psd" >&2
    echo "  → 立ち絵 PSD をダウンロードして配置するか、ZUNDA_PSD / METAN_PSD で指定する" >&2
    exit 1
  fi
  "$PY" "$ROOT/tools/psd_extract.py" "$psd" -o "$out" \
    --map "$out/mouth_map.json" \
    --emotions "$out/emotions.json"
}

echo "== ずんだもん =="
bake "$ZUNDA_PSD" "$ROOT/assets/zundamon"
echo "== 四国めたん =="
bake "$METAN_PSD" "$ROOT/assets/metan"
echo "完了: assets/zundamon, assets/metan に素材を再生成した"
