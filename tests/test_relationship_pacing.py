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
from fixture_conversation import a_days_conversation

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

    def seed(self, rows):
        """Write (timestamp, text) pairs into the message store, as Hermes would."""
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
                            [('s0', 'user', text, when.timestamp()) for when, text in rows])

    def chatted_on(self, days):
        """Seed a proper day of conversation on each given date."""
        rows = []
        for d in days:
            rows.extend(a_days_conversation(d))
        self.seed(rows)

    def pinged_on(self, days):
        """Seed the other kind of day: one word, once, and gone again."""
        self.seed([(dt.datetime.combine(d, dt.time(12), UTC), 'hey') for d in days])

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

    def test_bonded_is_reachable_without_adult_themes(self):
        """Bonded is the top of the relationship, not a door to adult content.

        It used to be held at 89 unless adult themes were on, so the deepest a
        friendship could ever be was one point short -- indistinguishable from a
        relationship still a day away from it. What Bonded unlocks is decided
        separately, and for a companion without the opt-in it unlocks nothing.
        """
        for days in (56, 120):
            self.setUp()
            self.c.explicit = False
            self.c.save()
            state = self.score_after(days)
            self.assertGreaterEqual(state['score'], BONDED, f'{days} days')
            self.assertEqual(state['stage_name'], 'Bonded')
            self.assertFalse(state['can_intimate'])
            self.assertFalse(state['can_send_adult_images'])

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


class PlatonicLadderTests(unittest.TestCase):
    """A relationship that is not a romance should not be described as one.

    Calling stage two "Chemistry" for a mentor, a sibling or a Jarvis was not a
    cosmetic problem: it named a relationship the user had explicitly not chosen,
    and then wrote that name into the companion's own prompt.
    """

    def build(self, boundary='best-friend', agent_type='companion', explicit=False):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = pathlib.Path(tmp.name)
        c = cc.Companion(agent='Jarvis', human='Alex', profile='j',
                         hermes_root=base / 'hermes', vault=base / 'vault',
                         boundary=boundary, agent_type=agent_type, explicit=explicit)
        c.home.mkdir(parents=True); c.life.mkdir(parents=True); c.save()
        return c

    def at(self, c, days):
        end = dt.date(2026, 9, 20)
        db = c.home / 'state.db'
        with contextlib.closing(sqlite3.connect(db)) as con, con:
            con.executescript(
                'CREATE TABLE sessions(id TEXT PRIMARY KEY,profile_name TEXT,source TEXT,'
                'started_at REAL,title TEXT);'
                'CREATE TABLE messages(session_id TEXT,role TEXT,content TEXT,timestamp REAL,'
                '_compressed_summary INTEGER,active INTEGER,compacted INTEGER);')
            con.execute("INSERT INTO sessions VALUES ('s0','j','cli',100,'t')")
            con.executemany(
                'INSERT INTO messages VALUES (?,?,?,?,0,1,0)',
                [('s0', 'user', text, when.timestamp())
                 for n in range(days)
                 for when, text in a_days_conversation(end - dt.timedelta(days=n))])
        return intimacy.compute(c, dt.datetime.combine(end, dt.time(18), UTC))

    def test_a_platonic_frame_never_reaches_chemistry_or_intimacy(self):
        names = [self.at(self.build(), d)['stage_name'] for d in (1, 20, 30, 45, 56)]
        self.assertNotIn('Chemistry', names)
        self.assertNotIn('Intimacy', names)
        self.assertEqual(names, ['Just Met', 'Familiar', 'Trusted', 'Confidant', 'Bonded'])

    def test_a_platonic_frame_can_be_bonded_and_it_unlocks_nothing(self):
        state = self.at(self.build(), 56)
        self.assertEqual(state['stage_name'], 'Bonded')
        self.assertFalse(state['can_flirt'], 'a best friend does not start flirting at stage four')
        self.assertFalse(state['can_intimate'])
        self.assertFalse(state['can_send_adult_images'])

    def test_a_romantic_frame_keeps_the_romantic_ladder(self):
        c = self.build(boundary='girlfriend', explicit=True)
        self.assertEqual(self.at(c, 45)['stage_name'], 'Intimacy')

    def test_a_colleague_is_platonic_whatever_its_frame_says(self):
        c = self.build(boundary='girlfriend', agent_type='colleague')
        self.assertEqual(self.at(c, 45)['stage_name'], 'Confidant')

    def test_the_guidance_given_to_a_platonic_companion_mentions_no_romance(self):
        c = self.build()
        bonded = intimacy.render(c, self.at(c, 56))
        self.assertTrue(bonded.strip(), 'a platonic relationship still needs describing')
        self.assertIn('BONDED', bonded.upper())
        confidant = intimacy.render(self.build(), self.at(self.build(), 45))
        self.assertIn('CONFIDANT', confidant.upper())
        for text in (bonded, confidant):
            for word in ('flirt', 'chemistry', 'intimate'):
                self.assertNotIn(word, text.lower(), word)
        # "not romance" is allowed to appear; "romantic chemistry" is not.
        self.assertNotIn('romantic', bonded.lower())


class AdultImagesAreTheirOwnPermissionTests(unittest.TestCase):
    """Wanting a romance is not the same as wanting nudes.

    Four call sites read `explicit` to decide whether adult imagery was allowed,
    so every romantic companion was also cleared for it with no way to say
    otherwise -- and a user with two companions could not want it from one.
    """

    def build(self, explicit=True, adult_images=False):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = pathlib.Path(tmp.name)
        c = cc.Companion(agent='Nova', human='Alex', profile='n',
                         hermes_root=base / 'hermes', vault=base / 'vault',
                         boundary='girlfriend', explicit=explicit, adult_images=adult_images)
        c.home.mkdir(parents=True); c.life.mkdir(parents=True); c.save()
        return c

    def test_romance_alone_does_not_permit_adult_images(self):
        self.assertFalse(self.build(explicit=True, adult_images=False).adult_images_allowed)

    def test_both_switches_permit_them(self):
        self.assertTrue(self.build(explicit=True, adult_images=True).adult_images_allowed)

    def test_adult_images_cannot_be_set_without_romance(self):
        with self.assertRaises(ValueError):
            self.build(explicit=False, adult_images=True)

    def test_two_companions_can_differ(self):
        """The case that motivated this: romance with both, nudes from one."""
        modest, willing = self.build(adult_images=False), self.build(adult_images=True)
        self.assertFalse(modest.adult_images_allowed)
        self.assertTrue(willing.adult_images_allowed)


class DayQualityTests(unittest.TestCase):
    """A day is worth what was actually said in it.

    Counting days the human said *anything* made the meter trivially farmable --
    one "k" at midnight bought exactly what an hour of real conversation did --
    and, worse, wrong: it reported a deepening relationship on evidence that
    there was not one. Each of these is a way the old count could be fed.
    """

    def day(self, texts, hours=None):
        base = dt.date(2026, 9, 20)
        hours = hours or list(range(len(texts)))
        return [(dt.datetime.combine(base, dt.time(h % 24, (n * 7) % 60), UTC), t)
                for n, (h, t) in enumerate(zip(hours, texts))]

    def test_a_real_days_conversation_is_a_whole_day(self):
        self.assertEqual(intimacy.day_credit(a_days_conversation(dt.date(2026, 9, 20))), 1.0)

    def test_showing_up_briefly_counts_for_something_but_not_a_day(self):
        credit = intimacy.day_credit(self.day(['hey']))
        self.assertEqual(credit, intimacy.SHOW_UP_FLOOR)
        self.assertLess(credit, 0.2)

    def test_the_same_message_pasted_all_day_is_worth_one_message(self):
        line = 'I have been thinking about what you said yesterday and I think you were right. ' * 3
        spammed = intimacy.day_credit(self.day([line] * 40, hours=list(range(40))))
        once = intimacy.day_credit(self.day([line]))
        self.assertEqual(spammed, once, 'repeats of something already said are not more of it')

    def test_one_enormous_paste_is_not_a_days_conversation(self):
        wall = 'x' * 20000
        self.assertLess(intimacy.day_credit(self.day([wall])), 0.4)

    def test_a_two_minute_burst_is_worth_less_than_the_same_words_spread_out(self):
        texts = [f'Here is a genuine and distinct thought number {n} about my day and how it went.'
                 for n in range(12)]
        burst = intimacy.day_credit(self.day(texts, hours=[9] * 12))
        spread = intimacy.day_credit(self.day(texts, hours=[8, 9, 10, 11, 13, 14, 16, 17, 19, 20, 21, 22]))
        self.assertLess(burst, spread)

    def test_no_single_signal_can_carry_a_whole_day(self):
        """Volume, turns and spread each saturate, so maxing one is not enough."""
        wall = 'y' * 5000
        volume_only = intimacy.day_credit(self.day([wall]))
        turns_only = intimacy.day_credit(self.day([f'ok {n}' for n in range(60)], hours=[9] * 60))
        for credit in (volume_only, turns_only):
            self.assertLess(credit, 0.75)


class ThinContactTests(unittest.TestCase):
    """Drifting apart is not only going silent.

    Inactivity decay watched the clock since the last message, so a daily
    one-word ping reset it completely while earning almost nothing. Neglect
    looked exactly like devotion, and cost nothing.
    """

    def build(self, **kw):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = pathlib.Path(tmp.name)
        c = cc.Companion(agent='Nova', human='Alex', profile='nova',
                         hermes_root=base / 'hermes', vault=base / 'vault',
                         boundary='partner', explicit=True, **kw)
        c.home.mkdir(parents=True); c.life.mkdir(parents=True); c.save()
        return c

    def seed(self, c, rows):
        db = c.home / 'state.db'
        fresh = not db.exists()
        with contextlib.closing(sqlite3.connect(db)) as con, con:
            if fresh:
                con.executescript(
                    'CREATE TABLE sessions(id TEXT PRIMARY KEY,profile_name TEXT,source TEXT,'
                    'started_at REAL,title TEXT);'
                    'CREATE TABLE messages(session_id TEXT,role TEXT,content TEXT,timestamp REAL,'
                    '_compressed_summary INTEGER,active INTEGER,compacted INTEGER);')
                con.execute("INSERT INTO sessions VALUES ('s0','nova','cli',100,'t')")
            con.executemany('INSERT INTO messages VALUES (?,?,?,?,0,1,0)',
                            [('s0', 'user', t, w.timestamp()) for w, t in rows])

    END = dt.date(2026, 9, 20)

    def state(self, c):
        return intimacy.compute(c, dt.datetime.combine(self.END, dt.time(23), UTC))

    def days(self, count, offset=0):
        return [self.END - dt.timedelta(days=n + offset) for n in range(count)]

    def test_daily_pings_alone_never_get_past_friends(self):
        c = self.build()
        self.seed(c, [(dt.datetime.combine(d, dt.time(12), UTC), f'hey {d}') for d in self.days(200)])
        state = self.state(c)
        self.assertLessEqual(state['score'], 49, 'two hundred one-word days is not a relationship')
        self.assertLess(state['cadence'], 1.0)

    def test_keeping_up_properly_carries_no_drag(self):
        c = self.build()
        rows = [m for d in self.days(60) for m in a_days_conversation(d)]
        self.seed(c, rows)
        state = self.state(c)
        self.assertGreaterEqual(state['cadence'], 1.0)
        self.assertGreaterEqual(state['score'], BONDED)

    def test_half_hearted_days_take_roughly_twice_as_long(self):
        """Half a day's conversation is half a day's closeness, not a whole one."""
        def score_at(count, slicer):
            c = self.build()
            rows = [m for d in self.days(count) for m in slicer(a_days_conversation(d))]
            self.seed(c, rows)
            return self.state(c)['score']
        self.assertGreaterEqual(score_at(56, lambda m: m), BONDED)
        self.assertLess(score_at(56, lambda m: m[:4]), BONDED)
        self.assertGreaterEqual(score_at(112, lambda m: m[:4]), BONDED)

    def test_going_thin_after_bonding_erodes_what_was_earned(self):
        """Sixty proper days then a fortnight of pings should not still read Bonded."""
        c = self.build()
        rows = [m for d in self.days(60, offset=14) for m in a_days_conversation(d)]
        rows += [(dt.datetime.combine(d, dt.time(12), UTC), f'hey {d}') for d in self.days(14)]
        self.seed(c, rows)
        state = self.state(c)
        self.assertLess(state['score'], BONDED)
        self.assertGreaterEqual(state['score'], 25, 'friendship is still the floor')

    def test_erosion_is_recoverable_by_showing_up_properly_again(self):
        c = self.build()
        rows = [m for d in self.days(60, offset=14) for m in a_days_conversation(d)]
        rows += [(dt.datetime.combine(d, dt.time(12), UTC), f'hey {d}') for d in self.days(14, offset=7)]
        rows += [m for d in self.days(7) for m in a_days_conversation(d)]
        self.seed(c, rows)
        self.assertGreater(self.state(c)['score'], 70)


class LocalDayTests(unittest.TestCase):
    """A day is the human's day.

    Bucketing on UTC cut an evening conversation in half for anyone west of
    Greenwich: one good evening was filed as two thin days, and two thin days are
    worth less than one good one, which is the whole point of the change.
    """

    def build(self, timezone):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = pathlib.Path(tmp.name)
        c = cc.Companion(agent='Nova', human='Alex', profile='nova',
                         hermes_root=base / 'hermes', vault=base / 'vault',
                         boundary='partner', explicit=True, timezone=timezone)
        c.home.mkdir(parents=True); c.life.mkdir(parents=True); c.save()
        return c

    def evening(self, c, day):
        """One evening's conversation, 19:00-23:00 New York -- which is the next
        day in UTC from midnight onward."""
        rows = [(dt.datetime.combine(day, dt.time(19 + n // 3, (n * 17) % 60),
                                     dt.timezone(dt.timedelta(hours=-4))), text)
                for n, (_, text) in enumerate(a_days_conversation(day))]
        db = c.home / 'state.db'
        fresh = not db.exists()
        with contextlib.closing(sqlite3.connect(db)) as con, con:
            if fresh:
                con.executescript(
                    'CREATE TABLE sessions(id TEXT PRIMARY KEY,profile_name TEXT,source TEXT,'
                    'started_at REAL,title TEXT);'
                    'CREATE TABLE messages(session_id TEXT,role TEXT,content TEXT,timestamp REAL,'
                    '_compressed_summary INTEGER,active INTEGER,compacted INTEGER);')
                con.execute("INSERT INTO sessions VALUES ('s0','nova','cli',100,'t')")
            con.executemany('INSERT INTO messages VALUES (?,?,?,?,0,1,0)',
                            [('s0', 'user', t, w.timestamp()) for w, t in rows])

    def test_an_evening_is_one_day_in_the_humans_timezone(self):
        end = dt.date(2026, 9, 20)
        days = [end - dt.timedelta(days=n) for n in range(10)]
        local, utc = self.build('America/New_York'), self.build('UTC')
        for c in (local, utc):
            for d in days:
                self.evening(c, d)
        now = dt.datetime(2026, 9, 21, 1, tzinfo=UTC)
        # Ten evenings are ten days where the human lives, and eleven part-days
        # in UTC -- the last hours of each one filed under tomorrow.
        self.assertEqual(intimacy.compute(local, now)['active_days'], 10)
        self.assertEqual(intimacy.compute(utc, now)['active_days'], 11)

    def test_splitting_an_evening_costs_the_day_its_quality(self):
        """The same conversation, scored whole and scored in halves."""
        day = dt.date(2026, 9, 20)
        rows = a_days_conversation(day)
        whole = intimacy.day_credit(rows)
        first = intimacy.day_credit(rows[:5])
        second = intimacy.day_credit(rows[5:])
        self.assertEqual(whole, 1.0)
        self.assertLess(first, whole)
        self.assertLess(second, whole)
