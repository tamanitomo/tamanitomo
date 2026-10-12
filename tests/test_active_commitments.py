"""Recent dialogue preserves proposals and promises without turning one into the other."""

import datetime as dt
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "kit/scripts"))

import companion_active as active  # noqa: E402
import companion_config as cc  # noqa: E402
from tests.chat_fixtures import HermesStore  # noqa: E402


@pytest.mark.parametrize(
    "reply",
    [
        None,
        "Yes, let's watch after I finish my sketch. I'll call you at eight.",
        "I'd like to finish my sketch tonight. How about watching tomorrow?",
    ],
)
def test_recent_dialogue_requires_acceptance_and_keeps_actual_promises(tmp_path, reply):
    c = cc.Companion(
        agent="Nova",
        human="Robin",
        profile="nova",
        hermes_root=tmp_path / "hermes",
        vault=tmp_path / "vault",
        timezone="UTC",
        soul_in_vault=False,
    )
    now = dt.datetime(2026, 10, 20, 19, tzinfo=dt.timezone.utc)
    store = HermesStore(c.home)
    session = store.session("invented-conversation", "cli")
    invitation = "Leave your sketch for now and watch a film with me?"
    store.say(session, "user", invitation, now.timestamp() - 60)
    if reply:
        store.say(session, "assistant", reply, now.timestamp() - 30)
    before = store.path.read_bytes()

    rendered = active.recent_conversation(c, now)

    assert f"**Them**: {invitation}" in rendered
    if reply:
        assert f"**Nova**: {reply}" in rendered
    assert "is a proposal, not an agreement" in rendered
    assert "You may accept, decline, or suggest another time" in rendered
    assert (
        "Honor activities you actually agreed to and follow-ups you promised"
        in rendered
    )
    assert "do not infer acceptance from the human's request alone" in rendered
    assert "a new proposal does not cancel them" in rendered
    assert "honor that agreement!" not in rendered
    assert store.path.read_bytes() == before
