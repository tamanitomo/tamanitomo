"""On this day: a few true memories from today's date a month, a season, a year or years ago.

Read from her own records (every conversation kept, what they watched, the moments she wrote down, the times she
felt close, what she said while watching), the furthest back first, at most four lines, machinery left out, and
nothing at all when there is nothing true to say.
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

import companion_config as cc  # noqa: E402
import companion_context as ctx  # noqa: E402
import companion_onthisday as otd  # noqa: E402
import companion_sensors as sensors  # noqa: E402
from chat_fixtures import OWNER_TELEGRAM, HermesStore  # noqa: E402

TZ = ZoneInfo("America/New_York")
TODAY = dt.datetime(2028, 3, 14, 12, 0, tzinfo=TZ)


def on(year, month, day, hour=20):
    return dt.datetime(year, month, day, hour, 0, tzinfo=TZ)


class OnThisDayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.c = cc.Companion(
            agent="Nova", human="Robin", profile="nova", timezone="America/New_York",
            hermes_root=self.tmp / ".hermes", vault=self.tmp / "vault", context_tokens=272000,
            sensors=["onthisday"],
        )  # fmt: skip
        self.c.home.mkdir(parents=True)
        self.c.life.mkdir(parents=True)
        self.c.soul_dir.mkdir(parents=True, exist_ok=True)
        (self.c.home / ".tamanitomo-chat-owner.json").write_text(
            json.dumps({"telegram": [OWNER_TELEGRAM]}), encoding="utf-8"
        )
        self.store = HermesStore(self.c.home)
        owner = dict(user_id=OWNER_TELEGRAM, chat_id=OWNER_TELEGRAM, chat_type="dm")
        self.store.session("tg", "telegram", started=on(2026, 1, 1).timestamp(), **owner)

    def say(self, when, text, role="user"):
        self.store.say("tg", role, text, when.timestamp())

    def write(self, name, rows):
        with (self.c.life / name).open("a", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")

    def test_nothing_true_to_say_is_nothing(self):
        self.assertEqual(otd.render(self.c, TODAY), ("", {"items": []}))

    def test_the_best_line_of_a_day_a_year_ago(self):
        self.say(on(2027, 3, 14, 9), "ok restart the gateway and check the logs")
        self.say(on(2027, 3, 14, 21), "We went to the harbor festival and I laughed the whole time, best night")
        self.say(on(2027, 3, 14, 22), "lol")
        text, data = otd.render(self.c, TODAY)
        self.assertIn('- A year ago today (14 March 2027): Robin said on Telegram: "We went to the harbor festival', text)
        self.assertNotIn("restart the gateway", text)
        self.assertEqual(data["items"][0]["date"], "2027-03-14")

    def test_machinery_and_paths_are_not_memories(self):
        self.say(on(2027, 3, 14), "copy it to /srv/files/backup/today and run the install script")
        self.assertEqual(otd.render(self.c, TODAY)[0], "")

    def test_what_she_kept_watched_and_felt(self):
        self.write("relationship.jsonl", [{"id": "rel-1", "kind": "moment", "moment": "note",
                                           "text": "Robin taught me a card trick", "happened_on": "2027-12-14",
                                           "status": "active", "recorded_at": "2027-12-14T22:00:00-05:00"}])  # fmt: skip
        self.write("relationship-feelings.jsonl", [{"kind": "connection", "text": "We stayed up talking about stars",
                                                    "at": on(2027, 9, 14).isoformat()}])  # fmt: skip
        self.write("viewing.jsonl", [
            {"kind": "seen", "what": "movie", "title": "Harbor Lights", "year": 2019, "together": True,
             "at": on(2028, 2, 14).isoformat()},
        ])  # fmt: skip
        self.write("watchalong.jsonl", [{"event": "said", "said": "aww, same", "title": "Harbor Lights (2019)",
                                         "at": on(2028, 2, 14, 21).isoformat()}])  # fmt: skip
        text, data = otd.render(self.c, TODAY)
        labels = [row["label"] for row in data["items"]]
        self.assertEqual(labels, ["Six months ago", "Three months ago", "A month ago"])  # the furthest back first
        self.assertIn('you felt close: "We stayed up talking about stars"', text)
        self.assertIn('you wrote down: "Robin taught me a card trick"', text)
        self.assertIn('you two watched Harbor Lights (2019); you said "aww, same" while watching Harbor Lights', text)

    def test_at_most_four_lines(self):
        for years in range(1, 7):
            self.say(on(2028 - years, 3, 14), f"Our favourite dinner again, year {years}, I love these nights")
        _text, data = otd.render(self.c, TODAY)
        self.assertEqual(sum(len(row["lines"]) for row in data["items"]), otd.MAX_ITEMS)
        self.assertEqual(data["items"][0]["label"], "6 years ago")

    def test_a_leap_day_and_short_months(self):
        days = dict((label, day) for label, day in otd.past_days(dt.date(2028, 2, 29)))
        self.assertEqual(days["A year ago"], dt.date(2027, 2, 28))
        self.assertEqual(dict(otd.past_days(dt.date(2028, 5, 31)))["Three months ago"], dt.date(2028, 2, 29))

    def test_her_context_carries_todays_memories(self):
        self.say(on(2027, 3, 14), "We went to the harbor festival and I laughed the whole time, best night")
        sensors.run_one(self.c, "onthisday", TODAY.astimezone(dt.timezone.utc))
        out = ctx.build(self.c, {"extra": {"user_message": "hey", "platform": "telegram"}}, now=TODAY)
        self.assertIn("[On this day]", out)
        self.assertIn("harbor festival", out)
        self.assertNotIn("On this day:", out)  # its own section, not the ambient block


if __name__ == "__main__":
    unittest.main()
