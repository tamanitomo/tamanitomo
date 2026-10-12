"""A record review repairs proven mistakes without erasing a companion's history."""

import datetime as dt
import json

import pytest

import companion_config as cc
import companion_feelings as feelings
import companion_intimacy as intimacy
import companion_relationship_review as reviews

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 12, 12, tzinfo=UTC)


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


def incident(c, ident, *, at=None, evidence=None):
    return feelings.record(
        c,
        {
            "id": ident,
            "kind": "rupture",
            "topic": "intimacy_boundary_violation",
            "text": f"Recorded incident {ident}",
            "evidence": evidence or f"Synthetic quote {ident}",
        },
        at or NOW - dt.timedelta(days=2),
    )["experience"]


def correct(c, ident, *, at=None):
    return feelings.record(
        c,
        {
            "id": "correct-" + ident,
            "kind": "correction",
            "related": ident,
            "topic": "intimacy_boundary_violation",
            "text": "The original classification was mistaken",
            "evidence": "Synthetic original conversation establishes this correction",
        },
        at or NOW,
    )["experience"]


def persisted(c):
    incident(c, "first")
    incident(c, "second", at=NOW - dt.timedelta(days=1))
    intimacy.compute(c, NOW - dt.timedelta(hours=1), record=True)
    return c.home / reviews.LOCK_FILE


def snapshot(c):
    return {
        str(p.relative_to(c.home.parent)): p.read_bytes()
        for p in c.home.parent.rglob("*")
        if p.is_file()
    }


def test_report_is_read_only_and_separates_configuration_from_choice(companion):
    before = snapshot(companion)
    report = reviews.report(companion, NOW)
    assert snapshot(companion) == before
    assert not report["configuration"]["explicit"]
    assert not report["restriction"]["present"]
    assert not report["stance"]["assessed"]
    assert not report["derived"]["intimacy_ready"]
    assert report["configuration"]["romantic_progression"]
    json.dumps(report)


def test_corrected_sources_require_explicit_review_preserve_history_and_settings(
    companion,
):
    lock = persisted(companion)
    lock_bytes = lock.read_bytes()
    correct(companion, "first")
    ledger = companion.life / "relationship-feelings.jsonl"
    ledger_bytes = ledger.read_bytes()
    before = snapshot(companion)
    report = reviews.report(companion, NOW)
    assert snapshot(companion) == before
    assert report["restriction"]["eligible"]
    assert report["restriction"]["effective"]
    assert {r["id"]: r["status"] for r in report["restriction"]["incidents"]} == {
        "first": "corrected",
        "second": "active",
    }
    result = reviews.review(
        companion,
        revision=report["revision"],
        reason="Original quote supports the recorded correction",
        now=NOW,
    )
    assert result["written"]
    assert result["report"]["restriction"]["status"] == "retired"
    assert not result["report"]["restriction"]["effective"]
    assert not intimacy.compute(companion, NOW)["permanent_friend"]
    assert lock.read_bytes() == lock_bytes
    assert ledger.read_bytes() == ledger_bytes
    assert not companion.explicit
    assert not result["report"]["derived"]["intimacy_ready"]
    assert result["review"]["incidents"][0]["corrections"][0]["id"] == "correct-first"
    before = snapshot(companion)
    reviews.report(companion, NOW)
    intimacy.compute(companion, NOW)
    assert snapshot(companion) == before


def test_repairs_and_elapsed_time_do_not_retire_real_restriction(companion):
    persisted(companion)
    for ident in ("first", "second"):
        feelings.record(
            companion,
            {
                "kind": "repair",
                "id": "repair-" + ident,
                "related": ident,
                "topic": "repair",
                "text": "A real repair",
                "evidence": "Synthetic apology",
                "strength": 1,
            },
            NOW,
        )
    report = reviews.report(companion, NOW + dt.timedelta(days=400))
    assert not report["restriction"]["eligible"]
    assert report["derived"]["active_violation_count"] == 2
    with pytest.raises(ValueError):
        reviews.review(
            companion,
            revision=report["revision"],
            reason="Time passed",
            now=NOW + dt.timedelta(days=400),
        )
    assert not (companion.life / reviews.REVIEWS_FILE).exists()


@pytest.mark.parametrize(
    "replacement",
    [
        {"permanent_friend": True, "violations": 2},
        {
            "permanent_friend": True,
            "violations": 2,
            "violation_ids": ["first", "missing"],
            "at": NOW.isoformat(),
        },
        {
            "permanent_friend": True,
            "violations": 2,
            "violation_ids": ["first", "first"],
            "at": NOW.isoformat(),
        },
        {
            "permanent_friend": True,
            "violations": 3,
            "violation_ids": ["first", "second"],
            "at": NOW.isoformat(),
        },
        "not JSON",
        [1],
        True,
        42,
        '"valid JSON string"',
    ],
)
def test_unknown_or_malformed_provenance_is_never_automatically_retired(
    companion, replacement
):
    path = persisted(companion)
    path.write_text(
        replacement if isinstance(replacement, str) else json.dumps(replacement)
    )
    correct(companion, "first")
    correct(companion, "second")
    original = path.read_bytes()
    report = reviews.report(companion, NOW)
    assert report["restriction"]["status"] == "inspection_required"
    assert not report["restriction"]["eligible"]
    assert report["restriction"]["effective"]
    assert intimacy.compute(companion, NOW)["permanent_friend"]
    with pytest.raises(ValueError):
        reviews.review(
            companion, revision=report["revision"], reason="Do not guess", now=NOW
        )
    assert path.read_bytes() == original


def test_stale_revision_cannot_review_changed_evidence(companion):
    persisted(companion)
    correct(companion, "first")
    report = reviews.report(companion, NOW)
    incident(companion, "third", at=NOW)
    with pytest.raises(reviews.StaleReviewError):
        reviews.review(
            companion, revision=report["revision"], reason="Old report", now=NOW
        )
    assert not (companion.life / reviews.REVIEWS_FILE).exists()
    assert not reviews.report(companion, NOW)["restriction"]["eligible"]


def retire(c):
    persisted(c)
    correct(c, "first")
    correct(c, "second")
    report = reviews.report(c, NOW)
    return reviews.review(
        c, revision=report["revision"], reason="Verified corrections", now=NOW
    )


def test_independent_incident_does_not_revive_corrected_sources_but_two_still_restrict(
    companion,
):
    retire(companion)
    feelings.record(
        companion,
        {
            "kind": "connection",
            "topic": "music",
            "text": "A shared song",
            "evidence": "Synthetic quote",
        },
        NOW,
    )
    assert not intimacy.compute(companion, NOW)["permanent_friend"]
    before = reviews.report(companion, NOW)
    incident(companion, "third", at=NOW)
    after = reviews.report(companion, NOW)
    assert after["revision"] != before["revision"]
    assert after["incident_revision"] != before["incident_revision"]
    assert after["source_revision"] == before["source_revision"]
    assert after["restriction"]["status"] == "retired"
    state = intimacy.compute(companion, NOW)
    assert not state["permanent_friend"]
    assert state["risk_level"] == "caution"
    incident(companion, "fourth", at=NOW)
    report = reviews.report(companion, NOW)
    assert not report["restriction"]["eligible"]
    assert report["restriction"]["status"] == "retired"
    assert not report["restriction"]["effective"]
    assert report["derived"]["active_violation_count"] == 2
    assert intimacy.compute(companion, NOW)["permanent_friend"]


def test_identical_evidence_revision_is_bound_to_the_profile(companion, tmp_path):
    persisted(companion)
    correct(companion, "first")
    other = cc.Companion(
        agent=companion.agent,
        human=companion.human,
        hermes_root=tmp_path / "other-home",
        vault=tmp_path / "other-vault",
        timezone=companion.timezone,
        boundary=companion.boundary,
    )
    other.home.mkdir(parents=True)
    other.life.mkdir(parents=True)
    persisted(other)
    correct(other, "first")
    report = reviews.report(companion, NOW)
    assert reviews.report(other, NOW)["revision"] != report["revision"]
    before = snapshot(other)
    with pytest.raises(reviews.StaleReviewError):
        reviews.review(
            other,
            revision=report["revision"],
            reason="A report from the other profile",
            now=NOW,
        )
    assert not (other.life / reviews.REVIEWS_FILE).exists()
    # Lock files can be created by an explicit write attempt; authored state cannot.
    assert {
        path: data for path, data in snapshot(other).items() if path in before
    } == before


@pytest.mark.parametrize("change", ["lock", "correction", "source"])
def test_review_cannot_apply_to_changed_lock_or_reappearing_source(companion, change):
    retire(companion)
    if change == "lock":
        path = companion.home / reviews.LOCK_FILE
        record = json.loads(path.read_text())
        record["at"] = (NOW + dt.timedelta(seconds=1)).isoformat()
        path.write_text(json.dumps(record))
    else:
        path = companion.life / "relationship-feelings.jsonl"
        rows = feelings.experiences(companion)
        if change == "correction":
            rows = [r for r in rows if r["id"] != "correct-first"]
        else:
            rows[0]["evidence"] = "Different source evidence"
        path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert intimacy.compute(companion, NOW + dt.timedelta(seconds=2))[
        "permanent_friend"
    ]
    assert (companion.life / reviews.REVIEWS_FILE).read_text()


def test_future_correction_and_future_review_cannot_change_the_past(companion):
    retire(companion)
    earlier = NOW - dt.timedelta(minutes=1)
    report = reviews.report(companion, earlier)
    assert report["restriction"]["effective"]
    assert not report["restriction"]["eligible"]
    assert intimacy.compute(companion, earlier)["permanent_friend"]


def test_duplicate_evidence_is_reported_without_reclassifying_incidents(companion):
    incident(companion, "first", evidence="Same original words")
    incident(companion, "second", evidence="Same original words")
    report = reviews.report(companion, NOW)
    assert report["duplicate_evidence_groups"] == [["first", "second"]]
    assert report["derived"]["active_violation_count"] == 2
    assert not report["restriction"]["eligible"]


@pytest.mark.parametrize("reason", ["", "   ", None, "x" * 1001])
def test_explicit_human_reason_is_required(companion, reason):
    persisted(companion)
    correct(companion, "first")
    report = reviews.report(companion, NOW)
    with pytest.raises(ValueError, match="reason"):
        reviews.review(companion, revision=report["revision"], reason=reason, now=NOW)
    assert not (companion.life / reviews.REVIEWS_FILE).exists()


def test_revocation_is_independent_of_corrected_relationship_restriction(companion):
    retire(companion)
    (companion.home / ".nsfw-revoked.json").write_text(
        json.dumps({"reason": "User choice"})
    )
    state = intimacy.compute(companion, NOW)
    assert not state["permanent_friend"] and state["nsfw_revoked"]
    report = reviews.report(companion, NOW)
    assert report["configuration"]["nsfw_revoked"]
    assert not report["derived"]["intimacy_ready"]


def test_malformed_experience_data_blocks_review_and_report_stays_read_only(companion):
    path = persisted(companion)
    correct(companion, "first")
    with (companion.life / "relationship-feelings.jsonl").open("a") as stream:
        stream.write(
            json.dumps(
                {"id": [], "kind": "rupture", "topic": [], "at": NOW.isoformat()}
            )
            + "\n"
        )
    before = snapshot(companion)
    report = reviews.report(companion, NOW)
    assert not report["restriction"]["eligible"]
    assert report["restriction"]["effective"]
    assert report["warnings"]
    assert snapshot(companion) == before
    assert path.exists()


def test_unverifiable_new_incident_cannot_be_ignored_to_retire_a_lock(companion):
    persisted(companion)
    correct(companion, "first")
    correct(companion, "second")
    new = incident(companion, "third", at=NOW)
    new["evidence"] = ""
    path = companion.life / "relationship-feelings.jsonl"
    rows = [new if r["id"] == "third" else r for r in feelings.experiences(companion)]
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    report = reviews.report(companion, NOW)
    assert report["restriction"]["effective"]
    assert not report["restriction"]["eligible"]
    assert report["restriction"]["status"] == "inspection_required"


def test_corrupt_audit_log_cannot_silently_keep_a_restriction_retired(companion):
    retire(companion)
    with (companion.life / reviews.REVIEWS_FILE).open("a") as stream:
        stream.write("not a review\n")
    before = snapshot(companion)
    report = reviews.report(companion, NOW)
    assert report["restriction"]["effective"]
    assert not report["restriction"]["eligible"]
    assert report["restriction"]["status"] == "inspection_required"
    assert snapshot(companion) == before


def next_restriction(c):
    retire(c)
    incident(c, "third", at=NOW)
    incident(c, "fourth", at=NOW)
    intimacy.compute(c, NOW, record=True)


def test_later_persisted_generation_needs_its_own_review_after_correction(companion):
    retire(companion)
    original = (companion.home / reviews.LOCK_FILE).read_bytes()
    old_reviews = (companion.life / reviews.REVIEWS_FILE).read_bytes()
    incident(companion, "third", at=NOW)
    incident(companion, "fourth", at=NOW)
    before = snapshot(companion)
    assert intimacy.compute(companion, NOW)["permanent_friend"]
    assert snapshot(companion) == before
    generations = companion.life / reviews.RESTRICTIONS_FILE
    assert not generations.exists()

    intimacy.compute(companion, NOW, record=True)
    recorded = generations.read_bytes()
    saved = json.loads(recorded)
    assert saved["violation_ids"] == ["third", "fourth"]
    assert (companion.home / reviews.LOCK_FILE).read_bytes() == original
    assert (companion.life / reviews.REVIEWS_FILE).read_bytes() == old_reviews
    intimacy.compute(companion, NOW, record=True)
    assert generations.read_bytes() == recorded

    correct(companion, "third")
    before = snapshot(companion)
    report = reviews.report(companion, NOW)
    assert snapshot(companion) == before
    assert report["restriction"]["source_ids"] == ["third", "fourth"]
    assert report["restriction"]["effective"] and report["restriction"]["eligible"]
    assert report["restriction_history"][0]["status"] == "retired"
    assert intimacy.compute(companion, NOW)["permanent_friend"]
    result = reviews.review(
        companion,
        revision=report["revision"],
        reason="The third incident was explicitly corrected",
        now=NOW,
    )
    assert [r["status"] for r in result["report"]["restriction_history"]] == [
        "retired",
        "retired",
    ]
    assert len(result["report"]["reviews"]) == 2
    assert not intimacy.compute(companion, NOW)["permanent_friend"]
    assert generations.read_bytes() == recorded
    assert (companion.home / reviews.LOCK_FILE).read_bytes() == original
    assert (companion.life / reviews.REVIEWS_FILE).read_bytes().startswith(old_reviews)


def test_uncovered_current_sources_persist_even_before_original_review(companion):
    persisted(companion)
    correct(companion, "first")
    incident(companion, "third", at=NOW)
    intimacy.compute(companion, NOW, record=True)
    saved = json.loads((companion.life / reviews.RESTRICTIONS_FILE).read_text())
    assert saved["violation_ids"] == ["second", "third"]
    correct(companion, "second")
    for expected in (["second", "third"], ["first", "second"]):
        report = reviews.report(companion, NOW)
        assert report["restriction"]["source_ids"] == expected
        assert report["restriction"]["effective"]
        reviews.review(
            companion,
            revision=report["revision"],
            reason="The source records contain explicit corrections",
            now=NOW,
        )
    assert not intimacy.compute(companion, NOW)["permanent_friend"]


def test_changed_older_correction_is_not_hidden_by_later_retirement(companion):
    next_restriction(companion)
    correct(companion, "third")
    correct(companion, "fourth")
    report = reviews.report(companion, NOW)
    reviews.review(
        companion, revision=report["revision"], reason="New sources corrected", now=NOW
    )
    assert not intimacy.compute(companion, NOW)["permanent_friend"]
    path = companion.life / "relationship-feelings.jsonl"
    rows = [r for r in feelings.experiences(companion) if r["id"] != "correct-first"]
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    report = reviews.report(companion, NOW)
    assert report["restriction"]["source_ids"] == ["first", "second"]
    assert report["restriction"]["effective"]
    assert report["restriction_history"][-1]["status"] == "retired"
    assert intimacy.compute(companion, NOW)["permanent_friend"]


@pytest.mark.parametrize("bad", ["not JSON", "[]", '{"kind":"unknown"}'])
def test_corrupt_generations_cannot_hide_a_saved_restriction(companion, bad):
    next_restriction(companion)
    correct(companion, "third")
    path = companion.life / reviews.RESTRICTIONS_FILE
    with path.open("a") as stream:
        stream.write(bad + "\n")
    before = snapshot(companion)
    report = reviews.report(companion, NOW)
    assert report["restriction"]["status"] == "inspection_required"
    assert report["restriction"]["effective"]
    assert not report["restriction"]["eligible"]
    assert intimacy.compute(companion, NOW)["permanent_friend"]
    assert snapshot(companion) == before


def test_missing_original_cannot_drop_a_later_saved_restriction(companion):
    next_restriction(companion)
    correct(companion, "third")
    (companion.home / reviews.LOCK_FILE).unlink()
    report = reviews.report(companion, NOW)
    assert report["restriction"]["effective"]
    assert not report["restriction"]["eligible"]
    assert intimacy.compute(companion, NOW)["permanent_friend"]


def test_duplicate_evidence_warning_does_not_silently_skip_persistence(companion):
    incident(companion, "first", evidence="Repeated words")
    incident(companion, "second", evidence="Repeated words")
    intimacy.compute(companion, NOW, record=True)
    assert (companion.home / reviews.LOCK_FILE).exists()
    correct(companion, "first")
    report = reviews.report(companion, NOW)
    assert report["duplicate_evidence_groups"]
    assert report["restriction"]["effective"]
    assert report["restriction"]["eligible"]
    assert intimacy.compute(companion, NOW)["permanent_friend"]
