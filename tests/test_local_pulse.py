import datetime as dt
import io
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'kit/scripts'))
import companion_config as cc
import companion_local_pulse as worker
import companion_presence as presence


class LocalPulseTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        root=pathlib.Path(temp.name)
        self.c=cc.Companion(hermes_root=root/'home',vault=root/'vault')
        self.c.home.mkdir();self.c.soul.write_text('You are Nova, an adult companion.')
        self.now=dt.datetime(2026,9,12,12,15,tzinfo=dt.timezone.utc)
        presence.update_wardrobe(self.c,[{'id':'tee','description':'green tee','use':'day'}])
        self.data={'outfit':['tee'],'location':'kitchen','activity':'lunch','mood':'calm',
                   'wants':[],'care':[],'private_stance':'A quiet day.',
                   'transition':'Continuing lunch.','text':'Lunch.'}
        presence.update(self.c,dict(self.data,previous_id=None),self.now-dt.timedelta(minutes=15))

    def response(self,finish='stop'):
        return io.BytesIO(json.dumps({'choices':[{'finish_reason':finish,
                        'message':{'content':json.dumps(self.data)}}]}).encode())

    def test_only_complete_valid_model_output_is_recorded_and_tick_is_idempotent(self):
        previous=presence.current(self.c)['id']
        with patch.object(worker.urllib.request,'urlopen',return_value=self.response('length')):
            with self.assertRaisesRegex(ValueError,'incomplete'):
                worker.pulse(self.c,'http://127.0.0.1:11435/v1','test',now=self.now)
        self.assertEqual(presence.current(self.c)['id'],previous)
        with patch.object(worker.urllib.request,'urlopen',return_value=self.response()) as call:
            self.assertEqual(worker.pulse(self.c,'http://127.0.0.1:11435/v1','test',now=self.now)['status'],'recorded')
            self.assertEqual(worker.pulse(self.c,'http://127.0.0.1:11435/v1','test',now=self.now)['status'],'skipped')
            self.assertEqual(call.call_count,1)

    def test_concurrent_chat_transition_is_never_overwritten(self):
        def response(*args,**kwargs):
            current=presence.current(self.c)
            presence.update(self.c,dict(self.data,previous_id=current['id'],id='chat-transition',
                            activity='reading',transition='Finished lunch.'),self.now)
            return self.response()
        with patch.object(worker.urllib.request,'urlopen',side_effect=response):
            with self.assertRaisesRegex(ValueError,'State changed'):
                worker.pulse(self.c,'http://127.0.0.1:11435/v1','test',now=self.now)
        self.assertEqual(presence.current(self.c)['state']['activity'],'reading')

    def test_impossible_plan_gets_one_correction_and_never_an_unbounded_loop(self):
        self.data.update(duration_minutes=30,next=dict(activity='run',duration_minutes=45,reason='Exercise'),
            commitments=[dict(id='visit',title='Guest arrives',starts_at='2026-09-12T13:00:00+00:00',
                ends_at='2026-09-12T14:00:00+00:00',buffer_minutes=15,status='planned',reason='Agreed')])
        bad=self.response()
        self.data['next']=dict(activity='stretch',duration_minutes=10,reason='Run will not fit')
        good=self.response()
        with patch.object(worker.urllib.request,'urlopen',side_effect=[bad,good]) as call:
            worker.pulse(self.c,'http://127.0.0.1:11435/v1','test',now=self.now)
            self.assertEqual(call.call_count,2)
            self.assertIn('PLAN CONFLICT',json.loads(call.call_args.args[0].data)['messages'][-1]['content'])
        self.assertEqual(presence.current(self.c)['state']['next']['activity'],'stretch')
        previous=presence.current(self.c)['id']
        self.data['next']=dict(activity='run',duration_minutes=45,reason='Exercise')
        with patch.object(worker.urllib.request,'urlopen',side_effect=lambda *a,**k:self.response()) as call:
            with self.assertRaisesRegex(ValueError,'PLAN CONFLICT'):
                worker.pulse(self.c,'http://127.0.0.1:11435/v1','test',now=self.now+dt.timedelta(minutes=15))
            self.assertEqual(call.call_count,2)
        self.assertEqual(presence.current(self.c)['id'],previous)

    def test_daily_phase_can_follow_a_confirmed_pulse_but_cannot_repeat(self):
        with patch.object(worker.urllib.request,'urlopen',return_value=self.response()):
            worker.pulse(self.c,'http://127.0.0.1:11435/v1','test',now=self.now)
        with patch.object(worker.urllib.request,'urlopen',side_effect=lambda *a,**k:self.response()) as call:
            result=worker.pulse(self.c,'http://127.0.0.1:11435/v1','test',now=self.now+dt.timedelta(minutes=1),phase='morning')
            self.assertEqual(result['status'],'recorded')
            self.assertEqual(presence.current(self.c)['id'],'state-morning-2026-09-12')
            result=worker.pulse(self.c,'http://127.0.0.1:11435/v1','test',now=self.now+dt.timedelta(hours=1),phase='morning')
            self.assertEqual(result['status'],'skipped');self.assertEqual(call.call_count,1)


if __name__=='__main__':unittest.main()
