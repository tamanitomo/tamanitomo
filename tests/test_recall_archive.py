"""Recall that outlasts the session store: her chapters answer "when did we...", and the vault's conversation archive
stands in for Hermes's session database when it is gone, so an explicit question about the past still finds what
the human said."""

import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "kit" / "scripts"), str(ROOT)]

import companion_config as cc  # noqa: E402
import companion_recall as recall  # noqa: E402


class RecallArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.c = cc.Companion(agent="Nova", human="Robin", profile="nova", timezone="America/New_York",
                              hermes_root=self.tmp / ".hermes", vault=self.tmp / "vault")  # fmt: skip
        self.c.home.mkdir(parents=True)

    def test_her_chapters_answer_when(self):
        story = self.c.data / "story" / "2027"
        story.mkdir(parents=True)
        (story / "2027-01.md").write_text(
            "# January 2027: Snow and porch light\n\n"
            "We watched Harbor Lights on a rainy night and argued about the ending for an hour.\n"
            "Robin fixed the porch swing at last.\n\n<!-- written 2027-02-01 -->\n",
            encoding="utf-8",
        )
        out = recall.search(self.c, "when did we watch harbor lights?", seconds=2)
        chapter = [r for r in out["results"] if r["kind"] == "her_chapter_summary"]
        self.assertEqual(len(chapter), 1)
        self.assertIn("Harbor Lights on a rainy night", chapter[0]["excerpt"])
        self.assertTrue(chapter[0]["source"].endswith("2027-01.md"))
        one = recall.search(self.c, "what did robin fix in the porch?", seconds=2)
        lines = [
            r["excerpt"] for r in one["results"] if r["kind"] == "her_chapter_summary"
        ]
        self.assertTrue(
            any("porch swing" in x for x in lines), lines
        )  # one rare word is enough
        quiet = recall.search(self.c, "harbor lights", seconds=2, implicit=True)
        self.assertFalse(
            [r for r in quiet["results"] if r["kind"] == "her_chapter_summary"]
        )  # explicit questions only

    def test_the_archive_stands_in_for_a_missing_session_store(self):
        month = self.c.data / "conversations" / "2027"
        month.mkdir(parents=True)
        rows = [
            {"id": 1, "at": "2027-01-09T20:00:00-05:00", "who": "owner", "speaker": "Robin",
             "text": "I finally fixed the porch swing, it squeaks less now"},
            {"id": 2, "at": "2027-01-09T20:01:00-05:00", "who": "companion", "speaker": "Nova",
             "text": "The porch swing! I knew you would"},
            {"id": 3, "at": "2027-01-10T20:00:00-05:00", "who": "owner", "speaker": "Robin",
             "text": "[Game event: Rook fixed a porch swing]"},
        ]  # fmt: skip
        (month / "2027-01.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
        )
        self.assertFalse((self.c.home / "state.db").exists())
        out = recall.search(self.c, "remember when I fixed the porch swing?", seconds=2)
        said = [
            r
            for r in out["results"]
            if r["kind"] == "human_statement_requires_interpretation"
        ]
        self.assertEqual(len(said), 1)
        self.assertTrue(
            said[0]["excerpt"].startswith("I finally fixed the porch swing")
        )
        self.assertEqual(said[0]["source"], "archive:2027-01.jsonl:1")
        self.assertIn("conversation archive", " ".join(out["warnings"]))


if __name__ == "__main__":
    unittest.main()
