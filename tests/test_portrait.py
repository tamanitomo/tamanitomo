"""The image identity block: the same person, described the same way, every time."""
import datetime as dt
import json
import pathlib,sys,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'kit/scripts'))
import companion_config as cc
import companion_presence as presence
import companion_portrait as portrait
import companion_render as cr
sys.path.insert(0,str(ROOT))

TZ=dt.timezone.utc

class PromptTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=pathlib.Path(self.tmp.name)
        self.c=cc.Companion(agent='Nova',human='Alex',hermes_root=root/'h',vault=root/'v',
                            soul_in_vault=False,image_style='anime-modern')
        self.c.soul.parent.mkdir(parents=True,exist_ok=True)
        interview={'visual':'set','age':26,'build':'Nova has an athletic build.',
                   'hair_color':'Her hair is dark brown.','eyes':'Nova has grey eyes.'}
        from kit.cli.common import mapping
        self.c.soul.write_text(cr.render_template('SOUL.md.tmpl',
            cr.mapping_for(self.c,'warm','anime-modern',interview={
                'physical':'Nova is a 26-year-old adult. Her hair is dark brown. Nova has grey eyes.'})),
            encoding='utf-8')
        self.now=dt.datetime(2026,9,10,9,0,tzinfo=TZ)

    def state(self):
        presence.update_wardrobe(self.c,[{'id':'sweater','description':'grey wool sweater','use':'day'}])
        presence.update(self.c,{'previous_id':None,'outfit':['sweater'],'location':'the kitchen',
            'activity':'making coffee','mood':'slow','care':[],'transition':'','text':'Coffee.'},self.now)

    def test_no_state_means_no_photo_rather_than_an_invented_scene(self):
        result=portrait.compile_prompt(self.c)
        self.assertFalse(result['ready'])
        self.assertIn('invented for the camera',result['reason'])

    def test_the_prompt_is_identity_then_scene_then_style(self):
        self.state()
        result=portrait.compile_prompt(self.c)
        self.assertTrue(result['ready'])
        prompt=result['prompt']
        self.assertLess(prompt.index('dark brown'),prompt.index('making coffee'))
        self.assertLess(prompt.index('making coffee'),prompt.index('anime'))
        self.assertIn('grey wool sweater',prompt)

    def test_the_identity_half_does_not_change_when_the_scene_does(self):
        self.state()
        first=portrait.compile_prompt(self.c)
        later=presence.update(self.c,{'previous_id':presence.current(self.c)['id'],
            'outfit':['sweater'],'location':'the garden','activity':'reading',
            'mood':'slow','care':[],'transition':'Went outside with the book.','text':'Outside.'},
            self.now+dt.timedelta(hours=1))
        second=portrait.compile_prompt(self.c)
        self.assertEqual(first['identity'],second['identity'])
        self.assertNotEqual(first['scene'],second['scene'])

    def test_no_markdown_leaks_into_the_prompt(self):
        self.state()
        prompt=portrait.compile_prompt(self.c)['prompt']
        self.assertNotIn('#',prompt)
        self.assertNotIn('<!--',prompt)
        self.assertNotIn('✎',prompt)

    def test_instructions_to_her_are_not_part_of_her_face(self):
        """The section ends by telling her how to maintain a wardrobe, with the
        command that does it. An image generator was being handed that."""
        self.state()
        prompt=portrait.compile_prompt(self.c)['prompt']
        self.assertNotIn('`',prompt)
        self.assertNotIn('companion_presence.py',prompt)
        self.assertNotIn('Clothing examples',prompt)
        self.assertIn('dark brown',prompt)

    def test_a_soul_written_before_the_marker_existed_is_still_cut(self):
        self.state()
        import companion_identity as identity
        body=('Nova is a 26-year-old adult.\n\nHer hair is dark brown.\n\n'
              'Clothing examples seed a varied wardrobe, not a permanent outfit. Maintain your '
              'closet and current\noutfit through `/usr/bin/python /kit/companion_presence.py`; '
              'choose clothes for the occasion.')
        identity.replace(self.c,'appearance',body)
        prompt=portrait.compile_prompt(self.c)['prompt']
        self.assertNotIn('companion_presence.py',prompt)
        # The sentence above the command belongs to the command.
        self.assertNotIn('Clothing examples',prompt)
        self.assertIn('dark brown',prompt)

    def test_a_reference_portrait_is_stored_but_only_offered_on_request(self):
        self.state()
        self.assertIsNone(portrait.compile_prompt(self.c)['reference_image'])
        from PIL import Image
        import io
        buf=io.BytesIO();Image.new('RGB',(8,8),(1,2,3)).save(buf,'PNG')
        source=pathlib.Path(self.tmp.name)/'face.png';source.write_bytes(buf.getvalue())
        saved=portrait.save_reference(self.c,source)
        self.assertTrue(pathlib.Path(saved['saved']).is_file())
        result=portrait.compile_prompt(self.c)
        self.assertIsNone(result['reference_image'])
        explicit=portrait.compile_prompt(self.c,use_reference=True)
        self.assertEqual(explicit['reference_image'],str(portrait.portrait_path(self.c)))

    def test_an_extra_instruction_sits_between_the_scene_and_the_style(self):
        self.state()
        prompt=portrait.compile_prompt(self.c,'seen from the doorway')['prompt']
        self.assertLess(prompt.index('making coffee'),prompt.index('seen from the doorway'))
        self.assertLess(prompt.index('seen from the doorway'),prompt.index('anime'))


if __name__=='__main__':unittest.main()


class VoiceTests(unittest.TestCase):
    """Voice notes go through the same gate as everything else, and a cloned
    voice is somebody's actual voice."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=pathlib.Path(self.tmp.name)
        self.c=cc.Companion(agent='Nova',human='Alex',hermes_root=root/'h',vault=root/'v',
                            timezone='UTC')
        self.c.home.mkdir(parents=True,exist_ok=True)
        self.c.life.mkdir(parents=True,exist_ok=True)
        import companion_voice
        self.voice=companion_voice

    def config(self,text):
        (self.c.home/'config.yaml').write_text(text,encoding='utf-8')

    def audio(self):
        path=pathlib.Path(self.tmp.name)/'note.mp3';path.write_bytes(b'ID3fake');return path

    def test_no_tts_provider_is_said_plainly_not_guessed_at(self):
        self.config('model:\n  default: x\n')
        state=self.voice.settings(self.c)
        self.assertFalse(state['configured'])
        self.assertIn('deliberately does not choose one for you',state['note'])

    def test_the_voice_is_whatever_hermes_already_has(self):
        self.config('tts:\n  provider: edge\n  edge:\n    voice: en-GB-SoniaNeural\n')
        state=self.voice.settings(self.c)
        self.assertEqual(state['provider'],'edge')
        self.assertEqual(state['voice'],'en-GB-SoniaNeural')

    def test_a_note_is_queued_with_its_words_beside_the_audio(self):
        self.config('tts:\n  provider: edge\n  edge:\n    voice: x\n')
        import companion_outbox as outbox
        result=self.voice.queue_note(self.c,'you left your keys here',str(self.audio()))
        self.assertTrue(result['ok'])
        entry=outbox.fold(self.c)[0]
        self.assertEqual(entry['content'],'voice')
        self.assertEqual(entry['body'],'you left your keys here')

    def test_missing_audio_says_how_to_make_it_rather_than_failing_silently(self):
        self.config('tts:\n  provider: edge\n')
        result=self.voice.queue_note(self.c,'hello','/nowhere/at/all.mp3')
        self.assertFalse(result['ok'])
        self.assertIn('text_to_speech',result['reason'])

    def test_cloning_a_voice_requires_saying_it_is_yours_to_use(self):
        self.config('tts:\n  provider: edge\n')
        with self.assertRaisesRegex(ValueError,'permission'):
            self.voice.set_clone(self.c,str(self.audio()),'this is what I said',confirmed=False)

    def test_a_clone_needs_the_transcript_or_it_comes_out_wrong(self):
        self.config('tts:\n  provider: edge\n')
        with self.assertRaisesRegex(ValueError,'transcript'):
            self.voice.set_clone(self.c,str(self.audio()),'',confirmed=True)

    def test_a_confirmed_clone_writes_hermes_own_keys(self):
        self.config('tts:\n  provider: edge\n')
        result=self.voice.set_clone(self.c,str(self.audio()),'this is what I said',confirmed=True)
        import yaml
        cfg=yaml.safe_load((self.c.home/'config.yaml').read_text())
        self.assertEqual(cfg['tts']['provider'],'neutts')
        self.assertEqual(cfg['tts']['neutts']['ref_text'],'this is what I said')
        self.assertTrue(pathlib.Path(cfg['tts']['neutts']['ref_audio']).is_file())
        self.assertTrue(str(self.c.data) in cfg['tts']['neutts']['ref_audio'])
