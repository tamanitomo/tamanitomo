"""Lived state remains continuous across ticks, wardrobe edits, races and midnight."""
import datetime as dt
import pathlib,sys,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'kit/scripts'))
import companion_config as cc
import companion_presence as presence
import companion_context as context

class PresenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=pathlib.Path(self.tmp.name)
        self.c=cc.Companion(hermes_root=root/'home',vault=root/'vault')
        self.now=dt.datetime(2026,9,9,23,45,tzinfo=dt.timezone.utc)
        presence.update_wardrobe(self.c,[{'id':'pajamas','description':'blue pajamas','use':'sleep'},
                                       {'id':'gym','description':'running shorts and tee','use':'exercise'}])
    def data(self,**updates):
        data={'previous_id':None,'outfit':['pajamas'],'location':'home','activity':'reading',
              'mood':'relaxed','care':[],'transition':'','text':'Reading before bed.'}
        data.update(updates);return data
    def test_state_survives_midnight_and_retries_do_not_duplicate(self):
        first=presence.update(self.c,self.data(),self.now)
        repeat=presence.update(self.c,self.data(),self.now)
        self.assertFalse(repeat['written'])
        second=presence.update(self.c,self.data(previous_id=first['episode']['id']),self.now+dt.timedelta(minutes=15))
        self.assertEqual(second['episode']['state']['outfit'],first['episode']['state']['outfit'])
        self.assertEqual(len(list(presence.events(self.c))),2)
        self.assertEqual(presence.current(self.c)['id'],second['episode']['id'])
    def test_outfit_location_and_activity_changes_need_a_transition(self):
        first=presence.update(self.c,self.data(),self.now)['episode']
        for change in ({'outfit':['gym']},{'location':'gym'},{'activity':'sleeping'}):
            with self.assertRaisesRegex(ValueError,'transition'):
                presence.update(self.c,self.data(previous_id=first['id'],**change),self.now+dt.timedelta(minutes=15))
        second=presence.update(self.c,self.data(previous_id=first['id'],activity='sleeping',transition='Put my book down and went to bed.',care=['brushed teeth']),self.now+dt.timedelta(minutes=15))
        self.assertEqual(second['episode']['state']['care'],['brushed teeth'])
    def test_stale_update_cannot_overwrite_newer_chat_transition(self):
        first=presence.update(self.c,self.data(),self.now)['episode']
        presence.update(self.c,self.data(previous_id=first['id'],id='bedtime',activity='sleeping',transition='Went to bed.'),self.now+dt.timedelta(minutes=1))
        with self.assertRaisesRegex(ValueError,'State changed'):
            presence.update(self.c,self.data(previous_id=first['id']),self.now+dt.timedelta(minutes=15))
        self.assertEqual(presence.current(self.c)['id'],'bedtime')
    def test_wardrobe_edits_do_not_change_historical_outfits(self):
        presence.update(self.c,self.data(),self.now)
        presence.update_wardrobe(self.c,[{'id':'pajamas','description':'repaired blue pajamas','use':'sleep','condition':'laundry'}])
        self.assertEqual(presence.current(self.c)['state']['outfit'][0]['description'],'blue pajamas')
        self.assertEqual(presence.show(self.c)['wardrobe']['items'][0]['last_worn'],self.now.isoformat())
    def test_unknown_outfits_are_rejected_and_current_state_is_in_context(self):
        with self.assertRaisesRegex(ValueError,'wardrobe'):presence.update(self.c,self.data(outfit=['made-up']),self.now)
        presence.update(self.c,self.data(),self.now)
        out=context.build(self.c,now=self.now)
        self.assertIn('blue pajamas',out);self.assertIn('home',out)

class EmotiveViewTests(unittest.TestCase):
    """Emotive.md is rendered from the state, so there is only one place a feeling
    lives and nothing that can disagree with it."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=pathlib.Path(self.tmp.name)
        self.c=cc.Companion(hermes_root=root/'home',vault=root/'vault')
        self.now=dt.datetime(2026,9,9,20,0,tzinfo=dt.timezone.utc)
        presence.update_wardrobe(self.c,[{'id':'pajamas','description':'blue pajamas','use':'sleep'}])

    def state(self,**kw):
        data={'previous_id':None,'outfit':['pajamas'],'location':'home','activity':'reading',
              'mood':'restless','care':[],'transition':'','text':'Reading.'}
        data.update(kw);return data

    def test_recording_a_state_writes_the_view(self):
        presence.update(self.c,self.state(wants=['an early night'],
                                          private_stance='a bit hurt he never answered'),self.now)
        text=(self.c.soul_dir/'Emotive.md').read_text(encoding='utf-8')
        self.assertIn('restless',text)
        self.assertIn('an early night',text)
        self.assertIn('a bit hurt he never answered',text)

    def test_an_edit_to_the_view_does_not_survive_the_next_state(self):
        first=presence.update(self.c,self.state(),self.now)['episode']
        (self.c.soul_dir/'Emotive.md').write_text('I am actually delighted.',encoding='utf-8')
        presence.update(self.c,self.state(previous_id=first['id'],mood='calmer'),
                        self.now+dt.timedelta(minutes=15))
        text=(self.c.soul_dir/'Emotive.md').read_text(encoding='utf-8')
        self.assertNotIn('actually delighted',text)
        self.assertIn('calmer',text)

    def test_wants_and_stance_are_optional_and_bounded(self):
        presence.update(self.c,self.state(),self.now)   # neither supplied
        self.assertEqual(presence.current(self.c)['state']['wants'],[])
        self.assertEqual(presence.current(self.c)['state']['private_stance'],'')
        with self.assertRaisesRegex(ValueError,'wants'):
            presence.update(self.c,self.state(wants=['a']*6),self.now)

    def test_the_view_says_so_when_no_state_exists_yet(self):
        self.assertIn('nothing here to feel',presence.render_emotive(self.c,self.now))
