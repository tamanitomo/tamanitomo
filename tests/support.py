"""Shared synthetic API fixtures; this module contains no tests."""

import json
import os
import pathlib
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import companion_config as cc
import companion_render as cr
from fastapi.testclient import TestClient

from kit.app.server import build

ROOT = Path(__file__).resolve().parents[1]


class WorkspaceFixture(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "hermes"
        self.vault = Path(self.tmp.name) / "vault"
        self.root.mkdir()
        self.vault.mkdir()
        self.c = cc.Companion(
            agent="Nova",
            human="Alex",
            profile="nova",
            hermes_root=self.root,
            vault=self.vault,
            soul_in_vault=False,
            context_mode="fixed",
        )
        self.c.home.mkdir(parents=True)
        self.c.life.mkdir(parents=True)
        self.c.save()
        self.c.soul.write_text(
            cr.render_template("SOUL.md.tmpl", cr.mapping_for(self.c, "warm", "none"))
        )
        self.other = cc.Companion(
            agent="Rowan",
            profile="rowan",
            hermes_root=self.root,
            vault=self.vault,
            context_mode="fixed",
        )
        self.other.home.mkdir(parents=True)
        self.other.save()
        self.app = build(
            self.root, token="workspace-token", state_dir=Path(self.tmp.name) / "state"
        )
        self.client = TestClient(self.app)
        self.headers = {"x-companion-token": "workspace-token"}
        self.fake = patch.dict(
            os.environ,
            {
                "COMPANION_HERMES_COMMAND": json.dumps(
                    [sys.executable, str(ROOT / "tests/fake_hermes.py")]
                )
            },
        )
        self.fake.start()
        self.addCleanup(self.fake.stop)
        self.addCleanup(self.app.state.operations.pool.shutdown, wait=True)
        self.addCleanup(self.app.state.dashboards.close)
        self.addCleanup(self.client.close)

    def get(self, path, profile="nova"):
        return self.client.get(path, params={"profile": profile}, headers=self.headers)

    def post(self, path, data=None, profile="nova"):
        return self.client.post(
            path, params={"profile": profile}, headers=self.headers, json=data or {}
        )

    def wait(self, response, profile="nova"):
        self.assertEqual(response.status_code, 200, response.text)
        ident = response.json()["id"]
        for _ in range(1000):
            row = self.get("/api/operations/" + ident, profile).json()
            if row["status"] != "running":
                return row
            time.sleep(0.01)
        self.fail("Operation did not finish")


class AppFixture(unittest.TestCase):

    def setUp(self):
        from kit.app.server import build

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        self.c = cc.Companion(
            agent="Nova",
            human="Alex",
            hermes_root=root / "h",
            vault=root / "v",
            timezone="UTC",
            soul_in_vault=False,
        )
        self.c.home.mkdir(parents=True, exist_ok=True)
        self.c.life.mkdir(parents=True, exist_ok=True)
        self.c.soul.write_text(
            cr.render_template("SOUL.md.tmpl", cr.mapping_for(self.c, "warm", "none")),
            encoding="utf-8",
        )
        self.c.save()
        self.client = TestClient(build(home=self.c.home))
        self.addCleanup(self.client.app.state.operations.pool.shutdown, wait=True)
        self.addCleanup(self.client.app.state.dashboards.close)
        self.addCleanup(self.client.close)
