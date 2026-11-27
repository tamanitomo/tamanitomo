"""The conversation archive: every conversation with the human, by month, as plain files in the vault.

Only conversations with them (never a scheduled job), only their words (a game's context block stays out), each
message once, under its own day, and a run with nothing new writes nothing.
"""

import datetime as dt
import json
import pathlib
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "kit" / "scripts"), str(ROOT)]

import companion_archive as archive  # noqa: E402
import companion_config as cc  # noqa: E402
from chat_fixtures import OWNER_TELEGRAM, HermesStore  # noqa: E402

TZ = ZoneInfo("America/New_York")


def at(month, day, hour, minute=0):
    return dt.datetime(2026, month, day, hour, minute, tzinfo=TZ).timestamp()


class ArchiveTests(unittest.TestCase):
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
        self.store.session("tg", "telegram", started=at(1, 30, 9), **owner)
        self.store.session("job", "cron", started=at(1, 30, 9))
        self.store.say(
            "tg", "user", "Morning! The snow finally stopped", at(1, 31, 8, 5)
        )
        self.store.say("tg", "assistant", "Snow day pancakes?", at(1, 31, 8, 6))
        self.store.say(
            "job", "user", "[Scheduled run] check the weather", at(1, 31, 8, 10)
        )
        self.store.say("tg", "user", "[Game, added automatically by the game add-on]\nRobin: level 3\n[/Game]\n\nRace you!",
                       at(2, 1, 21, 30))  # fmt: skip

    def months(self):
        return sorted(
            p.name for p in (self.c.data / "conversations" / "2026").iterdir()
        )

    def test_conversations_land_by_month_and_day(self):
        out = archive.update(self.c)
        self.assertEqual((out["copied"], out["months"]), (3, ["2026-01", "2026-02"]))
        self.assertEqual(
            self.months(),
            ["2026-01.jsonl", "2026-01.md", "2026-02.jsonl", "2026-02.md"],
        )
        january = (self.c.data / "conversations/2026/2026-01.md").read_text(
            encoding="utf-8"
        )
        self.assertTrue(january.startswith("# Conversations, January 2026\n"))
        self.assertIn("## Saturday 31 January", january)
        self.assertIn(
            "**08:05 · Telegram · Robin:** Morning! The snow finally stopped", january
        )
        self.assertIn("**08:06 · Telegram · Nova:** Snow day pancakes?", january)
        self.assertNotIn("Scheduled run", january)  # a job is not a conversation
        rows = [
            json.loads(line)
            for line in (self.c.data / "conversations/2026/2026-02.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        self.assertEqual(
            rows[0]["text"], "Race you!"
        )  # the words, not the game's context
        self.assertEqual((rows[0]["speaker"], rows[0]["who"]), ("Robin", "owner"))

    def test_each_message_once_and_new_ones_under_their_day(self):
        archive.update(self.c)
        self.assertEqual(archive.update(self.c)["copied"], 0)
        before = (self.c.data / "conversations/2026/2026-02.md").read_text(
            encoding="utf-8"
        )
        self.store.say("tg", "assistant", "You're on!", at(2, 1, 21, 31))
        self.store.say("tg", "user", "Good night", at(2, 2, 23, 0))
        self.assertEqual(archive.update(self.c)["copied"], 2)
        after = (self.c.data / "conversations/2026/2026-02.md").read_text(
            encoding="utf-8"
        )
        self.assertTrue(after.startswith(before))  # append-only
        self.assertEqual(
            after.count("## Sunday 1 February"), 1
        )  # the day it was already under
        self.assertIn("## Monday 2 February", after)
        lines = (
            (self.c.data / "conversations/2026/2026-02.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        self.assertEqual(len(lines), 3)

    def test_a_reply_that_was_only_silence_is_not_kept(self):
        self.store.say(
            "tg", "user", "[Game event: Robin just reached level 4]", at(2, 3, 20, 0)
        )
        self.store.say("tg", "assistant", "[SILENT]", at(2, 3, 20, 0))
        self.store.say("tg", "assistant", "NO_REPLY", at(2, 3, 20, 1))
        self.store.say(
            "tg", "assistant", "[silent] but this one has words", at(2, 3, 20, 2)
        )
        archive.update(self.c)
        february = (self.c.data / "conversations/2026/2026-02.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "Robin:** [Game event: Robin just reached level 4]", february
        )  # a game note, kept as one
        self.assertNotIn("Nova:** [SILENT]", february)
        self.assertNotIn("NO_REPLY", february)
        self.assertIn("Nova:** [silent] but this one has words", february)

    def test_silence_markers(self):
        import companion_transcript as transcript

        for said in (
            "[SILENT]",
            "silent",
            "[ SILENT ]",
            "NO_REPLY",
            "no reply.",
            "[\u200bSILENT]",
        ):
            self.assertTrue(transcript.silent(said), said)
        for said in ("[SILENT] nothing new", "Silently, yes", "", None, "ok"):
            self.assertFalse(transcript.silent(said), said)

    def test_no_history_yet_is_not_an_error(self):
        empty = cc.Companion(
            agent="Nova",
            human="Robin",
            hermes_root=self.tmp / "none",
            vault=self.tmp / "v2",
        )
        empty.home.mkdir(parents=True)
        self.assertEqual(archive.update(empty)["copied"], 0)


if __name__ == "__main__":
    unittest.main()
