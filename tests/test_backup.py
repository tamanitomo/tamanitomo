"""Recovery bundles preserve data in isolated homes and never activate delivery."""

from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

import yaml
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

import companion_backup as backup
import companion_config as cc
import companion_outreach as outreach


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.c = cc.Companion(
            agent="Nova",
            human="Robin",
            profile="nova",
            timezone="UTC",
            hermes_root=self.base / "original",
            vault=self.base / "life",
            cron_active=True,
            outreach="updates_only",
            remote_pin="7319",
        )
        self.c.save()
        self.c.canonical_soul.parent.mkdir(parents=True, exist_ok=True)
        self.c.canonical_soul.write_text(
            "Nova's authored identity.\n", encoding="utf-8"
        )
        try:
            self.c.soul.symlink_to(self.c.canonical_soul)
            self.linked = True
        except OSError:
            self.c.soul.write_text(self.c.canonical_soul.read_text(), encoding="utf-8")
            self.linked = False
        self.c.life.mkdir(parents=True)
        (self.c.life / "events.jsonl").write_text(
            '{"fiction":"painted a scene"}\n', encoding="utf-8"
        )
        (self.c.home / "config.yaml").write_text(
            yaml.safe_dump(
                {
                    "model": {"api_key": "model-secret", "api_key_env": "PROVIDER_KEY"},
                    "oauth": {"accessToken": "oauth-secret"},
                    "headers": {"Authorization": "Bearer header-secret"},
                    "path": str(self.c.soul),
                    "platforms": {"telegram": {"enabled": True}},
                }
            ),
            encoding="utf-8",
        )
        (self.c.home / ".env").write_text("PROVIDER_KEY=env-secret\n", encoding="utf-8")
        (self.c.home / "auth.json").write_text(
            '{"access_token":"auth-secret"}', encoding="utf-8"
        )
        (self.c.hermes_root / "config.yaml").write_text(
            "model:\n  api_key: root-secret\n", encoding="utf-8"
        )
        cron = self.c.home / "cron"
        cron.mkdir()
        (cron / "jobs.json").write_text(
            json.dumps(
                {
                    "jobs": [
                        {
                            "id": "pulse",
                            "enabled": True,
                            "paused": False,
                            "next_run_at": "2026-10-10T12:00:00Z",
                            "prompt": "Read " + str(self.c.canonical_soul),
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        (cron / "pulse.py").write_text(
            "HOME = " + repr(str(self.c.home)) + "\n", encoding="utf-8"
        )
        self.archive = self.base / "recovery.zip"

    def export(self, **kwargs):
        return backup.export(self.c, self.archive, **kwargs)

    def restore(self):
        result = backup.restore(
            self.archive, self.base / "restored", self.base / "restored-life"
        )
        return result, cc.load(Path(result["home"]))

    def database(self, shared=False, hardlink=False):
        path = self.c.hermes_root / "state.db" if shared else self.c.home / "state.db"
        db = sqlite3.connect(path)
        self.addCleanup(db.close)
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
            CREATE TABLE sessions(id TEXT PRIMARY KEY, source TEXT, started_at REAL,
                profile_name TEXT, parent_session_id TEXT, end_reason TEXT);
            CREATE TABLE messages(id INTEGER PRIMARY KEY,session_id TEXT,role TEXT,
                content TEXT,timestamp REAL,active INTEGER,compacted INTEGER);
            CREATE VIRTUAL TABLE messages_fts USING fts5(content);
            INSERT INTO sessions VALUES ('old','cli',1,'nova',NULL,'compression');
            INSERT INTO sessions VALUES ('new','cli',3,'nova','old',NULL);
            INSERT INTO sessions VALUES ('peer','cli',1,'other',NULL,NULL);
            INSERT INTO messages VALUES (1,'old','user','WAL_ONLY_ORIGINAL',2,0,1);
            INSERT INTO messages VALUES (2,'new','user','WAL_ONLY_CURRENT',4,1,0);
            INSERT INTO messages VALUES (3,'peer','user','PEER_PRIVATE_TRANSCRIPT',2,1,0);
            INSERT INTO messages_fts(rowid,content) SELECT id,content FROM messages;
        """)
        db.commit()
        if shared:
            try:
                if hardlink:
                    import os

                    os.link(path, self.c.home / "state.db")
                else:
                    (self.c.home / "state.db").symlink_to(path)
            except OSError:
                self.skipTest("Links unavailable on this host")
        return db, path

    def test_profile_vault_and_wal_roundtrip_is_paused_and_rebased(self):
        original, source = self.database()
        self.assertTrue(source.with_name("state.db-wal").exists())
        self.assertNotIn(b"WAL_ONLY_CURRENT", source.read_bytes())
        manifest = self.export()
        result, restored = self.restore()
        self.assertEqual(restored.profile, "nova")
        self.assertEqual(restored.vault, self.base / "restored-life")
        self.assertEqual(restored.soul.read_text(), "Nova's authored identity.\n")
        self.assertEqual(
            (restored.life / "events.jsonl").read_bytes(),
            (self.c.life / "events.jsonl").read_bytes(),
        )
        self.assertFalse(restored.cron_active)
        self.assertEqual(restored.outreach, "never")
        self.assertFalse(outreach.decide(restored)["allowed"])
        jobs = json.loads((restored.home / "cron/jobs.json").read_text())["jobs"]
        self.assertEqual(
            (jobs[0]["enabled"], jobs[0]["paused"], jobs[0]["next_run_at"]),
            (False, True, None),
        )
        self.assertIn(str(restored.canonical_soul), jobs[0]["prompt"])
        self.assertIn(str(restored.home), (restored.home / "cron/pulse.py").read_text())
        config = yaml.safe_load((restored.home / "config.yaml").read_text())
        self.assertEqual(config["path"], str(restored.soul))
        self.assertNotIn("platforms", config)
        self.assertTrue(
            json.loads((restored.home / "recovery.json").read_text())["review_required"]
        )
        self.assertEqual(
            original.execute("SELECT count(*) FROM sessions").fetchone()[0], 3
        )
        with closing(sqlite3.connect(restored.home / "state.db")) as db:
            self.assertEqual(
                db.execute(
                    "SELECT id,active,compacted FROM messages ORDER BY id"
                ).fetchall(),
                [(1, 0, 1), (2, 1, 0)],
            )
            self.assertEqual(
                db.execute(
                    "SELECT parent_session_id FROM sessions WHERE id='new'"
                ).fetchone()[0],
                "old",
            )
            self.assertEqual(
                db.execute(
                    "SELECT count(*) FROM messages_fts WHERE messages_fts MATCH 'PEER_PRIVATE_TRANSCRIPT'"
                ).fetchone()[0],
                0,
            )
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertNotIn(
            b"PEER_PRIVATE_TRANSCRIPT", (restored.home / "state.db").read_bytes()
        )
        self.assertEqual(manifest["transcript"]["other_sessions_excluded"], 1)
        self.assertEqual(result["agent"], "Nova")

    def test_default_export_excludes_credentials_and_redacts_config_secrets(self):
        manifest = self.export()
        with zipfile.ZipFile(self.archive) as archive:
            self.assertNotIn("home/.env", archive.namelist())
            self.assertNotIn("home/auth.json", archive.namelist())
            text = "\n".join(archive.read(name).decode() for name in archive.namelist())
            for secret in (
                "model-secret",
                "oauth-secret",
                "header-secret",
                "root-secret",
                "env-secret",
                "auth-secret",
                "7319",
            ):
                self.assertNotIn(secret, text)
            self.assertIn("PROVIDER_KEY", text)
        self.assertFalse(manifest["credentials_included"])

    def test_credentials_require_explicit_export_and_remote_pin_still_resets(self):
        self.export(include_credentials=True)
        with zipfile.ZipFile(self.archive) as archive:
            self.assertIn(b"env-secret", archive.read("home/.env"))
            self.assertIn(b"model-secret", archive.read("home/config.yaml"))
        _, restored = self.restore()
        self.assertEqual(restored.remote_pin, "")
        self.assertIn("env-secret", (restored.home / ".env").read_text())

    def test_shared_transcript_source_preserves_selected_history(self):
        self.database(shared=True)
        manifest = self.export()
        self.assertTrue(manifest["transcript"]["shared_source"])
        _, restored = self.restore()
        self.assertFalse((restored.home / "state.db").is_symlink())
        with closing(sqlite3.connect(restored.home / "state.db")) as db:
            self.assertEqual(
                db.execute("SELECT id FROM sessions ORDER BY id").fetchall(),
                [("new",), ("old",)],
            )

    def test_hardlinked_transcript_is_scoped_too(self):
        self.database(shared=True, hardlink=True)
        manifest = self.export()
        self.assertTrue(manifest["transcript"]["shared_source"])
        self.assertEqual(manifest["transcript"]["sessions_retained"], 2)
        _, restored = self.restore()
        with closing(sqlite3.connect(restored.home / "state.db")) as db:
            self.assertEqual(
                db.execute("SELECT content FROM messages WHERE id=2").fetchone()[0],
                "WAL_ONLY_CURRENT",
            )

    def test_cross_profile_compression_ancestry_fails_without_publishing(self):
        original, _ = self.database(shared=True)
        original.execute("UPDATE sessions SET parent_session_id='peer' WHERE id='new'")
        original.commit()
        with self.assertRaisesRegex(ValueError, "ownership boundaries"):
            self.export()
        self.assertFalse(self.archive.exists())

    def test_restored_identity_alias_tracks_canonical_edits(self):
        if not self.linked:
            self.skipTest("Symlinks unavailable")
        self.export()
        _, restored = self.restore()
        self.assertTrue(restored.soul_linked)
        restored.canonical_soul.write_text(
            "Updated authored identity.", encoding="utf-8"
        )
        self.assertEqual(restored.soul.read_text(), "Updated authored identity.")

    def test_external_linked_memory_is_materialized_and_preserved(self):
        external = self.base / "shared-memory"
        external.mkdir()
        (external / "USER.md").write_text("Robin likes tea.", encoding="utf-8")
        try:
            (self.c.home / "memories").symlink_to(external, target_is_directory=True)
        except OSError:
            self.skipTest("Symlinks unavailable")
        manifest = self.export()
        self.assertIn("home/memories", manifest["materialized_links"])
        _, restored = self.restore()
        self.assertEqual(
            (restored.home / "memories/USER.md").read_text(), "Robin likes tea."
        )

    def rewrite(self, transform):
        with zipfile.ZipFile(self.archive) as archive:
            data = {name: archive.read(name) for name in archive.namelist()}
        manifest = json.loads(data.pop("manifest.json"))
        transform(manifest, data)
        target = self.base / "modified.zip"
        with zipfile.ZipFile(target, "w") as archive:
            archive.writestr("manifest.json", json.dumps(manifest))
            for name, content in data.items():
                archive.writestr(name, content)
        return target

    def test_corruption_fails_before_destination_directories_are_created(self):
        self.export()

        def corrupt(manifest, data):
            data["home/config.yaml"] += b"changed"

        bad = self.rewrite(corrupt)
        root, vault = self.base / "new-root", self.base / "new-vault"
        with self.assertRaises(ValueError):
            backup.restore(bad, root, vault)
        self.assertFalse(root.exists())
        self.assertFalse(vault.exists())

    def test_traversal_case_collisions_control_links_and_limits_fail_closed(self):
        self.export()

        def traversal(manifest, data):
            manifest["files"]["home/../../escape"] = manifest["files"].pop(
                "home/config.yaml"
            )
            data["home/../../escape"] = data.pop("home/config.yaml")

        def duplicate(manifest, data):
            manifest["links"]["HOME/CONFIG.YAML"] = "home/config.yaml"

        def control_link(manifest, data):
            manifest["links"]["home/cron/other.py"] = "home/config.yaml"

        for mutate in (traversal, duplicate, control_link):
            with self.subTest(mutate=mutate.__name__):
                with self.assertRaises(ValueError):
                    backup.inspect(self.rewrite(mutate))
        with patch.object(backup, "MAX_BYTES", 10):
            with self.assertRaises(ValueError):
                backup.inspect(self.archive)
        with patch.object(backup, "MAX_FILES", 1):
            with self.assertRaises(ValueError):
                backup.inspect(self.archive)

    def test_existing_destinations_and_archive_are_never_overwritten(self):
        self.export()
        before = self.archive.read_bytes()
        with self.assertRaises(FileExistsError):
            self.export()
        self.assertEqual(self.archive.read_bytes(), before)
        with self.assertRaises(FileExistsError):
            backup.restore(self.archive, self.c.hermes_root, self.base / "unused")
        self.assertFalse((self.base / "unused").exists())

    def test_rebase_does_not_replace_its_own_new_paths(self):
        mappings = [
            ("/old/profiles/nova", "/old-new/profiles/nova"),
            ("/old", "/old-new"),
        ]
        self.assertEqual(
            backup._replace("/old/profiles/nova/memories /old/config.yaml", mappings),
            "/old-new/profiles/nova/memories /old-new/config.yaml",
        )

    def api(self):
        from kit.app.backups import register

        app = FastAPI()
        app.state.operations = SimpleNamespace(directory=self.base / "app/operations")
        app.state.runtimes = {}
        app.state.write_locks = {}
        app.state.linked_installations_file = self.base / "linked.json"
        selected = ["nova"]

        @app.exception_handler(ValueError)
        async def invalid(request, exc):
            return JSONResponse({"detail": str(exc)}, status_code=400)

        register(
            app,
            lambda: (SimpleNamespace(root=self.c.hermes_root), selected[0]),
            lambda: self.c,
        )
        client = TestClient(app)
        self.addCleanup(client.close)
        return client, selected

    def test_api_preview_is_profile_scoped_and_restore_registers_a_new_home(self):
        self.export()
        client, selected = self.api()
        response = client.post("/api/backup/preview", content=self.archive.read_bytes())
        self.assertEqual(response.status_code, 200, response.text)
        payload = {
            "id": response.json()["id"],
            "root": str(self.base / "api-root"),
            "vault": str(self.base / "api-vault"),
        }
        selected[0] = "other"
        self.assertEqual(
            client.post("/api/backup/restore", json=payload).status_code, 404
        )
        self.assertFalse((self.base / "api-root").exists())
        selected[0] = "nova"
        response = client.post("/api/backup/restore", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        restored = cc.load(Path(response.json()["home"]))
        self.assertEqual(restored.outreach, "never")
        self.assertIn(
            response.json()["installation"],
            json.loads((self.base / "linked.json").read_text()),
        )
        self.assertEqual(list((self.base / "app/recovery-uploads").glob("*")), [])

    def test_api_rejects_invalid_upload_and_removes_its_private_files(self):
        client, _ = self.api()
        response = client.post("/api/backup/preview", content=b"not a recovery bundle")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(list((self.base / "app/recovery-uploads").glob("*")), [])

    def test_api_reports_successful_restore_when_registration_write_fails(self):
        from kit.app import backups

        self.export()
        client, _ = self.api()
        preview = client.post(
            "/api/backup/preview", content=self.archive.read_bytes()
        ).json()
        payload = {
            "id": preview["id"],
            "root": str(self.base / "unlinked-root"),
            "vault": str(self.base / "unlinked-vault"),
        }
        with patch.object(
            backups, "atomic_write", side_effect=OSError("registry is read-only")
        ):
            response = client.post("/api/backup/restore", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertFalse(result["linked"])
        self.assertIsNone(result["installation"])
        self.assertIn("restored successfully", result["note"])
        self.assertIn("do not restore", result["note"])
        self.assertIn("registry is read-only", result["registration_error"])
        restored = cc.load(Path(result["home"]))
        self.assertEqual(restored.soul.read_text(), self.c.soul.read_text())
        self.assertEqual(restored.outreach, "never")
        self.assertFalse(restored.cron_active)
        self.assertEqual(client.app.state.runtimes, {})
        self.assertEqual(client.app.state.write_locks, {})
        self.assertFalse((self.base / "linked.json").exists())
        self.assertEqual(list((self.base / "app/recovery-uploads").glob("*")), [])
        with patch.object(backup, "restore") as restore_again:
            repeated = client.post("/api/backup/restore", json=payload)
        self.assertEqual(repeated.status_code, 400)
        restore_again.assert_not_called()

    def test_api_runtime_registration_failure_keeps_verified_restored_files(self):
        self.export()
        client, _ = self.api()
        preview = client.post(
            "/api/backup/preview", content=self.archive.read_bytes()
        ).json()
        with patch(
            "kit.app.runtime.Runtime", side_effect=ValueError("Runtime unavailable")
        ):
            response = client.post(
                "/api/backup/restore",
                json={
                    "id": preview["id"],
                    "root": str(self.base / "runtime-root"),
                    "vault": str(self.base / "runtime-vault"),
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["linked"])
        self.assertTrue((Path(response.json()["home"]) / "SOUL.md").is_file())
        self.assertFalse((self.base / "linked.json").exists())

    def test_concurrent_registrations_merge_the_shared_registry(self):
        from kit.app import runtime

        self.export()
        clients = [self.api()[0], self.api()[0]]
        payloads = []
        for index, client in enumerate(clients):
            preview = client.post(
                "/api/backup/preview", content=self.archive.read_bytes()
            ).json()
            payloads.append(
                {
                    "id": preview["id"],
                    "root": str(self.base / f"concurrent-root-{index}"),
                    "vault": str(self.base / f"concurrent-vault-{index}"),
                }
            )
        existing = {"linked-111111111111": str(self.base / "existing-installation")}
        (self.base / "linked.json").write_text(json.dumps(existing), encoding="utf-8")
        original = runtime.Runtime
        ready = threading.Barrier(2)

        def both_restored(root):
            result = original(root)
            ready.wait(timeout=5)
            return result

        with patch.object(runtime, "Runtime", side_effect=both_restored):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [
                    pool.submit(client.post, "/api/backup/restore", json=payload)
                    for client, payload in zip(clients, payloads)
                ]
                responses = [future.result(timeout=10) for future in futures]
        for response in responses:
            self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue(response.json()["linked"], response.text)
        saved = json.loads((self.base / "linked.json").read_text())
        self.assertEqual(len(saved), 3)
        self.assertEqual(saved["linked-111111111111"], existing["linked-111111111111"])
        for response in responses:
            self.assertEqual(
                saved[response.json()["installation"]], response.json()["root"]
            )
        self.assertTrue((self.base / "linked.lock").exists())

    def test_api_export_records_verified_status_without_sending_or_starting_jobs(self):
        client, _ = self.api()
        response = client.post(
            "/api/backup/export", json={"include_credentials": "true"}
        )
        self.assertEqual(response.status_code, 200, response.text)
        import io

        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            self.assertNotIn("home/.env", archive.namelist())
        status = client.get("/api/backup/status").json()
        self.assertTrue(status["verified_at"])
        self.assertFalse(status["credentials_included"])


if __name__ == "__main__":
    unittest.main()
