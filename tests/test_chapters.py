"""Chapters: their story a month at a time, a year from its months, and "so far" from all of them.

The story job's pre-read names the one piece that is due and everything it is written from (the kept
conversation's memorable lines, never a password, game events apart, quiet months folded into the next), or
prints nothing so the run is skipped. She saves the piece and checks it. A written chapter is never asked for
again; "so far" is, whenever a chapter is newer. Nothing here calls a model.
"""

import datetime as dt
import json
import os
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
BODY = "We talked and laughed and watched films together that month. " * 12


def at(year, month, day, hour=20, minute=0):
    return dt.datetime(year, month, day, hour, minute, tzinfo=TZ).timestamp()


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
        self.store.session("tg", "telegram", started=at(2026, 10, 1), **owner)
        self.tick = 0

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

    def touch(self, path):
        """Files written in one instant still sort in the order they were written."""
        self.tick += 1
        os.utime(path, ns=(1_800_000_000_000_000_000 + self.tick * 10**9,) * 2)

    def save(self, piece, title="Lanterns and long walks", body=BODY):
        """What she does in the story job: write the piece where it says, then check it."""
        heading = piece["heading"].replace("<a title you give it>", title)
        tail = (
            ""
            if piece["kind"] == "so-far"
            else "\n\nCarrying forward: the trip in spring."
        )
        path = pathlib.Path(piece["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{heading}\n\n{body}{tail}\n", encoding="utf-8")
        self.touch(path)
        out = chapters.check(self.c, path, NOW)
        self.touch(path)
        return out

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

    def test_oldest_month_first_then_the_year_then_so_far(self):
        self.month_of_talk(2026, 11)
        self.month_of_talk(2026, 12)
        self.month_of_talk(2027, 1)
        self.month_of_talk(2027, 2, days=5)  # this month: no chapter until it is over
        archive.update(self.c, now=NOW)
        done = []
        piece = chapters.next_piece(self.c, NOW)
        while piece and len(done) < 8:
            done.append(f"{piece['kind']} {piece['label']}")
            out = self.save(piece)
            self.assertTrue(out["ok"], out)
            piece = chapters.next_piece(self.c, NOW)
        self.assertEqual(done, ["month November 2026", "month December 2026", "month January 2027", "year 2026",
                                "so-far Our story so far"])  # fmt: skip
        nov = chapters.month_path(self.c, "2026-11").read_text()
        self.assertTrue(nov.startswith("# November 2026: Lanterns and long walks\n"))
        self.assertTrue(nov.rstrip().endswith("<!-- written 2027-02-10 -->"))

    def test_what_the_pre_read_says(self):
        self.month_of_talk(2026, 11)
        self.month_of_talk(2026, 12)
        archive.update(self.c, now=NOW)
        self.save(chapters.next_piece(self.c, NOW))
        text = chapters.render(self.c, chapters.next_piece(self.c, NOW))
        self.assertTrue(
            text.startswith(
                "[Your story: a month's chapter is due]\nWrite: December 2026, 180 to 350 words."
            )
        )
        self.assertIn(f"Save it to: {chapters.month_path(self.c, '2026-12')}", text)
        self.assertIn("Its first line: # December 2026: <a title you give it>", text)
        self.assertIn("Robin: We went to the lake today", text)
        self.assertIn("The chapter before this one, for continuity", text)
        self.assertIn("# November 2026: Lanterns and long walks", text)

    def test_quiet_months_fold_into_the_next_chapter(self):
        self.store.say(
            "tg",
            "user",
            "Hi! So happy to finally meet you, I love this already",
            at(2026, 10, 20),
        )
        self.store.say(
            "tg", "user", "We had a lovely dinner together tonight", at(2026, 11, 3)
        )
        self.month_of_talk(2026, 12)
        archive.update(self.c, now=NOW)
        piece = chapters.next_piece(self.c, NOW)
        self.assertEqual(
            (piece["what"], piece["label"]), ("2026-12", "October to December 2026")
        )
        self.assertIn(
            "# October 2026 (too little for a chapter of its own)", piece["material"]
        )
        self.assertIn(
            "So happy to finally meet you", piece["material"]
        )  # how it began is not lost
        self.save(piece)
        self.assertEqual(
            chapters.next_piece(self.c, NOW)["kind"], "year"
        )  # the quiet months are in that one

    def test_nothing_due_is_nothing_at_all(self):
        self.month_of_talk(2027, 2, days=5)
        archive.update(self.c, now=NOW)
        self.assertIsNone(chapters.next_piece(self.c, NOW))

    def test_check_refuses_what_is_not_a_chapter(self):
        self.month_of_talk(2027, 1)
        archive.update(self.c, now=NOW)
        piece = chapters.next_piece(self.c, NOW)
        self.assertIn(
            "placeholder", self.save(piece, title="<a title you give it>")["problem"]
        )
        self.assertIn("shorter", self.save(piece, body="Too short.")["problem"])
        self.assertIn(
            "belong in",
            chapters.check(self.c, self.tmp / "elsewhere.md", NOW)["problem"],
        )
        self.assertTrue(self.save(piece)["ok"])

    def test_so_far_follows_her_edit_and_the_chapter_stays_hers(self):
        self.month_of_talk(2027, 1)
        archive.update(self.c, now=NOW)
        self.save(chapters.next_piece(self.c, NOW))
        self.save(
            chapters.next_piece(self.c, NOW),
            body="We met over the winter and it grew from there. " * 6,
        )
        self.assertIsNone(chapters.next_piece(self.c, NOW))
        path = chapters.month_path(self.c, "2027-01")
        path.write_text(path.read_text() + "\nI added this later, by hand.\n")
        self.touch(path)
        self.assertEqual(
            chapters.next_piece(self.c, NOW)["kind"], "so-far"
        )  # her edit, so the summary follows

    def test_her_context_carries_the_story_so_far(self):
        self.month_of_talk(2027, 1)
        archive.update(self.c, now=NOW)
        self.save(chapters.next_piece(self.c, NOW))
        self.save(
            chapters.next_piece(self.c, NOW),
            body="We met over the winter and it grew from there. " * 6,
        )
        out = ctx.build(
            self.c, {"extra": {"user_message": "hey", "platform": "telegram"}}, now=NOW
        )
        self.assertIn("[Your story together so far, in your own words.", out)
        self.assertIn("We met over the winter", out)
        self.assertNotIn("# Our story so far", out)
        self.assertNotIn(
            "<!-- written", out
        )  # the signature is for the file, not for her

    def test_the_story_job(self):
        import companion_render as cr

        manifest = json.loads((ROOT / "kit/templates/cron/manifest.json").read_text())
        spec = next(j for j in manifest["jobs"] if j["key"] == "story")
        self.assertEqual(
            (spec["preread_module"], spec["tier"]), ("companion_chapters", "reflection")
        )
        self.assertFalse(spec.get("no_agent"))
        prompt = cr.render(
            (ROOT / "kit/templates/cron" / spec["file"]).read_text(),
            cr.mapping_for(self.c),
        )
        self.assertEqual(cr.unresolved(prompt), [])
        self.assertIn("companion_chapters.py --home", prompt)


if __name__ == "__main__":
    unittest.main()
