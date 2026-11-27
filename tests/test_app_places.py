"""A device or another app that keeps its own conversation going through the app's
chat names its place, and her other conversations call it that.

Hermes files every chat sent through the app as a local session, so without a name
the human's talk on a kitchen radio and in the app's own window were both "the app".
"""

import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
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
RADIO = "the kitchen radio"


def at(hours_ago):
    return (NOW - dt.timedelta(hours=hours_ago)).timestamp()


class PlaceTests(unittest.TestCase):
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
        self.store.session("tg", "telegram", started=at(9), **owner)
        self.store.say("tg", "user", "The kettle finally died this morning", at(8))
        with self.store.db() as db:
            for column in ("parent_session_id", "end_reason"):
                db.execute(f"ALTER TABLE sessions ADD COLUMN {column} TEXT")
        # The app's own chat window, and a radio that talks to her through the app:
        # one conversation Hermes compressed once ("radio-old" -> "radio").
        self.local("web", started=at(30))
        self.store.say("web", "user", "Checking in from my desk", at(6))
        self.local("radio-old", started=at(28), end_reason="compression")
        self.store.say("radio-old", "user", "The morning news was grim", at(27))
        self.local("radio", started=at(26), parent_session_id="radio-old")
        self.store.say("radio", "user", "Turn it up, I love this one", at(1))
        self.store.say("radio", "assistant", "Turning it up!", at(1))
        for ident in ("web", "radio-old"):
            runtime.note_workspace_session(self.c, ident)
        runtime.note_workspace_session(self.c, "radio", RADIO)

    def local(self, ident, *, started, **columns):
        names = ["id", "source", "started_at", "profile_name", "user_id", "chat_id", "chat_type", *columns]
        values = [ident, "oneshot", started, "nova", f"uid:{os.getuid()}" if hasattr(os, "getuid") else "",
                  ident, "dm", *columns.values()]  # fmt: skip
        with self.store.db() as db:
            db.execute(
                f"INSERT INTO sessions ({','.join(names)}) VALUES ({','.join('?' for _ in names)})",
                values,
            )  # fmt: skip

    def build(self, session, platform):
        payload = {
            "session_id": session,
            "extra": {"user_message": "hi", "platform": platform, "is_first_turn": False},
        }
        return ctx.build(self.c, payload, now=NOW)

    def labels(self, *idents):
        def read(view):
            return {i: (view.owner_session(i), view.channel_label(i)) for i in idents}

        return transcript.owner_evidence(self.c, read)

    def test_the_place_names_its_conversation_and_what_came_before_it(self):
        labels = self.labels("radio", "radio-old", "web", "tg")
        self.assertEqual(labels["radio"], ("workspace", RADIO))
        self.assertEqual(labels["radio-old"], ("workspace", RADIO))
        self.assertEqual(labels["web"], ("workspace", ""))
        self.assertEqual(labels["tg"], ("telegram", ""))

    def test_a_continuation_is_still_the_same_place(self):
        with self.store.db() as db:
            db.execute("UPDATE sessions SET end_reason='compression' WHERE id='radio'")
        self.local("radio-next", started=at(0.5), parent_session_id="radio")
        self.assertEqual(self.labels("radio-next")["radio-next"][1], RADIO)

    def test_telegram_hears_the_place_by_name(self):
        out = self.build("tg", "telegram")
        self.assertIn(f'{RADIO} · Robin: "Turn it up, I love this one"', out)
        self.assertIn(f'{RADIO} · Nova (you): "Turning it up!"', out)
        self.assertIn(f'{RADIO} · Robin: "The morning news was grim"', out)
        self.assertIn('the app · Robin: "Checking in from my desk"', out)

    def test_the_place_knows_where_it_is(self):
        out = self.build("radio", "cli")
        self.assertIn(
            f'This conversation is on "{RADIO}", which reaches you through the app.', out
        )
        self.assertNotIn("This is a terminal session", out)
        self.assertIn(f"on another channel than this one ({RADIO})", out)
        self.assertIn('the app · Robin: "Checking in from my desk"', out)
        # The app's own window is unchanged.
        self.assertIn("This is a terminal session", self.build("web", "cli"))

    def test_the_feed_names_the_place(self):
        def read(view):
            records, _ = view.recent(0, [], 50)
            return [runtime._feed_message(view, r) for r in records]

        rows = transcript.owner_evidence(self.c, read)
        radio = [r for r in rows if r["session"] in ("radio", "radio-old")]
        self.assertEqual(len(radio), 3)
        self.assertTrue(all(r["channel"] == "workspace" and r["channel_label"] == RADIO for r in radio))
        self.assertTrue(all("channel_label" not in r for r in rows if r["session"] in ("web", "tg")))

    def test_the_app_window_does_not_take_over_a_places_conversation(self):
        self.assertEqual(runtime.latest_session(self.c), "web")

    def test_place_names(self):
        self.assertEqual(runtime.place_name("  the kitchen\nradio "), "the kitchen radio")
        self.assertEqual(runtime.place_name(None), "")
        self.assertEqual(runtime.place_name(""), "")
        for bad in (3, ["radio"], " ", "x" * 61, "a\x1b[31mb", "a‮b"):
            with self.assertRaises(ValueError):
                runtime.place_name(bad)

    def test_the_newest_places_are_kept(self):
        for i in range(runtime.PLACES_KEPT + 5):
            runtime.note_place(self.c, f"s{i}", f"place {i}")
        runtime.note_place(self.c, "s10", "place 10 again")
        places = runtime.read_workspace_places(self.c)
        self.assertEqual(len(places), runtime.PLACES_KEPT)
        # The fixture's radio and s0-s4 were the oldest of 106.
        self.assertNotIn("radio", places)
        self.assertNotIn("s4", places)
        self.assertIn("s5", places)
        self.assertEqual(list(places)[-1], "s10")
        self.assertEqual(places["s10"], "place 10 again")

    def test_an_edited_or_broken_file_names_nothing_it_should_not(self):
        path = runtime.workspace_places_path(self.c)
        path.write_text(json.dumps({"radio": "x" * 200, "web": "the desk", "": "nowhere"}))
        self.assertEqual(runtime.read_workspace_places(self.c), {"web": "the desk"})
        path.write_text("not json")
        self.assertEqual(runtime.read_workspace_places(self.c), {})
        self.assertEqual(self.labels("radio")["radio"], ("workspace", ""))


class ChatEndpointTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient

        from kit.app.server import build

        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.c = cc.Companion(
            agent="Nova",
            human="Robin",
            hermes_root=self.tmp / "home",
            vault=self.tmp / "vault",
            timezone="UTC",
            profile="nova",
        )
        self.c.home.mkdir(parents=True)
        self.c.save()
        self.store = HermesStore(self.c.home)
        self.store.session("radio", "oneshot", user_id=f"uid:{os.getuid()}", chat_id="radio")
        runtime.note_workspace_session(self.c, "radio")
        self.app = build(home=self.c.home, state_dir=self.tmp / "app")
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.seen = []

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.app.state.operations.pool.shutdown(wait=True)
        self.app.state.dashboards.close()

    def chat(self, body):
        seen, c = self.seen, self.c

        def chat(rt, args, home, report):
            # What her context reads while the turn runs.
            seen.append(transcript.app_place(c, args[args.index("--resume") + 1]))
            result = subprocess.CompletedProcess(args, 0, "Turning it up!", "")
            result.session = "radio"
            return result

        original = runtime.Runtime.chat
        runtime.Runtime.chat = chat
        try:
            response = self.client.post("/api/chat", json=body)
            if response.status_code != 200:
                return response.status_code, response.json()
            row = response.json()
            deadline = time.monotonic() + 10
            while row["status"] == "running" and time.monotonic() < deadline:
                time.sleep(0.02)
                row = self.client.get("/api/operations/" + row["id"]).json()
            return 200, row
        finally:
            runtime.Runtime.chat = original

    def test_a_client_names_its_place_before_the_turn_runs(self):
        status, row = self.chat({"message": "Turn it up", "session": "radio", "place": RADIO})
        self.assertEqual((status, row["status"]), (200, "complete"), row)
        self.assertEqual(self.seen, [RADIO])
        self.assertEqual(runtime.read_workspace_places(self.c), {"radio": RADIO})

    def test_without_a_place_nothing_is_named(self):
        status, row = self.chat({"message": "Turn it up", "session": "radio"})
        self.assertEqual((status, row["status"]), (200, "complete"), row)
        self.assertEqual(runtime.read_workspace_places(self.c), {})

    def test_a_bad_place_is_refused_before_anything_runs(self):
        status, body = self.chat({"message": "hi", "session": "radio", "place": "a\nb" * 40})
        self.assertEqual(status, 400)
        self.assertIn("place", body["detail"])
        self.assertEqual(self.seen, [])


if __name__ == "__main__":
    unittest.main()
