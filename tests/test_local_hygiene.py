import datetime as dt,pathlib,tempfile,unittest,sys,os
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'kit/scripts'))
import companion_config as cc,companion_local_hygiene as h
class HygieneTests(unittest.TestCase):
 def test_archive_preserves_old_entry_and_prune_only_removes_expired_work(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=pathlib.Path(tmp);c=cc.Companion(hermes_root=root/'home',vault=root/'vault');c.home.mkdir();c.soul_dir.mkdir(parents=True)
   c.soul.write_text('A companion.\n'+h.slf.BEGIN+'\nI like books.\n'+h.slf.END);log=c.soul_dir/'Lifelog.md';log.write_text('# Lifelog\n\n## 2025-01-01\nOld entry.\n\n## 2026-09-12\nNew entry.\n')
   staging=c.life/'.inputs';staging.mkdir(parents=True);old=staging/'old.json';old.write_text('disposable');os.utime(old,(1,1));memory=c.life/'durable.jsonl';memory.write_text('retained')
   with patch.object(h.context,'build',return_value='context'):
    h.run(c,dt.datetime(2026,9,12,tzinfo=dt.timezone.utc),apply=True)
   self.assertIn('Old entry.',(c.soul_dir/'archive/Lifelog-2025-01.md').read_text());self.assertIn('New entry.',log.read_text());self.assertNotIn('Old entry.',log.read_text());self.assertFalse(old.exists());self.assertTrue(memory.exists())
 def test_undated_log_blocks_mutation(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=pathlib.Path(tmp);c=cc.Companion(hermes_root=root/'home',vault=root/'vault');c.soul_dir.mkdir(parents=True)
   p=c.soul_dir/'Lifelog.md';p.write_text('## Yesterday\nKeep me.\n')
   with self.assertRaisesRegex(ValueError,'Undated'):h.run(c,apply=True)
   self.assertEqual(p.read_text(),'## Yesterday\nKeep me.\n')
