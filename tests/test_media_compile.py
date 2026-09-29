"""Which moment each structured box describes when a picture is compiled."""

import pathlib
import tempfile
import unittest
from unittest.mock import patch

import companion_config as cc
import companion_media as media
import companion_portrait as portrait

RECORDED = {
    "identity": "adult woman, auburn hair",
    "scene": "taking a warm shower, bathroom at home",
    "wardrobe": "green pajamas",
    "feeling": "finishing the shower",
    "lighting": "warm bathroom light softened by steam",
    "camera": "misted bathroom air",
}
DRAFT = {
    "id": "draft",
    "provider": "comfyui",
    "endpoint": "http://127.0.0.1:8188",
    "parts": {"quality": "best quality"},
    "workflow": {},
    "mappings": {},
}


class CompileTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        self.c = cc.Companion(agent="Nova", human="Alex", hermes_root=root / "home", vault=root / "vault")
        self.c.home.mkdir(parents=True, exist_ok=True)
        patcher = patch.object(portrait, "recorded_parts", return_value=dict(RECORDED))
        patcher.start()
        self.addCleanup(patcher.stop)

    def parts(self, overrides=None):
        return media.compile(self.c, overrides=overrides, draft=dict(DRAFT))["parts"]

    def test_a_requested_scene_does_not_inherit_the_recorded_light_framing_or_mood(self):
        parts = self.parts({"scene": "on the back steps at dawn with coffee"})
        self.assertEqual(parts["scene"], "on the back steps at dawn with coffee")
        self.assertEqual([parts.get(k, "") for k in ("lighting", "camera", "feeling")], ["", "", ""])

    def test_she_is_still_wearing_what_she_has_on(self):
        self.assertEqual(self.parts({"scene": "on the back steps"})["wardrobe"], "green pajamas")

    def test_boxes_passed_with_the_scene_fill_their_own_nodes(self):
        parts = self.parts({"scene": "on the back steps", "lighting": "cool dawn light", "camera": "wide shot", "wardrobe": "jeans"})
        self.assertEqual((parts["lighting"], parts["camera"], parts["wardrobe"]), ("cool dawn light", "wide shot", "jeans"))

    def test_without_a_requested_scene_the_recorded_moment_fills_every_box(self):
        parts = self.parts()
        for key in ("scene", "wardrobe", "feeling", "lighting", "camera"):
            self.assertEqual(parts[key], RECORDED[key])


if __name__ == "__main__":
    unittest.main()
