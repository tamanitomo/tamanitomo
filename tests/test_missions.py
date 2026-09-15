"""Missions: work the human asked for, claimed so two windows cannot duplicate it."""
import datetime as dt
import json
import pathlib,sys,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'kit/scripts'))
import companion_config as cc
import companion_missions as missions
import companion_render as cr

TZ=dt.timezone.utc

class MissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=pathlib.Path(self.tmp.name)
        self.c=cc.Companion(agent='Nova',human='Alex',hermes_root=root/'home',vault=root/'vault',
                            timezone='UTC')
        self.c.life.mkdir(parents=True,exist_ok=True)
        self.now=dt.datetime(2026,9,10,10,20,tzinfo=TZ)

    def add(self,title,**kw):
        return missions.add(self.c,{'title':title,**kw},self.now)['entry']

    def test_a_claimed_mission_is_not_offered_twice(self):
        self.add('research Airbnbs for the 28th')
        first=missions.claim(self.c,self.now)
        self.assertIsNotNone(first)
        self.assertIsNone(missions.claim(self.c,self.now))

    def test_a_window_that_died_mid_mission_releases_it_by_itself(self):
        self.add('find out if they are touring')
        missions.claim(self.c,self.now)
        later=self.now+dt.timedelta(hours=missions.CLAIM_EXPIRY_HOURS+1)
        self.assertEqual(len(missions.missions(self.c,'open',later)),1)
        self.assertTrue(missions.missions(self.c,'open',later)[0]['stale_claim'])

    def test_releasing_is_not_failing_and_the_work_so_far_is_kept(self):
        made=self.add('price a replacement part')
        missions.claim(self.c,self.now)
        missions.update(self.c,made['id'],'open','found two suppliers, need the model number',self.now)
        again=missions.missions(self.c,'open',self.now)[0]
        self.assertEqual(again['detail_update'],'found two suppliers, need the model number')

    def test_a_finished_mission_leaves_the_queue_but_not_the_record(self):
        made=self.add('research Airbnbs')
        missions.update(self.c,made['id'],'done','three places, all under 200 a night',self.now)
        self.assertEqual(missions.missions(self.c,'open',self.now),[])
        self.assertEqual(len(missions.missions(self.c,'done',self.now)),1)
        self.assertIn('Airbnbs',missions.path_for(self.c).read_text())

    def test_an_empty_queue_says_the_hour_is_hers(self):
        self.assertIsNone(missions.claim(self.c,self.now))
        self.assertEqual(missions.render(self.c,self.now),'')

    def test_windows_render_to_one_cron_expression(self):
        self.assertEqual(cr.cron_times(['10:20','20:20']),'20 10,20 * * *')
        self.assertEqual(cr.cron_times(['07:05']),'5 7 * * *')
        self.assertEqual(cr.cron_times([]),'0 10,20 * * *')

    def test_a_bad_window_time_is_refused_at_setup_not_at_midnight(self):
        with self.assertRaisesRegex(ValueError,'HH:MM'):
            cc.Companion(agent='Nova',human='Alex',autonomy_windows=['half past ten'])


if __name__=='__main__':unittest.main()


class CheckinTests(unittest.TestCase):
    """The gate that makes a reflection happen minutes after a conversation
    instead of at four in the morning — and stay completely silent otherwise."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=pathlib.Path(self.tmp.name)
        self.c=cc.Companion(agent='Nova',human='Alex',hermes_root=root/'home',vault=root/'vault',
                            timezone='UTC')
        self.c.life.mkdir(parents=True,exist_ok=True)
        import companion_checkin
        self.checkin=companion_checkin
        self.now=dt.datetime(2026,9,10,21,0,tzinfo=TZ)

    def test_the_fingerprint_never_moves_on_its_own(self):
        first=self.checkin.fingerprint(self.c)
        self.assertEqual(first,self.checkin.fingerprint(self.c))
        self.assertNotIn('2026',first)   # no clock in it at all

    def test_a_finished_session_changes_it_and_clearing_settles_it(self):
        quiet=self.checkin.fingerprint(self.c)
        self.checkin.flag(self.c,self.now)
        self.assertNotEqual(self.checkin.fingerprint(self.c),quiet)
        self.checkin.clear(self.c,self.now)
        self.assertEqual(self.checkin.fingerprint(self.c),quiet)

    def test_two_sessions_before_a_reflection_still_only_ask_for_one(self):
        self.checkin.flag(self.c,self.now)
        one=self.checkin.fingerprint(self.c)
        self.checkin.flag(self.c,self.now+dt.timedelta(minutes=5))
        self.assertNotEqual(self.checkin.fingerprint(self.c),one)
        self.checkin.clear(self.c,self.now+dt.timedelta(minutes=6))
        self.assertEqual(int(self.checkin.read(self.c)['pending']),0)

    def test_an_unreadable_flag_file_does_not_take_the_hook_down(self):
        self.checkin.path_for(self.c).write_text('{not json',encoding='utf-8')
        self.assertEqual(self.checkin.read(self.c)['pending'],0)
        self.assertTrue(self.checkin.flag(self.c,self.now)['pending'])
