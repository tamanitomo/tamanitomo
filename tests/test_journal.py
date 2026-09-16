import pathlib,sys,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'kit/scripts'))
import companion_config as cc,companion_journal as journal
class JournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=pathlib.Path(self.tmp.name)
        self.c=cc.Companion(agent='Nova',human='Alex',hermes_root=root/'home',vault=root/'vault')
    def test_append_preserves_history_and_retries_without_duplicates(self):
        path=journal.path_for(self.c,'daily');path.parent.mkdir(parents=True)
        path.write_text('## 2026-09-10\nAn older entry.\n')
        data={'date':'2026-09-11','text':"Today's thought has an apostrophe and $HOME."}
        self.assertTrue(journal.append(self.c,'daily',data)['written'])
        self.assertFalse(journal.append(self.c,'daily',data)['written'])
        self.assertIn('An older entry.',path.read_text())
        self.assertEqual(path.read_text().count('## 2026-09-11'),1)
        with self.assertRaises(ValueError):journal.append(self.c,'daily',{**data,'text':'different'})
    def test_legacy_dated_entries_are_not_duplicated(self):
        path=journal.path_for(self.c,'daily');path.parent.mkdir(parents=True)
        original='## 2026-09-11\nWritten before this helper existed.\n';path.write_text(original)
        self.assertFalse(journal.append(self.c,'daily',{'date':'2026-09-11','text':'New draft'})['written'])
        self.assertEqual(path.read_text(),original)
    def test_empty_stub_is_filled_but_a_real_entry_is_never_overwritten(self):
        # A run can leave an empty marker pair behind by raising after the journal step
        # was committed: without this, every later run for that date is refused forever.
        path=journal.path_for(self.c,'daily');path.parent.mkdir(parents=True)
        path.write_text('## 2026-09-11\n<!-- companion-journal:daily-2026-09-11 -->\n<!-- /companion-journal:daily-2026-09-11 -->\n')
        first=journal.append(self.c,'daily',{'date':'2026-09-11','text':'The real entry.'})
        self.assertTrue(first['written']);self.assertEqual(first.get('replaced'),'empty stub')
        self.assertIn('The real entry.',path.read_text())
        # A second, different draft must not overwrite text that has actually landed.
        with self.assertRaises(ValueError):journal.append(self.c,'daily',{'date':'2026-09-11','text':'A rewrite.'})
        self.assertIn('The real entry.',path.read_text())
        # An empty body that is not a clean stub is refused rather than silently repaired.
        path.write_text('## 2026-09-12\n<!-- companion-journal:daily-2026-09-12 -->\n   \n<!-- /companion-journal:daily-2026-09-12 -->\n')
        with self.assertRaises(ValueError):journal.append(self.c,'daily',{'date':'2026-09-12','text':'Body.'})
    def test_tail_discloses_omissions_and_invalid_targets_are_refused(self):
        journal.append(self.c,'autonomy',{'date':'2026-09-11','id':'run-1','text':'x'*1000})
        got=journal.tail(self.c,'autonomy',500)
        self.assertEqual(len(got['text']),500);self.assertGreater(got['omitted_chars'],0)
        with self.assertRaises(ValueError):journal.path_for(self.c,'../../SOUL.md')
        with self.assertRaises(ValueError):journal.append(self.c,'autonomy',{'date':'2026-09-11','text':'Missing id'})
