"""台本(JSON) → 解説動画 のオーケストレーション。

各セリフごとに vvlipsync でキャラ素材（口パク連番＋音声）を作り、スライド背景・
聞き手・字幕と合成。全クリップを連結して 1 本の mp4 にする。
"""

from __future__ import annotations

import json
import os
import shutil
import wave

from vvlipsync.cli import _build_base_paths, resolve_mouth_paths
from vvlipsync.cli import main as vvmain
from vvlipsync.motion import motion_at
from vvlipsync.render import write_frames

from . import timeline as tl
from .compose import (CHAR_EDGE, CHAR_NATIVE, SPEAKER_COLORS, SUBTITLE_BAND_H, add_bgm,
                      compose_line, concat_clips, render_subtitle, slot_positions)
from .reading import apply_readings, line_reading
from .slides import (line_visuals, render_image_slide, render_slide, render_title_card,
                     resolve_images)

CHAR_HEIGHT = 860  # 立ち絵の表示高さ(px)。下は画面外に出す（compose.CHAR_CUT）
DEFAULT_SPEED = 1.15  # 話速 speedScale。VOICEVOX 既定の 1.0 は解説動画には少しゆっくり
SUBTITLE_TOP = 1080 - SUBTITLE_BAND_H  # 字幕帯の上端(px, 1080p)


def _body_margin(size):
    """立ち絵幅に合わせ、本文を中央カラムに収めるマージンを返す。"""
    cw = round(CHAR_NATIVE[0] * CHAR_HEIGHT / CHAR_NATIVE[1])
    m = cw + CHAR_EDGE + 20
    return (m, m)

# 左=四国めたん / 右=ずんだもん。素の立ち絵が めたん=画面右向き・ずんだもん=画面左向き
# なので、この配置なら反転なしで互いに内向き（向き合う）になる。
CHARACTERS = [
    {"name": "metan", "dir": "metan", "speaker": 2, "flip": False, "label": "四国めたん"},
    {"name": "zundamon", "dir": "zundamon", "speaker": 3, "flip": False, "label": "ずんだもん"},
]
LISTENER_EMOTION = "通常"


def _listener_frames(char_dir: str, n_frames: int, fps: float, t_offset: float,
                     out_dir: str, flip: bool) -> str:
    """聞き手（喋っていない側）の連番 = base_通常 ＋ 閉じ口 に、ふわふわ呼吸だけを付ける。
    t_offset は通し時刻。話者と同じ時計で呼吸させ、クリップを跨いでも位相が途切れないようにする。"""
    base_paths = _build_base_paths(char_dir, {LISTENER_EMOTION})
    if not any(base_paths.values()):
        raise SystemExit(f"聞き手の立ち絵が無い: {char_dir}")
    mouth_paths = resolve_mouth_paths(char_dir, "")
    specs = [((LISTENER_EMOTION, 0), "closed")] * n_frames
    tfs = [motion_at(LISTENER_EMOTION, (i + 0.5) / fps, t_offset + (i + 0.5) / fps)
           for i in range(n_frames)]
    write_frames(specs, mouth_paths, base_paths, out_dir, flip=flip, transforms=tfs)
    return out_dir


DONE_MARKER = "segment.json"  # セグメント完成の印（途中から再開する時に使う）


def _mark_done(seg_dir: str, n_frames: int, **speech) -> None:
    """speech にはセリフ・話者・感情・話速を入れておき、変わっていたら再利用しない。"""
    with open(os.path.join(seg_dir, DONE_MARKER), "w", encoding="utf-8") as f:
        json.dump({"n_frames": n_frames, **speech}, f, ensure_ascii=False)


def _load_done(seg_dir: str):
    try:
        with open(os.path.join(seg_dir, DONE_MARKER), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _drop_frames(seg_dir: str) -> None:
    """クリップ mp4 に焼き込んだあとの PNG 連番を消す（1 セグメント数百 MB になるため）。"""
    for name in os.listdir(seg_dir):
        if name == "frames" or name.startswith("listener_"):
            shutil.rmtree(os.path.join(seg_dir, name), ignore_errors=True)


def _wav_seconds(path: str) -> float:
    with wave.open(path) as w:
        return w.getnframes() / w.getframerate()


def _render_segment(idx, bg_png, speaker, emotion, text, *, out_dir, assets_root,
                    fps, size, char_by_name, head, tail, clock, subtitle=True,
                    show_characters=True, render_clip=True, keep_frames=True,
                    speed=DEFAULT_SPEED, yomi=None):
    """1 セグメント（タイトルコール or 1 セリフ）を 1 クリップに合成する。
    show_characters=False ならキャラを出さず、音声のみのナレーション（章扉向け）。
    clock は通し時刻（秒）を持つ 1 要素リスト。呼吸の位相に使い、クリップ尺だけ進める。
    (クリップ mp4 のパス or None, タイムライン用の Segment) を返す。
    render_clip=False ならクリップ mp4 の合成を省く（タイムラインだけ欲しい時）。
    keep_frames=False ならクリップを書き出した後に PNG 連番を消す（タイムラインには要る）。
    完成の印があるセグメントは作り直さずに使う（途中で止まった時の再開用）。"""
    if speaker not in char_by_name:
        raise SystemExit(f"未知の話者: {speaker}")
    spk = char_by_name[speaker]
    spk_dir = os.path.join(assets_root, spk["dir"])
    seg_dir = os.path.join(out_dir, f"seg_{idx:03d}")
    clip_path = os.path.join(out_dir, f"clip_{idx:03d}.mp4")
    audio = os.path.join(seg_dir, "audio.wav")

    yomi = yomi or text  # 読み上げる文（字幕は text のまま）
    speech = dict(text=text, yomi=yomi, speaker=speaker, emotion=emotion, speed=speed)
    done = _load_done(seg_dir)
    if done and "yomi" not in done:
        done = dict(done, yomi=done.get("text"))  # 読みを記録する前の印は、読み＝表記だった
    if done and any(done.get(k) != v for k, v in speech.items()):
        done = None  # セリフや話速が変わったので作り直す
    frames_ok = not keep_frames or os.path.isdir(os.path.join(seg_dir, "frames"))
    if done and frames_ok and os.path.isfile(audio) and (not render_clip or os.path.isfile(clip_path)):
        print(f"  （作成済みを再利用: seg_{idx:03d}）")
        audio_sec = _wav_seconds(audio)
        clock[0] += head + audio_sec + tail
        info = tl.Segment(bg_png=bg_png, speaker=speaker, label=spk["label"], text=text,
                          seg_dir=seg_dir, n_frames=done["n_frames"], head=head, tail=tail,
                          audio=audio, audio_seconds=audio_sec, subtitle=subtitle,
                          show_characters=show_characters)
        return (clip_path if render_clip else None), info

    argv = ["-t", yomi, "-e", emotion,
            "--emotions", os.path.join(spk_dir, "emotions.json"),
            "-m", spk_dir, "-s", str(spk["speaker"]),
            "--fps", str(fps), "-o", seg_dir,
            "--motion-offset", str(clock[0] + head), "--speed", str(speed)]
    if spk["flip"]:
        argv.append("--flip")
    vvmain(argv)

    sub_png = ""
    if subtitle and render_clip:
        sub_png = os.path.join(seg_dir, "sub.png")
        render_subtitle(text, sub_png, size, color=SPEAKER_COLORS.get(speaker, (60, 60, 60)))

    slots = []
    frames_dir = os.path.join(seg_dir, "frames")
    n_frames = len([f for f in os.listdir(frames_dir) if f.endswith(".png")])
    if show_characters:
        for c in CHARACTERS:
            if c["name"] == speaker:
                slots.append({"kind": "seq", "path": frames_dir})
            else:
                lis = _listener_frames(os.path.join(assets_root, c["dir"]), n_frames, fps,
                                       clock[0] + head, os.path.join(seg_dir, f"listener_{c['name']}"),
                                       c["flip"])
                slots.append({"kind": "seq", "path": lis})

    clip = None
    if render_clip:
        clip = clip_path
        compose_line(bg_png, slots, sub_png, audio,
                     clip, fps, size, char_height=CHAR_HEIGHT, head=head, tail=tail)
    _mark_done(seg_dir, n_frames, **speech)
    if render_clip and not keep_frames:
        _drop_frames(seg_dir)
    audio_sec = _wav_seconds(audio)
    clock[0] += head + audio_sec + tail
    info = tl.Segment(bg_png=bg_png, speaker=speaker, label=spk["label"], text=text,
                      seg_dir=seg_dir, n_frames=n_frames, head=head, tail=tail, audio=audio,
                      audio_seconds=audio_sec, subtitle=subtitle, show_characters=show_characters)
    return clip, info


def build_video(script: dict, out_dir: str, assets_root: str,
                fps: float = 30.0, size=(1920, 1080),
                bgm: str = "", bgm_volume: float = 0.18,
                title_call: bool = True, announcer: str = "zundamon",
                timeline: bool = False, video: bool = True, base_dir: str = ".",
                speed: float = DEFAULT_SPEED) -> str:
    """解説動画を作る。timeline=True なら DaVinci 取り込み用の timeline/ も書き出す。
    video=False なら完成 mp4 の合成を省く（timeline のみ）。完成物のパスを返す。
    base_dir は台本内の画像パス（images[].src）の基準ディレクトリ。"""
    os.makedirs(out_dir, exist_ok=True)
    char_by_name = {c["name"]: c for c in CHARACTERS}
    # 画像の指定ミスは、重い合成を始める前に止める
    for slide in script["slides"]:
        line_visuals(slide)
        resolve_images(slide, base_dir)
    common = dict(out_dir=out_dir, assets_root=assets_root, fps=fps, size=size,
                  char_by_name=char_by_name, clock=[0.0], render_clip=video,
                  keep_frames=timeline, speed=speed)

    readings = script.get("readings") or {}
    clips = []
    segments = []
    seg = 0
    for si, slide in enumerate(script["slides"]):
        heading = slide["heading"]
        slide_png = os.path.join(out_dir, f"slide_{si:02d}.png")
        bottom = render_slide(heading, slide.get("bullets", []), slide_png, size,
                              body_margin=_body_margin(size))
        if bottom > SUBTITLE_TOP:
            print(f"[警告] スライド「{heading}」の箇条書きが字幕帯にかかる"
                  f"（下端 y={bottom}）。箇条書きを短く・少なくする")
        # 台本で画像が指定されていれば、画像ごとの背景も描いておく
        visuals = line_visuals(slide)
        images = resolve_images(slide, base_dir)
        bg_by_key = {None: slide_png}
        for key in dict.fromkeys(v for v in visuals if v is not None):
            spec = images[key]
            png = os.path.join(out_dir, f"slide_{si:02d}_{key}.png")
            render_image_slide(heading, spec["src"], png, size,
                               caption=spec.get("caption", ""), credit=spec.get("credit", ""),
                               crop=spec.get("crop"))
            bg_by_key[key] = png

        # 段落（スライド）の頭にタイトルコール: タイトルカード＋見出しを読み上げ
        if title_call:
            tc_png = os.path.join(out_dir, f"title_{si:02d}.png")
            render_title_card(heading, tc_png, size, index=si + 1)
            print(f"[title {si + 1}] {heading}")
            clip, info = _render_segment(seg, tc_png, announcer, "喜び", heading,
                                         yomi=slide.get("heading_yomi")
                                         or apply_readings(heading, readings),
                                         head=0.5, tail=0.8, subtitle=False,
                                         show_characters=False, **common)
            clips.append(clip)
            segments.append(info)
            seg += 1

        dialogue = slide["dialogue"]
        for j, dl in enumerate(dialogue):
            head = 0.2 if j == 0 else 0.12
            tail = 0.55 if j == len(dialogue) - 1 else 0.28
            print(f"[seg {seg}] {char_by_name[dl['speaker']]['label']}/{dl['emotion']}: {dl['text']}")
            clip, info = _render_segment(seg, bg_by_key[visuals[j]], dl["speaker"], dl["emotion"],
                                         dl["text"], yomi=line_reading(dl, readings),
                                         head=head, tail=tail, **common)
            clips.append(clip)
            segments.append(info)
            seg += 1

    result = ""
    if timeline:
        result = export_timeline(segments, out_dir, fps, size, script.get("title") or "kaisetsu",
                                 bgm=bgm, bgm_volume=bgm_volume)
    if not video:
        return result

    final = os.path.join(out_dir, "video.mp4")
    if bgm:
        concat = os.path.join(out_dir, "_video_nobgm.mp4")
        concat_clips(clips, concat)
        print(f"BGM をミックス中（音量 {bgm_volume}）: {bgm}")
        add_bgm(concat, bgm, final, volume=bgm_volume)
    else:
        concat_clips(clips, final)
    return final


def export_timeline(segments, out_dir: str, fps: float, size, title: str,
                    bgm: str = "", bgm_volume: float = 0.18) -> str:
    """DaVinci 取り込み用の素材一式を out_dir/timeline/ に書き出し、FCPXML のパスを返す。"""
    from PIL import Image

    tdir = os.path.join(out_dir, "timeline")
    os.makedirs(tdir, exist_ok=True)
    placements = tl.place(segments, fps)
    total = sum(p.total for p in placements)

    characters = []
    for slot, (c, (x, y)) in enumerate(zip(CHARACTERS, slot_positions(size, CHAR_HEIGHT))):
        # キャラ非表示区間（章扉）用の透明フレーム。キャラ連番と同じサイズにする
        any_frame = next((os.path.join(s.seg_dir, "frames" if s.speaker == c["name"]
                                       else f"listener_{c['name']}")
                          for s in segments if s.show_characters), None)
        blank = os.path.join(tdir, f"_blank_{c['name']}.png")
        if any_frame:
            first = sorted(f for f in os.listdir(any_frame) if f.endswith(".png"))[0]
            with Image.open(os.path.join(any_frame, first)) as im:
                Image.new("RGBA", im.size, (0, 0, 0, 0)).save(blank)
        else:
            Image.new("RGBA", (2, CHAR_HEIGHT), (0, 0, 0, 0)).save(blank)
        frames = tl.character_frames(segments, placements, c["name"], blank)
        mov = os.path.join(tdir, f"{c['name']}.mov")
        print(f"[timeline] {c['label']} の透過トラックを書き出し中（{len(frames)} フレーム）")
        tl.write_character_mov(frames, mov, fps, size, CHAR_HEIGHT, x, y)
        os.remove(blank)
        characters.append((c["label"], mov, 2 + slot))

    voices = []
    for s, p in zip(segments, placements):
        sec, rate, ch = tl.wav_info(s.audio)
        dur = min(p.body, int(sec * fps))
        voices.append((s.audio, p.voice_start, dur, rate, ch))

    bgm_clip = None
    if bgm:
        bgm_wav = os.path.join(tdir, "bgm.wav")
        tl.write_bgm_wav(bgm, bgm_wav, total / fps)
        bgm_clip = (bgm_wav, total, 48000, 2, bgm_volume)

    tl.write_srt(tl.subtitle_entries(segments, placements, fps), os.path.join(tdir, "subtitles.srt"))
    xml = tl.build_fcpxml(title, fps, size, total, tl.slide_runs(segments, placements),
                          characters, voices, bgm_clip)
    path = os.path.join(tdir, "timeline.fcpxml")
    with open(path, "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"[timeline] {path}（字幕: timeline/subtitles.srt）")
    return path
