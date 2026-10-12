"""What each closeness stage unlocks: the owner's gentle ladder (2026-10-10)."""

import datetime as dt
import pathlib
import sys
from unittest.mock import patch

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "kit/scripts"))

import companion_config as cc  # noqa: E402
import companion_gates as gates  # noqa: E402

NOON = dt.datetime(2026, 9, 9, 12, 0, tzinfo=dt.timezone.utc)


@pytest.fixture
def companion(tmp_path):
    c = cc.Companion(
        agent="Nova",
        human="Robin",
        hermes_root=tmp_path / "hermes",
        vault=tmp_path / "vault",
        timezone="UTC",
        boundary="next-door",
        outreach="free",
        outreach_per_day=5,
        quiet_start="23:00",
        quiet_end="07:00",
        content_permissions={"image": "yes", "voice": "yes"},
        soul_in_vault=False,
    )
    c.home.mkdir(parents=True)
    c.life.mkdir(parents=True)
    c.save()
    return c


def at_stage(stage):
    return patch.object(gates, "stage_now", return_value=stage)


class TestTheLadder:
    def test_a_romance_climbs_the_gentle_ladder(self, companion):
        steps = {s["name"]: s["unlocks"] for s in gates.ladder(companion)}
        assert steps == {
            "Just Met": [],
            "Friends": [
                "starting conversations, up to your daily limit",
                "everyday photos of her day",
                "voice notes",
                "teasing and inside jokes",
                "saying “I miss you”",
            ],
            "Chemistry": [
                "flirting and pet names",
                "photos of herself",
                "sharing her worries and hopes",
            ],
            "Intimacy": [
                "planning dates with you",
                "more personal photos",
                "good-night and good-morning rituals",
                "a teasing photo in a towel, if adult themes are on",
            ],
            "Bonded": ["intimacy, if adult themes are on", "adult images, as a choice"],
        }

    def test_a_friendship_climbs_it_without_the_romance(self, companion):
        companion.boundary = "best-friend"
        companion.pronoun_set = "they"
        steps = {s["name"]: s["unlocks"] for s in gates.ladder(companion)}
        assert steps["Trusted"] == [
            "nicknames",
            "photos of themselves",
            "sharing their worries and hopes",
        ]
        assert steps["Confidant"][0] == "making plans to do things with you"
        assert steps["Bonded"] == []
        assert "flirting" not in gates.unlocked(companion, 4)

    def test_what_is_open_at_each_stage(self, companion):
        assert gates.unlocked(companion, 0) == set()
        assert "flirting" in gates.unlocked(companion, 2)
        assert "dates" not in gates.unlocked(companion, 2)
        assert "rituals" in gates.unlocked(companion, 3)

    def test_progression_off_holds_nothing_back_short_of_bonded(self, companion):
        companion.relationship_progression = "off"
        assert "rituals" in gates.unlocked(companion, 0)
        assert "intimacy" not in gates.unlocked(companion, 0)
        assert gates.messages_a_day(companion, 0) is None
        assert gates.may_send(companion, 0, "image")
        assert gates.guidance(companion, 0) == ""


class TestHerContext:
    def test_just_met(self, companion):
        text = gates.guidance(companion, 0)
        assert text.startswith("You have just met Robin")
        assert "at most once a day (enforced)" in text
        assert "This stage holds" not in text
        assert "flirt and use pet names" in text.split("Not yet")[1]

    def test_friends(self, companion):
        now, later = gates.guidance(companion, 1).split("Not yet")
        assert "say you miss Robin" in now and "send voice notes" in now
        assert "flirt and use pet names" in later
        assert "never mention this list" in later

    def test_it_reaches_her_with_the_stage(self, companion):
        import companion_intimacy as intimacy

        text = intimacy.render(companion, intimacy.compute(companion, NOON))
        assert "You have just met Robin" in text


class TestMessagesADay:
    def test_just_met_writes_first_once_a_day(self, companion):
        import companion_outreach as outreach

        with at_stage(0):
            first = outreach.decide(companion, NOON)
            assert first["allowed"] and first["limit"] == 1
            outreach.claim(companion, now=NOON)
            second = outreach.decide(companion, NOON)
        assert not second["allowed"]
        assert "just met" in second["reason"]

    def test_from_friends_the_persons_own_limit(self, companion):
        import companion_outreach as outreach

        with at_stage(1):
            assert outreach.decide(companion, NOON)["limit"] == 5

    def test_a_stage_that_cannot_be_read_holds_nothing_back(self, companion):
        import companion_outreach as outreach

        with patch.object(gates, "stage_now", side_effect=OSError("unreadable")):
            assert outreach.decide(companion, NOON)["limit"] == 5


class TestUnpromptedMedia:
    def entry(self, companion, content):
        import companion_outbox as outbox

        media = companion.life / "photo.png"
        media.write_bytes(b"not really a picture")
        kind = {"image": "image", "voice": "voice"}.get(content, "text")
        row = {"kind": kind, "body": "look", "reason": "test"}
        if kind != "text":
            row["media_path"] = str(media)
        return outbox.queue(companion, row, NOON)["entry"]

    @pytest.mark.parametrize("content", ["image", "voice"])
    def test_photos_and_voice_notes_wait_for_friends(self, companion, content):
        import companion_dispatch as dispatch

        entry = self.entry(companion, content)
        with at_stage(0):
            held = dispatch.verdict(companion, entry, NOON)
        with at_stage(1):
            allowed = dispatch.verdict(companion, entry, NOON)
        assert held["action"] == "withhold" and "Friends" in held["reason"]
        assert allowed["action"] == "send"

    def test_words_are_not_held_by_the_stage(self, companion):
        import companion_dispatch as dispatch

        with at_stage(0):
            assert dispatch.verdict(companion, self.entry(companion, "text"), NOON)[
                "action"
            ] == ("send")


class TestPhotoShares:
    def share(self, companion, stage):
        import companion_timeline as timeline

        with at_stage(stage):
            return timeline.share_opportunity(companion, {"variants": [{}]}, NOON)

    def test_none_while_just_met(self, companion):
        out = self.share(companion, 0)
        assert not out["ok"] and "just met" in out["why"]

    def test_one_a_day_at_friends_and_photos_of_her_day(self, companion):
        out = self.share(companion, 1)
        assert out["left_today"] == 1
        assert out["fits"].startswith("Photos of your day")

    def test_two_a_day_from_chemistry_and_more_personal_at_intimacy(self, companion):
        assert self.share(companion, 2)["left_today"] == 2
        assert "of yourself" in self.share(companion, 2)["fits"]
        assert "more personal" in self.share(companion, 3)["fits"]


def test_the_next_stage_says_what_it_brings(companion):
    import companion_feelings as feelings
    import companion_intimacy as intimacy
    import companion_meters as meters

    state = intimacy.compute(companion, NOON)
    out = meters.explain(companion, feelings.compute(companion, NOON), state, NOON)[
        "closeness"
    ]
    assert out["next"]["name"] == "Friends"
    assert out["next"]["unlocks"][0] == "starting conversations, up to your daily limit"
