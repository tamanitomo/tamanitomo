"""Regressions for the fresh-eyes audit, using disposable profiles only."""
import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests import test_workspace as workspace
import companion_config as cc
from kit.app.runtime import Runtime


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.fixture = workspace.WorkspaceTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_new_companions_stagger_without_moving_existing_schedules(self):
        from kit.cli.common import next_schedule_offset, load_manifest
        f=self.fixture
        fresh=cc.Companion(profile='new',hermes_root=f.root,vault=f.vault)
        self.assertEqual(next_schedule_offset(fresh),1)
        fresh.schedule_offset_minutes=next_schedule_offset(fresh)
        fresh.home.mkdir();fresh.save()
        self.assertEqual(next_schedule_offset(fresh),1)
        another=dataclasses.replace(fresh,profile='another')
        self.assertEqual(next_schedule_offset(another),2)
        base={s['key']:s['expr'] for s in load_manifest(f.c)['jobs']}
        offset={s['key']:s['expr'] for s in load_manifest(fresh)['jobs']}
        self.assertNotEqual(base['pulse'],offset['pulse'])
        self.assertEqual(base['window'],offset['window'])
        self.assertEqual(base['wake'],offset['wake'])
        self.assertEqual(cc.load(f.c.home).schedule_offset_minutes,0)

    def test_image_frequency_round_trips_and_rejects_invalid_intervals(self):
        f=self.fixture
        for minutes in (5,30,120,1440):
            response=f.post('/api/settings',{'image_interval_minutes':minutes})
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(f.get('/api/settings').json()['image_interval_minutes'],minutes)
        for value in (0,7,-15,True,15.5,'30'):
            self.assertEqual(f.post('/api/settings',{'image_interval_minutes':value}).status_code,400)
        self.assertEqual(cc.load(f.c.home).image_interval_minutes,1440)

    def test_image_frequency_sync_keeps_custom_cron_schedules(self):
        f=self.fixture
        c=cc.load(f.c.home);c.image_timeline=True;c.image_style='realistic';c.save()
        path=c.home/'cron/jobs.json';path.parent.mkdir(exist_ok=True)
        for original,expected in (('3-59/15 * * * *','3 */2 * * *'),('17 9 * * *',None)):
            c.image_interval_minutes=15;c.save()
            path.write_text(json.dumps({'jobs':[{'id':'photo','name':'Nova image timeline','schedule':{'expr':original}}]}))
            calls=[]
            def run(runtime,args,**kwargs):
                calls.append(args);return SimpleNamespace(returncode=0,stdout='ok',stderr='')
            with patch.object(Runtime,'run',run):
                result=f.post('/api/settings',{'image_interval_minutes':120}).json()
                row=f.wait(SimpleNamespace(status_code=200,text='',json=lambda:result['operation']))
            self.assertEqual(row['status'],'complete',row)
            edits=[args[-1] for args in calls if args[:2]==['cron','edit']]
            self.assertEqual(edits,[expected] if expected else [])

    def test_non_romantic_connections_do_not_offer_romantic_progress(self):
        import companion_intimacy
        f=self.fixture
        for kind,boundary,expected in (('companion','best-friend',False),('companion','girlfriend',True),('colleague','creative-partner',False),('worker','creative-partner',False)):
            with self.subTest(kind=kind,boundary=boundary):
                c=dataclasses.replace(f.c,agent_type=kind,boundary=boundary)
                self.assertEqual(companion_intimacy.compute(c)['romantic_progression'],expected)

    def test_job_usage_counts_continuations_and_isolates_profiles(self):
        import sqlite3
        from kit.app.runtime import job_usage
        f=self.fixture;now=1800000000
        con=sqlite3.connect(f.c.home/'state.db')
        con.execute('CREATE TABLE sessions(id TEXT, source TEXT, started_at REAL, profile_name TEXT, parent_session_id TEXT, input_tokens INTEGER, output_tokens INTEGER)')
        con.executemany('INSERT INTO sessions VALUES(?,?,?,?,?,?,?)',[
            ('cron_pulse_20270115_000000','cron',now-100,'nova',None,100,20),
            ('continuation','cron',now-90,'nova','cron_pulse_20270115_000000',50,10),
            ('cron_pulse_20270114_000000','cron',now-4000,'nova',None,300,40),
            ('cron_pulse_20270115_010000','cron',now-50,'rowan',None,9999,9999),
            ('chat','cli',now-20,'nova',None,8888,8888)])
        con.commit();con.close()
        report=job_usage(f.c,[{'id':'pulse'},{'id':'unrun'}],now)
        self.assertTrue(report['available'])
        self.assertEqual(report['jobs']['pulse'],{'runs':2,'last_run':180,'hour':180,'day':520,'week':520})
        self.assertIsNone(report['jobs']['unrun']['last_run'])
        self.assertIsNone(report['jobs']['unrun']['day'])
        self.assertFalse(job_usage(f.other,[{'id':'pulse'}],now)['available'])

    def test_link_existing_hermes_config_file_persists_without_changing_it(self):
        f=self.fixture
        existing=Path(f.tmp.name)/'separate hermes';existing.mkdir()
        config=existing/'config.yaml';config.write_text('model: preserved\n')
        result=f.post('/api/installations/link',{'path':str(config)})
        self.assertEqual(result.status_code,200,result.text)
        ident=result.json()['installation']
        self.assertEqual(f.app.state.runtimes[ident].root,existing)
        self.assertEqual(config.read_text(),'model: preserved\n')
        self.assertEqual(f.post('/api/installations/link',{'path':str(existing)}).json()['installation'],ident)
        self.assertEqual(f.post('/api/installations/link',{'path':str(existing/'missing')}).status_code,400)

    def test_schedule_approval_requires_a_successful_model_check(self):
        f=self.fixture
        for approved,reply,expected in ((False,'CONNECTION_OK',False),(True,'Provider unavailable',False),(True,'CONNECTION_OK',True)):
            calls=[]
            def run(runtime,args,**kwargs):
                calls.append(args)
                return SimpleNamespace(stdout=reply if args[0]=='chat' else 'saved',stderr='',returncode=0)
            with self.subTest(approved=approved,reply=reply),patch.object(Runtime,'run',run):
                response=f.post('/api/profiles',{'profile':'test-profile','answers':{'agent':'Test','boundary':'best-friend'},'schedule_approved':approved})
                result=f.wait(response)
                self.assertEqual(result['status'],'complete',result)
                self.assertEqual(result['result']['schedule_active'],expected)
                self.assertEqual(any('active' in args for args in calls),expected)
                self.assertEqual(any(args[0]=='chat' for args in calls),approved)

    def test_page_versions_its_assets_to_avoid_mixed_cached_controllers(self):
        response = self.fixture.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertRegex(response.text, r'/static/editing\.js\?v=[a-f0-9]{16}')
        self.assertRegex(response.text, r'/static/product\.js\?v=[a-f0-9]{16}')
        self.assertEqual(response.headers['cache-control'], 'no-cache')

    def test_operation_result_is_only_available_to_its_originating_profile(self):
        f = self.fixture
        response = f.post('/api/profile/display-name', {'name': 'Nova workspace'})
        row = f.wait(response)
        self.assertEqual(row['profile'], 'nova')
        self.assertEqual(f.get('/api/operations/' + row['id'], 'rowan').status_code, 404)
        self.assertEqual(f.get('/api/operations/' + row['id']).status_code, 200)

    def test_sharing_preserves_facts_in_both_directions_and_leaves_relationship_alone(self):
        f = self.fixture
        private = f.c.human_dir
        private.mkdir(parents=True, exist_ok=True)
        fact = {'id': 'known', 'kind': 'human_fact', 'category': 'preference',
                'statement': 'Likes tea', 'evidence': 'I like tea', 'source': 'chat',
                'confidence': 'stated', 'status': 'active', 'recorded_at': '2026-09-12T12:00:00+00:00'}
        (private / 'facts.jsonl').write_text(json.dumps(fact) + '\n')
        relationship = f.c.life / 'relationship.jsonl'
        relationship.write_text('relationship stays local\n')
        for shared in (True, False):
            response = f.post('/api/settings', {'share_people': shared})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(len(f.get('/api/ledgers').json()['facts']), 1)
            self.assertTrue((cc.load(f.c.home).human_dir / 'facts.jsonl').is_file())
            self.assertEqual(relationship.read_text(), 'relationship stays local\n')
        self.assertTrue((private / 'facts.jsonl').is_file())

    def test_sharing_conflict_preserves_configuration_and_both_ledgers(self):
        f = self.fixture
        private = f.c.human_dir
        shared = dataclasses.replace(f.c, share_people=True).human_dir
        for folder, text in ((private, 'private facts'), (shared, 'different shared facts')):
            folder.mkdir(parents=True, exist_ok=True)
            (folder / 'facts.jsonl').write_text(text)
        before = (f.c.home / cc.CONFIG_NAME).read_bytes()
        response = f.post('/api/settings', {'share_people': True})
        self.assertEqual(response.status_code, 400)
        self.assertEqual((f.c.home / cc.CONFIG_NAME).read_bytes(), before)
        self.assertEqual((private / 'facts.jsonl').read_text(), 'private facts')
        self.assertEqual((shared / 'facts.jsonl').read_text(), 'different shared facts')

    def test_both_editors_reject_photo_sessions_without_style(self):
        f = self.fixture
        before = (f.c.home / cc.CONFIG_NAME).read_bytes()
        payload = f.get('/api/profile/editor').json()
        payload['config'].update(image_timeline=True, image_style='none')
        self.assertEqual(f.post('/api/profile/editor', payload).status_code, 400)
        self.assertEqual(f.post('/api/settings', {'image_timeline': True, 'image_style': 'none'}).status_code, 400)
        self.assertEqual((f.c.home / cc.CONFIG_NAME).read_bytes(), before)

    def test_both_editors_synchronize_and_report_failed_job_updates(self):
        f = self.fixture
        cron = f.c.home / 'cron'
        cron.mkdir(exist_ok=True)
        (cron / 'jobs.json').write_text('{"jobs": []}')
        for route, hour in (('/api/settings', '22:00'), ('/api/profile/editor', '21:00')):
            with self.subTest(route=route):
                payload = {'quiet_start': hour}
                if route.endswith('editor'):
                    payload = f.get('/api/profile/editor').json()
                    payload['config']['quiet_start'] = hour
                with patch.object(Runtime, 'run', return_value=SimpleNamespace(returncode=1, stdout='', stderr='offline')):
                    response = f.post(route, payload)
                    self.assertEqual(response.status_code, 200, response.text)
                    operation = response.json()['operation']
                    row = f.wait(SimpleNamespace(status_code=200, text='', json=lambda: operation))
                self.assertEqual(row['status'], 'failed')
                self.assertIn('Preferences were saved', row['error'])
                self.assertEqual(cc.load(f.c.home).quiet_start, hour)

    def test_browser_regressions(self):
        import shutil
        import subprocess
        node = shutil.which('node')
        if not node:
            self.skipTest('Node is needed for browser state regression tests')
        subprocess.run([node, str(Path(__file__).with_name('test_reliability_ui.js'))], check=True)

    def test_content_and_feed_regressions(self):
        """Photo filters, message formatting, and the guard that keeps a slow
        reply to an abandoned page from repainting the feed."""
        import shutil
        import subprocess
        node = shutil.which('node')
        if not node:
            self.skipTest('Node is needed for the content and feed regressions')
        subprocess.run([node, str(Path(__file__).with_name('test_content_ui.js'))], check=True)

    def test_model_licence_notice(self):
        """Weights carry their publisher's terms, which are independent of this
        project's licence. The downloader has to show them before fetching."""
        import shutil
        import subprocess
        node = shutil.which('node')
        if not node:
            self.skipTest('Node is needed for the model licence regression')
        subprocess.run([node, str(Path(__file__).with_name('test_licence_ui.js'))], check=True)

    def test_creation_interview_stays_inside_the_catalogs(self):
        """The browser interview proposes a persona, a relationship frame and a
        set of answers on its own. Every one of them has to be something the
        backend will actually accept."""
        import shutil
        import subprocess
        node = shutil.which('node')
        if not node:
            self.skipTest('Node is needed for the creation interview regression')
        import companion_catalog as catalog
        from kit.cli.questions import known_answer_keys
        subprocess.run([node, str(Path(__file__).with_name('test_onboarding_ui.js')),
                        ','.join(catalog.BOUNDARIES), ','.join(sorted(known_answer_keys()))],
                       check=True)


class NoticeStripAndRetryLayoutTests(unittest.TestCase):
    """Layout faults that only show up on a real screen, pinned as source facts.

    `.notice-strip` is a flex ROW. That suits a one-line strip with a button on the
    end, and ruins any panel that puts a heading, a paragraph, release notes and an
    action bar inside one -- each block becomes its own crushed column, and the
    update notice read one word per line down a sliver on the left.
    """

    def source(self, name):
        return (Path(__file__).resolve().parents[1] / "kit/app/static" / name).read_text(encoding="utf-8")

    def test_multi_block_notices_opt_out_of_the_flex_row(self):
        css = self.source('product.css')
        self.assertIn('.notice-strip.notice-stack', css)
        self.assertIn('flex-direction:column', css.split('.notice-strip.notice-stack')[1][:200])
        settings = self.source('settings.js')
        # Both branches of the Updates panel hold block content.
        self.assertEqual(settings.count('notice-strip notice-stack'), 2)

    def test_the_provider_radio_cannot_stretch(self):
        """A bare radio in a flex row is a flex item like any other, so it grew and
        squeezed the provider name beside it into nothing."""
        css = self.source('product.css')
        rule = css.split('.provider-preset-option input[type=radio]')[1][:120]
        self.assertIn('flex:0 0 auto', rule)
        self.assertIn('.provider-preset-detail', css)
        self.assertIn('min-width:0', css.split('.provider-preset-detail')[1][:160])

    def test_generating_a_variant_does_not_hold_the_page(self):
        """The dialog used to await the render, so a slow provider pinned the user
        to a modal and a failed one reported only inside it.

        It also has to go through the operation queue rather than a plain request,
        or pressing Generate reports nothing at all until the picture exists --
        which is what it did, for as long as a render takes.
        """
        js = self.source('product.js')
        handler = js.split("$('retry-modal-submit').onclick=")[1].split('\n  };')[0]
        self.assertNotIn('await post(', handler, 'the render is awaited behind the modal again')
        close_at = handler.index("$('product-dialog').close()")
        submit_at = handler.index('action(`/timeline/')
        self.assertLess(close_at, submit_at, 'the dialog must close before the request starts')
        self.assertNotIn('post(`/timeline/', handler, 'the render bypasses the operation queue again')
        self.assertIn('.catch(', handler, 'a failed render has to reach the toast')


class DeletingAVariantReachesTheRightFileTests(unittest.TestCase):
    """Switching variants repoints the viewer at a different picture.

    The delete that followed sent the new path with the previous picture's etag, so
    the server refused it as a conflict every single time -- which is why deleting
    a variant appeared to do nothing at all, and left nothing behind to show for it.
    """

    def source(self, name):
        return (Path(__file__).resolve().parents[1] / "kit/app/static" / name).read_text(encoding="utf-8")

    def test_the_viewer_moves_the_etag_with_the_path(self):
        js = self.source('product.js')
        handler = js.split("for(const btn of variantsBar.querySelectorAll('[data-variant-fn]')){")[1][:700]
        self.assertIn('item.path=', handler)
        self.assertIn('item.etag=', handler, 'the path moved but the etag did not')

    def test_the_server_gives_every_variant_its_own_etag(self):
        content = (Path(__file__).resolve().parents[1] / 'kit/app/content.py').read_text(encoding='utf-8')
        self.assertIn('def with_etags', content)
        self.assertIn('variants=with_etags(', content)

    def test_a_deleted_timeline_image_is_taken_out_of_its_capture(self):
        content = (Path(__file__).resolve().parents[1] / 'kit/app/content.py').read_text(encoding='utf-8')
        self.assertIn('forget_timeline_image', content)
        # The capture id is not the image stem; that assumption was the whole bug.
        self.assertNotIn("(p.stem+'.json')", content)


class PromptsAreFiledUnderTheirOwnNamesTests(unittest.TestCase):
    """Each compiled prompt was filed under the other one's name.

    `prompt` is the comma-joined tag bag a diffusion model wants; the labelled
    section text is the structured one. They were stored as 'structured' and
    'prose' respectively -- each under the other's label -- so the viewer showed
    the identity-led tag bag as the prose prompt and the sectioned text as the
    structured one, with the headings plainly visible under the wrong title.
    """

    def test_compile_files_the_section_text_as_structured(self):
        media = (Path(__file__).resolve().parents[1] / 'kit/scripts/companion_media.py').read_text(encoding='utf-8')
        self.assertIn("'prompts':{'structured':structured,'tags':prompt}", media)
        self.assertNotIn("'prose':structured", media, 'the section text is filed as prose again')
        self.assertIn("active_type='tags' if p['provider']=='comfyui' else 'structured'", media)

    def test_the_viewer_translates_records_written_under_the_old_names(self):
        js = (Path(__file__).resolve().parents[1] / 'kit/app/static/product.js').read_text(encoding='utf-8')
        self.assertIn('function normalisePrompts', js)
        fn = js.split('function normalisePrompts')[1].split('function populateViewerInfo')[0]
        # Both old names moved; translating only one leaves the other pointing at
        # the prompt it no longer names.
        self.assertIn("p.prose!==undefined", fn)
        self.assertIn("'tags'", fn)

    def test_both_prompts_stay_visible_side_by_side(self):
        """Seeing what each workflow was actually given, next to the other, is the
        point of showing them at all; only the sent one is marked as sent."""
        js = (Path(__file__).resolve().parents[1] / 'kit/app/static/product.js').read_text(encoding='utf-8')
        block = js.split("let promptsHtml='';")[1].split("$('viewer-info-body')")[0]
        self.assertIn("box('structured')", block)
        self.assertIn("box('tags')", block)
        self.assertIn('Sent to', block)
        self.assertIn('Compiled, not sent', block)


class OneCompanionsPicturesStayTheirOwnTests(unittest.TestCase):
    """A capture id was derived from the clock alone.

    Two companions capturing in the same quarter hour therefore produced files with
    the same name, and the variant thumbnail was the one media URL built without the
    companion attached — so it fell back to the default profile and showed whoever
    happened to hold that filename, or nothing at all.
    """

    def test_the_capture_id_is_scoped_to_the_companion(self):
        import companion_timeline as timeline
        src = (Path(__file__).resolve().parents[1] / 'kit/scripts/companion_timeline.py').read_text(encoding='utf-8')
        self.assertIn("c.profile+'\\0'+slot.isoformat()", src)
        self.assertNotIn("hashlib.sha256(slot.isoformat().encode())", src)

    def test_every_rendered_media_url_carries_the_companion(self):
        js = (Path(__file__).resolve().parents[1] / 'kit/app/static/product.js').read_text(encoding='utf-8')
        import re
        # `item.url` is stored and later passed through mediaUrl; what matters is that
        # nothing is put into an src= attribute without it.
        for line in js.splitlines():
            if 'src="${' in line or "src='${" in line:
                with self.subTest(line=line.strip()[:70]):
                    self.assertNotIn('/media/timeline/${', line,
                                     'a media URL is rendered without the companion attached')

    def test_a_seed_asked_for_is_the_seed_used(self):
        media = (Path(__file__).resolve().parents[1] / 'kit/scripts/companion_media.py').read_text(encoding='utf-8')
        self.assertIn("overrides.get('seed'", media)
