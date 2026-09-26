"""The sole chat surface streams once and reads only the owner's conversations."""
import datetime as dt
import importlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'kit/scripts'))
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
import companion_config as cc
import companion_local_reflection as reflection
from kit.app import runtime
from kit.app.server import build


@pytest.fixture
def workspace(tmp_path):
    c = cc.Companion(agent='Nova', human='Robin', hermes_root=tmp_path / 'home',
                     vault=tmp_path / 'vault', timezone='UTC', profile='nova')
    c.home.mkdir(parents=True)
    c.save()
    (c.home / '.tamanitomo-chat-owner.json').write_text(json.dumps({'telegram': ['4242']}))
    runtime.note_workspace_session(c, 'web')
    with sqlite3.connect(c.home / 'state.db') as db:
        db.executescript('''
            CREATE TABLE sessions (id TEXT PRIMARY KEY, source TEXT, started_at REAL,
                profile_name TEXT, user_id TEXT, chat_id TEXT, chat_type TEXT);
            CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT,
                content TEXT, timestamp REAL, platform_message_id TEXT, display_kind TEXT,
                _compressed_summary INTEGER DEFAULT 0, active INTEGER DEFAULT 1,
                compacted INTEGER DEFAULT 0);
        ''')
        sessions = [
            ('web', 'cli', 1, 'nova', None, None, None),
            ('terminal', 'cli', 2, 'nova', None, None, None),
            ('owner', 'telegram', 3, 'nova', '4242', '4242', 'dm'),
            ('stranger', 'telegram', 4, 'nova', '9999', '9999', 'dm'),
            ('group', 'telegram', 5, 'nova', '4242', '-1000', 'group'),
            ('gateway-local', 'cli', 6, 'nova', None, 'remote', None),
            ('cron', 'cron', 7, 'nova', None, None, None),
            ('other-profile', 'cli', 8, 'rowan', None, None, None),
        ]
        db.executemany('INSERT INTO sessions VALUES (?,?,?,?,?,?,?)', sessions)
        for i, row in enumerate(sessions, 1):
            db.execute('INSERT INTO messages(id,session_id,role,content,timestamp,platform_message_id) '
                       'VALUES (?, ?, ?, ?, ?, ?)', (i, row[0], 'user', 'said in ' + row[0], 100 + i, str(i)))
        db.execute("INSERT INTO messages(id,session_id,role,content,timestamp) "
                   "VALUES (20,'owner','user','unverified sender',120)")
        db.execute("INSERT INTO messages(id,session_id,role,content,timestamp,display_kind) "
                   "VALUES (21,'web','assistant','internal note',121,'internal_notification')")
    app = build(home=c.home, state_dir=tmp_path / 'app')
    with TestClient(app) as client:
        yield c, app, client
    app.state.operations.pool.shutdown(wait=True)
    app.state.dashboards.close()


def test_feed_and_memory_exclude_other_people_and_internal_messages(workspace):
    c, app, client = workspace
    response = client.get('/api/feed')
    assert response.status_code == 200
    page = response.json()
    assert [row['content'] for row in page['messages']] == ['said in web', 'said in terminal', 'said in owner']
    assert page['session'] == 'terminal'
    rows, *_ = reflection.trusted_messages(c, dt.datetime.fromtimestamp(0, dt.timezone.utc),
                                         dt.datetime.fromtimestamp(200, dt.timezone.utc))
    assert [row['content'] for row in rows] == [row['content'] for row in page['messages']]


def test_feed_pages_have_no_gaps_or_duplicates(workspace):
    _, _, client = workspace
    seen, cursor = [], None
    while True:
        page = client.get('/api/feed', params={'limit': 1, **({'before': cursor} if cursor else {})}).json()
        seen = [row['content'] for row in page['messages']] + seen
        cursor = page['next_cursor']
        if cursor is None:
            break
    assert seen == ['said in web', 'said in terminal', 'said in owner']


@pytest.mark.parametrize('session', ['stranger', 'group', 'owner', 'gateway-local', 'other-profile'])
def test_resuming_requires_a_trusted_local_session(workspace, session):
    _, _, client = workspace
    response = client.post('/api/chat', json={'message': 'hello', 'session': session})
    assert response.status_code == 400
    assert 'local conversation with the owner' in response.json()['detail']


def test_chat_stream_emits_operation_deltas_and_final_without_replaying(workspace, monkeypatch):
    _, _, client = workspace
    calls = []

    def chat(self, args, home, report):
        calls.append(args)
        report.stream('Hello ')
        time.sleep(.06)
        report.stream('Robin')
        result = subprocess.CompletedProcess(args, 0, 'Hello Robin', '')
        result.session = 'web'
        return result

    monkeypatch.setattr(runtime.Runtime, 'chat', chat)
    response = client.post('/api/chat', json={'message': 'hello', 'session': 'web'},
                           headers={'Accept': 'text/event-stream'})
    events = [(block.splitlines()[0].removeprefix('event: '),
               json.loads(block.splitlines()[1].removeprefix('data: ')))
              for block in response.text.strip().split('\n\n')]
    assert response.status_code == 200
    assert events[0][0] == 'operation'
    assert ''.join(payload['text'] for kind, payload in events if kind == 'delta') == 'Hello Robin'
    kind, result = events[-1]
    assert kind == 'final'
    assert result['response'] == 'Hello Robin'
    assert result['session'] == 'web'
    assert [row['content'] for row in result['messages']] == ['said in web']
    operation = client.get('/api/operations/' + events[0][1]['id']).json()
    assert operation['status'] == 'complete'
    assert operation['result']['response'] == 'Hello Robin'
    assert len(calls) == 1


def test_chat_failure_is_a_stream_error(workspace, monkeypatch):
    _, _, client = workspace

    def fail(*args, **kwargs):
        raise ValueError('Provider unavailable')

    monkeypatch.setattr(runtime.Runtime, 'chat', fail)
    response = client.post('/api/chat', json={'message': 'hello'}, headers={'Accept': 'text/event-stream'})
    assert 'event: error' in response.text
    assert 'Provider unavailable' in response.text
    assert 'event: final' not in response.text


def test_unreadable_transcript_never_becomes_empty_evidence(workspace):
    c, _, _ = workspace
    (c.home / 'state.db').write_bytes(b'not a sqlite database')
    with pytest.raises(ValueError, match='nothing was reflected'):
        reflection.trusted_messages(c, dt.datetime.fromtimestamp(0, dt.timezone.utc),
                                    dt.datetime.fromtimestamp(200, dt.timezone.utc))


def test_entry_points_import_and_workspace_builds_under_one_second(workspace, tmp_path):
    c, _, client = workspace
    importlib.import_module('kit.cli.app')
    importlib.import_module('kit.app.hosted')
    started = time.perf_counter()
    app = build(home=c.home, state_dir=tmp_path / 'second-app')
    assert time.perf_counter() - started < 1
    assert client.get('/').status_code == 200
    assert not any('/chat/sends' in route.path for route in app.routes)
    app.state.operations.pool.shutdown()
    app.state.dashboards.close()
