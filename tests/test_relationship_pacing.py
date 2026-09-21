"""How long closeness takes to earn, and whether it can be earned at all.

Two faults, both of which let the score say something untrue about the
relationship it describes:

  - The day count reached back through every conversation the underlying
    assistant had ever had. A companion installed onto a long-lived Hermes woke
    up nearly Bonded with someone it had just met.
  - Trust was applied after the day count was capped, so the highest score any
    relationship could reach was 100 x trust_factor. A steady companion resting
    at default meters topped out at 88 and could never be Bonded at all.
"""
import contextlib
import datetime as dt
import pathlib
import sqlite3
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts')]

import companion_config as cc
import companion_intimacy as intimacy

UTC = dt.timezone.utc
BONDED = 90


class PacingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = pathlib.Path(self.tmp.name)
        self.c = cc.Companion(agent='Nova', human='Alex', profile='nova',
                              hermes_root=base / 'hermes', vault=base / 'vault',
                              boundary='partner', relationship_pace='natural',
                              # Bonded is the stage that unlocks intimate content, so it is
                              # gated on this; without it the score is held at 89 and the
                              # pacing these tests measure would be invisible.
                              explicit=True)
        self.c.home.mkdir(parents=True)
        self.c.life.mkdir(parents=True)
        self.c.save()

    def chatted_on(self, days):
        """Seed one user message on each given date, as the message store would."""
        db = self.c.home / 'state.db'
        fresh = not db.exists()
        with contextlib.closing(sqlite3.connect(db)) as con, con:
            if fresh:
                con.executescript(
                    'CREATE TABLE sessions(id TEXT PRIMARY KEY,profile_name TEXT,source TEXT,'
                    'started_at REAL,title TEXT);'
                    'CREATE TABLE messages(session_id TEXT,role TEXT,content TEXT,timestamp REAL,'
                    '_compressed_summary INTEGER,active INTEGER,compacted INTEGER);')
                con.execute("INSERT INTO sessions VALUES ('s0','nova','cli',100,'Talking)')")
            con.executemany('INSERT INTO messages VALUES (?,?,?,?,0,1,0)',
                            [('s0', 'user', 'hello',
                              dt.datetime.combine(d, dt.time(12), UTC).timestamp()) for d in days])

    def run_of_days(self, count, ending):
        return [ending - dt.timedelta(days=n) for n in range(count)]

    def score_after(self, count, ending=dt.date(2026, 9, 20)):
        self.chatted_on(self.run_of_days(count, ending))
        now = dt.datetime.combine(ending, dt.time(18), UTC)
        return intimacy.compute(self.c, now)

    # ---- the day count belongs to this relationship ------------------------

    def test_history_from_before_the_relationship_does_not_count(self):
        """The whole point: a fresh companion is not owed months it did not share."""
        today = dt.date(2026, 9, 20)
        # A year of the assistant being used for other things, then two weeks together.
        self.chatted_on(self.run_of_days(300, today - dt.timedelta(days=14)))
        self.chatted_on(self.run_of_days(14, today))
        now = dt.datetime.combine(today, dt.time(18), UTC)

        unanchored = intimacy.compute(self.c, now)
        self.assertGreaterEqual(unanchored['score'], BONDED,
                                'without an anchor the old history should still count')

        self.c.relationship_started = (today - dt.timedelta(days=13)).isoformat()
        self.c.save()
        anchored = intimacy.compute(self.c, now)
        self.assertEqual(anchored['stage_name'], 'Friends')
        self.assertLess(anchored['score'], 50)

    def test_an_anchor_in_the_past_keeps_everything_after_it(self):
        """Anchoring is not amnesia: days shared since the start still count."""
        today = dt.date(2026, 9, 20)
        self.chatted_on(self.run_of_days(60, today))
        self.c.relationship_started = (today - dt.timedelta(days=400)).isoformat()
        self.c.save()
        state = intimacy.compute(self.c, dt.datetime.combine(today, dt.time(18), UTC))
        self.assertGreaterEqual(state['score'], BONDED)

    def test_a_malformed_anchor_is_ignored_rather_than_stranding_anyone(self):
        object.__setattr__(self.c, 'relationship_started', 'not-a-date')
        state = self.score_after(60)
        self.assertGreaterEqual(state['score'], BONDED)

    # ---- how long two months of daily talking actually takes ---------------

    def test_bonded_takes_about_two_months_of_daily_conversation(self):
        state = self.score_after(56)
        self.assertGreaterEqual(state['score'], BONDED)
        self.assertEqual(state['stage_name'], 'Bonded')

    def test_bonded_is_not_reachable_in_a_month(self):
        self.assertLess(self.score_after(30)['score'], BONDED)

    def test_the_early_stages_still_arrive_promptly(self):
        """A companion that is a stranger for a fortnight is no fun either."""
        self.assertEqual(self.score_after(4)['stage_name'], 'Friends')

    def test_bonded_stays_shut_without_the_adult_opt_in(self):
        """Bonded is the stage that unlocks intimate content, so it is gated.

        Worth pinning because the cap lands one point short of the threshold: a
        companion without the opt-in sits at 89 forever, and that reads exactly
        like a relationship still a day away from bonding rather than one that
        has been held at a ceiling since day fifty-six.
        """
        for days in (56, 120, 400):
            self.setUp()
            self.c.explicit = False
            self.c.save()
            state = self.score_after(days)
            self.assertEqual(state['score'], 89, f'{days} days')
            self.assertEqual(state['stage_name'], 'Intimacy')
            self.assertFalse(state['can_intimate'])

    def test_pace_moves_the_target_in_the_direction_it_says(self):
        def days_to_bond(pace):
            for count in range(4, 300):
                with self.subTest(pace=pace, count=count):
                    pass
                self.setUp()
                self.c.relationship_pace = pace
                self.c.save()
                if self.score_after(count)['score'] >= BONDED:
                    return count
            return None
        quick, natural, slow = days_to_bond('quick'), days_to_bond('natural'), days_to_bond('slow')
        self.assertLess(quick, natural)
        self.assertLess(natural, slow)
        self.assertGreaterEqual(slow, 80)


class TrustSetsTheRateNotTheCeilingTests(unittest.TestCase):
    """Trust should make closeness slower to earn, never impossible.

    Capping the earned days and scaling afterwards meant the best score a
    relationship could reach was 100 x trust_factor, so every factor below 0.9 --
    including the one a steady companion has by default -- was locked out of
    Bonded permanently, however many years went by.
    """

    def curve(self, factor, cap_first):
        """The two orderings, side by side, at natural pace."""
        for active_days in range(1, 2000):
            stage0 = 25.0
            slow_burn = max(0, active_days - 4) * 1.25
            if cap_first:
                score = (stage0 + min(75.0, slow_burn)) * factor
            else:
                score = min(100.0, (stage0 + slow_burn) * factor)
            if min(100, round(score)) >= BONDED:
                return active_days
        return None

    def test_the_old_ordering_locked_out_every_unremarkable_relationship(self):
        self.assertIsNone(self.curve(0.884, cap_first=True), 'the default meters were a dead end')
        self.assertIsNone(self.curve(0.5, cap_first=True))

    def test_the_new_ordering_makes_them_slow_instead_of_impossible(self):
        self.assertIsNotNone(self.curve(0.884, cap_first=False))
        self.assertIsNotNone(self.curve(0.2, cap_first=False))
        self.assertGreater(self.curve(0.5, cap_first=False), self.curve(0.884, cap_first=False))

    def test_a_healthy_relationship_is_arithmetically_unchanged(self):
        """The fix must not quietly re-pace the companions it was not about."""
        self.assertEqual(self.curve(1.0, cap_first=True), self.curve(1.0, cap_first=False))


if __name__ == '__main__':
    unittest.main()
