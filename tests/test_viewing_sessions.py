"""Shared sessions use explicit participation and conversation evidence, without live accounts."""

import datetime as dt
import json
import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "kit/scripts"))

import companion_config as cc  # noqa: E402
import companion_context as context  # noqa: E402
import companion_notes as notes  # noqa: E402
import companion_sensors as sensors  # noqa: E402
import companion_viewing as viewing  # noqa: E402

NOW = dt.datetime(2026, 10, 11, 20, tzinfo=dt.timezone.utc)


@pytest.fixture
def companion(tmp_path, monkeypatch):
    c = cc.Companion(
        agent="Nova",
        human="Robin",
        timezone="UTC",
        soul_in_vault=False,
        hermes_root=tmp_path / "hermes",
        vault=tmp_path / "vault",
    )
    c.home.mkdir(parents=True)
    c.life.mkdir(parents=True)
    c.save()

    def no_network(*args, **kwargs):
        pytest.fail("a manual shared session must not contact a media server")

    monkeypatch.setattr(viewing, "_get", no_network)
    return c


def test_manual_session_reports_only_explicit_progress_and_expires(companion):
    started = viewing.together(companion, "Arrival", now=NOW, comments="quiet")
    ident = started["session_id"]
    assert started["written"] and started["entry"]["mode"] == "manual"
    viewing.report(
        companion,
        "We paused after the opening",
        "I paused it at 12 minutes",
        now=NOW,
        position_min=12,
    )
    later = NOW + dt.timedelta(hours=1)
    text, facts = viewing.sense(companion, later)
    assert "Quiet company" in text
    assert "12 minutes" in text and "60 minutes" not in text
    assert "Manual agreement, not observed playback" in text
    assert "Conversation evidence: I paused it at 12 minutes" in text
    assert facts["source"] == "manual" and facts["playing"] == []
    assert viewing.snapshot(companion, later)["sessions"][0]["id"] == ident
    assert viewing.seen(companion) == []
    expired = NOW + dt.timedelta(hours=3)
    assert viewing.active(companion, expired) == []
    ended_context = viewing.session_context(companion, expired)
    assert "expired" in ended_context
    assert "this does not mean the film finished" in ended_context
    assert viewing.session_context(companion, expired + dt.timedelta(hours=25)) == ""
    assert (
        viewing.snapshot(companion, expired)["recent_sessions"][0]["state"] == "expired"
    )


@pytest.mark.parametrize(
    "bad",
    [
        {"title": 123},
        {"title": None},
        {"mode": {"manual": True}},
        {"comments": ["quiet"]},
        {"evidence": True},
        {"evidence": None},
    ],
)
def test_invalid_json_field_types_do_not_create_a_session(companion, bad):
    arguments = {"title": "Arrival", **json.loads(json.dumps(bad))}
    with pytest.raises(ValueError, match="must be text"):
        viewing.together(companion, now=NOW, **arguments)
    assert viewing.agreements(companion) == []


def test_pause_resume_and_end_preserve_session_and_prevent_overlap(companion):
    first = viewing.together(companion, "Severance", now=NOW)
    ident = first["session_id"]
    assert viewing.pause(companion, NOW + dt.timedelta(minutes=5))["state"] == "paused"
    assert "participation is paused" in viewing.session_context(
        companion, NOW + dt.timedelta(minutes=6)
    )
    assert viewing.pause(companion, NOW + dt.timedelta(minutes=6))["written"] is False
    duplicate = viewing.together(
        companion, "Another film", now=NOW + dt.timedelta(minutes=7)
    )
    assert duplicate["written"] is False and duplicate["session_id"] == ident
    assert (
        viewing.resume(companion, NOW + dt.timedelta(minutes=10))["state"] == "active"
    )
    assert viewing.stop(companion, NOW + dt.timedelta(minutes=15), ident) == {
        "stopped": ["Severance"]
    }
    assert viewing.stop(companion, NOW + dt.timedelta(minutes=16), ident) == {
        "stopped": []
    }
    assert viewing.active(companion, NOW + dt.timedelta(minutes=16)) == []
    with pytest.raises(ValueError, match="no live"):
        viewing.resume(companion, NOW + dt.timedelta(minutes=17), ident)
    assert viewing.together(
        companion, "Another film", now=NOW + dt.timedelta(minutes=18)
    )["written"]


def test_fingerprint_changes_once_per_event_and_expiry_not_every_tick(companion):
    before = viewing.fingerprint(companion, NOW)
    viewing.together(companion, "Arrival", now=NOW)
    started = viewing.fingerprint(companion, NOW)
    assert started != before
    assert viewing.fingerprint(companion, NOW + dt.timedelta(minutes=1)) == started
    viewing.pause(companion, NOW + dt.timedelta(minutes=2))
    paused = viewing.fingerprint(companion, NOW + dt.timedelta(minutes=2))
    assert paused != started
    assert viewing.fingerprint(companion, NOW + dt.timedelta(minutes=3)) == paused
    viewing.resume(companion, NOW + dt.timedelta(minutes=4))
    resumed = viewing.fingerprint(companion, NOW + dt.timedelta(minutes=4))
    assert resumed != paused
    viewing.report(
        companion,
        "We reached the first scene",
        "Starting now",
        now=NOW + dt.timedelta(minutes=5),
    )
    reported = viewing.fingerprint(companion, NOW + dt.timedelta(minutes=5))
    assert reported != resumed
    assert viewing.fingerprint(companion, NOW + dt.timedelta(minutes=6)) == reported
    expired = viewing.fingerprint(companion, NOW + dt.timedelta(hours=3))
    assert expired != reported
    assert viewing.fingerprint(companion, NOW + dt.timedelta(hours=4)) == expired


def server_session(companion, monkeypatch):
    monkeypatch.setattr(viewing, "configured", lambda c: True)
    return viewing.together(companion, "Arrival", now=NOW, mode="server")


def test_manual_end_and_pause_do_not_receive_completion_grace(companion, monkeypatch):
    server_session(companion, monkeypatch)
    item = {"title": "Arrival"}
    viewing.pause(companion, NOW + dt.timedelta(minutes=10))
    viewing.resume(companion, NOW + dt.timedelta(minutes=30))
    viewing.stop(companion, NOW + dt.timedelta(minutes=45))
    sessions = viewing.agreements(companion)
    assert viewing._covered(item, NOW + dt.timedelta(minutes=9), sessions)
    assert not viewing._covered(item, NOW + dt.timedelta(minutes=10), sessions)
    assert not viewing._covered(item, NOW + dt.timedelta(minutes=20), sessions)
    assert viewing._covered(item, NOW + dt.timedelta(minutes=35), sessions)
    assert not viewing._covered(item, NOW + dt.timedelta(minutes=45), sessions)
    assert not viewing._covered(item, NOW + dt.timedelta(minutes=65), sessions)


def test_only_natural_unpaused_expiry_receives_grace(companion, monkeypatch):
    server_session(companion, monkeypatch)
    at = NOW + dt.timedelta(hours=3, minutes=20)
    assert viewing._covered({"title": "Arrival"}, at, viewing.agreements(companion))
    viewing.pause(companion, NOW + dt.timedelta(hours=2))
    assert not viewing._covered({"title": "Arrival"}, at, viewing.agreements(companion))


def test_manual_agreement_never_labels_server_history_as_observed_together(companion):
    viewing.together(companion, "Arrival", now=NOW)
    assert not viewing._covered(
        {"title": "Arrival"},
        NOW + dt.timedelta(minutes=5),
        viewing.agreements(companion),
    )


@pytest.mark.parametrize(
    "title,item,expected",
    [
        ("千と千尋の神隠し", {"title": "千と千尋の神隠し"}, True),
        ("Amélie", {"title": "Ame\u0301lie"}, True),
        ("Paddington", {"title": "Paddington 2"}, False),
        ("Paddington 2", {"title": "Paddington"}, False),
        ("Arrival (2016)", {"title": "Arrival", "year": 2016}, True),
        ("Arrival (2016)", {"title": "Arrival", "year": 1996}, False),
    ],
)
def test_title_identity_handles_unicode_without_confusing_sequels(
    title, item, expected
):
    assert viewing.matches(title, item) is expected



def test_legacy_sessions_still_end_without_grace(companion):
    path = viewing.path_for(companion)
    path.write_text(
        "\n".join(
            json.dumps(row)
            for row in [
                {
                    "id": "old",
                    "kind": "together",
                    "title": "Arrival",
                    "from": NOW.isoformat(),
                    "until": (NOW + dt.timedelta(hours=3)).isoformat(),
                },
                {
                    "id": "old",
                    "kind": "together_end",
                    "at": (NOW + dt.timedelta(minutes=10)).isoformat(),
                },
            ]
        )
        + "\n"
    )
    (session,) = viewing.agreements(companion)
    assert session["mode"] == "server" and session["comments"] == "occasional"
    assert not viewing._covered(
        {"title": "Arrival"}, NOW + dt.timedelta(minutes=20), [session]
    )


def test_personal_memory_is_linked_evidenced_and_retryable(companion, monkeypatch):
    ident = viewing.together(companion, "Arrival", now=NOW)["session_id"]
    real_add = notes.add_moment

    def unavailable(*args):
        raise OSError("simulated interrupted memory write")

    monkeypatch.setattr(notes, "add_moment", unavailable)
    with pytest.raises(OSError):
        viewing.moment(
            companion,
            "Our circle joke",
            'Robin said "draw another circle"',
            now=NOW,
            kind="joke",
        )
    assert len(viewing.moments(companion, ident)) == 1
    monkeypatch.setattr(notes, "add_moment", real_add)
    repaired = viewing.moment(
        companion,
        "Our circle joke",
        'Robin said "draw another circle"',
        now=NOW + dt.timedelta(minutes=1),
        kind="joke",
    )
    assert repaired["written"] is False and repaired["relationship"]["written"] is True
    assert len(notes.moments(companion)) == 1
    (memory,) = notes.moments(companion)
    assert ident in memory["evidence"] and "draw another circle" in memory["evidence"]
    assert "Our circle joke" in viewing.session_context(
        companion, NOW + dt.timedelta(minutes=1)
    )
    viewing.stop(companion, NOW + dt.timedelta(minutes=2))
    viewing.moment(
        companion,
        "That ending stayed with us",
        'Robin said "I am still thinking about the ending"',
        now=NOW + dt.timedelta(minutes=3),
        session_id=ident,
    )
    assert len(notes.moments(companion)) == 2
    aftermath = viewing.session_context(
        companion, NOW + dt.timedelta(minutes=4), limit=2000
    )
    assert "Session ended" in aftermath and "That ending stayed with us" in aftermath
    assert "optional, never a required message" in aftermath


def test_evidence_required_without_creating_a_memory(companion):
    viewing.together(companion, "Arrival", now=NOW)
    with pytest.raises(ValueError, match="evidence"):
        viewing.moment(companion, "An invented reaction", "", now=NOW)
    with pytest.raises(ValueError, match="evidence"):
        viewing.report(companion, "An invented scene", "", now=NOW)
    assert viewing.moments(companion) == [] and notes.moments(companion) == []


def test_retired_relationship_moment_is_not_revived_by_session_context(companion):
    viewing.together(companion, "Arrival", now=NOW)
    result = viewing.moment(
        companion,
        "Our circle joke",
        'Robin said "draw another circle"',
        now=NOW,
        kind="joke",
    )
    notes.retire_moment(
        companion,
        result["entry"]["relationship_id"],
        "Please stop that joke",
        NOW + dt.timedelta(minutes=1),
    )
    assert "Our circle joke" not in viewing.session_context(
        companion, NOW + dt.timedelta(minutes=2), limit=2000
    )
    assert len(viewing.moments(companion)) == 1  # the historical record is retained


def cached_viewing(companion):
    paths = [
        companion.soul_dir / "ambient/viewing.md",
        companion.home / "state/viewing-refreshed",
    ]
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("You are watching this together (agreed at 20:00).")
    return paths


def test_session_mutations_invalidate_only_successful_changed_context(
    companion, monkeypatch
):
    paths = cached_viewing(companion)
    viewing.together(companion, "Arrival", now=NOW)
    assert not any(path.exists() for path in paths)
    cached_viewing(companion)
    assert viewing.together(companion, "Arrival", now=NOW)["written"] is False
    assert all(path.exists() for path in paths)

    viewing.pause(companion, NOW + dt.timedelta(minutes=1))
    assert not any(path.exists() for path in paths)
    cached_viewing(companion)
    assert viewing.pause(companion, NOW + dt.timedelta(minutes=2))["written"] is False
    assert all(path.exists() for path in paths)
    viewing.resume(companion, NOW + dt.timedelta(minutes=3))
    assert not any(path.exists() for path in paths)

    cached_viewing(companion)
    real_append = viewing.slf._append

    def failed_write(*args, **kwargs):
        raise OSError("simulated interrupted write")

    monkeypatch.setattr(viewing.slf, "_append", failed_write)
    with pytest.raises(OSError):
        viewing.report(
            companion,
            "At the opening",
            "I just started",
            now=NOW + dt.timedelta(minutes=4),
        )
    assert all(path.exists() for path in paths)
    monkeypatch.setattr(viewing.slf, "_append", real_append)
    viewing.report(
        companion, "At the opening", "I just started", now=NOW + dt.timedelta(minutes=4)
    )
    assert not any(path.exists() for path in paths)
    cached_viewing(companion)
    assert (
        viewing.report(
            companion,
            "At the opening",
            "I just started",
            now=NOW + dt.timedelta(minutes=4),
        )["written"]
        is False
    )
    assert all(path.exists() for path in paths)
    viewing.stop(companion, NOW + dt.timedelta(minutes=5))
    assert not any(path.exists() for path in paths)
    cached_viewing(companion)
    assert viewing.stop(companion, NOW + dt.timedelta(minutes=6)) == {"stopped": []}
    assert all(path.exists() for path in paths)


def test_ending_does_not_leave_a_contradictory_cached_together_claim(companion):
    now = dt.datetime.now(dt.timezone.utc)
    companion.sensors = ["viewing"]
    viewing.together(companion, "Arrival", now=now - dt.timedelta(minutes=5))
    cached_viewing(companion)
    viewing.stop(companion, now - dt.timedelta(minutes=1))
    built = context.build(companion)
    assert "Session ended" in built
    assert "You are watching this together" not in built


def test_natural_expiry_discards_old_cache_but_keeps_new_observed_playback(companion):
    now = dt.datetime.now(dt.timezone.utc)
    companion.sensors = ["viewing"]
    started = now - dt.timedelta(hours=4)
    viewing.together(companion, "Arrival", now=started)
    cache, _ = cached_viewing(companion)
    during = (started + dt.timedelta(hours=2)).timestamp()
    os.utime(cache, (during, during))
    built = context.build(companion)
    assert "Session expired" in built
    assert "You are watching this together" not in built

    # A later sensor report is valid evidence again; expiry must not hide all
    # viewing context forever just because an old session remains in history.
    cache.write_text("Robin is watching a different film, recorded after our session.")
    after = (now - dt.timedelta(minutes=1)).timestamp()
    os.utime(cache, (after, after))
    built = context.build(companion)
    assert "recorded after our session" in built


@pytest.mark.parametrize(
    "mode,paused", [("manual", False), ("manual", True), ("server", True)]
)
def test_chat_does_not_poll_media_for_manual_or_paused_participation(
    companion, monkeypatch, mode, paused
):
    now = dt.datetime.now(dt.timezone.utc)
    companion.sensors = ["viewing"]
    monkeypatch.setattr(viewing, "configured", lambda c: True)
    viewing.together(companion, "Arrival", now=now - dt.timedelta(minutes=5), mode=mode)
    if paused:
        viewing.pause(companion, now - dt.timedelta(minutes=1))

    def no_poll(*args, **kwargs):
        pytest.fail(
            "Manual or paused participation must not trigger media polling from chat"
        )

    monkeypatch.setattr(sensors, "run_one", no_poll)
    built = context.build(companion)
    assert "[Time together]" in built
    assert "Arrival" in built
    assert not (companion.home / "state/viewing-refreshed").exists()


def test_cli_manual_lifecycle_returns_json_without_a_server(companion):
    def command(*args):
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "kit/scripts/companion_viewing.py"),
                "--home",
                str(companion.home),
                *args,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)

    ident = command("start", "--title", "Arrival", "--comments", "quiet")["session_id"]
    assert command("pause")["state"] == "paused"
    assert command("resume")["state"] == "active"
    command(
        "report",
        "--text",
        "At the opening",
        "--evidence",
        "I just started it",
        "--position-min",
        "0",
    )
    assert command("show")["sessions"][0]["id"] == ident
    command("end")
    assert command("show")["sessions"] == []
