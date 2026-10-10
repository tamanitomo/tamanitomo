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
