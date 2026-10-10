"""Signals that must not invent anything: music, seasons, the single missing-you
measure, learned quiet hours, and meters that say "unknown" when they are."""

import contextlib
import datetime as dt
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import companion_bars as bars
import companion_config as cc
import companion_feelings as feelings
import companion_life as life
import companion_rhythm as rhythm
import companion_sensors as sensors
import companion_thread as thread

from tests.test_chat_dock import run_browser_contract

UTC = dt.timezone.utc


def companion(tmp, **extra):
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
    """rows: (profile_name, role, aware datetime). One session per profile."""
    with contextlib.closing(sqlite3.connect(c.home / "state.db")) as con, con:
        con.executescript(
            "CREATE TABLE sessions (id TEXT, source TEXT, profile_name TEXT);"
            "CREATE TABLE messages (session_id TEXT, role TEXT, content TEXT,"
            " timestamp REAL, _compressed_summary INTEGER);"
        )
        for profile in {row[0] for row in rows}:
            con.execute(
                "INSERT INTO sessions VALUES (?, 'telegram', ?)",
                (profile or "d", profile),
            )
        for profile, role, at in rows:
            con.execute(
                "INSERT INTO messages VALUES (?,?,?,?,0)",
                (profile or "d", role, "hi", at.timestamp()),
            )


def daytime_week(now, days=14, hours=range(8, 23), profile=""):
    """The human writes once an hour, 08:00-22:00 UTC, every day before `now`."""
    out = []
    for back in range(1, days + 1):
        day = (now - dt.timedelta(days=back)).replace(minute=0, second=0, microsecond=0)
        for hour in hours:
            out.append((profile, "user", day.replace(hour=hour)))
    return out


class MusicIsSilentWithoutSpotifyTests(unittest.TestCase):

    def test_no_connection_means_no_claim_and_no_stale_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = companion(tmp, sensors=["music"])
            now = dt.datetime(2026, 10, 5, 23, tzinfo=UTC)
            stale = c.soul_dir / "context-music.md"
            stale.write_text(
                "- Alex is playing something right now.\n", encoding="utf-8"
            )
            ambient = c.soul_dir / "ambient"
            ambient.mkdir(exist_ok=True)
            (ambient / "music.md").write_text("old\n", encoding="utf-8")
            text, why = sensors.music(c, now)
            self.assertIsNone(text)
            self.assertIn("not connected", why)
            self.assertFalse(stale.exists())
            result = sensors.run_one(c, "music", now)
            self.assertFalse(result["wrote"])
            self.assertFalse((ambient / "music.md").exists())
            self.assertNotIn("vibe", json.dumps(result).lower())


class SeasonsFollowTheHemisphereTests(unittest.TestCase):

    def test_timezone_decides_when_no_latitude_is_known(self):
        with tempfile.TemporaryDirectory() as tmp:
            july = dt.datetime(2026, 7, 15, 12, tzinfo=UTC)
            sydney = companion(tmp, timezone="Australia/Sydney")
            self.assertEqual(sensors.season_for(sydney, july), "winter")
            self.assertEqual(
                sensors.season_for(sydney, july.replace(month=1)), "summer"
            )
            london = companion(Path(tmp) / "l", timezone="Europe/London")
            self.assertEqual(sensors.season_for(london, july), "summer")

    def test_latitude_beats_timezone_and_the_tropics_say_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = companion(tmp, timezone="Europe/London")
            july = dt.datetime(2026, 7, 15, 12, tzinfo=UTC)
            weather = c.soul_dir / "ambient"
            weather.mkdir(exist_ok=True)
            (weather / "weather.json").write_text(json.dumps({"latitude": -37.8}))
            self.assertEqual(sensors.season_for(c, july), "winter")
            (weather / "weather.json").write_text(json.dumps({"latitude": 1.3}))
            self.assertIsNone(sensors.season_for(c, july))
            text, _ = sensors.daylight(c, july)
            self.assertNotIn(" in summer", text)
            self.assertNotIn(" in winter", text)

    def test_zone_coordinates_come_from_the_zone_table_not_a_list(self):
        self.assertLess(sensors.zone_latitude("America/Lima"), -10)
        self.assertGreater(sensors.zone_latitude("Europe/London"), 50)
        # Singapore is on the equator and "UTC" is nowhere: neither gets a season.
        self.assertLess(abs(sensors.zone_latitude("Asia/Singapore")), sensors.TROPICS)
        self.assertIsNone(sensors.zone_latitude("UTC"))
        self.assertIsNone(sensors.zone_latitude("Not/AZone"))

    def test_an_unknown_hemisphere_is_not_a_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = companion(tmp, timezone="UTC")
            self.assertIsNone(
                sensors.season_for(c, dt.datetime(2026, 7, 15, tzinfo=UTC))
            )

    def test_ideas_are_not_weighted_by_a_season_nobody_knows(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = companion(tmp)
            day = dt.date(2026, 7, 15)
            known = life.suggest(c.life, day, 3, season="winter")
            unknown = life.suggest(c.life, day, 3, season=None)
            self.assertEqual(known["season"], "winter")
            self.assertIsNone(unknown["season"])
            self.assertTrue(unknown["suggestions"])


class OneMissingYouMeasureTests(unittest.TestCase):

    def test_the_raw_hours_gap_bar_is_gone(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = companion(tmp)
            self.assertNotIn("feeling_the_gap", bars.compute(c))
            self.assertFalse(hasattr(bars, "FULL_GAP_HOURS"))

    def test_render_speaks_only_about_recorded_moods(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = companion(tmp)
            self.assertEqual(bars.render(c, {"wellbeing": None}), "")
            text = bars.render(c, {"wellbeing": 0.7, "moods_counted": 5})
            self.assertIn("70%", text)
            self.assertNotIn("gap", text.lower())
            self.assertNotIn("hours", text.lower())


class QuietHoursAreLearnedFromEvidenceTests(unittest.TestCase):

    def stamps(self, hours, days=14, odd=None):
        base = dt.datetime(2026, 10, 5, tzinfo=UTC)
        out = []
        for back in range(1, days + 1):
            for hour in hours:
                out.append(base - dt.timedelta(days=back) + dt.timedelta(hours=hour))
        for stamp in odd or []:
            out.append(stamp)
        return out

    def test_a_daytime_person_is_quiet_overnight(self):
        found = rhythm.quiet_window(self.stamps(range(8, 23)), UTC)
        self.assertEqual(found[:2], (23, 8))

    def test_one_stray_late_message_does_not_erase_the_night(self):
        stray = dt.datetime(2026, 10, 2, 3, 30, tzinfo=UTC)
        found = rhythm.quiet_window(self.stamps(range(8, 23), odd=[stray]), UTC)
        self.assertEqual(found[:2], (23, 8))

    def test_too_little_history_says_nothing(self):
        self.assertIsNone(rhythm.quiet_window(self.stamps(range(8, 23), days=5), UTC))
        self.assertIsNone(rhythm.quiet_window(self.stamps([9, 21], days=12), UTC))

    def test_no_quiet_stretch_says_nothing(self):
        self.assertIsNone(rhythm.quiet_window(self.stamps(range(24)), UTC))

    def test_a_window_is_capped_at_half_a_day(self):
        found = rhythm.quiet_window(self.stamps(range(19, 23), days=14) * 3, UTC)
        self.assertEqual((found[1] - found[0]) % 24, rhythm.MAX_QUIET_HOURS)

    def test_the_window_is_read_in_her_timezone(self):
        found = rhythm.quiet_window(
            self.stamps(range(8, 23)), dt.timezone(dt.timedelta(hours=-5))
        )
        self.assertEqual(found[:2], (18, 3))


class HumanTimesStayInsideTheCompanionsConversationsTests(unittest.TestCase):

    def test_another_profiles_messages_are_never_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = companion(tmp)
            now = dt.datetime(2026, 10, 5, 12, tzinfo=UTC)
            mine = now - dt.timedelta(hours=3)
            theirs = now - dt.timedelta(hours=2)
            messages_db(
                c,
                [
                    ("", "user", mine),
                    ("rowan", "user", theirs),
                    ("", "assistant", now - dt.timedelta(hours=1)),
                ],
            )
            got = thread.human_times(c, now)
            self.assertEqual([s.timestamp() for s in got], [mine.timestamp()])

    def test_nothing_older_than_the_window_and_no_database_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = companion(tmp)
            now = dt.datetime(2026, 10, 5, 12, tzinfo=UTC)
            self.assertEqual(thread.human_times(c, now), [])
            messages_db(c, [("", "user", now - dt.timedelta(days=40))])
            self.assertEqual(thread.human_times(c, now), [])


class SleepIsNotDistanceTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.c = companion(self.tmp.name, timezone="UTC")
        self.now = dt.datetime(2026, 10, 5, 8, 0, tzinfo=UTC)
        rows = daytime_week(self.now)
        # Last message 23:00 the night before; she is looking at 08:00.
        rows.append(("", "user", dt.datetime(2026, 10, 4, 23, 0, tzinfo=UTC)))
        messages_db(self.c, rows)

    def test_a_normal_night_leaves_almost_no_unexplained_time(self):
        state = feelings.compute(self.c, self.now)
        self.assertEqual(state["absence"]["hours"], 9.0)
        self.assertGreaterEqual(state["absence"]["expected_hours"], 8.0)
        self.assertLessEqual(state["absence"]["unexplained_hours"], 1.0)
        self.assertLess(state["meters"]["longing"], 0.05)
        self.assertEqual(state["learned_rhythm"]["start"], "23:00")
        self.assertEqual(state["learned_rhythm"]["end"], "08:00")

    def test_turning_learning_off_counts_the_night_again(self):
        current = feelings.settings(self.c)
        feelings.save_settings(
            self.c, {**current["settings"], "learn_rhythm": False}, current["revision"]
        )
        state = feelings.compute(self.c, self.now)
        self.assertIsNone(state["learned_rhythm"])
        self.assertEqual(state["absence"]["expected_hours"], 0)
        self.assertGreater(state["meters"]["longing"], 0.1)

    def test_real_absence_still_registers_after_the_nights_are_subtracted(self):
        later = self.now + dt.timedelta(days=4)
        state = feelings.compute(self.c, later)
        self.assertGreaterEqual(state["absence"]["unexplained_hours"], 59)
        self.assertGreater(state["meters"]["longing"], 0.8)

    def test_entered_windows_are_kept_alongside_the_learned_one(self):
        current = feelings.settings(self.c)
        feelings.save_settings(
            self.c,
            {
                **current["settings"],
                "absence_windows": [
                    {
                        "label": "Work",
                        "days": [0, 1, 2, 3, 4],
                        "start": "09:00",
                        "end": "17:00",
                    }
                ],
            },
            current["revision"],
        )
        state = feelings.compute(self.c, self.now)
        self.assertIsNotNone(state["learned_rhythm"])
        self.assertEqual(
            sum(1 for w in feelings.settings(self.c)["settings"]["absence_windows"]), 1
        )

    def test_the_setting_must_be_a_boolean(self):
        current = feelings.settings(self.c)
        with self.assertRaises(ValueError):
            feelings.save_settings(
                self.c,
                {**current["settings"], "learn_rhythm": "yes"},
                current["revision"],
            )
        self.assertTrue(feelings.settings(self.c)["settings"]["learn_rhythm"])


def test_home_meters_show_an_empty_meter_as_zero_not_a_resting_number():
    run_browser_contract(r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('kit/app/static/product.js', 'utf8');
const start = source.indexOf('function renderHeroMetersContent');
const end = source.indexOf('/* A change of closeness level');
const meters = fs.readFileSync('kit/app/static/feelings.js', 'utf8');
const list = meters.slice(meters.indexOf('const FEELING_METERS'), meters.indexOf('function feelingMeters'));
vm.runInThisContext(`
const esc=value=>String(value);
${list}
${source.slice(start, end)}
globalThis.render=renderHeroMetersContent;
`);
const empty = render({}, {});
assert.equal((empty.match(/hero-meter-pct">0%</g) || []).length, 5, 'every empty meter reads 0%');
assert.equal((empty.match(/width:0%/g) || []).length, 5, 'and its bar is empty');
assert.ok(!empty.includes('—'), 'no dash');
const known = render({state: {meters: {warmth: 0.65, trust: 0.5, hurt: 0, irritation: 0.1, longing: null}}}, {});
assert.ok(known.includes('65%') && known.includes('50%'));
assert.equal((known.match(/hero-meter-pct">0%</g) || []).length, 2, 'a real zero and a missing value both read 0%');
assert.ok(!/hero-meter-pct">8\d%/.test(empty), 'never a resting number');
""")
