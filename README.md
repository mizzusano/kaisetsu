# vvlipsync / kaisetsu

このリポジトリは 2 つの CLI を含む。

| CLI | 概要 |
|---|---|
| **vvlipsync** | VOICEVOX の音声に口パク・表情を合わせた DaVinci 用素材を生成する低レベルツール |
| **kaisetsu** | markdown をずんだもん×四国めたんの掛け合い解説動画にする上位ツール |

## ドキュメント

- [vvlipsync リファレンス](docs/vvlipsync.md) — 使い方・オプション・DaVinci 取り込み手順
- [kaisetsu リファレンス](docs/kaisetsu.md) — 使い方・オプション
- [立ち絵素材の準備（bake）](docs/bake.md) — PSD から口形・表情 PNG を生成する手順

## クイックスタート

前提: VOICEVOX ENGINE 起動済み・[インストール済み](docs/vvlipsync.md#インストール)・[素材 bake 済み](docs/bake.md)

```bash
# 感情つきでセリフを渡し、プレビュー動画と DaVinci 取り込みファイルを生成
vvlipsync \
  -t "[3:喜び]やったー、今日はいい天気なのだ" \
  --emotions assets/zundamon/emotions.json \
  -m assets/zundamon/ -s 3 --fps 30 --preview -o out/

# kaisetsu: markdown から解説動画を生成（Gemini API キー必要）
kaisetsu 入力.md -o build_out/
kaisetsu --script examples/kaisetsu_sample_script.json -o build_out/  # Gemini なし
```

出力 `out/`:

```
frames/        表情つき全身キャラの透過連番  ← DaVinci 画像シーケンス
audio.wav      音声                        ← 音声トラック
subtitles.srt  字幕                        ← 字幕トラック
preview.mp4    確認用（--preview 時のみ）
```

## 立ち絵素材について

立ち絵 PNG はリポジトリに含まない（著作物のため）。PSD をダウンロードして `mise run bake` で生成する（→ [bake.md](docs/bake.md)）。

- ずんだもん立ち絵素材2.3 / 四国めたん立ち絵素材2.1（作: 坂本アヒル）
