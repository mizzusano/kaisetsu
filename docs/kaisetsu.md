# kaisetsu リファレンス

markdown（または任意テキスト）を**ずんだもん×四国めたんの掛け合い解説動画**にする CLI。

```
markdown
  └─[Gemini]→ 台本JSON（スライド毎: 見出し・箇条書き・掛け合い[話者/感情/セリフ]）
        ├─ スライド画像（PIL）
        ├─ 各セリフ → vvlipsync で口パク連番＋音声＋感情表情
        └─ ffmpeg 合成: スライド背景 ＋ ずんだもん(左) ＋ めたん(右) ＋ 字幕 ＋ 音声
              → 連結して解説動画 mp4
```

## 前提

- VOICEVOX ENGINE 起動（`http://localhost:50021`）・ffmpeg
- Gemini API キー（`.env` に `GEMINI_API_KEY=...`）
- キャラ素材を bake 済み（→ [bake.md](bake.md)）

## 使い方

```bash
# markdown ファイルから
kaisetsu 入力.md -o build_out/

# 任意のテキストを直接指定（Gemini で markdown に整理してから動画化）
kaisetsu -t "TCPはコネクション型で…UDPは…" -o build_out/

# テキストファイル（.md 以外は整理対象、.md はそのまま使う）
kaisetsu memo.txt -o build_out/

# 台本 JSON を直接指定（Gemini をスキップ。合成パイプラインだけ試したいとき）
kaisetsu --script 台本.json -o build_out/
kaisetsu --script examples/kaisetsu_sample_script.json -o build_out/
```

処理フロー:
```
生テキスト ─[Gemini]→ 構造化 markdown ─[Gemini]→ 台本 JSON ─→ 動画
   .md ファイルは最初の整理段階をスキップ
```

### オプション一覧

| オプション | 既定 | 説明 |
|---|---|---|
| `input` | — | 入力ファイル（`.md` はそのまま、他は整理してから使う） |
| `-t, --text` | — | 文章を直接指定 |
| `-o, --out` | `build_out` | 出力ディレクトリ |
| `--script` | — | 台本 JSON を直接指定（Gemini をスキップ） |
| `--assets-root` | `assets` | キャラ素材ルート（`zundamon/` `metan/` を含む） |
| `--model` | `gemini-2.5-flash` | Gemini モデル |
| `--fps` | 30 | フレームレート |
| `--bgm` | — | BGM ファイル（mp3 / mp4）。動画全体に小音量でミックス（短ければループ） |
| `--bgm-volume` | 0.18 | BGM の音量倍率 |
| `--no-title-call` | — | 段落頭のタイトルコール（章扉）を無効化 |
| `--announcer` | `zundamon` | タイトルコールを読む話者（zundamon / metan） |

```bash
# BGM つき
kaisetsu 入力.md -o build_out/ --bgm bgm.mp3
kaisetsu 入力.md -o build_out/ --bgm intro.mp4 --bgm-volume 0.12
```

出力 `build_out/`: `script.json`（生成台本）、スライド/クリップ中間物、`video.mp4`（完成動画）。

## 構成・テンポ

- **タイトルコール（章扉）**: 段落の頭に見出しを大きく出したフルスクリーンカードを表示し、announcer が読み上げる。`--no-title-call` で無効化。
- **「間」**: 各セリフ・章扉の前後に少しの無音＋フレーム保持を入れてテンポを整える。

## メモ

- 役割: めたん＝解説役、ずんだもん＝聞き役（`src/kaisetsu/gemini.py` のプロンプトで規定。台本 JSON を手で編集してもよい）
- 感情は `assets/*/emotions.json` の 6 種から選ばれ表情に反映される
- まず `--script examples/kaisetsu_sample_script.json` で Gemini なしに合成パイプラインだけ試せる
