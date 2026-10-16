"""kaisetsu → DaVinci 取り込み用タイムライン（FCPXML）のテスト。"""

import os
import tempfile
import unittest
import xml.etree.ElementTree as ET

from kaisetsu.timeline import (
    Segment,
    build_fcpxml,
    character_frames,
    fcpxml_time,
    place,
    slide_runs,
    subtitle_entries,
)


def _seg(**kw):
    base = dict(bg_png="/o/slide_00.png", speaker="zundamon", label="ずんだもん", text="やあ",
                seg_dir="/o/seg_000", n_frames=10, head=0.2, tail=0.3, audio="/o/seg_000/audio.wav",
                audio_seconds=0.3, subtitle=True, show_characters=True)
    base.update(kw)
    return Segment(**base)


class TestPlace(unittest.TestCase):
    def test_frames_are_head_body_tail_back_to_back(self):
        segs = [_seg(), _seg(n_frames=20, head=0.1, tail=0.0)]
        p = place(segs, 30)
        self.assertEqual((p[0].start, p[0].head, p[0].body, p[0].tail), (0, 6, 10, 9))
        self.assertEqual(p[0].total, 25)
        self.assertEqual((p[1].start, p[1].head, p[1].body, p[1].tail), (25, 3, 20, 0))
        self.assertEqual(p[1].voice_start, 28)  # 音声は「間」の後から


class TestCharacterFrames(unittest.TestCase):
    def test_speaker_listener_and_hidden_segments(self):
        with tempfile.TemporaryDirectory() as d:
            def mk(sub, n):
                os.makedirs(os.path.join(d, sub))
                for i in range(n):
                    open(os.path.join(d, sub, f"{i:05d}.png"), "wb").close()
            mk("seg_000/frames", 3)              # タイトルコール（キャラ非表示）
            mk("seg_001/frames", 2)              # ずんだもんが喋る
            mk("seg_001/listener_metan", 2)      # めたんは聞き手
            segs = [
                _seg(seg_dir=os.path.join(d, "seg_000"), n_frames=3, head=0, tail=0,
                     show_characters=False),
                _seg(seg_dir=os.path.join(d, "seg_001"), n_frames=2, head=1 / 30, tail=2 / 30),
            ]
            p = place(segs, 30)
            z = character_frames(segs, p, "zundamon", blank="BLANK")
            m = character_frames(segs, p, "metan", blank="BLANK")
            sp = os.path.join(d, "seg_001/frames")
            li = os.path.join(d, "seg_001/listener_metan")
            # 非表示区間は透明、間（head/tail）は最初/最後のフレームを保持
            self.assertEqual(z, ["BLANK"] * 3 + [f"{sp}/00000.png", f"{sp}/00000.png",
                                                 f"{sp}/00001.png", f"{sp}/00001.png", f"{sp}/00001.png"])
            self.assertEqual(m[3:], [f"{li}/00000.png", f"{li}/00000.png",
                                     f"{li}/00001.png", f"{li}/00001.png", f"{li}/00001.png"])
            self.assertEqual(len(z), sum(x.total for x in p))


class TestSlidesAndSubtitles(unittest.TestCase):
    def test_consecutive_same_slide_is_merged(self):
        segs = [_seg(bg_png="/o/title_00.png"), _seg(), _seg(), _seg(bg_png="/o/slide_01.png")]
        p = place(segs, 30)
        self.assertEqual(slide_runs(segs, p), [("/o/title_00.png", 0, 25), ("/o/slide_00.png", 25, 50),
                                               ("/o/slide_01.png", 75, 25)])

    def test_subtitles_cover_voice_only_and_skip_title_call(self):
        segs = [_seg(subtitle=False, text="章"), _seg(text="こんにちは")]
        p = place(segs, 30)
        self.assertEqual(subtitle_entries(segs, p, 30), [((25 + 6) / 30, (25 + 16) / 30, "ずんだもん「こんにちは」")])


class TestFcpxml(unittest.TestCase):
    def test_time_format(self):
        self.assertEqual(fcpxml_time(0, 30), "0s")
        self.assertEqual(fcpxml_time(45, 30), "45/30s")
        self.assertEqual(fcpxml_time(10, 29.97), "10010/30000s")

    def _build(self, bgm=None):
        return build_fcpxml(
            "テスト解説", 30, (1920, 1080), 100,
            slides=[("/o/タイトル 00.png", 0, 40), ("/o/slide_00.png", 40, 60)],
            characters=[("四国めたん", "/o/timeline/metan.mov", 2), ("ずんだもん", "/o/timeline/zundamon.mov", 3)],
            voices=[("/o/seg_000/audio.wav", 6, 30, 24000, 1), ("/o/seg_001/audio.wav", 50, 40, 24000, 1)],
            bgm=bgm,
        )

    def test_structure(self):
        root = ET.fromstring(self._build())
        self.assertEqual(root.tag, "fcpxml")
        fmt = root.find("resources/format[@id='r1']")
        self.assertEqual(fmt.get("frameDuration"), "1/30s")
        self.assertEqual((fmt.get("width"), fmt.get("height")), ("1920", "1080"))

        seq = root.find("library/event/project/sequence")
        self.assertEqual(root.find("library/event/project").get("name"), "テスト解説")
        self.assertEqual(seq.get("duration"), "100/30s")
        gap = seq.find("spine/gap")
        self.assertEqual(gap.get("duration"), "100/30s")

        assets = {a.get("id"): a for a in root.findall("resources/asset")}
        # パスは file:// の絶対 URL（日本語・空白はエンコード）
        srcs = [a.get("src") for a in assets.values()]
        self.assertIn("file:///o/%E3%82%BF%E3%82%A4%E3%83%88%E3%83%AB%2000.png", srcs)

        stills = gap.findall("video")
        self.assertEqual([(v.get("lane"), v.get("offset"), v.get("duration")) for v in stills],
                         [("1", "0s", "40/30s"), ("1", "40/30s", "60/30s")])

        chars = [c for c in gap.findall("asset-clip") if assets[c.get("ref")].get("hasVideo") == "1"]
        self.assertEqual([(c.get("name"), c.get("lane"), c.get("offset"), c.get("duration")) for c in chars],
                         [("四国めたん", "2", "0s", "100/30s"), ("ずんだもん", "3", "0s", "100/30s")])

        voices = [c for c in gap.findall("asset-clip") if c.get("lane") == "-1"]
        self.assertEqual([(c.get("offset"), c.get("duration")) for c in voices],
                         [("6/30s", "30/30s"), ("50/30s", "40/30s")])
        a = assets[voices[0].get("ref")]
        self.assertEqual((a.get("hasAudio"), a.get("audioRate"), a.get("audioChannels")), ("1", "24000", "1"))

    def test_bgm_on_its_own_lane_with_volume(self):
        root = ET.fromstring(self._build(bgm=("/o/timeline/bgm.wav", 100, 48000, 2, 0.18)))
        gap = root.find("library/event/project/sequence/spine/gap")
        bgm = [c for c in gap.findall("asset-clip") if c.get("lane") == "-2"]
        self.assertEqual(len(bgm), 1)
        self.assertEqual((bgm[0].get("offset"), bgm[0].get("duration")), ("0s", "100/30s"))
        vol = bgm[0].find("adjust-volume")
        self.assertEqual(vol.get("amount"), "-14.9dB")  # 20*log10(0.18)


if __name__ == "__main__":
    unittest.main()
