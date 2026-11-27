"""Their word: what the human said they were about to do, and whether the evening went that way.

Only a mismatch is worth a line (more messages after goodnight, a film starting, a long "right back"), never a
goodnight followed by sleep; a question, a negation or "I had a good night" is no plan; the next morning is not
"still up"; and her context reads it live.
"""

import datetime as dt
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "kit" / "scripts"), str(ROOT)]

import companion_config as cc  # noqa: E402
import companion_context as ctx  # noqa: E402
import companion_plans as plans  # noqa: E402
from chat_fixtures import OWNER_TELEGRAM, HermesStore  # noqa: E402

TZ = ZoneInfo("America/New_York")


def on(day, hour, minute=0):
    return dt.datetime(2027, 3, day, hour, minute, tzinfo=TZ)


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.c = cc.Companion(
            agent="Nova", human="Robin", profile="nova", timezone="America/New_York",
            hermes_root=self.tmp / ".hermes", vault=self.tmp / "vault", context_tokens=272000,
            sensors=["plans"],
        )  # fmt: skip
        self.c.home.mkdir(parents=True)
        self.c.life.mkdir(parents=True)
        (self.c.soul_dir / "ambient").mkdir(parents=True, exist_ok=True)
        (self.c.home / ".tamanitomo-chat-owner.json").write_text(
            json.dumps({"telegram": [OWNER_TELEGRAM]}), encoding="utf-8"
        )
        self.store = HermesStore(self.c.home)
        owner = dict(user_id=OWNER_TELEGRAM, chat_id=OWNER_TELEGRAM, chat_type="dm")
        self.store.session("tg", "telegram", started=on(1, 9).timestamp(), **owner)

    def say(self, when, text, role="user"):
        self.store.say("tg", role, text, when.timestamp())

    def test_messages_after_goodnight(self):
        self.say(on(5, 23, 40), "ok I'm going to bed, night!")
        self.say(on(5, 23, 41), "Night, sleep well", role="assistant")
        self.say(on(6, 0, 25), "can't sleep lol, are you up?")
        text, data = plans.render(self.c, on(6, 0, 30))
        self.assertTrue(
            text.startswith(
                'Their word: At 23:40 Robin said goodnight ("ok I\'m going to bed, night!").'
            )
        )
        self.assertIn(
            "Since then: 1 more message (Telegram), the last at 00:25. So not asleep, then.",
            text,
        )
        self.assertIn("never a reason to message them", text)
        self.assertEqual(data["kind"], "sleep")

    def test_goodnight_and_then_sleep_is_nothing(self):
        self.say(on(5, 23, 40), "goodnight!")
        self.say(
            on(5, 23, 44), "sweet dreams, love you"
        )  # the goodbyes are not "still up"
        self.assertEqual(plans.render(self.c, on(6, 1, 0)), ("", {}))
        self.say(on(6, 7, 30), "good morning!")
        self.assertEqual(
            plans.render(self.c, on(6, 7, 35)), ("", {})
        )  # that's the next day

    def test_not_plans(self):
        for when, text in ((on(5, 12), "I had a good night, thanks"), (on(5, 23), "are you going to bed?"),
                           (on(5, 23), "I'm not going to bed yet"), (on(5, 13), "goodnight moon is a great book")):  # fmt: skip
            self.assertIsNone(plans.plan_in(text, when.hour), text)
        self.assertEqual(plans.plan_in("brb", 15), ("away", 10))
        self.assertEqual(plans.plan_in("back in 20 min!", 15), ("away", 20))
        self.assertEqual(plans.plan_in("ugh gotta go, talk later", 15), ("out", None))
        self.assertEqual(
            plans.plan_in("so I have to go. Try the blue one", 15), ("out", None)
        )
        for text in ("we may have to go with the other plan", "I have to go to the plant for cables",
                     "we have to go through it", "gonna have to go back to the shop"):  # fmt: skip
            self.assertIsNone(
                plans.plan_in(text, 15), text
            )  # where they go next is not goodbye

    def test_a_long_right_back(self):
        self.say(on(5, 14, 0), "brb")
        self.assertEqual(plans.render(self.c, on(5, 14, 20)), ("", {}))  # not long yet
        text, _ = plans.render(self.c, on(5, 15, 5))
        self.assertIn(
            'said they\'d be right back ("brb"). That was 1 hour 5 minutes ago, and nothing since.',
            text,
        )
        self.say(on(5, 15, 10), "back! sorry")
        text, _ = plans.render(self.c, on(5, 15, 15))
        self.assertIn("They came back at 15:10, 1 hour 10 minutes later.", text)
        self.assertEqual(
            plans.render(self.c, on(5, 16, 0)), ("", {})
        )  # said once, not a running tally

    def test_a_quick_right_back_is_nothing(self):
        self.say(on(5, 14, 0), "one sec")
        self.say(on(5, 14, 6), "returned, hi again")
        self.assertEqual(plans.render(self.c, on(5, 14, 10)), ("", {}))

    def test_a_film_and_a_game_after_goodnight(self):
        self.say(on(5, 23, 0), "heading to bed")
        with open(self.c.life / "viewing.jsonl", "w", encoding="utf-8") as f:
            f.write(json.dumps({"kind": "seen", "what": "movie", "title": "Harbor Lights", "year": 2019,
                                "at": on(6, 0, 50).isoformat()}) + "\n")  # fmt: skip
        self.say(on(6, 1, 10), "[Game event: Rook just reached level 31.]")
        (self.c.soul_dir / "ambient/viewing.json").write_text(
            json.dumps(
                {
                    "checked_at": on(6, 1, 15).isoformat(),
                    "playing": ["Tidewater (2021)"],
                }
            )
        )
        text, _ = plans.render(self.c, on(6, 1, 20))
        self.assertIn("they were playing a game (last at 01:10); they finished Harbor Lights (2019); "
                      "playing now: Tidewater (2021). So not asleep, then.", text)  # fmt: skip

    def test_out_after_goodnight(self):
        self.say(on(5, 23, 40), "ok going to bed, night")
        where = self.c.soul_dir / "ambient/where.json"
        where.write_text(
            json.dumps(
                {
                    "place": "Corner Market",
                    "since": on(6, 0, 15).isoformat(),
                    "source": "phone",
                }
            )
        )
        text, _ = plans.render(self.c, on(6, 0, 20))
        self.assertIn(
            "Since then: they got to Corner Market at 00:15. So not asleep, then.", text
        )
        where.write_text(
            json.dumps(
                {
                    "place": "",
                    "left": "Home",
                    "moving": True,
                    "since": on(6, 0, 5).isoformat(),
                }
            )
        )
        self.assertIn(
            "they left Home at 00:05, on the move",
            plans.render(self.c, on(6, 0, 10))[0],
        )
        where.write_text(
            json.dumps({"place": "Home", "since": on(6, 0, 5).isoformat()})
        )
        self.assertEqual(
            plans.render(self.c, on(6, 0, 10)), ("", {})
        )  # getting home is no mismatch
        where.write_text(
            json.dumps({"place": "Corner Market", "since": on(5, 23, 0).isoformat()})
        )
        self.assertEqual(
            plans.render(self.c, on(6, 0, 10)), ("", {})
        )  # there before goodnight

    def test_still_here_after_gotta_go(self):
        self.say(on(5, 18, 0), "gotta run, ttyl")
        self.say(on(5, 18, 30), "ok one more thing")
        text, _ = plans.render(self.c, on(5, 18, 35))
        self.assertIn("said they were heading off", text)
        self.assertIn("So still around, then.", text)
        self.say(on(5, 21, 0), "hey I'm home")  # hours later is just a new conversation
        self.assertEqual(plans.render(self.c, on(5, 21, 5)), ("", {}))

    def test_odd_records_are_nothing_to_say_never_a_broken_turn(self):
        self.say(on(5, 23, 40), "ok going to bed, night")
        (self.c.soul_dir / "ambient/where.json").write_text(
            "[1, 2, 3]"
        )  # a list, not an object
        self.assertEqual(plans.render(self.c, on(6, 0, 20)), ("", {}))
        with patch("companion_plans.read", side_effect=KeyError("boom")):
            self.assertEqual(plans.render(self.c, on(6, 0, 20)), ("", {}))
            out = ctx.build(
                self.c,
                {"extra": {"user_message": "hey", "platform": "telegram"}},
                now=on(6, 0, 21),
            )
            self.assertNotIn("Their word", out)

    def test_her_context_reads_it_live(self):
        self.say(on(5, 23, 40), "night night")
        self.say(on(6, 0, 30), "ok one more episode")
        out = ctx.build(
            self.c,
            {"extra": {"user_message": "hey", "platform": "telegram"}},
            now=on(6, 0, 31),
        )
        self.assertIn("[Their word] At 23:40 Robin said goodnight", out)


if __name__ == "__main__":
    unittest.main()
