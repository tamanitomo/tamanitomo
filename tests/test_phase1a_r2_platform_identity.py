"""Phase 1A review R2 F3: a known platform message id is part of a source
row's identity.

Telegram identifies a message by its message_id WITHIN a chat. Two different
known ids in the same account/chat are two messages, whatever the Hermes row
id, session, role, timestamp or text say. Such a row is never folded in as an
edit or a replay under the old opaque id; the projection starts a new
generation and old cursors resync.

BOUNDARY: source store (tests/chat_fixtures) -> adapter -> projection.
"""
import contextlib
import pathlib
import sqlite3
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts'), str(ROOT / 'tests')]

from chat_fixtures import OWNER_TELEGRAM  # noqa: E402
from kit.app import chat_projection as cp, chat_sources as cs  # noqa: E402
from test_chat_projection import ProjectionCase  # noqa: E402

REBUILT = ('source_replaced', 'source_identity_changed')


class PlatformIdentityTests(ProjectionCase):
    def by_source(self, projection):
        return {m['source']['message']: m for m in self.all_history(projection, 200)}

    def pid(self, message):
        return (message['correlation'] or {}).get('platform_message_id')

    def assert_new_generation(self, projection, snap, old, stats, target, content, pid):
        self.assertIn(stats['rebuilt'], REBUILT)
        for read in (lambda: projection.history(snap['history']['before']), lambda: projection.changes(snap['changes']['after'])):
            with self.assertRaises(cp.ResyncRequired):read()
        now = self.by_source(projection)
        self.assertEqual((now[target]['content'], self.pid(now[target]), now[target]['revision']), (content, pid, 1))
        self.assertFalse({m['message_id'] for m in now.values()} & {m['message_id'] for m in old.values()},
                         'no old opaque id reused')

    def test_a_different_platform_id_with_different_text_is_not_an_edit(self):
        # 400 rows, target outside the identity sample: the apply path itself
        # must refuse, not only the sample.
        self.store.many('tg', [('user', f'n{i}', float(i)) for i in range(400)])
        projection, _ = self.sync()
        snap = projection.snapshot(2)
        target = 251
        with contextlib.closing(sqlite3.connect(projection.path)) as con:
            step = max(1, con.execute('SELECT count(*) FROM messages').fetchone()[0] // cp.IDENTITY_SAMPLE)
            sampled = {r[0] for r in con.execute('SELECT source_id FROM messages WHERE (pk % ?)=0 LIMIT ?', (step, cp.IDENTITY_SAMPLE + 1))}
        self.assertNotIn(target, sampled)
        old = self.by_source(projection)
        before = self.pid(old[str(target)])
        self.assertTrue(before)
        self.store.update(target, platform_message_id='900900', content='a different message')
        stats = projection.sync(self.projection()[1], force_reconcile=True)
        self.assert_new_generation(projection, snap, old, stats, str(target), 'a different message', '900900')

    def test_a_different_platform_id_with_identical_text_is_not_a_replay(self):
        for t in range(5):self.store.say('tg', 'user', f'm{t}', 100 + t)
        projection, _ = self.sync()
        snap = projection.snapshot(2)
        old = self.by_source(projection)
        self.store.update(3, platform_message_id='900900')
        stats = projection.sync(self.projection()[1], force_reconcile=True)
        self.assert_new_generation(projection, snap, old, stats, '3', 'm2', '900900')

    def test_an_ordinary_edit_with_the_same_platform_id_keeps_its_id(self):
        for t in range(5):self.store.say('tg', 'user', f'm{t}', 100 + t)
        projection, _ = self.sync()
        snap = projection.snapshot(2)
        old = self.by_source(projection)['3']
        self.store.update(3, content='m2, corrected')
        stats = projection.sync(self.projection()[1], force_reconcile=True)
        self.assertIsNone(stats['rebuilt'])
        [change] = projection.changes(snap['changes']['after'])['changes']
        self.assertEqual((change['kind'], change['message']['message_id'], change['message']['revision'],
                          change['message']['content'], self.pid(change['message'])),
                         ('edit', old['message_id'], 2, 'm2, corrected', self.pid(old)))

    def test_missing_to_known_enriches_and_loss_keeps_the_known_id(self):
        """Missing -> known: the same message gains a correlation (a revision,
        no new id). Known -> missing: the recorded id is kept, not erased, so a
        later DIFFERENT id still conflicts with it."""
        ident = self.store.say('tg', 'assistant', 'reply', 100)
        projection, _ = self.sync()
        snap = projection.snapshot()
        [first] = snap['messages']
        self.assertIsNone(first['correlation'])
        self.store.update(ident, platform_message_id='555')
        stats = projection.sync(self.projection()[1], force_reconcile=True)
        self.assertIsNone(stats['rebuilt'])
        [change] = projection.changes(snap['changes']['after'])['changes']
        self.assertEqual((change['message']['message_id'], change['message']['revision'], self.pid(change['message'])),
                         (first['message_id'], 2, '555'))
        mark = projection.snapshot()
        self.store.update(ident, platform_message_id=None)
        stats = projection.sync(self.projection()[1], force_reconcile=True)
        self.assertIsNone(stats['rebuilt'])
        self.assertEqual(projection.changes(mark['changes']['after'])['changes'], [], 'loss is not a new message')
        self.assertEqual(self.pid(projection.snapshot()['messages'][0]), '555', 'the known id is kept')
        self.store.update(ident, platform_message_id='556')
        stats = projection.sync(self.projection()[1], force_reconcile=True)
        self.assertIn(stats['rebuilt'], REBUILT, 'missing evidence is no licence to reuse the id')
        [now] = projection.snapshot()['messages']
        self.assertNotEqual(now['message_id'], first['message_id'])
        self.assertEqual(self.pid(now), '556')

    def test_an_owner_row_that_loses_its_id_then_gains_another_is_not_restored(self):
        for t in range(3):self.store.say('tg', 'user', f'm{t}', 100 + t)
        projection, _ = self.sync()
        old = self.by_source(projection)
        self.store.update(2, platform_message_id=None)
        projection.sync(self.projection()[1], force_reconcile=True)
        self.assertNotIn('2', {m['source']['message'] for m in projection.snapshot()['messages']},
                         'an owner row without its id is unverified')
        self.store.update(2, platform_message_id='900900')
        stats = projection.sync(self.projection()[1], force_reconcile=True)
        self.assertIn(stats['rebuilt'], REBUILT)
        now = self.by_source(projection)
        self.assertNotEqual(now['2']['message_id'], old['2']['message_id'])
        self.assertEqual(self.pid(now['2']), '900900')

    def test_the_same_bare_platform_id_in_two_chats_is_two_messages(self):
        second = '5151'
        self.store.session('tg2', 'telegram', user_id=second, chat_id=second, chat_type='dm', started=12)
        self.store.say('tg', 'user', 'same words', 100, platform_message_id='777')
        self.store.say('tg2', 'user', 'same words', 100, platform_message_id='777')
        binding = cs.OwnerBinding(telegram=(OWNER_TELEGRAM, second), origin='owner-file')
        projection, stats = self.sync(binding=binding)
        messages = projection.snapshot()['messages']
        self.assertEqual(len(messages), 2)
        self.assertEqual({(m['source']['channel'], self.pid(m)) for m in messages}, {(OWNER_TELEGRAM, '777'), (second, '777')})
        self.assertEqual(len({m['message_id'] for m in messages}), 2)
        stats = projection.sync(self.projection(binding=binding)[1], force_reconcile=True)
        self.assertIsNone(stats['rebuilt'])


if __name__ == '__main__':
    unittest.main()
