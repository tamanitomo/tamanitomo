"""Pausing one job is a choice, not a fault, so later settings saves keep working."""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "kit/scripts"))

import companion_config as cc  # noqa: E402
from kit.cli import doctor  # noqa: E402


def companion(tmp_path, active=True):
    c = cc.Companion(
        agent="Nova", human="Robin", hermes_root=tmp_path / "h", vault=tmp_path / "v"
    )
    c.cron_active = active
    return c


def job(name, enabled=True, **extra):
    return {
        "name": name,
        "enabled": enabled,
        "next_run_at": "2026-11-26T12:00:00",
        **extra,
    }


def test_a_job_paused_on_its_own_is_not_a_mismatch(tmp_path):
    c = companion(tmp_path)
    jobs = [
        job("Nova companion pulse"),
        job(
            "Nova image timeline",
            enabled=False,
            state="paused",
            paused_at="2026-11-26T10:00:00",
        ),
    ]
    assert doctor.schedule_state_mismatches(c, jobs, set()) == []
    assert doctor.deliberately_paused(jobs[1])


def test_a_job_that_is_off_for_no_reason_still_is(tmp_path):
    c = companion(tmp_path)
    jobs = [job("Nova companion pulse", enabled=False, state="scheduled")]
    assert [j["name"] for j in doctor.schedule_state_mismatches(c, jobs, set())] == [
        "Nova companion pulse"
    ]


def test_a_job_running_inside_a_paused_routine_is_wrong(tmp_path):
    c = companion(tmp_path, active=False)
    jobs = [
        job("Nova companion pulse"),
        job("Nova autonomy loop", enabled=False, state="paused"),
    ]
    assert [j["name"] for j in doctor.schedule_state_mismatches(c, jobs, set())] == [
        "Nova companion pulse"
    ]


def test_script_jobs_run_whatever_the_routine_unless_paused_on_purpose(tmp_path):
    c = companion(tmp_path, active=False)
    scripted = {"Nova outbox dispatcher"}
    assert (
        doctor.schedule_state_mismatches(c, [job("Nova outbox dispatcher")], scripted)
        == []
    )
    paused = job("Nova outbox dispatcher", enabled=False, state="paused")
    assert doctor.schedule_state_mismatches(c, [paused], scripted) == []
