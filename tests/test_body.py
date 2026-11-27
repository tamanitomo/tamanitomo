"""Their sleep, from a wearable (companion_body, the "sleep" sense): what a fresh ambient/body.json says, how the
dispatcher uses it (a lie-in holds her messages; being up in the night's last hours lets a good morning go; a 2 am
wake never does), the line in her context, and that nothing changes when the sense is off or the device has gone
quiet.
"""

import datetime as dt
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "kit" / "scripts")]

import companion_body as body  # noqa: E402
import companion_config as cc  # noqa: E402
import companion_dispatch as dispatch  # noqa: E402
import companion_outbox as outbox  # noqa: E402

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
    c.sensors = ["sleep"]
    c.save()
    return c


def write(c, checked, asleep, since=None, slept=None, source="watch"):
    folder = c.soul_dir / "ambient"
    folder.mkdir(parents=True, exist_ok=True)
    row = {"checked_at": checked.isoformat(), "asleep": asleep, "source": source}
    if since:
        row["since"] = since.isoformat()
    if slept:
        row["slept_minutes"] = slept
    (folder / "body.json").write_text(json.dumps(row))


SEQ = iter(range(1000))


def entry(c, now, priority="normal"):
    """A fresh message each time (the outbox merges an identical one into the first)."""
    body = f"morning, sleepyhead ({next(SEQ)})"
    return outbox.queue(c, {"kind": "text", "body": body, "reason": "test",
                            "priority": priority, "ttl_hours": 6}, now)["entry"]  # fmt: skip


def test_fresh_word_is_read_and_stale_or_odd_is_not(companion):
    now = at(13)
    write(companion, now - dt.timedelta(minutes=5), True, since=at(12, 10))
    assert body.asleep(companion, now) is True
    write(companion, now - dt.timedelta(minutes=45), True, since=at(12, 10))
    assert body.asleep(companion, now) is None  # a flat watch is not a sleeping human
    write(companion, now + dt.timedelta(hours=1), True)
    assert body.read(companion, now) == {}  # from the future
    (companion.soul_dir / "ambient" / "body.json").write_text(
        '{"asleep": "maybe", "checked_at": "now"}'
    )
    assert body.read(companion, now) == {}
    write(companion, now, False, since=at(7, 12), slept=400)
    companion.sensors = []
    assert body.read(companion, now) == {}  # the sense off: nothing is read


def test_her_context_line(companion):
    write(companion, at(23, 55, day=8), True, since=at(23, 40, day=8))
    line, data = body.render(companion, at(23, 58, day=8))
    assert (
        line.startswith("Robin is asleep (by his watch, since 23:40)")
        and "until he wakes" in line
    )
    assert data["asleep"] is True
    write(companion, at(7, 30), False, since=at(7, 12), slept=400)
    line, data = body.render(companion, at(7, 30))
    assert (
        line == "Robin is up, awake since 07:12 after 6 h 40 m of sleep (by his watch)."
    )
    write(companion, at(11, 30), False, since=at(7, 12), slept=400)
    assert (
        body.render(companion, at(11, 30))[0] == ""
    )  # by late morning, waking is not news


def test_up_for_the_day_is_a_morning_not_a_two_am_wake(companion):
    write(companion, at(6, 5), False, since=at(6, 0))
    assert not body.up_for_the_day(companion, at(6, 5))  # five minutes is not up
    write(companion, at(6, 20), False, since=at(6, 0))
    assert body.up_for_the_day(
        companion, at(6, 20)
    )  # within the night's last three hours
    write(companion, at(2, 30), False, since=at(2, 10))
    assert not body.up_for_the_day(companion, at(2, 30))
    write(companion, at(9, 30), False, since=at(9, 0))
    assert body.up_for_the_day(companion, at(9, 30))  # after quiet hours


def test_a_lie_in_holds_her_messages_and_waking_lets_them_go(companion):
    now = at(9, 30)  # past quiet hours, still asleep
    write(companion, now - dt.timedelta(minutes=3), True, since=at(0, 40))
    v = dispatch.verdict(companion, entry(companion, now), now)
    assert v["action"] == "hold" and "Robin is asleep, by the wearable" in v["reason"]
    assert (
        dispatch.verdict(companion, entry(companion, now, "high"), now)["action"]
        == "send"
    )
    write(companion, at(9, 50), False, since=at(9, 45))
    assert (
        dispatch.verdict(companion, entry(companion, at(9, 50)), at(9, 50))["action"]
        == "send"
    )


def test_up_early_lets_a_good_morning_through_quiet_hours(companion):
    now = at(6, 40)  # quiet hours end at 08:00
    e = entry(companion, now)
    assert (
        dispatch.verdict(companion, e, now)["action"] == "hold"
    )  # nothing says he is up
    write(companion, now, False, since=at(6, 20), slept=410)
    assert dispatch.verdict(companion, e, now)["action"] == "send"
    write(companion, at(2, 40), False, since=at(2, 20))
    assert (
        dispatch.verdict(companion, entry(companion, at(2, 40)), at(2, 40))["action"]
        == "hold"
    )


def test_a_silent_device_changes_nothing(companion):
    now = at(13)
    write(companion, now - dt.timedelta(hours=2), True, since=at(10))
    assert dispatch.verdict(companion, entry(companion, now), now)["action"] == "send"
    companion.sensors = []
    write(companion, now, True, since=at(12))
    assert dispatch.verdict(companion, entry(companion, now), now)["action"] == "send"


def test_the_sense_is_known_and_has_its_own_context_section(companion):
    import companion_context as cx
    import companion_sensors as sensors

    assert "sleep" in sensors.REGISTRY and sensors.REGISTRY["sleep"]["fn"] == "sleep"
    write(companion, at(23, 55, day=8), True, since=at(23, 40, day=8))
    assert "asleep" in sensors.sleep(companion, at(23, 58, day=8))[0]
    sensors.run_one(
        companion, "sleep", at(23, 58, day=8)
    )  # the senses job writes ambient/sleep.md too
    out = cx.build(
        companion,
        {"extra": {"user_message": "hey", "platform": "telegram"}},
        now=at(23, 58, day=8),
    )
    assert "[Their sleep] Robin is asleep (by his watch, since 23:40)." in out
    assert (
        out.count("Robin is asleep") == 1
    )  # its own section, never repeated in the ambient block
    companion.sensors = []
    companion.save()
    out = cx.build(
        companion,
        {"extra": {"user_message": "hey", "platform": "telegram"}},
        now=at(23, 58, day=8),
    )
    assert "[Their sleep]" not in out
