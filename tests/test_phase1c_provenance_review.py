"""Reviewer regression for known lost provenance in Phase 1C (synthetic stores only).

Copy into tests/ in the reviewed repository. No live home, model, send, or network
is used. This seeds the existing read-model state produced by a reset that could
not preserve old provenance; it does not retest or change the reset mechanism.
"""
import unittest

import companion_checkin as checkin
import companion_context as ctx
import companion_local_reflection as refl
from kit.app import chat_sends, send_protocol as sp
from tests.test_phase1c_continuity import Profile, T, at, empty


NOTE = '[System: Continue exactly where you left off. Do not restart or repeat prior text.]'


class KnownProvenanceLoss(unittest.TestCase):
    def setUp(self):
        self.p = Profile(self)
        self.c = self.p.c['nova']
        self.note_id = self.p.store.say('web', 'user', NOTE, T + 8200)
        directory = sp.ledger_dir(self.c.home)
        directory.mkdir()
        self.ledger = directory / sp.LEDGER_FILE
        con = sp.connect(self.ledger, create=True)
        try:
            con.executescript(sp.SCHEMA)
            con.execute('INSERT INTO provenance(kind,session_id,row_id,fingerprint,send_id,recorded_at) '
                        'VALUES (?,?,?,?,?,?)',
                        ('internal_row', 'web', self.note_id,
                         sp.fingerprint(self.note_id, 'web', 'user', T + 8200),
                         'synthetic-receipt', T + 8500))
        finally:
            con.close()

    def lose_provenance(self):
        con = sp.connect(self.ledger)
        try:
            con.execute('DELETE FROM provenance')
            con.execute('INSERT INTO meta(key,value) VALUES (?,?)',
                        ('provenance_lost_at', str(T + 8600)))
        finally:
            con.close()
        self.assertEqual(chat_sends.read_model(self.c.home).state, 'incomplete')

    def test_readable_provenance_excludes_only_the_proven_internal_row(self):
        owner_id = self.p.store.say('term', 'user', NOTE, T + 8300)
        rows, *_ = refl.trusted_messages(self.c, at(-10), at(9000))
        ids = {r['id'] for r in rows}
        self.assertNotIn(str(self.note_id), ids)
        self.assertIn(str(owner_id), ids, 'equal words are not an identity policy')

    def test_known_lost_provenance_is_not_certified_as_trusted_quotes(self):
        self.lose_provenance()
        with self.assertRaises(ValueError):
            refl.trusted_messages(self.c, at(-10), at(9000))

    def test_reflection_refuses_before_model_attempt_or_watermark_movement(self):
        self.lose_provenance()
        checkin.flag(self.c, at(9000), platform='telegram')
        before = checkin.read(self.c)
        calls = []
        with self.assertRaises(ValueError):
            refl.reflect(self.c, 'checkin', 'http://127.0.0.1:1', 'synthetic',
                         now=at(9000), trusted=True,
                         planner=lambda *a: (calls.append(1) or empty(), {}))
        self.assertEqual(calls, [])
        self.assertEqual(checkin.read(self.c), before)
        self.assertEqual(list((self.c.life / 'local-reflections').glob('*.attempts.json')), [])

    def test_handoff_omits_unverifiable_owner_evidence_and_discloses_failure(self):
        self.lose_provenance()
        text = ctx.cross_channel_handoff(self.c, {'session_id': 'term'}, at(9000), 1800)
        self.assertNotIn(NOTE, text or '')
        self.assertIn('could not be checked this turn', text or '')


if __name__ == '__main__':
    unittest.main()
