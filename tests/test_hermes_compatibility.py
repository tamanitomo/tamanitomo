"""Isolation guards always run; real-Hermes integration is an explicit opt-in."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tools import check_hermes_compatibility as compatibility


def test_probe_environment_drops_real_credentials_and_profile_overrides(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-reach-the-probe")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "must-not-reach-the-probe")
    monkeypatch.setenv("HERMES_HOME", "/a-real-profile")
    monkeypatch.setenv("HERMES_PROFILE", "a-real-person")
    monkeypatch.setenv("PYTHONPATH", "/unrelated-python-code")
    env = compatibility.isolated_environment(tmp_path, tmp_path / "checkout")
    assert "OPENAI_API_KEY" not in env
    assert "TELEGRAM_BOT_TOKEN" not in env
    assert "HERMES_PROFILE" not in env
    assert env["HERMES_HOME"].startswith(str(tmp_path))
    assert env["HERMES_CONFIG"].startswith(str(tmp_path))
    assert "/unrelated-python-code" not in env["PYTHONPATH"]


def test_probe_guard_blocks_network_and_writes_outside_scratch(tmp_path):
    scratch = tmp_path / "isolated"
    scratch.mkdir()
    (scratch / "guard").mkdir()
    (scratch / "guard/sitecustomize.py").write_text(
        compatibility.GUARD, encoding="utf-8"
    )
    outside = tmp_path / "original.txt"
    outside.write_text("unchanged", encoding="utf-8")
    program = (
        "import pathlib,socket\n"
        "try: socket.create_connection(('127.0.0.1', 9))\n"
        "except PermissionError: pass\n"
        "else: raise AssertionError('network allowed')\n"
        f"try: pathlib.Path({str(outside)!r}).write_text('changed')\n"
        "except PermissionError: pass\n"
        "else: raise AssertionError('external write allowed')\n"
    )
    subprocess.run(
        [sys.executable, "-c", program],
        check=True,
        env=compatibility.isolated_environment(scratch, tmp_path / "checkout"),
        cwd=scratch,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert outside.read_text() == "unchanged"
    assert (scratch / "network-attempted").is_file()


def test_probe_guard_reads_the_kit_when_hermes_is_checked_out_inside_it(tmp_path):
    # CI checks Hermes out inside this repository, so the folder around the checkout
    # is the kit itself; an ordinary install keeps it inside ~/.hermes, beside real
    # profile data. The base interpreter is used because a virtualenv inside the
    # repository would count as the runtime and hide the difference.
    scratch = tmp_path / "isolated"
    (scratch / "guard").mkdir(parents=True)
    (scratch / "guard/sitecustomize.py").write_text(
        compatibility.GUARD, encoding="utf-8"
    )
    profile = tmp_path / "hermes"
    (profile / "hermes-agent").mkdir(parents=True)
    (profile / "config.yaml").write_text("model: real\n", encoding="utf-8")
    manifest = compatibility.ROOT / "kit/templates/cron/manifest.json"
    read_kit = f"import pathlib\npathlib.Path({str(manifest)!r}).read_text()\n"
    profile_hidden = (
        f"try: pathlib.Path({str(profile / 'config.yaml')!r}).read_text()\n"
        "except PermissionError: pass\n"
        "else: raise AssertionError('real profile data readable')\n"
    )
    interpreter = getattr(sys, "_base_executable", None) or sys.executable
    for checkout, program in (
        (compatibility.ROOT / ".hermes-compat", read_kit),
        (profile / "hermes-agent", read_kit + profile_hidden),
    ):
        result = subprocess.run(
            [interpreter, "-c", program],
            env=compatibility.isolated_environment(scratch, checkout),
            cwd=scratch,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, result.stderr


def test_reviewed_revision_required_before_runtime_is_started(tmp_path, monkeypatch):
    monkeypatch.setattr(
        compatibility, "revision", lambda _: "different-upstream-commit"
    )
    with pytest.raises(RuntimeError, match="not the reviewed revision"):
        compatibility.main(["--hermes-root", str(tmp_path), "--python", sys.executable])


def test_actual_hermes_plugin_routing_and_gateway_hooks(tmp_path):
    checkout = os.environ.get("TAMANITOMO_TEST_HERMES_ROOT")
    interpreter = os.environ.get("TAMANITOMO_TEST_HERMES_PYTHON")
    if not checkout or not interpreter:
        pytest.skip(
            "Set TAMANITOMO_TEST_HERMES_ROOT and TAMANITOMO_TEST_HERMES_PYTHON for the isolated real-Hermes check"
        )
    report = tmp_path / "hermes-compatibility.json"
    result = subprocess.run(
        [
            sys.executable,
            str(Path(compatibility.__file__)),
            "--hermes-root",
            checkout,
            "--python",
            interpreter,
            "--report",
            str(report),
        ],
        text=True,
        capture_output=True,
        timeout=100,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    evidence = json.loads(report.read_text())
    assert evidence["status"] == "passed"
    assert evidence["hermes_revision"] == compatibility.SUPPORTED_REVISION
    assert evidence["model_calls"] == evidence["messages_sent"] == 0
    assert "generated_gateway_continuity_hook" in evidence["checks"]
    assert "native_no_agent_maintenance" in evidence["checks"]


def test_ci_checks_the_same_reviewed_hermes_revision():
    workflow = (
        compatibility.ROOT / ".github/workflows/hermes-compatibility.yml"
    ).read_text()
    assert f"ref: {compatibility.SUPPORTED_REVISION}" in workflow
    assert "tools/check_hermes_compatibility.py" in workflow
