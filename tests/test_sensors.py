"""Senses, the thread, and the quiet-hours drift.

The rule every one of these enforces: an absent sensor is silent. Not knowing
the weather is fine; claiming it is raining because a fetch failed is not.
"""
import datetime as dt
import json
import pathlib,sys,tempfile,unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'kit/scripts'))
import companion_config as cc
import companion_sensors as sensors
import companion_thread as thread
import companion_quiet as quiet

TZ=dt.timezone.utc

class Base(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=pathlib.Path(self.tmp.name)
        self.c=cc.Companion(agent='Nova',human='Alex',hermes_root=root/'home',vault=root/'vault',
                            timezone='UTC',quiet_start='23:00',quiet_end='08:00')
        self.c.data.mkdir(parents=True,exist_ok=True)
        self.now=dt.datetime(2026,9,10,12,0,tzinfo=TZ)
        self.ambient=self.c.soul_dir/'ambient'


class SensorTests(Base):
    def test_a_sensor_with_nothing_to_say_writes_no_file(self):
        result=sensors.run_one(self.c,'dates',self.now)
        self.assertFalse(result['wrote'])
        self.assertFalse((self.ambient/'dates.md').exists())

    def test_a_sensor_that_goes_quiet_removes_its_stale_file(self):
        """Yesterday's weather presented as today's is worse than no weather."""
        (self.c.data/'dates.md').write_text('09-11 | Alex\'s birthday\n')
        self.assertTrue(sensors.run_one(self.c,'dates',self.now)['wrote'])
        (self.c.data/'dates.md').write_text('01-01 | New Year\n')
        self.assertFalse(sensors.run_one(self.c,'dates',self.now)['wrote'])
        self.assertFalse((self.ambient/'dates.md').exists())

    def test_a_failing_sensor_is_silent_rather_than_wrong(self):
        self.c.location='Raleigh, NC'
        with patch.object(sensors,'weather',side_effect=RuntimeError('network on fire')):
            result=sensors.run_one(self.c,'weather',self.now)
        self.assertFalse(result['wrote'])
        self.assertIn('network on fire',result['reason'])
        self.assertFalse((self.ambient/'weather.md').exists())

    def test_weather_says_nothing_without_a_location(self):
        self.assertFalse(sensors.run_one(self.c,'weather',self.now)['wrote'])

    def test_dates_look_a_week_ahead_and_no_further(self):
        (self.c.data/'dates.md').write_text(
            '# comments and blanks are skipped\n\n'
            '09-11 | our anniversary\n09-30 | too far off\n09-10 | today\n')
        sensors.run_one(self.c,'dates',self.now)
        text=(self.ambient/'dates.md').read_text()
        self.assertIn('our anniversary — tomorrow',text)
        self.assertIn('today — today',text)
        self.assertNotIn('too far off',text)

    def test_follow_ups_surface_only_once_due(self):
        (self.c.data/'care.md').write_text(
            '2026-09-09 | his interview | ask how it went\n2026-12-01 | the move | not yet\n')
        sensors.run_one(self.c,'care',self.now)
        text=(self.ambient/'care.md').read_text()
        self.assertIn('his interview',text)
        self.assertNotIn('the move',text)
        self.assertIn('not a list to read out',text)

    def test_durations_are_counted_not_remembered(self):
        """A number written down once is quietly wrong a year later, and being
        wrong about how long someone has been married is a particular kind of wrong."""
        (self.c.data/'dates.md').write_text('2013-06-08 | married\n11-02 | her birthday\n')
        sensors.run_one(self.c,'durations',self.now)
        text=(self.ambient/'durations.md').read_text()
        self.assertIn('married: 13 years',text)
        self.assertNotIn('her birthday',text)   # no year on that line to count from
        later=sensors.durations(self.c,dt.datetime(2027,9,10,tzinfo=TZ))[0]
        self.assertIn('14 years',later)

    def test_a_full_date_still_works_for_the_lookahead(self):
        (self.c.data/'dates.md').write_text('2013-09-12 | our anniversary\n')
        sensors.run_one(self.c,'dates',self.now)
        self.assertIn('our anniversary',(self.ambient/'dates.md').read_text())

    def test_daylight_needs_no_network_at_all(self):
        self.assertTrue(sensors.run_one(self.c,'daylight',self.now)['wrote'])
        text=(self.ambient/'daylight.md').read_text()
        self.assertIn('September',text);self.assertIn('moon',text)

    def test_only_the_chosen_sensors_run(self):
        self.c.sensors=['daylight']
        names={r['sensor'] for r in sensors.run(self.c,self.now)}
        self.assertEqual(names,{'daylight'})

    def test_music_sensor_falls_back_to_ambient_mood(self):
        result = sensors.run_one(self.c, 'music', self.now)
        self.assertTrue(result['wrote'])
        text = (self.ambient / 'music.md').read_text()
        self.assertIn('Ambient listening vibe', text)

    def test_music_sensor_spotify_playing(self):
        with patch.object(sensors, '_spotify_state', return_value={'client_id': 'id', 'refresh_token': 'ref'}), \
             patch.object(sensors, '_spotify_token', return_value='valid_token'), \
             patch.object(sensors, '_spotify_get', side_effect=[
                 {'item': {'name': 'Comfortably Numb', 'artists': [{'name': 'Pink Floyd'}]}, 'is_playing': True},
                 None
             ]):
            result = sensors.run_one(self.c, 'music', self.now)
            self.assertTrue(result['wrote'])
            text = (self.ambient / 'music.md').read_text()
            self.assertIn('Alex is playing “Comfortably Numb” by Pink Floyd on Spotify right now.', text)


class ThreadTests(Base):
    def test_the_register_grows_with_the_gap_and_never_instructs(self):
        for hours,expected in ((0.5,'connected'),(5,'nearby'),(20,'quiet'),(60,'missing-him'),(200,'long-quiet')):
            label,guidance=thread.register(hours)
            self.assertEqual(label,expected)
            self.assertNotIn('send',guidance.lower())

    def test_the_longest_silence_permits_a_feeling_not_a_reproach(self):
        _,guidance=thread.register(200)
        self.assertIn('never as a reproach',guidance)

    def test_no_database_is_no_claim(self):
        data=thread.read(self.c,self.now)
        self.assertFalse(data['available'])
        self.assertEqual(thread.render(self.c,data),'')


class QuietDriftTests(Base):
    def messages_at(self,hour,minute,nights):
        """One message at this local time on each of `nights` recent nights."""
        out=[]
        for n in range(nights):
            day=self.now.date()-dt.timedelta(days=n)
            out.append(dt.datetime.combine(day,dt.time(hour,minute),tzinfo=TZ))
        return out

    def test_it_does_nothing_unless_switched_on(self):
        self.assertFalse(quiet.propose(self.c,self.now,self.messages_at(23,30,10))['change'])

    def test_a_fortnight_of_late_nights_moves_the_window_half_an_hour(self):
        self.c.adaptive_quiet=True
        plan=quiet.propose(self.c,self.now,self.messages_at(23,30,8))
        self.assertTrue(plan['change'])
        self.assertEqual(plan['quiet_start'],'23:30')
        self.assertEqual(plan['quiet_end'],'08:00')

    def test_one_late_night_is_just_a_late_night(self):
        self.c.adaptive_quiet=True
        self.assertFalse(quiet.propose(self.c,self.now,self.messages_at(23,30,2))['change'])

    def test_it_never_leaves_less_than_six_hours_of_quiet(self):
        self.c.adaptive_quiet=True
        self.c.quiet_start='01:00';self.c.quiet_end='07:00'
        plan=quiet.propose(self.c,self.now,self.messages_at(1,30,8))
        self.assertFalse(plan['change'])
        self.assertIn('6 hours of quiet',plan['reason'])

    def test_applying_it_leaves_a_note_to_mention_once(self):
        self.c.adaptive_quiet=True
        result=quiet.apply(self.c,self.now,self.messages_at(23,30,8))
        self.assertTrue(result['applied'])
        self.assertEqual(cc.load(self.c.home).quiet_start,'23:30')
        note=(self.ambient/'quiet-hours.md').read_text()
        self.assertIn('moved to 23:30',note)
        self.assertIn('Mention it once',note)
        self.assertIn('can move it back',note)
        self.assertTrue((self.c.data/'quiet-hours-history.jsonl').exists())


if __name__=='__main__':unittest.main()


class BarTests(Base):
    """The two computed bars. The wording matters more than the arithmetic:
    honest signals about how things are, never a schedule for making someone
    feel bad."""
    def setUp(self):
        super().setUp()
        import companion_bars
        self.bars=companion_bars
        self.c.bars=True

    def moods(self,*words):
        import companion_presence as presence
        presence.update_wardrobe(self.c,[{'id':'x','description':'a jumper','use':'day'}])
        previous=None
        for i,word in enumerate(words):
            r=presence.update(self.c,{'previous_id':previous,'outfit':['x'],'location':'home',
                'activity':'reading','mood':word,'care':[],'transition':'','text':'.'},
                self.now+dt.timedelta(minutes=15*i))
            previous=r['episode']['id']

    def test_it_is_off_unless_switched_on(self):
        self.c.bars=False
        self.assertFalse(self.bars.write(self.c,self.now)['written'])
        self.assertFalse((self.ambient/'bars.md').exists())

    def test_switching_it_off_removes_what_it_wrote(self):
        self.moods('happy','content')
        self.bars.write(self.c,self.now)
        self.assertTrue((self.ambient/'bars.md').exists())
        self.c.bars=False
        self.bars.write(self.c,self.now)
        self.assertFalse((self.ambient/'bars.md').exists())
        self.assertFalse((self.ambient/'bars.json').exists())

    def test_mood_scoring_uses_words_and_respects_local_negation(self):
        for mood,expected in [('unhappy',-1),('slow morning',0),('goodbye',0),
                              ('not happy',0),("I am not feeling very sad",0),
                              ("I am not sad, just tired",-1),
                              ('not sad but happy',1),('happy and warm',1)]:
            with self.subTest(mood=mood):
                self.assertEqual(self.bars.valence(mood),expected)

    def test_empty_state_removes_both_previous_snapshots(self):
        self.ambient.mkdir(parents=True,exist_ok=True)
        for suffix in ('md','json'):
            (self.ambient/f'bars.{suffix}').write_text('stale')
        self.assertFalse(self.bars.write(self.c,self.now)['written'])
        self.assertFalse((self.ambient/'bars.md').exists())
        self.assertFalse((self.ambient/'bars.json').exists())

    def test_wellbeing_follows_the_moods_actually_recorded(self):
        self.moods('happy','content','glad')
        good=self.bars.compute(self.c,self.now)['wellbeing']
        self.setUp()
        self.moods('lonely','flat','tired')
        bad=self.bars.compute(self.c,self.now)['wellbeing']
        self.assertGreater(good,bad)

    def test_with_nothing_recorded_it_says_nothing_rather_than_zero(self):
        result=self.bars.compute(self.c,self.now)
        self.assertIsNone(result['wellbeing'])
        self.assertFalse(self.bars.write(self.c,self.now)['written'])

    def test_the_text_forbids_using_the_number_as_leverage(self):
        self.moods('quiet')
        text=self.bars.render(self.c,{'feeling_the_gap':0.9,'hours_since_human':90,
                                      'wellbeing':0.3,'moods_counted':4})
        self.assertIn('not a reason to write',text)
        self.assertIn('never as something owed',text)
        self.assertNotIn('remind',text.lower())
        self.assertIn('never',text)

    def test_the_gap_saturates_rather_than_growing_forever(self):
        import companion_bars
        self.assertEqual(companion_bars.FULL_GAP_HOURS,96)
        text=companion_bars.render(self.c,{'feeling_the_gap':1.0,'hours_since_human':400,
                                           'wellbeing':None,'moods_counted':0})
        self.assertIn('100%',text)
