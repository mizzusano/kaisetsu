"""PSD 抽出: 同名グループの選択と、ポーズ差分の展開のテスト。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from psd_extract import base_filename, find_group, preset_poses  # noqa: E402


class FakeLayer:
    def __init__(self, name, children=None, visible=True):
        self.name = name
        self.visible = visible
        self.parent = None
        self._children = children
        for c in children or []:
            c.parent = self

    def is_group(self):
        return self._children is not None

    def __iter__(self):
        return iter(self._children or [])

    def descendants(self):
        for c in self._children or []:
            yield c
            if c.is_group():
                yield from c.descendants()


class TestFindGroup(unittest.TestCase):
    def test_prefers_group_under_visible_parents(self):
        # ずんだもん2.3 は 服装2(非表示) と 服装1(表示) の両方に「!左腕」がある
        hidden_arm = FakeLayer("!左腕", [FakeLayer("*基本")])
        shown_arm = FakeLayer("!左腕", [FakeLayer("*基本")])
        psd = FakeLayer("root", [
            FakeLayer("*服装2", [hidden_arm], visible=False),
            FakeLayer("*服装1", [shown_arm], visible=True),
        ])
        self.assertIs(find_group(psd, "左腕"), shown_arm)

    def test_falls_back_to_first_match(self):
        only = FakeLayer("!右腕", [])
        psd = FakeLayer("root", [FakeLayer("*服装2", [only], visible=False)])
        self.assertIs(find_group(psd, "右腕"), only)


class TestPresetPoses(unittest.TestCase):
    def test_without_poses_returns_single_selection(self):
        preset = {"voice": "ノーマル", "目": "目セット", "右腕": "基本"}
        self.assertEqual(preset_poses(preset), [{"voice": "ノーマル", "目": "目セット", "右腕": "基本"}])

    def test_poses_override_on_top_of_preset(self):
        preset = {"voice": "あまあま", "目": "にっこり", "右腕": "基本", "左腕": "基本",
                  "poses": [{"右腕": "手を挙げる", "左腕": "手を挙げる"}, {"右腕": "手を挙げる"}]}
        got = preset_poses(preset)
        self.assertEqual(len(got), 2)
        self.assertEqual(got[0]["右腕"], "手を挙げる")
        self.assertEqual(got[0]["左腕"], "手を挙げる")
        self.assertEqual(got[1]["右腕"], "手を挙げる")
        self.assertEqual(got[1]["左腕"], "基本")
        self.assertEqual(got[1]["目"], "にっこり")
        self.assertNotIn("poses", got[0])


class TestBaseFilename(unittest.TestCase):
    def test_names(self):
        self.assertEqual(base_filename("喜び", 0), "base_喜び.png")
        self.assertEqual(base_filename("喜び", 2), "base_喜び_p2.png")


if __name__ == "__main__":
    unittest.main()
