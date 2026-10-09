"""Recent messages from the human's other conversations, quoted into each turn.

A conversation starts fresh every morning and every channel is its own
conversation; these tests pin down what a new one is told about the rest."""

import datetime as dt
import json
import pathlib
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT)]

import companion_config as cc  # noqa: E402
import companion_context as ctx  # noqa: E402
from chat_fixtures import OWNER_TELEGRAM, STRANGER_TELEGRAM, HermesStore  # noqa: E402
from kit.app import runtime  # noqa: E402

TZ = ZoneInfo("America/New_York")
NOW = dt.datetime(2026, 3, 11, 8, 15, tzinfo=TZ)


def at(hours_ago):
    return (NOW - dt.timedelta(hours=hours_ago)).timestamp()


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.c = cc.Companion(
            agent="Nova",
            human="Robin",
            profile="nova",
            timezone="America/New_York",
            hermes_root=self.tmp / ".hermes",
            vault=self.tmp / "vault",
            context_tokens=272000,
        )
        self.c.home.mkdir(parents=True)
        (self.c.home / ".tamanitomo-chat-owner.json").write_text(
            json.dumps({"telegram": [OWNER_TELEGRAM]}), encoding="utf-8"
        )
        self.store = HermesStore(self.c.home)
        owner = dict(user_id=OWNER_TELEGRAM, chat_id=OWNER_TELEGRAM, chat_type="dm")
        # Last night's Telegram conversation, ended by the morning fresh start.
        self.store.session("tg-night", "telegram", started=at(12), **owner)
        self.store.say(
            "tg-night", "user", "Dentist at ten tomorrow, wish me luck", at(10)
        )
        self.store.say(
            "tg-night", "assistant", "Good luck! Ten o'clock, got it.", at(10)
        )
        # A web-app conversation earlier, and this morning's new Telegram one.
        self.store.session("web", "cli", started=at(30))
        runtime.note_workspace_session(self.c, "web")
        self.store.say("web", "user", "The porch light flickers again", at(29))
        self.store.session("tg-morning", "telegram", started=at(0.1), **owner)
        self.store.say("tg-morning", "user", "Morning!", at(0.05))
        # Never shown: too old, another person, a scheduled run.
        self.store.say("web", "user", "Something from two days ago", at(50))
        self.store.session(
            "stranger", "telegram", started=at(3),
            user_id=STRANGER_TELEGRAM, chat_id=STRANGER_TELEGRAM, chat_type="dm",
        )  # fmt: skip
        self.store.say("stranger", "user", "I am not the owner", at(2))
        self.store.session("job", "cron", started=at(1))
        self.store.say("job", "user", "Run the pulse", at(1))

    def build(self, session="tg-morning", c=None):
        payload = {
            "session_id": session,
            "extra": {
                "user_message": "Morning!",
                "platform": "telegram",
                "is_first_turn": True,
            },
        }
        return ctx.build(c or self.c, payload, now=NOW)

    def test_new_conversation_sees_last_night_and_the_other_channel(self):
        out = self.build()
        self.assertIn("before this conversation began, or on another channel", out)
        self.assertIn('Robin: "Dentist at ten tomorrow, wish me luck"', out)
        self.assertIn('Nova (you): "Good luck! Ten o\'clock, got it."', out)
        self.assertIn('the app · Robin: "The porch light flickers again"', out)
        self.assertIn("not new messages to answer", out)
        # Oldest first, so it reads as the conversation did.
        self.assertLess(out.index("porch light"), out.index("Dentist"))

    def test_only_the_owners_conversations_within_the_window(self):
        out = self.build()
        for absent in ("two days ago", "not the owner", "Run the pulse", 'Morning!"'):
            self.assertNotIn(absent, out)

    def test_a_scheduled_run_is_told_nothing(self):
        self.assertNotIn("Recent messages from", self.build(session="job"))

    def test_newest_kept_when_the_reserve_is_full(self):
        for i in range(30):
            self.store.say("tg-night", "user", f"note {i:02d} " + "x" * 400, at(9) + i)
        out = self.build()
        self.assertIn("note 29", out)
        self.assertNotIn("note 00", out)
        self.assertIn("are not shown here; nothing was deleted", out)
        section = out[out.index("[Recent messages") :].split("\n\n")[0]
        self.assertLessEqual(len(section), self.c.budgets()["conversation"] + 600)

    def test_switched_off(self):
        c = cc.dataclasses.replace(self.c, conversation_handoff=False)
        out = self.build(c=c)
        self.assertNotIn("Dentist", out)
        self.assertNotIn("recent messages from your other conversations", out)

    def test_reserved_on_top_of_every_other_section(self):
        on = self.c.budgets()
        off = cc.dataclasses.replace(self.c, conversation_handoff=False).budgets()
        self.assertEqual(on["conversation"], cc.conversation_reserve(272000))
        self.assertEqual(off["conversation"], 0)
        self.assertEqual(on["total"] - off["total"], on["conversation"])
        for key in cc._PRIORITY:
            self.assertEqual(on[key], off[key], key)

    def test_a_tiny_window_says_it_had_no_room(self):
        c = cc.dataclasses.replace(self.c, context_tokens=8192)
        out = self.build(c=c)
        self.assertNotIn("Dentist", out)
        self.assertIn("recent messages from your other conversations", out)

    def test_an_unknown_session_is_reported_not_guessed(self):
        out = self.build(session="not-yet-stored")
        self.assertIn("could not be checked this turn", out)
        self.assertNotIn("Dentist", out)


if __name__ == "__main__":
    unittest.main()
