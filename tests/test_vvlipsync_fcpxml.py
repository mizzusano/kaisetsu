"""vvlipsync 単体の DaVinci 取り込み用 FCPXML のテスト。"""

import unittest
import xml.etree.ElementTree as ET

from vvlipsync.fcpxml import build_fcpxml, fcpxml_time, single_character_fcpxml


class TestSingleCharacter(unittest.TestCase):
    def _root(self):
        return ET.fromstring(single_character_fcpxml(
            "ずんだもん", 30, (1920, 1080), 90,
            mov="/o/out/character.mov", mov_size=(1082, 1650),
            wav="/o/out/audio.wav", wav_frames=88, audio_rate=24000, audio_channels=1,
        ))

    def test_sequence_is_timeline_size_and_length(self):
        root = self._root()
        fmt = root.find("resources/format[@id='r1']")
        self.assertEqual((fmt.get("width"), fmt.get("height"), fmt.get("frameDuration")),
                         ("1920", "1080", "1/30s"))
        seq = root.find("library/event/project/sequence")
        self.assertEqual(seq.get("duration"), "90/30s")

    def test_character_keeps_native_size_on_v1(self):
        root = self._root()
        assets = {a.get("id"): a for a in root.findall("resources/asset")}
        formats = {f.get("id"): f for f in root.findall("resources/format")}
        gap = root.find("library/event/project/sequence/spine/gap")
        clips = gap.findall("asset-clip")
        char = [c for c in clips if assets[c.get("ref")].get("hasVideo") == "1"]
        self.assertEqual(len(char), 1)
        self.assertEqual((char[0].get("lane"), char[0].get("offset"), char[0].get("duration")),
                         ("1", "0s", "90/30s"))
        fmt = formats[assets[char[0].get("ref")].get("format")]
        # 立ち絵は元サイズのまま（DaVinci の「画面に収める」で全身が入る。後から自由に拡縮できる）
        self.assertEqual((fmt.get("width"), fmt.get("height")), ("1082", "1650"))

    def test_audio_on_a1(self):
        root = self._root()
        gap = root.find("library/event/project/sequence/spine/gap")
        aud = [c for c in gap.findall("asset-clip") if c.get("lane") == "-1"]
        self.assertEqual([(c.get("offset"), c.get("duration")) for c in aud], [("0s", "88/30s")])


class TestSharedBuilder(unittest.TestCase):
    def test_kaisetsu_uses_the_same_builder(self):
        from kaisetsu import timeline as kt
        self.assertIs(kt.build_fcpxml, build_fcpxml)
        self.assertIs(kt.fcpxml_time, fcpxml_time)


if __name__ == "__main__":
    unittest.main()
