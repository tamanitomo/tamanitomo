"""Day continuity, scheduling constraints and visuals share one authoritative record."""
import datetime as dt
import pathlib
import sys
import tempfile
import unittest
from PIL import Image
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'kit/scripts'))
import companion_config as cc
import companion_presence as presence
import companion_day as day
import companion_portrait as portrait
import companion_timeline as timeline
import companion_preread as preread
import companion_context as context

class DayTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name)
        self.c=cc.Companion(agent='Nova',hermes_root=self.root/'h',vault=self.root/'v',
                            image_timeline=True,image_style='realistic')
        self.now=dt.datetime(2026,9,12,18,tzinfo=dt.timezone.utc)
        presence.update_wardrobe(self.c,[{'id':'tee','description':'green tee','use':'everyday'}])
        self.visual=dict(pose='seated at the table',hands='holding a mug',gaze='at the page',
                         framing='candid wide view',props='book and mug',expression='absorbed',lighting='evening light')
        self.promise=dict(id='friends',title='Friends arriving',starts_at='2026-09-12T19:00:00+00:00',
                          ends_at='2026-09-12T21:00:00+00:00',buffer_minutes=30,status='planned',reason='Agreed today')
    def write(self,minutes=0,**kw):
        current=presence.current(self.c)
        data=dict(previous_id=current['id'] if current else None,outfit=['tee'],activity='reading',
                  location='home',mood='calm',text='Reading.',transition='')
        data.update(kw)
        return presence.update(self.c,data,self.now+dt.timedelta(minutes=minutes))['episode']
    def test_continuation_transition_retry_and_no_invented_previous(self):
        first=self.write(duration_minutes=40,next=dict(activity='breakfast',duration_minutes=20,reason='Hungry'),visual=self.visual)
        second=self.write(15)
        self.assertEqual(first['state']['started_at'],second['state']['started_at'])
        self.assertIsNone(second['state']['previous'])
        third=self.write(30,activity='breakfast',transition='Put the book away.',next=None)
        self.assertEqual(third['state']['previous']['activity'],'reading')
        self.assertEqual(third['state']['started_at'],(self.now+dt.timedelta(minutes=30)).isoformat())
        self.assertEqual(third['state']['visual'],{})
        retry=dict(previous_id=second['id'],outfit=['tee'],activity='breakfast',location='home',
                   mood='calm',text='Reading.',transition='Put the book away.',next=None)
        self.assertFalse(presence.update(self.c,retry,self.now+dt.timedelta(minutes=30))['written'])
    def test_promises_survive_omission_empty_patch_midnight_and_advancer(self):
        self.write(commitments=[self.promise])
        self.write(15,commitments=[])
        carried=presence.advance(self.c,self.now+dt.timedelta(hours=7))['episode']
        self.assertEqual(carried['state']['commitments'],[self.promise])
        self.assertFalse(carried['state']['confirmed'])
        self.assertIn('OVERDUE',day.render(carried['state'],self.now+dt.timedelta(hours=7)))
        self.assertFalse(timeline.prepare(self.c,self.now+dt.timedelta(hours=7))['ready'])
        final=self.write(435,commitments=[dict(self.promise,status='cancelled',reason='Plans changed')])
        self.assertEqual(final['state']['commitments'][0]['status'],'cancelled')
    def test_conflicts_reach_chat_and_jobs_and_deadlines_wake_monitor(self):
        row=self.write(-60,duration_minutes=10,commitments=[self.promise],
                       next=dict(activity='run',duration_minutes=45,reason='Want some exercise'))
        self.assertIn('PLAN CONFLICT',day.render(row['state'],self.now))
        self.assertIn('Friends arriving',context.build(self.c,now=self.now))
        self.assertIn('PLAN CONFLICT',preread.preread(self.c,self.now))
        self.assertNotEqual(preread.fingerprint(self.c,self.now+dt.timedelta(minutes=29)),
                            preread.fingerprint(self.c,self.now+dt.timedelta(minutes=30)))
    def test_pre_upgrade_record_retries_without_rewriting_history(self):
        from companion_life import record
        old=dict(location='home',activity='reading',outfit=[dict(id='tee',description='green tee')],
                 mood='calm',wants=[],private_stance='',care=[],transition='',confirmed=True)
        record(self.c.life,'Reading.','reading','in_progress',self.now,'legacy',self.c.agent,self.c.human,state=old)
        result=presence.update(self.c,dict(id='legacy',previous_id=None,outfit=['tee'],location='home',
                               activity='reading',mood='calm',text='Reading.'),self.now)
        self.assertFalse(result['written'])
        upgraded=self.write(15)
        self.assertEqual(upgraded['state']['started_at'],self.now.isoformat())
        self.assertNotIn('started_at',list(presence.events(self.c))[-1]['state'])

    def test_new_impossible_plan_is_rejected_without_losing_previous(self):
        first=self.write(commitments=[self.promise])
        with self.assertRaisesRegex(ValueError,'PLAN CONFLICT'):
            self.write(15,duration_minutes=30,next=dict(activity='run',duration_minutes=25,reason='Shorter run'))
        self.assertEqual(presence.current(self.c)['id'],first['id'])
        row=self.write(15,duration_minutes=15,next=dict(activity='stretch',duration_minutes=10,reason='Run deferred until tomorrow'))
        self.assertEqual(row['state']['next']['activity'],'stretch')

    def test_rejected_commitment_write_is_atomic(self):
        first=self.write(commitments=[self.promise])
        for changes in (dict(starts_at='2026-09-12T19:00:00'),dict(ends_at=self.promise['starts_at']),
                        dict(status='cancelled',reason=''),dict(buffer_minutes=-1)):
            with self.assertRaises(ValueError):self.write(15,commitments=[dict(self.promise,**changes)])
            self.assertEqual(presence.current(self.c)['id'],first['id'])
    def test_visual_direction_uses_frozen_now_not_next(self):
        first=self.write(visual=self.visual,next=dict(activity='visit the moon',duration_minutes=60,reason='fiction'))
        self.write(15,activity='cooking',transition='Went to cook.',visual=dict(self.visual,hands='stirring soup'))
        output=portrait.recorded_overrides(self.c,record=first)
        self.assertEqual(output['camera'],'candid wide view')
        self.assertEqual(output['lighting'],'evening light')
        self.assertIn('holding a mug',output['scene']);self.assertNotIn('moon',output['scene'])
        self.assertNotIn('soup',output['scene']);self.assertEqual(output['wardrobe'],'green tee')
    def test_successful_unchanged_images_skip_but_changes_capture(self):
        self.write(visual=self.visual)
        claim=timeline.prepare(self.c,self.now)
        image=self.root/'image.png';Image.new('RGB',(8,8)).save(image)
        timeline.save(self.c,claim['capture_id'],str(image),'test',self.now)
        self.write(15,mood='happy',next=dict(activity='walk',duration_minutes=30,reason='Later'))
        self.assertFalse(timeline.prepare(self.c,self.now+dt.timedelta(minutes=15))['ready'])
        self.write(30,visual=dict(self.visual,pose='reclining on the sofa'))
        self.assertTrue(timeline.prepare(self.c,self.now+dt.timedelta(minutes=30))['ready'])
    def test_failed_capture_does_not_suppress_retry_or_another_profile(self):
        self.write(visual=self.visual,commitments=[self.promise])
        claim=timeline.prepare(self.c,self.now)
        timeline.fail(self.c,claim['capture_id'],'renderer unavailable')
        self.write(15)
        self.assertTrue(timeline.prepare(self.c,self.now+dt.timedelta(minutes=15))['ready'])
        other=cc.Companion(agent='River',hermes_root=self.root/'other',vault=self.root/'other-vault')
        self.assertIsNone(presence.current(other))
        self.assertNotIn('Friends arriving',context.build(other,now=self.now))

if __name__=='__main__':unittest.main()
