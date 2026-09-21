"""The declared night: who decides she is asleep, and what stops while she is.

The bug these cover: a night produced twenty to thirty near-identical timeline
images of a dark bedroom, because nothing on disk asserted "asleep until seven".
Two mechanisms failed together — the image job was never gated at all, and the
gate that was supposed to quiet the agent jobs watched `started_at`, which is
derived from prose and so moved every time the same sleep was described in
slightly fresher words.
"""
import datetime as dt,json,pathlib,sys,tempfile,unittest
from zoneinfo import ZoneInfo
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'kit/scripts'))
import companion_config as cc
import companion_presence as presence
import companion_preread as preread
import companion_sleep as sleep
import companion_timeline as timeline

TZ=ZoneInfo('America/New_York')

class SleepWindowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.folder=pathlib.Path(self.tmp.name)
        self.c=cc.Companion(hermes_root=self.folder/'home',vault=self.folder/'vault',
                            image_timeline=True,image_style='realistic',
                            timezone='America/New_York',quiet_start='23:00',quiet_end='08:00')
    def at(self,hour,minute=0,day=20):
        return dt.datetime(2026,9,day,hour,minute,tzinfo=TZ)

    def test_quiet_hours_do_not_mean_asleep(self):
        """Quiet hours are a rule about not CONTACTING the human, nothing more.

        Conflating the two shut her whole life down for nine hours a night when
        all that was ever asked for was an undisturbed phone.
        """
        self.assertFalse(sleep.asleep(self.c,self.at(2)))
        self.assertEqual(sleep.status(self.c,self.at(2))['source'],'awake')
        self.assertFalse(sleep.asleep(self.c,self.at(14)))

    def test_a_declared_night_governs_its_own_start_and_end(self):
        sleep.declare(self.c,'07:00',now=self.at(22,40))
        self.assertTrue(sleep.asleep(self.c,self.at(23,30)))
        self.assertTrue(sleep.asleep(self.c,self.at(3,0,21)))
        self.assertEqual(sleep.status(self.c,self.at(3,0,21))['until_local'],'07:00')
        self.assertFalse(sleep.asleep(self.c,self.at(7,1,21)))

    def test_declared_beats_the_clock_in_both_directions(self):
        """An early start is a decision, not an error the quiet-hours setting corrects.

        Quiet hours run to 08:00 here, so a fallback would have overruled the
        07:00 she wrote down and kept her 'asleep' for another hour.
        """
        sleep.declare(self.c,'07:00',now=self.at(22,40))
        self.assertFalse(sleep.asleep(self.c,self.at(7,30,21)))
        # And waking early sticks, rather than handing the answer back to the clock.
        sleep.wake(self.c,self.at(6,0,21))
        self.assertFalse(sleep.asleep(self.c,self.at(6,5,21)))
        self.assertFalse(sleep.asleep(self.c,self.at(7,30,21)))

    def test_being_written_to_wakes_her(self):
        """Someone typing at 02:00 is not an argument for staying asleep."""
        sleep.declare(self.c,'07:00',now=self.at(22,40))
        self.assertTrue(sleep.asleep(self.c,self.at(2,0,21)))
        thread=self.c.soul_dir/'ambient/relationship-thread.json'
        thread.parent.mkdir(parents=True,exist_ok=True)
        thread.write_text(json.dumps({'last_from_human':self.at(2,0,21).isoformat()}),encoding='utf-8')
        self.assertFalse(sleep.asleep(self.c,self.at(2,5,21)))
        self.assertEqual(sleep.status(self.c,self.at(2,5,21))['source'],'messaged')

    def test_her_own_recorded_state_answers_when_nothing_was_declared(self):
        self.assertFalse(sleep.asleep(self.c,self.at(2)))

    def test_an_implausible_or_stale_plan_falls_back_rather_than_stranding_her(self):
        with self.assertRaises(ValueError):sleep.declare(self.c,'23:10',now=self.at(22,40))  # a nap
        with self.assertRaises(ValueError):sleep.declare(self.c,'22:00',now=self.at(22,40))  # ~24h
        sleep.path(self.c).parent.mkdir(parents=True,exist_ok=True)
        sleep.path(self.c).write_text('{"from":"nonsense"}',encoding='utf-8')
        self.assertEqual(sleep.status(self.c,self.at(2))['source'],'awake')

class NothingRunsWhileAsleepTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.folder=pathlib.Path(self.tmp.name)
        self.c=cc.Companion(hermes_root=self.folder/'home',vault=self.folder/'vault',
                            image_timeline=True,image_style='realistic',
                            timezone='America/New_York',quiet_start='23:00',quiet_end='08:00')
        presence.update_wardrobe(self.c,[{'id':'pjs','description':'grey pyjamas','use':'sleep'}])
        self.night=dt.datetime(2026,9,20,22,40,tzinfo=TZ)
        presence.update(self.c,{'previous_id':None,'outfit':['pjs'],'location':'bedroom',
                                'activity':'asleep at home','mood':'settled','text':'Going to sleep.'},self.night)

    def test_no_timeline_image_is_claimed_while_asleep(self):
        """The whole point: a night is not thirty photographs of a dark room."""
        sleep.declare(self.c,'07:00',now=self.night)
        for hour in (23,1,3,6):
            day=20 if hour==23 else 21
            call=timeline.prepare(self.c,dt.datetime(2026,9,day,hour,3,tzinfo=TZ))
            self.assertFalse(call['ready'],f'claimed an image at {hour:02d}:03')
            self.assertIn('asleep',call['reason'].lower())
        self.assertEqual(list(timeline.records(self.c)),[])

    def test_the_image_job_is_gated_by_her_recorded_sleep_alone(self):
        """No declaration, but she recorded herself asleep -- that is enough."""
        previous=presence.current(self.c)
        presence.update(self.c,{'previous_id':previous['id'],'outfit':['pjs'],'location':'bedroom',
                                'activity':'asleep at home','mood':'settled','text':'Asleep.',
                                'asleep':True,'transition':'Fell asleep.'},self.night+dt.timedelta(minutes=5))
        call=timeline.prepare(self.c,dt.datetime(2026,9,21,3,3,tzinfo=TZ))
        self.assertFalse(call['ready']);self.assertIn('asleep',call['reason'].lower())

    def test_rewording_the_same_sleep_no_longer_restarts_the_scene(self):
        """`started_at` is what the overnight gate watches, so prose must not move it."""
        sleep.declare(self.c,'07:00',now=self.night)
        first=presence.current(self.c)['state']['started_at']
        marks={first}
        moment=self.night
        for phrasing in ('asleep at home, deeper into the night',
                         'asleep at home — the quietest stretch',
                         'asleep at home, hours from morning'):
            moment+=dt.timedelta(minutes=15)
            previous=presence.current(self.c)
            presence.update(self.c,{'previous_id':previous['id'],'outfit':['pjs'],'location':'bedroom',
                                    'activity':phrasing,'mood':'settled','text':'Still asleep.',
                                    'transition':'Still asleep.'},moment)
            marks.add(presence.current(self.c)['state']['started_at'])
        self.assertEqual(marks,{first},'a reworded sleep restarted the scene clock')

    def test_the_overnight_fingerprint_holds_still_across_those_ticks(self):
        """Identical bytes are what make Hermes skip the model run entirely."""
        sleep.declare(self.c,'07:00',now=self.night)
        seen=set()
        moment=self.night
        for phrasing in ('asleep at home, deeper into the night','asleep at home — nearly morning'):
            moment+=dt.timedelta(minutes=15)
            previous=presence.current(self.c)
            presence.update(self.c,{'previous_id':previous['id'],'outfit':['pjs'],'location':'bedroom',
                                    'activity':phrasing,'mood':'settled','text':'Still asleep.',
                                    'transition':'Still asleep.'},moment)
            seen.add(preread.fingerprint(self.c,moment))
        self.assertEqual(len(seen),1,'the overnight gate moved while nothing happened')

    def test_getting_up_is_still_a_real_transition(self):
        """The gate must not become a trap that cannot be left."""
        sleep.declare(self.c,'07:00',now=self.night)
        morning=dt.datetime(2026,9,21,7,5,tzinfo=TZ)
        sleep.wake(self.c,morning)
        previous=presence.current(self.c)
        presence.update(self.c,{'previous_id':previous['id'],'outfit':['pjs'],'location':'kitchen',
                                'activity':'making coffee','mood':'slow','text':'Up.',
                                'transition':'Got up and came downstairs.'},morning)
        self.assertEqual(presence.current(self.c)['state']['started_at'],morning.isoformat())
        self.assertTrue(timeline.prepare(self.c,morning+dt.timedelta(minutes=1))['ready'])

if __name__=='__main__':
    unittest.main()

class NoModelCallWhenNothingChangedTests(unittest.TestCase):
    """The gate has to sit OUTSIDE the job, or the model is invoked to be told no.

    `prepare` declining still costs a scheduled model run every fifteen minutes,
    all day and all night. Hermes hashes `fingerprint` instead and skips the run
    outright, so an unchanged scene costs nothing at all.
    """
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.folder=pathlib.Path(self.tmp.name)
        self.c=cc.Companion(hermes_root=self.folder/'home',vault=self.folder/'vault',
                            image_timeline=True,image_style='realistic',
                            timezone='America/New_York',quiet_start='23:00',quiet_end='08:00')
        presence.update_wardrobe(self.c,[{'id':'tee','description':'green tee','use':'everyday'}])
        self.now=dt.datetime(2026,9,20,12,0,tzinfo=TZ)
        presence.update(self.c,{'previous_id':None,'outfit':['tee'],'location':'kitchen',
                                'activity':'eating lunch','mood':'content','text':'Lunch.'},self.now)

    def _reword(self,minutes,activity,**kw):
        previous=presence.current(self.c)
        presence.update(self.c,{'previous_id':previous['id'],'outfit':['tee'],'location':'kitchen',
                                'activity':activity,'mood':'content','text':'Still lunch.',
                                'transition':'Still eating.',**kw},self.now+dt.timedelta(minutes=minutes))

    def test_an_unchanged_scene_produces_identical_bytes(self):
        first=timeline.fingerprint(self.c,self.now)
        self.assertEqual(timeline.fingerprint(self.c,self.now+dt.timedelta(minutes=15)),first)
        self.assertEqual(timeline.fingerprint(self.c,self.now+dt.timedelta(minutes=30)),first)

    def test_a_genuinely_new_scene_changes_the_bytes(self):
        first=timeline.fingerprint(self.c,self.now)
        self._reword(15,'washing up at the sink')
        self.assertNotEqual(timeline.fingerprint(self.c,self.now+dt.timedelta(minutes=15)),first)

    def test_sleep_collapses_the_whole_night_to_one_value(self):
        sleep.declare(self.c,'07:00',now=dt.datetime(2026,9,20,22,40,tzinfo=TZ))
        night=[timeline.fingerprint(self.c,dt.datetime(2026,9,21,h,3,tzinfo=TZ)) for h in (0,2,4,6)]
        self.assertEqual(len(set(night)),1)
        self.assertIn('asleep',night[0])
