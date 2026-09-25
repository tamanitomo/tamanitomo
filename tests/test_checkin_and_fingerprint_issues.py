"""Regressions for GitHub issue #4: pulse/autonomy fingerprints opening on
generated prose.

`companion_preread.fingerprint` gates the pulse and autonomy cron jobs
(`--monitor-script`): identical bytes make Hermes skip the model run. Its
AWAKE branch hashed `activity`/`location`/`mood` directly -- fields the
model re-authors in fresh wording on every tick even when nothing about the
scene has changed -- so a pure reword opened the gate and spent a call to be
told nothing had happened. The ASLEEP branch already fixed the identical
mistake (see its comment in companion_preread.py) by hashing `started_at`,
a field companion_day.evolve only moves on a declared `activity_change:
transition`. This file pins the same fix for the awake branch.
"""
import datetime as dt, pathlib, sys, tempfile, unittest
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts')]
import companion_config as cc
import companion_presence as presence
import companion_preread as preread

TZ = ZoneInfo('America/New_York')


class AwakeFingerprintProseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        folder = pathlib.Path(self.tmp.name)
        self.c = cc.Companion(hermes_root=folder / 'home', vault=folder / 'vault',
                               timezone='America/New_York', quiet_start='23:00', quiet_end='08:00')
        presence.update_wardrobe(self.c, [{'id': 'tee', 'description': 'green tee', 'use': 'everyday'}])
        self.now = dt.datetime(2026, 9, 25, 12, 0, tzinfo=TZ)
        presence.update(self.c, {'previous_id': None, 'outfit': ['tee'], 'location': 'kitchen',
                                  'activity': 'eating lunch', 'mood': 'content', 'text': 'Lunch.',
                                  'activity_change': 'transition'}, self.now)

    def _reword(self, minutes, activity, mood='content', activity_change='continue', location='kitchen'):
        previous = presence.current(self.c)
        moment = self.now + dt.timedelta(minutes=minutes)
        presence.update(self.c, {'previous_id': previous['id'], 'outfit': ['tee'], 'location': location,
                                  'activity': activity, 'mood': mood, 'text': 'Still there.',
                                  'transition': 'Still there.', 'activity_change': activity_change}, moment)
        return moment

    def test_rewording_the_same_awake_activity_does_not_open_the_gate(self):
        first = preread.fingerprint(self.c, self.now)
        seen = {first}
        for minutes, (phrasing, mood) in enumerate((
                ('finishing the coffee at the kitchen table', 'content'),
                ('coffee, plate cleared', 'content, a little sleepy'),
                ('lingering over the last of it', 'settled')), start=1):
            moment = self._reword(minutes * 15, phrasing, mood=mood)
            seen.add(preread.fingerprint(self.c, moment))
        self.assertEqual(len(seen), 1, 'a reworded awake scene opened the pulse/autonomy gate')

    def test_a_declared_transition_still_opens_the_gate(self):
        """The fix must not become a trap the agent can never leave (ISS-04B)."""
        first = preread.fingerprint(self.c, self.now)
        moment = self._reword(15, 'washing up at the sink', activity_change='transition', location='kitchen')
        self.assertNotEqual(preread.fingerprint(self.c, moment), first,
                             'a genuine transition must still change the fingerprint')

    def test_confirmation_state_still_opens_the_gate(self):
        """`confirmed` is a code-owned flag (carried-forward vs. authored), not prose."""
        first = preread.fingerprint(self.c, self.now)
        later = self.now + dt.timedelta(minutes=25)
        result = presence.advance(self.c, now=later)  # no model confirmed it in time -> confirmed=False
        self.assertTrue(result.get('written'), result)
        self.assertFalse(presence.current(self.c)['state'].get('confirmed', True))
        self.assertNotEqual(preread.fingerprint(self.c, later), first,
                             'an unconfirmed (carried-forward) scene must be distinguishable from a confirmed one')
