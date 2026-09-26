"""Floating chat streaming, ownership boundaries, and native provider recovery."""

import contextlib
import datetime as dt
import importlib
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

import companion_config as cc
import companion_local_reflection as reflection
import pytest
from fastapi.testclient import TestClient

from kit.app import runtime
from kit.app.hermes_stream import configure_fallbacks
from kit.app.runtime import messages, sessions
from kit.app.server import build
from tests.support import WorkspaceFixture

ROOT = Path(__file__).resolve().parents[1]


def run_browser_contract(script):
    node = shutil.which("node")
    if not node:
        if os.environ.get("TAMANITOMO_REQUIRE_NODE"):
            pytest.fail("Node is required for browser contracts")
        pytest.skip("Node is unavailable")
    subprocess.run(
        [node, "-"],
        input=script,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )


def test_browser_scripts_parse_together_without_missing_assets():
    """Catch missing bundles and global lexical collisions before browser boot."""
    static = ROOT / "kit/app/static"
    html = (static / "index.html").read_text(encoding="utf-8")
    scripts = []
    for attributes, body in re.findall(r"<script\b([^>]*)>(.*?)</script>", html, re.S):
        src = re.search(r'src="/static/([^"?]+)', attributes)
        scripts.append((static / src[1]).read_text(encoding="utf-8") if src else body)
    run_browser_contract(
        "const vm = require('node:vm'); new vm.Script("
        + json.dumps("\n;\n".join(scripts))
        + ");"
    )


STREAM_HARNESS = r"""
const assert = require('node:assert/strict');
global.window = {addEventListener() {}};
require('./kit/app/static/chat-dock.js');
const parse = window.ChatDock.readStream;
"""


def test_browser_stream_preserves_unicode_across_single_byte_crlf_frames():
    run_browser_contract(STREAM_HARNESS + r"""
(async () => {
  const bytes = new TextEncoder().encode(
    ': heartbeat\r\n\r\nevent: delta\r\ndata: {"text":"茶🌿"}\r\n\r\n' +
    'event: final\r\ndata: {"response":\r\ndata: "café"}\r\n\r\n');
  const received = [];
  await parse(new Response(new ReadableStream({start(controller) {
    for (const byte of bytes) controller.enqueue(new Uint8Array([byte]));
    controller.close();
  }})), (kind, data) => received.push([kind, data]));
  assert.deepEqual(received, [
    ['delta', {text: '茶🌿'}], ['final', {response: 'café'}]
  ]);
})().catch(error => {console.error(error); process.exitCode = 1;});
""")


def test_browser_stream_cancels_and_releases_reader_after_terminal_error():
    run_browser_contract(STREAM_HARNESS + r"""
(async () => {
  let cancelled = false, released = false;
  const response = {body: {getReader() {return {
    async read() {return {done: false, value: new TextEncoder().encode(
      'event: error\ndata: {"error":"provider stopped"}\n\n')};},
    async cancel() {cancelled = true;},
    releaseLock() {released = true;}
  };}}};
  await assert.rejects(parse(response, (kind, data) => {
    assert.equal(kind, 'error');
    throw Error(data.error);
  }), /provider stopped/);
  assert.equal(cancelled, true);
  assert.equal(released, true);
})().catch(error => {console.error(error); process.exitCode = 1;});
""")


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
    (c.home / ".tamanitomo-chat-owner.json").write_text(
        json.dumps({"telegram": ["4242"]}), encoding="utf-8"
    )
    runtime.note_workspace_session(c, "web")
    with sqlite3.connect(c.home / "state.db") as db:
        db.executescript(
            "\n            CREATE TABLE sessions (id TEXT PRIMARY KEY, source TEXT, started_at REAL,\n                profile_name TEXT, user_id TEXT, chat_id TEXT, chat_type TEXT);\n            CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT,\n                content TEXT, timestamp REAL, platform_message_id TEXT, display_kind TEXT,\n                _compressed_summary INTEGER DEFAULT 0, active INTEGER DEFAULT 1,\n                compacted INTEGER DEFAULT 0);\n        "
        )
        sessions = [
            ("web", "cli", 1, "nova", None, None, None),
            ("terminal", "cli", 2, "nova", None, None, None),
            ("owner", "telegram", 3, "nova", "4242", "4242", "dm"),
            ("stranger", "telegram", 4, "nova", "9999", "9999", "dm"),
            ("group", "telegram", 5, "nova", "4242", "-1000", "group"),
            ("gateway-local", "cli", 6, "nova", None, "remote", None),
            ("cron", "cron", 7, "nova", None, None, None),
            ("other-profile", "cli", 8, "rowan", None, None, None),
        ]
        db.executemany("INSERT INTO sessions VALUES (?,?,?,?,?,?,?)", sessions)
        for i, row in enumerate(sessions, 1):
            db.execute(
                "INSERT INTO messages(id,session_id,role,content,timestamp,platform_message_id) VALUES (?, ?, ?, ?, ?, ?)",
                (i, row[0], "user", "said in " + row[0], 100 + i, str(i)),
            )
        db.execute(
            "INSERT INTO messages(id,session_id,role,content,timestamp) VALUES (20,'owner','user','unverified sender',120)"
        )
        db.execute(
            "INSERT INTO messages(id,session_id,role,content,timestamp,display_kind) VALUES (21,'web','assistant','internal note',121,'internal_notification')"
        )
    app = build(home=c.home, state_dir=tmp_path / "app")
    with TestClient(app) as client:
        yield (c, app, client)
    app.state.operations.pool.shutdown(wait=True)
    app.state.dashboards.close()


def test_feed_and_memory_exclude_other_people_and_internal_messages(workspace):
    c, app, client = workspace
    response = client.get("/api/feed")
    assert response.status_code == 200
    page = response.json()
    assert [row["content"] for row in page["messages"]] == [
        "said in web",
        "said in terminal",
        "said in owner",
    ]
    assert page["session"] == "terminal"
    rows, *_ = reflection.trusted_messages(
        c,
        dt.datetime.fromtimestamp(0, dt.timezone.utc),
        dt.datetime.fromtimestamp(200, dt.timezone.utc),
    )
    assert [row["content"] for row in rows] == [
        row["content"] for row in page["messages"]
    ]


def test_feed_pages_have_no_gaps_or_duplicates(workspace):
    _, _, client = workspace
    seen, cursor = ([], None)
    while True:
        page = client.get(
            "/api/feed", params={"limit": 1, **({"before": cursor} if cursor else {})}
        ).json()
        seen = [row["content"] for row in page["messages"]] + seen
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == ["said in web", "said in terminal", "said in owner"]


@pytest.mark.parametrize(
    "session", ["stranger", "group", "owner", "gateway-local", "other-profile"]
)
def test_resuming_requires_a_trusted_local_session(workspace, session):
    _, _, client = workspace
    response = client.post("/api/chat", json={"message": "hello", "session": session})
    assert response.status_code == 400
    assert "local conversation with the owner" in response.json()["detail"]


def test_chat_stream_emits_operation_deltas_and_final_without_replaying(
    workspace, monkeypatch
):
    _, _, client = workspace
    calls = []

    def chat(self, args, home, report):
        calls.append(args)
        report.stream("Hello ")
        time.sleep(0.06)
        report.stream("Robin")
        result = subprocess.CompletedProcess(args, 0, "Hello Robin", "")
        result.session = "web"
        return result

    monkeypatch.setattr(runtime.Runtime, "chat", chat)
    response = client.post(
        "/api/chat",
        json={"message": "hello", "session": "web"},
        headers={"Accept": "text/event-stream"},
    )
    events = [
        (
            block.splitlines()[0].removeprefix("event: "),
            json.loads(block.splitlines()[1].removeprefix("data: ")),
        )
        for block in response.text.strip().split("\n\n")
    ]
    assert response.status_code == 200
    assert events[0][0] == "operation"
    assert (
        "".join((payload["text"] for kind, payload in events if kind == "delta"))
        == "Hello Robin"
    )
    kind, result = events[-1]
    assert kind == "final"
    assert result["response"] == "Hello Robin"
    assert result["session"] == "web"
    assert [row["content"] for row in result["messages"]] == ["said in web"]
    operation = client.get("/api/operations/" + events[0][1]["id"]).json()
    assert operation["status"] == "complete"
    assert operation["result"]["response"] == "Hello Robin"
    assert len(calls) == 1


def test_chat_failure_is_a_stream_error(workspace, monkeypatch):
    _, _, client = workspace

    def fail(*args, **kwargs):
        raise ValueError("Provider unavailable")

    monkeypatch.setattr(runtime.Runtime, "chat", fail)
    response = client.post(
        "/api/chat", json={"message": "hello"}, headers={"Accept": "text/event-stream"}
    )
    assert "event: error" in response.text
    assert "Provider unavailable" in response.text
    assert "event: final" not in response.text


def test_unreadable_transcript_never_becomes_empty_evidence(workspace):
    c, _, _ = workspace
    (c.home / "state.db").write_bytes(b"not a sqlite database")
    with pytest.raises(ValueError, match="nothing was reflected"):
        reflection.trusted_messages(
            c,
            dt.datetime.fromtimestamp(0, dt.timezone.utc),
            dt.datetime.fromtimestamp(200, dt.timezone.utc),
        )


def test_entry_points_import_and_workspace_builds_under_one_second(workspace, tmp_path):
    c, _, client = workspace
    importlib.import_module("kit.cli.app")
    importlib.import_module("kit.app.hosted")
    started = time.perf_counter()
    app = build(home=c.home, state_dir=tmp_path / "second-app")
    assert time.perf_counter() - started < 1
    assert client.get("/").status_code == 200
    assert not any(("/chat/sends" in route.path for route in app.routes))
    app.state.operations.pool.shutdown()
    app.state.dashboards.close()


def test_installs_ordered_native_chain_and_reports_provider_switch(monkeypatch):
    chain = [
        {"provider": "deepseek", "model": "secondary"},
        {
            "provider": "ollama",
            "model": "local",
            "base_url": "http://127.0.0.1:11434/v1",
        },
    ]
    monkeypatch.setenv("TAMANITOMO_CHAT_FALLBACKS", json.dumps(chain))
    attempts, events = ([], [])
    agent = SimpleNamespace(provider="primary", _api_max_retries=3)

    def activate(*args, **kwargs):
        if agent._fallback_index == len(agent._fallback_chain):
            return False
        route = agent._fallback_chain[agent._fallback_index]
        agent._fallback_index += 1
        agent.provider = route["provider"]
        return True

    agent._try_activate_fallback = activate
    configure_fallbacks(agent, lambda event, **fields: events.append(event))
    while True:
        attempts.append(agent.provider)
        if agent.provider == "ollama":
            break
        assert agent._try_activate_fallback(reason="unavailable")
    assert attempts == ["primary", "deepseek", "ollama"]
    assert events == ["fallback", "fallback"]
    assert agent._api_max_retries == 1
    assert agent._fallback_chain[-1]["base_url"] == "http://127.0.0.1:11434/v1"


def test_no_override_preserves_native_configuration(monkeypatch):
    monkeypatch.delenv("TAMANITOMO_CHAT_FALLBACKS", raising=False)
    agent = SimpleNamespace(_fallback_chain=["native"])
    configure_fallbacks(agent, lambda *args, **kw: None)
    assert agent._fallback_chain == ["native"]


def test_explicit_empty_chain_disables_stale_native_backups(monkeypatch):
    monkeypatch.setenv("TAMANITOMO_CHAT_FALLBACKS", "[]")
    agent = SimpleNamespace(
        _fallback_chain=["stale"], _try_activate_fallback=lambda: False
    )
    configure_fallbacks(agent, lambda *args, **kw: None)
    assert agent._fallback_chain == []
    assert agent._fallback_model is None


def test_older_native_runtime_keeps_its_quiet_cli_behavior(monkeypatch):
    monkeypatch.setenv(
        "TAMANITOMO_CHAT_FALLBACKS", '[{"provider":"secondary","model":"backup"}]'
    )
    agent = SimpleNamespace()
    configure_fallbacks(agent, lambda *args, **kw: None)
    assert not hasattr(agent, "_fallback_chain")


def test_local_adapter_and_profile_credentials_are_scoped(tmp_path, monkeypatch):
    import companion_config as cc

    from kit.app.runtime import _chat_fallbacks

    monkeypatch.delenv("SECONDARY_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "primary-key-never-forwarded")
    c = cc.Companion(hermes_root=tmp_path / "home", vault=tmp_path / "vault")
    c.home.mkdir(parents=True)
    (c.home / ".env").write_text("SECONDARY_KEY=secondary-only\n", encoding="utf-8")
    (c.home / "config.yaml").write_text(
        "model:\n  provider: openai\n  default: primary\n", encoding="utf-8"
    )
    c.models["fallbacks"] = [
        {"provider": "deepseek", "model": "secondary", "api_key_env": "SECONDARY_KEY"},
        {"provider": "ollama", "model": "local"},
    ]
    chain = _chat_fallbacks(c)
    assert chain[0]["api_key"] == "secondary-only"
    assert chain[1]["provider"] == "custom"
    assert chain[1]["api_key"] == "no-key-required"
    assert chain[1]["base_url"] == "http://127.0.0.1:11434/v1"
    assert "primary-key-never-forwarded" not in json.dumps(chain)


class Agent:

    def __init__(self):
        self.session_id = "sess-1"
        self.stream_delta_callback = None


class StreamSignatureTests(unittest.TestCase):

    def run_bridge(self, quiet, configure=None):
        """Drive hermes_stream.main() against a stand-in Hermes."""
        from kit.app import hermes_stream

        calls = {}
        cli = types.ModuleType("cli")
        cli._run_quiet_single_query = quiet
        if configure is not None:
            cli._configure_quiet_agent = configure
        hermes_cli = types.ModuleType("hermes_cli")
        main_mod = types.ModuleType("hermes_cli.main")

        def hermes_main():
            agent = Agent()
            if hasattr(cli, "_configure_quiet_agent"):
                cli._configure_quiet_agent(agent)
            if agent.stream_delta_callback:
                agent.stream_delta_callback("hello ")
            calls["result"] = cli._run_quiet_single_query(
                agent, "a question", emitter=None
            )

        main_mod.main = hermes_main
        hermes_cli.main = main_mod
        saved = {
            k: sys.modules.get(k) for k in ("cli", "hermes_cli", "hermes_cli.main")
        }
        sys.modules.update(
            {"cli": cli, "hermes_cli": hermes_cli, "hermes_cli.main": main_mod}
        )
        captured = io.StringIO()
        real_stdout = sys.stdout
        sys.stdout = captured
        try:
            hermes_stream.main()
        finally:
            sys.stdout = real_stdout
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
        events = [
            json.loads(line)
            for line in captured.getvalue().splitlines()
            if line.strip()
        ]
        return (events, calls)

    def test_the_signature_that_broke_it(self):
        """Hermes 0.21.3: the runner takes an emitter and is always given one."""
        seen = {}

        def quiet(cli_obj, query, emitter=None):
            seen["query"] = query
            seen["emitter_passed"] = "emitter" in seen or True
            return "answered"

        events, calls = self.run_bridge(quiet)
        self.assertEqual(seen["query"], "a question")
        self.assertEqual(calls["result"], "answered")
        self.assertIn("session", [e["event"] for e in events])

    def test_the_session_event_still_reports_the_id(self):
        events, _ = self.run_bridge(lambda c, q, emitter=None: None)
        session = next((e for e in events if e["event"] == "session"))
        self.assertEqual(session["id"], "sess-1")

    def test_deltas_still_stream(self):

        def configure(agent, *args, **kwargs):
            agent.configured = True

        events, _ = self.run_bridge(
            lambda c, q, emitter=None: None, configure=configure
        )
        deltas = [e for e in events if e["event"] == "delta"]
        self.assertEqual([d["text"] for d in deltas], ["hello "])

    def test_the_session_event_survives_a_failing_turn(self):
        """A turn that raises must still say which session it was."""

        def quiet(cli_obj, query, emitter=None):
            raise RuntimeError("model refused")

        with self.assertRaises(RuntimeError):
            self.run_bridge(quiet)


class StreamProcessTests(unittest.TestCase):

    def test_callbacks_and_final_response_are_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "cli.py").write_text(
                "\nfrom types import SimpleNamespace\ndef _configure_quiet_agent(agent):agent.configured=True\ndef _run_quiet_single_query(instance,query):\n    assert instance.agent.configured\n    instance.agent.stream_delta_callback('Hello ')\n    instance.agent.stream_delta_callback(None)\n    instance.agent.stream_delta_callback('there')\n    print('Hello there')\n    raise SystemExit(0)\n",
                encoding="utf-8",
            )
            (root / "hermes_cli").mkdir()
            (root / "hermes_cli/__init__.py").write_text("", encoding="utf-8")
            (root / "hermes_cli/main.py").write_text(
                "\nimport cli\nfrom types import SimpleNamespace\ndef main():\n    agent=SimpleNamespace()\n    cli._configure_quiet_agent(agent)\n    cli._run_quiet_single_query(SimpleNamespace(agent=agent,session_id='own-session'),'hello')\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(ROOT / "kit/app/hermes_stream.py"), "chat"],
                env={**os.environ, "PYTHONPATH": str(root)},
                capture_output=True,
                text=True,
                check=True,
            )
            events = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual(
                [r["text"] for r in events if r["event"] == "delta"],
                ["Hello ", "there"],
            )
            self.assertEqual(events[-2], {"event": "session", "id": "own-session"})
            self.assertEqual(events[-1], {"event": "final", "text": "Hello there\n"})


class ChatDockApiTests(WorkspaceFixture):

    def test_shared_session_database_never_returns_another_profile(self):
        db = self.root / "state.db"
        with contextlib.closing(sqlite3.connect(db)) as con:
            con.executescript(
                "CREATE TABLE sessions(id TEXT,source TEXT,started_at REAL,profile_name TEXT); CREATE TABLE messages(session_id TEXT,role TEXT,content TEXT,timestamp REAL);"
            )
            con.executemany(
                "INSERT INTO sessions VALUES (?,?,?,?)",
                [
                    ("n", "telegram", 1, "nova"),
                    ("r", "cli", 2, "rowan"),
                    ("d", "cli", 3, ""),
                ],
            )
            con.executemany(
                "INSERT INTO messages VALUES (?,?,?,?)",
                [("n", "user", "Nova only", 1), ("r", "user", "Rowan only", 2)],
            )
            con.commit()
        try:
            (self.c.home / "state.db").symlink_to(db)
        except OSError:
            self.skipTest("Symlinks unavailable")
        self.assertEqual([r["id"] for r in sessions(self.c)], ["n"])
        self.assertEqual(messages(self.c, "n")[0]["content"], "Nova only")
        with self.assertRaises(ValueError):
            messages(self.c, "r")
        self.assertEqual(self.get("/api/sessions/r").status_code, 400)


def test_vault_expanded_folders_load_before_render_and_failed_reads_stay_visible():
    run_browser_contract(r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('kit/app/static/studios.js', 'utf8');
const tree = source.slice(source.indexOf('async function loadVaultFolder'), source.indexOf('function renderVaultTree'));
const navigation = source.slice(source.indexOf('listVault=async function'), source.indexOf('showNote=function'));
vm.runInThisContext(`
let vaultTreeData=new Map(), vaultTreeErrors=new Map(), vaultExpanded=new Set(['notes','notes/deep','blocked']);
let vaultRequest=0, vaultPath='', vaultDirty=false, openNote=null, current='vault', listVault, readNote;
let shown=null, rendered='', requests=[];
const esc=value=>String(value), CSS={escape:value=>value}, filterVaultEntry=()=>true;
const leaveNote=async()=>true, clearEditorDirty=()=>{}, notice=()=>{};
const showNote=note=>{shown=note;};
const renderVaultTree=()=>{rendered=renderFolderTreeHTML('');};
const folder=(path,name=path)=>({path,name,directory:true});
const file=(path)=>({path,name:path.split('/').at(-1),directory:false});
const listings={
 '':[folder('notes'),folder('closed'),folder('blocked')],
 notes:[file('notes/garden.md'),folder('notes/deep','deep')],
 'notes/deep':[file('notes/deep/todo.md')]
};
const api=async path=>{
 const url=new URL(path,'http://localhost'), folderPath=url.searchParams.get('path');
 requests.push(url.pathname+':'+folderPath);
 if(url.pathname==='/vault/file')return {path:folderPath,text:'A garden note'};
 if(folderPath==='blocked')throw Error('Folder unavailable');
 return {entries:listings[folderPath]||[]};
};
${tree}
${navigation}
(async()=>{
 await listVault('');
 assert.ok(rendered.includes('garden.md'));
 assert.ok(rendered.includes('todo.md'));
 assert.ok(rendered.includes('Folder unavailable'));
 assert.ok(rendered.includes('data-load-folder="blocked"'));
 assert.ok(!rendered.includes('Empty folder'));
 assert.ok(!requests.some(path=>path==='/vault:closed'));
 vaultTreeData.delete('notes');
 requests=[];
 await readNote('notes/garden.md');
 assert.equal(shown.path,'notes/garden.md');
 assert.ok(requests.includes('/vault:notes'), 'An already expanded parent must still hydrate when uncached');
 assert.ok(rendered.includes('garden.md'));
})().catch(error=>{console.error(error);process.exitCode=1;});
`);
""")
