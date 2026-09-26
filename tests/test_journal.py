"""Historical days, reflections, photo albums, and read-only archive access."""

import copy
import datetime as dt
import hashlib
import json
import os
import pathlib
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import companion_checkin as checkin
import companion_config as cc
import companion_journal as journal
import companion_life as life
import companion_local_reflection as reflection
import companion_self as slf
import companion_timeline as tl
from fastapi.testclient import TestClient

from kit.app import journal_archive as ja
from kit.app.server import build

ROOT = Path(__file__).resolve().parents[1]


class JournalTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        self.c = cc.Companion(
            agent="Nova", human="Alex", hermes_root=root / "home", vault=root / "vault"
        )

    def test_append_preserves_history_and_retries_without_duplicates(self):
        path = journal.path_for(self.c, "daily")
        path.parent.mkdir(parents=True)
        path.write_text("## 2026-09-10\nAn older entry.\n")
        data = {
            "date": "2026-09-11",
            "text": "Today's thought has an apostrophe and $HOME.",
        }
        self.assertTrue(journal.append(self.c, "daily", data)["written"])
        self.assertFalse(journal.append(self.c, "daily", data)["written"])
        self.assertIn("An older entry.", path.read_text())
        self.assertEqual(path.read_text().count("## 2026-09-11"), 1)
        with self.assertRaises(ValueError):
            journal.append(self.c, "daily", {**data, "text": "different"})

    def test_legacy_dated_entries_are_not_duplicated(self):
        path = journal.path_for(self.c, "daily")
        path.parent.mkdir(parents=True)
        original = "## 2026-09-11\nWritten before this helper existed.\n"
        path.write_text(original)
        self.assertFalse(
            journal.append(
                self.c, "daily", {"date": "2026-09-11", "text": "New draft"}
            )["written"]
        )
        self.assertEqual(path.read_text(), original)

    def test_empty_stub_is_filled_but_a_real_entry_is_never_overwritten(self):
        path = journal.path_for(self.c, "daily")
        path.parent.mkdir(parents=True)
        path.write_text(
            "## 2026-09-11\n<!-- companion-journal:daily-2026-09-11 -->\n<!-- /companion-journal:daily-2026-09-11 -->\n"
        )
        first = journal.append(
            self.c, "daily", {"date": "2026-09-11", "text": "The real entry."}
        )
        self.assertTrue(first["written"])
        self.assertEqual(first.get("replaced"), "empty stub")
        self.assertIn("The real entry.", path.read_text())
        with self.assertRaises(ValueError):
            journal.append(
                self.c, "daily", {"date": "2026-09-11", "text": "A rewrite."}
            )
        self.assertIn("The real entry.", path.read_text())
        path.write_text(
            "## 2026-09-12\n<!-- companion-journal:daily-2026-09-12 -->\n   \n<!-- /companion-journal:daily-2026-09-12 -->\n"
        )
        with self.assertRaises(ValueError):
            journal.append(self.c, "daily", {"date": "2026-09-12", "text": "Body."})

    def test_tail_discloses_omissions_and_invalid_targets_are_refused(self):
        journal.append(
            self.c,
            "autonomy",
            {"date": "2026-09-11", "id": "run-1", "text": "x" * 1000},
        )
        got = journal.tail(self.c, "autonomy", 500)
        self.assertEqual(len(got["text"]), 500)
        self.assertGreater(got["omitted_chars"], 0)
        with self.assertRaises(ValueError):
            journal.path_for(self.c, "../../SOUL.md")
        with self.assertRaises(ValueError):
            journal.append(
                self.c, "autonomy", {"date": "2026-09-11", "text": "Missing id"}
            )


NY = ZoneInfo("America/New_York")
TOKEN = "journal-token"


def at(text, tz=NY):
    return dt.datetime.fromisoformat(text).replace(tzinfo=tz)


def state(activity, location="home", mood="calm", confirmed=True):
    return {
        "activity": activity,
        "location": location,
        "mood": mood,
        "outfit": ["tee"],
        "transition": "",
        "confirmed": confirmed,
    }


class Fixture:
    """Two companions in one Hermes root; nova keeps a New York clock."""

    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="journal-")
        base = Path(self._tmp.name)
        self.root = base / "hermes"
        vault = base / "vault"
        self.root.mkdir()
        vault.mkdir()
        self.nova = cc.Companion(
            agent="Nova",
            human="Alex",
            profile="nova",
            hermes_root=self.root,
            vault=vault,
            soul_in_vault=False,
            context_mode="fixed",
            timezone="America/New_York",
        )
        self.rowan = cc.Companion(
            agent="Rowan",
            human="Alex",
            profile="rowan",
            hermes_root=self.root,
            vault=vault,
            soul_in_vault=False,
            context_mode="fixed",
            timezone="America/New_York",
        )
        for c in (self.nova, self.rowan):
            c.home.mkdir(parents=True)
            c.life.mkdir(parents=True, exist_ok=True)
            c.soul_dir.mkdir(parents=True, exist_ok=True)
            c.save()
        self.client = TestClient(
            build(self.root, token=TOKEN, state_dir=base / "state")
        )

    def close(self):
        self._tmp.cleanup()

    def get(self, path, profile="nova"):
        return self.client.get(
            path, params={"profile": profile}, headers={"x-companion-token": TOKEN}
        )

    def scene(self, c, when, activity, ident, status="in_progress", text=None, **kw):
        return life.record(
            c.life,
            text or f"{activity}.",
            activity,
            status,
            when,
            ident,
            c.agent,
            c.human,
            state=state(activity, **kw),
        )["episode"]

    def capture(self, c, episode, ident, colour="green"):
        from PIL import Image

        folder = c.data / "image-timeline"
        (folder / "captures").mkdir(parents=True, exist_ok=True)
        (folder / "images").mkdir(parents=True, exist_ok=True)
        name = ident + ".png"
        Image.new("RGB", (8, 8), colour).save(folder / "images" / name)
        (folder / "captures" / f"{ident}.json").write_text(
            json.dumps(
                {
                    "id": ident,
                    "created_at": episode["recorded_at"],
                    "status": "saved",
                    "scene": episode,
                    "filename": name,
                    "primary_filename": name,
                    "variants": [{"filename": name}],
                }
            )
        )
        return name

    def reflection(self, c, day, text):
        path = c.soul_dir / "Lifelog.md"
        old = path.read_text() if path.exists() else ""
        path.write_text(old + f"\n## {day}\n\n{text}\n")


def tree(path):
    """Every file under a profile with its bytes and mtime: the mutation witness."""
    out = {}
    for p in sorted(Path(path).rglob("*")):
        if p.is_file() and (not p.is_symlink()):
            st = p.stat()
            out[str(p.relative_to(path))] = (
                hashlib.sha256(p.read_bytes()).hexdigest(),
                st.st_mtime_ns,
            )
    return out


class HistoricalDay(unittest.TestCase):
    """Test 1: a past date with scenes, a genuinely associated photo and reflection text."""

    def setUp(self):
        self.f = Fixture()
        self.addCleanup(self.f.close)
        n = self.f.nova
        self.walk = self.f.scene(
            n,
            at("2026-09-20T09:00"),
            "walking to the market",
            "walk-1",
            location="market street",
        )
        self.f.scene(
            n,
            at("2026-09-20T09:15"),
            "walking to the market",
            "walk-2",
            location="market street",
        )
        self.read = self.f.scene(
            n, at("2026-09-20T11:00"), "reading", "read-1", location="library"
        )
        self.photo = self.f.capture(n, self.read, "a" * 24)
        self.f.capture(n, {**self.walk, "id": "walk-2"}, "b" * 24, "blue")
        self.f.reflection(
            n, "2026-09-20", "A slow **market** morning, then the library."
        )
        self.f.reflection(n, "2026-09-19", "The day before.")

    def test_day_and_reflection_agree_on_date_and_sources(self):
        r = self.f.get("/api/journal/archive/2026-09-20")
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(d["day"], "2026-09-20")
        self.assertEqual(
            [s["activity"] for s in d["scenes"]], ["walking to the market", "reading"]
        )
        walk, read = d["scenes"]
        self.assertEqual(walk["snapshots"], 2)
        self.assertEqual(walk["ids"], ["walk-1", "walk-2"])
        self.assertEqual(walk["until"], read["at"])
        self.assertIsNone(read["until"])
        self.assertEqual([p["capture_id"] for p in read["photos"]], ["a" * 24])
        self.assertEqual([p["capture_id"] for p in walk["photos"]], ["b" * 24])
        self.assertTrue(
            read["photos"][0]["url"].startswith("/api/content/file?path=image-timeline")
        )
        self.assertIn("not evidence about Alex", read["provenance"])
        self.assertEqual(d["reflection"]["state"], "available")
        (entry,) = d["reflection"]["entries"]
        self.assertEqual((entry["day"], entry["source"]), ("2026-09-20", "Lifelog.md"))
        full = self.f.get("/api/journals/" + entry["id"]).json()["entry"]
        self.assertEqual(full["day"], d["day"])
        self.assertIn("**market**", full["text"])
        rows = life.read_events(self.f.nova.life, "2026-09-20", limit=0)
        self.assertEqual([x["id"] for x in rows], ["walk-1", "walk-2", "read-1"])

    def test_index_marks_days_with_records(self):
        d = self.f.get("/api/journal/archive").json()
        self.assertEqual(d["days"]["2026-09-20"], {"scenes": True, "reflection": True})
        self.assertEqual(d["days"]["2026-09-19"], {"scenes": False, "reflection": True})

    def test_reading_writes_nothing_and_calls_no_model(self):
        before = (tree(self.f.root), tree(self.f.nova.vault))
        calls = []

        def refuse(*a, **k):
            calls.append(a)
            raise AssertionError("archive reads must not start a process")

        with (
            patch.object(subprocess, "run", refuse),
            patch.object(subprocess, "Popen", refuse),
            patch.object(os, "system", refuse),
        ):
            for path in (
                "/api/journal/archive",
                "/api/journal/archive/2026-09-20",
                "/api/journal/archive/2026-09-19",
                "/api/journals?limit=1000",
                "/api/journal/archive/2031-01-01",
            ):
                self.assertEqual(self.f.get(path).status_code, 200, path)
        self.assertEqual(calls, [])
        self.assertEqual((tree(self.f.root), tree(self.f.nova.vault)), before)


class TruthfulStates(unittest.TestCase):
    """Test 2: empty profile, no reflection, unreadable sources, planned/unconfirmed, no false links."""

    def setUp(self):
        self.f = Fixture()
        self.addCleanup(self.f.close)

    def test_new_profile_is_honestly_empty(self):
        d = self.f.get("/api/journal/archive/2026-09-20").json()
        self.assertEqual(d["scenes"], [])
        self.assertEqual(d["sources"], {"scenes": "none", "photos": "available"})
        self.assertEqual(
            d["reflection"], {"state": "none", "entries": [], "warnings": []}
        )
        self.assertEqual(d["plan"]["state"], "none")
        self.assertEqual(d["together"], {"state": "none", "moments": []})
        self.assertEqual(self.f.get("/api/journal/archive").json()["days"], {})

    def test_scenes_without_reflection(self):
        self.f.scene(self.f.nova, at("2026-09-21T08:00"), "coffee", "c-1")
        d = self.f.get("/api/journal/archive/2026-09-21").json()
        self.assertEqual(len(d["scenes"]), 1)
        self.assertEqual(d["reflection"]["state"], "none")

    def test_unreadable_scene_file_is_unavailable_not_empty(self):
        folder = self.f.nova.life / "episodes"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "2026-09-22.jsonl").mkdir()
        d = self.f.get("/api/journal/archive/2026-09-22").json()
        self.assertEqual(d["sources"]["scenes"], "unavailable")
        self.assertEqual(d["scenes"], [])

    def test_unreadable_journal_is_unavailable_not_absent(self):
        (self.f.nova.soul_dir / "Lifelog.md").write_bytes(
            b"## 2026-09-22\n\n\xff\xfe broken"
        )
        d = self.f.get("/api/journal/archive/2026-09-22").json()
        self.assertEqual(d["reflection"]["state"], "unavailable")
        self.assertTrue(d["reflection"]["warnings"])

    def test_corrupt_capture_record_is_unavailable(self):
        ep = self.f.scene(self.f.nova, at("2026-09-22T10:00"), "painting", "p-1")
        self.f.capture(self.f.nova, ep, "c" * 24)
        (
            self.f.nova.data / "image-timeline/captures" / ("d" * 24 + ".json")
        ).write_text("{not json")
        d = self.f.get("/api/journal/archive/2026-09-22").json()
        self.assertEqual(d["sources"]["photos"], "unavailable")
        self.assertEqual(d["scenes"][0]["photos"], [])

    def test_deleted_photo_is_reported_missing_not_relinked(self):
        ep = self.f.scene(self.f.nova, at("2026-09-22T10:00"), "painting", "p-1")
        name = self.f.capture(self.f.nova, ep, "c" * 24)
        (self.f.nova.data / "image-timeline/images" / name).unlink()
        (scene,) = self.f.get("/api/journal/archive/2026-09-22").json()["scenes"]
        self.assertEqual((scene["photos"], scene["missing_photos"]), ([], 1))

    def test_a_neighbouring_file_does_not_make_an_empty_day_look_recorded(self):
        self.f.scene(self.f.nova, at("2026-09-21T12:00"), "next day", "n-1")
        d = self.f.get("/api/journal/archive/2026-09-20").json()
        self.assertEqual((d["scenes"], d["sources"]["scenes"]), ([], "none"))

    def test_a_scan_limited_library_is_partial_not_missing(self):
        from kit.app import content

        ep = self.f.scene(self.f.nova, at("2026-09-22T10:00"), "painting", "p-1")
        self.f.capture(self.f.nova, ep, "c" * 24)
        with patch.object(
            content, "catalog", lambda *a, **k: {"items": [], "scan_limited": True}
        ):
            d = self.f.get("/api/journal/archive/2026-09-22").json()
        self.assertEqual(d["sources"]["photos"], "partial")
        self.assertEqual(
            (d["scenes"][0]["photos"], d["scenes"][0]["missing_photos"]), ([], 0)
        )

    def test_planned_skipped_and_carried_forward_keep_their_meaning(self):
        n = self.f.nova
        self.f.scene(n, at("2026-09-23T08:00"), "yoga", "y-1")
        self.f.scene(n, at("2026-09-23T08:30"), "yoga", "y-2", confirmed=False)
        self.f.scene(n, at("2026-09-23T08:45"), "yoga", "y-3", confirmed=False)
        life.record(
            n.life,
            "Will bake later.",
            "baking",
            "planned",
            at("2026-09-23T09:00"),
            "plan-1",
            n.agent,
            n.human,
        )
        life.record(
            n.life,
            "Did not swim.",
            "swimming",
            "skipped",
            at("2026-09-23T10:00"),
            "skip-1",
            n.agent,
            n.human,
        )
        plans = n.life / "plans"
        plans.mkdir()
        (plans / "2026-09-23.json").write_text(
            json.dumps(
                {
                    "intent": "A quiet day",
                    "items": [
                        {
                            "start": "14:00",
                            "end": "15:00",
                            "what": "visit the gallery",
                            "status": "planned",
                            "kind": "intended",
                        }
                    ],
                }
            )
        )
        d = self.f.get("/api/journal/archive/2026-09-23").json()
        self.assertEqual(
            [(s["activity"], s["status"], s["snapshots"]) for s in d["scenes"]],
            [
                ("yoga", "recorded", 1),
                ("yoga", "carried_forward", 2),
                ("baking", "planned", 1),
                ("swimming", "skipped", 1),
            ],
        )
        self.assertEqual(d["plan"]["state"], "available")
        self.assertEqual(d["plan"]["items"][0]["what"], "visit the gallery")

    def test_same_date_media_and_authored_activity_make_no_association(self):
        n = self.f.nova
        ep = self.f.scene(
            n,
            at("2026-09-24T15:00"),
            "having coffee with Alex",
            "coffee-1",
            text="Coffee with Alex.",
        )
        from PIL import Image

        (n.data / "creations").mkdir(parents=True)
        Image.new("RGB", (8, 8), "red").save(n.data / "creations/same-day.png")
        stamp = at("2026-09-24T15:05").timestamp()
        os.utime(n.data / "creations/same-day.png", (stamp, stamp))
        ghost = {**ep, "id": "gone-1", "state": state("stretching")}
        self.f.capture(n, ghost, "e" * 24)
        d = self.f.get("/api/journal/archive/2026-09-24").json()
        (scene,) = d["scenes"]
        self.assertEqual(scene["photos"], [])
        self.assertEqual([x["activity"] for x in d["unplaced_photos"]], ["stretching"])
        self.assertEqual(d["together"], {"state": "none", "moments": []})
        self.assertIn("not evidence about Alex", scene["provenance"])

    def test_you_two_only_from_an_explicit_dated_moment(self):
        import companion_notes as notes

        now = dt.datetime(2026, 9, 25, tzinfo=dt.timezone.utc)
        notes.add_moment(
            self.f.nova,
            {
                "moment": "first",
                "text": "First picnic together",
                "happened_on": "2026-09-24",
            },
            now,
        )
        notes.add_moment(
            self.f.nova,
            {
                "moment": "joke",
                "text": "The umbrella joke",
                "happened_on": "last spring",
            },
            now,
        )
        notes.add_moment(self.f.nova, {"moment": "ritual", "text": "Sunday calls"}, now)
        self.assertEqual(
            [
                m["text"]
                for m in self.f.get("/api/journal/archive/2026-09-24").json()[
                    "together"
                ]["moments"]
            ],
            ["First picnic together"],
        )
        self.assertEqual(
            self.f.get("/api/journal/archive/2026-09-25").json()["together"]["moments"],
            [],
        )


class Dates(unittest.TestCase):
    """Test 3: the profile's timezone decides the day, across midnight and DST."""

    def setUp(self):
        self.f = Fixture()
        self.addCleanup(self.f.close)

    def test_midnight_uses_the_profile_clock_not_the_file_name(self):
        n = self.f.nova
        self.f.scene(
            n,
            dt.datetime(2026, 9, 21, 3, 30, tzinfo=dt.timezone.utc),
            "late tea",
            "tea-1",
        )
        self.f.scene(n, at("2026-09-21T00:10"), "asleep", "sleep-1")
        self.assertTrue((n.life / "episodes/2026-09-21.jsonl").exists())
        on20 = self.f.get("/api/journal/archive/2026-09-20").json()["scenes"]
        on21 = self.f.get("/api/journal/archive/2026-09-21").json()["scenes"]
        self.assertEqual([s["activity"] for s in on20], ["late tea"])
        self.assertEqual([s["activity"] for s in on21], ["asleep"])
        self.assertTrue(on20[0]["at"].startswith("2026-09-20T23:30"))
        days = self.f.get("/api/journal/archive").json()["days"]
        self.assertIn("2026-09-20", days)

    def test_daylight_saving_boundaries(self):
        n = self.f.nova
        self.f.scene(n, at("2026-03-08T01:30"), "before the jump", "s-1")
        self.f.scene(
            n,
            dt.datetime(2026, 3, 8, 7, 30, tzinfo=dt.timezone.utc),
            "after the jump",
            "s-2",
        )
        self.f.scene(n, at("2026-03-08T23:59"), "last minute", "s-3")
        spring = self.f.get("/api/journal/archive/2026-03-08").json()["scenes"]
        self.assertEqual(
            [s["activity"] for s in spring],
            ["before the jump", "after the jump", "last minute"],
        )
        self.assertTrue(spring[1]["at"].startswith("2026-03-08T03:30:00-04:00"))
        self.assertEqual(spring[0]["until"], spring[1]["at"])
        self.f.scene(
            n,
            dt.datetime(2026, 11, 1, 5, 30, tzinfo=dt.timezone.utc),
            "first 1:30",
            "f-1",
        )
        self.f.scene(
            n,
            dt.datetime(2026, 11, 1, 6, 30, tzinfo=dt.timezone.utc),
            "second 1:30",
            "f-2",
        )
        self.f.scene(
            n,
            dt.datetime(2026, 11, 2, 4, 30, tzinfo=dt.timezone.utc),
            "still the 1st",
            "f-3",
        )
        fall = self.f.get("/api/journal/archive/2026-11-01").json()["scenes"]
        self.assertEqual(
            [s["activity"] for s in fall],
            ["first 1:30", "second 1:30", "still the 1st"],
        )
        self.assertEqual(
            [s["at"][11:] for s in fall[:2]], ["01:30:00-04:00", "01:30:00-05:00"]
        )

    def test_date_only_and_invalid_values_get_no_invented_time(self):
        folder = self.f.nova.life / "episodes"
        folder.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                "id": "d-1",
                "kind": "imagined_episode",
                "recorded_at": "2026-09-26",
                "status": "in_progress",
                "activity": "date only",
                "text": "x",
                "state": state("date only"),
            },
            {
                "id": "d-2",
                "kind": "imagined_episode",
                "recorded_at": "not a time",
                "status": "in_progress",
                "activity": "garbled",
                "text": "x",
                "state": state("garbled"),
            },
            {
                "id": "d-3",
                "kind": "imagined_episode",
                "recorded_at": "2026-09-26T10:00:00",
                "status": "in_progress",
                "activity": "naive",
                "text": "x",
                "state": state("naive"),
            },
        ]
        (folder / "2026-09-26.jsonl").write_text(
            "".join((json.dumps(r) + "\n" for r in rows))
        )
        (folder / "2026-09-27.jsonl").write_text(
            json.dumps({**rows[1], "id": "d-4", "activity": "elsewhere"}) + "\n"
        )
        scenes = self.f.get("/api/journal/archive/2026-09-26").json()["scenes"]
        self.assertEqual(
            [(s["activity"], s["at"], s["time_known"]) for s in scenes],
            [
                ("date only", None, False),
                ("garbled", None, False),
                ("naive", None, False),
            ],
        )
        for bad in ("2026-02-30", "26-09-2026", "2026-9-1", "today"):
            self.assertEqual(
                self.f.get("/api/journal/archive/" + bad).status_code, 400, bad
            )

    def test_local_helpers(self):
        self.assertIsNone(ja.local_moment("2026-09-26", NY))
        self.assertIsNone(ja.local_moment("2026-09-26T10:00:00", NY))
        self.assertIsNone(ja.local_moment(None, NY))
        self.assertEqual(ja.local_day("2026-09-27T01:00:00+00:00", NY), "2026-09-26")
        self.assertEqual(ja.parse_day("2024-02-29"), dt.date(2024, 2, 29))


class Isolation(unittest.TestCase):
    """Test 4 (server side): each profile reads only its own records."""

    def setUp(self):
        self.f = Fixture()
        self.addCleanup(self.f.close)

    def test_profiles_do_not_see_each_other(self):
        ep = self.f.scene(self.f.nova, at("2026-09-20T09:00"), "nova only", "n-1")
        self.f.capture(self.f.nova, ep, "f" * 24)
        self.f.reflection(self.f.nova, "2026-09-20", "Nova wrote this.")
        self.f.scene(self.f.rowan, at("2026-09-20T09:00"), "rowan only", "r-1")
        nova = self.f.get("/api/journal/archive/2026-09-20", "nova").json()
        rowan = self.f.get("/api/journal/archive/2026-09-20", "rowan").json()
        self.assertEqual([s["activity"] for s in nova["scenes"]], ["nova only"])
        self.assertEqual([s["activity"] for s in rowan["scenes"]], ["rowan only"])
        self.assertEqual(rowan["scenes"][0]["photos"], [])
        self.assertEqual(rowan["reflection"]["state"], "none")
        self.assertEqual(rowan["agent"], "Rowan")
        self.assertNotIn(
            "2026-09-20",
            {
                k
                for k, v in self.f.get("/api/journal/archive", "rowan")
                .json()["days"]
                .items()
                if v["reflection"]
            },
        )

    def test_token_is_required(self):
        r = self.f.client.get(
            "/api/journal/archive/2026-09-20", params={"profile": "nova"}
        )
        self.assertEqual(r.status_code, 401)

    def test_linked_episode_file_is_not_followed(self):
        other = Path(self.f._tmp.name) / "elsewhere.jsonl"
        other.write_text(
            json.dumps(
                {
                    "id": "x",
                    "kind": "imagined_episode",
                    "recorded_at": "2026-09-20T09:00:00-04:00",
                    "status": "in_progress",
                    "activity": "foreign",
                    "text": "x",
                    "state": state("foreign"),
                }
            )
            + "\n"
        )
        folder = self.f.nova.life / "episodes"
        folder.mkdir(parents=True, exist_ok=True)
        try:
            (folder / "2026-09-20.jsonl").symlink_to(other)
        except OSError:
            self.skipTest("Symlinks unavailable")
        d = self.f.get("/api/journal/archive/2026-09-20").json()
        self.assertEqual(d["scenes"], [])
        self.assertEqual(d["sources"]["scenes"], "unavailable")


TZ = dt.timezone.utc


def png(size=1):
    """A real one-pixel PNG, repeated to reach a size."""
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (size, size), (120, 140, 160)).save(buf, "PNG")
    return buf.getvalue()


class AlbumFixture(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        self.c = cc.Companion(
            agent="Nova",
            human="Alex",
            hermes_root=root / "h",
            vault=root / "v",
            image_timeline=True,
            timeline_budget_gb=0,
        )
        (tl.root(self.c) / "captures").mkdir(parents=True, exist_ok=True)
        (tl.root(self.c) / "images").mkdir(parents=True, exist_ok=True)
        self.now = dt.datetime(2026, 9, 10, 12, 0, tzinfo=TZ)

    def capture(self, ident, when, size=40):
        data = png(size)
        name = ident + ".png"
        (tl.root(self.c) / "images" / name).write_bytes(data)
        row = {
            "id": ident,
            "created_at": when.isoformat(),
            "status": "saved",
            "filename": name,
            "scene": {
                "recorded_at": when.isoformat(),
                "state": {
                    "activity": "reading",
                    "location": "home",
                    "outfit": [{"id": "x", "description": "blue pajamas"}],
                    "mood": "quiet",
                },
            },
            "image_style": "anime-modern",
            "image_style_guidance": "x",
        }
        (tl.root(self.c) / "captures" / (ident + ".json")).write_text(json.dumps(row))
        return row


class BudgetTests(AlbumFixture):

    def test_a_budget_drops_the_oldest_first_and_says_how_much_it_freed(self):
        ids = [f"{i:024x}" for i in range(5)]
        for n, ident in enumerate(ids):
            self.capture(ident, self.now - dt.timedelta(hours=10 - n), size=60)
        used = tl.prune(self.c, self.now)["bytes_used"]
        self.c.timeline_budget_gb = used / 2 / 1000000000
        report = tl.prune(self.c, self.now)
        self.assertGreater(report["removed"], 0)
        self.assertGreater(report["freed_bytes"], 0)
        self.assertLessEqual(report["bytes_used"], report["budget_bytes"])
        left = {r["id"] for _, r in tl.records(self.c)}
        self.assertNotIn(ids[0], left)
        self.assertIn(ids[-1], left)

    def test_with_no_budget_the_calendar_still_bounds_it(self):
        self.capture("a" * 24, self.now - dt.timedelta(days=40))
        self.capture("b" * 24, self.now - dt.timedelta(days=2))
        report = tl.prune(self.c, self.now)
        self.assertEqual(report["removed"], 1)
        self.assertEqual(report["retention_days"], tl.DAYS)

    def test_a_capture_that_never_landed_is_marked_failed_not_kept_pending(self):
        row = {
            "id": "c" * 24,
            "created_at": (self.now - dt.timedelta(hours=2)).isoformat(),
            "status": "pending",
            "scene": {},
            "image_style": "x",
            "image_style_guidance": "y",
        }
        (tl.root(self.c) / "captures" / ("c" * 24 + ".json")).write_text(
            json.dumps(row)
        )
        tl.prune(self.c, self.now)
        after = json.loads(
            (tl.root(self.c) / "captures" / ("c" * 24 + ".json")).read_text()
        )
        self.assertEqual(after["status"], "failed")

    def test_a_negative_budget_is_refused_at_configuration_time(self):
        with self.assertRaisesRegex(ValueError, "timeline_budget_gb"):
            cc.Companion(timeline_budget_gb=-1)


class AlbumTests(AlbumFixture):

    def test_keeping_one_copies_it_and_leaves_the_original(self):
        ident = "d" * 24
        self.capture(ident, self.now)
        result = tl.favorite(self.c, ident)
        self.assertTrue(pathlib.Path(result["file"]).is_file())
        self.assertTrue((tl.root(self.c) / "images" / (ident + ".png")).is_file())
        self.assertIn("Copied, not moved", result["note"])

    def test_an_album_copy_survives_the_budget_taking_the_original(self):
        ident = "e" * 24
        self.capture(ident, self.now - dt.timedelta(days=40))
        kept = pathlib.Path(tl.favorite(self.c, ident)["file"])
        tl.prune(self.c, self.now)
        self.assertFalse((tl.root(self.c) / "images" / (ident + ".png")).exists())
        self.assertTrue(kept.is_file())

    def test_the_copy_carries_the_moment_it_came_from(self):
        ident = "f" * 24
        self.capture(ident, self.now)
        result = tl.favorite(self.c, ident)
        caption = pathlib.Path(result["file"] + ".txt").read_text()
        self.assertIn("reading at home", caption)

    def test_a_person_can_add_their_own_pictures(self):
        source = pathlib.Path(self.tmp.name) / "mine.png"
        source.write_bytes(png(8))
        result = tl.add_to_album(self.c, source, "Trip to Lisbon")
        self.assertTrue(pathlib.Path(result["file"]).is_file())
        self.assertEqual([a["name"] for a in tl.albums(self.c)], ["Trip to Lisbon"])

    def test_album_names_cannot_escape_the_vault(self):
        for bad in ("../escape", "", ".", " /etc"):
            with self.assertRaises(ValueError):
                tl.favorite(self.c, "a" * 24, bad)

    def test_only_a_saved_capture_can_be_kept(self):
        ident = "0" * 24
        row = {
            "id": ident,
            "created_at": self.now.isoformat(),
            "status": "failed",
            "scene": {},
            "image_style": "x",
            "image_style_guidance": "y",
        }
        (tl.root(self.c) / "captures" / (ident + ".json")).write_text(json.dumps(row))
        with self.assertRaisesRegex(ValueError, "saved"):
            tl.favorite(self.c, ident)


def empty(text="A quiet day of reading, in my own imagined life."):
    return dict(
        reflection=text,
        preferences=[],
        questions=[],
        facts=[],
        standing=[],
        moments=[],
        answers=[],
        open_loops=[],
        soul_append="",
    )


class ReflectionTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        self.c = cc.Companion(
            agent="Nova",
            human="Alex",
            hermes_root=root / "home",
            vault=root / "vault",
            timezone="UTC",
        )
        self.c.home.mkdir(parents=True)
        self.c.soul_dir.mkdir(parents=True)
        self.c.soul.write_text(
            "A companion.\n" + slf.BEGIN + "\nI like books.\n" + slf.END + "\n"
        )
        self.now = dt.datetime(2026, 9, 12, 11, tzinfo=dt.timezone.utc)

    def db(self):
        db = sqlite3.connect(self.c.home / "state.db")
        db.executescript(
            "CREATE TABLE sessions(id TEXT, source TEXT,user_id TEXT); CREATE TABLE messages(id INTEGER,session_id TEXT,role TEXT,content TEXT,timestamp REAL,active INTEGER,compacted INTEGER,_compressed_summary INTEGER);"
        )
        db.execute("INSERT INTO sessions VALUES (?,?,?)", ("chat", "telegram", "human"))
        db.execute("INSERT INTO sessions VALUES (?,?,?)", ("cron", "cron", "human"))
        return db

    def test_evidence_is_exact_user_quote_and_dates_are_code_owned(self):
        source = {
            "1": {
                "id": "1",
                "role": "user",
                "content": "My sister is Bee.",
                "timestamp": self.now.timestamp(),
                "session_id": "chat",
            }
        }
        plan = empty()
        plan["facts"] = [
            {
                "quote_id": "1",
                "category": "people",
                "statement": "Alex's sister is Bee.",
            }
        ]
        reflection.validate(plan, "daily", source, [], "Alex")
        reflection.apply_plan(self.c, "daily", "2026-09-11", plan, source, self.now)
        self.assertIn("## 2026-09-11", journal.path_for(self.c, "daily").read_text())
        fact = slf.facts(self.c.human_dir)[0]
        self.assertEqual(fact["statement"], "Alex's sister is Bee.")
        self.assertTrue(
            fact["evidence"].endswith(": My sister is Bee."),
            "the exact quote stays the evidence",
        )
        bad = copy.deepcopy(plan)
        bad["facts"][0]["quote_id"] = "not-a-human-quote"
        with self.assertRaises(ValueError):
            reflection.validate(bad, "daily", source, [])
        bad = empty()
        bad["soul_append"] = "Change my identity"
        with self.assertRaises(ValueError):
            reflection.validate(bad, "daily", source, [])

    def test_daily_retry_does_not_call_model_or_duplicate_journal(self):
        calls = []

        def planner(*args):
            calls.append(1)
            return (empty(), {"completion_tokens": 20})

        first = reflection.reflect(
            self.c, "daily", "http://127.0.0.1:1", "test", now=self.now, planner=planner
        )
        second = reflection.reflect(
            self.c, "daily", "http://127.0.0.1:1", "test", now=self.now, planner=planner
        )
        self.assertEqual(first["status"], "recorded")
        self.assertEqual(second["status"], "skipped")
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            journal.path_for(self.c, "daily").read_text().count("## 2026-09-11"), 1
        )

    def test_checkin_does_not_clear_a_conversation_that_arrives_during_generation(self):
        db = self.db()
        stamp = self.now - dt.timedelta(minutes=1)
        db.execute(
            "INSERT INTO messages VALUES(1,?,?,?,?,1,0,0)",
            ("chat", "user", "My sister is Bee.", stamp.timestamp()),
        )
        db.commit()
        db.close()
        checkin.flag(self.c, self.now, platform="cli")

        def planner(*args):
            checkin.flag(self.c, self.now + dt.timedelta(seconds=10), platform="cli")
            plan = empty("")
            plan["facts"] = [
                {
                    "quote_id": "1:0",
                    "category": "people",
                    "statement": "Alex's sister is Bee.",
                }
            ]
            return (plan, {})

        result = reflection.reflect(
            self.c,
            "checkin",
            "http://127.0.0.1:1",
            "test",
            "human",
            now=self.now,
            planner=planner,
        )
        self.assertEqual(result["status"], "recorded")
        self.assertGreater(checkin.read(self.c)["pending"], 0)
        self.assertEqual(checkin.read(self.c)["last_reflected"], self.now.isoformat())

    def test_trusted_sources_and_same_timestamp_pagination_preserve_evidence(self):
        db = self.db()
        stamp = self.now.timestamp()
        for i in range(1, 4):
            db.execute(
                "INSERT INTO messages VALUES(?,?,?,?,?,1,0,0)",
                (i, "chat", "user", "x" * 200, stamp),
            )
        db.execute(
            "INSERT INTO messages VALUES(4,?,?,?,?,1,0,0)",
            ("cron", "user", "Not human evidence", stamp),
        )
        db.execute(
            "INSERT INTO messages VALUES(5,?,?,?,?,0,1,0)",
            ("chat", "user", "Compacted original", stamp),
        )
        db.commit()
        db.close()
        rows, more, through, cursor = reflection.messages(
            self.c,
            self.now - dt.timedelta(seconds=1),
            self.now,
            "human",
            limit_chars=500,
        )
        self.assertEqual([r["id"] for r in rows], ["1"])
        self.assertTrue(more)
        rest, _, _, _ = reflection.messages(
            self.c,
            dt.datetime.fromisoformat(through),
            self.now,
            "human",
            after_id=cursor,
        )
        self.assertEqual([r["id"] for r in rest], ["2", "3", "5"])

    def test_long_unbroken_evidence_is_bounded_without_losing_characters(self):
        content = "x" * 901
        result = reflection.quotation_sources(
            [dict(id="1", role="user", content=content)]
        )
        self.assertEqual("".join((s["content"] for s in result.values())), content)
        self.assertTrue(all((len(s["content"]) <= 300 for s in result.values())))
        plan = empty()
        plan["questions"] = ["q-deadbeef"]
        self.assertEqual(
            [d["text"] for d in reflection.validate(plan, "daily", {}, [])["omitted"]],
            ["q-deadbeef"],
        )

    def test_periodic_midnight_boundary_does_not_include_the_next_day(self):
        db = self.db()
        start = self.now.replace(hour=0) - dt.timedelta(days=1)
        end = start + dt.timedelta(days=1)
        db.execute(
            "INSERT INTO messages VALUES(1,?,?,?,?,1,0,0)",
            ("chat", "user", "At the start", start.timestamp()),
        )
        db.execute(
            "INSERT INTO messages VALUES(2,?,?,?,?,1,0,0)",
            ("chat", "user", "Next day", end.timestamp()),
        )
        db.commit()
        db.close()
        rows, *_ = reflection.messages(self.c, start, end, "human", end_inclusive=False)
        self.assertEqual([r["id"] for r in rows], ["1"])
        rows, *_ = reflection.messages(self.c, start, end, "human", end_inclusive=True)
        self.assertEqual([r["id"] for r in rows], ["1", "2"])


def test_rollover_finds_windows_python_and_preserves_the_host_environment(tmp_path):
    import sys
    from types import SimpleNamespace

    import companion_rollover as rollover

    scripts = tmp_path / "Hermes venv" / "Scripts"
    scripts.mkdir(parents=True)
    launcher = scripts / "hermes.exe"
    launcher.write_bytes(b"MZ")
    interpreter = scripts / "python.exe"
    interpreter.touch()
    companion = SimpleNamespace(home=tmp_path / "profile")
    with (
        patch.object(sys, "platform", "win32"),
        patch("shutil.which", return_value=str(launcher)),
        patch.dict(
            rollover.os.environ,
            {"PATH": "native search path", "SystemRoot": "C:\\Windows"},
        ),
        patch.object(rollover.subprocess, "run") as run,
    ):
        assert rollover.hermes_python() == str(interpreter)
        run.return_value = SimpleNamespace(returncode=0)
        rollover.end_sessions(companion, ["session-id"])
    assert run.call_args.args[0][0] == str(interpreter)
    environment = run.call_args.kwargs["env"]
    assert environment["PATH"] == "native search path"
    assert environment["SystemRoot"] == "C:\\Windows"
    assert environment["HERMES_HOME"] == str(companion.home)
