"""Agent types: what machinery exists at all.

Not a personality setting. A quiet worker has no present to advance and no
mornings to have, and a colleague that thinks it is a companion drifts toward
writing first.
"""
import json
import pathlib,sys,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'kit/scripts'));sys.path.insert(0,str(ROOT))
import companion_config as cc
import companion_render as cr
from kit.cli.common import load_manifest

def jobs_for(kind):
    c=cc.Companion(agent='Nova',human='Alex',agent_type=kind,
                   hermes_root=pathlib.Path(tempfile.mkdtemp()))
    return {spec['key'] for spec in load_manifest(c)['jobs']}

class JobSetTests(unittest.TestCase):
    def test_a_companion_gets_the_whole_life(self):
        keys=jobs_for('companion')
        # No 'present': the pulse, the morning and the wind-down all rebuild the
        # handoff through presence.update, so a separate advancer was a fourth
        # writer of one field and a job that rendered what was already rendered.
        for key in ('pulse','autonomy','wake','winddown','sensors','checkin','quiet'):
            self.assertIn(key,keys)

    def test_a_colleague_grows_but_has_no_mornings(self):
        keys=jobs_for('colleague')
        self.assertIn('pulse',keys);self.assertIn('checkin',keys)   # it still becomes someone
        for key in ('wake','winddown','quiet'):
            self.assertNotIn(key,keys,f'a colleague should not have {key}')

    def test_a_worker_has_no_inner_life_at_all(self):
        keys=jobs_for('worker')
        for key in ('pulse','autonomy','present','wake','winddown','sensors','checkin','daily'):
            self.assertNotIn(key,keys,f'a worker should not have {key}')
        # but it still does work, keeps records and can be recovered
        for key in ('window','hygiene','watch','vault','dispatch'):
            self.assertIn(key,keys)

    def test_everyone_keeps_the_safety_net(self):
        for kind in ('companion','colleague','worker'):
            self.assertIn('watch',jobs_for(kind))
            self.assertIn('vault',jobs_for(kind))


class SoulTests(unittest.TestCase):
    def test_each_type_is_told_plainly_what_it_is(self):
        rendered={}
        for kind in ('companion','colleague','worker'):
            c=cc.Companion(agent='Nova',human='Alex',agent_type=kind)
            rendered[kind]=cr.render_template('SOUL.md.tmpl',cr.mapping_for(c,'warm','none'))
            self.assertEqual(cr.unresolved(rendered[kind]),[])
        self.assertIn('not a companion',rendered['worker'])
        self.assertIn('colleague, not',rendered['colleague'])
        self.assertIn('only when something is genuinely broken',rendered['colleague'])
        # A companion is not told what it is not; it is simply itself.
        self.assertNotIn('not a companion',rendered['companion'])

    def test_the_inner_life_flag_matches_the_job_set(self):
        for kind,expected in (('companion',True),('colleague',True),('worker',False)):
            self.assertEqual(cc.Companion(agent_type=kind).has_inner_life,expected)

    def test_an_unknown_type_is_refused(self):
        with self.assertRaisesRegex(ValueError,'agent_type'):
            cc.Companion(agent_type='oracle')


if __name__=='__main__':unittest.main()
