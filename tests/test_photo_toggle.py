"""Switching photos back on in the app resumes the timeline job, as the CLI toggle does."""

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "kit/scripts"))

import companion_config as cc  # noqa: E402
from kit.app import settings_service  # noqa: E402


class Runtime:
    def __init__(self, code=0):
        self.calls, self.code = [], code

    def run(self, args, home=None, check=True, **_):
        self.calls.append(list(args))
        return subprocess.CompletedProcess(args, self.code, "", "")


def companion(tmp_path, jobs):
    c = cc.Companion(
        agent="Nova", human="Robin", hermes_root=tmp_path / "h", vault=tmp_path / "v"
    )
    (c.home / "cron").mkdir(parents=True)
    (c.home / "cron/jobs.json").write_text(json.dumps({"jobs": jobs}), encoding="utf-8")
    return c


def test_a_paused_timeline_job_is_resumed(tmp_path):
    c = companion(
        tmp_path,
        [
            {
                "id": "t1",
                "name": "Nova image timeline",
                "enabled": False,
                "state": "paused",
            }
        ],
    )
    runtime = Runtime()
    line = settings_service.resume_timeline(c, runtime)
    assert runtime.calls == [["cron", "resume", "t1"]]
    assert "running again" in line


def test_a_running_or_missing_job_is_left_alone(tmp_path):
    runtime = Runtime()
    running = companion(
        tmp_path / "a", [{"id": "t1", "name": "Nova image timeline", "enabled": True}]
    )
    assert "already running" in settings_service.resume_timeline(running, runtime)
    missing = companion(tmp_path / "b", [])
    assert "added by repair" in settings_service.resume_timeline(missing, runtime)
    assert runtime.calls == []


def test_a_failed_resume_says_so(tmp_path):
    c = companion(
        tmp_path, [{"id": "t1", "name": "Nova image timeline", "enabled": False}]
    )
    assert settings_service.resume_timeline(c, Runtime(code=1)).startswith("  !")
