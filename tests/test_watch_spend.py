"""A routine run far past its usual size is flagged the same day.

A model that explored instead of doing the job read about 2.9 million tokens a
pulse where other models read 0.3 million, and nothing said so until the
allowance ran low.
"""

import datetime as dt
import json
import sqlite3

import pytest

import companion_config as cc
import companion_watch as watch

NOW = dt.datetime(2026, 10, 12, 15, 30, tzinfo=dt.timezone.utc)


@pytest.fixture
def companion(tmp_path):
    c = cc.Companion(agent="Nova", human="Alex", hermes_root=tmp_path / "home", vault=tmp_path / "vault")
    (c.home / "cron").mkdir(parents=True)
    (c.home / "cron/jobs.json").write_text(
        json.dumps({"jobs": [{"id": "abc123", "name": "Nova companion pulse", "enabled": True}]}),
        encoding="utf-8",
    )
    db = sqlite3.connect(c.home / "state.db")
    db.execute(
        "create table sessions (id text, started_at real, model text, input_tokens int, "
        "cache_read_tokens int, output_tokens int)"
    )
    db.commit()
    db.close()
    return c


def runs(c, *rows):
    db = sqlite3.connect(c.home / "state.db")
    for hours_ago, total, model in rows:
        at = NOW - dt.timedelta(hours=hours_ago)
        db.execute(
            "insert into sessions values (?, ?, ?, ?, ?, ?)",
            (f"cron_abc123_{at:%Y%m%d_%H%M%S}", at.timestamp(), model, total // 10, total - total // 10, 0),
        )
    db.commit()
    db.close()


USUAL = [(h, 300_000, "steady-model") for h in (30, 28, 26, 24, 22, 20)]


def test_a_run_several_times_the_usual_size_is_flagged(companion):
    runs(companion, *USUAL, (1, 2_900_000, "explorer-model"))
    found = watch.check_spend(companion, NOW)
    assert len(found) == 1
    assert '"Nova companion pulse" is using far more than usual on explorer-model' in found[0]


def test_an_ordinary_run_is_not(companion):
    runs(companion, *USUAL, (1, 450_000, "steady-model"))
    assert watch.check_spend(companion, NOW) == []


def test_a_large_job_that_is_always_large_is_not(companion):
    runs(companion, *[(h, 2_000_000, "m") for h in (30, 28, 26, 24, 22)], (1, 2_200_000, "m"))
    assert watch.check_spend(companion, NOW) == []


def test_runs_after_the_moment_checked_do_not_count(companion):
    runs(companion, *USUAL, (1, 2_900_000, "explorer-model"))
    assert watch.check_spend(companion, NOW - dt.timedelta(hours=2)) == []


def test_the_wording_does_not_change_from_run_to_run(companion):
    # The watch repeats an alert only when its text changes.
    runs(companion, *USUAL, (1, 2_900_000, "explorer-model"))
    first = watch.check_spend(companion, NOW)
    runs(companion, (0.5, 3_400_000, "explorer-model"))
    assert watch.check_spend(companion, NOW) == first
