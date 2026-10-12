"""Familiarity survives distance; useful shared memories survive a large archive."""

import datetime as dt
import json

import pytest

import companion_config as cc
import companion_feelings as feelings
import companion_intimacy as intimacy
import companion_notes as notes


@pytest.fixture
def companion(tmp_path):
    c = cc.Companion(
        agent="Nova",
        human="Alex",
        hermes_root=tmp_path / "home",
        vault=tmp_path / "vault",
        timezone="UTC",
        boundary="next-door",
    )
    c.home.mkdir(parents=True)
    c.life.mkdir(parents=True)
    return c


NOW = dt.datetime(2026, 10, 12, 12, tzinfo=dt.timezone.utc)


@pytest.mark.parametrize("boundary", ["next-door", "best-friend"])
def test_twenty_months_apart_preserves_familiarity_without_forcing_friendship(
    companion, boundary
):
    companion.boundary = boundary
    ledger = companion.life / "meters.json"
    ledger.write_text(
        json.dumps(
            {
                "version": 1,
                "days": {"2025-02-12": {"closeness": 80}},
                "contact": {},
            }
        )
    )
    original = ledger.read_bytes()
    state = intimacy.compute(companion, NOW)
    assert state["points"] == 0
    assert state["stage_name"] == state["stage_badge"] == "Distant"
    assert state["established"]
    text = intimacy.render(companion, state)
    assert "shared history" in text
    assert "new acquaintances" not in text and "just met" not in text.lower()
    assert "at most once a day" in text
    assert not state["can_flirt"] and not state["can_intimate"]
    assert ledger.read_bytes() == original


def test_new_companion_really_is_just_met(companion):
    state = intimacy.compute(companion, NOW)
    assert state["stage_name"] == "Just Met"
    assert not state["established"]
    assert "You have just met Alex" in intimacy.render(companion, state)


def test_old_level_record_retains_familiarity_before_meter_migration(companion):
    path = companion.home / intimacy.LEVELS_FILE
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"seen": 0, "highest": 3}))
    state = intimacy.compute(companion, NOW)
    assert state["stage_name"] == "Distant"
    regained = intimacy.level_event(
        companion, {**state, "stage": 1, "stage_name": "Friends"}
    )
    assert regained["from_name"] == "Distant"
    assert regained["kind"] == "regained"


def test_recent_joke_and_ritual_survive_many_old_milestones(companion):
    for day in range(1, 21):
        notes.add_moment(
            companion,
            {
                "moment": "milestone",
                "text": f"Old milestone {day}: " + "A remembered occasion. " * 8,
            },
            NOW - dt.timedelta(days=100 + day),
        )
    notes.add_moment(
        companion,
        {"moment": "joke", "text": "The detective is always the toaster."},
        NOW,
    )
    notes.add_moment(
        companion,
        {"moment": "ritual", "text": "Sunday tea and a detective episode."},
        NOW,
    )
    before = notes.moments_path(companion).read_bytes()
    text = notes.render_relationship(companion, 700)
    assert "always the toaster" in text and "Sunday tea" in text
    assert len(text) <= 700 and "+more" in text
    assert notes.moments_path(companion).read_bytes() == before


def test_topic_can_recall_an_old_moment_without_reviving_retired_ones(companion):
    old = notes.add_moment(
        companion,
        {"moment": "joke", "text": "The marmalade detective."},
        NOW - dt.timedelta(days=100),
    )
    notes.add_moment(companion, {"moment": "note", "text": "A recent walk."}, NOW)
    text = notes.render_relationship(companion, 200, query="Our marmalade detective")
    assert text.index("marmalade") < text.index("recent walk")
    notes.retire_moment(companion, old["entry"]["id"], "No longer welcome", NOW)
    assert "marmalade" not in notes.render_relationship(
        companion, 200, query="marmalade"
    )


def test_topic_flood_does_not_displace_nickname_and_matching_ritual(companion):
    notes.add_moment(
        companion, {"moment": "nickname", "text": "You call each other duck."}, NOW
    )
    notes.add_moment(
        companion,
        {"moment": "ritual", "text": "Sunday detective tea."},
        NOW - dt.timedelta(days=2),
    )
    notes.add_moment(companion, {"moment": "ritual", "text": "Friday films."}, NOW)
    for day in range(20):
        notes.add_moment(
            companion,
            {
                "moment": "milestone",
                "text": f"Detective milestone {day}: "
                + "The detective was discussed. " * 8,
            },
            NOW - dt.timedelta(days=day),
        )
    text = notes.render_relationship(companion, 650, query="the detective")
    assert "call each other duck" in text
    assert "Sunday detective tea" in text
    assert len(text) <= 650


@pytest.mark.parametrize("limit", [0, 1, 10, 39, 40, 80])
def test_relationship_view_respects_even_tiny_budgets(companion, limit):
    notes.add_moment(
        companion, {"moment": "note", "text": "A very long occasion. " * 20}, NOW
    )
    text = notes.render_relationship(companion, limit)
    assert len(text) <= limit
    assert not text or "+more" in text


def test_complete_small_memory_does_not_need_room_for_omission_notice(companion):
    notes.add_moment(companion, {"moment": "joke", "text": "Duck."}, NOW)
    full = notes.render_relationship(companion)
    assert notes.render_relationship(companion, len(full)) == full


def test_first_open_while_distant_retains_historical_level_for_regain(companion):
    (companion.life / "meters.json").write_text(
        json.dumps(
            {
                "version": 1,
                "days": {"2025-02-12": {"closeness": 80}},
                "contact": {},
            }
        )
    )
    distant = intimacy.compute(companion, NOW)
    assert intimacy.level_event(companion, distant) is None
    assert intimacy._read_levels(companion)["highest"] == 3
    event = intimacy.level_event(
        companion,
        {
            **distant,
            "stage": 1,
            "stage_name": "Friends",
            "stage_badge": "Friends",
        },
    )
    assert event["from_name"] == "Distant"
    assert event["kind"] == "regained"


def test_newly_reached_stage_is_still_announced_as_new_high(companion):
    intimacy._write_levels(companion, {"seen": 0, "highest": 0})
    (companion.life / "meters.json").write_text(
        json.dumps(
            {
                "version": 1,
                "days": {"2026-10-12": {"closeness": 30}},
                "contact": {},
            }
        )
    )
    event = intimacy.level_event(
        companion,
        {
            "stage": 1,
            "stage_name": "Friends",
            "stage_badge": "Friends",
            "established": True,
        },
    )
    assert event["kind"] == "new_high"
    assert event["from_name"] == "Just Met"


def boundary_ruptures(c):
    rows = []
    for n in range(2):
        rows.append(
            feelings.record(
                c,
                {
                    "kind": "rupture",
                    "topic": "intimacy_boundary_violation",
                    "text": f"Boundary incident {n}",
                    "evidence": f"Synthetic quote {n}",
                },
                NOW - dt.timedelta(days=2 - n),
            )["experience"]
        )
    return rows


def correct_ruptures(c, rows):
    for n, row in enumerate(rows):
        feelings.record(
            c,
            {
                "kind": "correction",
                "related": row["id"],
                "topic": row["topic"],
                "text": f"Incident {n} was recorded by mistake",
                "evidence": f"Synthetic correction {n}",
            },
            NOW,
        )


def test_corrected_boundary_records_never_create_a_permanent_lock(companion):
    rows = boundary_ruptures(companion)
    correct_ruptures(companion, rows)
    for record in (False, True):
        state = intimacy.compute(companion, NOW, record=record)
        assert state["violations_count"] == 0
        assert not state["permanent_friend"]
        assert not (companion.home / ".permanent-friend.json").exists()


def test_real_boundary_violations_are_enforced_on_read_persisted_only_by_maintenance(
    companion,
):
    rows = boundary_ruptures(companion)
    state = intimacy.compute(companion, NOW)
    assert state["violations_count"] == 2
    assert state["permanent_friend"] and not state["can_intimate"]
    path = companion.home / ".permanent-friend.json"
    assert not path.exists()
    intimacy.compute(companion, NOW, record=True)
    saved = json.loads(path.read_text())
    assert saved["violation_ids"] == [row["id"] for row in rows]
    assert saved["permanent_friend"]


def test_legacy_permanent_decision_without_evidence_is_not_silently_reversed(companion):
    path = companion.home / ".permanent-friend.json"
    path.write_text(json.dumps({"permanent_friend": True, "violations": 2}))
    original = path.read_bytes()
    correct_ruptures(companion, boundary_ruptures(companion))
    state = intimacy.compute(companion, NOW)
    assert state["violations_count"] == 0
    assert state["permanent_friend"]
    assert path.read_bytes() == original
