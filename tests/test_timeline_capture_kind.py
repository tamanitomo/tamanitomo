"""A timeline capture is rendered as what the moment is.

A bath is intimate or not photographed at all; a towel is a tease, photographed
wrapped with the modesty negatives still on. Treating a towel as intimate asked the
closeness gate a question only Bonded can answer, and the capture failed.
"""

import pathlib
import tempfile
import unittest
from unittest.mock import patch

import companion_config as cc
import companion_media as media
import companion_portrait as portrait
import companion_presence as presence
import companion_timeline as timeline
import companion_timeline_capture as capture


def scene(outfit):
    return {"state": {"activity": "after a shower", "outfit": outfit}}


class CaptureKindTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = pathlib.Path(tmp.name)
        self.c = cc.Companion(agent="Nova", human="Alex", hermes_root=root / "home", vault=root / "vault")

    def render(self, outfit):
        claimed = {"ready": True, "capture_id": "cap1", "scene": scene(outfit)}
        made = {"path": "/tmp/x.png", "provider": "comfyui"}
        saved = {"status": "saved", "filename": "cap1.png", "provider": "comfyui", "sha256": "0"}
        with patch.object(timeline, "prepare", return_value=claimed), \
                patch.object(presence, "wardrobe", return_value={"items": []}), \
                patch.object(media, "effective", return_value={"default_preset": "studio"}), \
                patch.object(portrait, "recorded_overrides", return_value={"scene": "after a shower"}), \
                patch.object(media, "generate", return_value=made) as generate, \
                patch.object(timeline, "save", return_value=saved), \
                patch.object(media, "discard_scratch"):
            capture.capture(self.c)
        return generate.call_args.kwargs["intimate"]

    def test_a_towel_is_not_an_intimate_render(self):
        self.assertFalse(self.render([{"id": "towel", "description": "wrapped in a bath towel"}]))

    def test_a_bath_is(self):
        self.assertTrue(self.render([{"id": "bathing"}]))


if __name__ == "__main__":
    unittest.main()
