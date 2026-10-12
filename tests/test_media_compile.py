"""Which moment each structured box describes when a picture is compiled."""

import io
import json
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
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

    def test_a_photo_comes_back_with_the_line_that_sends_it(self):
        # Left to write the MEDIA line herself, a companion once sent a path to a
        # file that never existed and the reply arrived as bare alt text.
        made = {"path": "/vault/creations/image-studio/a.png", "file": "a.png"}
        argv = ["companion_portrait.py", "--home", str(self.c.home), "generate", "--scene", "on the back steps"]
        out = io.StringIO()
        with patch.object(sys, "argv", argv), patch.object(cc, "load", return_value=self.c), patch.object(media, "generate", return_value=dict(made)), redirect_stdout(out):
            portrait.main()
        result = json.loads(out.getvalue())
        self.assertEqual(next(iter(result)), "send")
        self.assertEqual(result["send"], "MEDIA:/vault/creations/image-studio/a.png")
        self.assertEqual(result["path"], made["path"])


if __name__ == "__main__":
    unittest.main()
