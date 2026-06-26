# 立ち絵素材の準備（bake）

口形・表情 PNG は PSD から確定論的に生成する。著作物のため PSD 自体はリポジトリに含めない。

## 対応素材

- ずんだもん立ち絵素材2.3 / 四国めたん立ち絵素材2.1（作: 坂本アヒル）
  - ずんだもん: <https://www.pixiv.net/artworks/92641379>
  - 四国めたん: <https://www.pixiv.net/artworks/92641351>
- 利用は各素材の readme / 公式ガイドラインに従うこと。

## 手順

1. PSD をダウンロードして `assets/` に置く

   | キャラ | 既定ファイル名 |
   |---|---|
   | ずんだもん | `tmp/ずんだもん立ち絵素材2.3.psd` |
   | 四国めたん | `tmp/四国めたん立ち絵素材2.1.psd` |

2. bake を実行

   ```bash
   mise run bake

   # PSD の場所を指定する場合
   ZUNDA_PSD=/path/to/zunda.psd METAN_PSD=/path/to/metan.psd mise run bake
   ```

3. 生成されるファイル（`.gitignore` 済み）

   ```
   assets/zundamon/
   assets/metan/
     a.png i.png u.png e.png o.png closed.png  ← 口6種（フルキャンバス透過）
     base.png                                   ← 通常立ち絵（口なし）
     base_通常.png base_喜び.png base_怒り.png …  ← 感情別立ち絵
   ```

## 別キャラを追加する

1. PSD のレイヤー名を確認する

   ```python
   from psd_tools import PSDImage
   for l in PSDImage.open("立ち絵.psd").descendants():
       print(l.name)
   ```

2. `mouth_map.json` を作成（口グループ名と母音マッピング）

   ```json
   {
     "mouth_group": "口",
     "mouths": {
       "a": "ほあー", "i": "んへー", "u": "ゆ",
       "e": "はへえ", "o": "お", "closed": "んー"
     }
   }
   ```

3. `emotions.json` を作成（感情プリセット）

4. 手動で抽出

   ```bash
   python tools/psd_extract.py 立ち絵.psd -o assets/mychar/ \
     --map assets/mychar/mouth_map.json \
     --emotions assets/mychar/emotions.json
   ```

## emotions.json の構造

`assets/zundamon/emotions.json` を参考に。`groups` でレイヤーグループ名を定義し、`presets` で感情ごとのレイヤー選択を指定する。

```json
{
  "groups": { "目": "目", "眉": "眉", "顔色": "顔色" },
  "presets": {
    "通常": { "voice": "ノーマル", "目": "通常", "眉": "通常", "顔色": "通常" },
    "喜び": { "voice": "あまあま",  "目": "笑い", "眉": "喜び", "顔色": "通常" }
  }
}
```

`voice` は VOICEVOX のスタイル名（`vvlipsync --list-speakers` で確認）。
