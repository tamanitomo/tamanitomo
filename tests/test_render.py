"""Template rendering: nesting, pronouns, and no silent placeholder loss."""
import sys,pathlib,itertools,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'kit/scripts'))
import companion_config as cc, companion_render as cr

class RenderTests(unittest.TestCase):
    def test_titlecase_key_capitalises(self):
        self.assertEqual(cr.render('{{Subj}} went. {{SUBJ}} left.',{'SUBJ':'she'}),'She went. she left.')

    def test_nested_placeholders_resolve(self):
        out=cr.render('{{A}}',{'A':'hello {{B}}','B':'{{C}}','C':'world'})
        self.assertEqual(out,'hello world')

    def test_unknown_placeholder_is_left_visible_not_blanked(self):
        out=cr.render('x {{MISSING}} y',{})
        self.assertIn('{{MISSING}}',out)
        self.assertEqual(cr.unresolved(out),['MISSING'])

    def test_cycles_terminate(self):
        out=cr.render('{{A}}',{'A':'{{B}}','B':'{{A}}'})   # must not hang
        self.assertTrue(out)

    def test_every_preset_combination_renders_with_no_leaks(self):
        for persona,style,pron,boundary in itertools.product(
                cr.load_personas(),cr.load_styles(),('she','he','they'),
                ('non-sexual','platonic','open')):
            c=cc.Companion(agent='Nova',human='Alex',pronoun_set=pron,boundary=boundary)
            out=cr.render_template('SOUL.md.tmpl',cr.mapping_for(c,persona,style))
            self.assertEqual(cr.unresolved(out),[],f'{persona}/{style}/{pron}/{boundary}')

    def test_rendered_soul_carries_the_self_authored_block(self):
        c=cc.Companion(agent='Nova',human='Alex',pronoun_set='she')
        out=cr.render_template('SOUL.md.tmpl',cr.mapping_for(c))
        self.assertIn('COMPANION-SELF-AUTHORED:BEGIN',out)
        self.assertIn('COMPANION-SELF-AUTHORED:END',out)

    def test_rendered_soul_keeps_edit_markers_for_the_human(self):
        c=cc.Companion(agent='Nova',human='Alex')
        out=cr.render_template('SOUL.md.tmpl',cr.mapping_for(c))
        self.assertGreaterEqual(out.count('✎ EDIT'),5)

    def test_pronouns_are_grammatical(self):
        c=cc.Companion(agent='Kit',human='Rowan',pronoun_set='he')
        out=cr.render_template('SOUL.md.tmpl',cr.mapping_for(c,'quiet','none'))
        self.assertIn('writes this part himself',out)
        self.assertNotIn('heself',out);self.assertNotIn('sheself',out)
        c_they=cc.Companion(agent='Sam',human='Rowan',pronoun_set='they')
        out_they=cr.render_template('SOUL.md.tmpl',cr.mapping_for(c_they,'quiet','none'))
        self.assertIn('writes this part themselves',out_they)
        self.assertIn('They do not reset',out_they)
        self.assertIn('They are',out_they)

    def test_soul_fits_the_smallest_context_file_budget(self):
        """A generated SOUL must not be born already over Hermes' truncation floor."""
        c=cc.Companion(agent='Nova',human='Alex',context_tokens=8192)
        out=cr.render_template('SOUL.md.tmpl',cr.mapping_for(c,'warm','realistic'))
        self.assertLess(len(out),c.soul_warn)

    def test_unknown_preset_is_rejected_clearly(self):
        c=cc.Companion()
        with self.assertRaises(ValueError):cr.mapping_for(c,persona='nope')
        with self.assertRaises(ValueError):cr.mapping_for(c,style='nope')

    def test_presets_are_well_formed(self):
        for k,v in cr.load_personas().items():
            self.assertTrue({'label','blurb','core','voice','support','humor','emotion'}<=set(v),k)
        for k,v in cr.load_styles().items():
            self.assertTrue({'label','blurb','soul'}<=set(v),k)

if __name__=='__main__':unittest.main()


class WizardTests(unittest.TestCase):
    """The setup interview: names, the age floor, and skip behavior."""
    def setUp(self):
        import companion_wizard as w;self.w=w

    def test_names_are_comma_separated_and_deduped(self):
        self.assertEqual(self.w.parse_names('Alex, Babe, Sweetie'),['Alex','Babe','Sweetie'])
        self.assertEqual(self.w.parse_names('Alex,,alex , Babe'),['Alex','Babe'])
        self.assertEqual(self.w.parse_names(''),['you'])
        self.assertEqual(len(self.w.parse_names(','.join(f'n{i}' for i in range(20)))),6)

    def test_names_sentence_reads_naturally(self):
        self.assertEqual(self.w.names_sentence(['Alex']),'Alex by name')
        s=self.w.names_sentence(['Alex','Babe'])
        self.assertIn('Alex by name',s);self.assertIn('"Babe"',s)

    def test_age_floor_is_enforced(self):
        for bad in (17,0,-5,'x',None):
            with self.assertRaises(ValueError):self.w.ask_age('Nova',{'age':bad})
        self.assertEqual(self.w.ask_age('Nova',{'age':18}),18)

    def test_girlfriend_frame_supplies_flirting_without_encounters(self):
        o=self.w.interview('Nova','Alex','warm',{'boundary':'girlfriend'},quick=True)
        self.assertFalse(o['explicit']);self.assertEqual(o['encounters'],'')
        self.assertIn('flirting',o['boundary'])

    def test_other_boundaries_carry_none(self):
        for b in ('non-sexual','platonic','open'):
            o=self.w.interview('Nova','Alex','warm',{'boundary':b},quick=True)
            self.assertFalse(o['explicit']);self.assertEqual(o['encounters'],'')

    def test_platonic_skips_flirtation(self):
        o=self.w.interview('Nova','Alex','warm',{'boundary':'platonic'},quick=True)
        self.assertIsNone(o['flirtation'])

    def test_skipped_answers_become_edit_markers(self):
        o=self.w.interview('Nova','Alex','warm',
                           {'boundary':'non-sexual','core':'','essence':'','hair_color':''},quick=True)
        self.assertIn('✎ EDIT',o['core']);self.assertIn('✎ EDIT',o['essence'])
        c=cc.Companion(agent='Nova',human='Alex')
        o['physical']=self.w.physical_paragraph(o,'Nova',c.pronouns)
        o['names_sentence']=self.w.names_sentence(['Alex'])
        out=cr.render_template('SOUL.md.tmpl',cr.mapping_for(c,'warm','none',interview=o))
        self.assertIn('✎ EDIT',out)
        self.assertEqual(cr.unresolved(out),[])

    def test_a_fully_answered_soul_has_no_edit_markers_left(self):
        w=self.w
        a={'core':w.CORE[0][1],'met':w.MET[0][1],'age':22,'build':w.BUILD[0][1],
           'height':w.HEIGHT[0][1],'hair_color':w.HAIR_COLOR[0][1],'hair_style':w.HAIR_STYLE[0][1],
           'eyes':w.EYES[0][1],'complexion':w.COMPLEXION[0][1],'style':w.STYLE[0][1],
           'boundary':'girlfriend','visual':'set','flirtation':w.FLIRT_SOFT[0][1],
           'likes':w.LIKES[0][1],'essence':w.ESSENCE[0][1]}
        o=w.interview('Nova','Alex','warm',a,quick=True)
        c=cc.Companion(agent='Nova',human='Alex',names=['Alex','Babe'])
        o['physical']=w.physical_paragraph(o,'Nova',c.pronouns)
        o['names_sentence']=w.names_sentence(c.all_names)
        out=cr.render_template('SOUL.md.tmpl',cr.mapping_for(c,'warm','anime-modern',interview=o))
        body=out.split('-->',1)[1]          # ignore the header comment
        self.assertNotIn('✎ EDIT',body)
        self.assertNotIn('## Sexual Encounters',out)
        self.assertIn('"Babe"',out)


class PromptQuotingTests(unittest.TestCase):
    """Model-authored prose must never travel as a quoted shell argument.

    An apostrophe in a remembered sentence broke an unattended cron run once; the
    fix everywhere is write_file plus a --file flag, so the guard is a scan of the
    rendered prompts rather than a note in the review log.
    """
    FLAGS=('--statement','--evidence','--text','--answer','--append','--message','--reason')

    def test_no_cron_prompt_tells_the_model_to_quote_prose(self):
        c=cc.Companion(agent='Nova',human='Alex')
        m=cr.mapping_for(c,'warm','none')
        for path in sorted((ROOT/'kit/templates/cron').glob('*.tmpl')):
            out=cr.render(path.read_text(),m)
            for flag in self.FLAGS:
                for quote in ("'",'"'):
                    self.assertNotIn(flag+' '+quote,out,f'{path.name} quotes prose after {flag}')

    def test_every_cron_prompt_renders_with_nothing_left_unresolved(self):
        c=cc.Companion(agent='Nova',human='Alex')
        m=cr.mapping_for(c,'warm','none')
        for path in sorted((ROOT/'kit/templates/cron').glob('*.tmpl')):
            self.assertEqual(cr.unresolved(cr.render(path.read_text(),m)),[],path.name)


if __name__=='__main__':unittest.main()
