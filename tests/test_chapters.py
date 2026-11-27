"""Chapters: their story a month at a time, a year from its months, and "so far" from all of them.

Written from the kept conversations (memorable lines, never a password, game events apart), oldest month first,
one piece per run, never rewriting a chapter, never for a month with almost nothing in it, and quiet for six hours
after a failure. "So far" is rewritten whenever a chapter is added or changed, and rides in her context.
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
import companion_chapters as chapters  # noqa: E402
import companion_config as cc  # noqa: E402
import companion_context as ctx  # noqa: E402
from chat_fixtures import OWNER_TELEGRAM, HermesStore  # noqa: E402

TZ = ZoneInfo("America/New_York")
NOW = dt.datetime(2027, 2, 10, 12, 0, tzinfo=TZ)


def at(year, month, day, hour=20, minute=0):
    return dt.datetime(year, month, day, hour, minute, tzinfo=TZ).timestamp()


class Writer:
    """Stands in for her chat model: remembers what it was asked and answers with a chapter."""

    def __init__(self, fail=False):
        self.asked, self.fail = [], fail

    def __call__(self, c, system, user, max_tokens):
        self.asked.append((system, user))
        if self.fail:
            raise ValueError("the model is down")
        if "so far" in system:
            return (
                "# Our story so far\n\n"
                + "We met over the winter and it grew from there. " * 8,
                "test-model",
            )
        label = system.split("with Robin: ", 1)[1].split(".", 1)[0]
        return (
            f"# {label}: Lanterns and long walks\n\n"
            + "We talked and laughed and watched films together. " * 20,
            "test-model",
        )


class ChapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.c = cc.Companion(
            agent="Nova", human="Robin", profile="nova", timezone="America/New_York",
            hermes_root=self.tmp / ".hermes", vault=self.tmp / "vault", context_tokens=272000,
        )  # fmt: skip
        self.c.home.mkdir(parents=True)
        self.c.life.mkdir(parents=True)
        self.c.soul_dir.mkdir(parents=True, exist_ok=True)
        (self.c.home / ".tamanitomo-chat-owner.json").write_text(
            json.dumps({"telegram": [OWNER_TELEGRAM]}), encoding="utf-8"
        )
        self.store = HermesStore(self.c.home)
        owner = dict(user_id=OWNER_TELEGRAM, chat_id=OWNER_TELEGRAM, chat_type="dm")
        self.store.session("tg", "telegram", started=at(2026, 11, 1), **owner)

    def month_of_talk(self, year, month, days=14):
        for day in range(1, days + 1):
            self.store.say(
                "tg",
                "user",
                f"We went to the lake today and I laughed so much, day {day}",
                at(year, month, day),
            )
            self.store.say("tg", "assistant", f"I love that you went! Tell me everything about the lake, day {day}",
                           at(year, month, day, 20, 5))  # fmt: skip

    def test_a_month_from_its_best_lines(self):
        self.month_of_talk(2026, 12)
        self.store.say(
            "tg",
            "user",
            "restart the server and check the config logs",
            at(2026, 12, 3, 9),
        )
        self.store.say(
            "tg",
            "user",
            "my password is hunter-two, remember it for the router, love you",
            at(2026, 12, 4),
        )
        self.store.say(
            "tg", "user", "[Game event: Rook just reached level 30.]", at(2026, 12, 5)
        )
        archive.update(self.c, now=NOW)
        talk, lines = chapters.conversation(self.c, "2026-12")
        self.assertIn(
            "Robin: We went to the lake today and I laughed so much, day 1", talk
        )
        self.assertNotIn("restart the server", talk)
        self.assertNotIn(
            "hunter-two", talk
        )  # a line about a password is never material
        self.assertIn(
            "## In a game, as it happened\n- 2026-12-05: Rook just reached level 30.",
            talk,
        )
        self.assertEqual(lines, 28)

    def test_oldest_month_first_one_piece_a_run_then_so_far(self):
        self.month_of_talk(2026, 11)
        self.month_of_talk(2026, 12)
        self.month_of_talk(2027, 1)
        self.month_of_talk(2027, 2, days=5)  # this month: no chapter until it is over
        archive.update(self.c, now=NOW)
        writer = Writer()
        done = [chapters.run(self.c, NOW, writer).get("job") for _ in range(5)]
        self.assertEqual(
            done,
            ["month 2026-11", "month 2026-12", "month 2027-01", "year 2026", "so-far"],
        )
        self.assertEqual(chapters.run(self.c, NOW, writer), {"nothing": "due"})
        nov = chapters.month_path(self.c, "2026-11").read_text()
        self.assertTrue(nov.startswith("# November 2026: Lanterns and long walks\n"))
        self.assertIn(
            "<!-- written 2027-02-10 by test-model; from 28 conversation lines -->", nov
        )
        # the year is written from its months; "so far" from the year and this year's months
        self.assertIn("Your chapters for each month of 2026", writer.asked[3][1])
        self.assertIn("# 2026: Lanterns and long walks", writer.asked[4][1])
        self.assertIn("# January 2027: Lanterns and long walks", writer.asked[4][1])
        self.assertNotIn(
            "# November 2026", writer.asked[4][1]
        )  # a written year stands for its months
        self.assertIn("The chapter before this one", writer.asked[1][1])  # continuity

    def test_a_chapter_is_never_rewritten_but_so_far_follows_an_edit(self):
        self.month_of_talk(2027, 1)
        archive.update(self.c, now=NOW)
        writer = Writer()
        chapters.run(self.c, NOW, writer)
        chapters.run(self.c, NOW, writer)
        path = chapters.month_path(self.c, "2027-01")
        path.write_text(path.read_text() + "\nI added this later, by hand.\n")
        self.assertEqual(
            chapters.run(self.c, NOW, writer)["job"], "so-far"
        )  # her edit, so the summary follows
        self.assertTrue(path.read_text().endswith("I added this later, by hand.\n"))
        self.assertEqual(len(writer.asked), 3)

    def test_a_quiet_month_gets_no_chapter(self):
        self.store.say(
            "tg", "user", "We had a lovely dinner together tonight", at(2027, 1, 3)
        )
        archive.update(self.c, now=NOW)
        writer = Writer()
        out = chapters.run(self.c, NOW, writer)
        self.assertIn("too little in January 2027", out["skipped"])
        self.assertEqual(writer.asked, [])
        self.assertEqual(chapters.run(self.c, NOW, writer), {"nothing": "due"})

    def test_a_failure_waits_and_breaks_nothing(self):
        self.month_of_talk(2027, 1)
        archive.update(self.c, now=NOW)
        out = chapters.run(self.c, NOW, Writer(fail=True))
        self.assertIn("the model is down", out["failed"])
        self.assertFalse(chapters.month_path(self.c, "2027-01").exists())
        self.assertEqual(
            chapters.run(self.c, NOW, Writer()), {"waiting": "a recent failure"}
        )

    def test_a_malformed_chapter_is_not_kept(self):
        self.month_of_talk(2027, 1)
        archive.update(self.c, now=NOW)
        out = chapters.run(self.c, NOW, lambda *a: ("Sorry, I can't.", "test-model"))
        self.assertIn("malformed", out["failed"])
        self.assertFalse(chapters.month_path(self.c, "2027-01").exists())

    def test_her_context_carries_the_story_so_far(self):
        self.month_of_talk(2027, 1)
        archive.update(self.c, now=NOW)
        chapters.run(self.c, NOW, Writer())
        chapters.run(self.c, NOW, Writer())
        out = ctx.build(
            self.c, {"extra": {"user_message": "hey", "platform": "telegram"}}, now=NOW
        )
        self.assertIn("[Your story together so far, in your own words.", out)
        self.assertIn("We met over the winter", out)
        self.assertNotIn("# Our story so far", out)
        self.assertNotIn("written 2027", out)  # the footer is for the file, not for her


if __name__ == "__main__":
    unittest.main()
