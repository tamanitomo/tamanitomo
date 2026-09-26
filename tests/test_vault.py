"""Safe vault history, profile boundaries, note conflicts, and navigable indexes."""

import dataclasses
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import companion_config as cc
import companion_local_context as local
import companion_vault as vault
import companion_vault_index as vi

from tests.support import WorkspaceFixture

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("git"), "git is not installed")
class VaultHistoryTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        self.c = cc.Companion(
            agent="Nova",
            human="Alex",
            hermes_root=root / "home",
            vault=root / "vault",
            timezone="UTC",
        )
        self.c.soul_dir.mkdir(parents=True, exist_ok=True)
        self.file = self.c.soul_dir / "SOUL.md"
        self.relative = str(self.file.relative_to(self.c.vault))

    def test_init_is_safe_to_run_twice_and_never_adds_a_remote(self):
        first = vault.init(self.c)
        second = vault.init(self.c)
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        remotes = subprocess.run(
            ["git", "-C", str(self.c.vault), "remote"], capture_output=True, text=True
        )
        self.assertEqual(remotes.stdout.strip(), "")

    def test_a_quiet_period_produces_no_commit(self):
        vault.init(self.c)
        self.file.write_text("first")
        self.assertTrue(vault.commit(self.c)["committed"])
        self.assertEqual(vault.commit(self.c)["reason"], "nothing changed")

    def test_an_old_version_comes_back_beside_the_file_not_over_it(self):
        vault.init(self.c)
        self.file.write_text("the careful original")
        vault.commit(self.c)
        old = vault.history(self.c, self.relative)[0]["commit"]
        self.file.write_text("a consolidation that went too far")
        vault.commit(self.c)
        result = vault.restore(self.c, self.relative, old)
        self.assertEqual(self.file.read_text(), "a consolidation that went too far")
        self.assertEqual(
            pathlib.Path(result["restored"]).read_text(), "the careful original"
        )
        self.assertIn("not over it", result["note"])

    def test_history_lists_every_version_newest_first(self):
        vault.init(self.c)
        for text in ("one", "two", "three"):
            self.file.write_text(text)
            vault.commit(self.c)
        versions = vault.history(self.c, self.relative)
        self.assertEqual(len(versions), 3)
        self.assertEqual(
            vault.show(self.c, self.relative, versions[0]["commit"]), "three"
        )
        self.assertEqual(
            vault.show(self.c, self.relative, versions[-1]["commit"]), "one"
        )

    def test_a_path_with_no_history_says_so_rather_than_guessing(self):
        vault.init(self.c)
        with self.assertRaises(ValueError):
            vault.show(
                self.c, self.relative, "0000000000000000000000000000000000000000"
            )
        self.assertEqual(vault.history(self.c, "nothing/here.md"), [])


def note(root, rel, text="", age=0):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    t = 1700000000 - age
    os.utime(p, (t, t))
    return p


class VaultIndexTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        self.vault = root / "vault"
        self.c = cc.Companion(
            agent="Nova",
            human="Alex",
            hermes_root=root / "home",
            vault=self.vault,
            timezone="UTC",
            context_tokens=272000,
        )
        note(self.vault, "README.md", "# README\n")
        note(
            self.vault,
            "projects/garden/plan.md",
            "# Garden plan\n## Beds\n## Watering\n```\n# not a heading\n```\n",
            age=10,
        )
        note(
            self.vault,
            "projects/garden/old.md",
            "# Old\n## Ancient history\n",
            age=99999,
        )
        note(self.vault, ".obsidian/workspace.md", "# hidden")
        note(self.vault, "agents/sam/diary.md", "# Private to Sam")
        note(self.vault, "agents/nova/mine.md", "# Mine")
        note(self.vault, "archive/big/one.md")
        note(self.vault, "image.png")

    def names(self, c=None):
        return {(n["dir"], n["name"]) for n in vi.scan(c or self.c)}

    def test_scan_skips_hidden_and_other_agents_private_folders(self):
        found = self.names()
        self.assertIn(("projects/garden", "plan"), found)
        self.assertNotIn((".obsidian", "workspace"), found)
        self.assertFalse(
            any((d.startswith("agents") for d, _ in found)),
            "the root agent maps no profile subtree",
        )
        nova = dataclasses.replace(self.c, profile="nova")
        self.assertIn(("agents/nova", "mine"), self.names(nova))
        self.assertNotIn(("agents/sam", "diary"), self.names(nova))
        self.assertNotIn(
            ("archive/big", "one"),
            self.names(dataclasses.replace(self.c, vault_index_exclude=["archive"])),
        )

    def test_headings_skip_code_fences_and_a_title_restating_the_name(self):
        by = {n["name"]: n["headings"] for n in vi.scan(self.c)}
        self.assertEqual(by["plan"], ["Garden plan", "Beds", "Watering"])
        self.assertEqual(by["README"], [])

    def test_every_folder_with_its_count_and_key_files(self):
        note(self.vault, "projects/garden/README.md", "# Readme", age=500000)
        text = vi.render(self.c, vi.scan(self.c), 100000)
        self.assertIn(
            "projects/garden/ (3): README, plan, old",
            text,
            "README explains the folder, then newest first",
        )
        self.assertIn("(vault root)/ (1): README", text)
        self.assertIn("archive/big/ (1): one", text)
        self.assertNotIn("Folder counts only", text)

    def test_many_notes_are_counted_not_listed(self):
        for i in range(12):
            note(self.vault, f"journal/d{i:02}.md", age=i)
        text = vi.render(self.c, vi.scan(self.c), 100000)
        self.assertIn("journal/ (12): d00, d01, d02, d03, d04 +7 more", text)

    def test_small_budgets_drop_key_files_then_depth_and_say_so(self):
        notes = vi.scan(self.c)
        bare = vi.render(self.c, notes, len(vi.render(self.c, notes, 10**9)) - 1)
        self.assertLess(len(bare), len(vi.render(self.c, notes, 10**9)))
        self.assertIn("projects/garden/ (2)", bare)
        head = len(vi.render(self.c, [], 10**9))
        for i in range(30):
            note(self.vault, f"archive/deep/level{i}/n.md")
        notes = vi.scan(self.c)
        tiny = vi.render(self.c, notes, head + 200)
        self.assertIn("Folder counts only", tiny)
        self.assertIn("archive/deep/ (30)", tiny)
        self.assertNotIn("level0", tiny)
        self.assertLessEqual(len(tiny), head + 200)

    def test_installed_tool_folders_are_not_part_of_the_vault(self):
        note(self.vault, "site/node_modules/pkg/README.md", "# pkg")
        self.assertNotIn(("site/node_modules/pkg", "README"), self.names())

    def test_show_lists_a_folder_in_full_with_sections(self):
        out = vi.show(self.c, "projects")
        self.assertIn("- plan: Garden plan · Beds · Watering", out)
        self.assertIn("- old: Old · Ancient history", out)

    def test_sent_once_per_session_and_again_once_compression_drops_it(self):
        first = vi.for_prompt(self.c, {"extra": {"conversation_history": []}})
        self.assertTrue(first.startswith(vi.BEGIN) and first.endswith(vi.END))
        carried = [
            {"role": "user", "content": "hi", "api_content": "hi\n\n" + first},
            {"role": "assistant", "content": "hey"},
        ]
        self.assertEqual(
            vi.for_prompt(self.c, {"extra": {"conversation_history": carried}}), ""
        )
        summarised = [{"role": "user", "content": "[summary of earlier turns]"}]
        self.assertTrue(
            vi.for_prompt(self.c, {"extra": {"conversation_history": summarised}})
        )
        self.assertEqual(
            vi.for_prompt(dataclasses.replace(self.c, vault_index_tokens=0), {}), ""
        )

    def test_cache_is_reused_while_fresh_and_rebuilt_on_demand(self):
        first = vi.build(self.c)
        note(self.vault, "new-note.md")
        self.assertEqual(vi.build(self.c), first)
        self.assertIn("README, new-note", vi.build(self.c, force=True))

    def test_the_local_context_engine_keeps_the_map_when_it_drops_old_snapshots(self):
        snapshot = local.BEGIN + "\n[Nova — continuity]\nstate\n" + local.END
        index = vi.BEGIN + "\nmap\n" + vi.END
        self.assertEqual(
            local.without_snapshot("hi\n\n" + snapshot + "\n\n" + index, "hi", "Nova"),
            "hi\n\n" + index,
        )

    def test_budget_follows_the_window_and_the_setting(self):
        self.assertEqual(cc.vault_index_cap(272000), 100000)
        self.assertEqual(cc.vault_index_cap(32768), int(32768 * 0.1) * 4)
        self.assertEqual(cc.vault_index_cap(272000, 0), 0)
        self.assertEqual(cc.vault_index_cap(272000, 70000), 280000)
        self.assertEqual(
            cc.vault_index_cap(32768, 70000),
            32768 * 2,
            "never more than half the window",
        )
        with self.assertRaises(ValueError):
            cc.Companion(vault_index_tokens=-2)
        with self.assertRaises(ValueError):
            cc.Companion(vault_index_exclude="archive")

    def test_scaffold_recognises_its_hook_under_any_interpreter(self):
        from kit.cli.scaffold import _runs_hook

        hook = pathlib.Path("/home/x/.hermes/hooks/companion-context.py")
        self.assertTrue(
            _runs_hook(
                "/usr/bin/python3 /home/x/.hermes/hooks/companion-context.py", hook
            )
        )
        self.assertTrue(
            _runs_hook(
                '/venv/bin/python "/home/x/.hermes/hooks/companion-context.py"', hook
            )
        )
        self.assertFalse(
            _runs_hook("/usr/bin/python3 /home/x/.hermes/hooks/other.py", hook)
        )
        self.assertFalse(_runs_hook("", hook))


class VaultApiTests(WorkspaceFixture):

    def test_vault_boundaries_and_note_conflicts(self):
        (self.vault / "notes").mkdir()
        note = self.vault / "notes/hello.md"
        note.write_text("# Hello\n")
        response = self.client.get(
            "/api/vault/file?profile=nova&path=notes/hello.md", headers=self.headers
        )
        body = response.json()
        self.assertTrue(body["editable"])
        note.write_text("Changed elsewhere")
        write = self.client.put(
            "/api/vault/file?profile=nova",
            headers=self.headers,
            json={**body, "text": "overwrite"},
        )
        self.assertEqual(write.status_code, 409)
        self.assertEqual(note.read_text(), "Changed elsewhere")
        for path in (
            "../outside.md",
            "/etc/passwd",
            ".git/config",
            "notes/.env",
            "notes/../../other",
        ):
            r = self.client.get(
                "/api/vault/file",
                params={"profile": "nova", "path": path},
                headers=self.headers,
            )
            self.assertEqual(r.status_code, 400, path)
        r = self.client.put(
            "/api/vault/file?profile=nova",
            headers=self.headers,
            json={"path": "notes/new.md", "revision": "", "text": "# New"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        r = self.client.put(
            "/api/vault/file?profile=nova",
            headers=self.headers,
            json={"path": "soul/SOUL.md", "revision": "", "text": "bad"},
        )
        self.assertEqual(r.status_code, 400)

    def test_symlink_cannot_escape_vault(self):
        outside = Path(self.tmp.name) / "outside.md"
        outside.write_text("not in vault")
        try:
            (self.vault / "escape.md").symlink_to(outside)
        except OSError:
            self.skipTest("Symlinks unavailable")
        r = self.client.get(
            "/api/vault/file?profile=nova&path=escape.md", headers=self.headers
        )
        self.assertEqual(r.status_code, 400)
