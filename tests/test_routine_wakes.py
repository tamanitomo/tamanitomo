"""Her own routines' writes do not wake the next routine (#4); the conversation's still do.

Hermes keeps a monitored job's mark from BEFORE each run, so whatever a run wrote read
as a change on the next tick, and pulse and autonomy kept waking each other. A write
made inside a scheduled run carries HERMES_CRON_SESSION, which is how it is told apart.
"""

import datetime as dt
import pathlib
import tempfile
import unittest
from unittest import mock
from zoneinfo import ZoneInfo

import companion_config as cc
import companion_day
import companion_loops as loops
import companion_preread as preread
import companion_presence as presence

NOON = dt.datetime(2026, 9, 25, 12, 0, tzinfo=ZoneInfo("America/New_York"))


def line(fingerprint, name):
    return next(row for row in fingerprint.splitlines() if row.startswith(name + " "))


class RoutineWakeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        folder = pathlib.Path(self.tmp.name)
        self.c = cc.Companion(
            agent="Nova",
            human="Robin",
            hermes_root=folder / "home",
            vault=folder / "vault",
            timezone="America/New_York",
            quiet_start="23:00",
            quiet_end="08:00",
        )
        self.c.life.mkdir(parents=True, exist_ok=True)
        presence.update_wardrobe(
            self.c, [{"id": "tee", "description": "green tee", "use": "everyday"}]
        )
        self.scene("eating lunch", NOON, change=None)
        environment = mock.patch.dict("os.environ")
        environment.start()
        self.addCleanup(environment.stop)

    def routine(self):
        return mock.patch.dict("os.environ", {"HERMES_CRON_SESSION": "1"})

    def scene(self, activity, moment, change="transition", location="kitchen"):
        previous = presence.current(self.c)
        data = {
            "previous_id": previous["id"] if previous else None,
            "outfit": ["tee"],
            "location": location,
            "activity": activity,
            "mood": "content",
            "text": activity.capitalize() + ".",
        }
        if change:
            data.update(transition=activity.capitalize() + ".", activity_change=change)
        presence.update(self.c, data, moment)

    def test_a_routines_own_transition_leaves_the_awake_gate_shut(self):
        later = NOON + dt.timedelta(minutes=20)
        before = preread.fingerprint(self.c, later)
        with self.routine():
            self.scene("washing up", NOON + dt.timedelta(minutes=10))
        self.assertEqual(presence.current(self.c)["state"]["started_by"], "routine")
        self.assertEqual(
            line(preread.fingerprint(self.c, later), "scene"), line(before, "scene")
        )

    def test_a_transition_in_conversation_still_opens_it(self):
        later = NOON + dt.timedelta(minutes=20)
        before = preread.fingerprint(self.c, later)
        self.scene("washing up", NOON + dt.timedelta(minutes=10))
        self.assertEqual(presence.current(self.c)["state"]["started_by"], "other")
        self.assertNotEqual(
            line(preread.fingerprint(self.c, later), "scene"), line(before, "scene")
        )

    def test_a_conversation_move_after_routine_ones_is_still_seen(self):
        later = NOON + dt.timedelta(minutes=40)
        before = preread.fingerprint(self.c, later)
        with self.routine():
            self.scene("washing up", NOON + dt.timedelta(minutes=10))
            self.scene("reading on the sofa", NOON + dt.timedelta(minutes=20))
        self.assertEqual(
            line(preread.fingerprint(self.c, later), "scene"), line(before, "scene")
        )
        self.scene("on a walk", NOON + dt.timedelta(minutes=30), location="park")
        self.assertNotEqual(
            line(preread.fingerprint(self.c, later), "scene"), line(before, "scene")
        )

    def test_a_state_from_before_keeps_the_mark_the_gate_already_had(self):
        then = NOON.isoformat()
        previous = {
            "recorded_at": then,
            "state": {"activity": "reading", "location": "home", "started_at": then},
        }
        state = {"activity": "cooking", "location": "home"}
        data = {"activity": "cooking", "activity_change": "transition"}
        later = NOON + dt.timedelta(minutes=30)
        with self.routine():
            moved = companion_day.evolve(data, state, previous, later)
        self.assertEqual(moved["started_at"], later.isoformat())
        self.assertEqual(moved["unscheduled_since"], then)
        stayed = companion_day.evolve(
            {"activity": "reading"},
            {"activity": "reading", "location": "home"},
            previous,
            later,
        )
        self.assertEqual(stayed["unscheduled_since"], then)

    def loop(self, moment, follow_up="2026-09-26T09:00:00-04:00", **extra):
        return loops.add(
            self.c,
            {
                "id": extra.pop("id", "ask"),
                "title": "Ask how the trip went",
                "detail": "Back on Saturday",
                "gentle_use": "One warm question",
                "follow_up_at": follow_up,
                **extra,
            },
            moment,
        )

    def test_a_loop_her_routine_adds_or_closes_wakes_nothing(self):
        later = NOON + dt.timedelta(minutes=30)
        before = line(preread.fingerprint(self.c, later), "loops")
        with self.routine():
            self.loop(NOON + dt.timedelta(minutes=5))
            loops.update(
                self.c,
                {"id": "ask", "status": "closed"},
                NOON + dt.timedelta(minutes=10),
            )
        self.assertEqual(line(preread.fingerprint(self.c, later), "loops"), before)

    def test_a_loop_from_conversation_still_wakes_and_a_routine_closing_it_does_not(
        self,
    ):
        later = NOON + dt.timedelta(minutes=30)
        before = line(preread.fingerprint(self.c, later), "loops")
        self.loop(NOON + dt.timedelta(minutes=5))
        seen = line(preread.fingerprint(self.c, later), "loops")
        self.assertNotEqual(seen, before)
        with self.routine():
            loops.update(
                self.c,
                {"id": "ask", "status": "closed"},
                NOON + dt.timedelta(minutes=10),
            )
        self.assertEqual(line(preread.fingerprint(self.c, later), "loops"), seen)
        loops.update(
            self.c,
            {"id": "ask", "status": "closed", "note": "asked in chat"},
            NOON + dt.timedelta(minutes=15),
        )
        self.assertNotEqual(line(preread.fingerprint(self.c, later), "loops"), seen)

    def test_a_callback_coming_due_wakes_once_even_if_a_routine_then_closes_it(self):
        with self.routine():
            self.loop(NOON, follow_up="2026-09-25T13:00:00-04:00")
        early = line(
            preread.fingerprint(self.c, NOON + dt.timedelta(minutes=50)), "loops"
        )
        due = line(
            preread.fingerprint(self.c, NOON + dt.timedelta(minutes=65)), "loops"
        )
        self.assertNotEqual(due, early)
        with self.routine():
            loops.update(
                self.c,
                {"id": "ask", "status": "closed"},
                NOON + dt.timedelta(minutes=70),
            )
        self.assertEqual(
            line(preread.fingerprint(self.c, NOON + dt.timedelta(minutes=80)), "loops"),
            due,
        )


if __name__ == "__main__":
    unittest.main()
