"""Coverage and consistency of the expanded adult character catalog."""
import itertools
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from test_cli import run,answers,CORE_JOBS,scripted_job_names
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'kit/scripts'))
import companion_catalog as catalog
import companion_config as cc
import companion_render as cr
import companion_wizard as wiz

class CatalogTests(unittest.TestCase):
    def test_every_category_offers_ten_to_thirty_unique_choices_per_gender(self):
        self.assertGreaterEqual(len(cr.load_personas()),10)
        self.assertGreaterEqual(len(cr.load_styles())-2,10)
        # Six frames with romance available, plus five that are their own thing
        # rather than a romance with the romance taken out.
        self.assertEqual(len(catalog.BOUNDARIES),11)
        for key in ('penpal','mentor','sibling','housemate','creative-partner'):
            self.assertIn(key,catalog.BOUNDARIES)
            self.assertFalse(catalog.BOUNDARIES[key][1],f'{key} must not be an explicit frame')
        for key,cat in catalog.load()['categories'].items():
            self.assertIn(cat['section'],catalog.sections(),key)
            for gender in catalog.genders(key):
                rows=cat[gender]
                self.assertTrue(10<=len(rows)<=30,(key,gender,len(rows)))
                self.assertEqual(len({row['text'] for row in rows}),len(rows),(key,gender))
                self.assertEqual(len({row['label'] for row in rows}),len(rows),(key,gender))
                self.assertEqual(len({row['id'] for row in rows}),len(rows),(key,gender))
                self.assertEqual(rows[catalog.default_index(key,gender)-1]['id'],cat['default'])

    def test_hair_color_and_style_are_asked_separately(self):
        colors=[l for l,_ in catalog.options('hair_color')]
        styles=[l for l,_ in catalog.options('hair_style','female')]
        self.assertTrue(any('red' in l.lower() or 'auburn' in l.lower() for l in colors))
        self.assertTrue(any('green' in l.lower() for l,_ in catalog.options('eyes')))
        self.assertTrue(any('bob' in l.lower() for l in styles))
        # A color choice never dictates a cut, and a cut never dictates a color.
        for _,text in catalog.options('hair_style','male'):
            self.assertNotIn('blond',text.lower())

    def test_no_attraction_or_body_detail_presets(self):
        self.assertNotIn('attraction',catalog.categories())
        self.assertNotIn('bust',str(catalog.meta('build')))

    def test_heights_are_listed_in_feet_and_inches(self):
        for gender in ('male','female'):
            labels=[l for l,_ in catalog.options('height',gender)]
            for label in labels:
                self.assertRegex(label,r'^\d\'\d{1,2}" \(\d{3} cm\)$',label)
            self.assertEqual(len(labels),20,gender)
        self.assertIn("5'9\" (175 cm)",[l for l,_ in catalog.options('height','male')])
        self.assertIn("5'5\" (165 cm)",[l for l,_ in catalog.options('height','female')])

    def test_facial_hair_is_asked_of_male_companions_only(self):
        self.assertEqual(catalog.genders('facial_hair'),('male',))
        self.assertFalse(catalog.applies_to('facial_hair','female'))
        with self.assertRaises(ValueError):catalog.options('facial_hair','female')
        self.assertIsNone(wiz.interview('Nova','Alex','warm',{'boundary':'non-sexual','pronoun_set':'she'},quick=True)['facial_hair'])
        self.assertTrue(wiz.interview('Sol','Alex','warm',{'boundary':'non-sexual','pronoun_set':'he'},quick=True)['facial_hair'])
        for key in catalog.categories():
            if key!='facial_hair':self.assertEqual(catalog.genders(key),('male','female'),key)

    def test_marks_and_facial_hair_accept_several_choices_at_once(self):
        self.assertEqual(catalog.multi('marks'),3)
        self.assertEqual(catalog.multi('facial_hair'),2)
        self.assertEqual(catalog.multi('build'),0)
        out=wiz.interview('Nova','Alex','warm',{'boundary':'non-sexual','pronoun_set':'she','marks':[3,16]},quick=True)
        self.assertIn('eyebrow',out['marks']);self.assertIn('dimples',out['marks'])
        # Order follows the catalog, so the same set always reads the same way.
        self.assertEqual(out['marks'],wiz.interview('Nova','Alex','warm',
            {'boundary':'non-sexual','pronoun_set':'she','marks':'16, 3'},quick=True)['marks'])
        with self.assertRaises(ValueError):
            wiz.interview('Nova','Alex','warm',{'boundary':'non-sexual','pronoun_set':'she','marks':[1,2,3,4]},quick=True)

    def test_body_detail_is_not_generated(self):
        for pron in ('he','she'):
            out=wiz.interview('Nova','Alex','warm',{'boundary':'girlfriend','pronoun_set':pron},quick=True)
            self.assertIsNone(out['bust'])
            self.assertFalse(out['explicit'])
            self.assertEqual(out['encounters'],'')

    def test_flaws_and_occupation_reach_the_soul_and_can_be_declined(self):
        quiet=1+[l for l,_ in catalog.options('flaws','female','warm')].index('Goes quiet when overwhelmed')
        o=wiz.interview('Nova','Alex','warm',
                        {'boundary':'non-sexual','flaws':quiet,'occupation':1},quick=True)
        c=cc.Companion(agent='Nova',human='Alex',pronoun_set='she')
        o['physical']=wiz.physical_paragraph(o,'Nova',c.pronouns)
        soul=cr.render_template('SOUL.md.tmpl',cr.mapping_for(c,'warm','none',interview=o))
        self.assertIn('## Heart and temper',soul)
        self.assertIn('goes quiet instead of saying what is wrong',soul)
        self.assertIn('teaches',soul)
        # The guardrail under the section is not optional and never varies.
        self.assertIn('use a mood as leverage',soul)
        off=wiz.interview('Nova','Alex','warm',{'boundary':'non-sexual','flaws':wiz.SKIP_NONE,'occupation':wiz.SKIP_NONE},quick=True)
        self.assertNotIn('✎ EDIT',off['flaws']);self.assertNotIn('✎ EDIT',off['occupation'])
        self.assertIn('no stated occupation',off['occupation'])

    def test_flaws_are_sorted_by_the_chosen_personality(self):
        personas=list(cr.load_personas())
        for persona in personas:
            rows=catalog.rows_for('flaws','female',persona)
            fits=[r for r in rows if persona in r['personas']]
            self.assertTrue(fits,persona)                       # every personality has some
            self.assertEqual(rows[:len(fits)],fits,persona)     # and they come first
            self.assertEqual(catalog.default_index('flaws','female',persona),1,persona)
            # Sorting only reorders; nothing is added, dropped or duplicated.
            self.assertEqual({r['id'] for r in rows},
                             {r['id'] for r in catalog.rows_for('flaws','female')},persona)
        # Two personalities with different stereotypes lead with different flaws.
        self.assertNotEqual(catalog.options('flaws','female','sharp')[0],
                            catalog.options('flaws','female','shy')[0])
        # Only flaws sort this way; the rest keep a fixed order for every persona.
        for key in catalog.categories():
            self.assertEqual(catalog.sorts_by_persona(key),key=='flaws',key)
            for gender in catalog.genders(key):
                if key!='flaws':
                    self.assertEqual(catalog.options(key,gender,'sharp'),
                                     catalog.options(key,gender),key)

    def test_flaws_accept_none_or_several(self):
        self.assertEqual(catalog.multi('flaws'),-1)
        self.assertTrue(catalog.can_opt_out('flaws'))
        picks=wiz.interview('Nova','Alex','sharp',{'boundary':'non-sexual','flaws':[1,2]},quick=True)['flaws']
        for label in ('Deflects with a joke','Argues past winning'):
            text=dict((l,t) for l,t in catalog.options('flaws','female','sharp'))[label]
            self.assertIn(catalog.fill(text,'Nova','Alex','she','he'),picks)
        none=wiz.interview('Nova','Alex','sharp',{'boundary':'non-sexual','flaws':wiz.SKIP_NONE},quick=True)
        self.assertNotIn('✎ EDIT',none['flaws'])
        self.assertIn('fallible anyway',none['flaws'])
        self.assertIn('Flaws & friction',none['opted_out'])

    def test_emotional_framing_comes_from_the_persona_rather_than_a_question(self):
        self.assertNotIn('emotion',catalog.categories())
        seen=set()
        for persona,detail in cr.load_personas().items():
            c=cc.Companion(agent='Nova',human='Alex')
            soul=cr.render_template('SOUL.md.tmpl',cr.mapping_for(c,persona,'none'))
            section=soul.split('## Heart and temper',1)[1].split('##',1)[0]
            self.assertIn(cr.render(detail['emotion'],cr.mapping_for(c,persona,'none')),section,persona)
            self.assertIn('use a mood as leverage',section)      # the universal guardrail stays
            seen.add(detail['emotion'])
        self.assertEqual(len(seen),len(cr.load_personas()))

    def test_every_category_can_be_deferred_and_says_which_can_be_left_out(self):
        for key in catalog.categories():
            self.assertIn('✎ EDIT',catalog.skip_text(key,'defer'),key)
            if catalog.can_opt_out(key):
                self.assertNotIn('✎ EDIT',catalog.skip_text(key,'opt_out'),key)
                self.assertTrue(catalog.opt_out_label(key),key)
            else:
                with self.assertRaises(ValueError):catalog.skip_text(key,'opt_out')

    def test_all_choices_render_gender_and_names_without_template_tokens(self):
        for gender,pron in [('male','he'),('female','she')]:
            for key in catalog.load()['categories']:
                if not catalog.applies_to(key,gender):continue
                for label,text in catalog.options(key,gender):
                    out=catalog.fill(text,'Nova','Alex',pron,pron)
                    self.assertFalse(re.search(r'\{[A-Z_]+\}',out),(gender,key,out))
                    self.assertNotRegex(out,r'\b(?:she|her|herself)\b' if pron=='he' else r'\b(?:he|his|him|himself)\b')

    def test_numeric_choices_are_used_and_custom_answers_survive(self):
        for gender,pron in [('male','he'),('female','she')]:
            gender='male' if pron=='he' else 'female'
            shaved=1+[l for l,_ in catalog.options('hair_style',gender)].index('Shaved head')
            alt=1+[l for l,_ in catalog.options('style',gender)].index('Alternative & dark')
            out=wiz.interview('Nova','Alex','creative',{'boundary':'non-sexual','pronoun_set':pron,'hair_color':6,'hair_style':shaved,
                'style':alt,'core':'My exact custom personality.'},quick=True)
            self.assertEqual(out['core'],'My exact custom personality.')
            self.assertIn('ginger red',out['hair_color'])
            self.assertIn('shaved head',out['hair_style'].lower())
            self.assertIn('dark denim',out['style'])
            self.assertEqual(out['attraction'],'')
        with self.assertRaises(ValueError):wiz.interview('Nova','Alex','warm',{'boundary':'non-sexual','hair_color':99},quick=True)

    def test_skipping_leaves_either_an_edit_marker_or_a_deliberate_absence(self):
        out=wiz.interview('Nova','Alex','warm',
            {'boundary':'non-sexual','core':wiz.SKIP_EDIT,'likes':wiz.SKIP_NONE,'essence':''},quick=True)
        self.assertIn('✎ EDIT',out['core']);self.assertIn('✎ EDIT',out['essence'])
        self.assertNotIn('✎ EDIT',out['likes'])
        self.assertIn('Personality detail',out['skipped'])
        self.assertIn('Interests & hobbies',out['opted_out'])
        # A category with no opt-out text degrades to the ✎ EDIT marker instead.
        eyes=wiz.interview('Nova','Alex','warm',{'boundary':'non-sexual','eyes':wiz.SKIP_NONE},quick=True)['eyes']
        self.assertIn('✎ EDIT',eyes)

    def test_a_visual_identity_can_be_declined_outright_or_deferred(self):
        off=wiz.interview('Nova','Alex','warm',{'boundary':'non-sexual','visual':'none'},quick=True)
        self.assertIsNone(off['hair_color']);self.assertIsNone(off['build'])
        self.assertNotIn('✎ EDIT',off['appearance_note'])
        self.assertIn('Visual identity',off['opted_out'])
        later=wiz.interview('Nova','Alex','warm',{'boundary':'non-sexual','visual':'edit'},quick=True)
        self.assertIn('✎ EDIT',later['appearance_note'])
        self.assertIn('Visual identity',later['skipped'])
        body=wiz.physical_paragraph(later,'Nova',cc.Companion().pronouns)
        self.assertIn('24-year-old adult',body);self.assertIn('✎ EDIT',body)
        with self.assertRaises(ValueError):wiz.interview('Nova','Alex','warm',{'boundary':'non-sexual','visual':'maybe'},quick=True)

    def test_non_romantic_boundaries_ask_no_flirtation_question(self):
        for b in wiz.NON_ROMANTIC:
            out=wiz.interview('Nova','Alex','warm',{'boundary':b},quick=True)
            self.assertIsNone(out['flirtation'],b)
            self.assertEqual(out['attraction'],'',b)

    def test_all_personas_boundaries_and_genders_agree_with_scheduled_prompts(self):
        for persona,boundary,pron in itertools.product(cr.load_personas(),catalog.BOUNDARIES,('he','she')):
            iv=wiz.interview('Nova','Alex',persona,{'pronoun_set':pron,'human_pronoun_set':pron,'boundary':boundary},quick=True)
            c=cc.Companion(agent='Nova',human='Alex',pronoun_set=pron,human_pronoun_set=pron,boundary=boundary)
            iv['physical']=wiz.physical_paragraph(iv,c.agent,c.pronouns)
            m=cr.mapping_for(c,persona,'realistic',interview=iv)
            soul=cr.render_template('SOUL.md.tmpl',m)
            self.assertEqual(cr.unresolved(soul),[])
            self.assertLess(len(soul),c.soul_warn)
            self.assertEqual(m['BOUNDARY_ONELINE'],catalog.boundary_text(boundary))
            self.assertEqual(iv['explicit'],catalog.BOUNDARIES[boundary][1])
            if boundary=='platonic':
                self.assertNotIn('## Sexual Encounters',soul)
                self.assertIn('No flirtation; warmth is expressed as friendship.',soul)
            if pron=='he':self.assertNotIn("is Alex's girlfriend",soul)

    def test_a_scripted_setup_must_state_the_boundary_and_spell_keys_right(self):
        with self.assertRaisesRegex(ValueError,'choose a relationship style'):
            wiz.interview('Nova','Alex','warm',{'core':1},quick=True)
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp)/'hermes';vault=Path(tmp)/'vault'
            # 'hair' was split into hair_color and hair_style; the stale key used to
            # be ignored, leaving both questions on their defaults without a word.
            bad=json.loads(answers());bad['hair']=5
            out=run('--home',str(home),'init','--vault',str(vault),'--answers',json.dumps(bad),expect=1)
            self.assertIn('Unknown answer key(s): hair',out.stdout+out.stderr)
            self.assertFalse((home/'companion.json').exists())   # refused before writing
            run('--home',str(home),'init','--vault',str(vault),'--answers',answers(),expect=0)
            self.assertTrue((home/'companion.json').exists())

    def test_catalog_browse_does_not_create_a_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp)/'no-home'
            out=run('--home',str(home),'catalog','--gender','male','--category','style',expect=0)
            self.assertIn('10.',out.stdout)
            self.assertFalse(home.exists())

    def test_browse_leaves_no_raw_placeholders_in_labels_or_text(self):
        named=False
        for key in catalog.categories():
            for gender in catalog.genders(key):
                out=run('--home','/nonexistent','catalog','--gender',gender,'--category',key,expect=0)
                self.assertNotRegex(out.stdout,r'\{[A-Z_]+\}',(key,gender))
                named=named or '<<agent>>' in out.stdout
        self.assertTrue(named)   # the stand-in name is what browsing shows instead of a companion

    def test_setup_can_pause_and_then_authorize_the_six_jobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp)/'hermes';vault=Path(tmp)/'vault'
            run('--home',str(home),'init','--vault',str(vault),'--answers',answers(cron_active=False),expect=0)
            jobs=json.loads((home/'cron/jobs.json').read_text())['jobs']
            self.assertEqual(len(jobs),CORE_JOBS)
            scripted=scripted_job_names()
            # Jobs that run without a model stay active through a paused setup:
            # they cost nothing and they are the model-down safety net.
            self.assertTrue(all(j['enabled']==(j['name'] in scripted) for j in jobs))
            run('--home',str(home),'schedule','active',expect=0)
            jobs=json.loads((home/'cron/jobs.json').read_text())['jobs']
            self.assertTrue(all(j['enabled'] and j['next_run_at'] for j in jobs))
            self.assertTrue(json.loads((home/'companion.json').read_text())['cron_active'])
            run('--home',str(home),'schedule','paused',expect=0)
            self.assertTrue(all(not j['enabled'] for j in json.loads((home/'cron/jobs.json').read_text())['jobs']
                                if j['name'] not in scripted))

    def test_they_them_persona_replaces_gendered_words(self):
        out_they = wiz.interview('Unit-7', 'Alex', 'warm', {'boundary': 'girlfriend', 'pronoun_set': 'they', 'human_pronoun_set': 'he'}, quick=True)
        self.assertNotIn('girlfriend', out_they['boundary'].lower())
        self.assertIn('partner', out_they['boundary'].lower())

        # Verify that for she and he, girlfriend / boyfriend remains as is
        out_she = wiz.interview('Nova', 'Alex', 'warm', {'boundary': 'girlfriend', 'pronoun_set': 'she', 'human_pronoun_set': 'he'}, quick=True)
        self.assertIn('girlfriend', out_she['boundary'].lower())

        # Verify SOUL rendering for they/them robot companion
        c = cc.Companion(agent='Unit-7', human='Alex', pronoun_set='they')
        out_they['physical'] = wiz.physical_paragraph(out_they, 'Unit-7', c.pronouns)
        soul = cr.render_template('SOUL.md.tmpl', cr.mapping_for(c, 'warm', 'none', interview=out_they))
        self.assertIn('Unit-7 is warm', soul)
        self.assertNotIn('They is', soul)
        self.assertIn('writes this part themselves', soul)
