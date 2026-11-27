"""Her always-loaded memory keeps the relationship; working notes are archived first, and a
topic he raises finds what was archived."""

import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "kit/scripts"))

import companion_config as cc  # noqa: E402
import companion_memory as mem  # noqa: E402
import companion_recall as rec  # noqa: E402


class MemoryTierTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        self.c = cc.Companion(
            agent="Nova",
            human="Alex",
            hermes_root=root / "h",
            vault=root / "v",
            timezone="UTC",
            context_tokens=8192,
        )
        self.dir = mem.memory_dir(self.c)
        self.dir.mkdir(parents=True)
        (self.c.home / "config.yaml").write_text(
            "memory:\n  memory_char_limit: 2200\n  user_char_limit: 1375\n",
            encoding="utf-8",
        )

    def write(self, name, items):
        (self.dir / name).write_text(mem.ENTRY_DELIMITER.join(items), encoding="utf-8")

    def read(self, name):
        return (self.dir / name).read_text(encoding="utf-8")

    def test_the_relationship_stays_in_view_and_working_notes_go_first(self):
        close = "- Alex likes to be called Lex, and a ring from him would mean a great deal."
        work = [
            f"- Server {i} answers at `http://192.168.1.{i}:8188`, settings in `/home/x/{i}.json`."
            for i in range(40)
        ]
        self.write("USER.md", [close] + work)  # the relationship is the OLDEST entry
        mem.archive(self.c, "USER.md", apply=True)
        self.assertIn("called Lex", self.read("USER.md"))
        archived = mem.archive_for(self.c, "USER.md").read_text(encoding="utf-8")
        self.assertIn("Server 0 ", archived)
        for i in range(40):
            self.assertIn(f"Server {i} ", self.read("USER.md") + archived)

    def test_a_curated_move_takes_exactly_those_entries(self):
        self.write("MEMORY.md", ["- first", "- second", "- third"])
        result = mem.archive(self.c, "MEMORY.md", move=[0, 2], apply=True)
        self.assertEqual((result["moved"], result["kept"]), (2, 1))
        self.assertEqual(self.read("MEMORY.md").strip(), "- second")
        archived = mem.archive_for(self.c, "MEMORY.md").read_text(encoding="utf-8")
        self.assertIn("- first", archived)
        self.assertIn("- third", archived)

    def test_a_curated_move_never_empties_the_file(self):
        self.write("MEMORY.md", ["- first", "- second"])
        with self.assertRaises(ValueError):
            mem.archive(self.c, "MEMORY.md", move=[0, 1], apply=True)

    def test_a_topic_he_raises_finds_the_archived_note(self):
        self.write(
            "MEMORY.md",
            ["- The lighthouse photo Alex sent arrived a couple of weeks late."]
            + [f"- Filler {i}." for i in range(900)],
        )
        mem.archive(self.c, "MEMORY.md", apply=True)
        self.assertNotIn("lighthouse", self.read("MEMORY.md"))
        hits = rec.search(
            self.c, "Did you like the lighthouse photo?", limit=3, implicit=True
        )
        self.assertTrue(any("lighthouse" in r["excerpt"] for r in hits["results"]))
        # An everyday word alone ("the photo") does not bring a note in; a specific one does.
        brush = rec.search(self.c, "Did you like the photo?", limit=3, implicit=True)
        self.assertFalse(
            any("lighthouse" in r.get("excerpt", "") for r in brush["results"])
        )
        specific = rec.search(
            self.c, "The lighthouse was foggy", limit=3, implicit=True
        )
        self.assertTrue(
            any("lighthouse" in r.get("excerpt", "") for r in specific["results"])
        )

    def test_her_archived_note_keeps_a_place_beside_stronger_matches(self):
        import companion_self as slf
        import datetime as dt

        now = dt.datetime(2026, 10, 10, 12, tzinfo=dt.timezone.utc)
        for i in range(3):
            slf.record_fact(
                self.c.human_dir,
                f"Alex built a keyboard voice note button {i}",
                "said so",
                now,
            )
        self.write(
            "MEMORY.md",
            ["- The keyboard voice button was flashed with new firmware."]
            + [f"- Filler {i}." for i in range(900)],
        )
        mem.archive(self.c, "MEMORY.md", apply=True)
        hits = rec.search(
            self.c, "Did the keyboard voice button work?", limit=2, implicit=True
        )
        kinds = [r.get("kind") for r in hits["results"]]
        self.assertIn("memory_note_requires_provenance_check", kinds)
        self.assertEqual(len(hits["results"]), 2)

    def test_an_archived_note_needs_two_words_that_say_what_it_is_about(self):
        generic = [
            f"- Favorite character {i} in a show Alex watched once." for i in range(6)
        ]
        self.write(
            "MEMORY.md",
            generic
            + [
                "- Alex's favorite anime is Starfall Harbor; his favorite character is Mirelle."
            ]
            + ["- The pocket terminal has a working one-button voice-note control."]
            + [f"- Filler {i}." for i in range(900)],
        )
        mem.archive(self.c, "MEMORY.md", apply=True)
        hits = rec.search(
            self.c, "Is Starfall Harbor still on Mirelle's arc?", limit=2, implicit=True
        )
        notes = [
            r["excerpt"]
            for r in hits["results"]
            if r.get("kind") == "memory_note_requires_provenance_check"
        ]
        self.assertTrue(notes and "Mirelle" in notes[0])
        hits = rec.search(
            self.c,
            "Did the pocket terminal voice note button work?",
            limit=2,
            implicit=True,
        )
        self.assertTrue(any("pocket terminal" in r["excerpt"] for r in hits["results"]))
        everyday = rec.search(
            self.c,
            "Who is your favorite character in the show?",
            limit=2,
            implicit=True,
        )
        self.assertFalse(
            any(
                r.get("kind") == "memory_note_requires_provenance_check"
                for r in everyday["results"]
            )
        )


if __name__ == "__main__":
    unittest.main()
