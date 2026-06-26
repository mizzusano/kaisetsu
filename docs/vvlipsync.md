# vvlipsync リファレンス

VOICEVOX の音声に口パクを合わせ、DaVinci Resolve にそのまま取り込める素材を生成する CLI。

| 出力 | 内容 | DaVinci での扱い |
|---|---|---|
| `frames/00000.png …` | 口パク＋表情の透過 PNG 連番（全身キャラ） | 画像シーケンス |
| `audio.wav` | 全セリフを連結した音声 | 音声トラック |
| `subtitles.srt` | セリフごとの字幕 | Subtitle 取り込み |

## 仕組み

口パクのタイミングは **VOICEVOX の `/audio_query` レスポンスに含まれるモーラ単位の母音と長さ（秒）** から直接求める。forced alignment や LAB ファイルは不要。

```
台本の各行ごとに:
  POST /audio_query  → モーラ列＋母音タイミング
  POST /synthesis    → 行の wav
全行を連結 → 通しタイムライン
  ├─ フレームごとに母音→口形を選び、base_<その行の感情>＋口 を合成して連番出力
  ├─ wav を連結（行間に無音、各行は算出秒数ぴったりに整える）
  └─ 行ごとに [開始→終了] テキストの SRT
```

## 前提

- **VOICEVOX ENGINE が起動している**こと（既定 `http://localhost:50021`）
  ```bash
  docker run --rm -p 50021:50021 voicevox/voicevox_engine:cpu-latest
  ```
- 口形 PNG が **6 枚**用意されていること（`a.png i.png u.png e.png o.png closed.png`）
- **各 PNG はフルキャンバスの透過画像**（口が正しい位置に置かれている）
- 表情つきにするなら `base_<感情>.png` を同じディレクトリに置く（→ [bake](bake.md)）

## インストール

### mise（推奨）

```bash
mise trust      # 初回のみ
mise install    # Python を用意
mise run setup  # .venv を作り vvlipsync を editable インストール
```

### mise を使わない場合

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[compose,psd]"
```

## 使い方

```bash
# 台本ファイル
vvlipsync 台本.txt -o out/ -m assets/zundamon/ -s 3 --fps 30

# テキスト直接（-t は複数回指定可）
vvlipsync -t "こんにちはなのだ" -o out/ -m assets/zundamon/ -s 3

# 感情つき
vvlipsync \
  -t "[3:喜び]やったーうれしいのだ" \
  -t "[3:怒り]むっ、怒ったのだ" \
  --emotions assets/zundamon/emotions.json \
  -m assets/zundamon/ -s 3 --fps 30 --preview -o out/

# 標準入力
echo "ぱいぷからなのだ" | vvlipsync -o out/ -m assets/zundamon/ -s 3
```

### オプション一覧

| オプション | 既定 | 説明 |
|---|---|---|
| `script` | — | 台本テキストファイル（1 行 = 1 セリフ） |
| `-t, --text` | — | セリフを直接指定（複数回指定可） |
| `-o, --out` | — | 出力ディレクトリ |
| `-m, --mouths` | — | 口形 PNG のディレクトリ |
| `-s, --speaker` | 1 | デフォルト話者ID |
| `--fps` | 30 | フレームレート（DaVinci と合わせる） |
| `--gap` | 0.3 | セリフ間の無音秒数 |
| `--speed` | 1.0 | 話速 speedScale |
| `--emotions` | — | 感情プリセット JSON |
| `-e, --emotion` | — | 感情名（声＋表情） |
| `--flip` | off | 左右反転（要 Pillow） |
| `--preview` | off | 確認用 mp4 も生成（要 ffmpeg） |
| `--bg` | white | プレビュー背景色 |
| `--intonation` | — | 抑揚（intonationScale） |
| `--pitch` | — | 音高（pitchScale） |
| `--volume` | — | 音量（volumeScale） |
| `--host` | `http://localhost:50021` | VOICEVOX ENGINE の URL |
| `--config` | — | 口形ファイル名を変える JSON |

### 台本フォーマット

```
こんにちは、ずんだもんなのだ
[3] 行頭の [n] で話者IDを上書き
[3:喜び] 話者IDと感情を同時に指定
# '#' 始まりはコメント、空行は無視
```

話者ID は `vvlipsync --list-speakers` または `GET http://localhost:50021/speakers` で確認。

## 感情（声＋表情）

感情は VOICEVOX のスタイル（声）と PSD の表情レイヤー（目・眉・顔色）を束ねたプリセット。

```bash
# 感情つき base を bake 済みであること（→ docs/bake.md）

vvlipsync -t "やったーなのだ" -e 喜び --emotions assets/zundamon/emotions.json \
    -o out/ -m assets/zundamon/ -s 3 --preview
```

- `base_<感情>.png` が無い感情は `base.png` にフォールバック
- base が一切無ければ口だけの連番になる（Pillow 不要）

対応キャラ:

| キャラ | ディレクトリ | 話者ID |
|---|---|---|
| ずんだもん | `assets/zundamon/` | 3 |
| 四国めたん | `assets/metan/` | 2 |

感情: `通常 / 喜び / 怒り / 悲しみ / 驚き / 照れ`

## 確認用プレビュー動画

```bash
# 生成と同時に作る
vvlipsync 台本.txt -o out/ -m assets/zundamon/ -s 3 --preview

# 既存の出力から後出し
vvlipsync-preview out/ --fps 30
```

出力は `out/preview.mp4`（チェック用、最終成果物ではない）。

## DaVinci Resolve への取り込み

1. **プロジェクトのフレームレートを `--fps` と一致させる**（ずれると同期が狂う）
2. `frames/` を画像シーケンスとして取り込む
   - 環境設定 → 一般 → 「シーケンスを単一クリップとして読み込む」を ON
   - ドラッグするだけで全身キャラ透過連番が 1 クリップになる
3. `audio.wav` を取り込み、画像シーケンスと**先頭を 0 に揃えて**配置
4. `subtitles.srt` を取り込む（字幕トラックへ）
5. 背景は連番の下のトラックに置く（連番は透過）

## 制限・メモ

- 口形は母音ベースの近似（`m/p/b` の閉唇などは厳密には再現しない）
- 連番 PNG は（感情×口形）ごとに実体 1 枚のみ、残りはハードリンクで使い回す
- base 画像との合成にのみ Pillow が必要
