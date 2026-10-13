"""The check-in runs once per conversation, after it settles, and is handed it."""

import datetime as dt
import sqlite3

import pytest

import companion_checkin as checkin
import companion_config as cc
import companion_loops as loops

UTC = dt.timezone.utc
NOON = dt.datetime(2026, 10, 20, 12, tzinfo=UTC)


def minutes(n):
    return NOON + dt.timedelta(minutes=n)


@pytest.fixture
def companion(tmp_path):
    c = cc.Companion(
        agent="Nova",
        human="Robin",
        hermes_root=tmp_path / "home",
        vault=tmp_path / "vault",
        timezone="UTC",
        soul_in_vault=False,
    )
    c.home.mkdir(parents=True)
    c.life.mkdir(parents=True)
    db = sqlite3.connect(c.home / "state.db")
    db.executescript(
        "CREATE TABLE sessions(id TEXT, source TEXT, profile_name TEXT);"
        "CREATE TABLE messages(id INTEGER, session_id TEXT, role TEXT, content TEXT,"
        " timestamp REAL, active INTEGER, compacted INTEGER, _compressed_summary INTEGER);"
    )
    db.execute("INSERT INTO sessions VALUES ('chat','telegram','')")
    db.execute("INSERT INTO sessions VALUES ('job','cron','')")
    db.commit()
    db.close()
    return c


def say(c, n, role, text, at, session="chat"):
    db = sqlite3.connect(c.home / "state.db")
    db.execute(
        "INSERT INTO messages VALUES(?,?,?,?,?,1,0,0)",
        (n, session, role, text, at.timestamp()),
    )
    db.commit()
    db.close()


def test_a_conversation_wakes_the_check_in_once_after_it_settles(companion):
    idle = checkin.fingerprint(companion, minutes(0))
    # Hermes ends a chat session after every reply: three replies, three flags.
    for n in (1, 6, 11):
        checkin.flag(companion, minutes(n), platform="telegram")
        assert checkin.fingerprint(companion, minutes(n + 5)) == idle
    settled = checkin.fingerprint(companion, minutes(31))
    assert settled != idle
    assert checkin.fingerprint(companion, minutes(41)) == settled
    # Clearing does not change the bytes, so it costs no second run.
    checkin.clear(companion, minutes(43))
    assert checkin.read(companion)["pending"] == 0
    assert checkin.fingerprint(companion, minutes(51)) == settled
    # The next conversation wakes it again, once it too has settled.
    checkin.flag(companion, minutes(120), platform="telegram")
    assert checkin.fingerprint(companion, minutes(125)) == settled
    assert checkin.fingerprint(companion, minutes(141)) != settled


def test_the_pre_read_holds_only_the_new_conversation_and_open_threads(companion):
    say(companion, 1, "user", "Old news from yesterday", NOON - dt.timedelta(hours=20))
    checkin.flag(companion, NOON - dt.timedelta(hours=19), platform="telegram")
    checkin.fingerprint(companion, NOON - dt.timedelta(hours=18))
    checkin.clear(companion, NOON - dt.timedelta(hours=18))

    say(companion, 2, "user", "My sister Bee is visiting on Friday", minutes(1))
    say(companion, 3, "assistant", "Oh, I'd love to hear how that goes.", minutes(2))
    say(companion, 4, "user", "run the pulse checklist", minutes(3), session="job")
    loops.add(
        companion,
        {"id": "bee-visit", "title": "Bee's visit", "gentle_use": "ask after Friday"},
        minutes(0),
    )
    checkin.flag(companion, minutes(2), platform="telegram")
    text = checkin.preread(companion, minutes(30))
    assert "My sister Bee is visiting on Friday" in text
    assert "I'd love to hear" in text
    assert "Old news" not in text
    assert "pulse checklist" not in text  # scheduled runs are never the conversation
    assert "bee-visit: Bee's visit" in text
    assert "closet" not in text.lower() and "laundry" not in text.lower()


def test_nothing_new_says_so_and_an_unreadable_store_keeps_it_pending(companion):
    text = checkin.preread(companion, NOON)
    assert "has said nothing since" in text
    (companion.home / "state.db").unlink()
    (companion.home / "state.db").write_bytes(b"not a database")
    text = checkin.preread(companion, NOON)
    assert "could not be read" in text and "do not clear" in text


def test_repair_rewrites_the_kit_shims_of_an_existing_job_and_nothing_else(companion):
    import json
    import pathlib

    from kit.cli import scaffold

    root = pathlib.Path(__file__).resolve().parents[1]
    specs = json.loads((root / "kit/templates/cron/manifest.json").read_text())["jobs"]
    spec = next(s for s in specs if s["key"] == "checkin")
    scripts = companion.home / "scripts"
    scripts.mkdir()
    old = "runpy.run_module('companion_preread',run_name=\"__main__\")\n"
    (scripts / "companion-checkin-preread.py").write_text(old)
    (scripts / "mine.py").write_text("print('mine')\n")
    job = {
        "script": "companion-checkin-preread.py",
        "monitor_script": "companion-checkin-fingerprint.py",
    }
    assert scaffold.refresh_shims(companion, spec, job) == [
        "companion-checkin-preread.py",
        "companion-checkin-fingerprint.py",
    ]
    assert "companion_checkin" in (scripts / "companion-checkin-preread.py").read_text()
    assert scaffold.refresh_shims(companion, spec, {"script": "mine.py"}) == []
    assert (scripts / "mine.py").read_text() == "print('mine')\n"
