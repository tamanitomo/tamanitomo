"""Care is transactional, chronological and shared by agent and local-model writes."""
import datetime as dt
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch
import io
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'kit/scripts'))
import companion_config as cc
import companion_presence as p
import companion_lifestyle as life
import companion_local_pulse as worker
import companion_preread as preread
import companion_day as day

class LifestyleTests(unittest.TestCase):
    def test_seeded_clothing_never_names_a_garment_it_is_not(self):
        """A description is all an image model gets, so it has to name the garment.

        The outfit reaches an image prompt as a flat list of descriptions with
        no category beside them. "bikini panties" is a cut of underwear to a
        person and a swimsuit to an image model, which duly painted one over a
        sleep tee. "trunks" and "vest" fail the same way in the other direction.
        These words are correct under swimwear and nowhere else.
        """
        import re
        source = (pathlib.Path(__file__).resolve().parent.parent
                  / 'kit/scripts/companion_lifestyle.py').read_text(encoding='utf-8')
        confusable = ('bikini', 'trunks', 'swimsuit', 'boardshorts', 'vest')
        offenders = []
        for line in source.splitlines():
            match = re.search(r'\b(\w*_desc)\s*=\s*(.+)$', line)
            if not match:
                continue
            name, value = match.group(1), match.group(2).lower()
            if name.startswith('swim'):
                continue
            for word in confusable:
                # "bikini-cut briefs" and "trunk-cut boxer briefs" name the
                # garment and qualify the cut, which is the fix, not the fault.
                if re.search(r'\b' + word + r'\b(?!-(?:cut|style))', value):
                    offenders.append(f'{name}: {word}')
        self.assertEqual(offenders, [],
            'these read as a different garment than intended: ' + ', '.join(offenders))

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=pathlib.Path(self.tmp.name)
        self.c=cc.Companion(hermes_root=root/'h',vault=root/'v',timezone='America/New_York')
        self.c.home.mkdir();self.c.soul.write_text('A companion who enjoys walking and reading.')
        self.now=dt.datetime(2026,9,13,12,tzinfo=dt.timezone.utc)
        p.update_wardrobe(self.c,[dict(id='old',description='old clothes',use='day',category='day'),
                                 dict(id='fresh',description='fresh clothes',use='day',category='day'),
                                 dict(id='pj',description='pajamas',use='sleep',category='sleep')])
        self.write(0)
        (self.c.life/'routine.json').write_text(json.dumps({'kind':'imagined_routine','daily':[
            dict(start='09:00',end='11:00',activity='park walk',setting='fictional park')],
            'lifestyle':{'enabled':True}}))
    def data(self,**kw):
        current=p.current(self.c)
        d=dict(previous_id=current['id'] if current else None,outfit=['old'],activity='reading',
               location='home',mood='calm',text='A new moment.',transition='A deliberate change.')
        d.update(kw);return d
    def write(self,minutes,**kw):return p.update(self.c,self.data(**kw),self.now+dt.timedelta(minutes=minutes))
    def actions(self,*kinds):return [dict(kind=k,items=[]) for k in kinds]
    def test_dressing_requires_teeth_and_pajamas_require_shower(self):
        previous=p.current(self.c)
        with self.assertRaisesRegex(ValueError,'brush teeth'):self.write(15,outfit=['fresh'])
        with self.assertRaisesRegex(ValueError,'shower'):self.write(15,outfit=['pj'],care_actions=self.actions('brush_teeth'))
        self.assertEqual(p.current(self.c),previous)
        self.write(15,outfit=['pj'],care_actions=self.actions('brush_teeth','shower'))
        self.assertEqual(p.current(self.c)['state']['lifestyle']['clothes']['old'],'dirty')
        self.assertEqual(len(p.current(self.c)['state']['care_actions']),2)
    def test_dirty_rewear_needs_prior_laundry_and_elapsed_drying(self):
        self.write(15,outfit=['fresh'],care_actions=self.actions('brush_teeth'))
        with self.assertRaisesRegex(ValueError,'laundry'):self.write(30,outfit=['old'])
        self.write(30,outfit=['fresh'],care_actions=[dict(kind='laundry_start',items=['old'])])
        before=p.current(self.c)
        with self.assertRaisesRegex(ValueError,'90 minutes'):
            self.write(45,outfit=['old'],care_actions=[dict(kind='laundry_finish',items=['old'])])
        self.assertEqual(p.current(self.c),before)
        self.write(120,outfit=['old'],care_actions=[dict(kind='laundry_finish',items=['old'])],routine_choice=dict(anchor='daily-0',decision='defer',reason='Finish the laundry before heading to the park.'))
        self.assertEqual(p.current(self.c)['state']['lifestyle']['clothes']['fresh'],'dirty')
        self.assertIsNone(p.current(self.c)['state']['lifestyle']['laundry'])
    def test_cannot_wash_worn_final_clothes_or_instantly_complete_care(self):
        for actions,minutes in [([dict(kind='laundry_start',items=['old'])],15),(self.actions('brush_teeth','shower'),1)]:
            with self.assertRaises(ValueError):self.write(minutes,care_actions=actions)
    def test_midnight_continuation_allowed_but_fresh_dressing_needs_new_teeth(self):
        self.write(15,outfit=['pj'],care_actions=self.actions('brush_teeth','shower'))
        self.write(17*60,outfit=['pj'])
        with self.assertRaisesRegex(ValueError,'brush teeth'):self.write(17*60+15,outfit=['fresh'])
        self.write(17*60+15,outfit=['fresh'],care_actions=self.actions('brush_teeth'))
    def test_unchanged_clothes_cannot_continue_forever(self):
        self.write(15)
        with self.assertRaisesRegex(ValueError,'24 hours'):self.write(24*60+30)
    def test_shopping_is_atomic_bounded_and_profile_local(self):
        item=dict(id='new',description='plum sports bra',use='exercise',category='active',condition='clean')
        bad=self.data(outfit=['new'],care_actions=self.actions('shop'),wardrobe_additions=[item])
        with self.assertRaisesRegex(ValueError,'brush teeth'):p.update(self.c,bad,self.now+dt.timedelta(minutes=15))
        self.assertNotIn('new',[i['id'] for i in p.wardrobe(self.c)['items']])
        good=self.data(outfit=['new'],care_actions=self.actions('brush_teeth','shop'),wardrobe_additions=[item])
        result=p.update(self.c,good,self.now+dt.timedelta(minutes=15))
        self.assertFalse(p.update(self.c,good,self.now+dt.timedelta(minutes=15))['written'])
        self.assertIn('new',[i['id'] for i in p.wardrobe(self.c)['items']])
        with self.assertRaisesRegex(ValueError,'not due'):self.write(30,outfit=['new'],care_actions=self.actions('shop'))
        other=cc.Companion(hermes_root=self.c.home/'other',vault=self.c.vault/'other')
        self.assertEqual(p.wardrobe(other)['items'],[])
    def test_advancer_does_not_complete_laundry_or_care(self):
        self.write(15,outfit=['fresh'],care_actions=self.actions('brush_teeth'))
        self.write(30,outfit=['fresh'],care_actions=[dict(kind='laundry_start',items=['old'])])
        old=p.current(self.c)['state']['lifestyle']
        p.advance(self.c,self.now+dt.timedelta(hours=4))
        self.assertEqual(p.current(self.c)['state']['lifestyle'],old)
    def test_context_includes_daily_routine_and_clothing_and_seed_is_idempotent(self):
        text=preread.preread(self.c,self.now)
        self.assertIn('park walk',text);self.assertIn('care_actions',text);self.assertIn('pajamas',text)
        first=life.seed(self.c);self.assertGreater(first['added_items'],10)
        self.assertEqual(life.seed(self.c)['added_items'],0)
        self.assertIn('park walk',(self.c.life/'routine.json').read_text())
    def test_local_model_gets_care_correction_and_records_valid_result(self):
        bad=self.data(outfit=['pj']);good=dict(bad,care_actions=self.actions('brush_teeth','shower'))
        def response(d):return io.BytesIO(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(d)}}]}).encode())
        with patch.object(worker.urllib.request,'urlopen',side_effect=[response(bad),response(good)]) as call:
            result=worker.pulse(self.c,'http://127.0.0.1:11434/v1','test',now=self.now+dt.timedelta(minutes=15))
        self.assertEqual(result['planning_attempts'],2)
        self.assertEqual(p.current(self.c)['state']['outfit'][0]['id'],'pj')
    def test_active_routine_and_overdue_activity_cannot_be_silently_ignored(self):
        with self.assertRaisesRegex(ValueError,'ROUTINE'):self.write(90)
        self.write(90,routine_choice=dict(anchor='daily-0',decision='defer',reason='Heavy rain; stretch indoors and reconsider the walk after lunch.'),duration_minutes=20)
        with self.assertRaisesRegex(ValueError,'OVERDUE'):
            self.write(120,routine_choice=dict(anchor='daily-0',decision='defer',reason='Rain continues'),duration_minutes=180)

    def test_rewording_does_not_reset_activity_clock(self):
        self.write(15,duration_minutes=20)
        old=p.current(self.c)['state']['started_at']
        self.write(30,activity='finishing my reading',activity_change='continue',duration_minutes=20,delay_reason='Finishing the last paragraph before setting the book down.')
        state=p.current(self.c)['state']
        self.assertEqual(state['started_at'],old)
    def test_starter_wardrobe_tailored_by_agent_type_sex_age_and_personality(self):
        # 1. Female young romantic companion (sporty, expressive, and revealing)
        c_comp_f = cc.Companion(agent_type='companion', pronoun_set='she', age=22, persona='romantic')
        w_comp_f = {i['id']: i['description'] for i in life.build_starter_wardrobe(c_comp_f)}
        self.assertIn('bikini-cut briefs with subtle lace trim', w_comp_f['closet-underwear-1'])
        self.assertIn('sundress', w_comp_f['closet-occasion'])
        self.assertIn('bikini', w_comp_f['closet-swimwear'])
        self.assertIn('cardigan', w_comp_f['closet-cardigan'])
        self.assertIn('crop top revealing the midriff', w_comp_f['closet-day-top-1'])
        self.assertIn('way-oversized slouchy boyfriend T-shirt', w_comp_f['closet-day-top-2'])
        self.assertIn('sculpting leggings', w_comp_f['closet-day-bottoms-1'])
        self.assertIn('booty shorts', w_comp_f['closet-day-bottoms-2'])
        self.assertIn('booty shorts', w_comp_f['closet-shorts'])
        self.assertIn('sports bra', w_comp_f['closet-sports-bra-1'])


        # 2. Male creative companion
        c_comp_m = cc.Companion(agent_type='companion', pronoun_set='he', age=30, persona='creative')
        w_comp_m = {i['id']: i['description'] for i in life.build_starter_wardrobe(c_comp_m)}
        self.assertIn('boxer briefs', w_comp_m['closet-underwear-1'])
        self.assertIn('corduroy', w_comp_m['closet-occasion'])
        self.assertIn('swimming trunks', w_comp_m['closet-swimwear'])

        # 3. Female sharp colleague
        c_col_f = cc.Companion(agent_type='colleague', pronoun_set='she', age=35, persona='sharp')
        w_col_f = {i['id']: i['description'] for i in life.build_starter_wardrobe(c_col_f)}
        self.assertIn('invisible microfiber briefs', w_col_f['closet-underwear-1'])
        self.assertIn('blazer', w_col_f['closet-cardigan'])
        self.assertIn('loafers', w_col_f['closet-trainers'])
        self.assertIn('button-down', w_col_f['closet-day-top-1'])

        # 4. Male steady colleague
        c_col_m = cc.Companion(agent_type='colleague', pronoun_set='he', age=52, persona='steady')
        w_col_m = {i['id']: i['description'] for i in life.build_starter_wardrobe(c_col_m)}
        self.assertIn('pima cotton boxer briefs', w_col_m['closet-underwear-1'])
        self.assertIn('blazer', w_col_m['closet-cardigan'])
        self.assertIn('oxford dress shoes', w_col_m['closet-trainers'])
        self.assertIn('two-piece wool suit', w_col_m['closet-occasion'])

        # 5. Worker (both female and male get heavy-duty utility gear and steel-toe boots)
        c_work_f = cc.Companion(agent_type='worker', pronoun_set='she', age=28, persona='protective')
        w_work_f = {i['id']: i['description'] for i in life.build_starter_wardrobe(c_work_f)}
        self.assertIn('steel-toe work boots', w_work_f['closet-trainers'])
        self.assertIn('canvas lined chore jacket', w_work_f['closet-cardigan'])
        self.assertIn('double-knee canvas utility work pants', w_work_f['closet-day-bottoms-1'])
        self.assertIn('reinforced cotton pocket work shirt', w_work_f['closet-day-top-1'])

    def test_daily_routine_tailored_by_agent_type(self):
        c_worker = cc.Companion(agent_type='worker')
        worker_acts = [a['activity'] for a in life.default_daily_routine(c_worker)]
        self.assertTrue(any('work clothes' in act for act in worker_acts))
        self.assertTrue(any('morning work shift' in act for act in worker_acts))

        c_colleague = cc.Companion(agent_type='colleague')
        col_acts = [a['activity'] for a in life.default_daily_routine(c_colleague)]
        self.assertTrue(any('professional daytime attire' in act for act in col_acts))
        self.assertTrue(any('deep work' in act for act in col_acts))


if __name__=='__main__':unittest.main()
