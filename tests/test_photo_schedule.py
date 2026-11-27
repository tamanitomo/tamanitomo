"""Photo times stay inside waking hours; the old quiet-hours-blind schedule is migrated."""

import dataclasses
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "kit/scripts"))

import companion_config as cc  # noqa: E402
from kit.cli import scaffold  # noqa: E402
from kit.cli.common import timeline_expr, waking_hours  # noqa: E402


def companion(tmp_path=None, **extra):
    base = dict(agent="Nova", human="Robin", quiet_start="23:00", quiet_end="08:00")
    if tmp_path is not None:
        base.update(hermes_root=tmp_path / "h", vault=tmp_path / "v")
    return cc.Companion(**{**base, **extra})


def test_hourly_and_longer_intervals_keep_to_waking_hours():
    c = companion()
    assert timeline_expr(c, 15) == "3-59/15 * * * *"
    assert timeline_expr(c, 240) == "3 8,12,16,20 * * *"
    assert timeline_expr(c, 720) == "3 8,20 * * *"
    assert timeline_expr(c, 1440) == "3 15 * * *"
    # Before, a day-long interval ran at 00:03, inside quiet hours: no photos at all.
    assert 0 not in waking_hours(c)


def test_a_night_that_crosses_midnight_and_one_ending_on_the_half_hour():
    late = companion(quiet_start="02:00", quiet_end="10:00")
    assert waking_hours(late)[0] == 10 and waking_hours(late)[-1] == 1
    assert timeline_expr(late, 1440) == "3 18 * * *"
    half = companion(quiet_end="07:30")
    assert waking_hours(half)[0] == 8


def run_refresh(tmp_path, expr, old_minutes, new_minutes):
    old = companion(tmp_path, image_timeline=True, image_interval_minutes=old_minutes)
    new = dataclasses.replace(old, image_interval_minutes=new_minutes)
    (new.home / "cron").mkdir(parents=True)
    job = {"id": "t1", "name": "Nova image timeline", "schedule": {"expr": expr}}
    (new.home / "cron/jobs.json").write_text(
        json.dumps({"jobs": [job]}), encoding="utf-8"
    )
    calls = []

    def run_cmd(args, home=None):
        calls.append(list(args))
        return subprocess.CompletedProcess(args, 0, "", "")

    scaffold.refresh_schedules(old, new, [], run_cmd=run_cmd)
    return calls


def test_the_old_schedule_follows_a_new_interval(tmp_path):
    calls = run_refresh(tmp_path, "3 0 * * *", 1440, 720)
    assert calls == [["cron", "edit", "t1", "--schedule", "3 8,20 * * *"]]


def test_a_schedule_someone_chose_is_left_alone(tmp_path):
    assert run_refresh(tmp_path, "7 9 * * *", 1440, 720) == []
