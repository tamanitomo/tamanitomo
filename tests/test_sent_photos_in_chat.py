"""Photos she sent from her routines are in her conversation context, not just their captions.

A photo sent through the outbox reached the conversation as its caption alone. Complimented
on it, she asked whether a photo had arrived at all and said she would not take credit for
something she never sent.
"""

import datetime as dt
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "kit/scripts"))

import companion_config as cc  # noqa: E402
import companion_context as context  # noqa: E402
import companion_outbox as outbox  # noqa: E402
import companion_timeline as timeline  # noqa: E402

NOW = dt.datetime(2026, 10, 10, 14, tzinfo=dt.timezone.utc)
PHOTO = "0123456789abcdef01234567"


class SentPhotoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        self.c = cc.Companion(
            agent="Nova",
            human="Robin",
            timezone="UTC",
            hermes_root=root / ".hermes",
            vault=root / "vault",
            context_tokens=272000,
        )
        self.c.home.mkdir(parents=True)
        images = timeline.root(self.c) / "images"
        captures = timeline.root(self.c) / "captures"
        images.mkdir(parents=True)
        captures.mkdir(parents=True)
        (images / f"{PHOTO}.png").write_bytes(b"png")
        scene = {"text": "Coffee at the kitchen table, hair still damp from the rain."}
        (captures / f"{PHOTO}.json").write_text(
            json.dumps({"id": PHOTO, "scene": scene})
        )
        entry = outbox.queue(
            self.c,
            {
                "kind": "image",
                "body": "Got rained on and now I'm at the table with coffee.",
                "media_path": str(images / f"{PHOTO}.png"),
            },
            NOW - dt.timedelta(minutes=30),
        )["entry"]
        outbox.mark(self.c, entry["id"], "sent", "ok", NOW - dt.timedelta(minutes=29))

    def build(self, platform):
        payload = {"extra": {"user_message": "You look great", "platform": platform}}
        return context.build(self.c, payload, now=NOW)

    def test_the_conversation_knows_the_photo_went_out_and_what_it_showed(self):
        out = self.build("telegram")
        self.assertIn("[Photos you sent Robin in the last day.", out)
        self.assertIn("Got rained on and now I'm at the table with coffee.", out)
        self.assertIn("It showed: Coffee at the kitchen table", out)

    def test_routines_keep_their_own_already_sent_list(self):
        self.assertNotIn("Photos you sent Robin", self.build("cron"))


if __name__ == "__main__":
    unittest.main()
