"""Phase 1A: the owner's private conversation, read from sources that stay
read-only, projected into an app-owned index with stable IDs, and read through
snapshot / history / changes contracts.

BOUNDARY: source store (a Hermes-schema state.db built by tests/chat_fixtures)
-> adapter -> projection. No provider, transport or UI is exercised here.
"""
import contextlib
import datetime as dt
import hashlib
import json
import pathlib
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts'), str(ROOT / 'tests')]

import companion_config as cc  # noqa: E402
import companion_outbox as outbox  # noqa: E402
from chat_fixtures import HermesStore, OWNER_TELEGRAM, STRANGER_TELEGRAM, standard_sessions  # noqa: E402
from kit.app import chat_projection as cp, chat_sources as cs, runtime as hr  # noqa: E402


class Clock:
    def __init__(self, t=1000.0):self.t = t
    def __call__(self):return self.t


class ProjectionCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        base = pathlib.Path(self.tmp.name)
        self.root = base / 'hermes';self.state = base / 'state'
        self.c = self.companion('nova')
        self.store = HermesStore(self.c.home)
        standard_sessions(self.store)
        hr.note_workspace_session(self.c, 'web')
        self.binding = cs.OwnerBinding(telegram=(OWNER_TELEGRAM,), origin='owner-file')
        self.clock = Clock()

    def companion(self, profile, agent='Nova'):
        c = cc.Companion(agent=agent, human='Robin', profile=profile, hermes_root=self.root,
                         vault=pathlib.Path(self.tmp.name) / 'vault', context_mode='fixed', timezone='UTC')
        c.home.mkdir(parents=True, exist_ok=True)
        return c

    def projection(self, c=None, binding=None, installation='existing'):
        c = c or self.c;binding = binding or self.binding
        scope = cp.ChatScope(installation, c.profile or 'default', str(c.home.resolve()), binding.digest())
        return cp.Projection(self.state, scope, clock=self.clock), cs.HermesSource(c, binding)

    def sync(self, c=None, binding=None, **kw):
        projection, source = self.projection(c, binding)
        stats = projection.sync(source, **kw)
        return projection, stats

    def contents(self, page):
        return [m['content'] for m in page['messages']]

    def all_history(self, projection, limit=2):
        page = projection.snapshot(limit);out = list(page['messages'])
        cursor = page['history']['before']
        while cursor:
            older = projection.history(cursor, limit)
            out = older['messages'] + out;cursor = older['history']['before']
        return out


class BoundaryTests(ProjectionCase):
    def test_trusted_workspace_terminal_and_telegram_appear_together(self):
        s = self.store
        s.say('web', 'user', 'from the workspace', 10);s.say('web', 'assistant', 'hello at the desk', 11)
        s.say('term', 'user', 'from a terminal', 12)
        s.say('tg', 'user', 'from telegram', 13, platform_message_id='77');s.say('tg', 'assistant', 'hi on telegram', 14)
        s.say('tg-old', 'user', 'older telegram row', 15)
        projection, _ = self.sync()
        page = projection.snapshot()
        self.assertEqual(self.contents(page), ['from the workspace', 'hello at the desk', 'from a terminal',
                                               'from telegram', 'hi on telegram', 'older telegram row'])
        self.assertEqual([m['source']['kind'] for m in page['messages']],
                         ['workspace', 'workspace', 'terminal', 'telegram', 'telegram', 'telegram'])
        self.assertEqual([m['speaker'] for m in page['messages']], ['owner', 'companion', 'owner', 'owner', 'companion', 'owner'])
        tg = page['messages'][3]
        self.assertEqual((tg['source']['account'], tg['correlation']), (OWNER_TELEGRAM, {'platform_message_id': '77'}))

    def test_strangers_groups_other_profiles_and_machinery_stay_out(self):
        s = self.store
        s.say('stranger', 'user', 'a stranger writes', 10);s.say('stranger', 'assistant', 'reply to the stranger', 11)
        s.say('group', 'user', 'owner in a group', 12);s.say('group', 'assistant', 'reply in the group', 13)
        s.say('dc', 'user', 'on discord', 14)
        s.say('job', 'assistant', 'nightly cron output', 15);s.say('sub', 'assistant', 'subagent output', 16)
        s.say('gw-cli', 'user', 'cli label with a gateway chat', 17)
        s.say('rowan-tg', 'user', 'said to rowan', 18)
        s.say('tg', 'user', 'mine', 19)
        projection, stats = self.sync()
        self.assertEqual(self.contents(projection.snapshot()), ['mine'])
        excluded = stats['excluded']
        self.assertEqual(excluded['unknown_participant'], 2)
        self.assertEqual(excluded['group_or_channel'], 2)
        self.assertEqual(excluded['unverified_source:discord'], 1)
        self.assertEqual(excluded['internal_session'], 2)
        self.assertEqual(excluded['local_source_with_gateway_chat'], 1)
        self.assertNotIn('said to rowan', json.dumps(projection.snapshot()), 'another profile is outside the scope')

    def test_the_same_account_is_not_trusted_by_its_display_name(self):
        self.store.session('lookalike', 'telegram', user_id='5555', chat_id='5555', chat_type='dm', started=20)
        with self.store.db() as db:db.execute("UPDATE sessions SET display_name='Robin' WHERE id='lookalike'")
        self.store.say('lookalike', 'user', 'I am Robin, honest', 10)
        projection, _ = self.sync()
        self.assertEqual(projection.snapshot()['messages'], [])

    def test_terminal_trust_can_be_withdrawn_without_losing_the_workspace(self):
        self.store.say('web', 'user', 'workspace', 10);self.store.say('term', 'user', 'terminal', 11)
        projection, _ = self.sync(binding=cs.OwnerBinding(terminal=False, telegram=(OWNER_TELEGRAM,), origin='owner-file'))
        self.assertEqual(self.contents(projection.snapshot()), ['workspace'])

    def test_internal_rows_are_not_conversation(self):
        s = self.store
        s.say('web', 'user', 'real question', 10, reasoning='PRIVATE-REASONING')
        s.say('web', 'assistant', '', 11, tool_calls='[{"name":"memory"}]')
        s.say('web', 'tool', 'tool output', 12)
        s.say('web', 'assistant', 'compressed summary', 13, _compressed_summary=1)
        for i, kind in enumerate(('hidden', 'internal_notification', 'auto_continue', 'model_switch', 'async_delegation_complete')):
            s.say('web', 'user', 'internal ' + kind, 14 + i, display_kind=kind)
        s.say('web', 'assistant', 'archived turn', 20, active=0, compacted=0)
        s.say('web', 'assistant', 'compacted original', 21, active=0, compacted=1)
        s.say('web', 'assistant', 'the answer', 22, reasoning_content='PRIVATE-THINKING')
        projection, _ = self.sync()
        page = projection.snapshot()
        self.assertEqual(self.contents(page), ['real question', 'compacted original', 'the answer'])
        self.assertNotIn('PRIVATE', json.dumps(page))

    def test_delivered_outreach_is_distinguished_from_cron_output(self):
        """The cron session's own output never appears. A proactive message
        Hermes delivered and mirrored into the owner's DM appears as the
        companion speaking on Telegram. Outbox entries are never joined by
        text, and a queued/withheld one never appears at all."""
        self.c.life.mkdir(parents=True, exist_ok=True)
        now = dt.datetime(2026, 9, 24, 9, tzinfo=dt.timezone.utc)
        sent = outbox.queue(self.c, {'body': 'Good morning, did you sleep?'}, now)['entry']
        outbox.mark(self.c, sent['id'], 'sent', 'sent', now)
        outbox.queue(self.c, {'body': 'An idea I never sent'}, now)
        self.store.say('job', 'assistant', 'Good morning, did you sleep?', 30)       # the generating run
        self.store.say('tg', 'assistant', 'Good morning, did you sleep?', 31)        # Hermes's delivery mirror
        self.store.say('tg', 'user', '[Cron delivery: morning]\nWeather brief', 32)  # role=user cron mirror
        projection, _ = self.sync()
        page = projection.snapshot()
        self.assertEqual(self.contents(page), ['Good morning, did you sleep?', '[Cron delivery: morning]\nWeather brief'])
        delivered, brief = page['messages']
        self.assertEqual((delivered['speaker'], delivered['source']['kind'], delivered['correlation']), ('companion', 'telegram', None))
        self.assertEqual(brief['speaker'], 'unverified', 'a cron mirror is not presented as the owner')
        self.assertIn('not verified', brief['note'])
        self.assertNotIn('An idea I never sent', json.dumps(page))
        self.assertEqual(cs.capabilities()['outbox (proactive delivery)']['status'], 'linkage unavailable')


class IdentityTests(ProjectionCase):
    def test_identical_text_with_distinct_ids_stays_distinct(self):
        for t in (10, 11, 12):self.store.say('tg', 'user', 'hi', t)
        projection, _ = self.sync()
        page = projection.snapshot()
        self.assertEqual(self.contents(page), ['hi', 'hi', 'hi'])
        self.assertEqual(len({m['message_id'] for m in page['messages']}), 3)

    def test_replay_of_the_same_source_identity_is_one_message(self):
        self.store.say('tg', 'user', 'once', 10)
        projection, _ = self.sync()
        first = projection.snapshot()
        for _ in range(3):projection.sync(self.projection()[1], force_reconcile=True)
        again = projection.snapshot()
        self.assertEqual(again['messages'], first['messages'])
        self.assertEqual(projection.changes(first['changes']['after'])['changes'], [], 'a replay is not a change')
        # A pushed webhook replay with the same source identity: still one.
        rec = cs.SourceRecord('telegram-webhook:4242:77', 'telegram', OWNER_TELEGRAM, OWNER_TELEGRAM, 'tg', '77', '77',
                              'owner', 50.0, 'pushed', True, source_revision=1.0)
        projection.apply_records([rec]);projection.apply_records([rec])
        self.assertEqual(self.contents(projection.snapshot()).count('pushed'), 1)

    def test_a_replayed_old_event_does_not_resurrect_edited_or_deleted_content(self):
        projection, _ = self.projection()
        base = dict(source_key='telegram-webhook:4242:9', source_kind='telegram', source_account=OWNER_TELEGRAM,
                    source_channel=OWNER_TELEGRAM, source_session='tg', source_message='9', platform_message_id='9',
                    speaker='owner', occurred_at=60.0)
        projection.apply_records([cs.SourceRecord(**base, content='first draft', visible=True, source_revision=1.0)])
        projection.apply_records([cs.SourceRecord(**base, content='edited', visible=True, source_revision=2.0)])
        projection.apply_records([cs.SourceRecord(**base, content='first draft', visible=True, source_revision=1.0)])
        self.assertEqual(self.contents(projection.snapshot()), ['edited'])
        projection.apply_records([cs.SourceRecord(**base, content='', visible=False, source_revision=3.0)])
        for rev, text in ((1.0, 'first draft'), (2.0, 'edited')):
            projection.apply_records([cs.SourceRecord(**base, content=text, visible=True, source_revision=rev)])
        self.assertEqual(projection.snapshot()['messages'], [], 'deletion stands against replays')

    def test_ids_survive_a_restart(self):
        self.store.say('tg', 'user', 'hello', 10)
        projection, _ = self.sync()
        before = projection.snapshot()
        restarted, source = self.projection()
        restarted.sync(source)
        after = restarted.snapshot()
        self.assertEqual([m['message_id'] for m in after['messages']], [m['message_id'] for m in before['messages']])
        self.assertEqual(restarted.changes(before['changes']['after'])['changes'], [])

    def test_an_interrupted_sync_leaves_the_last_consistent_state(self):
        self.store.say('tg', 'user', 'one', 10)
        projection, _ = self.sync()
        snap = projection.snapshot()
        self.store.say('tg', 'user', 'two', 11)
        real = cp.Projection._apply
        def crash(self_, con, record, now):
            real(self_, con, record, now);raise KeyboardInterrupt
        with mock.patch.object(cp.Projection, '_apply', crash), self.assertRaises(KeyboardInterrupt):
            projection.sync(self.projection()[1])
        self.assertEqual(projection.snapshot(), snap, 'rolled back')
        projection.sync(self.projection()[1])
        self.assertEqual(self.contents(projection.snapshot()), ['one', 'two'])


class OrderingTests(ProjectionCase):
    def test_identical_timestamps_page_with_a_stable_tie_breaker(self):
        for i in range(7):self.store.say('tg', 'user', f'm{i}', 100.0)
        projection, _ = self.sync()
        seen = self.all_history(projection, limit=2)
        self.assertEqual(sorted(m['content'] for m in seen), [f'm{i}' for i in range(7)])
        self.assertEqual(len({m['message_id'] for m in seen}), 7, 'no duplicates or gaps across pages')
        self.assertEqual([m['message_id'] for m in seen], sorted(m['message_id'] for m in seen))

    def test_a_message_arriving_after_the_snapshot_arrives_as_a_change(self):
        self.store.say('tg', 'user', 'before', 10)
        projection, _ = self.sync()
        snap = projection.snapshot()
        self.store.say('tg', 'assistant', 'during', 11)   # lands between history and change read
        projection.sync(self.projection()[1])
        changes = projection.changes(snap['changes']['after'])
        self.assertEqual([(c['kind'], c['message']['content']) for c in changes['changes']], [('insert', 'during')])
        self.assertNotIn('during', self.contents(snap))
        self.assertEqual(projection.changes(changes['after'])['changes'], [], 'the next read starts after it')

    def test_a_backdated_import_is_a_change_today_and_history_yesterday(self):
        self.store.say('tg', 'user', 'today', 2000)
        projection, _ = self.sync()
        snap = projection.snapshot()
        self.store.say('tg', 'user', 'yesterday, imported late', 1000)
        projection.sync(self.projection()[1])
        [change] = projection.changes(snap['changes']['after'])['changes']
        self.assertEqual(change['message']['content'], 'yesterday, imported late')
        self.assertEqual(self.contents(projection.snapshot()), ['yesterday, imported late', 'today'])
        self.assertLess(change['message']['occurred_at'], snap['messages'][0]['occurred_at'])

    def test_edits_and_deletions_change_revision_not_identity(self):
        a = self.store.say('tg', 'user', 'original', 10);b = self.store.say('tg', 'user', 'to delete', 11)
        c = self.store.say('tg', 'assistant', 'to hide', 12)
        projection, _ = self.sync()
        snap = projection.snapshot()
        ids = {m['content']: m['message_id'] for m in snap['messages']}
        self.store.update(a, content='corrected');self.store.delete(b);self.store.update(c, active=0)
        projection.sync(self.projection()[1], force_reconcile=True)
        changes = projection.changes(snap['changes']['after'])['changes']
        by_id = {ch['message']['message_id']: ch for ch in changes}
        self.assertEqual((by_id[ids['original']]['kind'], by_id[ids['original']]['revision'],
                          by_id[ids['original']]['message']['content']), ('edit', 2, 'corrected'))
        self.assertEqual(by_id[ids['original']]['message']['status'], 'edited')
        for gone in ('to delete', 'to hide'):
            self.assertEqual((by_id[ids[gone]]['kind'], by_id[ids[gone]]['message']['content']), ('delete', None))
        self.assertEqual(self.contents(projection.snapshot()), ['corrected'])
        with contextlib.closing(sqlite3.connect(projection.path)) as con, con:
            self.assertNotIn('to delete', json.dumps(con.execute('SELECT content FROM messages').fetchall()),
                             'the projection keeps no copy of deleted content')

    def test_reconciliation_is_bounded_per_call_and_resumes(self):
        self.store.many('tg', [('user', f'n{i}', float(i)) for i in range(25)])
        projection, _ = self.sync()
        with mock.patch.object(cp, 'RECONCILE_CHUNK', 10), mock.patch.object(cp, 'RECONCILE_INTERVAL', 0):
            self.store.update(25, content='edited last')
            calls = [projection.sync(self.projection()[1]) for _ in range(3)]
        self.assertEqual([c.get('edited', 0) for c in calls], [0, 0, 1], 'found on the chunk that covers it')


class ResyncTests(ProjectionCase):
    def test_a_replaced_source_store_invalidates_old_cursors(self):
        for t in range(5):self.store.say('tg', 'user', f'old {t}', t)
        projection, _ = self.sync()
        snap = projection.snapshot(2)
        # Restore an unrelated copy over state.db: same ids, different rows.
        self.store.path.unlink()
        other = HermesStore(self.c.home);standard_sessions(other)
        for t in range(5):other.say('tg', 'user', f'restored {t}', 100 + t)
        stats = projection.sync(self.projection()[1])
        self.assertEqual(stats['rebuilt'], 'source_replaced')
        for read in (lambda: projection.history(snap['history']['before']), lambda: projection.changes(snap['changes']['after'])):
            with self.assertRaises(cp.ResyncRequired) as caught:read()
            self.assertEqual(caught.exception.reason, 'projection_rebuilt')
        fresh = projection.snapshot()
        self.assertEqual(self.contents(fresh), [f'restored {t}' for t in range(5)])
        self.assertFalse({m['message_id'] for m in fresh['messages']} & {m['message_id'] for m in snap['messages']},
                         'old ids are not aliased to different messages')

    def test_an_older_backup_restored_is_detected_by_its_sequence(self):
        self.store.say('tg', 'user', 'a', 1)
        backup = self.store.path.with_suffix('.bak');shutil.copy(self.store.path, backup)
        self.store.say('tg', 'user', 'b', 2)
        projection, _ = self.sync()
        shutil.copy(backup, self.store.path)
        self.assertEqual(projection.sync(self.projection()[1])['rebuilt'], 'source_replaced')

    def test_changes_older_than_the_retained_window_require_a_resync(self):
        self.store.say('tg', 'user', 'first', 1)
        projection, _ = self.sync()
        snap = projection.snapshot()
        with mock.patch.object(cp, 'RETAIN_CHANGES', 3):
            for i in range(6):self.store.say('tg', 'user', f'more {i}', 10 + i)
            projection.sync(self.projection()[1])
        with self.assertRaises(cp.ResyncRequired) as caught:projection.changes(snap['changes']['after'])
        self.assertEqual(caught.exception.reason, 'changes_expired')

    def test_one_companions_cursor_is_refused_for_another(self):
        other = self.companion('rowan', 'Rowan');store = HermesStore(other.home)
        store.session('tg', 'telegram', profile='rowan', user_id=OWNER_TELEGRAM, chat_id=OWNER_TELEGRAM, chat_type='dm')
        for t in range(3):
            self.store.say('tg', 'user', f'nova {t}', t);store.say('tg', 'user', f'rowan {t}', t)
        nova, _ = self.sync()
        rowan, _ = self.sync(other)
        snap = nova.snapshot(1)
        for read in (lambda: rowan.history(snap['history']['before']), lambda: rowan.changes(snap['changes']['after'])):
            with self.assertRaises(cp.CursorError) as caught:read()
            self.assertIn('another conversation', str(caught.exception))
        tampered = snap['history']['before'][:-4] + 'abcd'
        with self.assertRaises(cp.CursorError):nova.history(tampered)

    def test_changing_the_owner_binding_stops_serving_what_it_authorised(self):
        self.store.say('tg', 'user', 'telegram secret', 10);self.store.say('web', 'user', 'workspace', 11)
        projection, _ = self.sync()
        snap = projection.snapshot()
        self.assertIn('telegram secret', self.contents(snap))
        revoked = cs.OwnerBinding(origin='owner-file')
        after, _ = self.projection(binding=revoked)
        with self.assertRaises(cp.ResyncRequired):after.snapshot()
        after.sync(self.projection(binding=revoked)[1])
        with self.assertRaises(cp.ResyncRequired):after.changes(snap['changes']['after'])
        self.assertEqual(self.contents(after.snapshot()), ['workspace'])
        with contextlib.closing(sqlite3.connect(after.path)) as con, con:
            self.assertNotIn('telegram secret', json.dumps(con.execute('SELECT content FROM messages').fetchall()))


class SourceSafetyTests(ProjectionCase):
    def test_source_files_stay_byte_for_byte_unchanged(self):
        self.c.life.mkdir(parents=True, exist_ok=True)
        now = dt.datetime(2026, 9, 24, 9, tzinfo=dt.timezone.utc)
        outbox.mark(self.c, outbox.queue(self.c, {'body': 'hello'}, now)['entry']['id'], 'sent', 'sent', now)
        for t in range(20):self.store.say('tg', 'user', f'm{t}', t)
        watched = [self.store.path, outbox.path_for(self.c), hr.workspace_sessions_path(self.c)]
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in watched}
        projection, _ = self.sync()
        snap = projection.snapshot(5);projection.history(snap['history']['before'])
        projection.sync(self.projection()[1], force_reconcile=True);projection.changes(snap['changes']['after'])
        self.assertEqual({p: hashlib.sha256(p.read_bytes()).hexdigest() for p in watched}, before)
        self.assertEqual(sorted(p.name for p in self.c.home.iterdir() if p.name.startswith('state.db')), ['state.db'],
                         'no journal or WAL was created beside the source')
        self.assertFalse(str(projection.path).startswith(str(self.c.home)), 'derived state lives outside the source home')
        if sys.platform != 'win32':
            self.assertEqual(projection.path.stat().st_mode & 0o777, 0o600)

    def test_an_unreadable_source_is_a_recoverable_error(self):
        self.store.say('tg', 'user', 'kept', 1)
        projection, _ = self.sync()
        snap = projection.snapshot()
        good = self.store.path.read_bytes()
        self.store.path.write_bytes(b'not a database' * 100)
        with self.assertRaises(cs.SourceUnavailable):projection.sync(self.projection()[1])
        self.assertEqual(projection.snapshot(), snap, 'the projection was not touched')
        self.store.path.write_bytes(good)
        projection.sync(self.projection()[1])
        self.assertEqual(self.contents(projection.snapshot()), ['kept'])

    def test_a_messages_table_without_stable_ids_is_unsupported(self):
        self.store.path.unlink()
        with contextlib.closing(sqlite3.connect(self.store.path)) as db, db:
            db.executescript('CREATE TABLE sessions(id TEXT, source TEXT, started_at REAL, profile_name TEXT);'
                             'CREATE TABLE messages(session_id TEXT, role TEXT, content TEXT, timestamp REAL);')
        with self.assertRaises(cs.SourceUnavailable):self.sync()

    def test_the_owner_binding_file_and_allowlist(self):
        self.assertEqual(cs.owner_binding(self.c).origin, 'none')
        (self.c.home / '.env').write_text('TELEGRAM_ALLOWED_USERS=4242\n')
        self.assertEqual((cs.owner_binding(self.c).telegram, cs.owner_binding(self.c).origin), (('4242',), 'telegram-allowlist-single'))
        (self.c.home / '.env').write_text('TELEGRAM_ALLOWED_USERS=4242,9999\n')
        self.assertEqual((cs.owner_binding(self.c).telegram, cs.owner_binding(self.c).origin), ((), 'telegram-allowlist-ambiguous'))
        (self.c.home / cs.BINDING_FILE).write_text(json.dumps({'telegram': ['9999'], 'terminal': False}))
        b = cs.owner_binding(self.c)
        self.assertEqual((b.telegram, b.terminal, b.origin), (('9999',), False, 'owner-file'))
        (self.c.home / cs.BINDING_FILE).write_text('{broken')
        with self.assertRaises(cs.SourceUnavailable):cs.owner_binding(self.c)


class ScaleTests(ProjectionCase):
    """50,000 synthetic messages: bounded pages, indexed reads, no all-history download."""
    N = 50000

    def test_fifty_thousand_messages(self):
        import time
        rows = [('user' if i % 2 else 'assistant', f'message {i} ' + 'x' * (i % 80), 1_700_000_000 + i // 3) for i in range(self.N)]
        self.store.many('tg', rows[:self.N // 2]);self.store.many('web', rows[self.N // 2:])
        projection, _ = self.projection()
        started = time.perf_counter();syncs = 0
        while True:
            stats = projection.sync(self.projection()[1]);syncs += 1
            if stats['caught_up']:break
        initial = time.perf_counter() - started
        started = time.perf_counter();snap = projection.snapshot();snapshot_s = time.perf_counter() - started
        size = len(json.dumps(snap))
        started = time.perf_counter()
        cursor = snap['history']['before']
        for _ in range(50):
            page = projection.history(cursor, 60);cursor = page['history']['before']
        page_s = (time.perf_counter() - started) / 50
        started = time.perf_counter();idle = projection.sync(self.projection()[1]);idle_s = time.perf_counter() - started
        started = time.perf_counter();projection.sync(self.projection()[1], force_reconcile=True);full_s = time.perf_counter() - started
        with contextlib.closing(sqlite3.connect(projection.path)) as con, con:
            plan = ' '.join(r[3] for r in con.execute(
                "EXPLAIN QUERY PLAN SELECT * FROM messages WHERE status<>'deleted' AND (sort_at<? OR (sort_at=? AND message_id<?)) "
                "ORDER BY sort_at DESC, message_id DESC LIMIT 61", (1e12, 1e12, 'z')))
        report = {'messages': self.N, 'initial_sync_s': round(initial, 2), 'initial_sync_calls': syncs,
                  'snapshot_s': round(snapshot_s, 4), 'snapshot_bytes': size, 'history_page_s': round(page_s, 4),
                  'idle_sync_s': round(idle_s, 4), 'full_reconcile_s': round(full_s, 2),
                  'projection_bytes': projection.path.stat().st_size, 'history_plan': plan}
        print('\nSCALE', json.dumps(report))
        self.assertEqual(len(snap['messages']), 60)
        self.assertLess(size, 40000, 'a snapshot is one page, not the history')
        self.assertIn('messages_history', plan, 'history pages are an index walk, not a scan')
        self.assertGreaterEqual(syncs, self.N // cp.SYNC_MAX_ROWS, 'initial indexing is split into bounded calls')
        self.assertLess(page_s, 0.25);self.assertLess(idle_s, 1.0)


if __name__ == '__main__':
    unittest.main()
