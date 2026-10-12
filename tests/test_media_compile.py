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

    def test_what_she_has_on_beats_the_presets_default_outfit(self):
        # A preset's wardrobe dressed every picture in the same outfit, over the one
        # she had on.
        draft = dict(DRAFT, parts={"quality": "best quality", "wardrobe": "grey hoodie"})
        parts = media.compile(self.c, overrides={"scene": "on the back steps"}, draft=draft)["parts"]
        self.assertEqual(parts["wardrobe"], "green pajamas")
        with patch.object(portrait, "recorded_parts", return_value=dict(RECORDED, wardrobe="")):
            parts = media.compile(self.c, overrides={"scene": "on the back steps"}, draft=draft)["parts"]
        self.assertEqual(parts["wardrobe"], "grey hoodie")

    def test_a_preset_nobody_saved_is_named_with_the_ones_that_were(self):
        (self.c.home / media.CONFIG).write_text(json.dumps({"version": 1, "presets": [dict(DRAFT, id="studio")]}))
        with self.assertRaisesRegex(ValueError, r"no image preset called 'nightlight'.*studio"):
            media.compile(self.c, "nightlight")

    def test_modesty_words_sort_into_the_bucket_she_may_set_aside(self):
        always, modesty = media.sort_negative("blurry, child, nude, cleavage, provocative pose")
        self.assertEqual(always, "blurry")
        self.assertEqual(modesty, "nude, cleavage, provocative pose")


SHOWERING = {"state": {"activity": "taking a shower", "outfit": [{"id": "bathing"}]}}


class UndressedPhotoTests(unittest.TestCase):
    """Asked for a photo while the record says she is undressed."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = pathlib.Path(tmp.name)
        self.c = cc.Companion(agent="Nova", human="Alex", hermes_root=root / "home", vault=root / "vault")
        self.c.home.mkdir(parents=True, exist_ok=True)

    def run_generate(self, *flags, now=SHOWERING, allowed=(False, "Adult images are switched off.")):
        import companion_presence as presence

        argv = ["companion_portrait.py", "--home", str(self.c.home), "generate", "--scene", "after a shower", *flags]
        made = {"path": "/vault/a.png", "file": "a.png"}
        with patch.object(sys, "argv", argv), patch.object(cc, "load", return_value=self.c), \
                patch.object(presence, "current", return_value=now), \
                patch.object(presence, "wardrobe", return_value={"items": []}), \
                patch.object(portrait, "undressed_render_allowed", return_value=allowed), \
                patch.object(media, "generate", return_value=made) as generate, redirect_stdout(io.StringIO()):
            portrait.main()
        return generate.call_args

    def test_not_yet_is_said_rather_than_painted_over_with_clothes(self):
        with self.assertRaisesRegex(ValueError, "in the bath or shower.*not a photo you send yet: Adult images"):
            self.run_generate()

    def test_once_it_is_hers_to_choose_the_refusal_names_how(self):
        with self.assertRaisesRegex(ValueError, "--intimate"):
            self.run_generate(allowed=(True, ""))

    def test_something_put_on_for_the_photo_can_be_photographed(self):
        call = self.run_generate("--wardrobe", "a white bath towel")
        self.assertEqual(call.args[3]["wardrobe"], "a white bath towel")
        self.assertFalse(call.kwargs["intimate"])

    def test_an_intimate_photo_she_chose_has_no_wardrobe_box(self):
        call = self.run_generate("--intimate", allowed=(True, ""))
        self.assertTrue(call.kwargs["intimate"])
        self.assertEqual(call.args[3]["wardrobe"], "")

    def test_an_intimate_photo_is_refused_before_anything_renders_when_not_allowed(self):
        with self.assertRaisesRegex(ValueError, "not one you send yet: Adult images"):
            self.run_generate("--intimate", now={"state": {"activity": "reading", "outfit": [{"id": "x", "description": "jeans"}]}})

    def test_no_record_at_all_is_not_undressed(self):
        call = self.run_generate(now=None)
        self.assertFalse(call.kwargs["intimate"])


if __name__ == "__main__":
    unittest.main()
