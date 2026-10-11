"""The meters can't be bent by the settings around them.

The owner's rules (2026-10-10): pace and temperament are chosen when the
companion is created and kept; the window before she misses you stays between 12
and 96 hours; one time-away plan covers at most 14 days and is renewed by
explaining again; learned quiet hours are on unless switched off."""

import datetime as dt
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "kit/scripts"))

import companion_config as cc  # noqa: E402
import companion_feelings as feelings  # noqa: E402
from tests.support import AppFixture  # noqa: E402

NOW = dt.datetime(2026, 10, 12, 12, 0, tzinfo=dt.timezone.utc)


@pytest.fixture
def companion(tmp_path):
    c = cc.Companion(
        agent="Nova",
        human="Robin",
        hermes_root=tmp_path / "hermes",
        vault=tmp_path / "vault",
        timezone="UTC",
        soul_in_vault=False,
        context_mode="fixed",
    )
    c.home.mkdir(parents=True)
    c.life.mkdir(parents=True)
    c.save()
    return c


def plan(c, start, end, ident="trip", action="create", now=NOW):
    return feelings.record_absence(
        c,
        {
            "action": action,
            "id": ident,
            "label": "Away",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "evidence": "Robin said they would be away.",
            "source": "conversation:test/message:1",
            "revision": feelings.expected_absences(c, now)["revision"],
        },
        now,
    )


def days(n):
    return dt.timedelta(days=n)


class TestTemperament:
    def test_is_kept_once_chosen(self, companion):
        current = feelings.settings(companion)
        with pytest.raises(ValueError, match="can't be changed"):
            feelings.save_settings(
                companion,
                {**current["settings"], "personality": "expressive"},
                current["revision"],
            )
        assert feelings.settings(companion)["settings"]["personality"] == "steady"

    def test_other_feelings_settings_still_save(self, companion):
        current = feelings.settings(companion)
        saved = feelings.save_settings(
            companion,
            {**current["settings"], "connection_hours": 72},
            current["revision"],
        )
        assert saved["settings"]["connection_hours"] == 72

    def test_setup_records_the_chosen_one(self, companion):
        from kit.cli import scaffold

        report = []
        scaffold.record_temperament(companion, {"temperament": "guarded"}, report)
        assert feelings.settings(companion)["settings"]["personality"] == "guarded"
        assert report == []
        # Setting the companion up again keeps what was chosen.
        scaffold.record_temperament(companion, {"temperament": "expressive"}, report)
        assert feelings.settings(companion)["settings"]["personality"] == "guarded"

    def test_setup_suggests_one_from_the_personality(self, companion):
        from kit.cli import scaffold

        companion.persona = "shy"
        scaffold.record_temperament(companion, {}, [])
        assert feelings.settings(companion)["settings"]["personality"] == "guarded"
        assert feelings.temperament_for("romantic") == "expressive"
        assert feelings.temperament_for("unknown") == "steady"


class TestConnectionWindow:
    @pytest.mark.parametrize("hours", [6, 11, 97, 168])
    def test_is_kept_between_12_and_96_hours(self, companion, hours):
        current = feelings.settings(companion)
        with pytest.raises(ValueError, match="between 12 and 96"):
            feelings.save_settings(
                companion,
                {**current["settings"], "connection_hours": hours},
                current["revision"],
            )

    def test_an_older_setting_outside_it_is_read_at_the_nearest_bound(self, companion):
        path = companion.life / "feelings-settings.json"
        path.write_text('{"personality": "steady", "connection_hours": 168}\n')
        assert feelings.settings(companion)["settings"]["connection_hours"] == 96
        path.write_text('{"personality": "steady", "connection_hours": 6}\n')
        assert feelings.settings(companion)["settings"]["connection_hours"] == 12


class TestTimeAway:
    def test_one_plan_covers_at_most_14_days(self, companion):
        plan(companion, NOW + days(1), NOW + days(15))
        with pytest.raises(ValueError, match="at most 14 days"):
            plan(companion, NOW + days(20), NOW + days(35), ident="long")

    def test_explaining_a_long_past_absence_is_limited_too(self, companion):
        with pytest.raises(ValueError, match="at most 14 days"):
            plan(companion, NOW - days(60), NOW)

    def test_plans_back_to_back_in_advance_are_one_stretch(self, companion):
        plan(companion, NOW + days(1), NOW + days(11))
        with pytest.raises(ValueError, match="more than 14 days"):
            plan(companion, NOW + days(11), NOW + days(18), ident="more")
        # A separate trip, days apart, is its own plan.
        plan(companion, NOW + days(14), NOW + days(18), ident="later")

    def test_it_is_renewed_by_explaining_again_once_it_has_begun(self, companion):
        plan(companion, NOW, NOW + days(10))
        during = NOW + days(8)
        plan(companion, NOW + days(10), NOW + days(20), ident="more", now=during)
        state = feelings.expected_absences(companion, during)
        assert {row["id"] for row in state["absences"]} == {"trip", "more"}

    def test_an_edit_can_carry_it_14_days_from_the_edit(self, companion):
        plan(companion, NOW, NOW + days(10))
        during = NOW + days(9)
        plan(
            companion,
            NOW,
            during + days(14),
            action="edit",
            now=during,
        )
        with pytest.raises(ValueError, match="at most 14 days"):
            plan(companion, NOW, during + days(15), action="edit", now=during)


class SettingsApiTests(AppFixture):
    def test_pace_cannot_change_after_creation(self):
        r = self.client.post("/api/settings", json={"relationship_pace": "quick"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("can't be changed", r.json()["detail"])
        self.assertEqual(cc.load(self.c.home).relationship_pace, "natural")

    def test_an_older_page_sending_the_same_pace_still_saves(self):
        r = self.client.post(
            "/api/settings", json={"relationship_pace": "natural", "location": "Oslo"}
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(cc.load(self.c.home).location, "Oslo")

    def test_learned_quiet_hours_are_on_until_switched_off(self):
        self.assertTrue(self.client.get("/api/settings").json()["learn_rhythm"])
        r = self.client.post("/api/settings", json={"learn_rhythm": False})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["saved"], ["learn_rhythm"])
        self.assertFalse(feelings.settings(self.c)["settings"]["learn_rhythm"])
        self.assertFalse(self.client.get("/api/settings").json()["learn_rhythm"])

    def test_the_switch_saves_with_other_settings_and_only_if_they_do(self):
        r = self.client.post(
            "/api/settings", json={"learn_rhythm": False, "outreach_per_day": 9999}
        )
        self.assertEqual(r.status_code, 400)
        self.assertTrue(feelings.settings(self.c)["settings"]["learn_rhythm"])
        r = self.client.post(
            "/api/settings", json={"learn_rhythm": False, "location": "Oslo"}
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(sorted(r.json()["saved"]), ["learn_rhythm", "location"])
        self.assertFalse(feelings.settings(self.c)["settings"]["learn_rhythm"])

    def test_the_switch_must_be_true_or_false(self):
        r = self.client.post("/api/settings", json={"learn_rhythm": "no"})
        self.assertEqual(r.status_code, 400)

    def test_temperament_cannot_change_through_the_feelings_api(self):
        current = self.client.get("/api/feelings").json()
        r = self.client.put(
            "/api/feelings/settings",
            json={
                "settings": {**current["settings"], "personality": "guarded"},
                "revision": current["revision"],
            },
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("can't be changed", r.json()["detail"])


# ---- the daily record and the per-day caps ------------------------------------
#
# Recorded days must be in the past: the record never writes a day ahead of the
# real clock, so these tests use dates that have already happened.

import companion_meters as meters  # noqa: E402

PAST = dt.datetime(2026, 9, 1, 12, 0, tzinfo=dt.timezone.utc)
START = {"warmth": 0.5, "trust": 0.5, "hurt": 0.0, "irritation": 0.0, "closeness": 50}


def on(day):
    return PAST + days(day)


class TestDailyCaps:
    def test_each_meter_moves_at_most_its_cap_in_a_day(self, companion):
        meters.settle(companion, on(0), START, write=True)
        up = meters.settle(
            companion,
            on(1),
            {"warmth": 1, "trust": 1, "hurt": 1, "irritation": 1, "closeness": 120},
        )
        assert {k: v["value"] for k, v in up.items()} == {
            "warmth": 0.7,
            "trust": 0.6,
            "hurt": 0.3,
            "irritation": 0.3,
            "closeness": 56,
        }
        assert all(v["held"] for v in up.values())
        down = meters.settle(
            companion, on(1), {"warmth": 0, "trust": 0, "closeness": 0}
        )
        assert {k: v["value"] for k, v in down.items()} == {
            "warmth": 0.3,
            "trust": 0.4,
            "closeness": 44,
        }

    def test_an_ordinary_day_is_not_held_back(self, companion):
        meters.settle(companion, on(0), START, write=True)
        out = meters.settle(companion, on(1), {"warmth": 0.62, "closeness": 51.25})
        assert out["warmth"] == {**out["warmth"], "value": 0.62, "held": False}
        assert out["closeness"]["value"] == 51.25

    def test_pace_scales_closeness_gains_but_not_losses(self, companion):
        meters.settle(companion, on(0), START, write=True)
        quick = meters.settle(companion, on(1), {"closeness": 120}, pace=1.8)
        slow = meters.settle(companion, on(1), {"closeness": 120}, pace=0.6)
        falling = meters.settle(companion, on(1), {"closeness": 0}, pace=1.8)
        assert quick["closeness"]["value"] == 60.8
        assert slow["closeness"]["value"] == 53.6
        assert falling["closeness"]["value"] == 44

    def test_the_rest_of_a_change_arrives_over_the_next_days(self, companion):
        meters.settle(companion, on(0), START, write=True)
        for day, expected in ((1, 0.3), (2, 0.6), (3, 0.8)):
            out = meters.settle(companion, on(day), {"hurt": 0.8}, write=True)
            assert out["hurt"]["value"] == expected
        # Making up partway through stops it.
        meters.settle(companion, on(4), {"hurt": 0.8}, write=True)
        assert meters.settle(companion, on(5), {"hurt": 0.1})["hurt"]["value"] == 0.5

    def test_days_with_no_record_each_count(self, companion):
        meters.settle(companion, on(0), START, write=True)
        out = meters.settle(companion, on(3), {"closeness": 120})
        assert out["closeness"]["value"] == 68

    def test_the_first_day_starts_from_the_seed_and_there_is_no_floor(self, companion):
        first = meters.settle(
            companion, on(0), {"closeness": 4}, seed={"closeness": 25}, write=True
        )
        assert first["closeness"] == {
            "value": 25,
            "target": 4,
            "held": False,
            "start": None,
        }
        values = [25]
        for day in range(1, 6):
            out = meters.settle(companion, on(day), {"closeness": 4}, write=True)
            values.append(out["closeness"]["value"])
        assert values == [25, 19, 13, 7, 4, 4]

    def test_reading_never_writes(self, companion):
        meters.settle(companion, on(0), START)
        meters.kept_credits(companion, {on(0).date(): 0.8})
        assert not meters.path(companion).exists()

    def test_an_earlier_or_future_day_is_never_written(self, companion):
        meters.settle(companion, on(3), START, write=True)
        meters.settle(companion, on(1), {"closeness": 1}, write=True)
        future = dt.datetime.now(dt.timezone.utc) + days(2)
        meters.settle(companion, future, {"closeness": 1}, write=True)
        assert [row["day"] for row in meters.history(companion, future, 60)] == [
            on(3).date().isoformat()
        ]

    def test_a_damaged_record_is_set_aside(self, companion):
        meters.path(companion).write_text("{not json")
        meters.settle(companion, on(0), START, write=True)
        assert meters.path(companion).with_name("meters.json.damaged").exists()
        assert meters.history(companion, on(0))[0]["closeness"] == 50

    def test_missing_you_is_a_live_gauge_and_not_held(self, companion):
        state = feelings.compute(companion, on(0))
        assert set(state["daily"]) == {"warmth", "trust", "hurt", "irritation"}


class TestSweetMoments:
    def moments(self, day, n=5):
        return [
            {
                "id": f"m{day.isoformat()}-{i}",
                "kind": "connection",
                "topic": "talk",
                "text": "A lovely evening.",
                "evidence": "Invented conversation",
                "strength": 1.0,
                "related": None,
                "at": dt.datetime.combine(
                    day, dt.time(18, i), tzinfo=dt.timezone.utc
                ).isoformat(),
            }
            for i in range(n)
        ]

    def trust(self, companion, rows, now):
        from unittest.mock import patch

        with patch.object(feelings, "experiences", return_value=rows):
            return feelings.compute(companion, now)["meters"]["trust"]

    def test_add_at_most_two_percent_trust_a_day(self, companion):
        day = meters.RULES_FROM + days(9)
        now = dt.datetime.combine(day, dt.time(23), tzinfo=dt.timezone.utc)
        assert self.trust(companion, self.moments(day), now) == pytest.approx(0.72)

    def test_moments_before_the_rule_keep_what_they_gave(self, companion):
        day = meters.RULES_FROM - days(9)
        now = dt.datetime.combine(day, dt.time(23), tzinfo=dt.timezone.utc)
        assert self.trust(companion, self.moments(day), now) == pytest.approx(0.9)


class TestRetention:
    def talk(self, store, first, last):
        for day in range(first, last):
            for turn in range(8):
                store.say(
                    "owner",
                    "user",
                    f"{turn} An invented, long enough conversation about the garden."
                    * 4,
                    (on(day) + dt.timedelta(hours=turn - 8)).timestamp(),
                )

    def test_a_deleted_conversation_lowers_nothing(self, companion):
        import companion_intimacy as intimacy
        from tests.chat_fixtures import HermesStore

        store = HermesStore(companion.home)
        store.session("owner", "telegram", profile="")
        self.talk(store, 0, 10)
        before = meters.tick(companion, on(10))
        with store.db() as database:
            database.execute(
                "DELETE FROM messages WHERE timestamp < ?", (on(6).timestamp(),)
            )
        after = intimacy.compute(companion, on(10))
        assert before["effective_days"] >= 9
        assert after["effective_days"] == before["effective_days"]
        assert after["score"] == before["score"]

    def test_closeness_falls_past_friends_a_capped_step_at_a_time(self, companion):
        from tests.chat_fixtures import HermesStore

        store = HermesStore(companion.home)
        store.session("owner", "telegram", profile="")
        self.talk(store, 0, 8)
        scores = [meters.tick(companion, on(8))["points"]]
        assert scores[0] >= 25
        for day in range(9, 40):
            scores.append(meters.tick(companion, on(day))["points"])
        assert scores[-1] < 25
        assert all(a - b <= 6 for a, b in zip(scores, scores[1:]))


# ---- reading the meters: what moves them and where closeness is heading -------

LATER = dt.datetime(2026, 9, 20, 18, 0, tzinfo=dt.timezone.utc)


def feelings_state(**overrides):
    state = {
        "personality": "steady",
        "experiences": [],
        "reasons": [],
        "slow_change": {"warmth": 0.1, "trust": 0.05, "contact_days": 12},
        "absence": {"hours": 0.4, "expected_hours": 0, "unexplained_hours": 0.4},
        "recent_return": None,
        "daily": {},
    }
    state.update(overrides)
    return state


def closeness_state(**overrides):
    state = {
        "points": 44,
        "stage": 1,
        "stage_name": "Friends",
        "pace_multiplier": 1.0,
        "today_credit": 0.5,
        "cooling": {"silence": 0, "thin_contact": 0, "silent_hours": 0.4},
        "daily": {"value": 44, "target": 44, "held": False},
        "meters": {"hurt": 0},
    }
    state.update(overrides)
    return state


def row(kind, text, at, ident, **extra):
    return {"id": ident, "kind": kind, "text": text, "at": at.isoformat(), **extra}


class TestExplain:
    def text(self, items):
        return [x["sign"] + x["text"] for x in items]

    def test_a_rupture_names_itself_under_each_meter_it_moves(self, companion):
        hurt = row("rupture", "Robin forgot the recital", LATER - days(1), "r1")
        out = meters.explain(
            companion,
            feelings_state(experiences=[hurt], reasons=[{"id": "r1", "repair": 0.5}]),
            closeness_state(),
            LATER,
        )["meters"]
        line = "−Robin forgot the recital (yesterday, partly made up)"
        assert line in self.text(out["warmth"]["causes"])
        assert line in self.text(out["trust"]["causes"])
        assert line in self.text(out["irritation"]["causes"])
        assert self.text(out["hurt"]["causes"]) == [line + "; fades over about 7 days"]

    def test_sweet_moments_and_time_together(self, companion):
        sweet = row("connection", "A long walk by the river", LATER - days(2), "c1")
        out = meters.explain(
            companion, feelings_state(experiences=[sweet]), closeness_state(), LATER
        )["meters"]
        assert self.text(out["warmth"]["causes"]) == [
            "+A sweet moment 2 days ago: A long walk by the river",
            "+12 days you both talked",
        ]
        assert "+Sweet moments, a little each day" in self.text(out["trust"]["causes"])

    def test_old_and_corrected_moments_are_left_out(self, companion):
        old = row("connection", "Long ago", LATER - days(30), "c1")
        wrong = row("rupture", "A misunderstanding", LATER - days(1), "r1")
        fix = row("correction", "That was not a rupture", LATER, "x1", related="r1")
        out = meters.explain(
            companion,
            feelings_state(experiences=[old, wrong, fix]),
            closeness_state(),
            LATER,
        )["meters"]
        assert out["hurt"]["causes"] == []
        assert all("Long ago" not in x["text"] for x in out["warmth"]["causes"])

    def test_silence_past_the_window_and_missing_you(self, companion):
        away = {"hours": 62, "expected_hours": 16, "unexplained_hours": 50}
        out = meters.explain(
            companion, feelings_state(absence=away), closeness_state(), LATER
        )["meters"]
        assert self.text(out["irritation"]["causes"]) == [
            "−50 hours without hearing from you, past the 48-hour window"
        ]
        assert self.text(out["longing"]["causes"]) == [
            "62 hours since you last wrote, 16 of them expected"
        ]
        near = meters.explain(companion, feelings_state(), closeness_state(), LATER)
        assert self.text(near["meters"]["longing"]["causes"]) == [
            "You wrote within the hour"
        ]

    def test_a_held_meter_says_where_it_is_heading(self, companion):
        daily = {"trust": {"value": 0.6, "target": 0.9, "held": True}}
        out = meters.explain(
            companion, feelings_state(daily=daily), closeness_state(), LATER
        )["meters"]["trust"]
        assert out["held"] and out["heading"] == 0.9

    @pytest.mark.parametrize(
        "overrides, line",
        [
            ({}, "Trusted in about 5 good days"),
            (
                {"points": 10, "stage": 0, "stage_name": "Just Met"},
                "Familiar in about 3 good days",
            ),
            (
                {"points": 10, "stage": 0, "pace_multiplier": 0.6},
                "Familiar in about 5 good days",
            ),
            (
                {"daily": {"value": 50, "target": 58, "held": True}},
                "Rising: today's step is taken, and the rest comes over the next days",
            ),
            (
                {"daily": {"value": 38, "target": 20, "held": True}},
                "Falling, at most 6 points a day",
            ),
            (
                {"cooling": {"silence": 2.4, "thin_contact": 1, "silent_hours": 72}},
                "Cooling: 3 days without hearing from you",
            ),
            (
                {"cooling": {"silence": 0, "thin_contact": 4, "silent_hours": 20}},
                "Cooling: thin contact these two weeks",
            ),
            (
                {"points": 95, "stage": 4, "stage_name": "Bonded"},
                "Bonded: as close as it gets",
            ),
            ({"permanent_friend": True}, "Friendship is where this rests now"),
        ],
    )
    def test_where_closeness_is_heading(self, companion, overrides, line):
        out = meters.explain(
            companion, feelings_state(), closeness_state(**overrides), LATER
        )["closeness"]
        assert out["line"] == line

    def test_a_romance_names_the_romantic_stages(self, companion):
        companion.boundary = "next-door"
        out = meters.explain(companion, feelings_state(), closeness_state(), LATER)[
            "closeness"
        ]
        assert out["line"] == "Chemistry in about 5 good days"
        assert out["next"] == {
            "name": "Chemistry",
            "at": 50,
            "good_days": 5,
            "unlocks": [
                "flirting and pet names",
                "photos of herself",
                "sharing her worries and hopes",
            ],
        }


def test_the_pages_render_the_reasons_escaped():
    from tests.test_chat_dock import run_browser_contract

    run_browser_contract(r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('kit/app/static/feelings.js', 'utf8');
vm.runInThisContext(`
const esc=v=>String(v).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
${source.slice(source.indexOf('function meterWhy'), source.indexOf('function feelingMeters'))}
globalThis.meterWhy=meterWhy;globalThis.closenessLine=closenessLine;
`);
const info = {causes: [
  {sign: '+', text: 'A sweet moment: <b>hi</b>'},
  {sign: '−', text: 'Silence'},
  {sign: '', text: 'Third'},
], held: true, heading: 0.9};
const two = meterWhy(info);
assert.ok(two.includes('&lt;b&gt;hi&lt;/b&gt;') && !two.includes('<b>'), 'escaped');
assert.equal((two.match(/<li/g) || []).length, 3, 'two causes and the held line');
assert.ok(two.includes('Heading for 90%'));
assert.equal((meterWhy(info, Infinity).match(/<li/g) || []).length, 4);
assert.equal(meterWhy({causes: [], held: false}), '');
assert.equal(meterWhy(null), '');
const line = closenessLine({line: 'Chemistry in about 5 good days', next: {good_days: 5}, good_day: 'a real conversation'});
assert.ok(line.includes('Chemistry in about 5 good days') && line.includes('title="A good day: a real conversation."'));
assert.equal(closenessLine(null), '');
""")


def test_setup_suggests_a_temperament_and_sends_the_choice():
    from tests.test_chat_dock import run_browser_contract

    run_browser_contract(r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('kit/app/static/onboarding.js', 'utf8');
const start = source.indexOf('const TEMPERAMENT_LABEL');
const end = source.indexOf('\n', source.indexOf('const temperamentOf'));
vm.runInThisContext(source.slice(start, end) + '\nglobalThis.temperamentOf=temperamentOf;globalThis.TEMPERAMENT_LABEL=TEMPERAMENT_LABEL;');
assert.deepEqual(Object.keys(TEMPERAMENT_LABEL), ['steady', 'expressive', 'guarded']);
assert.equal(temperamentOf({persona: 'romantic'}), 'expressive');
assert.equal(temperamentOf({persona: 'shy'}), 'guarded');
assert.equal(temperamentOf({persona: 'analytical'}), 'steady');
assert.equal(temperamentOf({persona: 'romantic', temperament: 'guarded'}), 'guarded', 'the choice wins');
assert.equal(temperamentOf({persona: 'shy', temperament: 'nonsense'}), 'guarded', 'an old draft falls back');
assert.ok(source.includes('temperament:temperamentOf(derived)'), 'the answers carry it to setup');
""")
