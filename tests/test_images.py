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


class UrlImportTests(unittest.TestCase):
    """Civitai's public API returns an empty `meta` to anonymous callers, so the
    import reads the image page instead, which still carries it."""

    PAGE = ('<html><script id="__NEXT_DATA__" type="application/json">'
            '{"props":{"pageProps":{"q":{"state":{"data":{"meta":'
            '{"prompt":"a seaside inn","negativePrompt":"lowres","steps":25,'
            '"cfgScale":7,"sampler":"Euler a","seed":3269595310,"Size":"896x1152"}'
            '}}}}}}</script></html>')

    def test_an_image_page_yields_its_settings(self):
        import companion_image_import as importer
        out = importer.read_image_url('https://civitai.com/images/12097475',
                                      fetch=lambda url: self.PAGE)
        self.assertEqual(out['found']['source'], 'Civitai image page')
        self.assertEqual(out['preset']['steps'], 25)
        self.assertEqual(out['preset']['cfg'], 7.0)
        self.assertEqual((out['preset']['width'], out['preset']['height']), (896, 1152))
        self.assertEqual(out['preset']['negative'], 'lowres')
        # A prompt is not a graph: it needs a checkpoint before it can serve a lane.
        self.assertTrue(out['preset']['incomplete'])

    def test_civitai_red_is_the_same_site(self):
        import companion_image_import as importer
        out = importer.read_image_url('https://civitai.red/images/12097475',
                                      fetch=lambda url: self.PAGE)
        self.assertEqual(out['found']['image_id'], '12097475')

    def test_a_link_that_is_not_an_image_page_is_refused(self):
        import companion_image_import as importer
        for bad in ('https://civitai.com/models/123', 'https://example.com/x', 'nonsense', ''):
            with self.assertRaises(ValueError):
                importer.read_image_url(bad, fetch=lambda url: self.PAGE)

    def test_a_page_without_settings_says_so_rather_than_inventing_them(self):
        import companion_image_import as importer
        with self.assertRaises(ValueError):
            importer.read_image_url('https://civitai.com/images/1', fetch=lambda url: '<html></html>')


class RecommendationTests(unittest.TestCase):
    def test_a_family_is_recognised_from_the_checkpoint_name(self):
        import companion_image_import as importer
        self.assertEqual(importer.family_of('illustriousXL_v01.safetensors'), 'Illustrious')
        self.assertEqual(importer.family_of('ponyDiffusionV6XL.safetensors'), 'Pony')
        self.assertEqual(importer.family_of('flux1-dev.safetensors'), 'Flux')
        self.assertEqual(importer.family_of('cyberrealisticXL_v10.safetensors'), 'SDXL')

    def test_an_unrecognised_name_offers_nothing_rather_than_guessing(self):
        import companion_image_import as importer
        self.assertEqual(importer.family_of('someRandomMerge.safetensors'), '')
        self.assertEqual(importer.recommendations('someRandomMerge.safetensors'), {'family': ''})

    def test_a_recognised_family_carries_usable_ranges(self):
        import companion_image_import as importer
        advice = importer.recommendations('illustriousXL_v01.safetensors')
        self.assertEqual(advice['family'], 'Illustrious')
        low, high = advice['steps']
        self.assertLess(low, high)
        self.assertTrue(all(k in advice for k in ('steps', 'cfg', 'clip_skip', 'size')))


class ModelScanTests(unittest.TestCase):
    """Reading what a model file says it was trained for, from its own header."""

    def _safetensors(self, metadata):
        import struct
        header = json.dumps({'__metadata__': metadata}).encode()
        return struct.pack('<Q', len(header)) + header + b'\0' * 16

    def test_a_header_names_the_architecture(self):
        import companion_model_scan as scan
        path = pathlib.Path(self.tmp.name) / 'a.safetensors'
        path.write_bytes(self._safetensors({'ss_base_model_version': 'sdxl_base_v1-0'}))
        self.assertEqual(scan.describe(str(path))['family'], 'SDXL')

    def test_a_file_with_no_header_is_unknown_not_guessed(self):
        import companion_model_scan as scan
        path = pathlib.Path(self.tmp.name) / 'b.safetensors'
        path.write_bytes(b'not a safetensors file at all')
        result = scan.describe(str(path))
        self.assertEqual(result['family'], '')
        self.assertEqual(result['source'], 'no header')

    def test_a_header_without_a_base_model_says_which_it_was(self):
        import companion_model_scan as scan
        path = pathlib.Path(self.tmp.name) / 'c.safetensors'
        path.write_bytes(self._safetensors({'ss_network_dim': '32'}))
        result = scan.describe(str(path))
        self.assertEqual(result['family'], '')
        self.assertEqual(result['source'], 'header had no base model')

    def test_nested_models_keep_the_name_comfyui_uses(self):
        """ComfyUI names a nested model by its path under the folder root, so the
        scan has to key by the same thing or nothing matches up."""
        import companion_model_scan as scan
        root = pathlib.Path(self.tmp.name) / 'loras'
        (root / 'style').mkdir(parents=True)
        (root / 'style' / 'd.safetensors').write_bytes(
            self._safetensors({'ss_base_model_version': 'flux'}))
        found = scan.scan([str(root)])
        self.assertIn('style/d.safetensors', found)
        self.assertEqual(found['style/d.safetensors']['family'], 'Flux')

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)


class MediaCacheTests(unittest.TestCase):
    """The person's own pictures should be fetched once, not on every page."""

    def setUp(self):
        from tests import test_workspace as workspace
        self.f = workspace.WorkspaceTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.rel = 'photos/cached.png'
        target = self.f.c.data / self.rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'\x89PNG\r\n\x1a\n' + b'0' * 64)

    def get(self, **headers):
        return self.f.client.get('/api/content/file', params={'profile': 'nova', 'path': self.rel},
                                 headers={**self.f.headers, **headers})

    def test_a_picture_is_cacheable_and_carries_its_identity(self):
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertIn('private', response.headers['cache-control'])
        self.assertIn('max-age', response.headers['cache-control'])
        self.assertTrue(response.headers.get('etag'))

    def test_an_unchanged_picture_is_answered_without_its_bytes(self):
        tag = self.get().headers['etag']
        again = self.get(**{'If-None-Match': tag})
        self.assertEqual(again.status_code, 304)
        self.assertEqual(again.content, b'')

    def test_a_replaced_picture_is_fetched_again(self):
        """The tag is the file's identity, so rewriting it must invalidate."""
        import os, time
        tag = self.get().headers['etag']
        target = self.f.c.data / self.rel
        target.write_bytes(b'\x89PNG\r\n\x1a\n' + b'1' * 128)
        os.utime(target, (time.time() + 5, time.time() + 5))
        self.assertEqual(self.get(**{'If-None-Match': tag}).status_code, 200)

    def test_the_api_itself_is_still_never_cached(self):
        response = self.f.client.get('/api/overview', params={'profile': 'nova'}, headers=self.f.headers)
        self.assertEqual(response.headers.get('cache-control'), 'no-store')
