"""Disposable multi-day self-development acceptance harness."""

import json

from tools import check_self_development as scenario


def test_multi_day_self_development_scenario(tmp_path):
    output = tmp_path / "evidence"
    report = scenario.run(output)
    assert report["passed"]
    assert report["deterministic"] == {
        "model_calls": 0,
        "messages_sent": 0,
        "external_actions": 0,
        "claim": "storage, restart, context, reflection and planning plumbing only",
    }
    assert len(report["checks"]) == 8
    assert [
        row["change"] for row in next(iter(report["current_state"]["history"].values()))
    ] == [
        "new",
        "unchanged",
        "nuance",
    ]
    assert (output / report["artifact"]["path"]).is_file()
    saved = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert saved["frontier"]["requested"] is False
    assert saved["deterministic"]["model_calls"] == 0


def test_frontier_requires_explicit_isolated_runtime_before_writing(tmp_path):
    try:
        scenario.run(tmp_path / "evidence", frontier=True)
    except ValueError as exc:
        assert "explicit" in str(exc)
    else:
        raise AssertionError("frontier run accepted implicit credentials/runtime")
    assert not (tmp_path / "evidence").exists()
