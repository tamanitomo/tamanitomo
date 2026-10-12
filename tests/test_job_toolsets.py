"""Each kit job runs with only the tools its work needs.

The manifest always named them, but Hermes's cron command line has no flag to pass
them, so every job ran with every tool the platform allows. A model inclined to
explore spent a day pulse searching files, loading skills and inspecting images.
"""

import json
from unittest.mock import patch

import pytest

import companion_config as cc
from kit.cli import scaffold
from kit.cli.common import load_manifest


@pytest.fixture
def companion(tmp_path):
    c = cc.Companion(agent="Nova", human="Alex", hermes_root=tmp_path / "home", vault=tmp_path / "vault")
    (c.home / "cron").mkdir(parents=True)
    return c


def write_jobs(c, jobs):
    (c.home / "cron/jobs.json").write_text(json.dumps({"jobs": jobs}), encoding="utf-8")


def spec(c, key):
    return next(s for s in load_manifest(c)["jobs"] if s["key"] == key)


def run(c, jobs, bridge=None):
    write_jobs(c, jobs)
    calls = []

    def fake(_c, changes):
        calls.append(changes)
        return bridge(changes) if bridge else [
            {"id": ch["id"], "ok": True, "toolsets": ch["toolsets"], "unknown": []} for ch in changes
        ]

    report = []
    with patch.object(scaffold, "_cron_bridge", side_effect=fake):
        done = scaffold.apply_job_toolsets(c, {"AGENT": "Nova"}, report)
    return done, calls, report


def test_a_job_with_every_tool_is_given_only_its_own(companion):
    done, calls, report = run(companion, [{"id": "p1", "name": "Nova companion pulse", "enabled_toolsets": None}])
    assert done
    assert calls == [[{"id": "p1", "name": "Nova companion pulse", "toolsets": spec(companion, "pulse")["toolsets"]}]]
    assert any("tools limited to file, terminal" in line for line in report)


def test_a_job_already_limited_is_left_alone(companion):
    done, calls, _ = run(
        companion,
        [{"id": "p1", "name": "Nova companion pulse", "enabled_toolsets": list(reversed(spec(companion, "pulse")["toolsets"]))}],
    )
    assert done and calls == []


def test_scripted_jobs_are_not_given_tools(companion):
    done, calls, _ = run(companion, [{"id": "d1", "name": "Nova outbox dispatcher", "enabled_toolsets": None, "no_agent": True}])
    assert done and calls == []


def test_a_failure_is_reported_and_not_counted_as_done(companion):
    failing = lambda changes: [{"id": ch["id"], "ok": False, "error": "locked"} for ch in changes]
    done, _, report = run(companion, [{"id": "p1", "name": "Nova companion pulse"}], bridge=failing)
    assert not done
    assert any("could not set the tools for Nova companion pulse: locked" in line for line in report)


def test_research_gets_the_web_toolset_not_a_tool_name(companion):
    # "web_search" is a tool inside the `web` toolset; as a toolset name it named nothing.
    assert spec(companion, "window")["toolsets"] == ["file", "terminal", "web"]
    for job in load_manifest(companion)["jobs"]:
        assert "web_search" not in (job.get("toolsets") or [])
