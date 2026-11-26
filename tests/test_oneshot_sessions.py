"""`hermes chat --oneshot` (the workspace chat, local clients) is a local conversation."""

import os
import pathlib
import sys
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "kit/scripts"))

import companion_transcript as transcript  # noqa: E402

TRUSTED = transcript.OwnerBinding()
ME = f"uid:{os.getuid()}" if hasattr(os, "getuid") else ""


def kind(**row):
    return transcript.session_kind({"session_id": "s1", **row}, TRUSTED, set())


def test_a_local_oneshot_is_a_terminal_conversation():
    assert kind(source="oneshot", chat_id="s1", user_id=ME) == ("terminal", "")
    assert kind(source="oneshot") == ("terminal", "")


def test_a_oneshot_from_elsewhere_is_refused():
    assert kind(source="oneshot", chat_id="other") == (None, "oneshot_not_local")
    if hasattr(os, "getuid"):
        assert kind(source="oneshot", user_id="uid:99999") == (
            None,
            "oneshot_not_local",
        )


def test_without_a_uid_the_user_check_is_skipped():
    with mock.patch.object(transcript.os, "getuid", None, create=True):
        assert kind(source="oneshot", user_id="uid:12345") == ("terminal", "")


def test_scheduled_runs_are_never_conversations():
    assert kind(source="cron")[0] is None
