"""Who keeps each part of the soul, and when she may change it."""
import datetime as dt, json, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'kit/scripts')]
import companion_config as cc, companion_render as cr, companion_soul as soul


class KeeperTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        self.c=cc.Companion(agent='Mira',human='Alex',profile='m',vault=root/'v',hermes_root=root/'h',
                            pronoun_set='she',human_pronoun_set='he',boundary='girlfriend',
                            relationship_started='2026-06-01',context_mode='fixed')
        self.c.home.mkdir(parents=True);self.c.soul_dir.mkdir(parents=True);self.c.save()
        text=cr.render_template('SOUL.md.tmpl',cr.mapping_for(self.c,'warm','none'))
        Path(self.c.soul).resolve().parent.mkdir(parents=True,exist_ok=True)
        Path(self.c.soul).write_text(text,encoding='utf-8')
        self.now=dt.datetime(2026,9,23,12,tzinfo=dt.timezone.utc)

    def at(self,stage):return patch.object(soul,'stage_reached',return_value=stage)

    def test_her_reach_grows_with_the_relationship(self):
        with self.at(0):
            self.assertTrue(soul.access(self.c,'daily-life',self.now)['can'])
            self.assertIn('opens at',soul.access(self.c,'voice',self.now)['why'])
            self.assertIn('opens at',soul.access(self.c,'about-you',self.now)['why'])
        with self.at(4):
            for key in ('voice','heart','support','core','about-you','for-us'):
                self.assertTrue(soul.access(self.c,key,self.now)['can'],key)

    def test_anchors_are_never_hers_and_appearance_only_when_unlocked(self):
        with self.at(4):
            for key in ('relationship','closeness','hard-lines','being-herself','appearance'):
                self.assertFalse(soul.access(self.c,key,self.now)['can'],key)
            soul.set_lock(self.c,'appearance',False)
            self.assertTrue(soul.access(self.c,'appearance',self.now)['can'])
        with self.assertRaises(ValueError):soul.set_lock(self.c,'hard-lines',False)

    def test_a_locked_shared_section_is_closed_to_her(self):
        with self.at(4):
            soul.set_lock(self.c,'heart',True)
            self.assertIn('locked',soul.access(self.c,'heart',self.now)['why'])
            with self.assertRaises(ValueError):soul.write(self.c,'heart','x','set','why',self.now)

    def test_a_write_is_logged_backed_up_and_cooled_down(self):
        with self.at(1):
            soul.write(self.c,'voice','She texts in bursts now.','set','I noticed I stopped writing essays.',self.now)
            body=Path(self.c.soul).read_text()
            self.assertIn('She texts in bursts now.',body)
            self.assertIn('## How Mira talks',body)         # heading kept
            self.assertEqual(soul.changes(self.c)[-1]['section'],'voice')
            self.assertIn('next change after',soul.access(self.c,'voice',self.now+dt.timedelta(days=3))['why'])
            self.assertTrue(soul.access(self.c,'voice',self.now+dt.timedelta(days=15))['can'])
        with self.assertRaisesRegex(ValueError,'say why'):
            with self.at(4):soul.write(self.c,'heart','x','set','',self.now)

    def test_private_notes_stay_out_of_soul_and_reach_only_the_prompt(self):
        with self.at(1):
            soul.write(self.c,'about-you','He is kinder than he lets on.','set','first real impression',self.now)
        self.assertNotIn('kinder than he lets on',Path(self.c.soul).read_text())
        self.assertTrue(soul.private_path(self.c).name.startswith('.'))
        self.assertIn('kinder than he lets on',soul.render_private(self.c))

    def test_own_words_go_through_the_self_authored_block(self):
        with self.at(0):
            soul.write(self.c,'own-words','I like rain on a tin roof.','append','it is true',self.now)
        self.assertIn('I like rain on a tin roof.',Path(self.c.soul).read_text())

    def test_the_new_soul_has_every_keeper_section_and_no_machinery(self):
        text=Path(self.c.soul).read_text()
        import companion_identity as ident
        self.assertEqual(set(ident.sections(text)),set(soul.SECTIONS))
        for word in ('shared fiction','imagined','premise','PRESENCE.md','companion_presence','Operational'):
            self.assertNotIn(word,text)


class IdentityPageTests(KeeperTests):
    def client(self):
        from kit.app.server import build
        from fastapi.testclient import TestClient
        c=TestClient(build(self.c.home,token='t',state_dir=Path(self.temp.name)/'state'));self.addCleanup(c.close)
        return c

    def test_the_page_shows_keepers_and_hides_private_notes(self):
        with self.at(1):soul.write(self.c,'about-you','He hums when he is nervous.','set','noticed it twice',self.now)
        client=self.client();h={'x-companion-token':'t'}
        d=client.get('/api/identity',headers=h).json()
        by={s['name']:s for s in d['sections']}
        self.assertEqual(by['heart']['keeper'],'shared');self.assertTrue(by['heart']['lockable'])
        self.assertEqual(by['own-words']['keeper'],'hers');self.assertFalse(by['own-words']['lockable'])
        self.assertNotIn('hums when he is nervous',client.get('/api/identity',headers=h).text)
        self.assertTrue(next(n for n in d['private'] if n['id']=='about-you')['written'])

    def test_locks_and_protected_sections(self):
        client=self.client();h={'x-companion-token':'t'}
        self.assertEqual(client.post('/api/identity-lock',json={'section':'heart','locked':True},headers=h).status_code,200)
        self.assertTrue(soul.locked(self.c,'heart'))
        self.assertEqual(client.post('/api/identity-lock',json={'section':'hard-lines','locked':False},headers=h).status_code,400)
        self.assertEqual(client.post('/api/identity/own-words',json={'body':'x'},headers=h).status_code,403)
        self.assertEqual(client.post('/api/identity/being-herself',json={'body':'x'},headers=h).status_code,403)
        self.assertEqual(client.post('/api/identity/heart',json={'body':'## Heart and temper\n\nWarm.'},headers=h).status_code,200)


if __name__=='__main__':unittest.main()
