"""Reading a workflow out of somebody else's picture, and saying what is missing."""
import io
import json
import pathlib
import sys
import unittest
from PIL import Image
from PIL.PngImagePlugin import PngInfo
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'kit/scripts'))
import companion_image_import as imp


def png(chunks,size=(64,64)):
    meta=PngInfo()
    for k,v in chunks.items():meta.add_text(k,v)
    buf=io.BytesIO()
    Image.new('RGB',size,(20,20,20)).save(buf,'PNG',pnginfo=meta)
    return buf.getvalue()


# A node pack that fuses loader, prompt and sampler into three nodes of its own,
# which is the shape that used to come back empty.
PACK_GRAPH={
 '10':{'class_type':'SOLoaderCoreEngineStudio','inputs':{
     'diffusion_model':'BIG MODEL_FP8.safetensors','main_enabled':True,
     'main_lora':'chars\\\\someone\\\\someone_epoch_09.safetensors','main_strength':1.0}},
 '11':{'class_type':'SOPromptLogEngineStudio','inputs':{
     'prompt_source':'manual','manual_prompt':'photo of a woman leaning on a fence at a ranch',
     'prefix_enabled':False}},
 '12':{'class_type':'SOGenerationPipelineStudio','inputs':{
     'clip_name':'qwen3vl_4b_fp8_scaled.safetensors','vae_name':'qwen_image_vae.safetensors',
     'custom_width':1440,'custom_height':1920,'steps':9,'cfg':1.0,'sampler_name':'euler',
     'seed_value':649526996593298,'model':['10',0],'positive_text':['11',0]}},
 '13':{'class_type':'SOOutputBuilderSaveStudio','inputs':{
     'extension':'png','saved_path':'output\\\\run\\\\prior_render_00001.png','samples':['12',0]}},
}

STOCK_GRAPH={
 '1':{'class_type':'CheckpointLoaderSimple','inputs':{'ckpt_name':'stock.safetensors'}},
 '2':{'class_type':'CLIPTextEncode','inputs':{'text':'a lighthouse at dusk','clip':['1',1]}},
 '3':{'class_type':'CLIPTextEncode','inputs':{'text':'blurry','clip':['1',1]}},
 '4':{'class_type':'EmptyLatentImage','inputs':{'width':832,'height':1216,'batch_size':1}},
 '5':{'class_type':'KSampler','inputs':{'seed':7,'steps':24,'cfg':6.5,'model':['1',0],
      'positive':['2',0],'negative':['3',0],'latent_image':['4',0]}},
}


class CustomNodeGraphTests(unittest.TestCase):
    """The reader knew four stock class names and nothing else."""
    def setUp(self):
        self.result=imp.read_image_workflow(png({'prompt':json.dumps(PACK_GRAPH)}),'pack.png')
        self.found=self.result['found'];self.preset=self.result['preset']

    def test_the_weights_are_found_through_the_packs_own_loader(self):
        self.assertEqual(self.found['checkpoints'],['BIG MODEL_FP8.safetensors'])
        self.assertEqual(self.found['loras'],['someone_epoch_09.safetensors'])
        self.assertEqual(self.found['vaes'],['qwen_image_vae.safetensors'])

    def test_a_remembered_output_path_is_not_mistaken_for_a_model(self):
        every=sum([self.found.get(k) or [] for k in ('checkpoints','loras','vaes','clips')],[])
        self.assertFalse([x for x in every if x.endswith('.png')])

    def test_the_numbers_come_off_the_packs_sampler(self):
        for key,value in (('steps',9),('cfg',1.0),('width',1440),('height',1920)):
            self.assertEqual(self.found.get(key),value,key)

    def test_the_prompt_box_is_wired(self):
        self.assertEqual(self.preset['mappings']['prompt'],['11','manual_prompt'])

    def test_it_is_not_called_incomplete_merely_for_being_unfamiliar(self):
        self.assertFalse(self.preset['incomplete'])

    def test_the_custom_nodes_are_named_so_they_can_be_installed(self):
        self.assertEqual(self.found['custom_nodes'],sorted(n['class_type'] for n in PACK_GRAPH.values()))


class StockGraphTests(unittest.TestCase):
    """The stock path has to keep reading exactly as it did."""
    def setUp(self):
        self.result=imp.read_image_workflow(png({'prompt':json.dumps(STOCK_GRAPH)}),'stock.png')

    def test_stock_nodes_are_read_as_before(self):
        preset=self.result['preset']
        self.assertEqual(preset['mappings']['prompt'],['2','text'])
        self.assertEqual(preset['mappings']['negative'],['3','text'])
        self.assertEqual(preset['mappings']['width'],['4','width'])
        self.assertEqual(self.result['found']['checkpoints'],['stock.safetensors'])
        self.assertFalse(preset['incomplete'])

    def test_a_stock_graph_needs_no_node_pack(self):
        self.assertNotIn('custom_nodes',self.result['found'])


class NonFiniteTests(unittest.TestCase):
    """ComfyUI stamps is_changed: [NaN] onto the nodes it saves."""
    def test_a_graph_carrying_nan_survives_being_sent_on(self):
        graph=json.loads(json.dumps(STOCK_GRAPH))
        graph['5']['is_changed']=[float('nan')]
        result=imp.read_image_workflow(png({'prompt':json.dumps(graph)}),'nan.png')
        json.dumps(result,allow_nan=False)   # what the response encoder does
        self.assertIsNone(result['preset']['workflow']['5']['is_changed'][0])


class FitAdviceTests(unittest.TestCase):
    CARD=8*1024**3

    def test_a_model_far_over_the_card_says_so_and_says_what_to_do(self):
        text=imp.describe_fit(self.CARD,20*1024**3,'BIG MODEL_FP8.safetensors')
        self.assertIn('will not fit',text)
        self.assertIn('GGUF',text)

    def test_a_comfortable_model_does_not_lecture(self):
        text=imp.describe_fit(self.CARD,3*1024**3,'small.safetensors')
        self.assertIn('room to spare',text)
        self.assertNotIn('GGUF',text)

    def test_a_tight_fit_is_called_tight_rather_than_impossible(self):
        text=imp.describe_fit(self.CARD,int(6.5*1024**3),'mid.safetensors')
        self.assertIn('may load',text)

    def test_nobody_is_told_to_quantise_a_quantisation(self):
        self.assertNotIn('GGUF',imp.describe_fit(self.CARD,int(7.6*1024**3),'model-Q4_K_M.gguf'))

    def test_an_unknown_size_still_gives_the_card_and_the_advice(self):
        text=imp.describe_fit(self.CARD,None,'unknown.safetensors')
        self.assertIn('8.0 GB',text);self.assertIn('GGUF',text)

    def test_an_unknown_card_says_nothing_rather_than_guessing(self):
        self.assertEqual(imp.describe_fit(0,20*1024**3,'x.safetensors'),'')


class CivitaiMirrorTests(unittest.TestCase):
    """civitai.red serves the same ids and refuses an ordinary client."""
    PAGE=('<script id="__NEXT_DATA__" type="application/json">'
          +json.dumps({'a':{'prompt':'a lighthouse','steps':24,'cfgScale':6.5,'seed':11,
                            'Size':'832x1216','Model':'stock'}})+'</script>')

    def test_a_red_link_is_read_from_the_com_mirror(self):
        asked=[]
        def fetch(url):
            asked.append(url)
            if 'civitai.red' in url:raise OSError('403 Forbidden')
            return self.PAGE
        result=imp.read_image_url('https://civitai.red/images/140760013',
                                  fetch=fetch,fetch_json=lambda url:{})
        self.assertEqual(asked[0],'https://civitai.com/images/140760013')
        self.assertEqual(result['found']['image_id'],'140760013')
        self.assertEqual(result['found']['steps'],24)

    def test_the_address_as_given_is_still_tried_if_the_mirror_fails(self):
        asked=[]
        def fetch(url):
            asked.append(url)
            if 'civitai.com' in url:raise OSError('blocked here')
            return self.PAGE
        result=imp.read_image_url('https://civitai.red/images/140760013',
                                  fetch=fetch,fetch_json=lambda url:{})
        self.assertEqual(asked,['https://civitai.com/images/140760013',
                                'https://civitai.red/images/140760013'])
        self.assertEqual(result['found']['image_id'],'140760013')

    def test_both_failing_still_reports_the_link(self):
        def fetch(url):raise OSError('no')
        with self.assertRaises(ValueError) as caught:
            imp.read_image_url('https://civitai.red/images/1',fetch=fetch,fetch_json=lambda u:{})
        self.assertIn('Could not reach',str(caught.exception))


if __name__=='__main__':unittest.main()


class HostGapTests(unittest.TestCase):
    """What the target ComfyUI is missing decides whether this can run at all."""
    def setUp(self):
        sys.path.insert(0,str(ROOT))
        import companion_media as media
        self.media=media
        self.real=media.request_json
        self.addCleanup(setattr,media,'request_json',self.real)

    def serve(self,classes,installed,vram=8*1024**3):
        def fake(url,payload=None,headers=None):
            if url.endswith('/object_info'):
                return {c:{'input':{'required':{'x':[list(installed)]}}} for c in classes}
            if url.endswith('/system_stats'):
                return {'devices':[{'vram_total':vram}]}
            raise AssertionError(url)
        self.media.request_json=fake

    def build(self):
        import tempfile, pathlib as pl
        from fastapi.testclient import TestClient
        from kit.app.server import build
        return TestClient(build(home=pl.Path(tempfile.mkdtemp())))

    def png_of(self,graph):
        return png({'prompt':json.dumps(graph)})

    def test_a_graph_needing_absent_nodes_is_not_offered_as_renderable(self):
        self.serve({'KSampler','CLIPTextEncode','EmptyLatentImage','CheckpointLoaderSimple'},
                   {'stock.safetensors'})
        r=self.build().post('/api/images/import',content=self.png_of(PACK_GRAPH),
                            headers={'x-image-name':'pack.png'})
        self.assertEqual(r.status_code,200)
        body=r.json()
        self.assertTrue(body['preset']['incomplete'])
        self.assertIn('SOLoaderCoreEngineStudio',body['found']['missing_nodes'])
        self.assertTrue(any('Not installed in this ComfyUI' in n for n in body['notes']))

    def test_a_graph_this_comfyui_can_run_is_left_alone(self):
        self.serve({'KSampler','CLIPTextEncode','EmptyLatentImage','CheckpointLoaderSimple',
                    'VAEDecode','SaveImage'},{'stock.safetensors'})
        body=self.build().post('/api/images/import',content=self.png_of(STOCK_GRAPH),
                               headers={'x-image-name':'stock.png'}).json()
        self.assertFalse(body['preset']['incomplete'])
        # No lecture about VRAM for weights that are already sitting there.
        self.assertFalse([n for n in body['notes'] if 'VRAM' in n],body['notes'])

    def test_a_model_still_to_be_downloaded_does_get_the_vram_warning(self):
        self.serve({'KSampler','CLIPTextEncode','EmptyLatentImage','CheckpointLoaderSimple',
                    'VAEDecode','SaveImage'},{'somethingelse.safetensors'})
        body=self.build().post('/api/images/import',content=self.png_of(STOCK_GRAPH),
                               headers={'x-image-name':'stock.png'}).json()
        self.assertIn('stock.safetensors',body['found']['missing_models'])
        self.assertTrue([n for n in body['notes'] if 'VRAM' in n])
