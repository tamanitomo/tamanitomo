"""The interactive prompt itself: paging, toggling, writing in and skipping.

Every other suite reaches the questionnaire through the answers dict, which is
the non-interactive branch. These drive the keyboard path that a person actually
uses, by feeding `input` and pretending to be a terminal.
"""
import io
import os
import pathlib
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'kit/scripts'))
import companion_catalog as catalog
import companion_wizard as wiz

BANK=[(f'Option {i}',f'Text {i}.') for i in range(1,21)]

def keyboard(keys,buf):
    """input() prints its prompt in a real terminal; the mock has to as well, or
    the screen under test is missing every hint line."""
    it=iter(list(keys))
    def typed(prompt=''):
        buf.write(str(prompt))
        return next(it)
    return typed

def drive(keys,**kw):
    """Run one prompt against a scripted keyboard. Returns (result, screen)."""
    buf=io.StringIO();ascii_output=kw.pop('ascii_output',False)
    with patch.dict(os.environ,{'COMPANION_PLAIN':'1'}),patch.object(wiz,'ascii_mode',return_value=ascii_output),patch.object(wiz,'_tty',return_value=True),\
         patch.object(wiz,'_color_ok',return_value=False),\
         patch('builtins.input',side_effect=keyboard(keys,buf)),redirect_stdout(buf):
        got=wiz.choose('Prompt?',kw.pop('options',BANK),**kw)
    return got,buf.getvalue()

class SingleChoiceTests(unittest.TestCase):
    def test_a_number_picks_and_enter_takes_the_default(self):
        self.assertEqual(drive(['4'])[0],'Text 4.')
        self.assertEqual(drive([''],default=7)[0],'Text 7.')

    def test_out_of_range_and_junk_are_rejected_without_choosing(self):
        got,screen=drive(['0','99','banana','3'])
        self.assertEqual(got,'Text 3.')
        self.assertEqual(screen.count('pick a number from the list'),3)

    def test_paging_keeps_numbering_global(self):
        got,screen=drive(['n','15'])
        self.assertEqual(got,'Text 15.')
        self.assertIn('showing 13–20 of 20',screen)
        got,screen=drive(['n','p','2'])
        self.assertEqual(got,'Text 2.')
        self.assertIn('showing 1–12 of 20',screen)

    def test_an_option_on_a_later_page_can_be_picked_without_paging_to_it(self):
        self.assertEqual(drive(['18'])[0],'Text 18.')

    def test_write_your_own_collects_lines_until_a_blank_one(self):
        got,_=drive(['21','I wrote this.','And this.',''])
        self.assertEqual(got,'I wrote this. And this.')
        got,screen=drive(['21','','5'])          # nothing typed falls back to the list
        self.assertEqual(got,'Text 5.')
        self.assertIn('nothing written',screen)

    def test_the_two_skips_are_numbered_and_distinct(self):
        got,screen=drive(['22'])
        self.assertIs(got,wiz.SKIP_EDIT)
        self.assertIn('✎ EDIT',screen)
        self.assertIs(drive(['23'],opt_out_label='not a thing here')[0],wiz.SKIP_NONE)
        # Without an opt-out label there is no third skip to reach.
        got,screen=drive(['23','1'])
        self.assertEqual(got,'Text 1.')
        self.assertIn('pick a number from the list',screen)

class ToggleTests(unittest.TestCase):
    def test_numbers_tick_and_untick_and_enter_accepts(self):
        got,screen=drive(['3','1','3',''],multi=3)
        self.assertEqual(got,'Text 1.')                  # 3 was ticked then unticked
        self.assertIn('[x] Option 1',screen)
        self.assertIn('1 of 3 chosen',screen)

    def test_several_come_back_in_catalog_order_not_typing_order(self):
        self.assertEqual(drive(['9','2','5',''],multi=3)[0],'Text 2. Text 5. Text 9.')

    def test_the_cap_is_enforced_and_recoverable(self):
        got,screen=drive(['1','2','4','5','2','7',''],multi=3)
        self.assertIn('that is the most you can pick',screen)   # 5 refused at the cap
        self.assertEqual(got,'Text 1. Text 4. Text 7.')         # untick 2, then 7 fits

    def test_enter_with_nothing_ticked_asks_again_rather_than_returning_empty(self):
        got,screen=drive(['','6',''],multi=2)
        self.assertEqual(got,'Text 6.')
        self.assertIn('nothing ticked yet',screen)

    def test_enter_with_nothing_ticked_points_at_the_none_option(self):
        got,screen=drive(['','23'],multi=2,opt_out_label='none at all')
        self.assertIs(got,wiz.SKIP_NONE)
        self.assertIn('or 23 for none at all',screen)

    def test_toggling_survives_paging(self):
        got,screen=drive(['2','n','15','p',''],multi=3)
        self.assertEqual(got,'Text 2. Text 15.')

    def test_single_choice_questions_show_no_checkboxes(self):
        self.assertNotIn('[ ]',drive(['1'])[1])
        self.assertIn('[ ]',drive(['1',''],multi=2)[1])

class RealQuestionTests(unittest.TestCase):
    """The same widget against the actual catalog, through the interview."""
    def test_marks_and_flaws_are_ticked_not_typed(self):
        keys=iter([])
        def run(answers,keys):
            with patch.dict(os.environ,{'COMPANION_PLAIN':'1'}),\
                 patch.object(wiz,'_tty',return_value=True),\
                 patch.object(wiz,'_color_ok',return_value=False),\
                 patch('builtins.input',side_effect=keyboard(keys,io.StringIO())),\
                 redirect_stdout(io.StringIO()):
                return wiz.interview('Nova','Alex','sharp',answers,quick=True)
        # every question answered from the answers dict except the two driven here
        base={k:1 for k in catalog.categories() if k not in ('marks','flaws')}
        base.update({'boundary':'non-sexual','visual':'set','age':30,'birthdate':'','pronoun_set':'she',
                     'texting_style':1,'pet_names':3,'wont_do':1,'human_boundary':1})
        out=run(base,['1','3','','2',''])
        self.assertEqual(out['flaws'].count('Nova'),2)   # two flaws ticked
        self.assertIn('close work',out['marks'])   # option 2 of the marks bank

    def test_every_multi_category_declares_a_sane_cap(self):
        for key in catalog.categories():
            cap=catalog.multi(key)
            self.assertTrue(cap==-1 or 0<=cap<=3,key)
            if cap:self.assertLess(cap,len(catalog.options(key,catalog.genders(key)[0])),key)


class ConsolePresentationTests(unittest.TestCase):
    def test_off_page_selection_is_named_until_it_is_unticked(self):
        _,screen=drive(['18','2','18',''],multi=3)
        self.assertIn('Selected: 18) Option 18',screen)
        self.assertIn('Selected: 2) Option 2; 18) Option 18',screen)
        self.assertIn('Selected: 2) Option 2',screen)

    def test_ascii_rendering_does_not_change_the_selected_value(self):
        value='Café — kept exactly'
        got,screen=drive(['1'],options=[('Café — label',value)],ascii_output=True)
        self.assertEqual(got,value);screen.encode('ascii')
        self.assertIn('[EDIT]',screen)

    def test_no_color_and_failed_vt_never_emit_escape_codes(self):
        import os
        for env,vt in [({'NO_COLOR':'1'},True),({},False)]:
            buf=io.StringIO()
            with patch.object(wiz,'_tty',return_value=True),patch.object(wiz,'_VT_OK',vt),patch.dict(os.environ,env),redirect_stdout(buf):
                wiz.clear();wiz.banner('Test','Preview')
            self.assertNotIn('\x1b',buf.getvalue())

    def test_long_option_labels_wrap_to_the_terminal_width(self):
        with patch.object(wiz,'width',return_value=32):
            _,screen=drive(['1'],options=[('A long appearance label that must wrap across several lines','value')])
        for line in screen.splitlines():
            if 'appearance' in line or 'several' in line:self.assertLessEqual(len(line),32)

    def test_legacy_windows_defaults_to_ascii_but_terminal_can_use_unicode(self):
        import os
        with patch.object(wiz,'_tty',return_value=True),patch.object(os,'name','nt'),patch.dict(os.environ,{},clear=True):
            self.assertTrue(wiz.ascii_mode())
            with patch.dict(os.environ,{'WT_SESSION':'test'}):self.assertFalse(wiz.ascii_mode())
            with patch.dict(os.environ,{'COMPANION_ASCII':'0'}):self.assertFalse(wiz.ascii_mode())

class InteractiveControlsTests(unittest.TestCase):
    def test_arrows_space_and_continue_select_multiple_options(self):
        from prompt_toolkit.application import create_app_session
        from prompt_toolkit.input import create_pipe_input
        from prompt_toolkit.output import DummyOutput
        with create_pipe_input() as pipe,create_app_session(input=pipe,output=DummyOutput()):
            pipe.send_text(' \x1b[B \r')
            result=wiz._interactive_choose('Traits',BANK,allow_write=True,allow_skip=True,
                opt_out_label='',note='',default=1,multi=-1,write_label='',write_hint='')
        self.assertEqual(result,'Text 1. Text 2.')

    def test_scrolling_reaches_options_beyond_the_old_page_boundary(self):
        from prompt_toolkit.application import create_app_session
        from prompt_toolkit.input import create_pipe_input
        from prompt_toolkit.output import DummyOutput
        with create_pipe_input() as pipe,create_app_session(input=pipe,output=DummyOutput()):
            pipe.send_text('\x1b[B'*17+' \r')
            result=wiz._interactive_choose('Wardrobe',BANK,allow_write=True,allow_skip=True,
                opt_out_label='',note='',default=1,multi=-1,write_label='',write_hint='')
        self.assertEqual(result,'Text 18.')

    def test_single_choice_enter_accepts_focused_row(self):
        from prompt_toolkit.application import create_app_session
        from prompt_toolkit.input import create_pipe_input
        from prompt_toolkit.output import DummyOutput
        with create_pipe_input() as pipe,create_app_session(input=pipe,output=DummyOutput()):
            pipe.send_text('\x1b[B\r')
            result=wiz._select_options('Choose', [('0','One'),('1','Two')],
                multi=0,selected=[],default=0,note='')
        self.assertEqual(result,['1'])

    def test_space_deselects_without_enter_reselecting(self):
        from prompt_toolkit.application import create_app_session
        from prompt_toolkit.input import create_pipe_input
        from prompt_toolkit.output import DummyOutput
        with create_pipe_input() as pipe,create_app_session(input=pipe,output=DummyOutput()):
            pipe.send_text(' \r')
            result=wiz._select_options('Choose', [('0','One'),('1','Two')],
                multi=-1,selected=['0','1'],default=0,note='')
        self.assertEqual(result,['1'])

    def test_custom_additions_preserve_selected_traits(self):
        with patch.object(wiz,'_select_options',side_effect=[['0','write'],['0','write'],['0','1']]) as picker,\
             patch.object(wiz,'_custom_entry',side_effect=['Collects maps.','Plays piano.']):
            result=wiz._interactive_choose('Traits',BANK,allow_write=True,allow_skip=True,
                opt_out_label='',note='',default=1,multi=-1,write_label='',write_hint='')
        self.assertEqual(picker.call_args.kwargs['selected'],['0'])
        self.assertEqual(result,'Text 1. Text 2. Collects maps. Plays piano.')

    def test_all_traits_can_be_selected_and_flaws_can_be_skipped(self):
        base = {k: 1 for k in catalog.categories()}
        base.update({'boundary': 'best-friend', 'visual': 'set', 'age': 30, 'birthdate': '', 'pronoun_set': 'she',
                     'texting_style': 1, 'pet_names': 3, 'wont_do': 1, 'human_boundary': 1})
        for key in ('core', 'flaws', 'likes'):
            rows = catalog.options(key)
            ans = dict(base, **{key: list(range(1, len(rows) + 1))})
            result = wiz.interview('Nova', 'Alex', 'warm', ans, quick=True)
            self.assertTrue(result[key])
        for skip in (wiz.SKIP_NONE, wiz.SKIP_EDIT):
            ans = dict(base, flaws=skip)
            result = wiz.interview('Nova', 'Alex', 'warm', ans, quick=True)
            self.assertIn('fallible', result['flaws'])

if __name__ == '__main__':
    unittest.main()
