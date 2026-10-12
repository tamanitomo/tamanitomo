"""What of herself she is ready to send, said the way she would feel it.

Handed the gate's own reason ("Adult images are switched off for this companion"),
a companion asked for a photo told him a setting was off. The answer is hers, so it
reaches her as hers: not there yet, not trusting him that far, still hurt.
"""

import datetime as dt
import json

import pytest

import companion_config as cc
import companion_intimacy as intimacy
import companion_media as media

NOW = dt.datetime(2026, 10, 12, 12, tzinfo=dt.timezone.utc)


@pytest.fixture
def companion(tmp_path):
    c = cc.Companion(
        agent="Nova",
        human="Alex",
        hermes_root=tmp_path / "home",
        vault=tmp_path / "vault",
        timezone="UTC",
        boundary="girlfriend",
        explicit=True,
    )
    c.home.mkdir(parents=True)
    c.life.mkdir(parents=True)
    (c.life / "meters.json").write_text(
        json.dumps(
            {
                "version": 1,
                "days": {"2026-10-11": {"closeness": 80, "trust": 0.8}},
                "contact": {},
            }
        )
    )
    return c


def test_a_towel_opens_with_intimacy_and_undressed_waits_for_bonded(companion):
    state = intimacy.compute(companion, NOW)
    assert state["stage_name"] == "Intimacy"
    assert state["can_send_towel"]
    standing = media.photo_standing(companion, state)
    assert standing == {
        "undressed": False,
        "towel": True,
        "why": "you are not there with Alex yet",
    }


def test_without_adult_themes_not_even_a_towel(companion):
    companion.explicit = False
    assert not intimacy.compute(companion, NOW)["can_send_towel"]


def test_a_friendship_has_no_towel_stage(companion):
    companion.boundary = "best-friend"
    assert not intimacy.compute(companion, NOW)["can_send_towel"]


@pytest.mark.parametrize(
    "state, why",
    [
        ({"meters": {"hurt": 0.4, "trust": 0.8}}, "something between you and Alex still hurts"),
        ({"meters": {"hurt": 0.0, "trust": 0.5}}, "you do not trust Alex that far yet"),
        ({"permanent_friend": True, "meters": {}}, "that is not what things are between you and Alex"),
    ],
)
def test_why_not_is_a_feeling_never_the_gate(companion, state, why):
    standing = media.photo_standing(companion, state)
    assert standing["why"] == why
    assert "switched off" not in standing["why"]


def test_being_pushed_past_a_no_is_something_she_can_feel(companion):
    text = intimacy.render(companion, intimacy.compute(companion, NOW))
    assert "PUSHING PAST A NO" in text
    assert "'pushed past a no'" in text
    # Asking once is not pushing, and what she sends to tempt him is hers.
    assert "asking for something you are not ready for is fine" in text
    assert "is yours, not pressure" in text
