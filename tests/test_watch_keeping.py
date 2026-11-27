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
        (vault / "note.md").write_text("one")
        subprocess.run(["git", "-C", str(vault), "add", "-A"], check=True)
        subprocess.run(
            ["git", "-C", str(vault), "commit", "-qm", "first"], check=True, env=env
        )
        self.assertFalse(
            [p for p in self.problems() if "vault" in p]
        )  # nothing waiting
        (vault / "note.md").write_text("two")
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
            json.dumps({"jobs": [{"name": "Nova story", "id": "s1"}]})
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
            )
        )
        self.assertFalse([p for p in self.problems() if "chapter" in p])
        made = (NOW - dt.timedelta(days=6)).isoformat()
        jobs.write_text(
            json.dumps(
                {"jobs": [{"name": "Nova story", "id": "s1", "created_at": made}]}
            )
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
            )
        )
        self.assertTrue(
            any(
                "the last backup failed: repo init failed" in p for p in self.problems()
            )
        )
        report.write_text(
            json.dumps({"ok": True, "at": (NOW - dt.timedelta(hours=40)).isoformat()})
        )
        self.assertTrue(any("no backup for 40 hours" in p for p in self.problems()))
        report.write_text(
            json.dumps({"ok": True, "at": (NOW - dt.timedelta(hours=5)).isoformat()})
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
        (vault / "note.md").write_text("one")
        subprocess.run(["git", "-C", str(vault), "add", "-A"], check=True)
        subprocess.run(
            ["git", "-C", str(vault), "commit", "-qm", "first"], check=True, env=env
        )
        (vault / "note.md").write_text("two")
        self.assertEqual(
            len(self.problems()), 2
        )  # behind, and uncommitted (a repo with no author, too)
        watch.run(self.c, NOW, notify=lambda *a, **k: (True, "test"))
        healed = (self.c.home / "state" / "companion-watch-healed.jsonl").read_text()
        self.assertIn("copied 1 message(s) the archive had missed", healed)
        self.assertIn("committed the vault's waiting changes", healed)
        log = subprocess.run(
            ["git", "-C", str(vault), "log", "--format=%s"],
            capture_output=True,
            text=True,
        ).stdout
        self.assertIn(
            "health watch: changes left waiting", log
        )  # the repo had no author; now it has the vault's
        self.assertFalse([p for p in self.problems() if "archive" in p])

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
