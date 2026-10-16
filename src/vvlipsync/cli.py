"""CLI エントリポイント。

使い方:
    vvlipsync 台本.txt -o out/ -m mouths/ -s 1 --fps 30

台本フォーマット（1 行 = 1 セリフ = 字幕 1 件）:
    こんにちは、ずんだもんなのだ
    [3] 話者IDを行頭の [n] で上書きできる
    # '#' で始まる行はコメント、空行は無視
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from typing import List, Tuple

from .emotion import EmotionResolver, format_catalog
from .render import (
    build_audio,
    shapes_per_frame,
    values_per_frame,
    write_frames,
    write_srt,
)
from .motion import motion_at
from .timeline import Segment, pause_starts, pose_intervals, query_segments
from .voicevox import VoicevoxClient

DEFAULT_MOUTHS = {
    "a": "a.png",
    "i": "i.png",
    "u": "u.png",
    "e": "e.png",
    "o": "o.png",
    "closed": "closed.png",
}

# 行頭タグ: [話者] / [話者:感情] / [:感情] / [感情]
TAG_RE = re.compile(r"^\[([^\]]*)\]\s*(.*)$")


def _parse_tag(tag: str):
    """行頭の [...] 中身を (speaker|None, emotion|None) に分解する。"""
    tag = tag.strip()
    if ":" in tag:
        left, right = tag.split(":", 1)
        spk = int(left) if left.strip().isdigit() else None
        emo = right.strip() or None
        return spk, emo
    if tag.isdigit():
        return int(tag), None
    return None, (tag or None)  # 数字以外の単独タグは感情名


def parse_text(content: str, default_speaker: int, default_emotion):
    """各行を (speaker, emotion, text) に正規化する。"""
    lines = []
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = TAG_RE.match(line)
        if m:
            spk, emo = _parse_tag(m.group(1))
            lines.append((spk if spk is not None else default_speaker,
                          emo if emo is not None else default_emotion,
                          m.group(2).strip()))
        else:
            lines.append((default_speaker, default_emotion, line))
    return lines


def load_lines(args):
    """--text / 台本ファイル / 標準入力 のいずれかからセリフを読む。"""
    if args.text:
        content = "\n".join(args.text)
    elif args.script:
        with open(args.script, encoding="utf-8") as f:
            content = f.read()
    elif not sys.stdin.isatty():
        content = sys.stdin.read()
    else:
        sys.exit("セリフが無い。台本ファイル、--text、または標準入力のいずれかで渡す。")
    return parse_text(content, args.speaker, args.emotion)


def resolve_mouth_paths(mouths_dir: str, config_path: str) -> dict:
    mapping = dict(DEFAULT_MOUTHS)
    if config_path:
        with open(config_path, encoding="utf-8") as f:
            cfg = json.load(f)
        mapping.update(cfg.get("mouths", {}))

    paths = {}
    for shape, name in mapping.items():
        p = name if os.path.isabs(name) else os.path.join(mouths_dir, name)
        if not os.path.isfile(p):
            sys.exit(f"口形 PNG が見つからない: {shape} -> {p}")
        paths[shape] = p
    return paths


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="vvlipsync",
        description="VOICEVOX の音声に口パクを合わせ、DaVinci 取り込み用素材を出力する",
    )
    p.add_argument("script", nargs="?", help="台本テキストファイル（省略時は --text か標準入力）")
    p.add_argument(
        "-t", "--text", action="append",
        help="セリフを直接渡す（複数回指定で複数行。1つの値に改行を含めてもよい）",
    )
    p.add_argument("-o", "--out", help="出力ディレクトリ（--list-speakers 以外で必須）")
    p.add_argument("-m", "--mouths", help="口形 PNG が入ったディレクトリ（--list-speakers 以外で必須）")
    p.add_argument("-s", "--speaker", type=int, default=1, help="デフォルト話者ID (既定: 1)")
    p.add_argument(
        "-e", "--emotion", default=None,
        help="感情=VOICEVOX スタイル名（例: あまあま, ツンツン, なみだめ）。行頭 [話者:感情] でも指定可",
    )
    p.add_argument("--intonation", type=float, default=None, help="抑揚 intonationScale（感情の強さ。1.0=既定）")
    p.add_argument("--pitch", type=float, default=None, help="音高 pitchScale（既定 0.0）")
    p.add_argument("--volume", type=float, default=None, help="音量 volumeScale（既定 1.0）")
    p.add_argument("--list-speakers", action="store_true", help="話者と感情(スタイル)の一覧を表示して終了")
    p.add_argument("--fps", type=float, default=30.0, help="フレームレート (既定: 30)")
    p.add_argument("--gap", type=float, default=0.3, help="セリフ間の無音秒数 (既定: 0.3)")
    p.add_argument("--speed", type=float, default=1.0, help="話速 speedScale (既定: 1.0)")
    p.add_argument("--host", default="http://localhost:50021", help="VOICEVOX ENGINE の URL")
    p.add_argument("--config", default="", help="口形マップ等の JSON 設定ファイル")
    p.add_argument(
        "--emotions", default="",
        help="感情プリセット JSON。指定すると -e/[タグ] は感情名（通常・喜び等）として声＋表情を解決する",
    )
    p.add_argument(
        "--flip", action="store_true",
        help="左右反転して出力（動画の右端/左端に置く時、キャラを内向きにする）",
    )
    p.add_argument(
        "--no-motion", action="store_true",
        help="体の動き（ふわふわ呼吸・感情モーション）を付けない",
    )
    p.add_argument(
        "--motion-offset", type=float, default=0.0,
        help="呼吸の位相に使う通し時刻のオフセット秒（クリップを繋ぐ時に呼吸を連続させる）",
    )
    p.add_argument("--preview", action="store_true", help="確認用 mp4 (preview.mp4) も生成する")
    p.add_argument("--bg", default="white", help="プレビュー背景色 (既定: white)")
    p.add_argument(
        "--alpha-video", nargs="?", const="mov", choices=["mov", "webm"], default=None,
        help="背景透過の動画 character.<mov|webm> も生成する（既定 mov=ProRes 4444。webm=VP9）",
    )
    p.add_argument(
        "--timeline", action="store_true",
        help="DaVinci 取り込み用の timeline.fcpxml も生成する（character.mov ＋ audio.wav を並べる）",
    )
    p.add_argument("--timeline-size", default="1920x1080",
                   help="--timeline のタイムライン解像度 (既定: 1920x1080。縦動画なら 1080x1920)")
    return p


def _apply_scales(query: dict, args) -> None:
    if args.speed != 1.0:
        query["speedScale"] = args.speed
    if args.intonation is not None:
        query["intonationScale"] = args.intonation
    if args.pitch is not None:
        query["pitchScale"] = args.pitch
    if args.volume is not None:
        query["volumeScale"] = args.volume


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    client = VoicevoxClient(host=args.host)
    resolver = EmotionResolver(client.speakers())

    if args.list_speakers:
        print(format_catalog(client.speakers()))
        return 0

    if not args.out or not args.mouths:
        sys.exit("-o/--out と -m/--mouths は必須（--list-speakers を除く）")

    lines = load_lines(args)
    if not lines:
        sys.exit("有効なセリフがない")

    # 感情プリセット（あれば）。-e/[タグ] の名前 → 声スタイル名 へ引き直す。
    presets = {}
    if args.emotions:
        with open(args.emotions, encoding="utf-8") as f:
            presets = json.load(f).get("presets", {})

    def emotion_to_style(emotion):
        if emotion and emotion in presets:
            return presets[emotion].get("voice")
        return emotion  # プリセット未使用なら素のスタイル名として扱う

    mouth_paths = resolve_mouth_paths(args.mouths, args.config)

    all_segments: List[Segment] = []
    audio_items: List[Tuple[float, bytes, float]] = []
    srt_entries: List[Tuple[float, float, str]] = []
    line_faces = []  # (line_start, emotion) — 行ごとの表情に使う
    line_pauses = []  # 各行の句読点ポーズ開始（通し時刻）— ポーズ切り替えに使う

    cursor = 0.0
    for idx, (speaker, emotion, text) in enumerate(lines):
        gap_before = args.gap if idx > 0 else 0.0
        cursor += gap_before

        try:
            sid = resolver.resolve(speaker, emotion_to_style(emotion))
        except KeyError as e:
            sys.exit(str(e))

        line_faces.append((cursor, emotion))

        query = client.audio_query(text, sid)
        _apply_scales(query, args)
        wav = client.synthesis(query, sid)

        segs, total = query_segments(query, args.speed)
        line_pauses.append([cursor + t for t in pause_starts(query, args.speed)])
        for s in segs:
            all_segments.append(Segment(s.start + cursor, s.end + cursor, s.shape))
        srt_entries.append((cursor, cursor + total, text))
        audio_items.append((gap_before, wav, total))

        cursor += total
        emo_label = f" {emotion}" if emotion else ""
        print(f"  [{idx + 1}/{len(lines)}] spk={sid}{emo_label} {total:.2f}s  {text}")

    timeline_end = cursor
    total_frames = max(1, math.ceil(timeline_end * args.fps))

    os.makedirs(args.out, exist_ok=True)
    frames_dir = os.path.join(args.out, "frames")
    shapes = shapes_per_frame(all_segments, total_frames, args.fps)

    print(f"総尺 {timeline_end:.2f}s / {total_frames} frames @ {args.fps}fps")
    # 行ごとの表情を、各行の開始〜次行の開始まで（＝その行のギャップ後まで）の区間にする。
    # base 画像があれば「表情＋口」を合成、無ければ口だけの連番に自動で縮退する。
    face_intervals = [
        (start, line_faces[i + 1][0] if i + 1 < len(line_faces) else timeline_end, emo)
        for i, (start, emo) in enumerate(line_faces)
    ]
    default_emo = line_faces[-1][1] if line_faces else None
    base_paths = _build_base_paths(args.mouths, {e for _, e in line_faces})

    # ポーズ: 句読点ごとに、その感情のポーズ差分を巡回する
    pose_ivs = []
    for (start, end, emo), pauses in zip(face_intervals, line_pauses):
        n = sum(1 for k in base_paths if isinstance(k, tuple) and k[0] == emo)
        pose_ivs += [(s, e, (emo, k)) for s, e, k in pose_intervals(start, end, pauses, n)]
    frame_keys = values_per_frame(pose_ivs, total_frames, args.fps, (default_emo, 0))

    transforms = None
    if not args.no_motion:
        line_ivs = [(s, e, (emo, s)) for s, e, emo in face_intervals]
        frame_lines = values_per_frame(line_ivs, total_frames, args.fps, (default_emo, 0.0))
        transforms = []
        for i, (emo, line_start) in enumerate(frame_lines):
            t = (i + 0.5) / args.fps
            kind = presets.get(emo, {}).get("motion") if emo else None
            transforms.append(motion_at(emo, t - line_start, t + args.motion_offset, kind=kind))

    write_frames(list(zip(frame_keys, shapes)), mouth_paths, base_paths, frames_dir,
                 flip=args.flip, transforms=transforms)

    build_audio(audio_items, os.path.join(args.out, "audio.wav"))
    write_srt(srt_entries, os.path.join(args.out, "subtitles.srt"))

    has_base = any(v for v in base_paths.values())
    print(f"出力完了: {args.out}")
    frames_desc = "表情つき全身キャラ連番" if has_base else "口パク透過連番"
    print(f"  frames/        {frames_desc} ({total_frames} 枚, {args.fps}fps で取り込む)")
    print("  audio.wav      連結音声")
    print("  subtitles.srt  字幕")

    if args.preview:
        from .preview import compile_preview
        # frames は完成済み（表情があれば焼き込み済み）なので base は重ねない
        preview_out = os.path.join(args.out, "preview.mp4")
        compile_preview(
            frames_dir, os.path.join(args.out, "audio.wav"), preview_out,
            args.fps, base="", bg=args.bg,
        )
    if args.alpha_video or args.timeline:
        from .preview import compile_alpha_video
        kinds = {args.alpha_video} if args.alpha_video else set()
        if args.timeline:
            kinds.add("mov")  # タイムラインは ProRes 4444 の透過動画を参照する
        for kind in sorted(kinds):
            compile_alpha_video(frames_dir, os.path.join(args.out, "audio.wav"),
                                os.path.join(args.out, f"character.{kind}"), args.fps)
    if args.timeline:
        _write_timeline(args, resolver, frames_dir, total_frames)
    return 0


def _write_timeline(args, resolver, frames_dir: str, total_frames: int) -> None:
    import wave

    from .fcpxml import single_character_fcpxml
    from .preview import _canvas_size

    try:
        tw, th = (int(v) for v in args.timeline_size.lower().split("x"))
    except ValueError:
        sys.exit(f"--timeline-size は 幅x高さ で指定する: {args.timeline_size}")
    audio = os.path.join(args.out, "audio.wav")
    with wave.open(audio) as w:
        rate, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
    name = resolver.describe(args.speaker)[0]
    xml = single_character_fcpxml(
        name, args.fps, (tw, th), total_frames,
        mov=os.path.join(args.out, "character.mov"),
        mov_size=_canvas_size(os.path.join(frames_dir, "00000.png")),
        wav=audio, wav_frames=int(n / rate * args.fps), audio_rate=rate, audio_channels=ch,
    )
    path = os.path.join(args.out, "timeline.fcpxml")
    with open(path, "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"タイムライン: {path}（字幕は subtitles.srt を読み込む）")


def _build_base_paths(mouths_dir: str, emotions) -> dict:
    """(感情, ポーズ番号) → base 画像パス。ポーズ 0 は base_<感情>.png（無ければ None）、
    1 以降は base_<感情>_p<n>.png があるだけ。None キーは base.png のフォールバック。"""
    paths = {}
    for e in emotions:
        p = os.path.join(mouths_dir, f"base_{e}.png") if e else ""
        paths[(e, 0)] = p if p and os.path.isfile(p) else None
        k = 1
        while e and os.path.isfile(os.path.join(mouths_dir, f"base_{e}_p{k}.png")):
            paths[(e, k)] = os.path.join(mouths_dir, f"base_{e}_p{k}.png")
            k += 1
    fallback = os.path.join(mouths_dir, "base.png")
    paths[None] = fallback if os.path.isfile(fallback) else None
    return paths


if __name__ == "__main__":
    raise SystemExit(main())
