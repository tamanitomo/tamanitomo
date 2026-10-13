"""A caring callback wakes at its horizon, without turning every tick into a run."""

import datetime as dt
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "kit/scripts"))

import companion_config as cc  # noqa: E402
import companion_loops as loops  # noqa: E402
import companion_preread as preread  # noqa: E402
import companion_sleep as sleep  # noqa: E402

DAY = dt.datetime(2026, 10, 20, tzinfo=dt.timezone.utc)


def at(hour, minute=0):
    return DAY + dt.timedelta(hours=hour, minutes=minute)


@pytest.fixture
def companion(tmp_path):
    c = cc.Companion(
        agent="Nova",
        human="Robin",
        hermes_root=tmp_path / "hermes",
        vault=tmp_path / "vault",
        timezone="UTC",
        quiet_start="23:00",
        quiet_end="07:00",
        soul_in_vault=False,
    )
    c.life.mkdir(parents=True)
    loops.add(
        c,
        {
            "id": "interview",
            "title": "Ask how the interview went",
            "detail": "The interview is this morning",
            "gentle_use": "One warm question after the interview",
            "follow_up_at": "2026-10-20T11:00:00+01:00",
        },
        at(9),
    )
    return c


def test_callback_crosses_its_horizon_once_without_waiting_for_six_hour_bucket(
    companion,
):
    before = preread.fingerprint(companion, at(9, 42))
    due = preread.fingerprint(companion, at(10))
    assert "CALLBACKS READY" not in loops.render(companion, now=at(9, 42))
    assert "CALLBACKS READY" in loops.render(companion, now=at(10))
    assert before != due
    assert preread.fingerprint(companion, at(9, 59)) == before
    assert preread.fingerprint(companion, at(10, 12)) == due
    assert preread.fingerprint(companion, at(11, 59)) == due


@pytest.mark.parametrize(
    "change",
    [
        {"detail": "The interview finished early"},
        {"gentle_use": "Only raise this if they mention work"},
        {"category": "promise"},
        {"note": "They asked to discuss this after lunch"},
        {"follow_up_at": "2026-10-20T11:00:00+00:00"},
        {"status": "closed"},
    ],
)
def test_meaningful_callback_changes_wake_autonomy(companion, change):
    before = preread.fingerprint(companion, at(9, 10))
    loops.update(companion, {"id": "interview", **change}, at(9, 11))
    after = preread.fingerprint(companion, at(9, 12))
    assert before != after
    assert after == preread.fingerprint(companion, at(9, 13))


def test_identical_update_and_reordering_do_not_wake_autonomy(companion):
    loops.add(
        companion,
        {"id": "other", "title": "Another thread", "gentle_use": "When it fits"},
        at(9, 1),
    )
    before = preread.fingerprint(companion, at(9, 10))
    loops.update(
        companion,
        {"id": "interview", "detail": "The interview is this morning"},
        at(9, 11),
    )
    assert preread.fingerprint(companion, at(9, 12)) == before


def test_a_due_callback_preserves_sleep_gating(companion):
    sleep.declare(companion, "07:00", now=at(1))
    loops.update(companion, {"id": "interview", "follow_up_after": "+1h"}, at(1))
    before = preread.fingerprint(companion, at(1, 42))
    assert before.startswith("sleep ")
    assert preread.fingerprint(companion, at(2, 12)) == before
    assert not preread.fingerprint(companion, at(8)).startswith("sleep ")


def test_a_long_ledger_renders_recent_threads_and_names_the_rest(companion):
    # Forty threads, one a month-old callback: the run sees this week's, not all.
    for i in range(40):
        loops.add(
            companion,
            {
                "id": f"thread-{i:02d}",
                "title": f"Thread {i:02d}",
                "detail": "x" * 590,
                "gentle_use": "only if it comes up",
                **(
                    {"follow_up_at": "2026-09-15T09:00:00+00:00"}
                    if i == 0
                    else {}
                ),
            },
            DAY - dt.timedelta(days=40 - i),
        )
    shown = loops.render(companion, now=at(12))
    assert "Ask how the interview went" in shown  # due today
    assert "**Thread 00**" not in shown  # a September callback is not "ready" now
    assert "### Thread 39" in shown and "### Thread 20" not in shown
    assert "x" * 300 not in shown
    assert "older open thread(s) not shown" in shown and "and 20 more" in shown
    assert len(shown) < 6000
    everything = loops.render(companion, limit=None, now=at(12))
    assert "**Thread 00**" in everything and "x" * 590 in everything
