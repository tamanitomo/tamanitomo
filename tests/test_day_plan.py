"""Every day she lives has a plan, whichever model wrote her evening."""

import datetime as dt
import json
import pathlib
import subprocess
import sys
from unittest.mock import patch

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "kit/scripts"))

import companion_config as cc  # noqa: E402
import companion_life as life  # noqa: E402
import companion_meters as meters  # noqa: E402
import companion_needs as needs  # noqa: E402
import companion_plan as plan  # noqa: E402
import companion_sleep as sleep  # noqa: E402

UTC = dt.timezone.utc
DAY = dt.datetime(2026, 10, 20, tzinfo=UTC)  # a Tuesday
ROUTINE = {
    "kind": "imagined_routine",
    "weekly": [
        {
            "day": "tuesday",
            "start": "18:00",
            "end": "19:00",
            "activity": "pottery class",
            "setting": "the community studio",
        }
    ],
    "daily": [
        {"start": "08:00", "end": "09:00", "activity": "breakfast", "setting": "home"},
    ],
    "routines_catalog": {
        "beach-day": {
            "anchors": [
                {"start": "10:00", "end": "15:00", "activity": "the beach"},
            ]
        }
    },
}


def at(hour, minute=0, day=0):
    return DAY + dt.timedelta(days=day, hours=hour, minutes=minute)


@pytest.fixture
def companion(tmp_path):
    c = cc.Companion(
        agent="Nova",
        human="Robin",
        hermes_root=tmp_path / "hermes",
        vault=tmp_path / "vault",
        timezone="UTC",
        boundary="next-door",
        quiet_start="23:00",
        quiet_end="07:00",
        soul_in_vault=False,
    )
    c.home.mkdir(parents=True)
    c.life.mkdir(parents=True)
    c.save()
    (c.life / "routine.json").write_text(json.dumps(ROUTINE))
    return c


def night(c, start, end):
    sleep.path(c).write_text(
        json.dumps(
            {
                "from": start.isoformat(),
                "until": end.isoformat(),
                "hours": (end - start).total_seconds() / 3600,
            }
        )
    )


def run_life(c, *args):
    out = subprocess.run(
        [sys.executable, str(ROOT / "kit/scripts/companion_life.py"), "--home"]
        + [str(c.home), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(out.stdout)


class TestHerEveningPlan:
    def test_planning_tomorrow_writes_the_days_plan(self, companion):
        out = run_life(
            companion, "plan-tomorrow", "--intent", "A slow day with a long walk"
        )
        written = plan.read(companion, out["date"])
        assert written["intent"] == "A slow day with a long walk"
        assert written["settled_at"] and written["items"] == []
        # The calendar still shows her routine for a plan that lists nothing.
        shape = life.expected_day(companion.life, dt.date.fromisoformat(out["date"]))
        assert shape["source"] == "routine"
        assert "breakfast" in [a["activity"] for a in shape["anchors"]]
        assert shape["intended_plan"]["intent"] == "A slow day with a long walk"

    def test_a_chosen_day_shape_keeps_its_anchors(self, companion):
        out = run_life(
            companion, "plan-tomorrow", "--intent", "Sun", "--theme", "beach-day"
        )
        shape = life.expected_day(companion.life, dt.date.fromisoformat(out["date"]))
        assert [a["activity"] for a in shape["anchors"]] == ["the beach"]

    def test_her_own_hours_become_the_plan(self, companion, tmp_path):
        anchors = tmp_path / "anchors.json"
        anchors.write_text(
            json.dumps(
                [
                    {"start": "09:00", "end": "10:00", "activity": "swim"},
                    {"start": "09:30", "end": "11:00", "activity": "market"},
                    {"start": "12:00", "end": "13:00", "activity": "lunch out"},
                ]
            )
        )
        out = run_life(
            companion,
            "plan-tomorrow",
            "--intent",
            "Swim, then lunch out",
            "--anchors-file",
            str(anchors),
        )
        items = plan.read(companion, out["date"])["items"]
        assert [i["what"] for i in items] == ["swim", "lunch out"]
        assert out["not_planned"] == ["market overlaps something earlier"]


class TestADaySheDidNotPlan:
    def test_gets_a_plain_plan_once(self, companion):
        first = plan.ensure(companion, DAY.date(), at(8))
        again = plan.ensure(companion, DAY.date(), at(9))
        assert first["author"] == "routine"
        assert first["intent"] == "A usual Tuesday, nothing special planned"
        assert again["history"] == first["history"]

    def test_never_replaces_her_own(self, companion):
        plan.settle(companion, DAY.date(), "A day at the lake", now=at(7))
        assert plan.ensure(companion, DAY.date(), at(8))["intent"] == (
            "A day at the lake"
        )

    def test_her_evening_plan_replaces_it(self, companion):
        plan.ensure(companion, DAY.date(), at(8))
        plan.settle(companion, DAY.date(), "Changed my mind: the lake", now=at(9))
        assert plan.read(companion, DAY.date())["author"] == "companion"


class TestTheMetersJobKeepsTheDay:
    UNLUCKY = {
        "day": "2026-10-20",
        "kind": "unlucky",
        "roll": 4,
        "what": "a rough night",
        "effect": {"energy_start": -0.3},
    }

    def test_a_day_without_a_plan_gets_one_and_its_luck(self, companion):
        night(companion, at(23, day=-1), at(7))
        with patch.object(needs, "luck", return_value=self.UNLUCKY):
            meters.tick(companion, at(9))
            meters.tick(companion, at(9, 15))
        day = plan.read(companion, DAY.date())
        notes = [row["change"] for row in day["history"]]
        assert notes.count("luck: a rough night (unlucky, rolled 4 of 20)") == 1

    def test_nothing_is_planned_while_she_sleeps(self, companion):
        night(companion, at(23, day=-1), at(7))
        meters.tick(companion, at(3))
        assert not (companion.life / "plans").exists()
