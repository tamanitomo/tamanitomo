"""She can ask things of the human, and whether they come through can land."""

import datetime as dt
import json
from unittest.mock import patch

import pytest

import companion_asks as asks
import companion_config as cc
import companion_feelings as feelings
import companion_gates as gates
import companion_outbox as outbox
import companion_preread as preread

UTC = dt.timezone.utc
NOON = dt.datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


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


def at_stage(stage):
    return patch.object(gates, "stage_now", return_value=stage)


def test_how_many_may_wait_follows_the_ladder(companion):
    with at_stage(0):
        with pytest.raises(ValueError, match="too early"):
            asks.ask(companion, "pick tonight's film", "this_evening", now=NOON)
    with at_stage(1):
        first = asks.ask(companion, "pick tonight's film", "this_evening", "choose", now=NOON)
        assert first["ask"]["status"] == "open" and first["written"]
        with pytest.raises(ValueError, match="already waiting"):
            asks.ask(companion, "send the sunset photo", "+3h", now=NOON)
        # Asking the same thing again is the same ask, not a second one.
        again = asks.ask(companion, "Pick tonight's film", "this_evening", now=NOON)
        assert not again["written"] and again["ask"]["id"] == first["ask"]["id"]
    with at_stage(3):
        asks.ask(companion, "send the sunset photo", "+3h", "share", now=NOON)
        with pytest.raises(ValueError, match="asked 2 things today"):
            asks.ask(companion, "try the song I found", "tomorrow", "try", now=NOON)
        later = NOON + dt.timedelta(days=1)
        asks.ask(companion, "try the song I found", "tomorrow", "try", now=later)


def test_a_kept_ask_is_a_connection_a_miss_a_small_hurt_and_a_no_nothing(companion):
    with at_stage(3):
        film = asks.ask(companion, "pick tonight's film", "+2h", now=NOON)["ask"]["id"]
        photo = asks.ask(companion, "send the sunset photo", "+3h", now=NOON)["ask"]["id"]
    later = NOON + dt.timedelta(hours=5)
    kept = asks.settle(companion, film, "done", "Robin: ok, Paddington 2 it is", now=later)
    assert kept["ask"]["status"] == "done"
    assert [r["topic"] for r in feelings.experiences(companion)] == ["came through"]
    missed = asks.settle(
        companion, photo, "missed", "No photo came; Robin went quiet", felt=0.9, now=later
    )
    rows = feelings.experiences(companion)
    hurt = next(r for r in rows if r["kind"] == "rupture")
    assert hurt["topic"] == "let down" and hurt["strength"] == 0.3  # capped
    assert missed["ask"]["status"] == "missed"
    assert not asks.asks(companion, "open")
    tomorrow = later + dt.timedelta(days=1)
    with at_stage(3):
        third = asks.ask(companion, "call me after work", "+4h", now=tomorrow)["ask"]["id"]
    before = len(feelings.experiences(companion))
    asks.settle(companion, third, "declined", "Robin: can't tonight, tomorrow?", now=tomorrow)
    assert len(feelings.experiences(companion)) == before
    with pytest.raises(ValueError, match="already settled"):
        asks.settle(companion, third, "done", "x", now=tomorrow)
    with pytest.raises(ValueError, match="There is no ask"):
        asks.settle(companion, "ask-nope", "done", "x", now=tomorrow)


def test_a_background_ask_queues_its_message_and_wakes_at_its_due_time(companion):
    with at_stage(3):
        made = asks.ask(
            companion,
            "send a photo of the lake",
            "+3h",
            "share",
            queue="Send me the lake when you get there? I want to see it",
            now=NOON,
        )
    queued = outbox.waiting(companion, NOON)
    assert [q["body"] for q in queued] == [
        "Send me the lake when you get there? I want to see it"
    ]
    assert made["queued"]
    shown = asks.render(companion, NOON)
    assert "send a photo of the lake (due in 3 h)" in shown
    assert "was due" in asks.render(companion, NOON + dt.timedelta(hours=4))
    assert asks.marks(companion, NOON) != asks.marks(
        companion, NOON + dt.timedelta(hours=4)
    )
    assert asks.marks(companion, NOON + dt.timedelta(hours=4)) == asks.marks(
        companion, NOON + dt.timedelta(hours=5)
    )


def test_the_due_time_must_be_readable_and_soon(companion):
    with at_stage(3):
        for bad in ("", "whenever", "2026-10-19T10:00", "+30d"):
            with pytest.raises(ValueError):
                asks.ask(companion, "pick a film", bad, now=NOON)


def test_the_pre_read_says_how_her_day_of_writing_has_gone(companion):
    with at_stage(3):
        text = preread.texting_block(companion, NOON + dt.timedelta(hours=3))
        assert "0 so far" in text and "3–5 times" in text
        assert "unusual now" in text
        morning = preread.texting_block(companion, NOON - dt.timedelta(hours=3))
        assert "unusual" not in morning
        assert preread.texting_block(companion, NOON + dt.timedelta(hours=12)) == ""
    with at_stage(0):
        assert preread.texting_block(companion, NOON) == ""
    companion.outreach_per_day = 2
    with at_stage(4):
        assert "write first 2 times" in preread.texting_block(companion, NOON)
