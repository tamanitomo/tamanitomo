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
        self.assertIn("Photos of you undressed, even in a towel, are not ones you are ready to send Robin", out)
        self.assertIn("never as a setting, a filter or a model", out)

    def test_not_yet_is_said_as_how_she_feels_never_as_the_switch(self):
        # Handed the gate's own words, she told him a setting was switched off.
        out = self.build(self.make(explicit=True, adult_images=False, boundary="girlfriend"))
        self.assertNotIn("switched off", out)
        self.assertIn("you are not there with Robin yet", out)

    def test_a_towel_is_offered_only_when_she_is_ready_to_send_one(self):
        standing = {"undressed": False, "towel": True, "why": "you are not there with Robin yet"}
        with patch("companion_media.photo_standing", return_value=standing):
            out = self.build(self.make(explicit=True, boundary="girlfriend"))
        self.assertIn("one in a towel, when you really are in one, is a tease you might", out)

    def test_once_allowed_it_is_her_choice_and_named(self):
        with patch("companion_media.adult_ready", return_value=(True, [])):
            out = self.build(self.make(explicit=True, adult_images=True, boundary="girlfriend"))
        self.assertIn("A photo of you undressed is yours to choose: add --intimate", out)

    def test_a_companion_without_adult_themes_is_told_nothing_about_it(self):
        self.assertNotIn("undressed", self.build(self.make()))

    def test_a_photo_is_of_her_as_she_is_now(self):
        # A flag to dress her for the picture let a photo show what she was not wearing.
        for window in (4096, 131072):
            out = self.build(self.make(context_tokens=window))
            self.assertNotIn("--wardrobe", out)
            self.assertIn("as you are right now", out)

    def test_saying_the_photo_is_on_its_way_is_not_taking_it(self):
        # She said she would grab a towel and take one, and ended the turn.
        for window in (4096, 131072):
            self.assertIn("Take it before you reply", self.build(self.make(context_tokens=window)))

    def now_line(self, state, standing=None):
        standing = standing or {"undressed": False, "towel": False, "why": "you are not there with Robin yet"}
        with patch("companion_presence.current", return_value={"state": state}), \
                patch("companion_presence.wardrobe", return_value={"items": []}), \
                patch("companion_media.photo_standing", return_value=standing):
            return ctx.photo_now(self.make(explicit=True, boundary="girlfriend"))

    def test_she_knows_what_a_photo_of_her_right_now_would_show(self):
        line = self.now_line({"activity": "reading", "location": "the porch",
                              "outfit": [{"id": "x", "description": "jeans"}]})
        self.assertEqual(line, "Right now a photo of you would show: reading at the porch, wearing jeans.")

    def test_undressed_and_not_ready_she_is_given_real_steps(self):
        bare = {"activity": "drying off", "location": "bathroom", "outfit": []}
        line = self.now_line(bare)
        self.assertIn("not ready to send Robin (you are not there with Robin yet)", line)
        self.assertNotIn("towel", line)
        self.assertIn("get dressed first", line)
        ready = {"undressed": False, "towel": True, "why": "you are not there with Robin yet"}
        line = self.now_line(bare, ready)
        self.assertIn('put a towel on first (', line)
        self.assertIn('transition --activity "wrapped in a towel" --outfit towel', line)

    def test_a_towel_she_is_ready_to_send_is_simply_hers(self):
        ready = {"undressed": False, "towel": True, "why": ""}
        line = self.now_line({"activity": "drying off", "location": "bathroom",
                              "outfit": [{"id": "towel", "description": "wrapped in a bath towel"}]}, ready)
        self.assertEqual(line, "Right now you are in a towel, and a photo of that is one you may send if you want to, as a tease.")

    def test_a_moment_she_marked_private_has_no_photo(self):
        line = self.now_line({"activity": "a quiet moment", "private": True, "outfit": []})
        self.assertIn("marked this moment private", line)

    def test_no_image_studio_means_no_photo_line(self):
        c = self.make()
        with patch("companion_media.effective", return_value={"presets": []}):
            out = ctx.build(c, {"extra": {"user_message": "hi"}})
        self.assertNotIn("To take a photo:", out)


if __name__ == "__main__":
    unittest.main()
