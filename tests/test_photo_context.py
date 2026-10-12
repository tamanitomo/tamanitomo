"""How to take a photo is in every turn's context, however full that context is.

It used to ride in the Image Studio section, the first to go when the snapshot ran
long. Asked for a photo on such a turn, a companion guessed at a command, failed,
and replied with a MEDIA path to a file that never existed."""

import datetime as dt
import pathlib
import tempfile
import unittest
from unittest.mock import patch

import companion_config as cc
import companion_context as ctx
import companion_self as slf

WINDOWS = [4096, 8192, 16384, 32768, 65536, 131072, 272000]
RECIPES = {
    "presets": [{"id": "studio", "category": "portrait"}],
    "routes": {"portrait": "studio"},
    "default_preset": "studio",
}


class PhotoContextTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)

    def make(self, **kw):
        c = cc.Companion(
            agent="Nova",
            human="Robin",
            timezone="UTC",
            hermes_root=self.root / ".hermes",
            vault=self.root / "vault",
            **kw,
        )
        c.soul_dir.mkdir(parents=True, exist_ok=True)
        return c

    def build(self, c):
        with patch("companion_media.effective", return_value=RECIPES):
            return ctx.build(c, {"extra": {"user_message": "send me a photo?"}})

    def test_the_photo_command_survives_when_the_studio_section_is_dropped(self):
        for window in WINDOWS:
            c = self.make(context_tokens=window)
            # Enough recorded facts that the droppable sections overflow.
            for i in range(60):
                slf.record_fact(
                    c.human_dir,
                    f"Robin detail {i} recorded at quite some length to fill the window",
                    f"said it {i}",
                    dt.datetime.now(dt.timezone.utc),
                    category="likes",
                )
            out = self.build(c)
            self.assertIn("To take a photo:", out, f"lost at {window}")
            self.assertIn("companion_portrait.py", out, f"lost at {window}")
            self.assertIn("`send` line", out, f"lost at {window}")
            self.assertIn("never write a MEDIA: path", out, f"lost at {window}")

    def test_the_compact_tail_carries_it_too(self):
        c = self.make(context_tokens=4096)
        self.assertTrue(c.compact)
        self.assertIn("To take a photo:", self.build(c))

    def test_she_knows_before_promising_that_undressed_photos_are_not_yet(self):
        # Not knowing, she could offer a photo the render would never produce.
        out = self.build(self.make(explicit=True, adult_images=False, boundary="girlfriend"))
        self.assertIn("Photos of you undressed are not something you send yet (Adult images are switched off", out)
        self.assertIn("is your call", out)

    def test_once_allowed_it_is_her_choice_and_named(self):
        with patch("companion_media.adult_ready", return_value=(True, [])):
            out = self.build(self.make(explicit=True, adult_images=True, boundary="girlfriend"))
        self.assertIn("A photo of you undressed is yours to choose: add --intimate", out)

    def test_a_companion_without_adult_themes_is_told_nothing_about_it(self):
        self.assertNotIn("undressed", self.build(self.make()))

    def test_the_wardrobe_is_part_of_the_photo_command(self):
        for window in (4096, 131072):
            self.assertIn('--wardrobe "what you have on in it"', self.build(self.make(context_tokens=window)))

    def test_no_image_studio_means_no_photo_line(self):
        c = self.make()
        with patch("companion_media.effective", return_value={"presets": []}):
            out = ctx.build(c, {"extra": {"user_message": "hi"}})
        self.assertNotIn("To take a photo:", out)


if __name__ == "__main__":
    unittest.main()
