"""The one module that calls a model.

What is tested here is not the model. It is everything around it: that a reply
is read tolerantly, that nothing the model says about age or length gets into a
locked section, that the proposal is shaped exactly like a typed one, and that
looking at a photograph never writes a file by itself.
"""
import pathlib,sys,tempfile,unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'kit/scripts'));sys.path.insert(0,str(ROOT))
import companion_config as cc
import companion_render as cr
import companion_vision as vision


class ReplyTests(unittest.TestCase):
    def test_bare_json_is_read(self):
        self.assertEqual(vision._extract('{"a":1}'),{'a':1})

    def test_a_fence_or_a_preamble_does_not_throw_the_answer_away(self):
        for reply in ('Here you go:\n```json\n{"a":1}\n```',
                      'Sure!\n\n{"a":1}\n\nHope that helps.',
                      '```\n{"a":1}\n```'):
            self.assertEqual(vision._extract(reply),{'a':1},reply)

    def test_braces_inside_a_string_do_not_confuse_it(self):
        self.assertEqual(vision._extract('{"a":"a { and a }","b":2}'),{'a':'a { and a }','b':2})

    def test_prose_with_no_json_is_an_error_not_a_guess(self):
        with self.assertRaises(ValueError):vision._extract('I cannot see the image.')

    def test_a_refusal_is_surfaced_as_the_reason(self):
        with self.assertRaises(ValueError) as caught:
            vision.fields_from('{"error":"no visible face"}')
        self.assertIn('no visible face',str(caught.exception))


class FieldTests(unittest.TestCase):
    def test_age_is_never_taken_from_the_model(self):
        fields=vision.fields_from('{"age":"about 30","hair_color":"black hair"}')
        self.assertEqual(fields,{'hair_color':'black hair'})

    def test_unknown_keys_and_non_strings_are_dropped(self):
        fields=vision.fields_from('{"name":"Ada","eyes":["green"],"build":"slim","mood":"happy"}')
        self.assertEqual(fields,{'build':'slim'})

    def test_an_essay_in_one_field_is_refused_rather_than_stored(self):
        fields=vision.fields_from('{"style":"%s","build":"slim"}'%('x'*400))
        self.assertEqual(fields,{'build':'slim'})

    def test_whitespace_is_normalized(self):
        self.assertEqual(vision.fields_from('{"hair_color":"  dark\\n  auburn "}'),
                         {'hair_color':'dark auburn'})

    def test_nothing_usable_is_an_error(self):
        with self.assertRaises(ValueError):vision.fields_from('{"mood":"cheerful"}')


class ProposalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=pathlib.Path(self.tmp.name)
        self.c=cc.Companion(agent='Nova',human='Alex',hermes_root=root/'h',vault=root/'v',
                            timezone='UTC',soul_in_vault=False,birthdate='1996-01-01')
        self.c.home.mkdir(parents=True,exist_ok=True)
        self.c.soul.write_text(cr.render_template('SOUL.md.tmpl',cr.mapping_for(self.c,'warm','none')),
                               encoding='utf-8')
        self.c.save()

    def test_the_proposal_is_shaped_like_a_typed_one(self):
        body=vision.proposal(self.c,{'hair_color':'dark auburn hair','build':'slight build',
                                     'eyes':'grey eyes'})
        self.assertIn(f'Nova is a {self.c.current_age()}-year-old adult.',body)
        self.assertIn('## What Nova looks like',body)
        # Fixed order is the whole reason a likeness stays the same person.
        self.assertLess(body.index('grey eyes'),body.index('dark auburn hair'))
        self.assertLess(body.index('dark auburn hair'),body.index('slight build'))
        self.assertNotIn('✎ EDIT',body)

    def test_describe_returns_a_proposal_and_leaves_the_soul_alone(self):
        import companion_portrait as pt
        path=pt.portrait_path(self.c);path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(b'not read by describe, only existence is checked')
        before=self.c.soul.read_text()
        with patch.object(vision,'ask',return_value='{"hair_color":"black hair"}'):
            out=vision.describe(self.c)
        self.assertFalse(out['written'])
        self.assertIn('black hair',out['body'])
        self.assertEqual(self.c.soul.read_text(),before)

    def test_a_missing_likeness_is_refused_before_any_model_is_called(self):
        with patch('subprocess.run') as ran:
            with self.assertRaises(ValueError):vision.describe(self.c)
        ran.assert_not_called()


class CallTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=pathlib.Path(self.tmp.name)
        self.c=cc.Companion(agent='Nova',human='Alex',hermes_root=root/'h',vault=root/'v',
                            timezone='UTC')
        self.c.home.mkdir(parents=True,exist_ok=True)
        self.image=root/'face.png';self.image.write_bytes(b'x')

    def _run(self,returncode=0,stdout='{"build":"slim"}',stderr=''):
        class Result:pass
        result=Result();result.returncode=returncode
        result.stdout=stdout;result.stderr=stderr
        return result

    def test_the_companions_own_soul_is_not_injected_into_the_look(self):
        with patch('subprocess.run',return_value=self._run()) as ran:
            vision.ask(self.c,self.image)
        argv=ran.call_args[0][0]
        self.assertIn('--ignore-rules',argv)
        self.assertIn('--image',argv)
        self.assertIn(str(self.image),argv)
        self.assertIn('--oneshot',argv)
        self.assertEqual(ran.call_args[1]['env']['HERMES_HOME'],str(self.c.home))

    def test_a_pinned_model_is_passed_through(self):
        with patch('subprocess.run',return_value=self._run()) as ran:
            vision.ask(self.c,self.image,model='some/vision-model',provider='somewhere')
        argv=ran.call_args[0][0]
        self.assertEqual(argv[argv.index('--model')+1],'some/vision-model')
        self.assertEqual(argv[argv.index('--provider')+1],'somewhere')

    def test_a_failed_call_says_so_instead_of_returning_nothing(self):
        with patch('subprocess.run',return_value=self._run(returncode=1,stdout='',stderr='no credit')):
            with self.assertRaises(ValueError) as caught:vision.ask(self.c,self.image)
        self.assertIn('no credit',str(caught.exception))

    def test_the_prompt_is_passed_as_a_file_so_nothing_is_shell_interpreted(self):
        seen={}
        def fake(argv,**kw):
            seen['prompt']=pathlib.Path(argv[argv.index('--query-file')+1]).read_text(encoding='utf-8')
            return self._run()
        with patch('subprocess.run',side_effect=fake):
            vision.ask(self.c,self.image)
        self.assertIn('single JSON object',seen['prompt'])
        self.assertIn('do not include an age key',seen['prompt'])
        for field in vision.FIELDS:self.assertIn('- '+field,seen['prompt'])


if __name__=='__main__':unittest.main()
