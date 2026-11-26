"""A local conversation follows the model plan instead of the model it started on.

Hermes 0.23 freezes a local conversation's launch policy when it begins, so `--resume`
kept the workspace chat (and any app client that keeps one conversation going) on that
model after a new plan, or on an exhausted account's fallbacks.
"""

import json
import sqlite3
import subprocess
import time

import companion_config as cc
import companion_transcript as transcript
import pytest
import yaml
from fastapi.testclient import TestClient

from kit.app import runtime
from kit.app.server import build


def policy(model, provider, default=None):
    config = {"model": {"default": default or model, "provider": provider}}
    return json.dumps(
        {
            "session_id": "x",
            "policy": {"model": model, "config_json": json.dumps(config), "source": "oneshot"},
        }
    )


@pytest.fixture
def workspace(tmp_path):
    c = cc.Companion(
        agent="Nova",
        human="Robin",
        hermes_root=tmp_path / "home",
        vault=tmp_path / "vault",
        timezone="UTC",
        profile="nova",
    )
    c.home.mkdir(parents=True)
    c.save()
    for name in ("web", "older", "unrecorded"):
        runtime.note_workspace_session(c, name)
    (c.home / "config.yaml").write_text(
        yaml.safe_dump({"model": {"default": "model-b", "provider": "provider-b"}}),
        encoding="utf-8",
    )
    with sqlite3.connect(c.home / "state.db") as db:
        db.executescript(
            """
            CREATE TABLE sessions (id TEXT PRIMARY KEY, source TEXT, started_at REAL,
                profile_name TEXT, user_id TEXT, chat_id TEXT, chat_type TEXT);
            CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT,
                content TEXT, timestamp REAL, platform_message_id TEXT, display_kind TEXT,
                _compressed_summary INTEGER DEFAULT 0, active INTEGER DEFAULT 1,
                compacted INTEGER DEFAULT 0);
            CREATE TABLE state_meta (key TEXT PRIMARY KEY, value TEXT);
            """
        )
        db.executemany(
            "INSERT INTO sessions VALUES (?,?,?,?,?,?,?)",
            [
                ("web", "oneshot", 1, "nova", "uid:1000", "web", "dm"),
                ("older", "oneshot", 2, "nova", "uid:1000", "older", "dm"),
                ("unrecorded", "oneshot", 3, "nova", "uid:1000", "unrecorded", "dm"),
                ("other-profile", "oneshot", 4, "rowan", "uid:1000", "other-profile", "dm"),
            ],
        )
        db.executemany(
            "INSERT INTO state_meta VALUES (?,?)",
            [
                (transcript.LOCAL_POLICY_PREFIX + "web", policy("model-b", "provider-b")),
                (transcript.LOCAL_POLICY_PREFIX + "older", policy("model-a", "provider-a")),
                (transcript.LOCAL_POLICY_PREFIX + "other-profile", policy("model-a", "provider-a")),
            ],
        )
    app = build(home=c.home, state_dir=tmp_path / "app")
    with TestClient(app) as client:
        yield c, client
    app.state.operations.pool.shutdown(wait=True)
    app.state.dashboards.close()


def locked(c, session):
    return transcript.owner_evidence(c, lambda view: view.locked_route(session))


def test_reads_the_route_hermes_froze_for_this_profile_only(workspace):
    c, _ = workspace
    assert locked(c, "older") == {"model": "model-a", "provider": "provider-a"}
    assert locked(c, "unrecorded") is None
    assert locked(c, "other-profile") is None
    assert locked(c, "missing") is None


def test_a_store_without_policies_or_with_a_broken_one_reads_as_unknown(workspace):
    c, _ = workspace
    with sqlite3.connect(c.home / "state.db") as db:
        db.execute(
            "UPDATE state_meta SET value='{not json' WHERE key=?",
            (transcript.LOCAL_POLICY_PREFIX + "older",),
        )
    assert locked(c, "older") is None
    with sqlite3.connect(c.home / "state.db") as db:
        db.execute("DROP TABLE state_meta")
    assert locked(c, "web") is None


@pytest.mark.parametrize(
    "cfg, expected",
    [
        ({"model": {"default": "model-b", "provider": "provider-b"}}, None),
        ({"model": {"default": "provider-b/model-b", "provider": "provider-b"}}, None),
        ({"model": {"default": "model-b", "provider": "auto"}}, None),
        ({"model": "model-b"}, None),
        ({"model": {"default": "model-c", "provider": "provider-b"}}, "model-c"),
        ({"model": {"default": "model-b", "provider": "provider-c"}}, "model-b"),
        ({}, None),
        ({"model": {"provider": "provider-b"}}, None),
    ],
)
def test_plan_moved_on_compares_with_what_a_new_conversation_starts_on(
    workspace, cfg, expected
):
    c, _ = workspace
    drift = runtime.plan_moved_on(c, "web", cfg)
    assert (drift[1]["model"] if drift else None) == expected
    if drift:
        assert drift[0] == {"model": "model-b", "provider": "provider-b"}


def chat_args(c, client, monkeypatch, session):
    calls = []

    def chat(self, args, home, report):
        calls.append(args)
        if "--resume" in args:
            ident = args[args.index("--resume") + 1]
        else:  # Hermes files a new conversation, on config.yaml's model
            ident = "fresh"
            with sqlite3.connect(c.home / "state.db") as db:
                db.execute(
                    "INSERT INTO sessions VALUES (?,?,?,?,?,?,?)",
                    (ident, "oneshot", 5, "nova", "uid:1000", ident, "dm"),
                )
        result = subprocess.CompletedProcess(args, 0, "Hello Robin", "")
        result.session = ident
        return result

    monkeypatch.setattr(runtime.Runtime, "chat", chat)
    response = client.post("/api/chat", json={"message": "hello", "session": session})
    assert response.status_code == 200
    row = response.json()
    deadline = time.monotonic() + 10
    while row["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.02)
        row = client.get("/api/operations/" + row["id"]).json()
    assert row["status"] == "complete", row
    return calls[0], row["result"]


def test_a_conversation_on_the_plan_resumes(workspace, monkeypatch):
    c, client = workspace
    args, result = chat_args(c, client, monkeypatch, "web")
    assert args[-2:] == ["--resume", "web"]
    assert result["session"] == "web"
    assert "moved" not in result


def test_a_conversation_left_on_an_old_model_continues_on_the_plan(
    workspace, monkeypatch
):
    c, client = workspace
    args, result = chat_args(c, client, monkeypatch, "older")
    assert "--resume" not in args
    assert result["session"] == "fresh"
    assert "model-b" in result["moved"] and "model-a" in result["moved"]
    assert "fresh" in runtime.read_workspace_sessions(c)


def test_a_conversation_hermes_recorded_no_policy_for_resumes(workspace, monkeypatch):
    c, client = workspace
    args, result = chat_args(c, client, monkeypatch, "unrecorded")
    assert args[-2:] == ["--resume", "unrecorded"]
    assert "moved" not in result
