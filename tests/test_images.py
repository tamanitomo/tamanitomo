"""A workflow can be rendered before it is saved.

The point of a test render is to judge a workflow before committing to it, so
the draft has to travel with the request rather than being looked up by an id
that does not exist in the library yet.
"""
import copy,json,pathlib,sys,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'kit/scripts'))
import companion_config as cc
import companion_media as media

class DraftRenderTests(unittest.TestCase):
    def setUp(self):
        from tests import test_workspace as workspace
        self.f=workspace.WorkspaceTests();self.f.setUp();self.addCleanup(self.f.doCleanups)

    def _preset(self):
        return {'id':'saved-one','name':'Saved','provider':'comfyui','category':'anime',
                'endpoint':'http://127.0.0.1:8188','parts':{'quality':'crisp'},
                'workflow':{'1':{'class_type':'CLIPTextEncode','inputs':{'text':''}}},
                'mappings':{'prompt':['1','text']},'width':832,'height':1216,
                'steps':18,'cfg':5,'seed':-1,'negative':''}

    def test_a_draft_that_is_not_in_the_library_still_compiles(self):
        c=self.f.c
        draft=copy.deepcopy(self._preset())
        draft['id']='never-saved';draft['name']='Unsaved draft'
        out=media.compile(c,'','anime',None,draft)
        self.assertEqual(out['preset']['name'],'Unsaved draft')
        self.assertIn('crisp',out['prompt'])

    def test_an_incomplete_draft_is_refused_rather_than_half_rendered(self):
        with self.assertRaises(ValueError):
            media.compile(self.f.c,'','anime',None,{'name':'no provider'})
        with self.assertRaises(ValueError):
            media.compile(self.f.c,'','anime',None,'not a dict')

if __name__=='__main__':unittest.main()


class ImportTests(unittest.TestCase):
    """Reading a workflow back out of a picture, in both dialects and neither."""

    def _png(self, **text):
        import io
        from PIL import Image
        from PIL.PngImagePlugin import PngInfo
        meta = PngInfo()
        for k, v in text.items():
            meta.add_text(k, v)
        buf = io.BytesIO()
        Image.new('RGB', (64, 64)).save(buf, 'PNG', pnginfo=meta)
        return buf.getvalue()

    def test_a_comfyui_render_carries_its_whole_graph(self):
        import companion_image_import as importer
        graph = {
            '1': {'class_type': 'CheckpointLoaderSimple', 'inputs': {'ckpt_name': 'walnut.safetensors'}},
            '2': {'class_type': 'LoraLoader', 'inputs': {'lora_name': 'style.safetensors',
                                                          'strength_model': 0.7, 'strength_clip': 0.7}},
            '3': {'class_type': 'CLIPTextEncode', 'inputs': {'text': 'a lighthouse'}},
            '4': {'class_type': 'CLIPTextEncode', 'inputs': {'text': 'blurry'}},
            '5': {'class_type': 'EmptyLatentImage', 'inputs': {'width': 832, 'height': 1216}},
            '6': {'class_type': 'KSampler', 'inputs': {'steps': 24, 'cfg': 6.0, 'seed': 42,
                                                        'positive': ['3', 0], 'negative': ['4', 0]}},
        }
        out = importer.read_image_workflow(self._png(prompt=json.dumps(graph)), 'render.png')
        self.assertEqual(out['found']['source'], 'ComfyUI graph')
        self.assertEqual(out['found']['checkpoints'], ['walnut.safetensors'])
        self.assertEqual(out['found']['loras'], ['style.safetensors'])
        self.assertEqual((out['preset']['steps'], out['preset']['cfg'], out['preset']['seed']), (24, 6.0, 42))
        # The sampler names its own conditioning, so these are read rather than guessed.
        self.assertEqual(out['preset']['mappings']['prompt'], ['3', 'text'])
        self.assertEqual(out['preset']['mappings']['negative'], ['4', 'text'])
        self.assertFalse(out['preset']['incomplete'])

    def test_a_civitai_download_gives_settings_but_not_a_graph(self):
        import companion_image_import as importer
        params = ('a seaside inn\nNegative prompt: lowres, watermark\n'
                  'Steps: 30, Sampler: DPM++ 2M, CFG scale: 7.5, Seed: 998877, Size: 832x1216, '
                  'Model: illustriousXL_v01, Lora hashes: "YellowThing: ab12, GENESIS: cd34"')
        out = importer.read_image_workflow(self._png(parameters=params), 'civitai.png')
        self.assertIn('Automatic1111', out['found']['source'])
        self.assertEqual(out['preset']['steps'], 30)
        self.assertEqual(out['preset']['cfg'], 7.5)
        self.assertEqual((out['preset']['width'], out['preset']['height']), (832, 1216))
        self.assertEqual(out['preset']['negative'], 'lowres, watermark')
        self.assertEqual(out['found']['loras'], ['YellowThing', 'GENESIS'])
        # Named, not chosen: the model may not exist on this ComfyUI.
        self.assertTrue(out['preset']['incomplete'])

    def test_a_picture_with_nothing_in_it_still_yields_a_draft(self):
        import companion_image_import as importer
        out = importer.read_image_workflow(self._png(), 'screenshot.png')
        self.assertEqual(out['found']['source'], 'nothing recoverable')
        self.assertTrue(out['preset']['incomplete'])
        self.assertTrue(out['notes'])

    def test_a_file_that_is_not_an_image_is_refused(self):
        import companion_image_import as importer
        with self.assertRaises(ValueError):
            importer.read_image_workflow(b'not an image at all', 'x.png')
