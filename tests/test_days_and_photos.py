"""Varied days, laundry when it is due, photos that actually get offered, commands that run."""
import datetime as dt, json, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'kit/scripts')]
import companion_config as cc


def companion(tmp,**kw):
    c=cc.Companion(agent='Mira',human='Alex',profile='m',vault=Path(tmp)/'v',hermes_root=Path(tmp)/'h',
                   timezone='UTC',context_mode='fixed',**kw)
    c.home.mkdir(parents=True);c.life.mkdir(parents=True);c.soul_dir.mkdir(parents=True);c.save()
    return c


class DaysTests(unittest.TestCase):
    def test_every_run_gets_fresh_ideas_and_how_to_mark_one_taken(self):
        import companion_preread as pr
        with tempfile.TemporaryDirectory() as tmp:
            c=companion(tmp);now=dt.datetime(2026,9,23,9,tzinfo=dt.timezone.utc)
            text=pr.day_ideas(c,now)
            self.assertIn('Ideas for today',text);self.assertIn('chose --idea',text)
            self.assertGreaterEqual(text.count('\n- '),3)

    def test_laundry_is_due_only_when_clean_clothes_run_low(self):
        import companion_lifestyle as ls
        closet=[{'id':f'top{i}','category':'day','covers':'top'} for i in range(3)]+\
               [{'id':f'bot{i}','category':'day','covers':'bottom'} for i in range(3)]+\
               [{'id':f'u{i}','category':'underwear'} for i in range(3)]+\
               [{'id':f'pj{i}','category':'sleep'} for i in range(3)]
        self.assertIn('not due',ls.laundry_status({'clothes':{}},closet))
        dirty={'clothes':{'u0':'dirty','u1':'dirty'}}
        self.assertIn('LAUNDRY DUE: running low on clean underwear',ls.laundry_status(dirty,closet))

    def test_no_default_day_schedules_laundry(self):
        import companion_lifestyle as ls
        for kind in ('companion','colleague','worker'):
            c=cc.Companion(agent_type=kind)
            self.assertFalse(any('hamper' in a['activity'] for a in ls.default_daily_routine(c)),kind)


class PhotoShareTests(unittest.TestCase):
    def test_a_saved_photo_is_offered_within_the_daily_allowance(self):
        import companion_timeline as tl, companion_outbox as outbox
        with tempfile.TemporaryDirectory() as tmp:
            c=companion(tmp,content_permissions={'image':'yes'},outreach='free',outreach_per_day=5)
            now=dt.datetime(2026,9,23,12,tzinfo=dt.timezone.utc)
            row={'variants':[{'rating':'safe'}]}
            self.assertEqual(tl.share_opportunity(c,row,now),{'ok':True,'left_today':2})
            img=Path(tmp)/'a.png';img.write_bytes(b'x')
            for i in range(2):outbox.queue(c,{'kind':'image','body':f'look {i}','media_path':str(img)},now)
            self.assertFalse(tl.share_opportunity(c,row,now)['ok'])
            self.assertFalse(tl.share_opportunity(companion(tmp+'/2',content_permissions={'image':'ask'}),row,now)['ok'])
            with patch('companion_media.adult_ready',return_value=(False,['no'])):
                self.assertIn('adult',tl.share_opportunity(companion(tmp+'/3',content_permissions={'image':'yes'}),
                                                           {'variants':[{'rating':'nsfw'}]},now)['why'])

    def test_the_photo_job_offers_the_share(self):
        text=(ROOT/'kit/templates/cron/timeline.md.tmpl').read_text()
        self.assertIn('share --id <capture_id>',text);self.assertIn('share.ok',text)


class CommandPythonTests(unittest.TestCase):
    def test_commands_use_the_apps_own_python_when_it_has_one(self):
        import companion_platform as cp
        venv=ROOT/'.venv/bin/python'
        if venv.is_file():self.assertEqual(cp.kit_python(),str(venv))
        self.assertIn(cp.kit_python(),cp.terminal_python_command('x.py'))


if __name__=='__main__':unittest.main()
