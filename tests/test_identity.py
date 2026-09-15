"""Identity: an age that moves, sections that can be rebuilt one at a time, and
the parts the companion does not get to rewrite."""
import datetime as dt
import json
import pathlib,sys,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'kit/scripts'))
import companion_config as cc
import companion_identity as identity
import companion_render as cr
import companion_self as slf
import companion_context as ctx

class AgeTests(unittest.TestCase):
    def test_a_birthdate_makes_the_age_move(self):
        c=cc.Companion(agent='Nova',human='Alex',birthdate='2001-03-14')
        self.assertEqual(c.current_age(dt.date(2026,3,13)),24)
        self.assertEqual(c.current_age(dt.date(2026,3,14)),25)
        self.assertEqual(c.current_age(dt.date(2027,3,14)),26)

    def test_without_one_the_recorded_number_still_works(self):
        self.assertEqual(cc.Companion(age=31).current_age(),31)
        self.assertIsNone(cc.Companion(age=31).birthday_in())

    def test_a_birthdate_that_would_make_a_child_is_refused(self):
        year=dt.date.today().year-5
        with self.assertRaisesRegex(ValueError,'adult'):
            cc.Companion(birthdate=f'{year}-01-01')
        with self.assertRaisesRegex(ValueError,'YYYY-MM-DD'):
            cc.Companion(birthdate='March 14th')

    def test_the_rendered_soul_uses_the_computed_age(self):
        c=cc.Companion(agent='Nova',human='Alex',age=24,birthdate='1996-01-01')
        m=cr.mapping_for(c,'warm','none')
        self.assertEqual(m['AGE'],str(c.current_age()))
        self.assertNotEqual(m['AGE'],'24')

    def test_the_physical_description_ages_with_her_too(self):
        """The number in the appearance paragraph is what a photo prompt reads,
        so a frozen one there is a companion who never gets older in pictures."""
        import companion_wizard as wiz
        import sys as _sys,pathlib as _p
        _sys.path.insert(0,str(ROOT))
        from kit.cli.common import mapping
        tmp=pathlib.Path(tempfile.mkdtemp())
        c=cc.Companion(agent='Nova',human='Alex',age=24,birthdate='1996-01-01',
                       hermes_root=tmp/'h',vault=tmp/'v')
        answers={'interview':{'age':24,'visual':'set','appearance_note':'',
                              'build':'slight','opted_out':[],'skipped':[]}}
        m=mapping(c,answers)
        self.assertIn(f'{c.current_age()}-year-old',m['PHYSICAL'])
        self.assertNotIn('24-year-old',m['PHYSICAL'])

    def test_the_turn_is_told_the_age_and_the_birthday(self):
        tmp=pathlib.Path(tempfile.mkdtemp())
        # The companion's date, not this machine's: the default config timezone
        # is UTC, and a host east or west of it is on another day for hours.
        from zoneinfo import ZoneInfo
        today=dt.datetime.now(ZoneInfo(cc.Companion.timezone)).date()
        c=cc.Companion(agent='Nova',human='Alex',hermes_root=tmp/'h',vault=tmp/'v',
                       birthdate=f'{today.year-30:04d}-{today.month:02d}-{today.day:02d}')
        c.soul_dir.mkdir(parents=True,exist_ok=True)
        (c.soul_dir/'ActiveContext.md').write_text('## Right now\nhere\n')
        out=ctx.build(c,{'extra':{'user_message':'hi'}})
        self.assertIn('It is your birthday',out)
        self.assertIn('not a thing to fish for',out)


class SectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=pathlib.Path(self.tmp.name)
        self.c=cc.Companion(agent='Nova',human='Alex',hermes_root=root/'h',vault=root/'v',
                            soul_in_vault=False)
        self.c.soul.parent.mkdir(parents=True,exist_ok=True)
        self.c.soul.write_text(cr.render_template('SOUL.md.tmpl',cr.mapping_for(self.c,'warm','none')),
                               encoding='utf-8')

    def test_every_section_is_findable_and_the_locked_ones_are_marked(self):
        found=identity.sections(self.c.soul.read_text())
        self.assertIn('core',found);self.assertIn('appearance',found)
        self.assertEqual(identity.locked_names(self.c),['appearance','boundary'])
        self.assertFalse(found['core']['locked'])

    def test_replacing_one_section_leaves_every_other_byte_alone(self):
        before=self.c.soul.read_text()
        identity.replace(self.c,'humor','She laughs at her own jokes first.')
        after=self.c.soul.read_text()
        self.assertIn('She laughs at her own jokes first.',after)
        found_before=identity.sections(before);found_after=identity.sections(after)
        for name in found_before:
            if name=='humor':continue
            self.assertEqual(found_before[name]['body'],found_after[name]['body'],name)

    def test_a_hand_edited_soul_survives_a_re_render_of_one_section(self):
        text=self.c.soul.read_text().replace('## Essence','## Essence\n\nI wrote this myself and it stays.')
        self.c.soul.write_text(text,encoding='utf-8')
        identity.replace(self.c,'humor',identity.render_section(self.c,'humor'))
        self.assertIn('I wrote this myself and it stays.',self.c.soul.read_text())

    def test_markers_cannot_be_smuggled_into_a_section(self):
        with self.assertRaisesRegex(ValueError,'markers'):
            identity.replace(self.c,'humor','<!-- COMPANION-SECTION:appearance -->')

    def test_an_unknown_section_is_named_not_guessed(self):
        with self.assertRaisesRegex(ValueError,'no section'):
            identity.replace(self.c,'sense-of-smell','x')


class LockGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=pathlib.Path(self.tmp.name)
        self.c=cc.Companion(agent='Nova',human='Alex',hermes_root=root/'h',vault=root/'v',
                            soul_in_vault=False,birthdate='1999-05-02')
        self.c.soul.parent.mkdir(parents=True,exist_ok=True)
        self.c.soul.write_text(cr.render_template('SOUL.md.tmpl',cr.mapping_for(self.c,'warm','none')),
                               encoding='utf-8')
        slf.soul_init(self.c)

    def test_she_can_still_write_about_who_she_is_becoming(self):
        result=slf.soul_write(self.c,'- I have got more impatient with small talk this month.','append')
        self.assertTrue(result['written'])

    def test_she_cannot_restate_her_own_boundaries_in_her_own_block(self):
        with self.assertRaisesRegex(ValueError,'not yours to change'):
            slf.soul_write(self.c,'- My boundaries are looser than they were.','append')

    def test_she_cannot_redescribe_her_build(self):
        with self.assertRaisesRegex(ValueError,'not yours to change'):
            slf.soul_write(self.c,'- My build is taller than it says up there.','append')

    def test_the_guard_names_what_it_objected_to(self):
        self.assertEqual(identity.guard(self.c,'my boundaries are different now'),['boundaries'])
        self.assertEqual(identity.guard(self.c,'nothing to see here'),[])


if __name__=='__main__':unittest.main()


class StyleTests(unittest.TestCase):
    """The four questions that make the difference between a companion and a
    template: how she writes, what she calls you, what she won't do, and the
    paragraph you wrote that she cannot argue with."""

    def render(self,**interview):
        c=cc.Companion(agent='Nova',human='Alex')
        return cr.render_template('SOUL.md.tmpl',cr.mapping_for(c,'warm','none',interview=interview))

    def test_pet_names_have_three_honest_settings(self):
        self.assertIn('No pet names',self.render(pet_names='no'))
        self.assertIn('affectionate names',self.render(pet_names='yes'))
        develop=self.render(pet_names='develop')
        self.assertIn('may try one',develop)
        self.assertIn('has to be insisted on is not a pet name',develop)

    def test_the_default_is_to_let_one_develop(self):
        self.assertEqual(self.render(),self.render(pet_names='develop'))

    def test_a_wont_do_list_says_a_repeat_is_the_same_request(self):
        out=self.render(wont_do='she never claims to have gone anywhere.')
        self.assertIn('never claims to have gone anywhere',out)
        self.assertIn('A request repeated is still the same request',out)

    def test_the_human_boundary_is_marked_as_not_hers_to_touch(self):
        out=self.render(human_boundary='Nothing sexual, ever.')
        self.assertIn('Nothing sexual, ever.',out)
        self.assertIn('does not edit it',out)
        self.assertIn('not negotiable',out)

    def test_an_empty_human_boundary_leaves_an_invitation_not_a_rule(self):
        out=self.render()
        self.assertIn('this paragraph is yours',out)

    def test_the_boundary_section_stays_locked_with_the_human_block_in_it(self):
        c=cc.Companion(agent='Nova',human='Alex')
        text=cr.render_template('SOUL.md.tmpl',
                                cr.mapping_for(c,'warm','none',interview={'human_boundary':'No romance.'}))
        section=identity.sections(text)['boundary']
        self.assertTrue(section['locked'])
        self.assertIn('No romance.',section['body'])
