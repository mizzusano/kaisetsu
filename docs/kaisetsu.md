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
| `--timeline` | off | DaVinci 取り込み用のタイムライン（`timeline/timeline.fcpxml`＋素材）も書き出す |
| `--timeline-only` | off | タイムラインだけ書き出す（完成 mp4 の合成を省く） |

```bash
# BGM つき
kaisetsu 入力.md -o build_out/ --bgm bgm.mp3
kaisetsu 入力.md -o build_out/ --bgm intro.mp4 --bgm-volume 0.12
```

出力 `build_out/`: `script.json`（生成台本）、スライド/クリップ中間物、`video.mp4`（完成動画）。

## DaVinci Resolve で編集する（`--timeline`）

完成 mp4 の代わりに（または加えて）、**DaVinci で編集できるタイムライン**を書き出す。

```bash
kaisetsu --script 台本.json -o build_out/ --timeline-only --bgm bgm.mp3
```

`build_out/timeline/`:

| ファイル | 中身 |
|---|---|
| `timeline.fcpxml` | タイムライン本体（DaVinci: ファイル → 読み込み → タイムライン） |
| `metan.mov` / `zundamon.mov` | キャラごとの全尺透過トラック（ProRes 4444。完成動画と同じ位置に配置済み） |
| `subtitles.srt` | 通しの字幕（字幕トラックに読み込む） |
| `bgm.wav` | `--bgm` 指定時。全尺ぶんにループ済み（音量は FCPXML 側で下げてある） |

トラック構成: V1=スライド/章扉（静止画）、V2=めたん、V3=ずんだもん、A1=セリフ（1 セリフ 1 クリップ）、A2=BGM。

- キャラは 1920x1080 の透過キャンバス上に配置済みなので、読み込んだ時点で完成動画と同じ見た目になる。
  位置・大きさは DaVinci のインスペクタで後から変えられる。
- セリフ音声は各 `seg_*/audio.wav` を参照するので、`build_out/` を移動・削除しないこと。
- 透過トラックは容量が大きい（キャラ 1 人あたり約 10MB/秒）。

## 画像を見せる（台本の `images`）

スライドに図やスクリーンショットを出したいときは、台本 JSON に画像を定義する。
画像は「ヘッダー＋キャプション＋画像（左右のキャラと下の字幕帯を避けて中央に収める）」の背景になる。

```json
{
  "heading": "オントロジーとは何なのか",
  "bullets": ["…"],
  "images": {
    "core": {"src": "images/core.png", "caption": "3 層の構成", "credit": "出典: Palantir"},
    "top":  {"src": "images/table.png", "crop": [0, 0, 1534, 590], "caption": "表の上半分"}
  },
  "image": "core",
  "dialogue": [
    {"speaker": "metan", "emotion": "通常", "text": "まずこの図を見て。"},
    {"speaker": "metan", "emotion": "通常", "text": "次は表よ。", "image": "top"},
    {"speaker": "zundamon", "emotion": "通常", "text": "箇条書きに戻すのだ。", "image": null}
  ]
}
```

| キー | 説明 |
|---|---|
| `images.<キー>.src` | 画像ファイル。台本 JSON のあるディレクトリからの相対パス（絶対パスも可） |
| `images.<キー>.caption` / `credit` | 画像の上の説明 / 右下の出典（任意） |
| `images.<キー>.crop` | `[x0, y0, x1, y1]`（元画像のピクセル）。縦長の表などを分けて拡大したい時に |
| `image`（スライド） | スライド冒頭に出す画像のキー。省略時は箇条書き |
| `image`（セリフ） | そのセリフから表示を切り替える。`null` で箇条書きに戻る。書かないセリフは直前の表示を引き継ぐ |

- 未定義のキーや存在しないファイルは、合成を始める前にエラーで止まる。
- 字幕が 3 行になると画像の下端にかかるので、セリフは字幕 2 行（話者名込みで 60 字弱）に収めるとよい。
- Gemini で台本を生成する経路は画像を扱わない（台本 JSON を手で書く / 編集するときに使う）。

## 途中で止まった時・ディスク使用量

- 各セリフのクリップ（`clip_NNN.mp4`）を書き出すと、そのセグメントの PNG 連番は消す
  （1 セグメント数百 MB になるため）。`--timeline` 指定時はタイムライン書き出しに使うので残す。
- 完成したセグメントには `seg_NNN/segment.json` が残る。**途中で止まったら同じコマンドを再実行**すれば、
  完成済みのセグメントは作り直さずに使う。
- 一部だけ作り直したい時は、該当セグメントの `clip_NNN.mp4` と `seg_NNN/segment.json` を消してから再実行する。
- 箇条書きが字幕帯にかかるスライドは、生成時に `[警告]` を出す（中央カラムは 1 行 約 14 字。1 項目 14 字前後・5 項目までが目安）。

## 構成・テンポ

- **タイトルコール（章扉）**: 段落の頭に見出しを大きく出したフルスクリーンカードを表示し、announcer が読み上げる。`--no-title-call` で無効化。
- **「間」**: 各セリフ・章扉の前後に少しの無音＋フレーム保持を入れてテンポを整える。
- **体の動き**: 話し手は感情ごとのモーション、聞き手もふわふわ呼吸する（→ [vvlipsync](vvlipsync.md#体の動きとポーズ)）。

## メモ

- 役割: めたん＝解説役、ずんだもん＝聞き役（`src/kaisetsu/gemini.py` のプロンプトで規定。台本 JSON を手で編集してもよい）
- 感情は `assets/*/emotions.json` の 6 種から選ばれ表情に反映される
- まず `--script examples/kaisetsu_sample_script.json` で Gemini なしに合成パイプラインだけ試せる
