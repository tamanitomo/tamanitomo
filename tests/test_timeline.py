"""No provider calls: validate capture state, image import, opt-in and retention."""
import datetime as dt,json,pathlib,sys,tempfile,unittest
from PIL import Image
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'kit/scripts'))
import companion_config as cc
import companion_presence as presence
import companion_timeline as timeline

class TimelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.folder=pathlib.Path(self.tmp.name)
        self.c=cc.Companion(hermes_root=self.folder/'home',vault=self.folder/'vault',image_timeline=True,image_style='realistic')
        self.now=dt.datetime(2026,9,9,12,2,tzinfo=dt.timezone.utc)
        presence.update_wardrobe(self.c,[{'id':'tee','description':'green tee','use':'everyday'}])
        self.data={'previous_id':None,'outfit':['tee'],'location':'kitchen','activity':'lunch','mood':'cheerful','text':'Making lunch.'}
        presence.update(self.c,self.data,self.now-dt.timedelta(minutes=2))
        self.image=self.folder/'provider.png';Image.new('RGB',(16,16),'green').save(self.image)
    def test_photo_interval_applies_even_after_the_scene_changes(self):
        self.c.image_interval_minutes=120
        first=timeline.prepare(self.c,self.now)
        timeline.save(self.c,first['capture_id'],str(self.image),'test',self.now)
        later=self.now+dt.timedelta(minutes=65)
        previous=presence.current(self.c)
        presence.update(self.c,{**self.data,'previous_id':previous['id'],'activity':'reading','transition':'Lunch finished.'},later)
        self.assertFalse(timeline.prepare(self.c,later)['ready'])
        later=self.now+dt.timedelta(minutes=121)
        previous=presence.current(self.c)
        presence.update(self.c,{**self.data,'previous_id':previous['id'],'activity':'writing','transition':'Finished reading.'},later)
        self.assertTrue(timeline.prepare(self.c,later)['ready'])

    def test_opt_out_and_stale_state_prevent_claiming(self):
        self.c.image_timeline=False;self.assertFalse(timeline.prepare(self.c,self.now)['ready'])
        self.c.image_timeline=True
        self.assertFalse(timeline.prepare(self.c,self.now+dt.timedelta(minutes=16))['ready'])
        self.assertEqual(list(timeline.records(self.c)),[])
    def test_once_per_interval_and_saved_image_keeps_its_original_scene(self):
        capture=timeline.prepare(self.c,self.now);ident=capture['capture_id']
        self.assertFalse(timeline.prepare(self.c,self.now)['ready'])
        previous=presence.current(self.c)
        presence.update(self.c,{**self.data,'previous_id':previous['id'],'id':'after-lunch','activity':'washing dishes','transition':'Finished lunch.'},self.now+dt.timedelta(minutes=1))
        saved=timeline.save(self.c,ident,str(self.image),'test-provider',self.now+dt.timedelta(minutes=2))
        self.assertEqual(saved['scene']['state']['activity'],'lunch')
        stored=timeline.root(self.c)/'images'/saved['filename']
        self.assertEqual(stored.read_bytes(),self.image.read_bytes())
        self.assertEqual(timeline.save(self.c,ident,str(self.image),'test-provider',self.now+dt.timedelta(minutes=3)),saved)
        gallery=(timeline.root(self.c)/'index.html').read_text()
        self.assertIn('green tee',gallery);self.assertIn('Save favorite',gallery)
    def test_calendar_cleanup_leaves_provider_original_favorites_and_unknown_files(self):
        """Retention is a storage budget now; with no budget set the old calendar
        still bounds the folder, and this is that path."""
        self.c.timeline_budget_gb=0
        capture=timeline.prepare(self.c,self.now)
        saved=timeline.save(self.c,capture['capture_id'],str(self.image),'test-provider',self.now)
        favorite=self.folder/'favorite.png';favorite.write_bytes(self.image.read_bytes())
        unknown=timeline.root(self.c)/'images/keep.png';unknown.write_bytes(self.image.read_bytes())
        self.assertEqual(timeline.prune(self.c,self.now+dt.timedelta(days=30)-dt.timedelta(seconds=1))['removed'],0)
        self.assertEqual(timeline.prune(self.c,self.now+dt.timedelta(days=30))['removed'],1)
        self.assertFalse((timeline.root(self.c)/'images'/saved['filename']).exists())
        for path in [favorite,unknown,self.image]:self.assertTrue(path.exists())
    def test_not_an_image_does_not_become_a_successful_capture(self):
        capture=timeline.prepare(self.c,self.now);self.image.write_text('not an image')
        with self.assertRaises((ValueError,OSError)):timeline.save(self.c,capture['capture_id'],str(self.image),'test',self.now)
        self.assertEqual(next(timeline.records(self.c))[1]['status'],'pending')
        timeline.prune(self.c,self.now+dt.timedelta(minutes=16))
        self.assertEqual(next(timeline.records(self.c))[1]['status'],'failed')
    def test_a_state_confirmed_earlier_in_the_same_interval_still_counts(self):
        """The presence loop never lands on the quarter-hour, so a capture must
        not be refused merely because the confirming record predates the slot
        boundary by a few minutes."""
        self.assertIs(self.now.minute,2)
        capture=timeline.prepare(self.c,self.now)
        self.assertTrue(capture['ready'])
        self.assertEqual(capture['scene']['state']['activity'],'lunch')
    def test_a_state_from_a_previous_interval_is_still_stale(self):
        self.assertFalse(timeline.prepare(self.c,self.now+dt.timedelta(minutes=16))['ready'])
    def test_bounds_admit_a_recent_record(self):
        now=self.now.astimezone(dt.timezone.utc)
        start,end=timeline.bounds(now)
        record=presence.current(self.c)
        self.assertTrue(start<=timeline.timestamp(record['recorded_at'])<=end)
    def test_cleanup_rejects_a_traversal_in_corrupted_metadata(self):
        capture=timeline.prepare(self.c,self.now);path=timeline.capture_path(self.c,capture['capture_id'])
        data=json.loads(path.read_text());data['filename']='../../favorite.png';path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'Unsafe'):timeline.prune(self.c,self.now+dt.timedelta(days=31))
        self.assertTrue(self.image.exists())
    def test_image_directory_symlink_cannot_redirect_cleanup(self):
        outside=self.folder/'favorites';outside.mkdir()
        root=timeline.root(self.c);root.mkdir(parents=True)
        try:(root/'images').symlink_to(outside,target_is_directory=True)
        except (OSError,NotImplementedError):self.skipTest('Symlinks unavailable')
        with self.assertRaisesRegex(ValueError,'symlinks'):timeline.prepare(self.c,self.now)
        self.assertTrue(outside.exists())

    def test_gallery_escapes_authored_text(self):
        previous=presence.current(self.c)
        presence.update(self.c,{**self.data,'previous_id':previous['id'],'id':'strange-place','location':'<script>alert(1)</script>','transition':'A story setting.'},self.now)
        capture=timeline.prepare(self.c,self.now)
        timeline.save(self.c,capture['capture_id'],str(self.image),'test',self.now)
        page=(timeline.root(self.c)/'index.html').read_text()
        self.assertNotIn('<script>',page);self.assertIn('&lt;script&gt;',page)

    def test_latest_and_share_queues_image(self):
        import companion_outbox as outbox
        self.assertIsNone(timeline.latest(self.c))
        with self.assertRaises(ValueError):timeline.share(self.c,'Teasing you')
        capture=timeline.prepare(self.c,self.now)
        saved=timeline.save(self.c,capture['capture_id'],str(self.image),'test',self.now)
        latest_info=timeline.latest(self.c)
        self.assertIsNotNone(latest_info)
        self.assertEqual(latest_info['id'],capture['capture_id'])
        self.assertTrue(pathlib.Path(latest_info['path']).is_file())
        res=timeline.share(self.c,'Look at what I am doing today!')
        self.assertEqual(res['written'],True)
        queued=outbox.waiting(self.c)
        self.assertEqual(len(queued),1)
        self.assertEqual(queued[0]['content'],'image')
        self.assertEqual(queued[0]['body'],'Look at what I am doing today!')
        self.assertEqual(queued[0]['media_path'],latest_info['path'])

    def test_variants_add_and_select(self):
        capture=timeline.prepare(self.c,self.now)
        ident=capture['capture_id']
        saved=timeline.save(self.c,ident,str(self.image),'provider-1',self.now)
        self.assertEqual(len(saved['variants']),1)
        self.assertEqual(saved['primary_filename'],saved['filename'])

        image2=self.folder/'provider2.png'
        Image.new('RGB',(16,16),'blue').save(image2)
        with_variant=timeline.add_variant(self.c,ident,str(image2),'provider-2',now=self.now)
        self.assertEqual(len(with_variant['variants']),2)
        v2_fn=with_variant['variants'][1]['filename']
        self.assertTrue(v2_fn.startswith(ident+'_v2.'))
        self.assertTrue((timeline.root(self.c)/'images'/v2_fn).is_file())
        # Primary is still original
        self.assertEqual(with_variant['primary_filename'],saved['filename'])

        selected=timeline.select_variant(self.c,ident,v2_fn)
        self.assertEqual(selected['filename'],v2_fn)
        self.assertEqual(selected['primary_filename'],v2_fn)
        self.assertEqual(selected['provider'],'provider-2')

    def test_save_persists_prompts(self):
        capture=timeline.prepare(self.c,self.now)
        ident=capture['capture_id']
        prompts={'prose':'Sam in a garden with warm light','structured':'1girl, garden, sunlight'}
        saved=timeline.save(self.c,ident,str(self.image),'test-provider',self.now,prompts=prompts)
        self.assertEqual(saved['prompts'],prompts)

