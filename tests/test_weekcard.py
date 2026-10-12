"""Her week as numbers, from her own records."""

import datetime as dt
import json

import pytest

import companion_config as cc
import companion_weekcard as weekcard

NOW = dt.datetime(2026, 10, 12, 18, 0, tzinfo=dt.timezone.utc)


@pytest.fixture
def companion(tmp_path):
    c = cc.Companion(agent="Nova", human="Alex", hermes_root=tmp_path / "home", vault=tmp_path / "vault", timezone="UTC")
    (c.life / "episodes").mkdir(parents=True)
    return c


def day(c, date, *states):
    rows = [json.dumps({"state": s}) for s in states]
    (c.life / "episodes" / f"{date}.jsonl").write_text("\n".join(rows) + "\n", encoding="utf-8")


def test_a_week_at_home_says_so(companion):
    day(companion, "2026-10-11",
        {"started_at": "2026-10-11T08:00:00+00:00", "location": "home, kitchen", "place": "home"},
        {"started_at": "2026-10-11T12:00:00+00:00", "location": "home, studio", "place": "home"})
    d = weekcard.card(companion, NOW)
    assert d["share_out"] == 0 and d["places_visited"] == [] and d["people_seen"] == []
    text = weekcard.render(companion, NOW)
    assert "home most of the week" in text and "you saw nobody" in text
    assert "not a quota" in text


def test_outings_places_and_people_are_counted(companion):
    day(companion, "2026-10-11",
        {"started_at": "2026-10-11T08:00:00+00:00", "location": "home, kitchen", "place": "home"},
        {"started_at": "2026-10-11T10:00:00+00:00", "location": "the pool", "place": "ymca", "with": ["priya"]},
        {"started_at": "2026-10-11T13:00:00+00:00", "location": "home", "place": "home"})
    d = weekcard.card(companion, NOW)
    assert d["places_visited"] == ["ymca"] and d["people_seen"] == ["priya"]
    assert d["hours_out"] == 3.0


def test_sleep_is_not_counted(companion):
    day(companion, "2026-10-11",
        {"started_at": "2026-10-11T00:00:00+00:00", "location": "home", "asleep": True},
        {"started_at": "2026-10-11T08:00:00+00:00", "location": "home"})
    assert weekcard.card(companion, NOW)["activities"] == 1


def test_the_weekly_reflection_reads_it_and_the_command_exists():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    assert "{{WEEKCARD_CMD}}" in (root / "kit/templates/cron/weekly.md.tmpl").read_text()
    assert "kit/scripts/companion_weekcard.py" in json.loads((root / "release-files.json").read_text())
