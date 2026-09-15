"""Standing instructions and the relationship record.

Between them these are most of what makes a companion feel like it has been
there rather than been briefed: the rules you gave it once, and the things that
have actually happened between you.
"""
import datetime as dt
import json
import pathlib,sys,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'kit/scripts'))
import companion_config as cc
import companion_notes as notes
import companion_context as ctx

TZ=dt.timezone.utc

class Base(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=pathlib.Path(self.tmp.name)
        self.c=cc.Companion(agent='Nova',human='Alex',hermes_root=root/'home',vault=root/'vault',
                            timezone='UTC')
        self.c.soul_dir.mkdir(parents=True,exist_ok=True)
        (self.c.soul_dir/'ActiveContext.md').write_text('## Right now\nAt the desk.\n')
        self.now=dt.datetime(2026,9,10,12,0,tzinfo=TZ)


class StandingTests(Base):
    def test_a_rule_needs_evidence_like_a_fact_does(self):
        with self.assertRaisesRegex(ValueError,'evidence'):
            notes.add_standing(self.c,{'instruction':'never call me at work'},self.now)

    def test_a_retired_rule_stops_applying_but_stays_on_the_record(self):
        made=notes.add_standing(self.c,{'instruction':"don't write my homework for me",
                                        'evidence':'he said so on 2026-08-01'},self.now)
        ident=made['entry']['id']
        self.assertEqual(len(notes.standing(self.c)),1)
        notes.retire_standing(self.c,ident,'he changed his mind',self.now)
        self.assertEqual(notes.standing(self.c),[])
        self.assertEqual(notes.standing(self.c,'retired')[0]['id'],ident)
        self.assertIn('homework',notes.standing_path(self.c).read_text())

    def test_rules_are_injected_as_rules_not_as_preferences(self):
        notes.add_standing(self.c,{'instruction':'answer first, reasoning after',
                                   'evidence':'said it twice this week'},self.now)
        out=ctx.build(self.c,{'extra':{'user_message':'hi'}},now=self.now)
        self.assertIn('answer first, reasoning after',out)
        self.assertIn('rules, not',out)


class RelationshipTests(Base):
    def test_moments_are_grouped_by_what_kind_of_thing_they_are(self):
        for moment,text in (('nickname','he calls her Nov'),('joke','the thing about the nachos'),
                            ('first','the first time he sent a photo of his lunch')):
            notes.add_moment(self.c,{'moment':moment,'text':text},self.now)
        rendered=notes.render_relationship(self.c)
        self.assertIn('What you call each other:',rendered)
        self.assertIn('Running jokes:',rendered)
        self.assertIn('Firsts:',rendered)
        self.assertLess(rendered.index('What you call each other'),rendered.index('Running jokes'))

    def test_a_nickname_that_stopped_landing_is_retired_not_deleted(self):
        made=notes.add_moment(self.c,{'moment':'nickname','text':'he tried "Nov"'},self.now)
        notes.retire_moment(self.c,made['entry']['id'],'it did not stick',self.now)
        self.assertEqual(notes.moments(self.c),[])
        self.assertEqual(len(notes.moments(self.c,'retired')),1)
        self.assertIn('Nov',notes.moments_path(self.c).read_text())

    def test_the_history_is_injected_as_something_to_use_not_recite(self):
        notes.add_moment(self.c,{'moment':'ritual','text':'Sunday morning crossword'},self.now)
        out=ctx.build(self.c,{'extra':{'user_message':'hi'}},now=self.now)
        self.assertIn('Sunday morning crossword',out)
        self.assertIn('not as a list to recite',out)


class SharingTests(Base):
    def test_sharing_puts_the_rules_where_every_agent_reads_them(self):
        shared=cc.dataclasses.replace(self.c,profile='nova',share_people=True)
        private=cc.dataclasses.replace(self.c,profile='nova',share_people=False)
        self.assertEqual(shared.people,shared.vault/'people')
        self.assertTrue(private.people.is_relative_to(private.data))
        self.assertNotEqual(shared.human_dir,private.human_dir)

    def test_two_sharing_agents_see_one_ledger(self):
        one=cc.dataclasses.replace(self.c,agent='Nova',profile='nova',share_people=True)
        two=cc.dataclasses.replace(self.c,agent='Kit',profile='kit',share_people=True)
        notes.add_standing(one,{'instruction':'he is allergic to shellfish',
                                'evidence':'he said so on 2026-09-01'},self.now)
        self.assertEqual([r['instruction'] for r in notes.standing(two)],
                         ['he is allergic to shellfish'])

    def test_a_private_agent_starts_from_nothing(self):
        one=cc.dataclasses.replace(self.c,agent='Nova',profile='nova',share_people=True)
        alone=cc.dataclasses.replace(self.c,agent='Kit',profile='kit',share_people=False)
        notes.add_standing(one,{'instruction':'he is allergic to shellfish',
                                'evidence':'he said so on 2026-09-01'},self.now)
        self.assertEqual(notes.standing(alone),[])


class BatchTests(Base):
    def test_cli_exits_nonzero_for_a_partially_failed_batch(self):
        from unittest.mock import patch
        import contextlib,io
        path=self.c.home/'failed-input.json';path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps({'entries':[{'kind':'moment','text':'A real first'}, {'kind':'unknown'}]}))
        with patch.object(sys,'argv',['companion_notes.py','add','--file',str(path)]), \
             patch.object(cc,'load',return_value=self.c),contextlib.redirect_stdout(io.StringIO()), \
             self.assertRaises(SystemExit) as caught:
            notes.main()
        self.assertEqual(caught.exception.code,1)
        self.assertEqual(len(notes.moments(self.c)),1)

    def test_one_file_carries_both_kinds_and_stops_at_the_first_bad_entry(self):
        path=pathlib.Path(self.tmp.name)/'notes.json'
        path.write_text(json.dumps([
            {'kind':'standing','instruction':"don't guess at his sister's name",
             'evidence':"he corrected me on 2026-09-02"},
            {'kind':'moment','moment':'joke','text':'the nachos'},
            {'kind':'moment','moment':'gossip','text':'not a real kind'}]),encoding='utf-8')
        result=notes.batch(self.c,path,self.now)
        self.assertEqual(result['applied'],2);self.assertEqual(result['failed_at'],2)
        self.assertEqual(len(notes.standing(self.c)),1)
        self.assertEqual(len(notes.moments(self.c)),1)


if __name__=='__main__':unittest.main()
