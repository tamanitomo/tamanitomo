"""Her needs: rest, company, fun and, once close, affection. Natural, not a game."""

import datetime as dt
import json
import pathlib
import sys
from unittest.mock import patch

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "kit/scripts"))

import companion_config as cc  # noqa: E402
import companion_needs as needs  # noqa: E402
import companion_presence as presence  # noqa: E402
import companion_sleep as sleep  # noqa: E402

UTC = dt.timezone.utc
# Needs began on 2026-10-11; these days come after it.
DAY = dt.datetime(2026, 10, 20, tzinfo=UTC)
ORDINARY = {"day": "2026-10-20", "kind": "ordinary", "roll": 10}


def at(hour, minute=0, day=0):
    return DAY + dt.timedelta(days=day, hours=hour, minutes=minute)


@pytest.fixture
def companion(tmp_path):
    c = cc.Companion(
        agent="Nova",
        human="Robin",
        hermes_root=tmp_path / "hermes",
        vault=tmp_path / "vault",
        timezone="UTC",
        boundary="next-door",
        quiet_start="23:00",
        quiet_end="07:00",
        soul_in_vault=False,
    )
    c.home.mkdir(parents=True)
    c.life.mkdir(parents=True)
    c.save()
    return c


def ordinary_luck():
    return patch.object(needs, "luck", return_value=dict(ORDINARY))


def usual_life():
    """You talked last night; two days ago she went out with friends."""
    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(
        patch.object(needs, "_talk_hours", return_value=[at(20, day=-1)])
    )
    stack.enter_context(
        patch.object(
            needs,
            "_presence_feeds",
            return_value=[(at(19, day=-2), "social"), (at(19, day=-2), "fun")],
        )
    )
    return stack


def night(c, start, end):
    sleep.path(c).write_text(
        json.dumps(
            {
                "from": start.isoformat(),
                "until": end.isoformat(),
                "hours": (end - start).total_seconds() / 3600,
            }
        )
    )


class TestEnergy:
    def test_a_full_night_and_a_long_day(self, companion):
        night(companion, at(23, day=-1), at(7))
        with ordinary_luck():
            morning = needs.compute(companion, at(8), stage=0)["needs"]["energy"]
            late = needs.compute(companion, at(23, 30), stage=0)["needs"]["energy"]
        assert morning["level"] == pytest.approx(0.955)
        assert not morning["low"]
        assert late["low"] and "up since 07:00" in late["why"]

    def test_a_short_night_starts_the_day_lower(self, companion):
        night(companion, at(2), at(7))
        with ordinary_luck():
            energy = needs.compute(companion, at(7, 30), stage=0)["needs"]["energy"]
        assert energy["level"] == pytest.approx(0.625 - 0.0225, abs=1e-3)
        assert energy["why"] == ["a short night (5 hours)"]

    def test_asleep_is_not_tired(self, companion):
        night(companion, at(23, day=-1), at(7))
        with ordinary_luck():
            state = needs.compute(companion, at(3), stage=0)
        assert state["asleep"] and state["needs"]["energy"]["level"] is None
        assert state["wants"] == []

    def test_a_rest_she_records_gives_some_back(self, companion):
        night(companion, at(23, day=-1), at(7))
        with (
            ordinary_luck(),
            patch.object(needs, "_presence_feeds", return_value=[(at(15), "energy")]),
        ):
            rested = needs.compute(companion, at(22), stage=0)["needs"]["energy"]
        assert rested["level"] == pytest.approx(1 - 0.045 * 15 + 0.3)

    def test_an_undeclared_night_is_still_a_night(self, companion):
        with ordinary_luck():
            early = needs.compute(companion, at(6), stage=0)["needs"]["energy"]
            late = needs.compute(companion, at(0, 30), stage=0)["needs"]["energy"]
        # Up at six, seven hours into the quiet hours: slept and woke early.
        assert early["level"] == pytest.approx(7 / 8)
        # Up at half past midnight: staying up, her day goes on.
        assert late["low"] and "up since 07:00" in late["why"]


class TestCompanyFunAffection:
    def test_life_as_usual_is_comfortable(self, companion):
        with ordinary_luck(), usual_life():
            state = needs.compute(companion, at(12), stage=2)
        assert state["needs"]["social"]["level"] > needs.COMFORTABLE
        assert state["wants"] == []

    def test_a_long_dry_spell_runs_low_and_says_why(self, companion):
        with ordinary_luck():
            state = needs.compute(companion, at(12), stage=2)
        assert state["needs"]["social"]["low"]
        assert state["needs"]["social"]["why"] == ["little company for 5 days"]
        assert set(state["wants"]) >= {"company", "some fun", "closeness"}

    def test_never_counted_from_before_needs_began(self, companion):
        first = dt.datetime(2026, 10, 12, 12, tzinfo=UTC)
        with ordinary_luck():
            state = needs.compute(companion, first, stage=2)
        assert state["wants"] == []

    def test_what_she_does_and_your_moments_fill_them(self, companion):
        with (
            ordinary_luck(),
            patch.object(needs, "_presence_feeds", return_value=[(at(10), "fun")]),
            patch.object(needs, "_moments", return_value=[(at(11), 1.0)]),
        ):
            state = needs.compute(companion, at(12), stage=2)["needs"]
        assert state["fun"]["level"] > needs.COMFORTABLE
        assert state["affection"]["level"] > needs.COMFORTABLE

    def test_bad_luck_can_bring_one_low(self, companion):
        unlucky = {
            **ORDINARY,
            "kind": "unlucky",
            "what": "plans fell through",
            "effect": {"fun": -0.35},
        }
        with ordinary_luck(), usual_life():
            usual = needs.compute(companion, at(12), stage=2)["needs"]["fun"]
        with patch.object(needs, "luck", return_value=unlucky), usual_life():
            state = needs.compute(companion, at(12), stage=2)["needs"]["fun"]
        assert state["level"] == pytest.approx(usual["level"] - 0.35, abs=1e-3)
        assert "plans fell through" in state["why"]


class TestWhichNeedsAndWhen:
    def test_they_unlock_with_closeness(self, companion):
        assert needs.unlocked(companion, 0) == ["energy"]
        assert needs.unlocked(companion, 1) == ["energy", "social", "fun"]
        assert needs.unlocked(companion, 2) == ["energy", "social", "fun", "affection"]

    def test_affection_belongs_to_a_romance(self, companion):
        companion.boundary = "best-friend"
        assert "affection" not in needs.unlocked(companion, 4)

    def test_progression_off_has_the_everyday_ones(self, companion):
        companion.relationship_progression = "off"
        assert needs.unlocked(companion, 0) == ["energy", "social", "fun"]


class TestLuck:
    def test_one_day_in_twenty_lucky_five_unlucky(self, companion):
        days = [dt.date(2026, 1, 1) + dt.timedelta(days=n) for n in range(4000)]
        kinds = [needs.luck(companion, day)["kind"] for day in days]
        assert 0.035 < kinds.count("lucky") / len(days) < 0.065
        assert 0.22 < kinds.count("unlucky") / len(days) < 0.28

    def test_the_same_day_always_rolls_the_same(self, companion):
        day = dt.date(2026, 10, 20)
        assert needs.luck(companion, day) == needs.luck(companion, day)

    def test_a_lucky_or_unlucky_day_is_noted_in_its_plan_once(self, companion):
        import companion_plan

        unlucky = {**ORDINARY, "kind": "unlucky", "what": "a lonely day", "roll": 4}
        night(companion, at(23, day=-1), at(7))
        with patch.object(needs, "luck", return_value=unlucky):
            assert needs.log_luck(companion, at(9)) is None  # no plan yet
            companion_plan.settle(companion, DAY.date(), "A slow Tuesday", now=at(8))
            needs.log_luck(companion, at(9))
            needs.log_luck(companion, at(10))
        notes = [
            row["change"]
            for row in companion_plan.read(companion, DAY.date())["history"]
            if row["change"].startswith("luck:")
        ]
        assert notes == ["luck: a lonely day (unlucky, rolled 4 of 20)"]

    def test_an_ordinary_day_writes_nothing(self, companion):
        night(companion, at(23, day=-1), at(7))
        with ordinary_luck():
            assert needs.log_luck(companion, at(9)) is None


class TestHerContext:
    def test_nothing_to_say_when_all_is_well(self, companion):
        night(companion, at(23, day=-1), at(7))
        with ordinary_luck(), usual_life():
            state = needs.compute(companion, at(12), stage=2)
        assert needs.render(companion, state) == ""

    def test_a_calling_need_in_her_terms_never_a_number(self, companion):
        with ordinary_luck():
            text = needs.render(companion, needs.compute(companion, at(12), stage=2))
        assert "you would like some company" in text
        assert "never as a demand" in text
        assert '"feeds"' in text
        assert "0." not in text and "%" not in text


class TestHerScheduledRuns:
    """The morning, pulse, autonomy and wind-down read the pre-read, not the chat
    hook, so needs and luck have to be there too."""

    UNLUCKY = {
        **ORDINARY,
        "kind": "unlucky",
        "roll": 4,
        "what": "a rough night",
        "effect": {"energy_start": -0.3},
    }

    def test_the_morning_knows_the_days_luck(self, companion):
        import companion_preread

        night(companion, at(23, day=-1), at(7))
        with patch.object(needs, "luck", return_value=self.UNLUCKY):
            text = companion_preread.preread(companion, at(7, 15))
        assert "[Your needs, yours rather than a score]" in text
        assert "Today's luck: a rough night" in text

    def test_meters_off_means_no_needs(self, companion):
        import companion_preread

        companion.bars = False
        night(companion, at(23, day=-1), at(7))
        with patch.object(needs, "luck", return_value=self.UNLUCKY):
            text = companion_preread.preread(companion, at(7, 15))
        assert "Your needs" not in text and "Today's luck" not in text


class TestFeedsInPresence:
    def setup(self, companion):
        presence.update_wardrobe(
            companion,
            [{"id": "jeans", "description": "blue jeans", "use": "day"}],
        )

    def state(self, **extra):
        return {
            "previous_id": None,
            "outfit": ["jeans"],
            "location": "a cafe downtown",
            "activity": "coffee with a friend",
            "mood": "bright",
            "care": [],
            "transition": "",
            "text": "Coffee with Mia.",
            **extra,
        }

    def test_she_says_what_an_hour_gave_her(self, companion):
        self.setup(companion)
        presence.update(companion, self.state(feeds=["social", "fun"]), at(10))
        assert presence.current(companion)["state"]["feeds"] == ["fun", "social"]
        found = needs._presence_feeds(companion, at(9), at(11))
        assert sorted(need for _, need in found) == ["fun", "social"]

    def test_only_rest_company_or_fun(self, companion):
        self.setup(companion)
        with pytest.raises(ValueError, match="feeds"):
            presence.update(companion, self.state(feeds=["affection"]), at(10))


def test_home_shows_needs_in_words_only():
    from tests.test_chat_dock import run_browser_contract

    run_browser_contract(r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('kit/app/static/feelings.js', 'utf8');
vm.runInThisContext(`
const esc=v=>String(v).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
${source.slice(source.indexOf('const NEED_WORDS'), source.indexOf('function feelingMeters'))}
globalThis.needsRow=needsRow;
`);
const calling = needsRow({has: ['energy', 'social', 'fun'], wants: ['rest', 'some fun'], asleep: false,
  luck: {kind: 'unlucky', what: 'a rough night'}, needs: {energy: {level: 0.2}}});
assert.ok(calling.includes('rest, some fun'));
assert.ok(!/\d/.test(calling.replace(/title="[^"]*"/, '')), 'no numbers on the row');
assert.ok(calling.includes('Today: a rough night.'));
assert.ok(needsRow({has: ['energy'], wants: [], asleep: false}).includes('Nothing pressing'));
assert.ok(needsRow({has: ['energy'], wants: [], asleep: true}).includes('Asleep'));
assert.equal(needsRow({has: []}), '');
assert.equal(needsRow(null), '');
""")
