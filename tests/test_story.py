"""Phase 1: what she can notice, the dates she keeps, and the story she must not contradict."""

import contextlib
import datetime as dt
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import companion_canon as canon
import companion_config as cc
import companion_context as context
import companion_feelings as feelings
import companion_notes as notes
import companion_places as places
import companion_rhythm as rhythm
import companion_sensors as sensors
import companion_story as story
import companion_thread as thread
import companion_together as together

UTC = dt.timezone.utc


def companion(tmp, **extra):
    extra.setdefault("timezone", "UTC")
    c = cc.Companion(
        agent="Nova",
        human="Alex",
        hermes_root=Path(tmp) / "h",
        vault=Path(tmp) / "v",
        **extra,
    )
    c.home.mkdir(parents=True)
    c.life.mkdir(parents=True)
    c.soul_dir.mkdir(parents=True, exist_ok=True)
    return c


def messages_db(c, rows):
    """rows: (role, aware datetime, text). One telegram session, root profile."""
    with contextlib.closing(sqlite3.connect(c.home / "state.db")) as con, con:
        con.executescript(
            "CREATE TABLE sessions (id TEXT, source TEXT, profile_name TEXT);"
            "CREATE TABLE messages (session_id TEXT, role TEXT, content TEXT,"
            " timestamp REAL, _compressed_summary INTEGER);"
            "INSERT INTO sessions VALUES ('t', 'telegram', '');"
        )
        for role, at, text in rows:
            con.execute(
                "INSERT INTO messages VALUES ('t',?,?,?,0)",
                (role, text, at.timestamp()),
            )


def at(day, hour, minute=0):
    return dt.datetime(2026, 10, day, hour, minute, tzinfo=UTC)


class ThreadHelpersTests(unittest.TestCase):

    def test_a_message_that_ends_on_a_question_is_waiting_for_an_answer(self):
        self.assertEqual(
            thread.last_question("Want to grab dinner?"), "Want to grab dinner?"
        )
        self.assertEqual(thread.last_question("Really?? 😊"), "Really??")
        self.assertEqual(thread.last_question('So... you coming?"'), "you coming?")
        self.assertEqual(thread.last_question("Want dinner? Or not."), "")
        self.assertEqual(thread.last_question("Hi."), "")
        self.assertEqual(thread.last_question(""), "")

    def test_counts_and_lengths_come_from_the_database_without_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = companion(tmp)
            now = at(5, 12)
            messages_db(
                c,
                [
                    ("user", at(1, 9), "hello there"),
                    ("assistant", at(1, 9, 5), "hi"),
                    ("user", at(3, 22), "x" * 40),
                ],
            )
            rows = thread.activity(c, now)
            self.assertEqual(
                [(r, n) for r, _s, n in rows],
                [("user", 40), ("assistant", 2), ("user", 11)],
            )
            self.assertEqual(
                thread.contact_days(c, now),
                {dt.date(2026, 10, 1): (1, 1), dt.date(2026, 10, 3): (1, 0)},
            )
            self.assertEqual(thread.first_contact(c, now), at(1, 9))

    def test_the_whole_history_is_counted_but_only_this_companions(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = companion(tmp)
            messages_db(c, [("user", at(1, 9), "hi")])
            with contextlib.closing(sqlite3.connect(c.home / "state.db")) as con, con:
                con.execute("INSERT INTO sessions VALUES ('o','telegram','rowan')")
                con.execute(
                    "INSERT INTO messages VALUES ('o','user','secret',?,0)",
                    (at(2, 9).timestamp(),),
                )
            self.assertEqual(
                list(thread.contact_days(c, at(5, 12))), [dt.date(2026, 10, 1)]
            )
            self.assertEqual(thread.first_contact(c, at(5, 12)), at(1, 9))


class ObservationsTests(unittest.TestCase):

    def stamp_rows(self, days_back, hour, count=1):
        base = at(5, 12)
        return [
            (base - dt.timedelta(days=d)).replace(hour=hour, minute=m)
            for d in days_back
            for m in range(count)
        ]

    def test_late_nights_are_counted_this_week_against_a_usual_week(self):
        now = at(5, 12)
        daytime = self.stamp_rows(range(0, 27), 14)
        late = self.stamp_rows([1, 2, 4, 5], 1)
        count, typical = rhythm.late_nights(daytime + late, (0, 5), now)
        self.assertEqual(count, 4)
        self.assertEqual(typical, 0.0)

    def test_the_late_hours_of_one_night_belong_to_one_night(self):
        now = at(5, 12)
        stamps = [at(3, 23, 30), at(4, 0, 15), at(4, 1, 0)]
        self.assertEqual(rhythm.late_nights(stamps, (23, 5), now)[0], 1)

    def test_a_much_shorter_day_is_noticed_and_an_ordinary_one_is_not(self):
        now = at(5, 18)
        usual = [
            ("user", at(5, 12) - dt.timedelta(days=d), 100)
            for d in range(1, 21)
            for _ in range(2)
        ]
        short = usual + [("user", at(5, 9 + i), 12) for i in range(6)]
        found = rhythm.writing_style(short, now)
        self.assertEqual(found, ("shorter", 12, 100))
        same = usual + [("user", at(5, 9 + i), 90) for i in range(6)]
        self.assertIsNone(rhythm.writing_style(same, now))
        self.assertIsNone(rhythm.writing_style(usual + [("user", at(5, 9), 5)], now))

    def test_she_knows_when_a_question_was_left_hanging(self):
        now = at(5, 18)
        asked = {
            "who": "you",
            "at": at(5, 12).isoformat(),
            "text": "dinner?",
            "asks": "dinner?",
        }
        # Nothing came back.
        found = rhythm.unanswered([asked], now)
        self.assertEqual(
            (found["question"], found["replied"], found["hours"]),
            ("dinner?", False, 6.0),
        )
        # The next message came five hours later: not claimed to be an answer.
        late = {"who": "them", "at": at(5, 17).isoformat(), "text": "hey", "asks": ""}
        found = rhythm.unanswered([asked, late], now)
        self.assertTrue(found["replied"])
        self.assertEqual(found["hours"], 5.0)
        # An ordinary chat reply is not "leaving".
        quick = {
            "who": "them",
            "at": at(5, 12, 4).isoformat(),
            "text": "yes",
            "asks": "",
        }
        self.assertIsNone(rhythm.unanswered([asked, quick], now))
        # Her own message did not ask anything.
        plain = {**asked, "asks": ""}
        self.assertIsNone(rhythm.unanswered([plain], now))

    def test_the_observations_never_claim_a_mood(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = companion(tmp)
            now = at(5, 18)
            rows = [("assistant", at(5, 12), "Do you want to come over tonight?")]
            messages_db(c, rows)
            text = rhythm.render(c, now)
            self.assertIn("Do you want to come over tonight?", text)
            self.assertIn("has not written back", text)
            self.assertIn("Do not say why", text)
            for word in ("stressed", "upset", "sad", "angry", "feel"):
                self.assertNotIn(word, text.replace("do not claim a mood", ""))


class SlowChangeTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.c = companion(self.tmp.name)
        self.now = at(20, 12)

    def talk(self, days, human=4, hers=2, start=1):
        rows = []
        for d in range(days):
            day = start + d
            rows += [("user", at(day, 9 + i), "x") for i in range(human)]
            rows += [("assistant", at(day, 9, 30 + i), "y") for i in range(hers)]
        return rows

    def test_without_conversation_nothing_moves(self):
        state = feelings.compute(self.c, self.now)
        self.assertEqual(state["meters"]["warmth"], 0.65)
        self.assertEqual(state["meters"]["trust"], 0.7)
        self.assertEqual(state["slow_change"]["contact_days"], 0)

    def test_days_of_real_two_way_conversation_raise_warmth_and_trust_slowly(self):
        messages_db(self.c, self.talk(10))
        state = feelings.compute(self.c, self.now)
        self.assertEqual(state["slow_change"]["contact_days"], 10)
        self.assertGreater(state["meters"]["warmth"], 0.65)
        self.assertGreater(state["meters"]["trust"], 0.7)
        # Slowly: ten days of chat is a nudge, not a transformation.
        self.assertLess(state["meters"]["warmth"], 0.85)
        self.assertLess(state["meters"]["trust"], 0.76)

    def test_one_sided_days_do_not_count(self):
        messages_db(self.c, self.talk(10, hers=0) + self.talk(3, human=1, start=12))
        state = feelings.compute(self.c, self.now)
        self.assertEqual(state["slow_change"]["contact_days"], 0)

    def test_it_is_capped(self):
        rows = []
        for month_day in range(1, 29):
            rows += self.talk(1, start=month_day)
        messages_db(self.c, rows)
        slow = feelings.compute(self.c, at(30, 12))["slow_change"]
        self.assertLessEqual(slow["warmth"], feelings.WARMTH_CAP)
        self.assertLessEqual(
            slow["trust"], feelings.TRUST_CAP + feelings.TRUST_KEPT_CAP
        )

    def test_warmth_fades_when_the_talking_stops_but_trust_stays(self):
        messages_db(self.c, self.talk(10))
        soon = feelings.compute(self.c, at(12, 12))
        later = feelings.compute(self.c, at(12, 12) + dt.timedelta(days=60))
        self.assertLess(later["meters"]["warmth"], soon["meters"]["warmth"])
        self.assertEqual(later["slow_change"]["trust"], soon["slow_change"]["trust"])

    def test_an_unrepaired_rupture_stops_trust_building(self):
        messages_db(self.c, self.talk(10))
        open_trust = feelings.compute(self.c, self.now)["meters"]["trust"]
        feelings.record(
            self.c,
            {
                "kind": "rupture",
                "topic": "promise",
                "text": "Broke a promise about Friday.",
                "evidence": "Alex: I said I would come and I did not.",
                "strength": 0.6,
                "at": at(11, 9).isoformat(),
            },
            self.now,
        )
        state = feelings.compute(self.c, self.now)
        self.assertTrue(state["slow_change"]["paused_by_unrepaired_rupture"])
        self.assertEqual(state["slow_change"]["trust"], 0.0)
        self.assertLess(state["meters"]["trust"], open_trust)

    def test_a_kept_request_adds_a_little_trust(self):
        import companion_missions as missions

        base = feelings.compute(self.c, self.now)["meters"]["trust"]
        entry = missions.add(
            self.c,
            {"title": "Find the flight", "detail": "Raleigh to Denver"},
            self.now,
        )
        missions.update(
            self.c, entry["entry"]["id"], "done", "Found two options.", self.now
        )
        self.assertGreater(feelings.compute(self.c, self.now)["meters"]["trust"], base)


class DatesAreCountedTests(unittest.TestCase):

    def test_monthly_and_day_marks_come_from_the_start_date(self):
        begin = dt.date(2026, 7, 8)
        found = together.milestones(begin, dt.date(2026, 10, 3), horizon=7)
        labels = {label: when for when, label in found}
        self.assertEqual(labels["3-month anniversary"], dt.date(2026, 10, 8))
        self.assertNotIn("100 days together", labels)
        self.assertEqual(
            [
                label
                for _w, label in together.milestones(
                    begin, dt.date(2026, 10, 14), horizon=3
                )
            ],
            ["100 days together"],
        )

    def test_a_month_that_is_too_short_lands_on_its_last_day(self):
        self.assertEqual(
            together.add_months(dt.date(2026, 1, 31), 1), dt.date(2026, 2, 28)
        )
        self.assertEqual(
            together.add_months(dt.date(2026, 1, 31), 13), dt.date(2027, 2, 28)
        )

    def test_a_year_is_an_anniversary_not_twelve_months(self):
        labels = [
            l
            for _w, l in together.milestones(
                dt.date(2025, 10, 8), dt.date(2026, 10, 8), 0
            )
        ]
        self.assertIn("1-year anniversary", labels)
        self.assertFalse(any("12-month" in l for l in labels))

    def test_the_start_is_the_first_message_unless_one_was_entered(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = companion(tmp)
            now = at(5, 12)
            self.assertIsNone(together.start(c, now)[0])
            messages_db(c, [("user", at(1, 9), "hi")])
            self.assertEqual(
                together.start(c, now), (dt.date(2026, 10, 1), "first message")
            )
            together.write(c, since="2026-03-14")
            self.assertEqual(together.start(c, now), (dt.date(2026, 3, 14), "entered"))
            with self.assertRaises(ValueError):
                together.write(c, since="March")

    def test_a_birthday_needs_the_words_it_came_from(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = companion(tmp)
            with self.assertRaisesRegex(ValueError, "words it came from"):
                together.write(c, human_birthday="03-14")
            with self.assertRaises(ValueError):
                together.write(c, human_birthday="02-31", evidence="said so")
            together.write(
                c, human_birthday="1990-10-07", evidence="Alex: my birthday is Oct 7th"
            )
            when, label = together.birthday(c, dt.date(2026, 10, 5))
            self.assertEqual(when, dt.date(2026, 10, 7))
            self.assertIn("turning 36", label)
            self.assertIsNone(together.birthday(c, dt.date(2026, 9, 1)))

    def test_traditions_are_counted_from_when_they_began(self):
        begun = dt.date(2024, 12, 24)
        self.assertEqual(
            together.occurrence(begun, "yearly", dt.date(2026, 12, 20)),
            (dt.date(2026, 12, 24), 3),
        )
        self.assertEqual(
            together.occurrence(begun, "yearly", dt.date(2026, 12, 25)),
            (dt.date(2027, 12, 24), 4),
        )
        self.assertEqual(
            together.occurrence(dt.date(2026, 9, 5), "monthly", dt.date(2026, 10, 3)),
            (dt.date(2026, 10, 5), 2),
        )
        self.assertEqual(
            together.occurrence(dt.date(2026, 9, 1), "weekly", dt.date(2026, 9, 9)),
            (dt.date(2026, 9, 15), 3),
        )

    def test_a_recorded_ritual_shows_up_before_it_comes_round(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = companion(tmp)
            now = at(5, 12)
            notes.add_moment(
                c,
                {
                    "moment": "ritual",
                    "text": "Baking the same cookies on Christmas Eve",
                    "recurs": "yearly",
                    "first_on": "2024-12-24",
                    "evidence": "Alex: we always do the cookies",
                },
                now,
            )
            self.assertIn(
                "the 3rd time",
                together.render(c, dt.datetime(2026, 12, 20, tzinfo=UTC))[0],
            )
            self.assertIn("yearly, since 2024-12-24", notes.render_relationship(c))
            self.assertEqual(together.traditions(c, dt.date(2026, 6, 1)), [])

    def test_recurrence_is_only_for_rituals_and_needs_a_beginning(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = companion(tmp)
            now = at(5, 12)
            with self.assertRaises(ValueError):
                notes.add_moment(
                    c,
                    {
                        "moment": "joke",
                        "text": "x",
                        "recurs": "yearly",
                        "first_on": "2025-01-01",
                    },
                    now,
                )
            with self.assertRaises(ValueError):
                notes.add_moment(
                    c, {"moment": "ritual", "text": "x", "recurs": "yearly"}, now
                )
            with self.assertRaises(ValueError):
                notes.add_moment(
                    c,
                    {
                        "moment": "ritual",
                        "text": "x",
                        "recurs": "daily",
                        "first_on": "2025-01-01",
                    },
                    now,
                )

    def test_the_together_sense_writes_nothing_without_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = companion(tmp, sensors=["together"])
            result = sensors.run_one(c, "together", at(5, 12))
            self.assertFalse(result["wrote"])
            messages_db(c, [("user", at(1, 9), "hi")])
            result = sensors.run_one(c, "together", at(5, 12))
            self.assertTrue(result["wrote"])
            text = (c.soul_dir / "ambient/together.md").read_text(encoding="utf-8")
            self.assertIn("first talked on 2026-10-01", text)
            self.assertIn("4 days ago", text)


class HolidaysTests(unittest.TestCase):

    API_ROWS = [
        {
            "date": "2026-10-12",
            "localName": "Columbus Day",
            "name": "Columbus Day",
            "global": True,
        },
        {
            "date": "2026-10-09",
            "localName": "Regional Day",
            "name": "Regional",
            "global": False,
        },
        {
            "date": "2026-12-25",
            "localName": "Christmas Day",
            "name": "Christmas Day",
            "global": True,
        },
    ]

    def test_the_country_comes_from_her_timezone_and_only_it_is_sent(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = companion(tmp, timezone="America/New_York")
            calls = []

            def fake(url, timeout=0):
                calls.append(url)
                return json.dumps(self.API_ROWS)

            with patch.object(sensors, "_get", fake):
                text, extra = sensors.holidays(c, at(8, 12))
            self.assertEqual(
                calls, ["https://date.nager.at/api/v3/PublicHolidays/2026/US"]
            )
            self.assertIn("Columbus Day — in 4 days (2026-10-12)", text)
            self.assertNotIn("Regional", text)
            self.assertEqual(extra["country"], "US")

    def test_a_year_is_fetched_once_and_offline_is_silent(self):
        import urllib.error

        with tempfile.TemporaryDirectory() as tmp:
            c = companion(tmp, timezone="America/New_York")
            with patch.object(
                sensors, "_get", lambda url, timeout=0: json.dumps(self.API_ROWS)
            ):
                sensors.holidays(c, at(8, 12))

            def boom(url, timeout=0):
                raise urllib.error.URLError("offline")

            with patch.object(sensors, "_get", boom):
                text, _ = sensors.holidays(c, at(8, 12))
                self.assertIn("Columbus Day", text)  # from the kept copy
            other = companion(Path(tmp) / "o", timezone="America/New_York")
            with patch.object(sensors, "_get", boom):
                text, why = sensors.holidays(other, at(8, 12))
            self.assertIsNone(text)
            self.assertIn("offline", why)

    def test_no_country_no_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = companion(tmp, timezone="UTC")
            text, why = sensors.holidays(c, at(8, 12))
            self.assertIsNone(text)
            self.assertIn("country", why)

    def test_nothing_this_week_is_not_a_holiday(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = companion(tmp, timezone="America/New_York")
            with patch.object(
                sensors, "_get", lambda url, timeout=0: json.dumps(self.API_ROWS)
            ):
                text, _ = sensors.holidays(c, at(20, 12))
            self.assertIsNone(text)


class CanonTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.c = companion(self.tmp.name)
        self.now = at(5, 12)

    def test_what_she_says_about_her_past_is_fixed_once_told(self):
        first = canon.add(
            self.c,
            {"topic": "Sister", "statement": "Maya, two years older, lives in Denver."},
            self.now,
        )
        self.assertTrue(first["written"])
        refused = canon.add(
            self.c,
            {"topic": "sister", "statement": "Priya, her younger sister."},
            self.now,
        )
        self.assertFalse(refused["written"])
        self.assertEqual(refused["conflict"][0]["id"], first["entry"]["id"])
        self.assertIn("--supersedes", refused["reason"])
        self.assertEqual(len(canon.canon(self.c)), 1)

    def test_a_revision_keeps_the_old_statement_in_the_history(self):
        first = canon.add(
            self.c, {"topic": "sister", "statement": "Maya lives in Denver."}, self.now
        )
        revised = canon.add(
            self.c,
            {
                "topic": "sister",
                "statement": "Maya moved to Boulder last spring.",
                "supersedes": first["entry"]["id"],
            },
            self.now,
        )
        self.assertTrue(revised["written"])
        self.assertEqual(
            [r["statement"] for r in canon.canon(self.c)],
            ["Maya moved to Boulder last spring."],
        )
        history = canon.canon(self.c, None)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["status"], "superseded")
        self.assertEqual(history[0]["superseded_by"], revised["entry"]["id"])

    def test_an_addition_sits_beside_what_was_said(self):
        canon.add(self.c, {"topic": "sister", "statement": "Maya is older."}, self.now)
        canon.add(
            self.c,
            {"topic": "sister", "statement": "She teaches piano.", "also": True},
            self.now,
        )
        self.assertEqual(len(canon.canon(self.c)), 2)

    def test_retrying_is_harmless_and_bad_requests_are_rejected(self):
        entry = {"topic": "hometown", "statement": "Duluth, Minnesota."}
        canon.add(self.c, entry, self.now)
        again = canon.add(self.c, {**entry, "also": True}, self.now)
        self.assertFalse(again["written"])
        self.assertEqual(len(canon.canon(self.c)), 1)
        with self.assertRaises(ValueError):
            canon.add(
                self.c, {"topic": "x", "statement": "y", "supersedes": "nope"}, self.now
            )
        with self.assertRaises(ValueError):
            canon.add(
                self.c,
                {"topic": "x", "statement": "y", "also": True, "supersedes": "z"},
                self.now,
            )

    def test_it_is_kept_apart_from_what_is_known_about_the_human(self):
        canon.add(
            self.c,
            {"topic": "job", "statement": "Left a bakery job at twenty-two."},
            self.now,
        )
        self.assertTrue((self.c.life / "canon.jsonl").exists())
        self.assertFalse((self.c.human_dir / "facts.jsonl").exists())


class PlacesTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.c = companion(self.tmp.name, location="Raleigh, NC")
        self.now = at(5, 12)

    def set_home(self):
        return places.add(
            self.c,
            {
                "home": True,
                "description": "A 1950s brick rancher with a screened porch.",
                "rooms": [
                    "Kitchen=yellow tile, a window over the sink",
                    "Study=books to the ceiling",
                ],
            },
            self.now,
        )

    def test_home_has_a_floor_plan_and_is_described_once(self):
        self.assertTrue(self.set_home()["written"])
        h = places.home(self.c)
        self.assertEqual([r["name"] for r in h["rooms"]], ["Kitchen", "Study"])
        again = self.set_home()
        self.assertFalse(again["written"])
        self.assertIn("detail command", again["reason"])
        self.assertEqual(len(places.places(self.c)), 1)

    def test_rooms_can_be_added_later_without_rewriting_the_home(self):
        self.set_home()
        places.add_room(self.c, "Porch=green rocking chair", self.now)
        self.assertEqual(len(places.home(self.c)["rooms"]), 3)
        self.assertFalse(places.add_room(self.c, "porch=anything", self.now)["written"])
        homeless = companion(Path(self.tmp.name) / "x")
        with self.assertRaisesRegex(ValueError, "describe your home first"):
            places.add_room(homeless, "Attic=dusty", self.now)

    def test_a_venue_is_recorded_the_first_time_and_then_only_added_to(self):
        out = places.add(
            self.c,
            {
                "name": "The Corner Bookstore",
                "description": "Narrow shop on Hillsborough St.",
                "details": ["Bell over the door"],
            },
            self.now,
        )
        place_id = out["entry"]["id"]
        again = places.add(
            self.c,
            {"name": "the corner bookstore", "description": "Totally different."},
            self.now,
        )
        self.assertFalse(again["written"])
        places.add_detail(
            self.c,
            place_id,
            "A grey cat named Pages sleeps on the poetry shelf",
            self.now,
        )
        self.assertFalse(
            places.add_detail(self.c, place_id, "bell over the door", self.now)[
                "written"
            ]
        )
        shop = places.places(self.c)[0]
        self.assertEqual(shop["description"], "Narrow shop on Hillsborough St.")
        self.assertEqual(len(shop["details"]), 2)

    def test_only_the_home_has_a_floor_plan(self):
        with self.assertRaisesRegex(ValueError, "only your home"):
            places.add(
                self.c,
                {"name": "Gym", "description": "x", "rooms": ["Pool=cold"]},
                self.now,
            )

    def test_a_readable_copy_is_kept_beside_the_ledger(self):
        self.set_home()
        places.add(
            self.c,
            {
                "name": "Gym",
                "description": "Basement gym.",
                "details": ["Smells of chalk"],
            },
            self.now,
        )
        text = (self.c.life / "places.md").read_text(encoding="utf-8")
        self.assertIn("## Home (home)", text)
        self.assertIn("**Kitchen**", text)
        self.assertIn("Smells of chalk", text)
        self.assertIn("Editing this file changes nothing", text)
        self.assertTrue(places.render(self.c).startswith("- [home] Home (your home)"))


class StoryInContextTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.c = companion(
            self.tmp.name,
            location="Raleigh, NC",
            context_tokens=200000,
            context_mode="fixed",
        )
        self.now = at(5, 18)

    def test_she_is_asked_to_describe_a_home_until_she_has(self):
        text = context.build(self.c, now=self.now)
        self.assertIn("Keeping your story straight", text)
        self.assertIn("You have not described your home yet", text)
        self.assertIn("in Raleigh, NC", text)
        places.add(
            self.c,
            {
                "home": True,
                "description": "A brick rancher.",
                "rooms": ["Kitchen=yellow"],
            },
            self.now,
        )
        text = context.build(self.c, now=self.now)
        self.assertNotIn("You have not described your home yet", text)
        self.assertIn("A brick rancher.", text)
        self.assertIn("Kitchen — yellow", text)

    def test_what_she_has_told_is_carried_and_the_commands_are_real(self):
        canon.add(
            self.c, {"topic": "hometown", "statement": "Duluth, Minnesota."}, self.now
        )
        text = context.build(self.c, now=self.now)
        self.assertIn("hometown: Duluth, Minnesota.", text)
        for script in (
            "companion_canon.py",
            "companion_places.py",
            "companion_notes.py",
            "companion_together.py",
        ):
            self.assertIn(script, text)
            self.assertTrue((Path(story.__file__).parent / script).exists())

    def test_observations_ride_along_when_there_is_something_to_notice(self):
        messages_db(self.c, [("assistant", at(5, 10), "Are you coming tonight?")])
        text = context.build(self.c, now=self.now)
        self.assertIn("Are you coming tonight?", text)
        self.assertIn("has not written back", text)

    def test_while_answering_a_live_message_she_is_never_told_they_have_not_written(
        self,
    ):
        messages_db(self.c, [("assistant", at(5, 10), "Are you coming tonight?")])
        live = {"extra": {"user_message": "hey, sorry, long day"}}
        text = context.build(self.c, payload=live, now=self.now)
        self.assertNotIn("has not written back", text)

    def test_nothing_is_added_when_the_relationship_indicators_are_off(self):
        self.c.bars = False
        messages_db(self.c, [("assistant", at(5, 10), "Are you coming tonight?")])
        self.assertNotIn("has not written back", context.build(self.c, now=self.now))

    def test_a_scheduled_run_sees_her_places_but_not_her_tool_instructions(self):
        self.assertEqual(story.scheduled(self.c), story.HOME_MISSING)
        places.add(self.c, {"name": "Gym", "description": "Basement gym."}, self.now)
        block = story.scheduled(self.c)
        self.assertIn("Basement gym.", block)
        self.assertIn("[place-gym-", block)
        self.assertNotIn("set-home", block)
        places.add(
            self.c,
            {"home": True, "description": "A flat.", "rooms": ["Kitchen=small"]},
            self.now,
        )
        self.assertNotIn("not on record", story.scheduled(self.c))

    def test_a_small_window_says_what_it_left_out_instead_of_dropping_it_silently(self):
        small = companion(
            Path(self.tmp.name) / "s", context_tokens=8000, context_mode="fixed"
        )
        canon.add(
            small, {"topic": "hometown", "statement": "Duluth, Minnesota."}, self.now
        )
        text = context.build(small, now=self.now)
        self.assertIn("your places and history", text)
        self.assertNotIn("Keeping your story straight", text)


class PlaceInPresenceTests(unittest.TestCase):
    """Where she is, as a field she sets, so one kitchen is one kitchen."""

    def setUp(self):
        import companion_presence as presence

        self.presence = presence
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.c = companion(self.tmp.name)
        presence.update_wardrobe(
            self.c, [{"id": "jeans", "description": "blue jeans", "use": "day"}]
        )
        self.now = at(5, 9)
        self.step = 0

    def write(self, location, **extra):
        self.step += 1
        current = self.presence.current(self.c)
        record = {
            "previous_id": current["id"] if current else None,
            "outfit": ["jeans"],
            "location": location,
            "activity": f"something {self.step}",
            "mood": "fine",
            "care": [],
            "transition": "walked over" if current else "",
            "text": "An ordinary moment.",
            **extra,
        }
        when = self.now + dt.timedelta(minutes=20 * self.step)
        self.presence.update(self.c, record, when)
        return self.presence.current(self.c)["state"]

    def describe_home(self):
        return self.write(
            "home, kitchen",
            home={
                "description": "A small flat over a bakery.",
                "rooms": ["Kitchen=narrow, yellow tiles", "Bedroom=a skylight"],
            },
            room="kitchen",
        )

    def test_before_her_home_is_on_record_nothing_is_refused(self):
        self.write("the kitchen")
        state = self.write("the park")
        self.assertNotIn("place", state)

    def test_describing_her_home_records_it_and_puts_her_in_a_room(self):
        state = self.describe_home()
        self.assertEqual((state["place"], state["room"]), ("home", "Kitchen"))
        home = places.home(self.c)
        self.assertEqual([r["name"] for r in home["rooms"]], ["Kitchen", "Bedroom"])

    def test_once_home_is_on_record_a_move_must_say_where(self):
        self.describe_home()
        with self.assertRaisesRegex(ValueError, "say where you are") as raised:
            self.write("the bedroom")
        self.assertIn("Kitchen, Bedroom", str(raised.exception))
        state = self.write("the bedroom", room="Bedroom")
        self.assertEqual((state["place"], state["room"]), ("home", "Bedroom"))

    def test_staying_put_carries_the_place(self):
        self.describe_home()
        state = self.write("home, kitchen")
        self.assertEqual((state["place"], state["room"]), ("home", "Kitchen"))

    def test_a_new_room_joins_the_floor_plan(self):
        self.describe_home()
        state = self.write("the little study", place="home", room="Study")
        self.assertEqual(state["room"], "Study")
        self.assertIn("Study", [r["name"] for r in places.home(self.c)["rooms"]])

    def test_somewhere_new_is_described_once_and_visited_by_id(self):
        self.describe_home()
        state = self.write(
            "Larkin's Books on the high street",
            new_place={"name": "Larkin's Books", "description": "Two narrow floors."},
        )
        shop = state["place"]
        self.assertTrue(shop.startswith("place-larkin-s-books-"))
        self.write("home, kitchen", room="Kitchen")
        self.assertEqual(self.write("the bookshop", place=shop)["place"], shop)
        again = self.write(
            "the bookshop again",
            new_place={"name": "larkin's books", "description": "Different words."},
        )
        self.assertEqual(again["place"], shop)
        self.assertEqual(len(places.places(self.c)), 2)

    def test_what_cannot_be_is_refused_with_the_choices(self):
        self.describe_home()
        with self.assertRaisesRegex(ValueError, "no place 'place-nowhere'"):
            self.write("somewhere", place="place-nowhere")
        places.add(self.c, {"name": "Gym", "description": "Basement."}, self.now)
        gym = places.places(self.c)[-1]["id"]
        with self.assertRaisesRegex(ValueError, "rooms belong to your home"):
            self.write("the gym pool", place=gym, room="Pool")

    def test_out_and_about_needs_no_description(self):
        self.describe_home()
        self.assertEqual(
            self.write("walking by the river", place="out")["place"], "out"
        )

    def test_a_check_writes_no_places(self):
        current = self.presence.current(self.c)
        self.presence.check(
            self.c,
            {
                "previous_id": current["id"] if current else None,
                "outfit": ["jeans"],
                "location": "home",
                "activity": "a check",
                "mood": "fine",
                "care": [],
                "transition": "",
                "text": "x",
                "home": {"description": "A flat.", "rooms": ["Kitchen=small"]},
            },
            self.now,
        )
        self.assertIsNone(places.home(self.c))

    def test_the_short_form_says_where_too(self):
        self.describe_home()
        state = self.presence.transition_scene(
            self.c,
            "browsing",
            "walked to the market",
            "Stalls everywhere.",
            location="the Saturday market",
            new_place={"name": "Saturday market", "description": "Stalls on a lot."},
            now=self.now + dt.timedelta(hours=3),
        )
        self.assertTrue(state["written"] is not False)
        here = self.presence.current(self.c)["state"]
        self.assertTrue(here["place"].startswith("place-saturday-market-"))
        with self.assertRaisesRegex(ValueError, "say where you are"):
            self.presence.transition_scene(
                self.c,
                "heading home",
                "walked back",
                "Tired feet.",
                location="the walk home",
                now=self.now + dt.timedelta(hours=4),
            )

    def test_a_picture_of_a_place_looks_like_the_place(self):
        import companion_portrait as portrait

        self.describe_home()
        scene, _ = portrait.scene_block(self.c)
        self.assertIn("the kitchen: narrow, yellow tiles", scene)
        self.write(
            "Larkin's Books",
            new_place={"name": "Larkin's Books", "description": "Two narrow floors."},
        )
        scene, _ = portrait.scene_block(self.c)
        self.assertIn("Larkin's Books: Two narrow floors.", scene)
