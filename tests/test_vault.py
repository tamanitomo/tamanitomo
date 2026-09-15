"""The vault's history, and the way back from a bad edit.

The kit's promise is that nothing important is ever lost. Archives cover a file
growing too large; this covers a file being made worse.
"""
import datetime as dt
import pathlib,shutil,subprocess,sys,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'kit/scripts'))
import companion_config as cc
import companion_vault as vault

@unittest.skipUnless(shutil.which('git'),'git is not installed')
class VaultHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=pathlib.Path(self.tmp.name)
        self.c=cc.Companion(agent='Nova',human='Alex',hermes_root=root/'home',vault=root/'vault',
                            timezone='UTC')
        self.c.soul_dir.mkdir(parents=True,exist_ok=True)
        self.file=self.c.soul_dir/'SOUL.md'
        self.relative=str(self.file.relative_to(self.c.vault))

    def test_init_is_safe_to_run_twice_and_never_adds_a_remote(self):
        first=vault.init(self.c);second=vault.init(self.c)
        self.assertTrue(first['created']);self.assertFalse(second['created'])
        remotes=subprocess.run(['git','-C',str(self.c.vault),'remote'],capture_output=True,text=True)
        self.assertEqual(remotes.stdout.strip(),'')

    def test_a_quiet_period_produces_no_commit(self):
        vault.init(self.c)
        self.file.write_text('first')
        self.assertTrue(vault.commit(self.c)['committed'])
        self.assertEqual(vault.commit(self.c)['reason'],'nothing changed')

    def test_an_old_version_comes_back_beside_the_file_not_over_it(self):
        vault.init(self.c)
        self.file.write_text('the careful original')
        vault.commit(self.c)
        old=vault.history(self.c,self.relative)[0]['commit']
        self.file.write_text('a consolidation that went too far')
        vault.commit(self.c)
        result=vault.restore(self.c,self.relative,old)
        self.assertEqual(self.file.read_text(),'a consolidation that went too far')
        self.assertEqual(pathlib.Path(result['restored']).read_text(),'the careful original')
        self.assertIn('not over it',result['note'])

    def test_history_lists_every_version_newest_first(self):
        vault.init(self.c)
        for text in ('one','two','three'):
            self.file.write_text(text);vault.commit(self.c)
        versions=vault.history(self.c,self.relative)
        self.assertEqual(len(versions),3)
        self.assertEqual(vault.show(self.c,self.relative,versions[0]['commit']),'three')
        self.assertEqual(vault.show(self.c,self.relative,versions[-1]['commit']),'one')

    def test_a_path_with_no_history_says_so_rather_than_guessing(self):
        vault.init(self.c)
        with self.assertRaises(ValueError):
            vault.show(self.c,self.relative,'0000000000000000000000000000000000000000')
        self.assertEqual(vault.history(self.c,'nothing/here.md'),[])


if __name__=='__main__':unittest.main()
