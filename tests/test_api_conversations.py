"""A conversation the human has through the Hermes API server (a game add-on, a voice
front end) joins the rest of their conversation once they name it as theirs.

Any client holding the API key can open an API conversation, so none is the owner's
by default. Named in companion.json, it is quoted into Telegram and the app, and they
into it, as one conversation that moves between places."""

import datetime as dt
import json
import pathlib
import sqlite3
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "kit" / "scripts"), str(ROOT)]

import companion_config as cc  # noqa: E402
import companion_context as ctx  # noqa: E402
import companion_transcript as transcript  # noqa: E402
from chat_fixtures import OWNER_TELEGRAM, HermesStore  # noqa: E402
from kit.app import runtime  # noqa: E402

TZ = ZoneInfo("America/New_York")
NOW = dt.datetime(2026, 3, 11, 20, 15, tzinfo=TZ)


def at(hours_ago):
    return (NOW - dt.timedelta(hours=hours_ago)).timestamp()


class ApiConversationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.c = self.companion({"game-chat": "the game"})
        self.c.home.mkdir(parents=True)
        (self.c.home / ".tamanitomo-chat-owner.json").write_text(
            json.dumps({"telegram": [OWNER_TELEGRAM]}), encoding="utf-8"
        )
        self.store = HermesStore(self.c.home)
        owner = dict(user_id=OWNER_TELEGRAM, chat_id=OWNER_TELEGRAM, chat_type="dm")
        # This afternoon on Telegram.
        self.store.session("tg", "telegram", started=at(8), **owner)
        self.store.say("tg", "user", "The kettle finally died this morning", at(7))
        self.store.say("tg", "assistant", "RIP kettle. Tea emergency?", at(7))
        # The columns Hermes keeps for API conversations and compression.
        with self.store.db() as db:
            for column in ("session_key", "parent_session_id", "end_reason"):
                db.execute(f"ALTER TABLE sessions ADD COLUMN {column} TEXT")
        # Last night and tonight in the game, one named API conversation that Hermes
        # compressed once: "api-old" handed over to "api-now".
        self.session("api-old", started=at(26), end_reason="compression")
        self.store.say("api-old", "user", "Finally beat the second boss", at(25))
        self.session("api-now", started=at(24), parent_session_id="api-old")
        self.store.say("api-now", "user", "Which quest should I do next?", at(0.5))
        self.store.say("api-now", "assistant", "The lighthouse one, obviously.", at(0.5))
        # A script on the same API key: not the human.
        self.session("api-script", started=at(3))
        self.store.say("api-script", "user", "Summarise the server log", at(2))
        self.responses({"game-chat": "api-now", "script-run": "api-script"})

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

    def session(self, ident, *, started, **columns):
        with self.store.db() as db:
            names = ["id", "source", "started_at", "profile_name", "user_id", "chat_id", "chat_type", *columns]
            values = [ident, "api_server", started, "nova", "api", ident, "dm", *columns.values()]
            db.execute(
                f"INSERT INTO sessions ({','.join(names)}) VALUES ({','.join('?' for _ in names)})",
                values,
            )  # fmt: skip

    def responses(self, latest):
        """Hermes's response store: each conversation name points at its latest
        response, whose record names the session it ran in."""
        with sqlite3.connect(self.c.home / transcript.RESPONSE_STORE) as db:
            db.execute(
                "CREATE TABLE responses (response_id TEXT PRIMARY KEY, data TEXT NOT NULL, accessed_at REAL NOT NULL)"
            )
            db.execute(
                "CREATE TABLE conversations (name TEXT PRIMARY KEY, response_id TEXT NOT NULL)"
            )
            for i, (name, session) in enumerate(latest.items()):
                record = {"response": {}, "conversation_history": [{"role": "user", "content": "x" * 50}],
                          "instructions": "", "session_id": session}  # fmt: skip
                db.execute("INSERT INTO responses VALUES (?,?,?)", (f"resp_{i}", json.dumps(record), 1.0))
                db.execute("INSERT INTO conversations VALUES (?,?)", (name, f"resp_{i}"))

    def build(self, session, platform, c=None):
        payload = {
            "session_id": session,
            "extra": {"user_message": "hi", "platform": platform, "is_first_turn": False},
        }
        return ctx.build(c or self.c, payload, now=NOW)

    def kinds(self, c=None):
        def read(view):
            return {
                ident: (view.owner_session(ident), view.channel_label(ident))
                for ident in ("api-now", "api-old", "api-script", "tg")
            }

        return transcript.owner_evidence(c or self.c, read)

    def test_a_named_api_conversation_is_the_owners(self):
        kinds = self.kinds()
        self.assertEqual(kinds["api-now"], ("api", "the game"))
        # Before Hermes compressed it, it was the same conversation.
        self.assertEqual(kinds["api-old"], ("api", "the game"))
        self.assertEqual(kinds["api-script"], (None, ""))
        self.assertEqual(kinds["tg"], ("telegram", ""))

    def test_the_game_hears_what_was_said_on_telegram(self):
        out = self.build("api-now", "api_server")
        self.assertIn("on another channel than this one (the game)", out)
        self.assertIn('Telegram · Robin: "The kettle finally died this morning"', out)
        self.assertIn('Telegram · Nova (you): "RIP kettle. Tea emergency?"', out)
        self.assertNotIn("Summarise the server log", out)
        self.assertIn("comes through another app connected to Hermes", out)

    def test_telegram_hears_what_was_said_in_the_game(self):
        out = self.build("tg", "telegram")
        self.assertIn('the game · Robin: "Which quest should I do next?"', out)
        self.assertIn('the game · Nova (you): "The lighthouse one, obviously."', out)
        self.assertIn('the game · Robin: "Finally beat the second boss"', out)
        self.assertNotIn("Summarise the server log", out)

    def test_unnamed_api_conversations_stay_out(self):
        c = self.companion({})
        self.assertEqual(self.kinds(c)["api-now"], (None, ""))
        out = self.build("tg", "telegram", c=c)
        self.assertNotIn("second boss", out)
        self.assertNotIn("Which quest", out)
        self.assertNotIn("Recent messages from", self.build("api-now", "api_server", c=c))

    def test_a_declared_session_key_names_it_without_the_response_store(self):
        (self.c.home / transcript.RESPONSE_STORE).unlink()
        self.session("api-keyed", started=at(1), session_key="game-chat")
        self.store.say("api-keyed", "user", "Logged in on the alt", at(0.8))
        out = self.build("tg", "telegram")
        self.assertIn('the game · Robin: "Logged in on the alt"', out)
        # Without the store the response-chained conversation is no longer known.
        self.assertNotIn("Which quest", out)

    def test_an_unreadable_response_store_trusts_nothing(self):
        path = self.c.home / transcript.RESPONSE_STORE
        with sqlite3.connect(path) as db:
            db.execute("UPDATE responses SET data='not json'")
        self.assertEqual(self.kinds()["api-now"], (None, ""))
        path.write_bytes(b"this is not a database")
        self.assertEqual(self.kinds()["api-now"], (None, ""))
        # The turn still builds; it just is not told about the other conversations.
        self.assertNotIn("Recent messages from", self.build("api-now", "api_server"))

    def test_the_app_feed_names_the_place(self):
        def read(view):
            records, _ = view.recent(0, [], 50)
            return [runtime._feed_message(view, r) for r in records]

        rows = transcript.owner_evidence(self.c, read)
        game = [r for r in rows if r["session"] == "api-now"]
        self.assertTrue(game)
        self.assertTrue(all(r["channel"] == "api" and r["channel_label"] == "the game" for r in game))
        self.assertTrue(all("channel_label" not in r for r in rows if r["session"] == "tg"))

    def test_setting_shapes(self):
        listed = self.companion(["game-chat"])
        self.assertEqual(listed.owner_api_conversations, {"game-chat": "game-chat"})
        for bad in ({"": "x"}, {"a": "x" * 61}, {"a\nb": "x"}, {"a": 3}, "game-chat", [3]):
            with self.assertRaises(ValueError):
                self.companion(bad)


class ConversationBudgetTests(unittest.TestCase):
    def test_room_for_a_real_stretch_of_conversation(self):
        self.assertEqual(cc.conversation_reserve(272_000), 16_000)
        self.assertGreater(cc.conversation_reserve(64_000), 4_000)
        self.assertEqual(ctx.HANDOFF_ITEMS, 40)


if __name__ == "__main__":
    unittest.main()
