"""Deletion isolation, privacy defaults and actual-image review gates."""
import sys,unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parents[1]/'kit/scripts')]
import companion_config as cc
import companion_media as media
import companion_media_review as review
from kit.app.content import catalog
from kit.app.server import build
from fastapi.testclient import TestClient
from PIL import Image

class MediaReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);root=Path(self.temp.name)
        self.c=cc.Companion(profile='test',agent='Test',vault=root/'vault',hermes_root=root/'hermes',context_mode='fixed')
        self.c.home.mkdir(parents=True);self.c.soul_dir.mkdir(parents=True);self.c.save()
        self.path=self.c.data/'creations/image-studio/a.png';self.path.parent.mkdir(parents=True);Image.new('RGB',(8,8),'blue').save(self.path)
        self.client=TestClient(build(self.c.home,token='secret',state_dir=root/'state'));self.addCleanup(self.client.close)
    def post(self,url,data):return self.client.post('/api/'+url,json=data,headers={'x-companion-token':'secret'})
    def test_unknown_is_distinct_from_nsfw_and_ratings_obey_setting(self):
        self.assertTrue(catalog(self.c)['items'][0]['blur'])
        self.assertEqual(self.post('content/rating',{'path':'creations/image-studio/a.png','rating':'safe'}).status_code,200)
        self.assertFalse(catalog(self.c)['items'][0]['blur'])
        self.post('content/rating',{'path':'creations/image-studio/a.png','rating':'nsfw'})
        self.assertTrue(catalog(self.c)['items'][0]['blur'])
        self.post('media/preferences',{'blur_nsfw_initially':False})
        self.assertFalse(catalog(self.c)['items'][0]['blur'])
        self.assertEqual(self.post('media/preferences',{'blur_nsfw_initially':'false'}).status_code,400)
    def test_delete_is_authenticated_versioned_and_does_not_delete_album_copy(self):
        self.post('content/album',{'path':'creations/image-studio/a.png','album':'Favorites'})
        row=next(x for x in catalog(self.c)['items'] if x['path'].endswith('/a.png'))
        self.assertEqual(self.client.post('/api/content/delete',json=row).status_code,401)
        self.assertEqual(self.post('content/delete',{**row,'etag':'stale'}).status_code,400)
        self.assertTrue(self.path.exists())
        self.assertEqual(self.post('content/delete',row).status_code,200)
        self.assertFalse(self.path.exists());self.assertEqual(len(list((self.c.data/'albums/Favorites').glob('*.png'))),1)
        reference=self.c.soul_dir/'reference-portrait.png';Image.new('RGB',(8,8)).save(reference)
        row=next(x for x in catalog(self.c)['items'] if x['path']=='soul/reference-portrait.png')
        self.assertFalse(row['deletable']);self.assertEqual(self.post('content/delete',row).status_code,400)
    def test_review_uses_pixels_and_holds_unintended_nudity(self):
        def result(c,command,payload):
            self.assertEqual(command,'review');self.assertEqual(Path(payload['path']),self.path)
            return {'matches_request':True,'nsfw':True,'reason':'Unintended nudity'}
        with patch.object(media,'hermes_bridge',side_effect=result):
            decision=review.inspect(self.c,self.path,'Casual clothes at a table')
            self.assertEqual(decision['status'],'held')
            with self.assertRaises(ValueError):review.ensure_delivery(self.c,self.path,'At a table')
            self.assertEqual(review.inspect(self.c,self.path,'Intentional adult portrait',True)['status'],'passed')
        review.ensure_delivery(self.c,self.path,'Intentional adult portrait')
        self.path.write_bytes(b'changed')
        with patch.object(media,'hermes_bridge',side_effect=ValueError('offline')),self.assertRaises(ValueError):review.ensure_delivery(self.c,self.path,'changed image')
    def test_malformed_or_missing_review_does_not_approve(self):
        for response in ({'nsfw':False},{'matches_request':'true','nsfw':False}):
            with patch.object(media,'hermes_bridge',return_value=response),self.assertRaises(ValueError):review.inspect(self.c,self.path,'At a table')
        with patch.object(media,'hermes_bridge',side_effect=ValueError('offline')),self.assertRaises(ValueError):review.ensure_delivery(self.c,self.path,'At a table')
        self.assertNotEqual(review.metadata(self.path).get('review',{}).get('status'),'passed')
    def test_album_carries_generation_and_rating(self):
        review.write_metadata(self.path,{'generation':'ComfyUI · Example','rating':'nsfw'})
        self.post('content/album',{'path':'creations/image-studio/a.png','album':'Favorites'})
        row=next(x for x in catalog(self.c)['items'] if any(copy['source']=='album' for copy in x.get('copies',[])))
        self.assertEqual(row['generation'],'ComfyUI · Example');self.assertTrue(row['blur'])

    def test_local_scan_never_calls_remote_and_unknown_stays_blurred(self):
        import companion_nsfw
        review.save_preferences(self.c,{'review_provider':'local-nsfw'})
        with patch.object(media,'hermes_bridge',side_effect=AssertionError('Remote call')):
            for rating,status,blur in [('safe','passed',False),('nsfw','held',True),('unknown','held',True)]:
                with patch.object(companion_nsfw,'scan',return_value={'rating':rating,'scope':'nsfw_only'}):
                    self.assertEqual(review.inspect(self.c,self.path,'scene')['status'],status)
                self.assertEqual(catalog(self.c)['items'][0]['blur'],blur)
            with patch.object(companion_nsfw,'scan',side_effect=ValueError('offline')):
                with self.assertRaisesRegex(ValueError,'No remote reviewer'):review.inspect(self.c,self.path,'scene')
            self.assertEqual(review.metadata(self.path)['rating'],'unknown')
            self.assertTrue(catalog(self.c)['items'][0]['blur'])

    def test_local_scan_cannot_approve_changed_pixels(self):
        import companion_nsfw
        review.save_preferences(self.c,{'review_provider':'local-nsfw'})
        def scan(*args):
            self.path.write_bytes(b'changed')
            return {'rating':'safe'}
        with patch.object(companion_nsfw,'scan',side_effect=scan),self.assertRaises(ValueError):
            review.inspect(self.c,self.path,'scene')
        self.assertEqual(review.metadata(self.path)['review']['status'],'unavailable')

    def test_scanner_install_is_optional_and_selection_is_profile_owned(self):
        from kit.app import scanner
        self.assertFalse(self.client.get('/api/media/scanner',headers={'x-companion-token':'secret'}).json()['installed'])
        self.assertEqual(self.client.post('/api/media/scanner/install').status_code,401)
        self.assertEqual(self.post('media/scanner/use',{}).status_code,400)
        with patch.object(scanner,'status',return_value={'installed':True}):
            self.assertEqual(self.post('media/scanner/use',{}).status_code,200)
        self.assertEqual(review.preferences(self.c)['review_provider'],'local-nsfw')
        self.assertFalse((self.c.hermes_root/'companion-media-preferences.json').exists())

    def test_scanner_failed_install_does_not_select_provider(self):
        from kit.app import scanner
        with patch.object(scanner,'status',return_value={'installed':False}),patch.object(scanner.shutil,'disk_usage',return_value=type('Space',(),{'free':0})()):
            with self.assertRaisesRegex(ValueError,'600 MB'):scanner.install(self.c,lambda msg:None)
        self.assertNotEqual(review.preferences(self.c)['review_provider'],'local-nsfw')

    def test_unintended_nudity_retries_once_and_replaces_only_after_safe_scan(self):
        review.write_metadata(self.path,{'rating':'nsfw','review':{'status':'held'}})
        self.path.with_suffix('.json').write_text(json.dumps({'parts':{'scene':'reading in a navy shirt'}}))
        replacement=self.path.with_name('b.png');Image.new('RGB',(8,8),'green').save(replacement)
        review.write_metadata(replacement,{'rating':'safe','review':{'status':'passed'}})
        held=media.ImageHeld('held',self.path,'nsfw')
        with patch.object(media,'_generate',side_effect=[held,{'path':str(replacement)}]) as generate:
            result=media.generate(self.c,overrides={'scene':'reading in a navy shirt'})
            self.assertTrue(result['replaced_nsfw'])
            self.assertEqual(generate.call_count,2)
            self.assertIn('reading in a navy shirt',generate.call_args.args[3]['scene'])
            self.assertIn('fully clothed',generate.call_args.args[3]['scene'])
        self.assertTrue(self.path.exists())
        self.assertEqual([x['path'] for x in catalog(self.c)['items']],['creations/image-studio/b.png'])
        replacement.unlink()
        self.assertTrue(catalog(self.c)['items'][0]['blur'])

    def test_retry_failure_preserves_blurred_original_and_has_no_third_attempt(self):
        review.write_metadata(self.path,{'rating':'nsfw','review':{'status':'held'}})
        self.path.with_suffix('.json').write_text(json.dumps({'parts':{'scene':'reading'}}))
        held=media.ImageHeld('held',self.path,'nsfw')
        with patch.object(media,'_generate',side_effect=[held,ValueError('offline')]) as generate:
            with self.assertRaisesRegex(ValueError,'one replacement attempt failed'):media.generate(self.c)
            self.assertEqual(generate.call_count,2)
        self.assertEqual(review.metadata(self.path)['replacement_status'],'failed')
        self.assertTrue(catalog(self.c)['items'][0]['blur'])
        with patch.object(media,'_generate',side_effect=held) as generate:
            with self.assertRaises(media.ImageHeld):media.generate(self.c,allow_nsfw=True)
            self.assertEqual(generate.call_count,1)
