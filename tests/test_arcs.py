"""Storylines: the parts of her life that take weeks."""

import datetime as dt
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "kit/scripts"))

import companion_arcs as arcs  # noqa: E402
import companion_config as cc  # noqa: E402
import companion_story as story  # noqa: E402

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 20, 12, tzinfo=UTC)


def day(n):
    return NOW + dt.timedelta(days=n)


@pytest.fixture
def companion(tmp_path):
    c = cc.Companion(
        agent="Nova",
        human="Robin",
        hermes_root=tmp_path / "hermes",
        vault=tmp_path / "vault",
        timezone="UTC",
        soul_in_vault=False,
    )
    c.home.mkdir(parents=True)
    c.life.mkdir(parents=True)
    return c


def begin(c, title="Learning the wheel", when=NOW, weeks=4):
    out = arcs.start(
        c, title, "A six-week beginners' pottery course.", "learning", weeks, now=when
    )
    return out["entry"]["id"]


class TestAStoryline:
    def test_starts_moves_and_ends(self, companion):
        ident = begin(companion)
        arcs.beat(companion, ident, "First class: everything collapsed.", now=day(1))
        arcs.end(
            companion, ident, "resolved", "Brought home a lopsided bowl.", now=day(30)
        )
        (done,) = arcs.arcs(companion)
        assert [b["text"] for b in done["beats"]] == [
            "First class: everything collapsed."
        ]
        assert done["ended"]["outcome"] == "resolved"
        assert arcs.active(companion) == []

    def test_one_step_a_day(self, companion):
        ident = begin(companion)
        assert arcs.beat(companion, ident, "Bought clay.", now=day(1))["written"]
        again = arcs.beat(companion, ident, "And glaze.", now=day(1))
        assert not again["written"] and "already moved today" in again["reason"]

    def test_two_at_once_at_most(self, companion):
        begin(companion, "Learning the wheel")
        begin(companion, "The boiler saga")
        third = arcs.start(companion, "A new job", "Shifts at the bookshop.", now=NOW)
        assert (
            not third["written"]
            and "end one before starting another" in third["reason"]
        )

    def test_what_cannot_be(self, companion):
        with pytest.raises(ValueError, match="weeks"):
            arcs.start(companion, "Forever", "x", "other", 52, now=NOW)
        with pytest.raises(ValueError, match="kind"):
            arcs.start(companion, "Odd", "x", "saga", 4, now=NOW)
        with pytest.raises(ValueError, match="no storyline 'arc-nope'"):
            arcs.beat(companion, "arc-nope", "x", now=NOW)


class TestThePace:
    def test_nothing_running_invites_one(self, companion):
        assert "Nothing in your life is running over weeks" in arcs.render(
            companion, NOW
        )

    def test_a_still_storyline_is_nudged(self, companion):
        ident = begin(companion)
        arcs.beat(companion, ident, "First class.", now=day(1))
        text = arcs.render(companion, day(6))
        assert "Last step (2026-10-21): First class." in text
        assert "Nothing has moved for 5 days" in text

    def test_one_that_has_run_its_course_is_asked_to_end(self, companion):
        begin(companion, weeks=2)
        assert "It has run its course" in arcs.render(companion, day(15))

    def test_her_runs_and_her_chats_both_carry_it(self, companion):
        ident = begin(companion)
        assert ident in story.scheduled(companion)
        parts, _ = story.chat_parts(companion, 4000)
        assert any(ident in text for _, text in parts)

    def test_story_surfaces_use_the_callers_clock(self, companion):
        begin(companion, weeks=2)
        scheduled = story.scheduled(companion, now=day(15))
        parts, _ = story.chat_parts(companion, 4000, now=day(15))
        chat = "\n".join(text for _, text in parts)

        assert "week 3 of about 2" in scheduled
        assert "It has run its course" in scheduled
        assert "week 3 of about 2" in chat
        assert "It has run its course" in chat
