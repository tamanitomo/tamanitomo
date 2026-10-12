"""Combined continuity acceptance with synthetic evidence and no live provider."""

import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import urllib.error

import pytest

from tools import check_continuity as continuity


def test_six_day_scenario_preserves_real_work_and_fictional_life(tmp_path):
    output = tmp_path / "evidence"
    report = continuity.run_acceptance(output)
    assert report["passed"] is True
    assert len(report["checks"]) == 10
    assert report["deterministic_model_calls"] == 0
    assert len(report["snapshots"]) == 5
    checks = {row["check"]: row for row in report["checks"]}
    assert (
        checks["ended explanation still exempts historical hours"]["evidence"][
            "expected_hours"
        ]
        == 82
    )
    work = next(
        row for row in report["tool_evidence"] if row["action"] == "local calculation"
    )
    assert work["exit_code"] == 0 and "20.0 mm" in work["stdout"]
    assert report["saved_artifacts"][work["artifact"]] == work["sha256"]
    restarted = checks["restart preserves completed action exactly once"]["evidence"]
    assert restarted["completed"] == ["rain-calibration"]
    assert restarted["artifact_sha256"] == work["sha256"]
    final = report["snapshots"][-1]
    assert "mesh screen" in final["context"]
    assert "PRIVATE STRANGER" not in final["context"]
    assert "copper-pencil moth" in final["context"]
    assert json.loads((output / "report.json").read_text())["passed"]
    assert "auth.json" not in " ".join(report["saved_artifacts"])


def test_mocked_transport_recovery_does_not_repeat_completed_work(tmp_path):
    routes = []

    def transport(route):
        routes.append(route["provider"])
        if len(routes) == 1:
            raise urllib.error.HTTPError(
                "https://synthetic.invalid", 429, "Busy", {}, None
            )
        return {"content": "Recovered via configured second route", "usage": None}

    report = continuity.run_acceptance(tmp_path / "evidence", transport=transport)
    assert routes == ["synthetic-primary", "synthetic-fallback"]
    assert (
        sum(row["action"] == "local calculation" for row in report["tool_evidence"])
        == 1
    )
    recovered = next(
        row
        for row in report["tool_evidence"]
        if row["action"] == "simulated provider recovery"
    )
    assert recovered["usage"] == {"input": None, "output": None}


def test_frontier_process_cannot_inherit_live_profile_or_credentials(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-inherit")
    monkeypatch.setenv("HERMES_PROFILE", "real-profile")
    monkeypatch.setenv("TAMANITOMO_HOME", "/real/private/profile")
    snapshot = {
        "case": "probe",
        "prompt": "Synthetic",
        "context": "Only invented data",
        "readouts": {},
        "rubric": [],
    }

    def process(command, **kwargs):
        assert kwargs["env"]["HOME"] == str(tmp_path)
        assert kwargs["env"]["HERMES_HOME"] == str(tmp_path / "hermes")
        assert "OPENAI_API_KEY" not in kwargs["env"]
        assert "HERMES_PROFILE" not in kwargs["env"]
        assert "TAMANITOMO_HOME" not in kwargs["env"]
        assert kwargs["timeout"] <= 120
        request = json.loads(kwargs["input"])
        assert request["provider"] == "chosen-provider"
        assert request["model"] == "chosen-model"
        assert request["snapshot"] == snapshot
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {"completed": True, "usage": {"input": 121, "output": 40}}
            ),
        )

    result = continuity.frontier_turn(
        snapshot,
        folder=tmp_path,
        runtime_python="/synthetic/python",
        runtime_source="/synthetic/runtime",
        provider="chosen-provider",
        model="chosen-model",
        timeout=900,
        run=process,
    )
    assert result["usage"] == {"input": 121, "output": 40}


def test_frontier_unavailable_stops_and_removes_only_temporary_auth(
    tmp_path, monkeypatch
):
    original = tmp_path / "credentials.json"
    original.write_text('{"access_token":"synthetic-secret-value"}')
    seen = []

    def unavailable(snapshot, **kwargs):
        temporary = kwargs["folder"] / "hermes/auth.json"
        assert temporary.read_bytes() == original.read_bytes()
        assert temporary != original
        seen.append(temporary)
        return {
            "case": snapshot["case"],
            "completed": False,
            "error": "Provider unavailable (synthetic)",
            "usage": {"input": None, "output": None},
        }

    monkeypatch.setattr(continuity, "frontier_turn", unavailable)
    output = tmp_path / "evidence"
    report = continuity.run_acceptance(
        output,
        frontier=True,
        runtime_python="python",
        runtime_source="runtime",
        provider="explicit-provider",
        model="explicit-model",
        auth_file=original,
    )
    assert len(seen) == 1
    assert not seen[0].exists()
    assert original.read_text() == '{"access_token":"synthetic-secret-value"}'
    assert report["frontier"]["turns"][0]["usage"]["input"] is None
    assert "synthetic-secret-value" not in (output / "report.json").read_text()
    assert report["passed"] is True  # Clearly separate from frontier availability.
    assert report["frontier"]["turns"][0]["completed"] is False


def test_frontier_timeout_keeps_unknown_usage_and_does_not_retry(tmp_path, monkeypatch):
    auth = tmp_path / "credentials.json"
    auth.write_text("{}")
    calls = []

    def timeout(*args, **kwargs):
        calls.append(kwargs)
        raise subprocess.TimeoutExpired("synthetic", 120)

    monkeypatch.setattr(continuity, "frontier_turn", timeout)
    report = continuity.run_acceptance(
        tmp_path / "evidence",
        frontier=True,
        runtime_python="python",
        runtime_source="runtime",
        provider="explicit-provider",
        model="explicit-model",
        auth_file=auth,
    )
    assert len(calls) == 1
    assert report["frontier"]["turns"][0]["usage"] == {"input": None, "output": None}
    assert "120-second" in report["frontier"]["turns"][0]["error"]


@pytest.mark.parametrize("turns", [0, 6, -1])
def test_dialogue_turn_limit_is_enforced_before_writes(tmp_path, turns):
    with pytest.raises(ValueError, match="one and five"):
        continuity.run_acceptance(tmp_path / "evidence", max_turns=turns)
    assert not (tmp_path / "evidence").exists()


def test_live_mode_requires_explicit_credentials_and_runtime(tmp_path):
    with pytest.raises(ValueError, match="explicit"):
        continuity.run_acceptance(tmp_path / "evidence", frontier=True)
    assert not (tmp_path / "evidence").exists()


@pytest.mark.parametrize("exception", ["RuntimeError", "SystemExit"])
def test_actual_child_redacts_auth_and_bearer_values_from_provider_failure(
    tmp_path, exception
):
    runtime = tmp_path / "runtime"
    package = runtime / "hermes_cli"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "env_loader.py").write_text(
        "def load_hermes_dotenv(*args, **kwargs): return []\n"
    )
    (package / "_early_recovery.py").write_text(
        "def restore_interrupted_pull(): return False\n"
    )
    (package / "runtime_provider.py").write_text(
        "def resolve_runtime_provider(**kwargs):\n"
        "    print('Diagnostic: Bearer temporary-secret; saved synthetic-auth-token')\n"
        f"    raise {exception}('Provider unavailable: Bearer transient-secret; saved synthetic-auth-token')\n"
    )
    (runtime / "run_agent.py").write_text("class AIAgent: pass\n")
    home = tmp_path / "isolated"
    (home / "hermes").mkdir(parents=True)
    (home / "hermes/auth.json").write_text('{"access_token":"synthetic-auth-token"}')
    result = continuity.frontier_turn(
        {"case": "failure"},
        folder=home,
        runtime_python=sys.executable,
        runtime_source=runtime,
        provider="synthetic",
        model="synthetic",
    )
    assert result["completed"] is False
    assert f"{exception}: Provider unavailable" in result["error"]
    assert "transient-secret" not in result["error"]
    assert "synthetic-auth-token" not in result["error"]
    assert result["stage"] == "provider-resolution"
    assert result["request_started"] is False
    assert "synthetic-auth-token" not in json.dumps(result)
    assert "temporary-secret" not in json.dumps(result)
    assert result["usage"] == {"input": None, "output": None}


@pytest.mark.parametrize("operation", ["write", "rename", "subprocess", "private-read"])
def test_guard_blocks_installed_bootstrap_side_effects_before_import(
    tmp_path, operation
):
    runtime = tmp_path / "runtime"
    package = runtime / "hermes_cli"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    launcher = runtime / "launcher"
    launcher.write_text("original installed launcher")
    private = runtime / ".env"
    private.write_text("private sentinel")
    home = tmp_path / "isolated"
    home.mkdir()
    candidate = home / "replacement"
    candidate.write_text("replacement")
    operations = {
        "write": f"Path({str(launcher)!r}).write_text('modified')",
        "rename": f"Path({str(candidate)!r}).replace({str(launcher)!r})",
        "subprocess": "subprocess.run(['unavailable-command'])",
        "private-read": f"Path({str(private)!r}).read_text()",
    }
    (package / "env_loader.py").write_text(
        "from pathlib import Path\nimport subprocess\n"
        + operations[operation]
        + "\nraise AssertionError('The isolation guard was bypassed')\n"
    )
    result = continuity.frontier_turn(
        {"case": "bootstrap-isolation"},
        folder=home,
        runtime_python=sys.executable,
        runtime_source=runtime,
        provider="synthetic",
        model="synthetic",
    )
    assert result["completed"] is False
    assert "PermissionError" in result["error"]
    assert result["stage"] == "bootstrap"
    assert result["request_started"] is False
    assert launcher.read_text() == "original installed launcher"
    assert candidate.read_text() == "replacement"
    assert "private sentinel" not in json.dumps(result)


@pytest.mark.skipif(not hasattr(os, "fchmod"), reason="fchmod is Unix-only")
@pytest.mark.parametrize("target", ["scratch", "external", "symlink", "hardlink"])
def test_guard_checks_actual_file_behind_mutating_descriptor(tmp_path, target):
    home = tmp_path / "isolated"
    home.mkdir()
    external = tmp_path / "external"
    external.write_text("external sentinel")
    external.chmod(0o600)
    local = home / "temporary-auth"
    if target == "symlink":
        local.symlink_to(external)
    elif target == "hardlink":
        os.link(external, local)
    else:
        local.write_text("synthetic scratch auth")
        local.chmod(0o600)
    selected = external if target == "external" else local
    # Open before the guard so the external test reaches the fd-specific check.
    script = (
        f"import os\nfd=os.open({str(selected)!r},os.O_RDONLY)\n"
        + continuity.FRONTIER_GUARD
        + "\ntry:\n    os.fchmod(fd,0o640)\n    print('allowed')\n"
        "except PermissionError:\n    print('blocked')\n"
        "finally:\n    os.close(fd)\n"
    )
    env = continuity.isolated_env(home)
    env["PYTHONPATH"] = str(tmp_path / "runtime")
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        cwd=home,
        text=True,
        capture_output=True,
        check=True,
        timeout=10,
    )
    assert result.stdout.strip() == ("allowed" if target == "scratch" else "blocked")
    assert external.stat().st_mode & 0o777 == 0o600
    assert external.read_text() == "external sentinel"
    if target == "scratch":
        assert local.stat().st_mode & 0o777 == 0o640
