"""Phase 1B C1 integration over HTTP: keyed sends through the app (review R5 section 5).

BOUNDARY: HTTP routes (app fixture, TestClient) -> chat_send_routes -> SendService ->
executor -> the local fake Hermes double (tests/phase1b_c1/fake_hermes) -> a synthetic
state.db -> the Phase 1A read routes. The fake Hermes is a PROTOCOL DOUBLE, not evidence
about Hermes; the same lifecycle against the pinned Hermes and the mock provider is in
tests/test_phase1b_c1_pinned.py::PinnedHttp (the designated lane).

The app is built with an explicit `chat_sends=Options(...)`. Without it (every shipped
entry point) the routes do not exist: see Disabled. Matrix ids are PHASE1B_DESIGN.md 10.
"""
import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts')]

from fastapi.testclient import TestClient      # noqa: E402
import companion_config as cc                  # noqa: E402

from kit.app import chat_send_routes as csr    # noqa: E402
from kit.app import chat_sends as cs           # noqa: E402
from kit.app import chat_sources as csrc       # noqa: E402
from kit.app import send_protocol as sp        # noqa: E402
from kit.app.server import build               # noqa: E402
from tests.phase1b_c1 import harness as h      # noqa: E402

LINUX = h.LINUX
POSIX_ONLY = 'the C1 supervision is established on Linux only (O-8, O-9, O-11)'
PROC = ROOT / 'tests' / 'phase1b_c1' / 'mutation_proc.py'
NOTE = ('[System: The previous response was cut off by a network error mid-stream. Continue exactly '
        'where you left off. Do not restart or repeat prior text. Finish the answer directly.]')


def wait_for(pred, timeout=30.0, interval=0.05):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = pred()
        if value:
            return value
        time.sleep(interval)
    return None


class App:
    """A synthetic Hermes installation (profiles nova and rowan) and an app built with keyed
    sends enabled, the executor pointed at the fake Hermes double. `restart()` builds a new
    app over the same state: a new controller, no in-memory operation rows."""

    def __init__(self, test, enable=True, executor=None):
        self.test = test
        self.executor = executor or (lambda rt, home: h.fake_executor(home))
        tmp = tempfile.TemporaryDirectory(prefix='c1i-')
        test.addCleanup(tmp.cleanup)
        self.tmp = pathlib.Path(tmp.name)
        self.root = self.tmp / 'hermes'
        vault = self.tmp / 'vault'
        self.root.mkdir()
        vault.mkdir()
        self.companions = {}
        for name, agent in (('nova', 'Nova'), ('rowan', 'Rowan')):
            c = cc.Companion(agent=agent, profile=name, hermes_root=self.root, vault=vault, soul_in_vault=False,
                             context_mode='fixed')
            c.home.mkdir(parents=True)
            c.save()
            self.companions[name] = c
        self.state = self.tmp / 'state'
        self.enable = enable
        self.apps = []
        self._build()

    def _build(self):
        options = csr.Options(executor=self.executor, turn_timeout=120, stop_grace=1.0,
                              watchdog_interval=0.1) if self.enable else None
        self.app = build(self.root, token='t', state_dir=self.state, chat_sends=options)
        self.apps.append(self.app)
        if self.enable:
            self.test.addCleanup(self.app.state.chat_sends.close)
        self.client = TestClient(self.app)

    def restart(self):
        wait_for(lambda: not self.app.state.operations.busy, 30)
        self.app.state.chat_sends.close()
        self._build()

    def home(self, profile='nova'):
        return self.companions[profile].home

    def scenario(self, profile='nova', **values):
        h.scenario(self.home(profile), **values)

    def get(self, path, profile='nova', **params):
        return self.client.get('/api' + path, params={'profile': profile, **params}, headers={'x-companion-token': 't'})

    def post(self, path, body=None, profile='nova'):
        return self.client.post('/api' + path, params={'profile': profile}, headers={'x-companion-token': 't'},
                                json=body if body is not None else {})

    def bootstrap(self, profile='nova'):
        r = self.get('/chat/sends/bootstrap', profile)
        self.test.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def body(self, message='A synthetic owner message', profile='nova', session=None, key=None, boot=None):
        boot = boot or self.bootstrap(profile)
        return {'client_key': key or cs.new_ulid(), 'generation': boot['generation'],
                'conversation_id': boot['conversation_id'], 'message': message, 'session': session}

    def settle(self, send_id, profile='nova', timeout=90):
        def done():
            r = self.get(f'/chat/sends/{send_id}', profile)
            return r.json() if r.status_code == 200 and r.json()['settled'] else None
        receipt = wait_for(done, timeout)
        self.test.assertIsNotNone(receipt, f'{send_id} did not settle')
        wait_for(lambda: not self.app.state.operations.busy, 10)
        return receipt

    def send(self, message='A synthetic owner message', profile='nova', **kw):
        body = self.body(message, profile, **kw)
        r = self.post('/chat/sends', body, profile)
        self.test.assertEqual(r.status_code, 202, r.text)
        return body, r.json(), self.settle(r.json()['send']['send_id'], profile)

    def ledger(self, profile='nova'):
        return sp.ledger_dir(self.home(profile)) / sp.LEDGER_FILE

    def facts(self, send_id, profile='nova'):
        con = sp.connect(self.ledger(profile), readonly=True)
        try:
            return [k for (k,) in con.execute('SELECT kind FROM send_facts WHERE send_id=? ORDER BY seq', (send_id,))]
        finally:
            con.close()

    def launches(self, send_id, profile='nova'):
        return self.facts(send_id, profile).count('executor_started')

    def rows(self, profile='nova'):
        con = sqlite3.connect(self.home(profile) / 'state.db')
        try:
            return con.execute('SELECT id, session_id, role, content, timestamp FROM messages ORDER BY id').fetchall()
        finally:
            con.close()

    def snapshot(self, profile='nova', **params):
        r = self.get('/chat/snapshot', profile, **params)
        self.test.assertEqual(r.status_code, 200, r.text)
        return r.json()


@unittest.skipUnless(LINUX, POSIX_ONLY)
class HttpLifecycle(unittest.TestCase):

    def setUp(self):
        self.a = App(self)

    def test_connected_lifecycle_links_reads_and_replays(self):
        """bootstrap -> keyed acceptance (202) -> execution -> operation and receipt -> source
        correlation in the Phase 1A reads -> same-key replay (200), one launch (M-1, M-14)."""
        body, accepted, receipt = self.a.send()
        send_id = accepted['send']['send_id']
        self.assertIn(accepted['send']['state'], ('accepted', 'launching', 'generating', 'complete'))
        self.assertEqual((receipt['state'], receipt['owner_turn'], receipt['reply'], receipt['links']),
                         ('complete', 'recorded', 'final', 'linked'))
        rows = self.a.rows()
        self.assertEqual(receipt['session'], rows[0][1])
        snap = self.a.snapshot()
        by_id = {m['message_id']: m for m in snap['messages']}
        owner, reply = by_id[receipt['owner_message_id']], by_id[receipt['reply_message_ids'][0]]
        self.assertEqual((owner['content'], owner['source']['kind']), (body['message'], 'workspace'))
        self.assertEqual(owner['correlation'], {'send_id': send_id, 'send_part': 'owner'})
        self.assertEqual(reply['correlation'], {'send_id': send_id, 'send_part': 'reply:0'})
        self.assertEqual(snap['provenance']['state'], 'ok')
        again = self.a.post('/chat/sends', body)
        self.assertEqual((again.status_code, again.json()['replay'], again.json()['send']['send_id']),
                         (200, True, send_id))
        self.assertEqual(self.a.launches(send_id), 1)
        op = self.a.get('/operations/' + accepted['operation']['id']).json()
        self.assertEqual((op['status'], op['send_id'], op['format']), ('complete', send_id, 2))
        self.assertEqual((op['result']['response'], op['result']['content_retained']), ('A synthetic reply.', True))
        self.assertEqual([m['content'] for m in op['result']['messages']], [body['message'], 'A synthetic reply.'])

    def test_a_post_before_bootstrap_is_refused_and_creates_nothing(self):
        """M-6e over HTTP."""
        from kit.app.chat_projection import ChatScope
        scope = ChatScope('existing', 'nova', str(self.a.home().resolve()), 'unused')
        r = self.a.post('/chat/sends', {'client_key': cs.new_ulid(), 'generation': 'x' * 32, 'message': 'hello',
                                        'session': None, 'conversation_id': scope.conversation_id})
        self.assertEqual((r.status_code, r.json()['error']), (409, 'not_bootstrapped'))
        self.assertFalse(sp.ledger_dir(self.a.home()).exists())

    def test_lost_response_is_recovered_by_key_and_retried_without_a_second_launch(self):
        """M-5, M-5a: before the POST the key is unknown (404); after a POST whose response was
        lost, GET ?key= returns the receipt and the identical retry replays it."""
        body = self.a.body()
        missing = self.a.get('/chat/sends', key=body['client_key'])
        self.assertEqual((missing.status_code, missing.json()['error']), (404, 'not_found'))
        self.a.post('/chat/sends', body)                # the response is "lost": never read
        found = self.a.get('/chat/sends', key=body['client_key'])
        self.assertEqual(found.status_code, 200)
        send_id = found.json()['send_id']
        retry = self.a.post('/chat/sends', body)
        self.assertEqual((retry.status_code, retry.json()['send']['send_id']), (200, send_id))
        self.a.settle(send_id)
        self.assertEqual(self.a.launches(send_id), 1)

    def test_admission_refusals_change_nothing(self):
        """M-3, M-6, wrong conversation, unauthorised session, over HTTP."""
        body, accepted, _ = self.a.send()
        conflict = self.a.post('/chat/sends', {**body, 'message': 'different'})
        self.assertEqual((conflict.status_code, conflict.json()['error'], conflict.json()['send_id']),
                         (409, 'key_conflict', accepted['send']['send_id']))
        stale = self.a.post('/chat/sends', {**self.a.body(), 'generation': '0' * 32})
        self.assertEqual((stale.status_code, stale.json()['error']), (409, 'generation_changed'))
        old = self.a.post('/chat/sends', self.a.body(key=cs.new_ulid(time.time() - 2 * 86400)))
        self.assertEqual((old.status_code, old.json()['error']), (422, 'key_expired'))
        wrong = self.a.post('/chat/sends', {**self.a.body(), 'conversation_id': 'conv_elsewhere'})
        self.assertEqual((wrong.status_code, wrong.json()['error']), (400, 'wrong_conversation'))
        stranger = self.a.post('/chat/sends', self.a.body(session='no-such-session'))
        self.assertEqual((stranger.status_code, stranger.json()['error']), (400, 'unauthorised_session'))
        con = sp.connect(self.a.ledger(), readonly=True)
        try:
            self.assertEqual(con.execute('SELECT count(*) FROM sends').fetchone()[0], 1)
        finally:
            con.close()

    def test_a_resumed_workspace_session_is_authorised_by_the_current_binding(self):
        """A session the send created is resumable; with workspace trust withdrawn it is not."""
        _, _, first = self.a.send()
        _, _, second = self.a.send('A second message', session=first['session'])
        self.assertEqual((second['state'], second['session']), ('complete', first['session']))
        (self.a.home() / csrc.BINDING_FILE).write_text(json.dumps({'workspace': False}))
        refused = self.a.post('/chat/sends', self.a.body('A third', session=first['session']))
        self.assertEqual((refused.status_code, refused.json()['error']), (400, 'unauthorised_session'))

    def test_one_active_attempt_and_same_key_replay_while_running(self):
        """M-1a, M-4 through HTTP: while the first send runs, its own retry replays and a new key
        is refused; then stop reaches the running turn (M-12)."""
        self.a.scenario(hang=20)
        body = self.a.body()
        first = self.a.post('/chat/sends', body)
        self.assertEqual(first.status_code, 202, first.text)
        send_id = first.json()['send']['send_id']
        self.assertTrue(wait_for(lambda: self.a.get(f'/chat/sends/{send_id}').json()['state'] == 'generating'))
        same = self.a.post('/chat/sends', body)
        self.assertEqual((same.status_code, same.json()['send']['send_id']), (200, send_id))
        other = self.a.post('/chat/sends', self.a.body('another'))
        self.assertEqual((other.status_code, other.json()['error']), (409, 'turn_in_progress'))
        stopped = self.a.post(f'/chat/sends/{send_id}/stop')
        self.assertEqual(stopped.status_code, 200, stopped.text)
        self.assertIn(stopped.json()['state'], ('generating', 'stopping'))     # never interrupted by request
        final = self.a.settle(send_id)
        self.assertEqual((final['state'], final['error']['code']), ('interrupted', 'stopped'))
        self.assertEqual(self.a.launches(send_id), 1)
        op = self.a.get('/operations/' + first.json()['operation']['id']).json()
        self.assertEqual((op['status'], op['error']), ('interrupted', 'Stopped.'))

    def test_open_receipts(self):
        self.a.scenario(hang=20)
        r = self.a.post('/chat/sends', self.a.body())
        send_id = r.json()['send']['send_id']
        listed = self.a.get('/chat/sends', open=1).json()['sends']
        self.assertEqual([s['send_id'] for s in listed], [send_id])
        self.a.post(f'/chat/sends/{send_id}/stop')
        self.a.settle(send_id)
        self.assertEqual(self.a.get('/chat/sends', open=1).json()['sends'], [])

    def test_explicit_reset_is_confirmed_and_fences_earlier_requests(self):
        """M-6c/M-6f over HTTP: an unconfirmed reset changes nothing; a confirmed one gives a
        new generation, and a retry of a request frozen before it is generation_changed."""
        boot = self.a.bootstrap()
        pending = self.a.body(boot=boot)         # minted, never delivered before the reset
        unconfirmed = self.a.post('/chat/sends/ledger/reset', {})
        self.assertEqual((unconfirmed.status_code, unconfirmed.json()['error']), (400, 'confirmation_required'))
        self.assertEqual(self.a.bootstrap()['generation'], boot['generation'])
        reset = self.a.post('/chat/sends/ledger/reset', {'confirm': csr.RESET_CONFIRMATION})
        self.assertEqual(reset.status_code, 200, reset.text)
        self.assertNotEqual(reset.json()['generation'], boot['generation'])
        retry = self.a.post('/chat/sends', pending)
        self.assertEqual((retry.status_code, retry.json()['error']), (409, 'generation_changed'))

    def test_reset_is_refused_while_a_turn_runs(self):
        self.a.scenario(hang=20)
        r = self.a.post('/chat/sends', self.a.body())
        send_id = r.json()['send']['send_id']
        self.assertTrue(wait_for(lambda: self.a.get(f'/chat/sends/{send_id}').json()['state'] == 'generating'))
        refused = self.a.post('/chat/sends/ledger/reset', {'confirm': csr.RESET_CONFIRMATION})
        self.assertEqual((refused.status_code, refused.json()['error']), (409, 'executor_live'))
        self.a.post(f'/chat/sends/{send_id}/stop')
        self.a.settle(send_id)


@unittest.skipUnless(LINUX, POSIX_ONLY)
class OperationViews(unittest.TestCase):
    """5.6/5.7: the ledger is authoritative; files hold only the allowlist; the legacy
    result is transient or reconstructed under the CURRENT authorisation, never regenerated."""

    def setUp(self):
        self.a = App(self)

    def op_file(self, ident):
        return self.a.state / 'operations' / (ident + '.json')

    def test_operation_files_hold_no_text(self):
        """M-23 (operation leg): the file at completion, and at failure."""
        secret, reply = 'Unmistakable owner text 5521', 'Unmistakable reply text 8830'
        self.a.scenario(reply=reply)
        _, accepted, _ = self.a.send(secret)
        self.a.scenario(exit=1)
        _, failed, receipt = self.a.send('Unmistakable failing text 1190')
        self.assertEqual(receipt['state'], 'failed')
        for ident in (accepted['operation']['id'], failed['operation']['id']):
            data = json.loads(self.op_file(ident).read_text())
            self.assertLessEqual(set(data), set(csr.PERSISTED) | {'result'})
            self.assertEqual(set(data.get('result') or {}), {'session', 'send_id', 'note'})
            self.assertNotIn('Unmistakable', self.op_file(ident).read_text())
        failed_file = json.loads(self.op_file(failed['operation']['id']).read_text())
        self.assertEqual((failed_file['status'], failed_file['error_code'], failed_file['error']),
                         ('failed', 'hermes_failed', cs.ERRORS['hermes_failed']))

    def test_operation_file_during_the_turn_holds_no_text(self):
        """M-23 (intermediate progress point)."""
        self.a.scenario(hang=20, reply='Unmistakable streamed 4410')
        r = self.a.post('/chat/sends', self.a.body('Unmistakable owner 7002'))
        ident, send_id = r.json()['operation']['id'], r.json()['send']['send_id']
        self.assertTrue(wait_for(lambda: self.op_file(ident).exists()))
        self.assertTrue(wait_for(lambda: self.a.get(f'/chat/sends/{send_id}').json()['state'] == 'generating'))
        view = self.a.get('/operations/' + ident).json()
        self.assertEqual((view['status'], view['progress']), ('running', 'Replying'))
        self.assertNotIn('result', view)
        self.assertNotIn('Unmistakable', self.op_file(ident).read_text())
        self.a.post(f'/chat/sends/{send_id}/stop')
        self.a.settle(send_id)

    def test_after_restart_the_result_is_reconstructed_and_a_missing_file_never_relaunches(self):
        """M-22 (new-path leg): in-memory gone -> reconstructed from linked rows; with the
        operation file deleted the view is still built from the ledger; nothing relaunches."""
        body, accepted, _ = self.a.send()
        ident, send_id = accepted['operation']['id'], accepted['send']['send_id']
        self.a.restart()
        self.op_file(ident).unlink()
        op = self.a.get('/operations/' + ident).json()
        self.assertEqual((op['status'], op['result']['response'], op['result']['content_retained']),
                         ('complete', 'A synthetic reply.', True))
        self.assertEqual(self.a.launches(send_id), 1)
        self.assertEqual(self.a.post('/chat/sends', body).status_code, 200)
        self.assertEqual(self.a.launches(send_id), 1)

    def test_revocation_withholds_links_and_content_on_both_branches(self):
        """M-14a: in the live process (in-memory result) and after a restart (reconstruction)."""
        _, accepted, _ = self.a.send()
        ident, send_id = accepted['operation']['id'], accepted['send']['send_id']
        self.assertTrue(self.a.get('/operations/' + ident).json()['result']['content_retained'])
        (self.a.home() / csrc.BINDING_FILE).write_text(json.dumps({'workspace': False}))
        for branch in ('in_memory', 'reconstructed'):
            with self.subTest(branch=branch):
                if branch == 'reconstructed':
                    self.a.restart()
                receipt = self.a.get(f'/chat/sends/{send_id}').json()
                self.assertEqual(receipt['state'], 'complete')
                for key in ('owner_message_id', 'reply_message_ids', 'session', 'links'):
                    self.assertNotIn(key, receipt)
                result = self.a.get('/operations/' + ident).json()['result']
                self.assertEqual((result['response'], result['messages'], result['content_retained']),
                                 (None, [], False))
                self.assertEqual(self.a.snapshot()['messages'], [])

    def test_a_replaced_source_row_is_lost_not_reassigned(self):
        """M-15: the reply row's identity changes (same id, different authored time): the link
        is `lost`, the row loses its correlation, and the legacy result is not retained."""
        _, accepted, receipt = self.a.send()
        send_id, ident = accepted['send']['send_id'], accepted['operation']['id']
        reply_row = [r for r in self.a.rows() if r[2] == 'assistant'][0]
        con = sqlite3.connect(self.a.home() / 'state.db')
        with con:
            con.execute('UPDATE messages SET timestamp=timestamp+100 WHERE id=?', (reply_row[0],))
        con.close()
        again = self.a.get(f'/chat/sends/{send_id}').json()
        self.assertEqual((again['links'], again['reply_message_ids']), ('lost', []))
        linked = [m for m in self.a.snapshot()['messages'] if (m['correlation'] or {}).get('send_id') == send_id]
        self.assertEqual([m['correlation']['send_part'] for m in linked], ['owner'])   # the reply row is not it
        self.assertFalse(self.a.get('/operations/' + ident).json()['result']['content_retained'])

    def test_projection_rebuild_keeps_the_join(self):
        """M-14: a rebuilt projection has new opaque ids; the join finds them."""
        _, accepted, receipt = self.a.send()
        send_id = accepted['send']['send_id']
        for path in (self.a.state / 'chat').rglob('*.sqlite3'):
            path.unlink()
        again = self.a.get(f'/chat/sends/{send_id}').json()
        self.assertEqual(again['links'], 'linked')
        self.assertNotEqual(again['owner_message_id'], receipt['owner_message_id'])
        parts = {m['correlation']['send_part'] for m in self.a.snapshot()['messages'] if m['correlation']}
        self.assertEqual(parts, {'owner', 'reply:0'})

    def test_format_two_retention_leaves_other_records(self):
        _, accepted, _ = self.a.send()
        ops = self.a.app.state.operations
        legacy = self.a.state / 'operations' / ('f' * 32 + '.json')
        legacy.write_text(json.dumps({'id': 'f' * 32, 'status': 'complete', 'result': {'response': 'old text'},
                                      'finished_at': '2020-01-01T00:00:00+00:00'}))
        self.assertEqual(ops.prune_chat_records(now=time.time() + 8 * 86400), 1)
        self.assertFalse(self.op_file(accepted['operation']['id']).exists())
        self.assertTrue(legacy.exists())


@unittest.skipUnless(LINUX, POSIX_ONLY)
class ReadBoundary(unittest.TestCase):
    """Fresh-session provenance and O-12 exclusion in the Phase 1A reads (review R5 section 4).
    The note here is produced by the fake Hermes through the same two seams the pinned Hermes
    uses; PinnedHttp repeats the exclusion against the real pinned note."""

    def setUp(self):
        self.a = App(self)

    def workspace_file(self):
        return self.a.home() / '.tamanitomo-sessions.json'

    def test_a_created_session_is_the_workspaces_from_its_receipt(self):
        """The fresh-session receipt, not the post-completion JSON note, is the authority."""
        _, _, receipt = self.a.send()
        self.workspace_file().unlink()
        (self.a.home() / csrc.BINDING_FILE).write_text(json.dumps({'terminal': False}))
        kinds = {m['source']['kind'] for m in self.a.snapshot()['messages']}
        self.assertEqual(kinds, {'workspace'})

    def test_without_a_ledger_nothing_changes(self):
        """No ledger (every live profile today): provenance `none`, same classification."""
        store = sqlite3.connect(self.a.home() / 'state.db')
        with store:
            store.executescript('CREATE TABLE sessions(id TEXT PRIMARY KEY, source TEXT, started_at REAL);'
                                'CREATE TABLE messages(id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, '
                                'role TEXT, content TEXT, timestamp REAL);')
            store.execute("INSERT INTO sessions VALUES ('t1','cli',1)")
            store.execute("INSERT INTO messages(session_id,role,content,timestamp) VALUES ('t1','user',?,2)", (NOTE,))
        store.close()
        snap = self.a.snapshot()
        self.assertEqual(snap['provenance']['state'], 'none')
        self.assertEqual([(m['content'], m['speaker'], m['source']['kind']) for m in snap['messages']],
                         [(NOTE, 'owner', 'terminal')])        # a terminal note stays as recorded

    def note_turn(self, message='A synthetic owner message', **extra):
        self.a.scenario(note=True, **extra)
        return self.a.send(message)

    def assert_reads_exclude(self, note_id, owner_text, linked=True):
        snap = self.a.snapshot()
        ids = {m['source']['message'] for m in snap['messages']}
        self.assertNotIn(str(note_id), ids)
        owners = [m for m in snap['messages'] if m['speaker'] == 'owner']
        self.assertEqual([m['content'] for m in owners], [owner_text])
        if linked:
            self.assertEqual(owners[0]['correlation']['send_part'], 'owner')
        else:       # the receipt was pruned or reset: no correlation, and the note is still excluded
            self.assertIsNone(owners[0]['correlation'])
        history = self.a.get('/chat/snapshot', limit=1).json()
        older = self.a.get('/chat/history', before=history['history']['before'], limit=200).json()
        self.assertNotIn(str(note_id), {m['source']['message'] for m in older['messages']})
        return snap

    def test_the_continuation_note_is_excluded_from_snapshot_history_and_changes(self):
        before = self.a.snapshot()
        _, _, receipt = self.note_turn()
        self.assertEqual((receipt['state'], receipt['owner_turn'], len(receipt['reply_message_ids'])),
                         ('complete', 'recorded', 2))      # the partial `length` reply, then the final one
        rows = self.a.rows()
        note = [r for r in rows if r[2] == 'user'][1]
        snap = self.assert_reads_exclude(note[0], 'A synthetic owner message')
        self.assertEqual(snap['excluded'].get('internal_turn_machinery'), 1)
        changes = self.a.get('/chat/changes', after=before['changes']['after']).json()
        self.assertEqual(sorted(c['message']['source']['message'] for c in changes['changes']),
                         sorted(str(r[0]) for r in rows if r[0] != note[0]))

    def test_an_owner_message_with_the_notes_exact_words_stays_owner_speech(self):
        """Equal-text control: of two rows with identical words, only the proven note goes."""
        self.note_turn(message=NOTE)
        rows = [r for r in self.a.rows() if r[2] == 'user']
        self.assertEqual([r[3] for r in rows], [NOTE, NOTE])
        snap = self.assert_reads_exclude(rows[1][0], NOTE)
        self.assertEqual([m['source']['message'] for m in snap['messages'] if m['speaker'] == 'owner'],
                         [str(rows[0][0])])

    def test_provenance_arriving_after_projection_withdraws_the_row(self):
        """The note row committed and projected before its provenance fact exists (it is
        written when Hermes's flush returns): it first shows as an owner row, then the next
        read withdraws it as a change, and snapshot/history no longer have it."""
        pause = self.a.tmp / 'release-note'
        self.a.scenario(note=True, note_pause_file=str(pause))
        body = self.a.body()
        send_id = self.a.post('/chat/sends', body).json()['send']['send_id']
        self.assertTrue(wait_for(lambda: pathlib.Path(str(pause) + '.reached').exists()))
        early = self.a.snapshot()
        owners = [m for m in early['messages'] if m['speaker'] == 'owner']
        self.assertEqual(len(owners), 2)                   # the note, not yet proven internal
        note_msg = owners[1]
        pause.write_text('go')
        self.a.settle(send_id)
        changes = self.a.get('/chat/changes', after=early['changes']['after']).json()
        withdrawn = [c for c in changes['changes'] if c['message']['message_id'] == note_msg['message_id']]
        self.assertEqual([(c['kind'], c['message']['content'], c['message'].get('note')) for c in withdrawn],
                         [('delete', None, 'internal_turn_machinery')])
        self.assert_reads_exclude(note_msg['source']['message'], body['message'])

    def test_rebuild_retention_and_reset_keep_the_exclusion(self):
        """A projection rebuild, pruning the send's receipt, and an explicit reset of a readable
        ledger never turn the known note back into owner speech."""
        _, accepted, _ = self.note_turn()
        note_id = [r for r in self.a.rows() if r[2] == 'user'][1][0]
        for path in (self.a.state / 'chat').rglob('*.sqlite3'):
            path.unlink()                                  # projection rebuild
        self.assert_reads_exclude(note_id, 'A synthetic owner message')
        svc = self.a.app.state.chat_sends.service(self.a.app.state.runtimes['existing'], self.a.home())
        self.assertEqual(svc.prune(now=time.time() + 31 * 86400)[0], 1)   # receipt retention
        con = sp.connect(self.a.ledger(), readonly=True)
        self.assertEqual(con.execute('SELECT count(*) FROM sends').fetchone()[0], 0)
        con.close()
        self.assert_reads_exclude(note_id, 'A synthetic owner message', linked=False)
        reset = self.a.post('/chat/sends/ledger/reset', {'confirm': csr.RESET_CONFIRMATION})
        self.assertEqual(reset.status_code, 200, reset.text)
        for path in (self.a.state / 'chat').rglob('*.sqlite3'):
            path.unlink()                                  # and a rebuild after the reset
        snap = self.assert_reads_exclude(note_id, 'A synthetic owner message', linked=False)
        self.assertEqual(snap['provenance']['state'], 'ok')

    def test_a_reset_that_cannot_read_the_old_ledger_discloses_the_lost_guarantee(self):
        self.note_turn()
        self.a.ledger().write_bytes(b'not a database' * 100)
        lost = self.a.get('/chat/sends/bootstrap')
        self.assertEqual((lost.status_code, lost.json()['error']), (503, 'send_ledger_lost'))
        reset = self.a.post('/chat/sends/ledger/reset', {'confirm': csr.RESET_CONFIRMATION})
        self.assertEqual(reset.status_code, 200, reset.text)
        for path in (self.a.state / 'chat').rglob('*.sqlite3'):
            path.unlink()
        # Rebuilt without the lost provenance, the note reads as the session recorded it, and
        # every read says the guarantee is gone (it is not presented silently).
        snap = self.a.snapshot()
        self.assertEqual(snap['provenance']['state'], 'incomplete')
        self.assertIn('notice', snap['provenance'])
        self.assertEqual(len([m for m in snap['messages'] if m['speaker'] == 'owner']), 2)
        self.assertEqual(self.a.get('/chat/history', before=self.a.snapshot(limit=1)['history']['before']
                                    ).json()['provenance']['state'], 'incomplete')

    def test_an_unreadable_ledger_is_disclosed_on_reads(self):
        self.note_turn()
        os.chmod(self.a.ledger(), 0)
        self.addCleanup(os.chmod, self.a.ledger(), 0o600)
        if os.access(self.a.ledger(), os.R_OK):
            self.skipTest('running as a user that bypasses file permissions')
        snap = self.a.snapshot()
        self.assertEqual((snap['provenance']['state'], snap['provenance']['reason']),
                         ('unavailable', 'ledger_unreadable'))


@unittest.skipUnless(LINUX, POSIX_ONLY)
class Scopes(unittest.TestCase):

    def setUp(self):
        self.a = App(self)

    def test_independent_profiles_with_the_same_key(self):
        """M-17 through HTTP: two profile homes, same client_key and text: two receipts, two
        launches; one profile's send_id, key lookup and operation id are 404 in the other."""
        key = cs.new_ulid()
        _, nova, _ = self.a.send(key=key)
        _, rowan, _ = self.a.send(profile='rowan', key=key)
        n, r = nova['send']['send_id'], rowan['send']['send_id']
        self.assertNotEqual(n, r)
        self.assertEqual((self.a.launches(n), self.a.launches(r, 'rowan')), (1, 1))
        self.assertEqual(self.a.get(f'/chat/sends/{n}', 'rowan').status_code, 404)
        self.assertEqual(self.a.get(f'/chat/sends/{r}').status_code, 404)
        self.assertEqual(self.a.get('/chat/sends', 'rowan', key=key).json()['send_id'], r)
        self.assertEqual(self.a.get('/operations/' + nova['operation']['id'], 'rowan').status_code, 404)
        self.assertEqual(self.a.post(f'/chat/sends/{n}/stop', profile='rowan').status_code, 404)
        rowan_text = {m['content'] for m in self.a.snapshot('rowan')['messages']}
        self.assertEqual(rowan_text, {'A synthetic owner message', 'A synthetic reply.'})
        self.assertEqual({(m['correlation'] or {}).get('send_id') for m in self.a.snapshot('rowan')['messages']}, {r})


class Disabled(unittest.TestCase):
    """Every shipped entry point builds the app without `chat_sends`: nothing is registered."""

    def test_routes_absent_and_phase_1a_reads_unchanged(self):
        a = App(self, enable=False)
        self.assertEqual(a.get('/chat/sends/bootstrap').status_code, 404)
        self.assertEqual(a.post('/chat/sends', {}).status_code, 404)
        self.assertIsNone(a.app.state.operations.guard)
        self.assertFalse(hasattr(a.app.state, 'chat_sends'))
        self.assertIn('/api/chat', {r.path for r in a.app.routes})
        self.assertNotIn('provenance', a.snapshot())
        self.assertNotIn('send provenance', a.get('/chat/sources').json()['capabilities'])
        self.assertFalse(sp.ledger_dir(a.home()).exists())

    def test_a_ledger_left_behind_is_disclosed_not_applied(self):
        a = App(self, enable=False)
        sp.ledger_dir(a.home()).mkdir()
        self.assertEqual(a.snapshot()['provenance']['state'], 'not_applied')

    def test_no_entry_point_enables_it_and_shipped_files_stand_alone(self):
        """No caller passes `chat_sends`; the files release-files.json ships import without any
        unshipped Phase 1B module (no release entry is added in this changeset)."""
        callers = [p for p in list(ROOT.glob('*.py')) + list((ROOT / 'kit').rglob('*.py'))
                   if 'build(' in p.read_text(encoding='utf-8') and 'chat_sends=' in p.read_text(encoding='utf-8')
                   and p.name not in ('server.py',)]
        self.assertEqual(callers, [])
        shipped = json.loads((ROOT / 'release-files.json').read_text())
        for name in ('kit/app/chat_sends.py', 'kit/app/chat_send_routes.py', 'kit/app/send_protocol.py',
                     'kit/app/send_executor.py', 'kit/app/send_quiescence.py'):
            self.assertNotIn(name, shipped)
        with tempfile.TemporaryDirectory() as tmp:
            for name in shipped:
                src = ROOT / name
                if src.is_file():
                    dst = pathlib.Path(tmp) / name
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    dst.write_bytes(src.read_bytes())
            code = ('import sys; sys.path[:0]=[sys.argv[1], sys.argv[1]+"/kit/scripts"]; '
                    'import kit.app.server, kit.app.chat_routes, kit.app.chat_sources, kit.app.chat_projection, '
                    'kit.app.manage, kit.app.runtime, kit.app.terminal')
            proc = subprocess.run([sys.executable, '-c', code, tmp], capture_output=True, text=True, cwd=tmp)
            self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])

    def test_fingerprints_agree(self):
        for args in ((1, 's', 'user', 1.5), (99, 'x_y', 'assistant', 1758700000.123456), (3, 's', 'user', None)):
            self.assertEqual(csrc.fingerprint(*args), sp.fingerprint(*args))


@unittest.skipUnless(LINUX, POSIX_ONLY)
class InstallationGuard(unittest.TestCase):
    """4.7 wired to the real paths, with a SECOND OS PROCESS each time (M-2d). No in-process
    lock is shared between the two sides."""

    def setUp(self):
        self.a = App(self)
        self.work = self.a.tmp / 'proc'
        self.work.mkdir()

    def spawn(self, *args):
        proc = subprocess.Popen([sys.executable, str(PROC), *map(str, args)], cwd=str(ROOT),
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        def reap():
            if proc.poll() is None:
                proc.kill()
            proc.wait(10)
        self.addCleanup(reap)
        return proc

    def read(self, path, timeout=30):
        return wait_for(lambda: json.loads(path.read_text()) if path.exists() else None, timeout)

    def test_a_mutation_in_another_process_refuses_acceptance_and_then_admits(self):
        out, release = self.work / 'hold.json', self.work / 'release'
        self.spawn('hold', self.a.root, out, release)
        self.assertEqual(self.read(out), {'held': True})
        body = self.a.body()
        refused = self.a.post('/chat/sends', body)
        self.assertEqual((refused.status_code, refused.json()['error']), (409, 'installation_busy'))
        con = sp.connect(self.a.ledger(), readonly=True)
        self.assertEqual(con.execute('SELECT count(*) FROM sends').fetchone()[0], 0)
        con.close()
        release.write_text('go')
        accepted = wait_for(lambda: (lambda r: r if r.status_code == 202 else None)(self.a.post('/chat/sends', body)))
        self.assertIsNotNone(accepted)
        self.a.settle(accepted.json()['send']['send_id'])

    def test_an_open_send_refuses_a_mutation_in_another_process(self):
        self.a.scenario(hang=20)
        send_id = self.a.post('/chat/sends', self.a.body()).json()['send']['send_id']
        out = self.work / 'hold.json'
        proc = self.spawn('hold', self.a.root, out, self.work / 'release')
        self.assertEqual(self.read(out), {'refused': 'chat_reply_running'})
        proc.wait(10)
        self.a.post(f'/chat/sends/{send_id}/stop')
        self.a.settle(send_id)
        out2, release = self.work / 'hold2.json', self.work / 'release2'
        self.spawn('hold', self.a.root, out2, release)
        self.assertEqual(self.read(out2), {'held': True})
        release.write_text('go')

    def test_an_app_mutation_is_refused_while_another_process_runs_a_send(self):
        h.scenario(self.a.home(), hang=20)
        out = self.work / 'send.json'
        proc = self.spawn('send', self.a.home(), self.a.state, out)
        started = self.read(out)
        self.assertEqual(started.get('status'), 202, started)
        ops = self.a.app.state.operations
        with self.assertRaisesRegex(ValueError, 'chat reply is still running'):
            ops.submit(str(self.a.root), 'Save Hermes setting', lambda report: None)
        self.assertNotIn(str(self.a.root), ops.busy)          # the refused action left no slot behind
        svc = self.a.app.state.chat_sends.service(self.a.app.state.runtimes['existing'], self.a.home())
        con = sp.connect(svc.db)
        with sp.immediate(con):
            con.execute('UPDATE sends SET stop_requested_at=? WHERE send_id=?', (time.time(), started['send_id']))
        con.close()
        proc.wait(60)
        self.assertEqual(self.read(out)['final'], 'interrupted')
        row = ops.submit(str(self.a.root), 'Save Hermes setting', lambda report: {'saved': True})
        self.assertTrue(wait_for(lambda: ops.get(row['id'])['status'] == 'complete'))

    def test_an_app_mutation_refuses_a_send_in_another_process_for_its_whole_duration(self):
        ops = self.a.app.state.operations
        gate = threading.Event()
        row = ops.submit(str(self.a.root), 'Save Hermes setting', lambda report: gate.wait(30))
        out = self.work / 'send.json'
        proc = self.spawn('send', self.a.home(), self.a.state, out)
        self.assertEqual(self.read(out), {'refused': 'installation_busy'})
        proc.wait(10)
        gate.set()
        self.assertTrue(wait_for(lambda: ops.get(row['id'])['status'] == 'complete'))
        out2 = self.work / 'send2.json'
        proc = self.spawn('send', self.a.home(), self.a.state, out2)
        proc.wait(60)
        self.assertEqual(self.read(out2).get('final'), 'complete')

    def test_the_native_console_holds_the_guard_until_it_ends(self):
        """The console is an installation mutation: while it runs another process's send is
        refused; when its process ends the hold is released (and on a refused open, at once)."""
        from kit.app.terminal import Consoles

        gate = self.work / 'console-end'

        class Runtime:
            root = self.a.root
            def command(self):
                return [sys.executable, '-c', 'import os,sys,time\nwhile not os.path.exists(sys.argv[1]): '
                        'time.sleep(0.02)', str(gate)]
            def env(self, home):
                return {'PATH': '/usr/bin:/bin', 'HOME': str(home)}
        hold = cs.hold_installation(self.a.root)
        consoles = Consoles()
        console = consoles.open(Runtime(), self.a.home(), 'setup', hold=hold)
        out = self.work / 'send.json'
        self.spawn('send', self.a.home(), self.a.state, out).wait(20)
        self.assertEqual(self.read(out), {'refused': 'installation_busy'})
        gate.write_text('end')
        self.assertTrue(wait_for(lambda: console.finished, 20))
        second = cs.hold_installation(self.a.root)      # released by the console's end
        with self.assertRaises(ValueError):
            consoles.open(Runtime(), self.a.home(), 'nonsense', hold=second)
        cs.hold_installation(self.a.root).release()     # the refused open released its hold

    def test_the_application_update_scope_is_not_an_installation(self):
        self.assertIsNone(self.a.app.state.chat_sends.guard(str(ROOT)))


if __name__ == '__main__':
    unittest.main()
