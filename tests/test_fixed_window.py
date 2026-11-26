"""A context budget fixed by choice stays fixed: repair resizes only an automatic one."""

import dataclasses
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "kit/scripts"))

import companion_config as cc  # noqa: E402
from kit.cli import doctor  # noqa: E402


def companion(tmp_path, mode):
    c = cc.Companion(
        agent="Nova",
        human="Robin",
        hermes_root=tmp_path / "h",
        vault=tmp_path / "v",
        context_mode=mode,
        context_tokens=272000,
    )
    c.home.mkdir(parents=True, exist_ok=True)
    (c.home / "config.yaml").write_text(
        "model:\n  default: big-model\n  context_length: 1000000\n", encoding="utf-8"
    )
    return c


def test_a_fixed_budget_is_noted_not_followed(tmp_path):
    detected, how, follow = doctor.window_drift(companion(tmp_path, "fixed"))
    assert detected == 1_000_000 and not follow


def test_an_automatic_budget_follows_the_model(tmp_path):
    assert doctor.window_drift(companion(tmp_path, "auto"))[2] is True


def test_no_drift_when_they_agree(tmp_path):
    c = dataclasses.replace(companion(tmp_path, "fixed"), context_tokens=1_000_000)
    assert doctor.window_drift(c) is None
