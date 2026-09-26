"""Safe vault history, profile boundaries, note conflicts, and navigable indexes."""

import dataclasses
import hashlib
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import companion_config as cc
import companion_local_context as local
import companion_vault as vault
import companion_vault_index as vi

from tests.support import WorkspaceFixture
from kit.app import vault as editor
from kit.app import vault_link_index as links

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

        hook = self.c.home / "hooks/companion-context.py"
        self.assertTrue(_runs_hook(f'"{sys.executable}" "{hook}"', hook))
        self.assertTrue(_runs_hook(f'python "{hook}"', hook))
        self.assertFalse(_runs_hook(f'python "{hook.with_name("other.py")}"', hook))
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


class VaultEditorTests(WorkspaceFixture):
    """Exact saves, portable file actions, and links through a synthetic Vault."""

    def setUp(self):
        super().setUp()
        (self.vault / "notes").mkdir()

    def read_note(self, relative):
        return self.client.get(
            "/api/vault/file",
            params={"profile": "nova", "path": relative},
            headers=self.headers,
        )

    def save_note(self, relative, text, revision):
        return self.client.put(
            "/api/vault/file",
            params={"profile": "nova"},
            headers=self.headers,
            json={"path": relative, "text": text, "revision": revision},
        )

    def backups(self, relative):
        folder = (
            self.vault
            / editor.BACKUPS
            / hashlib.sha256(relative.encode()).hexdigest()[:24]
        )
        return sorted(folder.glob("*.bak"))

    def revision(self, relative):
        return hashlib.sha256((self.vault / relative).read_bytes()).hexdigest()

    def test_saves_preserve_bytes_coalesce_autosaves_and_keep_external_versions(self):
        relative = "notes/raw.md"
        raw = "\ufeff---\r\ntitle: Ünïcødé ✨\r\n---\r\n:::custom\r\n\ttab\u00a0space  \r\nlast"
        path = self.vault / relative
        path.write_bytes(raw.encode())
        body = self.read_note(relative).json()
        self.assertEqual(body["text"], raw)
        self.assertEqual(body["revision"], hashlib.sha256(raw.encode()).hexdigest())
        revision = body["revision"]
        for i in range(4):
            edited = raw + str(i)
            saved = self.save_note(relative, edited, revision)
            self.assertEqual(saved.status_code, 200, saved.text)
            revision = saved.json()["revision"]
            self.assertEqual(path.read_bytes(), edited.encode())
        self.assertEqual(
            [p.read_bytes() for p in self.backups(relative)], [raw.encode()]
        )
        replacement = self.vault / "notes/replacement.tmp"
        replacement.write_bytes(b"external\r\n")
        os.replace(replacement, path)
        self.assertEqual(self.save_note(relative, "mine", revision).status_code, 409)
        self.assertEqual(path.read_bytes(), b"external\r\n")
        revision = self.read_note(relative).json()["revision"]
        self.assertEqual(self.save_note(relative, "mine", revision).status_code, 200)
        self.assertIn(b"external\r\n", [p.read_bytes() for p in self.backups(relative)])
        self.assertEqual(self.save_note("notes/copy.md", "mine", "").status_code, 200)
        self.assertEqual(
            self.save_note("notes/copy.md", "overwrite", "").status_code, 409
        )

    def test_backups_are_bounded_per_note_and_hidden_from_browsing(self):
        relative = "notes/history.md"
        for i in range(editor.BACKUP_KEEP + 3):
            editor.backup(self.c, relative, str(i).encode(), now=1700000000 + i * 601)
        kept = self.backups(relative)
        self.assertEqual(len(kept), editor.BACKUP_KEEP)
        self.assertEqual(kept[0].read_bytes(), b"3")
        self.assertEqual(kept[-1].read_bytes(), str(editor.BACKUP_KEEP + 2).encode())
        names = [row["name"] for row in self.get("/api/vault").json()["entries"]]
        self.assertNotIn(editor.BACKUPS, names)
        self.assertEqual(
            self.read_note(editor.BACKUPS + "/hidden.bak").status_code, 400
        )

    def test_saves_and_file_actions_refuse_symlink_paths(self):
        real = self.vault / "real"
        real.mkdir()
        note(real, "a.md", "original")
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()
        try:
            (self.vault / "linked").symlink_to(real, target_is_directory=True)
            (self.vault / editor.BACKUPS).symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Symlinks unavailable")
        with self.assertRaises(ValueError):
            editor.mkdir(self.c, "linked/new")
        with self.assertRaises(ValueError):
            editor.duplicate(self.c, "linked/a.md", self.revision("real/a.md"))
        with self.assertRaises(ValueError):
            editor.move(self.c, "real/a.md", "linked/b.md", self.revision("real/a.md"))
        self.assertEqual(
            self.save_note(
                "real/a.md", "overwrite", self.revision("real/a.md")
            ).status_code,
            400,
        )
        self.assertEqual(self.save_note("notes/new.md", "fresh", "").status_code, 400)
        self.assertEqual((real / "a.md").read_text(), "original")
        self.assertEqual(list(outside.iterdir()), [])

    def test_file_actions_require_current_revisions_and_safe_destinations(self):
        note(self.vault, "notes/a.md", "original")
        revision = self.revision("notes/a.md")
        with self.assertRaises(ValueError):
            editor.move(self.c, "notes/a.md", "notes/b.md")
        with self.assertRaises(FileExistsError):
            editor.move(self.c, "notes/a.md", "notes/b.md", "stale")
        for destination in (
            "SOUL.md",
            "notes/CON.md",
            "notes/trailing.",
            "../escape.md",
        ):
            with self.assertRaises(ValueError, msg=destination):
                editor.move(self.c, "notes/a.md", destination, revision)
        upper = self.vault / "notes/A.md"
        if not upper.exists():
            upper.write_text("another file", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                editor.move(self.c, "notes/a.md", "notes/A.md", revision)
            self.assertEqual(upper.read_text(), "another file")
            upper.unlink()
        editor.move(self.c, "notes/a.md", "notes/A.md", revision)
        self.assertIn("A.md", {p.name for p in upper.parent.iterdir()})
        self.assertEqual(upper.read_text(), "original")
        replace = os.replace
        calls = 0

        def fail_second_move(source, destination):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("synthetic rename failure")
            return replace(source, destination)

        with patch.object(editor.os, "replace", side_effect=fail_second_move):
            with self.assertRaises(OSError):
                editor.move(self.c, "notes/A.md", "notes/a.md", revision)
        self.assertEqual(upper.read_text(), "original")
        self.assertFalse(list(upper.parent.glob(".vault-move-*")))

    def test_duplicate_preserves_text_and_binary_bytes_without_collisions(self):
        for relative, raw in (
            ("notes/raw.md", b"\xef\xbb\xbf# A\r\nbody\r\n"),
            ("notes/image.png", bytes(range(256))),
        ):
            (self.vault / relative).write_bytes(raw)
            revision = self.revision(relative)
            with self.assertRaises(FileExistsError):
                editor.duplicate(self.c, relative, "stale")
            first = editor.duplicate(self.c, relative, revision)["duplicated"]
            second = editor.duplicate(self.c, relative, revision)["duplicated"]
            self.assertNotEqual(first, second)
            self.assertEqual((self.vault / first).read_bytes(), raw)
            self.assertEqual((self.vault / second).read_bytes(), raw)
            self.assertEqual((self.vault / relative).read_bytes(), raw)
        note(self.vault, "SOUL.md", "identity")
        with self.assertRaises(ValueError):
            editor.duplicate(self.c, "SOUL.md", self.revision("SOUL.md"))

    def test_note_move_rewrites_both_directions_and_preserves_recovery_bytes(self):
        (self.vault / "notes/Target.md").write_bytes(b"[other](Other.md)\r\n")
        note(self.vault, "notes/Other.md", "# Other")
        citing = "[[Target#Heading|label]] [relative](Target.md)\r\n`[[Target]]`\r\n```\r\n[[Target]]\r\n```\r\n"
        (self.vault / "notes/Citing.md").write_bytes(citing.encode())
        result = editor.move(
            self.c,
            "notes/Target.md",
            "archive/Renamed.md",
            self.revision("notes/Target.md"),
        )
        self.assertEqual(
            result["links"]["updated"], [{"path": "notes/Citing.md", "links": 2}]
        )
        self.assertEqual(result["links"]["own_links_updated"], 1)
        self.assertEqual(
            (self.vault / "archive/Renamed.md").read_bytes(),
            b"[other](../notes/Other.md)\r\n",
        )
        expected = citing.replace("[[Target#Heading", "[[Renamed#Heading").replace(
            "(Target.md)", "(../archive/Renamed.md)"
        )
        self.assertEqual(
            (self.vault / "notes/Citing.md").read_bytes(), expected.encode()
        )
        self.assertIn(
            citing.encode(), [p.read_bytes() for p in self.backups("notes/Citing.md")]
        )

    def test_ambiguous_links_are_reported_without_guessing_or_rewriting(self):
        note(
            self.vault,
            "a/Note.md",
            "---\naliases: [Alias]\ntags: [project]\n---\n# First\ntext ^block",
        )
        note(self.vault, "b/Note.md", "# Second")
        note(self.vault, "Citing.md", "[[Note]] and `[[Fake]]`\n```\n[[Fenced]]\n```")
        entries, incomplete = links.build(self.c)
        self.assertFalse(incomplete)
        parsed = entries["a/Note.md"]
        self.assertEqual(parsed["aliases"], ["Alias"])
        self.assertEqual(parsed["tags"], ["project"])
        self.assertEqual(parsed["block_ids"], ["block"])
        self.assertEqual(
            [row["target"] for row in entries["Citing.md"]["outbound"]], ["Note"]
        )
        lookup = links.build_lookup(entries)
        self.assertEqual(links.resolve_wiki("Alias", lookup), ["a/Note.md"])
        self.assertEqual(
            set(links.resolve_wiki("Note", lookup)), {"a/Note.md", "b/Note.md"}
        )
        malformed = links.parse_note("---\ntitle: [broken\n---\n# Fallback")
        self.assertTrue(malformed["properties"]["_malformed"])
        self.assertEqual(malformed["title"], "Fallback")
        result = editor.move(
            self.c, "a/Note.md", "a/Renamed.md", self.revision("a/Note.md")
        )
        self.assertEqual(result["links"]["updated"], [])
        self.assertEqual(result["links"]["ambiguous"][0]["path"], "Citing.md")
        self.assertTrue((self.vault / "Citing.md").read_text().startswith("[[Note]]"))

    def test_link_index_reuses_unchanged_notes_and_tracks_changes_and_removal(self):
        note(self.vault, "notes/a.md", "# A")
        note(self.vault, ".private/hidden.md", "secret")
        note(self.vault, "api_key.md", "secret")
        entries, _ = links.build(self.c)
        self.assertIn("notes/a.md", entries)
        self.assertNotIn(".private/hidden.md", entries)
        self.assertNotIn("api_key.md", entries)
        with patch.object(links, "parse_note", wraps=links.parse_note) as parse:
            links.build(self.c)
            parse.assert_not_called()
            (self.vault / "notes/a.md").write_text("# A changed", encoding="utf-8")
            changed, _ = links.build(self.c)
            self.assertEqual(parse.call_count, 1)
        self.assertEqual(changed["notes/a.md"]["title"], "A changed")
        (self.vault / "notes/a.md").unlink()
        self.assertNotIn("notes/a.md", links.build(self.c)[0])

    def test_file_action_routes_enforce_auth_conflicts_and_profile_isolation(self):
        unauthenticated = self.client.post(
            "/api/vault/mkdir?profile=nova", json={"path": "forbidden"}
        )
        self.assertEqual(unauthenticated.status_code, 401)
        self.assertFalse((self.vault / "forbidden").exists())
        self.assertEqual(
            self.post("/api/vault/mkdir", {"path": "notes/new"}).status_code, 200
        )
        self.assertEqual(
            self.post("/api/vault/mkdir", {"path": "notes/new"}).status_code, 409
        )
        self.assertEqual(
            self.post("/api/vault/mkdir", {"path": "CON"}).status_code, 400
        )
        self.assertEqual(self.post("/api/vault/mkdir", {}).status_code, 400)
        note(self.vault, "notes/a.md", "# A")
        self.assertEqual(
            self.post(
                "/api/vault/duplicate", {"path": "notes/a.md", "revision": "stale"}
            ).status_code,
            409,
        )
        duplicate = self.post(
            "/api/vault/duplicate",
            {"path": "notes/a.md", "revision": self.revision("notes/a.md")},
        )
        self.assertEqual(duplicate.status_code, 200, duplicate.text)
        moved = self.post(
            "/api/vault/move",
            {
                "path": "notes/a.md",
                "dest": "notes/b.md",
                "revision": self.revision("notes/a.md"),
            },
        )
        self.assertEqual(moved.status_code, 200, moved.text)
        self.assertEqual(self.read_note("notes/b.md").json()["text"], "# A")
        other_vault = Path(self.tmp.name) / "rowan-vault"
        other_vault.mkdir()
        dataclasses.replace(self.other, vault=other_vault).save()
        created = self.post("/api/vault/mkdir", {"path": "rowan-only"}, profile="rowan")
        self.assertEqual(created.status_code, 200, created.text)
        self.assertTrue((other_vault / "rowan-only").is_dir())
        self.assertFalse((self.vault / "rowan-only").exists())

    def test_link_routes_share_resolution_boundaries_and_bounded_embeds(self):
        note(self.vault, "Target.md", "# Target\n## Keep\nkept\n## Drop\ndropped")
        note(self.vault, "notes/Citing.md", "[[Target]]")
        note(self.vault, "duplicate/Target.md", "# Other target")

        def query(route, **params):
            return self.client.get(
                "/api/vault/links/" + route,
                params={"profile": "nova", **params},
                headers=self.headers,
            )

        resolved = query("resolve", source="notes/Citing.md", target="Target").json()
        self.assertEqual(
            set(resolved["candidates"]), {"Target.md", "duplicate/Target.md"}
        )
        backlinks = query("backlinks", path="Target.md").json()
        self.assertEqual(backlinks["linked"], [])
        self.assertEqual(backlinks["ambiguous"][0]["path"], "notes/Citing.md")
        ambiguous = query(
            "embed-note", source="notes/Citing.md", target="Target"
        ).json()
        self.assertFalse(ambiguous["resolved"])
        (self.vault / "duplicate/Target.md").unlink()
        embedded = query(
            "embed-note", source="notes/Citing.md", target="Target", heading="Keep"
        ).json()
        self.assertIn("kept", embedded["text"])
        self.assertNotIn("dropped", embedded["text"])
        note(self.vault, "Large.md", "x" * (links.EMBED_NOTE_CHAR_LIMIT + 10))
        bounded = query("embed-note", source="notes/Citing.md", target="Large").json()
        self.assertTrue(bounded["truncated"])
        self.assertEqual(len(bounded["text"]), links.EMBED_NOTE_CHAR_LIMIT)
        self.assertEqual(query("backlinks", path="../outside.md").status_code, 400)
        self.assertEqual(
            query("embed-image", source="notes/Citing.md", target="Large").status_code,
            400,
        )
        raw = b"\x89PNG\r\n\x1a\nFAKE"
        (self.vault / "photo.png").write_bytes(raw)
        image = query("embed-image", source="notes/Citing.md", target="photo.png")
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image.headers["content-type"], "image/png")
        self.assertEqual(image.content, raw)
