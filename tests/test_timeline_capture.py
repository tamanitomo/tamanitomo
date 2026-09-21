"""Scripted capture preserves claims, source provenance and failure state."""
import datetime as dt
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'kit/scripts'))
import companion_config as cc
import companion_presence as presence
import companion_timeline as timeline
import companion_timeline_capture as worker


class CaptureTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=pathlib.Path(temp.name)
        self.c=cc.Companion(hermes_root=self.root/'home',vault=self.root/'vault',
                            image_timeline=True,image_style='realistic')
        self.now=dt.datetime(2026,9,12,12,2,tzinfo=dt.timezone.utc)
        presence.update_wardrobe(self.c,[{'id':'tee','description':'green tee','use':'day'}])
        self.state={'previous_id':None,'outfit':['tee'],'location':'kitchen',
                    'activity':'making lunch','mood':'calm','text':'Lunch.'}
        presence.update(self.c,self.state,self.now)
        self.image=self.root/'generated.png';Image.new('RGB',(16,16),'green').save(self.image)

    def test_capture_freezes_scene_and_duplicate_tick_never_generates_twice(self):
        def generate(c,preset,category,overrides):
            self.assertIn('making lunch',overrides['scene'])
            self.assertEqual(overrides['wardrobe'],'green tee')
            old=presence.current(c)
            presence.update(c,{**self.state,'previous_id':old['id'],'id':'later',
                               'activity':'washing dishes','transition':'Finished lunch.'},
                            self.now+dt.timedelta(seconds=1))
            return {'path':str(self.image),'provider':'fixture-generator'}
        with patch.object(worker.media,'effective',return_value={'default_preset':'saved'}), \
             patch.object(worker.media,'generate',side_effect=generate) as gen:
            result=worker.capture(self.c,self.now)
            self.assertEqual(result['status'],'saved')
            self.assertEqual(pathlib.Path(result['path']).read_bytes(),self.image.read_bytes())
            row=json.loads(timeline.capture_path(self.c,result['capture_id']).read_text())
            self.assertEqual(row['scene']['state']['activity'],'making lunch')
            self.assertEqual(row['provider'],'fixture-generator')
            self.assertEqual(worker.capture(self.c,self.now+dt.timedelta(seconds=2))['status'],'skipped')
            self.assertEqual(gen.call_count,1)

    def test_generator_failure_is_durable_and_cannot_be_retried_by_next_tick(self):
        with patch.object(worker.media,'effective',return_value={'default_preset':'saved'}), \
             patch.object(worker.media,'generate',side_effect=ValueError('review unavailable')) as gen:
            with self.assertRaisesRegex(ValueError,'review unavailable'):
                worker.capture(self.c,self.now)
            row=next(timeline.records(self.c))[1]
            self.assertEqual(row['status'],'failed')
            self.assertIn('review unavailable',row['error'])
            self.assertEqual(worker.capture(self.c,self.now)['status'],'skipped')
            self.assertEqual(gen.call_count,1)

    def test_capture_persists_dual_prompts_and_omits_outerwear_when_bathing(self):
        import companion_portrait as pt
        curr=presence.current(self.c)
        bathing_state={'id':'bathing-state','previous_id':curr['id'],'outfit':['bathing'],'location':'bathroom',
                       'activity':'under a warm shower','mood':'relaxed','text':'Showering.',
                       'transition':'Stepping into the bathroom for a shower.'}
        presence.update(self.c,bathing_state,self.now+dt.timedelta(minutes=30))
        overrides=pt.recorded_overrides(self.c)
        self.assertNotIn('green tee',overrides.get('wardrobe',''))

        def generate(c,preset,category,overrides):
            return {'path':str(self.image),'provider':'dual-prompt-generator',
                    'prompts':{'prose':'warm steam in bathroom','structured':'steamy bathroom, natural light'}}

        with patch.object(worker.media,'effective',return_value={'default_preset':'saved'}), \
             patch.object(worker.media,'generate',side_effect=generate):
            result=worker.capture(self.c,self.now+dt.timedelta(minutes=30))
            self.assertEqual(result['status'],'saved')
            row=json.loads(timeline.capture_path(self.c,result['capture_id']).read_text())
            self.assertEqual(row['prompts'],{'prose':'warm steam in bathroom','structured':'steamy bathroom, natural light'})


if __name__=='__main__':unittest.main()
