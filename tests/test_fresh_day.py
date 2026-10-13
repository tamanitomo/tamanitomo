"""A new day starts fresh: last night's reading of the human does not outlive it,
a good morning is part of a close relationship, and teeth do not block getting dressed."""

import datetime as dt
import json
from unittest.mock import patch

import pytest

import companion_config as cc
import companion_gates as gates
import companion_lifestyle as lifestyle
import companion_preread as preread
import companion_sleep as sleep
import companion_thread as thread

UTC = dt.timezone.utc
EVENING = dt.datetime(2026, 10, 19, 21, 0, tzinfo=UTC)
MORNING = dt.datetime(2026, 10, 20, 8, 30, tzinfo=UTC)


@pytest.fixture
def companion(tmp_path):
    c = cc.Companion(
        agent="Nova",
        human="Robin",
        hermes_root=tmp_path / "hermes",
        vault=tmp_path / "vault",
        timezone="UTC",
        outreach="free",
        outreach_per_day=8,
        quiet_start="23:00",
        quiet_end="07:00",
        soul_in_vault=False,
    )
    c.home.mkdir(parents=True)
    c.life.mkdir(parents=True)
    c.save()
    return c


def last_heard(at):
    return patch.object(
        thread,
        "read",
        return_value={
            "available": True,
            "last_from_human": at.isoformat(),
            "hours_since_human": 11.5,
        },
    )


def declare(c, start, until):
    sleep.path(c).write_text(
        json.dumps({"from": start.isoformat(), "until": until.isoformat()})
    )


def test_a_night_since_they_talked_starts_the_day_fresh(companion):
    declare(companion, EVENING + dt.timedelta(hours=2), MORNING)
    with last_heard(EVENING), patch.object(gates, "stage_now", return_value=3):
        text = preread.texting_block(companion, MORNING + dt.timedelta(hours=5))
    assert "A night has passed since you two last talked" in text
    assert "does not carry into today" in text
    # The same evening, nothing is fresh yet.
    declare(companion, EVENING + dt.timedelta(hours=2), MORNING)
    with last_heard(EVENING), patch.object(gates, "stage_now", return_value=3):
        late = preread.texting_block(companion, EVENING + dt.timedelta(hours=1))
    assert "A night has passed" not in late


def test_without_a_declared_night_the_end_of_quiet_hours_counts(companion):
    assert preread.slept_since(companion, EVENING, MORNING)
    assert not preread.slept_since(companion, MORNING, MORNING + dt.timedelta(hours=2))


def test_the_morning_job_hears_about_its_good_morning_at_a_close_stage(companion):
    declare(companion, EVENING + dt.timedelta(hours=2), MORNING)
    with last_heard(EVENING), patch.object(gates, "stage_now", return_value=3):
        close = preread.texting_block(companion, MORNING, waking=True)
    assert "A good morning from you is part of how you and Robin are now" in close
    with last_heard(EVENING), patch.object(gates, "stage_now", return_value=1):
        newer = preread.texting_block(companion, MORNING, waking=True)
    assert "good morning from you" not in newer


def dressing(companion, elapsed_minutes, teeth_at=None):
    (companion.life / "routine.json").write_text(
        json.dumps({"kind": "imagined_routine", "lifestyle": {"enabled": True}})
    )
    start = MORNING
    previous = {
        "recorded_at": start.isoformat(),
        "state": {
            "outfit": [{"id": "pajamas"}],
            "activity": "waking up",
            "lifestyle": {
                "clothes": {"pajamas": "wearing", "tee": "clean"},
                "teeth_at": teeth_at,
                "shower_at": None,
                "laundry": None,
                "wearing_since": {"pajamas": start.isoformat()},
            },
        },
    }
    closet = [
        {"id": "pajamas", "category": "sleep"},
        {"id": "tee", "category": "day"},
    ]
    with patch("companion_life.routine", return_value={"active_suggestions": []}):
        return lifestyle.evolve(
            companion,
            {"activity": "getting dressed", "activity_change": "transition"},
            ["tee"],
            previous,
            closet,
            start + dt.timedelta(minutes=elapsed_minutes),
        )


def test_getting_dressed_brushes_her_teeth_when_there_was_time(companion):
    done = dressing(companion, elapsed_minutes=10)
    assert done["teeth_at"] == (MORNING + dt.timedelta(minutes=10)).isoformat()
    with pytest.raises(ValueError, match="brush teeth today"):
        dressing(companion, elapsed_minutes=1)
