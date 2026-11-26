"""A conversation's first turn carries the whole snapshot; later turns only what changed.

Hermes replays every turn's injected context with the history. A whole snapshot each turn
meant each message re-sent (and re-cached) the same sections; now the first turn's snapshot
stays in the history, cached, and each later turn adds only its changes. Scheduled runs are
one turn each and keep one plain snapshot.
"""

import datetime as dt
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "kit/scripts"))

import companion_config as cc  # noqa: E402
import companion_context as context  # noqa: E402
import companion_local_context as engine  # noqa: E402

NOW = dt.datetime(2026, 10, 10, 12, tzinfo=dt.timezone.utc)


class ConversationTurnTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        self.c = cc.Companion(
            agent="Nova",
            human="Robin",
            profile="nova",
            timezone="UTC",
            hermes_root=root / ".hermes",
            vault=root / "vault",
            context_tokens=272000,
        )
        self.c.home.mkdir(parents=True)

    def turn(self, text, history=(), first=False, minutes=0, platform="telegram"):
        payload = {
            "session_id": "20261010_120000_abc",
            "extra": {
                "user_message": text,
                "platform": platform,
                "is_first_turn": first,
                "conversation_history": list(history),
            },
        }
        return context.for_turn(
            self.c, payload, now=NOW + dt.timedelta(minutes=minutes)
        )

    @staticmethod
    def sent(text, block):
        return {"role": "user", "content": text, "api_content": text + "\n\n" + block}

    def test_later_turns_carry_only_what_changed(self):
        first = self.turn("Hi", first=True)
        self.assertIn("continuity-base:begin", first)
        self.assertIn("[Nova — continuity workflow]", first)
        history = [self.sent("Hi", first)]
        second = self.turn("How was your day?", history, minutes=5)
        self.assertIn("continuity-update:begin", second)
        self.assertIn("[Current time: 2026-10-10T12:05", second)
        self.assertNotIn("[Nova — continuity workflow]", second)
        self.assertLess(len(second), len(first) / 2)
        history.append(self.sent("How was your day?", second))
        third = self.turn("Same minute", history, minutes=5)
        self.assertNotIn(
            "[Current time:", third
        )  # nothing changed since the last update

    def test_a_snapshot_the_history_no_longer_holds_is_sent_whole_again(self):
        self.turn("Hi", first=True)
        summary = [{"role": "user", "content": "[Summary of the earlier conversation]"}]
        again = self.turn("Still there?", summary, minutes=5)
        self.assertIn("continuity-base:begin", again)
        self.assertIn("[Nova — continuity workflow]", again)

    def test_scheduled_runs_keep_one_plain_snapshot(self):
        out = self.turn("[Scheduled run] check in", first=True, platform="cron")
        self.assertTrue(out.startswith(engine.BEGIN))
        self.assertNotIn("continuity-base", out)
        self.assertFalse((self.c.home / context.TURNS_DIR).exists())

    def test_the_context_engine_leaves_both_new_fences_in_place(self):
        first = self.turn("Hi", first=True)
        rows = [self.sent("Hi", first)]
        second = self.turn("And now?", rows, minutes=5)
        rows.append(self.sent("And now?", second))
        request = [{"role": "user", "content": row["api_content"]} for row in rows]
        self.assertIsNone(engine.select_messages(request, rows, "Nova"))


if __name__ == "__main__":
    unittest.main()
