"""Regressions for the 2026-09-23 audit: permissions, privacy, outreach and routines.

Each class pins one finding, so a later change that reopens it fails by name.
"""
import datetime as dt, json, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'kit/scripts')]
import companion_config as cc
import companion_media as media
import companion_media_review as review
from PIL import Image


def companion(root,**kw):
    c=cc.Companion(profile='test',agent='Test',vault=root/'vault',hermes_root=root/'hermes',
                   context_mode='fixed',**kw)
    c.home.mkdir(parents=True,exist_ok=True);c.soul_dir.mkdir(parents=True,exist_ok=True);c.save()
    return c


class AdultGateTests(unittest.TestCase):
    """The switches say the user is willing; only the one gate says the image may go."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.c=companion(Path(self.temp.name),boundary='girlfriend',explicit=True,adult_images=True)
        self.path=self.c.data/'creations/image-studio/a.png';self.path.parent.mkdir(parents=True)
        Image.new('RGB',(8,8),'blue').save(self.path)

    def test_switches_alone_are_not_readiness(self):
        with patch.object(media,'intimacy_gate',return_value=(False,['Intimacy stage (Friends) is not yet at Bonded readiness.'])):
            ready,why=media.adult_ready(self.c)
        self.assertFalse(ready);self.assertIn('Bonded',why[0])
        self.c.adult_images=False
        with patch.object(media,'intimacy_gate',return_value=(True,[])):
            self.assertFalse(media.adult_ready(self.c)[0])

    def test_a_caller_asking_for_nsfw_does_not_clear_it(self):
        seen={}
        def fake(c,preset,category,overrides,report,allow_nsfw,*rest):
            seen['allow']=allow_nsfw;return {'path':str(self.path)}
        with patch.object(media,'_generate',side_effect=fake), \
                patch.object(media,'intimacy_gate',return_value=(False,['not yet'])):
            media.generate(self.c,allow_nsfw=True)
        self.assertFalse(seen['allow'])
        with patch.object(media,'_generate',side_effect=fake), \
                patch.object(media,'intimacy_gate',return_value=(True,[])):
            media.generate(self.c)
        self.assertTrue(seen['allow'])

    def test_a_cached_pass_does_not_survive_the_gate_closing(self):
        """Passed while ready, queued, then the relationship stepped back: it stays home."""
        import hashlib
        digest=hashlib.sha256(self.path.read_bytes()).hexdigest()
        review.write_metadata(self.path,{'rating':'nsfw','review':{'status':'passed','sha256':digest,'provider':'x'}})
        with patch.object(media,'intimacy_gate',return_value=(True,[])):
            review.ensure_delivery(self.c,self.path,'x')
        with patch.object(media,'intimacy_gate',return_value=(False,['locked at friendship'])):
            with self.assertRaisesRegex(ValueError,'rated adult'):review.ensure_delivery(self.c,self.path,'x')
        # Even with pre-delivery review switched off, a known adult rating is held.
        review.save_preferences(self.c,{'review_before_delivery':False})
        with patch.object(media,'intimacy_gate',return_value=(False,['not yet'])):
            with self.assertRaisesRegex(ValueError,'rated adult'):review.ensure_delivery(self.c,self.path,'x')

    def test_a_safe_picture_is_unaffected(self):
        import hashlib
        digest=hashlib.sha256(self.path.read_bytes()).hexdigest()
        review.write_metadata(self.path,{'rating':'safe','review':{'status':'passed','sha256':digest,'provider':'x'}})
        with patch.object(media,'intimacy_gate',return_value=(False,['not yet'])):
            review.ensure_delivery(self.c,self.path,'x')

    def test_undressed_renders_use_the_same_gate(self):
        import companion_portrait as portrait
        with patch.object(media,'intimacy_gate',return_value=(False,['not yet'])):
            self.assertFalse(portrait.undressed_render_allowed(self.c)[0])
        with patch.object(media,'intimacy_gate',return_value=(True,[])):
            self.assertTrue(portrait.undressed_render_allowed(self.c)[0])


class CoverageTests(unittest.TestCase):
    """Socks, a cardigan or a top alone do not cover underwear."""
    CLOSET=[{'id':'closet-underwear-1','category':'underwear','description':'cream briefs'},
            {'id':'closet-socks-1','category':'day','description':'ankle socks'},
            {'id':'closet-day-top-1','category':'day','description':'ribbed crop top'},
            {'id':'closet-cardigan','category':'outerwear','description':'knit cardigan'},
            {'id':'closet-jeans','category':'day','description':'blue jeans'},
            {'id':'teal-ribbed-tank','category':'day','covers':'top','description':'teal tank'}]

    def state(self,*ids):
        known={i['id']:i for i in self.CLOSET}
        return {'outfit':[{'id':i,'description':known[i]['description']} for i in ids]}

    def test_nothing_over_the_hips_is_underwear_and_described_in_full(self):
        import companion_presence as presence
        for ids in (('closet-underwear-1','closet-socks-1'),('closet-underwear-1','closet-day-top-1'),
                    ('closet-underwear-1','closet-cardigan'),('closet-underwear-1','teal-ribbed-tank'),
                    ('closet-underwear-1',)):
            with self.subTest(ids=ids):
                kind,text=presence.visible_outfit(self.state(*ids),self.CLOSET)
                self.assertEqual(kind,'underwear')
                self.assertIn('cream briefs',text)
                self.assertEqual(presence.private_reason(self.state(*ids),self.CLOSET),'undressed')

    def test_a_bottom_hides_the_base_layer(self):
        import companion_presence as presence
        kind,text=presence.visible_outfit(self.state('closet-underwear-1','closet-day-top-1',
                                                      'closet-jeans','closet-socks-1'),self.CLOSET)
        self.assertIsNone(kind)
        self.assertNotIn('briefs',text);self.assertIn('blue jeans',text);self.assertIn('ankle socks',text)

    def test_the_starter_closet_states_what_each_piece_covers(self):
        import companion_lifestyle as lifestyle, companion_presence as presence
        with tempfile.TemporaryDirectory() as tmp:
            c=companion(Path(tmp))
            items=lifestyle.build_starter_wardrobe(c)
        self.assertTrue(all(i.get('covers') in presence.COVERS for i in items))
        by={i['id']:i['covers'] for i in items}
        self.assertEqual(by['closet-socks-1'],'none');self.assertEqual(by['closet-day-top-1'],'top')
        self.assertEqual(by['closet-occasion'],'full')


class DeclaredPrivacyTests(unittest.TestCase):
    """Her own "not this one" is final; permissions only unlock undressed moments."""
    def setUp(self):
        import companion_presence as presence
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.c=companion(Path(self.temp.name),image_timeline=True)
        presence.update_wardrobe(self.c,[{'id':'tee','description':'green tee','use':'day','category':'day'},
                                         {'id':'jeans','description':'jeans','use':'day','category':'day','covers':'bottom'}])
        self.now=dt.datetime.now(dt.timezone.utc)

    def test_declared_private_is_never_photographed(self):
        import companion_presence as presence, companion_timeline as timeline, companion_portrait as portrait
        presence.update(self.c,{'previous_id':None,'outfit':['tee','jeans'],'location':'bedroom',
                                'activity':'crying over a letter','mood':'raw','text':'x',
                                'private':True,'setting':'private'},self.now)
        with patch.object(portrait,'undressed_render_allowed',return_value=(True,'')):
            out=timeline.prepare(self.c,self.now)
        self.assertFalse(out['ready']);self.assertIn('marked this moment private',out['reason'])
        self.assertEqual(timeline.fingerprint(self.c,self.now),'private moment (declared)\n')


class WatchDeliversTests(unittest.TestCase):
    """Kit jobs deliver locally, so the watch has to send its own alert."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.c=companion(Path(self.temp.name),quiet_start='23:00',quiet_end='08:00',timezone='UTC')

    def run_at(self,hour,sent):
        import companion_watch as watch
        def notify(c,message):sent.append(message);return True,'sent'
        with patch.object(watch,'problems',return_value=['the job "x" is missing']):
            return watch.run(self.c,dt.datetime(2026,9,23,hour,tzinfo=dt.timezone.utc),notify=notify)

    def test_held_overnight_then_sent_once(self):
        sent=[]
        self.assertIn('quiet hours',self.run_at(3,sent)['held'])
        self.assertEqual(sent,[])
        self.assertTrue(self.run_at(9,sent)['delivered'])
        self.assertEqual(len(sent),1)
        self.assertTrue(self.run_at(10,sent)['repeat_suppressed'])
        self.assertEqual(len(sent),1)

    def test_a_failed_send_is_not_recorded_as_told(self):
        import companion_watch as watch
        with patch.object(watch,'problems',return_value=['broken']):
            out=watch.run(self.c,dt.datetime(2026,9,23,12,tzinfo=dt.timezone.utc),
                          notify=lambda c,m:(False,'unconfirmed'))
            self.assertFalse(out['delivered'])
            sent=[]
            again=watch.run(self.c,dt.datetime(2026,9,23,13,tzinfo=dt.timezone.utc),
                            notify=lambda c,m:(sent.append(m) or (True,'sent')))
        self.assertTrue(again['delivered']);self.assertEqual(len(sent),1)

    def test_a_look_by_hand_does_not_silence_the_alert(self):
        import companion_watch as watch
        with patch.object(watch,'problems',return_value=['broken']):
            watch.run(self.c,dt.datetime(2026,9,23,12,tzinfo=dt.timezone.utc),record=False)
            sent=[]
            watch.run(self.c,dt.datetime(2026,9,23,12,5,tzinfo=dt.timezone.utc),
                      notify=lambda c,m:(sent.append(m) or (True,'sent')))
        self.assertEqual(len(sent),1)


class MorningTests(unittest.TestCase):
    """The morning job runs once, at the morning she declared -- early or late."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.c=companion(Path(self.temp.name),quiet_start='23:00',quiet_end='08:00',timezone='UTC')

    def at(self,h,m=0):return dt.datetime(2026,9,23,h,m,tzinfo=dt.timezone.utc)

    def test_undeclared_morning_is_just_after_quiet_hours(self):
        import companion_sleep as sleep
        self.assertEqual(sleep.wake_fingerprint(self.c,self.at(8,5)),'morning 2026-09-22\n')
        self.assertEqual(sleep.wake_fingerprint(self.c,self.at(8,10)),'morning 2026-09-23\n')

    def test_a_declared_lie_in_is_kept(self):
        import companion_sleep as sleep
        sleep.declare(self.c,'10:30',now=dt.datetime(2026,9,22,23,0,tzinfo=dt.timezone.utc))
        for h,m in ((8,10),(9,0),(10,15)):
            self.assertEqual(sleep.wake_fingerprint(self.c,self.at(h,m)),'morning 2026-09-22\n',(h,m))
        self.assertEqual(sleep.wake_fingerprint(self.c,self.at(10,30)),'morning 2026-09-23\n')

    def test_an_early_start_is_kept(self):
        import companion_sleep as sleep
        sleep.declare(self.c,'06:00',now=dt.datetime(2026,9,22,22,0,tzinfo=dt.timezone.utc))
        self.assertEqual(sleep.wake_fingerprint(self.c,self.at(6,0)),'morning 2026-09-23\n')

    def test_the_schedule_covers_the_window(self):
        import companion_render as render
        self.assertEqual(render.cron_window('08:00'),'*/15 5,6,7,8,9,10,11,12,13,14 * * *')
        self.assertEqual(render.cron_window('01:00'),'*/15 0,1,2,3,4,5,6,7,22,23 * * *')


class SingleSendPathTests(unittest.TestCase):
    def test_no_prompt_teaches_a_direct_send(self):
        for path in (ROOT/'kit/templates').rglob('*.tmpl'):
            with self.subTest(path=path.name):
                self.assertNotIn('{{OUTREACH_CMD}} send',path.read_text(encoding='utf-8'))
        import companion_render as render
        with tempfile.TemporaryDirectory() as tmp:
            c=companion(Path(tmp),outreach='free',outreach_per_day=3)
            policy=render.mapping_for(c)['OUTREACH_POLICY']
        self.assertIn('queueing on the outbox',policy);self.assertNotIn(' send ',policy)


class CheckinRaceTests(unittest.TestCase):
    def test_a_conversation_ending_mid_reflection_is_not_erased(self):
        import companion_checkin as checkin
        with tempfile.TemporaryDirectory() as tmp:
            c=companion(Path(tmp))
            checkin.flag(c)
            checkin.fingerprint(c)       # the tick that starts the reflection
            checkin.flag(c)              # another session ends while it runs
            self.assertEqual(checkin.clear(c)['pending'],1)
            checkin.fingerprint(c)
            self.assertEqual(checkin.clear(c)['pending'],0)


class KeepsakeTruthTests(unittest.TestCase):
    def test_an_unshared_keepsake_does_not_claim_to_be_shared(self):
        import companion_keepsake as keepsake, companion_outbox as outbox
        with tempfile.TemporaryDirectory() as tmp:
            c=companion(Path(tmp))
            src=Path(tmp)/'x.png';Image.new('RGB',(4,4),'red').save(src)
            out=keepsake.save(c,src,'A title','A note',share=True)   # images default to "ask"
            self.assertFalse(out['shared'])
            stored=json.loads((keepsake.folder_for(c)/f"{out['id']}.json").read_text())
            self.assertFalse(stored['shared']);self.assertIn('ask',stored['share_error'])
            self.assertEqual(outbox.waiting(c),[])
            with self.assertRaisesRegex(ValueError,'ask'):keepsake.share(c,out['id'])


class DispatchSlotTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.c=companion(Path(self.temp.name),quiet_start='00:00',quiet_end='00:00',outreach_per_day=1,
                         content_permissions={'image':'yes'})
        self.now=dt.datetime(2026,9,23,12,tzinfo=dt.timezone.utc)

    def test_a_dry_run_uses_no_slot(self):
        import companion_outbox as outbox, companion_dispatch as dispatch, companion_outreach as outreach
        outbox.queue(self.c,{'body':'hello'},self.now)
        self.assertEqual(dispatch.run(self.c,self.now,send=False)['handled'][0]['action'],'would-send')
        self.assertEqual(outreach.sent_today(self.c,self.now),0)

    def test_a_held_image_uses_no_slot(self):
        import companion_outbox as outbox, companion_dispatch as dispatch, companion_outreach as outreach
        img=Path(self.temp.name)/'p.png';Image.new('RGB',(4,4)).save(img)
        outbox.queue(self.c,{'kind':'image','body':'look','media_path':str(img)},self.now)
        with patch('companion_media_review.ensure_delivery',side_effect=ValueError('rated adult')), \
                patch.object(dispatch,'deliver') as deliver:
            out=dispatch.run(self.c,self.now)
        deliver.assert_not_called()
        self.assertEqual(out['handled'][0]['action'],'withhold')
        self.assertEqual(outreach.sent_today(self.c,self.now),0)
        self.assertEqual(outbox.fold(self.c)[0]['status'],'withheld')


class QueuedFingerprintTests(unittest.TestCase):
    def test_a_sent_message_moves_the_fingerprint(self):
        import companion_outbox as outbox, companion_preread as preread
        with tempfile.TemporaryDirectory() as tmp:
            c=companion(Path(tmp));now=dt.datetime(2026,9,23,12,tzinfo=dt.timezone.utc)
            entry=outbox.queue(c,{'body':'hello'},now)['entry']
            self.assertIn('queued 1',preread.fingerprint(c,now))
            outbox.mark(c,entry['id'],'sent','ok',now)
            self.assertIn('queued 0',preread.fingerprint(c,now))


class VaultMapPrivacyTests(unittest.TestCase):
    def test_a_profile_does_not_map_the_root_agents_life(self):
        import companion_vault_index as index
        with tempfile.TemporaryDirectory() as tmp:
            c=companion(Path(tmp))
            for rel in ('soul/SOUL.md','companion-life/PROTOCOL.md','knowledge/cooking.md',
                        'agents/other/soul/x.md','agents/test/soul/mine.md','people/alex/facts.md'):
                f=c.vault/rel;f.parent.mkdir(parents=True,exist_ok=True);f.write_text('# x\n')
            dirs={n['dir'] for n in index.scan(c)}
            self.assertIn('knowledge',dirs);self.assertIn('agents/test/soul',dirs)
            for hidden in ('soul','companion-life','agents/other/soul','people/alex'):
                self.assertNotIn(hidden,dirs)
            root=cc.Companion(agent='Root',vault=c.vault,hermes_root=Path(tmp)/'hermes',context_mode='fixed')
            self.assertIn('soul',{n['dir'] for n in index.scan(root)})


class ClosetReadOnlyTests(unittest.TestCase):
    def test_opening_the_closet_changes_nothing(self):
        import companion_lifestyle as lifestyle
        with tempfile.TemporaryDirectory() as tmp:
            c=companion(Path(tmp))
            from kit.app.server import build
            from fastapi.testclient import TestClient
            client=TestClient(build(c.home,token='t',state_dir=Path(tmp)/'state'))
            try:
                r=client.get('/api/closet',headers={'x-companion-token':'t'})
                self.assertEqual(r.status_code,200)
            finally:client.close()
            self.assertFalse(lifestyle.enabled(c))
            self.assertFalse((c.life/'wardrobe.json').exists())


class HookConsentTests(unittest.TestCase):
    """Repair under a different Python must not rewrite the hook and lose its consent."""
    def test_repair_keeps_a_working_hook_command(self):
        import yaml
        from kit.cli import scaffold
        from kit.cli.common import mapping
        with tempfile.TemporaryDirectory() as tmp:
            c=companion(Path(tmp))
            hook=c.home/'hooks/companion-context.py';end=c.home/'hooks/companion-session-end.py'
            existing=f'{sys.executable} {hook}';existing_end=f'{sys.executable} {end}'
            (c.home/'config.yaml').write_text(yaml.safe_dump({'hooks':{
                'pre_llm_call':[{'command':existing}],'on_session_end':[{'command':existing_end}]}}))
            report=[]
            with patch.object(scaffold.cp,'python_command',side_effect=lambda h:f'/nonexistent/python {h}'):
                scaffold.install_hook(c,mapping(c,{}),report)
            hooks=yaml.safe_load((c.home/'config.yaml').read_text())['hooks']
            self.assertEqual([e['command'] for e in hooks['pre_llm_call']],[existing])
            self.assertEqual([e['command'] for e in hooks['on_session_end']],[existing_end])
            self.assertIn('  hook: already registered; command unchanged',report)
            # An interpreter that no longer exists is replaced.
            (c.home/'config.yaml').write_text(yaml.safe_dump({'hooks':{'pre_llm_call':[{'command':f'/gone/python {hook}'}]}}))
            scaffold.install_hook(c,mapping(c,{}),[])
            hooks=yaml.safe_load((c.home/'config.yaml').read_text())['hooks']
            self.assertNotIn('/gone/python',hooks['pre_llm_call'][0]['command'])


class DeliveryTargetTests(unittest.TestCase):
    """A companion queued "target": "<its human's name>"; Hermes refused it at send time and the messages were lost."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.c=companion(Path(self.temp.name),quiet_start='00:00',quiet_end='00:00')
        self.now=dt.datetime(2026,9,23,12,tzinfo=dt.timezone.utc)

    def test_a_person_is_not_a_target(self):
        import companion_outbox as outbox
        with self.assertRaisesRegex(ValueError,'not a person'):
            outbox.queue(self.c,{'body':'hi','target':'alex'},self.now)
        self.assertEqual(outbox.queue(self.c,{'body':'hi'},self.now)['entry']['target'],'telegram')
        self.assertEqual(outbox.queue(self.c,{'body':'yo','target':'telegram:123'},self.now)['entry']['target'],'telegram:123')

    def test_a_bad_target_already_queued_is_withheld_without_a_slot(self):
        import companion_outbox as outbox, companion_dispatch as dispatch, companion_outreach as outreach
        import companion_self as slf
        slf._append(outbox.path_for(self.c),{'id':'m1','kind':'outbox','content':'text','body':'hi','media_path':'',
            'priority':'normal','reason':'','not_before':'','expires_at':(self.now+dt.timedelta(hours=2)).isoformat(),
            'target':'alex','status':'queued','queued_at':self.now.isoformat()})
        with patch.object(dispatch,'deliver') as deliver:
            out=dispatch.run(self.c,self.now)
        deliver.assert_not_called()
        self.assertEqual(out['handled'][0]['action'],'withhold')
        self.assertEqual(outreach.sent_today(self.c,self.now),0)

    def test_hermes_reason_is_kept(self):
        import subprocess, companion_dispatch as dispatch
        done=subprocess.CompletedProcess([],1,'{"error":"Unknown or unregistered plugin platform: x"}','')
        with patch.object(dispatch.subprocess,'run',return_value=done):
            ok,detail=dispatch.hermes_send(self.c,'hi','telegram')
        self.assertFalse(ok);self.assertIn('Unknown or unregistered plugin platform',detail)


class LevelEventTests(unittest.TestCase):
    """A change of level is announced once: big for a new high or a drop, small for a return."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.c=companion(Path(self.temp.name),boundary='girlfriend')

    def at(self,stage):
        import companion_intimacy as intimacy
        ladder=intimacy.stages_for(self.c)
        return {'stage':stage,'stage_name':ladder[stage]['name'],'stage_badge':ladder[stage]['badge'],
                'description':ladder[stage]['desc'],'romantic_progression':True}

    def test_the_sequence(self):
        import companion_intimacy as intimacy
        self.assertIsNone(intimacy.level_event(self.c,self.at(1)))          # baseline, silent
        self.assertIsNone(intimacy.level_event(self.c,self.at(1)))
        ev=intimacy.level_event(self.c,self.at(2))
        self.assertEqual((ev['kind'],ev['size']),('new_high','big'))
        self.assertEqual(ev['name'],'Chemistry')
        self.assertEqual(intimacy.level_event(self.c,self.at(2))['kind'],'new_high')  # until seen
        intimacy.acknowledge_level(self.c,2)
        self.assertIsNone(intimacy.level_event(self.c,self.at(2)))
        ev=intimacy.level_event(self.c,self.at(1))
        self.assertEqual((ev['kind'],ev['size'],ev['from_name']),('drop','big','Chemistry'))
        intimacy.acknowledge_level(self.c,1)
        self.assertEqual(intimacy.level_event(self.c,self.at(2))['size'],'small')
        intimacy.acknowledge_level(self.c,2)
        self.assertEqual(intimacy.level_event(self.c,self.at(3))['kind'],'new_high')


class BondedReserveTests(unittest.TestCase):
    def test_bonded_has_room_above_the_threshold(self):
        import companion_intimacy as intimacy
        for ladder in (intimacy.ROMANTIC_STAGES,intimacy.PLATONIC_STAGES):
            top=ladder[-1]
            self.assertEqual((top['name'],top['min_score'],top['max_score']),('Bonded',90,intimacy.SCORE_CEILING))
        self.assertEqual(intimacy.SCORE_CEILING,120)


class AdultImagesOnlyAtBondedTests(unittest.TestCase):
    def setUp(self):
        from kit.app.server import build
        from fastapi.testclient import TestClient
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.c=companion(Path(self.temp.name),boundary='girlfriend',explicit=True)
        self.client=TestClient(build(self.c.home,token='t',state_dir=Path(self.temp.name)/'state'))
        self.addCleanup(self.client.close)

    def post(self,data):return self.client.post('/api/settings',json=data,headers={'x-companion-token':'t'})

    def test_refused_and_hidden_before_bonded(self):
        import companion_intimacy as intimacy
        r=self.post({'adult_images':True})
        self.assertEqual(r.status_code,400);self.assertIn('Bonded',r.text)
        s=self.client.get('/api/settings',headers={'x-companion-token':'t'}).json()
        self.assertFalse(s['adult_images_available'])
        real=intimacy.compute
        with patch.object(intimacy,'compute',side_effect=lambda c,now=None:{**real(c,now),'can_intimate':True}):
            self.assertEqual(self.post({'adult_images':True}).status_code,200)
            self.assertTrue(self.client.get('/api/settings',headers={'x-companion-token':'t'}).json()['adult_images_available'])


if __name__=='__main__':unittest.main()
