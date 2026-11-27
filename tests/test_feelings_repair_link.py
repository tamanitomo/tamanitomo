"""A repair finds its rupture: by `related`, by the names she reaches for, or by a clear refusal."""

import datetime as dt
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "kit/scripts"))

import companion_config as cc  # noqa: E402
import companion_feelings as feelings  # noqa: E402

NOW = dt.datetime(2026, 10, 10, 12, tzinfo=dt.timezone.utc)


@pytest.fixture
def companion(tmp_path):
    c = cc.Companion(
        agent="Nova",
        human="Robin",
        timezone="UTC",
        hermes_root=tmp_path / "h",
        vault=tmp_path / "v",
    )
    c.life.mkdir(parents=True)
    feelings.record(
        c,
        {
            "kind": "rupture",
            "id": "photo-wait",
            "topic": "let down",
            "text": "I asked for a photo and it slipped by",
            "evidence": "Synthetic",
            "at": (NOW - dt.timedelta(days=1)).isoformat(),
        },
        NOW,
    )
    return c


def test_a_repair_can_name_its_rupture_the_way_she_tried_to(companion):
    feelings.record(
        companion,
        {
            "kind": "repair",
            "rupture": "photo-wait",
            "text": "The photo came, late, and that was enough",
            "evidence": "Synthetic",
        },
        NOW,
    )
    [repair] = [r for r in feelings.experiences(companion) if r["kind"] == "repair"]
    assert repair["related"] == "photo-wait" and repair["topic"] == "let down"


def test_an_unlinked_repair_is_told_the_field_and_the_ruptures(companion):
    with pytest.raises(ValueError) as refused:
        feelings.record(
            companion,
            {"kind": "repair", "text": "It's fine now", "evidence": "Synthetic"},
            NOW,
        )
    assert '"related"' in str(refused.value) and "photo-wait" in str(refused.value)
