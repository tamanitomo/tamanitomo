"""The queue and the dispatcher: what leaves, what waits, and what is dropped.

The incident these exist for is on the record. A companion whose restraint lived
in a prompt sent the same tick report four to six times a day for a week, held
the rest through quiet hours, and flushed the backlog at 00:07.
"""
import datetime as dt
import json
import pathlib,sys,tempfile,unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'kit/scripts'))
import companion_config as cc
import companion_outbox as outbox
import companion_dispatch as dispatch

TZ=dt.timezone.utc

class Base(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=pathlib.Path(self.tmp.name)
        self.c=cc.Companion(agent='Nova',human='Alex',hermes_root=root/'home',vault=root/'vault',
                            timezone='UTC',quiet_start='23:00',quiet_end='08:00',outreach_per_day=2)
        self.c.life.mkdir(parents=True,exist_ok=True)
        self.day=dt.datetime(2026,9,10,14,0,tzinfo=TZ)   # mid-afternoon, awake
        self.night=dt.datetime(2026,9,11,2,0,tzinfo=TZ)  # inside quiet hours
        self.evening=dt.datetime(2026,9,10,22,30,tzinfo=TZ)  # queued just before bed

    def q(self,**kw):
        now=kw.pop('now',self.day)
        entry={'kind':'text','body':'thinking about you','reason':'test'}
        entry.update(kw)
        return outbox.queue(self.c,entry,now)['entry']


class QueueTests(Base):
    def test_a_message_carries_an_expiry_from_the_moment_it_is_queued(self):
        entry=self.q()
        self.assertEqual(entry['status'],'queued')
        self.assertTrue(entry['expires_at']>entry['queued_at'])

    def test_media_needs_an_absolute_path_that_exists_by_send_time(self):
        with self.assertRaisesRegex(ValueError,'media_path'):self.q(kind='image')
        with self.assertRaisesRegex(ValueError,'absolute'):self.q(kind='image',media_path='pic.png')

    def test_a_full_queue_is_an_error_not_a_bigger_queue(self):
        for i in range(outbox.MAX_QUEUED):self.q(body=f'message {i}')
        with self.assertRaisesRegex(ValueError,'queue is full'):self.q(body='one too many')

    def test_the_fold_is_the_state_and_the_file_keeps_everything(self):
        entry=self.q()
        outbox.mark(self.c,entry['id'],'sent','ok',self.day)
        self.assertEqual([e['status'] for e in outbox.fold(self.c)],['sent'])
        self.assertEqual(outbox.waiting(self.c,self.day),[])
        self.assertIn('thinking about you',(self.c.life/'outbox.jsonl').read_text())

    def test_high_priority_goes_to_the_front(self):
        self.q(body='ordinary')
        self.q(body='urgent',priority='high')
        self.assertEqual([e['body'] for e in outbox.waiting(self.c,self.day)],['urgent','ordinary'])


class DispatcherTests(Base):
    def dispatch(self,now,**kw):
        with patch.object(dispatch,'deliver',return_value=(True,'sent')) as sent:
            result=dispatch.run(self.c,now,**kw)
        return result,sent

    def test_an_expired_message_is_dropped_and_never_sent_late(self):
        """The 00:07 backlog flush, prevented: an afternoon thought does not
        arrive in the small hours because the queue finally opened."""
        self.q(body='want to say goodnight',ttl_hours=1)
        result,sent=self.dispatch(self.day+dt.timedelta(hours=4))
        self.assertEqual(result['handled'][0]['action'],'expire')
        sent.assert_not_called()
        self.assertEqual([e['status'] for e in outbox.fold(self.c)],['expired'])

    def test_a_backlog_is_never_flushed_at_once(self):
        for i in range(3):self.q(body=f'thought {i}')
        result,sent=self.dispatch(self.day)
        self.assertEqual(sent.call_count,1)
        self.assertEqual(result['still_waiting'],2)

    def test_quiet_hours_hold_a_message_rather_than_dropping_it(self):
        self.q(body='awake and thinking',now=self.evening)
        result,sent=self.dispatch(self.night)
        self.assertEqual(result['handled'][0]['action'],'hold')
        self.assertIn('quiet hours',result['handled'][0]['reason'])
        sent.assert_not_called()

    def test_being_visibly_awake_beats_the_sleep_window(self):
        """A window describes someone's night. If they just wrote, they are up."""
        self.q(body='me too',now=self.evening)
        thread=self.c.soul_dir/'ambient';thread.mkdir(parents=True,exist_ok=True)
        (thread/'relationship-thread.json').write_text(json.dumps(
            {'last_from_human':(self.night-dt.timedelta(minutes=5)).isoformat()}))
        result,sent=self.dispatch(self.night)
        self.assertEqual(result['handled'][0]['action'],'sent')

    def test_being_awake_does_not_raise_the_daily_cap(self):
        thread=self.c.soul_dir/'ambient';thread.mkdir(parents=True,exist_ok=True)
        (thread/'relationship-thread.json').write_text(json.dumps(
            {'last_from_human':(self.night-dt.timedelta(minutes=5)).isoformat()}))
        for i in range(3):self.q(body=f'thought {i}',now=self.evening)
        for _ in range(2):self.dispatch(self.night)
        result,sent=self.dispatch(self.night)
        self.assertEqual(result['handled'][0]['action'],'hold')
        self.assertIn('Daily limit',result['handled'][0]['reason'])

    def test_an_old_message_from_the_human_does_not_count_as_awake(self):
        self.q(body='me too',now=self.evening)
        thread=self.c.soul_dir/'ambient';thread.mkdir(parents=True,exist_ok=True)
        (thread/'relationship-thread.json').write_text(json.dumps(
            {'last_from_human':(self.night-dt.timedelta(hours=5)).isoformat()}))
        result,_=self.dispatch(self.night)
        self.assertEqual(result['handled'][0]['action'],'hold')

    def test_a_photo_set_to_ask_is_withheld_with_a_reason_she_can_act_on(self):
        self.c.content_permissions={'image':'ask'}
        self.q(kind='image',body='the light in the kitchen',media_path='/tmp/x.png')
        result,sent=self.dispatch(self.day)
        self.assertEqual(result['handled'][0]['action'],'withhold')
        self.assertIn('offer it in words',result['handled'][0]['reason'])
        sent.assert_not_called()

    def test_a_photo_set_to_no_never_goes(self):
        self.c.content_permissions={'image':'no'}
        self.q(kind='image',body='look',media_path='/tmp/x.png')
        result,sent=self.dispatch(self.day)
        self.assertEqual(result['handled'][0]['action'],'withhold')
        sent.assert_not_called()

    def test_the_daily_cap_holds_and_is_counted_on_disk(self):
        for i in range(3):self.q(body=f'thought {i}')
        for _ in range(2):self.dispatch(self.day)
        result,sent=self.dispatch(self.day)
        self.assertEqual(result['handled'][0]['action'],'hold')
        self.assertIn('Daily limit',result['handled'][0]['reason'])
        sent.assert_not_called()

    def test_a_failed_send_keeps_its_slot_and_is_not_retried(self):
        self.q(body='hello')
        with patch.object(dispatch,'deliver',return_value=(False,'unconfirmed')):
            dispatch.run(self.c,self.day)
        # Phase 1B C2 (PHASE1B_DESIGN 7.5): an UNCONFIRMED send is `unknown`, not `failed` --
        # Hermes may have delivered it. Either way the slot is kept and it is never retried.
        self.assertEqual([e['status'] for e in outbox.fold(self.c)],['unknown'])
        # the slot was spent, so a second message this hour is capped after one more
        self.q(body='again')
        result,_=self.dispatch(self.day)
        self.assertEqual(result['handled'][0]['action'],'sent')
        self.q(body='third')
        result,_=self.dispatch(self.day)
        self.assertEqual(result['handled'][0]['action'],'hold')

    def test_not_before_holds_without_burning_anything(self):
        self.q(body='morning',not_before=(self.day+dt.timedelta(hours=2)).isoformat())
        result,sent=self.dispatch(self.day)
        self.assertEqual(result['handled'][0]['action'],'hold')
        result,sent=self.dispatch(self.day+dt.timedelta(hours=3))
        self.assertEqual(result['handled'][0]['action'],'sent')

    def test_a_dry_run_still_expires_but_sends_nothing(self):
        self.q(body='stale',ttl_hours=1)
        self.q(body='fresh')
        result,sent=self.dispatch(self.day+dt.timedelta(hours=4),send=False)
        actions=[h['action'] for h in result['handled']]
        self.assertIn('expire',actions);self.assertIn('would-send',actions)
        sent.assert_not_called()


if __name__=='__main__':unittest.main()
