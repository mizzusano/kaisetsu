"""台本(JSON) → 解説動画 のオーケストレーション。

各セリフごとに vvlipsync でキャラ素材（口パク連番＋音声）を作り、スライド背景・
聞き手・字幕と合成。全クリップを連結して 1 本の mp4 にする。
"""

from __future__ import annotations

import os

from vvlipsync.cli import main as vvmain

from .compose import CHAR_NATIVE, add_bgm, compose_line, concat_clips, render_subtitle
from .slides import render_slide, render_title_card

CHAR_HEIGHT = 680  # 立ち絵の表示高さ(px)


def _body_margin(size):
    """立ち絵幅に合わせ、本文を中央カラムに収めるマージンを返す。"""
    cw = round(CHAR_NATIVE[0] * CHAR_HEIGHT / CHAR_NATIVE[1])
    m = cw + 60
    return (m, m)

# 左=四国めたん / 右=ずんだもん。素の立ち絵が めたん=画面右向き・ずんだもん=画面左向き
# なので、この配置なら反転なしで互いに内向き（向き合う）になる。
CHARACTERS = [
    {"name": "metan", "dir": "metan", "speaker": 2, "flip": False, "label": "四国めたん"},
    {"name": "zundamon", "dir": "zundamon", "speaker": 3, "flip": False, "label": "ずんだもん"},
]
LISTENER_EMOTION = "通常"


def _listener_image(char_dir: str, cache_dir: str) -> str:
    """聞き手（喋っていない側）の静止画 = base_通常 ＋ 閉じ口 を合成してキャッシュする。
    base はマウスを抜いた立ち絵なので、closed.png を重ねて口を結ばせる。"""
    out = os.path.join(cache_dir, f"_listener_{os.path.basename(char_dir)}.png")
    if os.path.isfile(out):
        return out
    from PIL import Image
    base = None
    for c in (f"base_{LISTENER_EMOTION}.png", "base.png"):
        p = os.path.join(char_dir, c)
        if os.path.isfile(p):
            base = p
            break
    if base is None:
        raise SystemExit(f"聞き手の立ち絵が無い: {char_dir}")
    img = Image.open(base).convert("RGBA").copy()
    closed = os.path.join(char_dir, "closed.png")
    if os.path.isfile(closed):
        img.alpha_composite(Image.open(closed).convert("RGBA"))
    img.save(out)
    return out


def _render_segment(idx, bg_png, speaker, emotion, text, *, out_dir, assets_root,
                    fps, size, char_by_name, head, tail, subtitle=True,
                    show_characters=True) -> str:
    """1 セグメント（タイトルコール or 1 セリフ）を 1 クリップに合成する。
    show_characters=False ならキャラを出さず、音声のみのナレーション（章扉向け）。"""
    if speaker not in char_by_name:
        raise SystemExit(f"未知の話者: {speaker}")
    spk = char_by_name[speaker]
    spk_dir = os.path.join(assets_root, spk["dir"])
    seg_dir = os.path.join(out_dir, f"seg_{idx:03d}")

    argv = ["-t", text, "-e", emotion,
            "--emotions", os.path.join(spk_dir, "emotions.json"),
            "-m", spk_dir, "-s", str(spk["speaker"]),
            "--fps", str(fps), "-o", seg_dir]
    if spk["flip"]:
        argv.append("--flip")
    vvmain(argv)

    sub_png = ""
    if subtitle:
        sub_png = os.path.join(seg_dir, "sub.png")
        render_subtitle(f"{spk['label']}「{text}」", sub_png, size)

    slots = []
    if show_characters:
        for c in CHARACTERS:
            if c["name"] == speaker:
                slots.append({"kind": "seq", "path": os.path.join(seg_dir, "frames")})
            else:
                base = _listener_image(os.path.join(assets_root, c["dir"]), out_dir)
                slots.append({"kind": "img", "path": base, "flip": c["flip"]})

    clip = os.path.join(out_dir, f"clip_{idx:03d}.mp4")
    compose_line(bg_png, slots, sub_png, os.path.join(seg_dir, "audio.wav"),
                 clip, fps, size, char_height=CHAR_HEIGHT, head=head, tail=tail)
    return clip


def build_video(script: dict, out_dir: str, assets_root: str,
                fps: float = 30.0, size=(1920, 1080),
                bgm: str = "", bgm_volume: float = 0.18,
                title_call: bool = True, announcer: str = "zundamon") -> str:
    os.makedirs(out_dir, exist_ok=True)
    char_by_name = {c["name"]: c for c in CHARACTERS}
    common = dict(out_dir=out_dir, assets_root=assets_root, fps=fps, size=size,
                  char_by_name=char_by_name)

    clips = []
    seg = 0
    for si, slide in enumerate(script["slides"]):
        heading = slide["heading"]
        slide_png = os.path.join(out_dir, f"slide_{si:02d}.png")
        render_slide(heading, slide.get("bullets", []), slide_png, size,
                     body_margin=_body_margin(size))

        # 段落（スライド）の頭にタイトルコール: タイトルカード＋見出しを読み上げ
        if title_call:
            tc_png = os.path.join(out_dir, f"title_{si:02d}.png")
            render_title_card(heading, tc_png, size, index=si + 1)
            print(f"[title {si + 1}] {heading}")
            clips.append(_render_segment(seg, tc_png, announcer, "喜び", heading,
                                         head=0.5, tail=0.8, subtitle=False,
                                         show_characters=False, **common))
            seg += 1

        dialogue = slide["dialogue"]
        for j, dl in enumerate(dialogue):
            head = 0.2 if j == 0 else 0.12
            tail = 0.55 if j == len(dialogue) - 1 else 0.28
            print(f"[seg {seg}] {char_by_name[dl['speaker']]['label']}/{dl['emotion']}: {dl['text']}")
            clips.append(_render_segment(seg, slide_png, dl["speaker"], dl["emotion"],
                                         dl["text"], head=head, tail=tail, **common))
            seg += 1

    final = os.path.join(out_dir, "video.mp4")
    if bgm:
        concat = os.path.join(out_dir, "_video_nobgm.mp4")
        concat_clips(clips, concat)
        print(f"BGM をミックス中（音量 {bgm_volume}）: {bgm}")
        add_bgm(concat, bgm, final, volume=bgm_volume)
    else:
        concat_clips(clips, final)
    return final
