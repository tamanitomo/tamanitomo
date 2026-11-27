"""Their day in motion, from a wearable (companion_activity, the "activity" sense): what a fresh ambient/steps.json
says (steps so far today, against their usual by this hour when the device knows it), the line in her context, and
that nothing is said when the sense is off, the count is stale or from another day, or the file is malformed.
"""

import datetime as dt
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "kit" / "scripts")]

import companion_activity as activity  # noqa: E402
import companion_config as cc  # noqa: E402

UTC = dt.timezone.utc


def at(hour, minute=0, day=9):
    return dt.datetime(2026, 9, day, hour, minute, tzinfo=UTC)


@pytest.fixture
def companion(tmp_path):
    c = cc.Companion(agent="Nova", human="Robin", hermes_root=tmp_path / "hermes", vault=tmp_path / "vault",
                     timezone="UTC", boundary="next-door", outreach="free", outreach_per_day=5,
                     quiet_start="23:00", quiet_end="08:00", soul_in_vault=False)  # fmt: skip
    c.home.mkdir(parents=True)
    c.life.mkdir(parents=True)
    c.soul_dir.mkdir(parents=True, exist_ok=True)
    c.sensors = ["activity"]
    c.save()
    return c


def write(c, checked, steps, usual=None, source="watch", raw=None):
    folder = c.soul_dir / "ambient"
    folder.mkdir(parents=True, exist_ok=True)
    row = {"checked_at": checked.isoformat(), "steps": steps, "source": source}
    if usual is not None:
        row["usual_by_now"] = usual
    (folder / "steps.json").write_text(
        raw if raw is not None else json.dumps(row), encoding="utf-8"
    )


def test_a_count_without_a_usual(companion):
    write(companion, at(15, 10), 3_412)
    line, data = activity.render(companion, at(15, 20))
    assert line.startswith(
        "Robin has walked about 3,400 steps today by 15:10 (by his watch)."
    )
    assert "never a goal, a score or a lecture" in line
    assert data == {"steps": 3412, "usual_by_now": None}


@pytest.mark.parametrize(
    "steps, usual, day, words",
    [
        (
            9_800,
            5_200,
            "busy",
            "well over his usual of about 5,200 by this hour: a busy day on his feet",
        ),
        (
            1_100,
            4_000,
            "quiet",
            "well under his usual of about 4,000 by this hour: a quiet day so far",
        ),
        (4_600, 5_000, "usual", "about his usual for this time of day"),
        (
            300,
            900,
            "usual",
            "about his usual",
        ),  # an early, slow usual: "quiet" would mean nothing
    ],
)
def test_against_their_usual(companion, steps, usual, day, words):
    write(companion, at(15, 0), steps, usual)
    line, data = activity.render(companion, at(15, 5))
    assert words in line
    assert data["day"] == day


@pytest.mark.parametrize(
    "checked, now",
    [
        (at(14, 0), at(15, 0)),  # an hour old: not "today so far"
        (at(23, 50, day=8), at(0, 10)),  # yesterday's last count, ten minutes later
        (at(15, 30), at(15, 0)),  # from the future
    ],
)
def test_stale_or_another_day_says_nothing(companion, checked, now):
    write(companion, checked, 5_000, 4_000)
    assert activity.render(companion, now) == ("", {})


@pytest.mark.parametrize(
    "raw",
    ["not json", "[]", '{"checked_at": "soon", "steps": 10}', '{"checked_at": "2026-09-09T15:00:00+00:00"}',
     '{"checked_at": "2026-09-09T15:00:00+00:00", "steps": true}',
     '{"checked_at": "2026-09-09T15:00:00+00:00", "steps": -5}'],
)  # fmt: skip
def test_malformed_says_nothing(companion, raw):
    write(companion, at(15, 0), 0, raw=raw)
    assert activity.render(companion, at(15, 5)) == ("", {})


def test_sense_off_or_no_file_says_nothing(companion):
    assert activity.render(companion, at(15, 0)) == ("", {})
    write(companion, at(15, 0), 5_000)
    companion.sensors = []
    assert activity.render(companion, at(15, 5)) == ("", {})


def test_the_sense_is_known_and_has_its_own_context_section(companion):
    import companion_context as cx
    import companion_sensors as sensors

    assert (
        "activity" in sensors.REGISTRY
        and sensors.REGISTRY["activity"]["fn"] == "activity"
    )
    write(companion, at(15, 0), 9_800, 5_200)
    assert "busy day" in sensors.activity(companion, at(15, 5))[0]
    sensors.run_one(
        companion, "activity", at(15, 5)
    )  # the senses job writes activity.md and .json beside it
    assert (
        json.loads(
            (companion.soul_dir / "ambient" / "steps.json").read_text(encoding="utf-8")
        )["steps"]
        == 9_800
    )  # untouched
    out = cx.build(
        companion,
        {"extra": {"user_message": "hey", "platform": "telegram"}},
        now=at(15, 5),
    )
    assert (
        "[Their day in motion] Robin has walked about 9,800 steps today by 15:00 (by his watch)"
        in out
    )
    assert (
        out.count("Robin has walked") == 1
    )  # its own section, never repeated in the ambient block
    companion.sensors = []
    companion.save()
    out = cx.build(
        companion,
        {"extra": {"user_message": "hey", "platform": "telegram"}},
        now=at(15, 5),
    )
    assert "[Their day in motion]" not in out
