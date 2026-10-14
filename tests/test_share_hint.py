"""The share hint only suggests a photo that could actually be sent.

It named undies as an example for every companion, including ones with adult
images switched off, where such a photo can never go out.
"""

import pytest

import companion_active as active
import companion_config as cc
import companion_media
import companion_timeline


@pytest.fixture
def companion(tmp_path, monkeypatch):
    c = cc.Companion(
        agent="Nova",
        human="Robin",
        hermes_root=tmp_path / "home",
        vault=tmp_path / "vault",
    )
    monkeypatch.setattr(
        companion_timeline,
        "latest",
        lambda c: {"path": "/x/photo.png", "activity": "reading", "location": "home"},
    )
    return c


def test_with_adult_images_off_the_hint_does_not_mention_undies(companion, monkeypatch):
    monkeypatch.setattr(
        companion_media, "adult_ready", lambda c: (False, ["switched off"])
    )
    text = active.recent_photo(companion)
    assert "undies" not in text
    assert "an outfit you like" in text and "Robin" in text


def test_where_an_undressed_photo_can_go_out_the_hint_may_say_so(
    companion, monkeypatch
):
    monkeypatch.setattr(companion_media, "adult_ready", lambda c: (True, []))
    assert "undies" in active.recent_photo(companion)


def test_a_gate_that_will_not_answer_counts_as_no(companion, monkeypatch):
    def broken(c):
        raise RuntimeError("closeness unreadable")

    monkeypatch.setattr(companion_media, "adult_ready", broken)
    assert "undies" not in active.recent_photo(companion)
