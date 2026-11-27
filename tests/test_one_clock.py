"""Her sense of when the human last wrote counts every place they talk to her.

The thread (the last message each way, the gap, the recent tail) read only messaging
and terminal chats. Hermes files the app's own chats (a radio, a voice device, the
app window) as one-shot runs and a game add-on's chat as an API conversation, so an
evening's talk in the game left her thinking the human had been gone for hours: the
gap fed her missing them and her decisions to reach out on another channel.
"""

import datetime as dt
import contextlib
import json
import os
import pathlib
import sqlite3
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "kit" / "scripts"), str(ROOT)]

import companion_config as cc  # noqa: E402
import companion_thread as thread  # noqa: E402
import companion_transcript as transcript  # noqa: E402
from chat_fixtures import OWNER_TELEGRAM, HermesStore  # noqa: E402
from kit.app import runtime  # noqa: E402

TZ = ZoneInfo("America/New_York")
NOW = dt.datetime(2026, 3, 11, 21, 0, tzinfo=TZ)


def at(minutes_ago):
    return (NOW - dt.timedelta(minutes=minutes_ago)).timestamp()


def stamp(minutes_ago):
    return dt.datetime.fromtimestamp(at(minutes_ago), TZ).isoformat()


class ClockFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.c = self.companion({"game-chat": "the game"})
        self.c.home.mkdir(parents=True)
        (self.c.home / ".tamanitomo-chat-owner.json").write_text(
            json.dumps({"telegram": [OWNER_TELEGRAM]}), encoding="utf-8"
        )
        self.store = HermesStore(self.c.home)
        owner = dict(user_id=OWNER_TELEGRAM, chat_id=OWNER_TELEGRAM, chat_type="dm")
        # This afternoon on Telegram, then nothing there.
        self.store.session("tg", "telegram", started=at(600), **owner)
        with self.store.db() as db:
            for column in ("session_key", "parent_session_id", "end_reason"):
                db.execute(f"ALTER TABLE sessions ADD COLUMN {column} TEXT")
        self.store.say("tg", "user", "Off to the market for parsnips", at(360))
        self.store.say("tg", "assistant", "Get the good ones!", at(359))
        # Tonight in the game: one named API conversation, compressed once.
        self.api("game-old", started=at(300), end_reason="compression")
        self.store.say("game-old", "user", "Starting the harbor quest", at(120))
        self.api("game-now", started=at(100), parent_session_id="game-old")
        self.store.say("game-now", "user", "Which way to the windmill?", at(40))
        self.store.say("game-now", "assistant", "North, past the docks.", at(39))
        # Then the kitchen radio, which talks to her through the app's chat.
        self.local("radio", started=at(30))
        self.store.say("radio", "user", "Turn it up, I love this one", at(3))
        self.store.say("radio", "assistant", "Turning it up!", at(2))
        runtime.note_workspace_session(self.c, "radio")
        # A script on the same API key, and a one-shot run the app did not start.
        self.api("script", started=at(10))
        self.store.say("script", "user", "Summarise the server log", at(1))
        self.local("job-run", started=at(5))
        self.store.say("job-run", "user", "Rotate the backups", at(0.5))
        self.responses({"game-chat": "game-now", "script-run": "script"})

    def companion(self, named):
        return cc.Companion(
            agent="Nova",
            human="Robin",
            profile="nova",
            timezone="America/New_York",
            hermes_root=self.tmp / ".hermes",
            vault=self.tmp / "vault",
            context_tokens=272000,
            owner_api_conversations=named,
        )

    def insert(self, ident, source, user, started, columns):
        names = [
            "id",
            "source",
            "started_at",
            "profile_name",
            "user_id",
            "chat_id",
            "chat_type",
            *columns,
        ]
        values = [ident, source, started, "nova", user, ident, "dm", *columns.values()]
        with self.store.db() as db:
            db.execute(
                f"INSERT INTO sessions ({','.join(names)}) VALUES ({','.join('?' for _ in names)})",
                values,
            )  # fmt: skip

    def api(self, ident, *, started, **columns):
        self.insert(ident, "api_server", "api", started, columns)

    def local(self, ident, *, started, **columns):
        user = f"uid:{os.getuid()}" if hasattr(os, "getuid") else ""
        self.insert(ident, "oneshot", user, started, columns)

    def responses(self, latest):
        with (
            contextlib.closing(
                sqlite3.connect(self.c.home / transcript.RESPONSE_STORE)
            ) as db,
            db,
        ):
            db.execute(
                "CREATE TABLE responses (response_id TEXT PRIMARY KEY, data TEXT NOT NULL, accessed_at REAL NOT NULL)"
            )
            db.execute(
                "CREATE TABLE conversations (name TEXT PRIMARY KEY, response_id TEXT NOT NULL)"
            )
            for i, (name, session) in enumerate(latest.items()):
                record = {
                    "response": {},
                    "conversation_history": [],
                    "instructions": "",
                    "session_id": session,
                }
                db.execute(
                    "INSERT INTO responses VALUES (?,?,?)",
                    (f"resp_{i}", json.dumps(record), 1.0),
                )
                db.execute(
                    "INSERT INTO conversations VALUES (?,?)", (name, f"resp_{i}")
                )


class OneClockTests(ClockFixture):
    def test_the_radio_was_the_last_thing_the_human_said(self):
        data = thread.read(self.c, NOW, tail=6)
        self.assertEqual(data["last_from_human"], stamp(3))
        self.assertEqual(data["previous_from_human"], stamp(40))
        self.assertEqual(data["last_from_agent"], stamp(2))
        self.assertLessEqual(data["hours_since_human"], 0.1)

    def test_the_tail_holds_the_game_and_the_radio_but_no_script(self):
        said = [row["text"] for row in thread.read(self.c, NOW, tail=6)["tail"]]
        self.assertIn("Turn it up, I love this one", said)
        self.assertIn("Which way to the windmill?", said)
        self.assertNotIn("Summarise the server log", said)
        self.assertNotIn("Rotate the backups", said)

    def test_the_game_before_its_compression_is_still_the_human(self):
        days = thread.contact_days(self.c, NOW)
        # Parsnips on Telegram, the harbor (before Hermes compressed the game), the
        # windmill and the radio; neither the script nor the backup run.
        self.assertEqual(days[NOW.date()][0], 4)

    def test_unnamed_places_leave_the_clock_where_it_was(self):
        (self.c.home / ".tamanitomo-sessions.json").unlink()
        plain = self.companion({})
        data = thread.read(plain, NOW)
        self.assertEqual(data["last_from_human"], stamp(360))
        self.assertGreater(data["hours_since_human"], 5.9)


if __name__ == "__main__":
    unittest.main()


class AutomaticContextTests(ClockFixture):
    """A game add-on puts what it gathered (the character, the zone) before the human's words. Quoted anywhere
    else, only the words come along: the block is not what they said."""

    BLOCK = "[Game, added automatically by the game add-on]\nRobin: level 16 Human Mage\nWhere: Goldshire\n[/Game]\n\n"

    def setUp(self):
        super().setUp()
        self.store.say("game-now", "user", self.BLOCK + "Race you to the inn?", at(1.5))

    def test_the_thread_keeps_the_words(self):
        said = [row["text"] for row in thread.read(self.c, NOW, tail=8)["tail"]]
        self.assertIn("Race you to the inn?", said)
        self.assertFalse(any("added automatically" in text for text in said))

    def test_other_conversations_quote_the_words(self):
        import companion_context as ctx

        payload = {
            "session_id": "tg",
            "extra": {
                "user_message": "hi",
                "platform": "telegram",
                "is_first_turn": False,
            },
        }
        out = ctx.build(self.c, payload, now=NOW)
        self.assertIn('the game · Robin: "Race you to the inn?"', out)
        self.assertNotIn("added automatically", out)

    def test_context_alone_is_kept_rather_than_emptied(self):
        alone = (
            "[Game, added automatically by the game add-on]\nonly context\n[/Game]\n"
        )
        self.assertEqual(transcript.spoken(alone), alone)
