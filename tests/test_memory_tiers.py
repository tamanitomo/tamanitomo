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
            ["- The turkey photo Alex sent arrived a couple of weeks late."]
            + [f"- Filler {i}." for i in range(900)],
        )
        mem.archive(self.c, "MEMORY.md", apply=True)
        self.assertNotIn("turkey", self.read("MEMORY.md"))
        hits = rec.search(self.c, "Did you like the turkey photo?", limit=3, implicit=True)
        self.assertTrue(any("turkey" in r["excerpt"] for r in hits["results"]))
        # One shared word is not enough to bring a note in.
        brush = rec.search(self.c, "The turkey was dry", limit=3, implicit=True)
        self.assertFalse(any("turkey photo" in r.get("excerpt", "") for r in brush["results"]))


if __name__ == "__main__":
    unittest.main()
