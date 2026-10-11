"""People in her life: her own, who she is with, and what is going on with them."""

import datetime as dt
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "kit/scripts"))

import companion_config as cc  # noqa: E402
import companion_life as life  # noqa: E402
import companion_needs as needs  # noqa: E402
import companion_preread as preread  # noqa: E402
import companion_presence as presence  # noqa: E402

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 20, 10, tzinfo=UTC)
FRIENDS = [
    {
        "id": "ines",
        "name": "Ines",
        "who": "runs the bakery stall at the market",
        "standing": "Thursday evenings, tea at hers",
    },
    {"id": "teo", "name": "Teo", "who": "plays in a covers band"},
]


def make(tmp_path, name="nova", friends=None):
    c = cc.Companion(
        agent=name.title(),
        human="Robin",
        hermes_root=tmp_path / name / "hermes",
        vault=tmp_path / name / "vault",
        timezone="UTC",
        boundary="next-door",
        soul_in_vault=False,
    )
    c.home.mkdir(parents=True)
    c.life.mkdir(parents=True)
    c.save()
    routine = {"kind": "imagined_routine", "weekly": [], "daily": []}
    if friends is not None:
        routine["recurring_cast"] = friends
    (c.life / "routine.json").write_text(json.dumps(routine))
    presence.update_wardrobe(
        c, [{"id": "jeans", "description": "blue jeans", "use": "day"}]
    )
    return c


@pytest.fixture
def companion(tmp_path):
    return make(tmp_path, friends=FRIENDS)


class TestOneCast:
    def test_the_people_setup_wrote_are_hers_and_weekly(self, companion):
        people = {p["id"]: p for p in life.cast(companion.life)}
        assert people["ines"]["own"] and people["ines"]["cadence"] == "weekly"
        assert people["ines"]["note"] == "Thursday evenings, tea at hers"
        assert life.own_people(companion.life) == 2

    def test_a_few_seeded_people_only_until_she_has_her_own(self, companion):
        seeded = [p for p in life.cast(companion.life) if not p.get("own")]
        assert len(seeded) == life.SEEDS_OFFERED
        life.add_person(companion.life, {"name": "Marguerite", "relation": "aunt"})
        assert all(p.get("own") for p in life.cast(companion.life))

    def test_a_seed_she_spent_time_with_stays(self, companion):
        seed = next(p for p in life.cast(companion.life) if not p.get("own"))
        life.saw_people(companion.life, [seed["id"]], NOW.date())
        life.add_person(companion.life, {"name": "Marguerite", "relation": "aunt"})
        assert seed["id"] in {p["id"] for p in life.cast(companion.life)}

    def test_two_companions_are_not_offered_the_same_friends(self, tmp_path):
        one = {p["id"] for p in life.cast(make(tmp_path, "nova").life)}
        other = {p["id"] for p in life.cast(make(tmp_path, "kit").life)}
        assert one != other


class TestWhoSheIsWith:
    def write(self, c, location, minutes, **extra):
        current = presence.current(c)
        presence.update(
            c,
            {
                "previous_id": current["id"] if current else None,
                "outfit": ["jeans"],
                "location": location,
                "activity": f"moment {minutes}",
                "mood": "fine",
                "care": [],
                "transition": "moved on" if current else "",
                "text": "An ordinary moment.",
                **extra,
            },
            NOW + dt.timedelta(minutes=minutes),
        )
        return presence.current(c)["state"]

    def test_with_records_seeing_them_by_name_or_id(self, companion):
        state = self.write(companion, "the market", 0, **{"with": ["INES", "teo"]})
        assert state["with"] == ["ines", "teo"]
        seen = {p["id"]: p["last_seen"] for p in life.cast(companion.life)}
        assert seen["ines"] == seen["teo"] == "2026-10-20"

    def test_company_stays_while_she_does_and_ends_when_she_moves(self, companion):
        self.write(companion, "the market", 0, **{"with": ["ines"]})
        assert self.write(companion, "the market", 20)["with"] == ["ines"]
        assert "with" not in self.write(companion, "the bus home", 40)

    def test_nobody_she_has_not_met(self, companion):
        with pytest.raises(ValueError, match="nobody called 'Zed'") as raised:
            self.write(companion, "the market", 0, **{"with": ["Zed"]})
        assert '"ines" (Ines)' in str(raised.value)

    def test_time_with_someone_is_company(self, companion):
        self.write(companion, "the market", 0)
        self.write(companion, "the market", 20, **{"with": ["ines"]})
        fed = needs._presence_feeds(
            companion, NOW - dt.timedelta(hours=1), NOW + dt.timedelta(hours=1)
        )
        assert fed == [(NOW + dt.timedelta(minutes=20), "social")]


class TestWhatIsGoingOnWithThem:
    def test_news_rides_along_when_they_are_due(self, companion):
        life.add_news(
            companion.life,
            "ines",
            "Her stall moved to the covered market",
            "2026-10-02",
        )
        text = preread.day_ideas(companion, NOW)
        assert "Ines [id=ines]" in text
        assert "last you heard (2026-10-02): Her stall moved to the covered market" in (
            text
        )
        assert '"with": ["<id>"]' in text

    def test_a_life_with_few_people_is_asked_to_let_someone_in(self, tmp_path):
        alone = make(tmp_path, "solo")
        assert "few people of your own yet (0)" in preread.day_ideas(alone, NOW)
        for name in ("Ada", "Bo", "Cy"):
            life.add_person(alone.life, {"name": name})
        assert "few people of your own" not in preread.day_ideas(alone, NOW)
