"""Is her memory still being kept? The hourly health watch says so when the conversation archive falls behind, the
vault sits uncommitted, last month's chapter is overdue, or a backup that reports itself fails or goes stale.
"""

import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "kit" / "scripts"), str(ROOT)]

import companion_archive as archive  # noqa: E402
import companion_config as cc  # noqa: E402
import companion_watch as watch  # noqa: E402
from chat_fixtures import OWNER_TELEGRAM, HermesStore  # noqa: E402

TZ = ZoneInfo("America/New_York")
NOW = dt.datetime(2027, 2, 10, 12, 0, tzinfo=TZ)


def at(month, day, hour=20):
    return dt.datetime(2027, month, day, hour, 0, tzinfo=TZ).timestamp()


class KeepingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.c = cc.Companion(
            agent="Nova", human="Robin", profile="nova", timezone="America/New_York",
            hermes_root=self.tmp / ".hermes", vault=self.tmp / "vault",
        )  # fmt: skip
        self.c.home.mkdir(parents=True)
        (self.c.home / ".tamanitomo-chat-owner.json").write_text(
            json.dumps({"telegram": [OWNER_TELEGRAM]}), encoding="utf-8"
        )
        self.store = HermesStore(self.c.home)
        owner = dict(user_id=OWNER_TELEGRAM, chat_id=OWNER_TELEGRAM, chat_type="dm")
        self.store.session("tg", "telegram", started=at(1, 1), **owner)

    def problems(self):
        return watch.check_keeping(self.c, NOW)

    def test_an_archive_that_has_fallen_behind(self):
        self.store.say("tg", "user", "We walked to the old mill and back", at(2, 10, 6))
        found = self.problems()
        self.assertTrue(
            any("conversation archive is behind" in p for p in found), found
        )
        archive.update(self.c, now=NOW)
        self.assertFalse([p for p in self.problems() if "archive" in p])
        self.store.say("tg", "user", "fresh words a minute old", NOW.timestamp() - 60)
        self.assertFalse(
            [p for p in self.problems() if "archive" in p]
        )  # recent is not behind

    def test_a_vault_left_uncommitted(self):
        vault = pathlib.Path(self.c.vault)
        vault.mkdir(parents=True, exist_ok=True)
        env = {**os.environ, "GIT_AUTHOR_DATE": "2027-02-09T08:00:00-05:00", "GIT_COMMITTER_DATE": "2027-02-09T08:00:00-05:00",
               "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}  # fmt: skip
        subprocess.run(["git", "init", "-q", str(vault)], check=True)
        (vault / "note.md").write_text("one", encoding="utf-8")
        subprocess.run(["git", "-C", str(vault), "add", "-A"], check=True)
        subprocess.run(
            ["git", "-C", str(vault), "commit", "-qm", "first"], check=True, env=env
        )
        self.assertFalse(
            [p for p in self.problems() if "vault" in p]
        )  # nothing waiting
        (vault / "note.md").write_text("two", encoding="utf-8")
        found = self.problems()
        self.assertTrue(any("no commit for 28 hours" in p for p in found), found)

    def test_an_overdue_chapter_only_when_the_story_job_exists(self):
        for day in range(1, 15):
            self.store.say(
                "tg",
                "user",
                f"We went to the lake today and I laughed so much, day {day}",
                at(1, day),
            )
        archive.update(self.c, now=NOW)
        self.assertFalse(
            [p for p in self.problems() if "chapter" in p]
        )  # no story job: nothing to blame
        (self.c.home / "cron").mkdir(parents=True, exist_ok=True)
        (self.c.home / "cron/jobs.json").write_text(
            json.dumps({"jobs": [{"name": "Nova story", "id": "s1"}]}), encoding="utf-8"
        )
        found = self.problems()
        self.assertTrue(
            any("chapter for January 2027 is 9 days overdue" in p for p in found),
            found,
        )
        # A job that arrived yesterday owes its backlog from yesterday: catching up is not late.
        jobs = self.c.home / "cron/jobs.json"
        made = (NOW - dt.timedelta(days=1)).isoformat()
        jobs.write_text(
            json.dumps(
                {"jobs": [{"name": "Nova story", "id": "s1", "created_at": made}]}
            ),
            encoding="utf-8",
        )
        self.assertFalse([p for p in self.problems() if "chapter" in p])
        made = (NOW - dt.timedelta(days=6)).isoformat()
        jobs.write_text(
            json.dumps(
                {"jobs": [{"name": "Nova story", "id": "s1", "created_at": made}]}
            ),
            encoding="utf-8",
        )
        self.assertTrue(
            any(
                "chapter for January 2027 is 6 days overdue" in p
                for p in self.problems()
            )
        )

    def test_a_backup_that_reports_itself(self):
        state = self.c.home / "state"
        state.mkdir(parents=True, exist_ok=True)
        report = state / "vault-backup-last.json"
        report.write_text(
            json.dumps(
                {"ok": False, "at": NOW.isoformat(), "error": "repo init failed"}
            ),
            encoding="utf-8",
        )
        self.assertTrue(
            any(
                "the last backup failed: repo init failed" in p for p in self.problems()
            )
        )
        report.write_text(
            json.dumps({"ok": True, "at": (NOW - dt.timedelta(hours=40)).isoformat()}),
            encoding="utf-8",
        )
        self.assertTrue(any("no backup for 40 hours" in p for p in self.problems()))
        report.write_text(
            json.dumps({"ok": True, "at": (NOW - dt.timedelta(hours=5)).isoformat()}),
            encoding="utf-8",
        )
        self.assertFalse([p for p in self.problems() if "backup" in p])

    def test_the_watch_mends_what_it_can_before_telling_anyone(self):
        self.store.say("tg", "user", "We walked to the old mill and back", at(2, 10, 6))
        vault = pathlib.Path(self.c.vault)
        vault.mkdir(parents=True, exist_ok=True)
        env = {**os.environ, "GIT_AUTHOR_DATE": "2027-02-09T08:00:00-05:00",
               "GIT_COMMITTER_DATE": "2027-02-09T08:00:00-05:00", "GIT_AUTHOR_NAME": "t",
               "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}  # fmt: skip
        subprocess.run(["git", "init", "-q", str(vault)], check=True)
        (vault / "note.md").write_text("one", encoding="utf-8")
        subprocess.run(["git", "-C", str(vault), "add", "-A"], check=True)
        subprocess.run(
            ["git", "-C", str(vault), "commit", "-qm", "first"], check=True, env=env
        )
        (vault / "note.md").write_text("two", encoding="utf-8")
        self.assertEqual(
            len(self.problems()), 2
        )  # behind, and uncommitted (a repo with no author, too)
        watch.run(self.c, NOW, notify=lambda *a, **k: (True, "test"))
        healed = (self.c.home / "state" / "companion-watch-healed.jsonl").read_text(
            encoding="utf-8"
        )
        self.assertIn("copied 1 message(s) the archive had missed", healed)
        self.assertIn("committed the vault's waiting changes", healed)
        log = subprocess.run(
            ["git", "-C", str(vault), "log", "--format=%s"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        ).stdout
        self.assertIn(
            "health watch: changes left waiting", log
        )  # the repo had no author; now it has the vault's
        self.assertFalse([p for p in self.problems() if "archive" in p])

    def fts(self):
        with self.store.db() as db:
            db.executescript("""
                CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(content);
                INSERT INTO messages_fts(rowid, content) SELECT id, content FROM messages;
            """)

    def test_her_recall_drilled_against_things_said_long_ago(self):
        import random
        from unittest.mock import patch

        old = [
            "The lighthouse keeper waved at us from the gallery",
            "We bought a kite shaped like a heron at the fair",
            "My sister finally finished the quilt with the blue squares",
            "The bakery on Elm closed early because of the storm",
        ]
        for n, text in enumerate(old):
            self.store.say("tg", "user", text, at(1, 2 + n, 9))
        for n in range(30):
            self.store.say(
                "tg",
                "user",
                f"maybe we should see the storm tonight {n}",
                at(2, 9, 8) + n,
            )
        self.fts()
        archive.update(self.c, now=NOW)
        report = watch.recall_drill(self.c, NOW, rng=random.Random(1))
        self.assertEqual(
            (report["tried"], report["found"]), (4, 4), report
        )  # only lines a month old or more
        self.assertEqual(
            json.loads(watch.recall_drill_path(self.c).read_text(encoding="utf-8"))[
                "found"
            ],
            4,
        )
        self.assertEqual(watch.check_recall(self.c, NOW), [])
        # A broken search: the next drill misses, and the hourly checks say so (with the dates), without re-running
        # the drill until a week has passed.
        stale = NOW + dt.timedelta(days=8)
        with patch("companion_recall.search", return_value={"results": []}):
            found = watch.check_recall(self.c, stale)
        self.assertTrue(found and "her recall missed 4 of 4" in found[0], found)
        self.assertIn("2027-01-02", found[0])
        with patch("companion_recall.search") as search:
            self.assertTrue(watch.check_recall(self.c, stale + dt.timedelta(hours=1)))
        search.assert_not_called()

    def test_no_archive_no_drill_problem(self):
        self.assertEqual(watch.check_recall(self.c, NOW), [])

    def test_part_of_the_hourly_watch(self):
        self.assertIn(
            "check_keeping",
            watch.problems.__code__.co_names
            + tuple(
                n
                for const in watch.problems.__code__.co_consts
                if hasattr(const, "co_names")
                for n in const.co_names
            ),
        )


if __name__ == "__main__":
    unittest.main()
