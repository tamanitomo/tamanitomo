"""A private stance and wants carry across a gap, then lapse once they are old.

Code used to copy both into every later record, so a conclusion drawn one evening
about what the human wanted was still steering every pulse the next afternoon,
after the two of them had talked twice.
"""

import datetime as dt
import pathlib
import tempfile
import unittest
from unittest.mock import patch

import companion_active as active
import companion_config as cc
import companion_presence as presence

HURT = "A little stung by the short reply; keeping it light for now."


class StanceLapseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        self.c = cc.Companion(hermes_root=root / "home", vault=root / "vault")
        # Midday, well clear of quiet hours (23:00-08:00 UTC by default).
        self.t0 = dt.datetime(2026, 9, 9, 12, 0, tzinfo=dt.timezone.utc)
        presence.update_wardrobe(
            self.c, [{"id": "jeans", "description": "jeans and a tee", "use": "day"}]
        )
        self.human = None
        thread = patch(
            "companion_thread.read",
            side_effect=lambda c, now=None, tail=4: (
                {"available": True, "last_from_human": self.human.isoformat()}
                if self.human
                else {"available": False}
            ),
        )
        thread.start()
        self.addCleanup(thread.stop)

    def write(self, at, previous=None, **kw):
        data = {
            "previous_id": previous,
            "outfit": ["jeans"],
            "location": "home",
            "activity": "reading",
            "mood": "fine",
            "care": [],
            "transition": "",
            "text": "Reading.",
        }
        data.update(kw)
        return presence.update(self.c, data, at)["episode"]

    def later(self, minutes):
        return self.t0 + dt.timedelta(minutes=minutes)

    def test_a_stance_carries_across_a_gap_with_no_conversation(self):
        first = self.write(self.t0, private_stance=HURT)
        presence.continue_scene(self.c, "Still reading.", now=self.later(30))
        presence.continue_scene(self.c, "Still reading.", now=self.later(60))
        state = presence.current(self.c)["state"]
        self.assertEqual(state["private_stance"], HURT)
        # It keeps the time it was first written, not the time it was last copied.
        self.assertEqual(state["stance_since"], first["state"]["stance_since"])
        self.assertEqual(state["stance_since"], self.t0.isoformat())

    def test_it_stays_while_they_are_talking_and_lapses_once_it_goes_quiet(self):
        self.write(self.t0, private_stance=HURT)
        scene = presence.current(self.c)
        self.human = self.later(60)
        shown, gone = presence.held(self.c, scene, self.later(65))
        self.assertEqual(shown["private_stance"], HURT)
        self.assertFalse(gone["private_stance"])
        shown, gone = presence.held(self.c, scene, self.later(90))
        self.assertEqual(shown["private_stance"], "")
        self.assertTrue(gone["private_stance"])

    def test_a_lapsed_stance_is_not_carried_by_code(self):
        self.write(self.t0, private_stance=HURT)
        self.human = self.later(60)
        presence.continue_scene(self.c, "Still reading.", now=self.later(90))
        state = presence.current(self.c)["state"]
        self.assertEqual(state["private_stance"], "")
        self.assertNotIn("stance_since", state)

    def test_rewording_a_stance_that_still_holds_does_not_restart_its_clock(self):
        first = self.write(self.t0, private_stance=HURT)
        reworded = self.write(
            self.later(30), first["id"], private_stance="Still stung; keeping it light."
        )
        self.assertEqual(reworded["state"]["stance_since"], self.t0.isoformat())
        self.human = self.later(45)
        shown, gone = presence.held(self.c, reworded, self.later(70))
        self.assertTrue(gone["private_stance"])

    def test_copied_back_word_for_word_it_is_dropped_and_new_words_are_kept(self):
        first = self.write(self.t0, private_stance=HURT)
        self.human = self.later(60)
        copied = self.write(self.later(90), first["id"], private_stance=HURT)
        self.assertEqual(copied["state"]["private_stance"], "")
        fresh = "Glad we talked; still a bit tender about it."
        again = self.write(self.later(105), copied["id"], private_stance=fresh)
        self.assertEqual(again["state"]["private_stance"], fresh)
        self.assertEqual(again["state"]["stance_since"], self.later(105).isoformat())

    def test_a_night_ends_a_stance_even_without_a_conversation(self):
        evening = self.t0.replace(hour=21)
        self.write(evening, private_stance=HURT)
        scene = presence.current(self.c)
        next_morning = evening + dt.timedelta(hours=12)
        shown, gone = presence.held(self.c, scene, next_morning)
        self.assertTrue(gone["private_stance"])
        self.assertEqual(shown["private_stance"], "")

    def test_the_job_summary_says_it_lapsed_without_repeating_it(self):
        self.write(self.t0, private_stance=HURT)
        self.human = self.later(60)
        text = active.right_now(self.c, self.later(90))
        self.assertNotIn(HURT, text)
        self.assertIn("lapsed", text)
        self.assertIn("new words", text)
        self.assertNotIn(HURT, presence.render_emotive(self.c, self.later(90)))

    def test_show_does_not_offer_a_lapsed_stance_to_copy(self):
        self.write(self.t0, private_stance=HURT)
        self.human = self.later(60)
        shown = presence.show(self.c, self.later(90))["current"]["state"]
        self.assertEqual(shown["private_stance"], "")

    def test_wants_lapse_one_by_one_after_six_hours(self):
        first = self.write(self.t0, wants=["finish the chapter"])
        second = self.write(
            self.later(5 * 60),
            first["id"],
            wants=["finish the chapter", "call a friend"],
        )
        since = second["state"]["wants_since"]
        self.assertEqual(since["finish the chapter"], self.t0.isoformat())
        self.assertEqual(since["call a friend"], self.later(5 * 60).isoformat())
        shown, gone = presence.held(
            self.c, presence.current(self.c), self.later(6 * 60 + 5)
        )
        self.assertEqual(gone["wants"], ["finish the chapter"])
        self.assertEqual(shown["wants"], ["call a friend"])
        presence.continue_scene(self.c, "Still reading.", now=self.later(6 * 60 + 5))
        self.assertEqual(presence.current(self.c)["state"]["wants"], ["call a friend"])

    def test_records_from_before_the_since_fields_are_dated_by_their_run(self):
        first = self.write(self.t0, private_stance=HURT, wants=["a long walk"])
        second = self.write(
            self.later(30),
            first["id"],
            private_stance="Same feeling, other words.",
            wants=["a long walk"],
        )
        # Strip the fields the way a record written by an older release lacks them.
        for row in (first, second):
            row["state"].pop("stance_since")
            row["state"].pop("wants_since")
        with patch.object(presence, "events", lambda c: iter([second, first])):
            self.assertEqual(presence._stance_since(self.c, second), self.t0)
            self.assertEqual(
                presence._wants_since(self.c, second), {"a long walk": self.t0}
            )


if __name__ == "__main__":
    unittest.main()
