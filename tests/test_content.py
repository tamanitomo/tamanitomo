"""Content discovery serves only the selected companion's visible files."""
import sys,tempfile,unittest,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'kit/scripts')]
import companion_config as cc
from kit.app.content import catalog,journals,resolve,life_moments
from kit.app.server import build
from fastapi.testclient import TestClient

class ContentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        p=Path(self.tmp.name)
        self.c=cc.Companion(profile='nova',agent='Nova',vault=p/'vault',hermes_root=p/'hermes',context_mode='fixed')
        self.c.home.mkdir(parents=True);self.c.soul_dir.mkdir(parents=True);self.c.save()
        self.client=TestClient(build(self.c.home,token='private',state_dir=p/'state'))
        self.headers={'x-companion-token':'private'}
    def add(self,path,text='content'):
        p=self.c.data/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text);return p
    def test_catalog_includes_creations_and_excludes_secrets_backups_and_peers(self):
        self.add('companion-life/frames/art.png');self.add('companion-life/notes/thought.md')
        self.add('.private/image.png');self.add('soul/soul-backups/SOUL.md');self.add('notes/credentials.txt')
        peer=self.c.data.parent/'rowan';peer.mkdir();(peer/'other.png').touch()
        paths={x['path'] for x in catalog(self.c)['items']}
        self.assertEqual(paths,{'companion-life/frames/art.png','companion-life/notes/thought.md'})
    def test_paths_refuse_symlinks_traversal_hidden_and_unsafe_types(self):
        self.add('notes/a.md');self.add('notes/run.html')
        for p in ('../rowan/other.png','/etc/passwd','.private/a.md','notes/run.html','notes/../notes/a.md'):
            with self.assertRaises(ValueError):resolve(self.c,p)
        try:(self.c.data/'linked.md').symlink_to(self.c.data/'notes/a.md')
        except OSError:return
        with self.assertRaises(ValueError):resolve(self.c,'linked.md')
        self.assertNotIn('linked.md',[r['path'] for r in catalog(self.c)['items']])
    def test_journals_include_vault_and_archived_entries_without_rewriting(self):
        body='# Lifelog\n\n## 2026-09-10\n\nA real entry.\n\n### A detail\nStill that day.\n\n## 2026-09-11\n\nA new day.'
        p=self.add('soul/Lifelog.md',body)
        self.add('soul/continuity/archive/Lifelog-2026-08.md','## 2026-08-01\n\nAn older day.')
        entries=journals(self.c)['entries']
        self.assertEqual([r['day'] for r in entries],['2026-09-11','2026-09-10','2026-08-01'])
        self.assertIn('### A detail',entries[1]['text']);self.assertEqual(p.read_text(),body)
    def test_content_routes_require_token_and_preserve_raw_text(self):
        self.add('notes/unsafe.md','<script>alert(1)</script>')
        self.assertEqual(self.client.get('/api/content').status_code,401)
        response=self.client.get('/api/content/text?path=notes/unsafe.md',headers=self.headers)
        self.assertEqual(response.json()['text'],'<script>alert(1)</script>')
        self.assertEqual(self.client.get('/api/content/file?path=notes/unsafe.md',headers=self.headers).headers['x-content-type-options'],'nosniff')
        self.assertEqual(self.client.get('/api/content/file?path=../rowan/other.png',headers=self.headers).status_code,400)
    def test_album_copy_keeps_original_and_rejects_linked_destination(self):
        from PIL import Image
        image=self.c.data/'art.png';Image.new('RGB',(8,8),'blue').save(image)
        before=image.read_bytes()
        response=self.client.post('/api/content/album',headers=self.headers,json={'path':'art.png','album':'Favorites'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(image.read_bytes(),before)
        self.assertEqual(len(list((self.c.data/'albums/Favorites').glob('*.png'))),1)
        outside=Path(self.tmp.name)/'outside';outside.mkdir()
        try:(self.c.data/'albums/Linked').symlink_to(outside,target_is_directory=True)
        except OSError:return
        result=self.client.post('/api/content/album',headers=self.headers,json={'path':'art.png','album':'Linked'})
        self.assertEqual(result.status_code,400);self.assertEqual(list(outside.iterdir()),[])

    def test_image_copies_are_one_item_with_all_collections_and_stable_time(self):
        original=self.add('creations/image-studio/original.png','image one')
        os.utime(original,(100,100))
        before=catalog(self.c)['items'][0]
        self.add('image-timeline/images/capture.png','image one')
        self.add('albums/Favorites/kept.png','image one')
        self.add('creations/other.png','image two')
        rows=catalog(self.c)['items']
        self.assertEqual(len(rows),2)
        row=next(r for r in rows if r['content_id']==before['content_id'])
        self.assertEqual(row['path'],before['path'])
        self.assertEqual(row['at'],before['at'])
        self.assertEqual({p['source'] for p in row['copies']},{'creation','photo session','album'})
        self.assertTrue(all((self.c.data/p['path']).exists() for p in row['copies']))
        # A same-length edit must invalidate the cached content identity.
        original.write_text('image two')
        self.assertEqual(next(r for r in catalog(self.c)['items'] if any(p['path']=='creations/image-studio/original.png' for p in r.get('copies',[])))['content_id'],next(r for r in rows if r['path']=='creations/other.png')['content_id'])

    def test_copy_review_stays_conservative_and_user_rating_updates_group(self):
        import companion_media_review as review
        a=self.add('creations/a.png','same');b=self.add('albums/Favorites/b.png','same')
        review.write_metadata(a,{'rating':'safe'})
        review.write_metadata(b,{'rating':'nsfw'})
        row=catalog(self.c)['items'][0]
        self.assertEqual(row['rating'],'nsfw');self.assertTrue(row['blur'])
        response=self.client.post('/api/content/rating',headers=self.headers,json={'path':'creations/a.png','rating':'safe'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(review.metadata(b)['rating'],'safe')
        self.assertFalse(catalog(self.c)['items'][0]['blur'])

    def test_life_moments_collapse_only_adjacent_unchanged_states(self):
        def row(ident,activity,confirmed=True):
            return {'id':ident,'state':{'activity':activity,'confirmed':confirmed,'mood':'calm'}}
        events=[row('5','reading',False),row('4','reading',False),row('3','reading'),row('2','walking'),row('1','reading')]
        self.assertEqual([r['id'] for r in life_moments(events)],['5','3','2','1'])
        self.assertEqual(len(events),5)

    def test_root_content_catalog_excludes_named_profiles(self):
        root=cc.Companion(vault=self.c.vault,hermes_root=self.c.hermes_root,context_mode='fixed')
        self.add('photo.png');(root.data/'root.png').touch()
        self.assertEqual([r['path'] for r in catalog(root)['items']],['root.png'])

    def test_journal_archive_cannot_link_into_another_profile(self):
        outside=Path(self.tmp.name)/'other-profile';outside.mkdir()
        (outside/'Lifelog-2026-08.md').write_text('## 2026-08-01\n\nNot this companion.')
        folder=self.c.soul_dir/'continuity';folder.mkdir()
        try:(folder/'archive').symlink_to(outside,target_is_directory=True)
        except OSError:self.skipTest('Symlinks unavailable')
        result=journals(self.c)
        self.assertEqual(result['entries'],[])
        self.assertTrue(result['warnings'])

    def settled(self,ident,tries=100):
        """Wait for a queued operation and hand back its result."""
        import time
        for _ in range(tries):
            row=self.client.get('/api/operations/'+ident,headers=self.headers).json()
            if row['status']!='running':
                self.assertEqual(row['status'],'complete',row.get('error'))
                return row['result']
            time.sleep(0.05)
        self.fail('operation never finished')

    def test_timeline_rerender_and_select_variant(self):
        from PIL import Image
        import companion_presence as presence
        import companion_timeline as timeline
        import companion_media as media
        from unittest.mock import patch
        import datetime as dt
        now=dt.datetime(2026,9,14,12,0,tzinfo=dt.timezone.utc)
        presence.update_wardrobe(self.c,[{'id':'tee','description':'simple tee','use':'day'}])
        presence.update(self.c,{'previous_id':None,'outfit':['tee'],'location':'garden','activity':'gardening','mood':'peaceful','text':'In the garden.'},now)
        self.c.image_timeline=True
        self.c.image_style='realistic'
        self.c.save()
        capture=timeline.prepare(self.c,now)
        self.assertTrue(capture['ready'])
        cid=capture['capture_id']
        img1=self.c.data/'img1.png';Image.new('RGB',(16,16),'green').save(img1)
        timeline.save(self.c,cid,str(img1),'initial-provider',now)

        media.save(self.c,{'version':1,'presets':[{'id':'p-alt','name':'Alt Engine','provider':'hermes','category':'portrait','active':True}],'default_preset':'p-alt'},media.revision(self.c))

        img2=self.c.data/'img2.png';Image.new('RGB',(16,16),'red').save(img2)
        with patch.object(media,'generate',return_value={'path':str(img2),'provider':'Alt Engine · Hermes'}):
            # Rendering is queued, not awaited: it used to hold the request open
            # for as long as the render took, which is why pressing Generate
            # looked like it did nothing at all.
            res=self.client.post(f'/api/timeline/{cid}/rerender',headers=self.headers,json={'preset_id':'p-alt'})
            self.assertEqual(res.status_code,200,res.text)
            queued=res.json()
            self.assertEqual(queued['status'],'running')
            self.assertEqual(queued['label'],'Regenerate photo')
            data=self.settled(queued['id'])
            self.assertEqual(data['status'],'saved')
            self.assertEqual(len(data['capture']['variants']),2)
            var_fn=data['variant']['filename']
            self.assertTrue(var_fn.startswith(cid+'_v2.'))
            # The new version arrives with its own review, so the viewer cannot
            # read it as safe and reveal it before anyone has judged it.
            self.assertIn('blur',data['variant'])
            self.assertIn('rating',data['variant'])

            res_sel=self.client.post(f'/api/timeline/{cid}/select-variant',headers=self.headers,json={'filename':var_fn})
            self.assertEqual(res_sel.status_code,200,res_sel.text)
            self.assertEqual(res_sel.json()['filename'],var_fn)
            self.assertEqual(res_sel.json()['primary_filename'],var_fn)

            res_tl=self.client.get('/api/timeline',headers=self.headers)
            self.assertEqual(res_tl.status_code,200)
            captures=res_tl.json()['captures']
            c_row=next(r for r in captures if r['id']==cid)
            self.assertEqual(c_row['filename'],var_fn)
            self.assertEqual(c_row['primary_filename'],var_fn)
            self.assertEqual(len(c_row['variants']),2)

if __name__=='__main__':unittest.main()

class JournalArchiveTests(unittest.TestCase):
    def setUp(self):
        from tests import test_workspace as workspace
        self.f=workspace.WorkspaceTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.f.c.soul_dir.mkdir(parents=True,exist_ok=True)
    def test_paging_reaches_past_one_thousand_entries(self):
        import datetime as dt
        body='\n\n'.join('## '+(dt.date(2020,1,1)+dt.timedelta(days=i)).isoformat()+'\n\nEntry '+str(i) for i in range(1005))
        (self.f.c.soul_dir/'Lifelog.md').write_text(body)
        first=journals(self.f.c)
        self.assertEqual(first['total'],1005);self.assertEqual(len(first['entries']),1000)
        rest=journals(self.f.c,before=first['next_cursor'])
        self.assertEqual(len(rest['entries']),5);self.assertIsNone(rest['next_cursor'])
        ids=[r['id'] for r in first['entries']+rest['entries']]
        self.assertEqual(len(set(ids)),1005)
    def test_full_entry_and_search_include_text_beyond_preview(self):
        body='## 2026-09-12\n\n'+('A long day. '*10000)+'Needle at the end.'
        (self.f.c.soul_dir/'Lifelog.md').write_text(body)
        data=journals(self.f.c,q='Needle')
        self.assertEqual(data['total'],1);entry=data['entries'][0];self.assertTrue(entry['truncated'])
        response=self.f.get('/api/journals/'+entry['id'])
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.json()['entry']['text'].endswith('Needle at the end.'))
        self.assertFalse(response.json()['entry']['truncated'])
        self.assertEqual(journals(self.f.c,month='2026-08')['total'],0)
        self.assertEqual(self.f.get('/api/journals/'+entry['id'],'rowan').status_code,400)
    def test_journal_paging_validates_input(self):
        for params in ({'before':'bad'},{'month':'2026-99'},{'limit':0},{'q':'a'*201},{'entry_id':'../secrets'}):
            with self.subTest(params=params),self.assertRaises(ValueError):journals(self.f.c,**params)

class GalleryArchiveTests(unittest.TestCase):
    def setUp(self):
        from tests import test_workspace as workspace
        self.f=workspace.WorkspaceTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
    def test_gallery_pages_beyond_1500_and_filters_before_paging(self):
        import os
        for i in range(1505):
            p=self.f.c.data/f'image-{i:04}.png';p.write_bytes(str(i).encode());os.utime(p,(100,100))
        first=catalog(self.f.c,kind='image')
        self.assertEqual(first['total'],1505);self.assertEqual(len(first['items']),1500)
        rest=catalog(self.f.c,kind='image',before=first['next_cursor'])
        self.assertEqual(len(rest['items']),5);self.assertIsNone(rest['next_cursor'])
        self.assertEqual(len({x['path'] for x in first['items']+rest['items']}),1505)
        filtered=catalog(self.f.c,kind='image',q='image 0000',limit=1)
        self.assertEqual(filtered['total'],1);self.assertEqual(filtered['items'][0]['path'],'image-0000.png')
        self.assertFalse(first['scan_limited'])
        import companion_media_review as review
        album=self.f.c.data/'albums/Favorites';album.mkdir(parents=True)
        copy=album/'old.png';copy.write_bytes(b'0');os.utime(copy,(100,100))
        review.write_metadata(copy,{'rating':'nsfw'})
        response=self.f.client.post('/api/content/rating?profile=nova',headers=self.f.headers,json={'path':'image-0000.png','rating':'safe'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(review.metadata(copy)['rating'],'safe')
    def test_album_membership_and_concealment_survive_paging(self):
        source=self.f.c.data/'picture.png';source.write_bytes(b'unique picture')
        album=self.f.c.data/'albums/Favorites';album.mkdir(parents=True)
        copy=album/'kept.png';copy.write_bytes(source.read_bytes())
        import companion_media_review as review
        review.write_metadata(source,{'rating':'safe'});review.write_metadata(copy,{'rating':'nsfw'})
        page=catalog(self.f.c,kind='image',collection='album:Favorites',limit=1)
        self.assertEqual(page['total'],1);self.assertTrue(page['items'][0]['blur'])
        self.assertEqual(len(page['items'][0]['copies']),2)
        self.assertEqual(catalog(self.f.c,kind='image',collection='album:Other')['total'],0)
    def test_invalid_gallery_filters_are_rejected(self):
        for params in ({'limit':0},{'before':'broken'},{'day':'2026-02-30'},{'kind':'secret'},{'q':'x'*201}):
            with self.subTest(params=params),self.assertRaises(ValueError):catalog(self.f.c,**params)


class DeletingAPhotoDeletesThePhotoTests(unittest.TestCase):
    """Deleting a photo must delete the photo, not one of its two copies.

    Every generated picture is written twice -- into the studio and into the
    photo session -- byte-identical, so the library groups them and shows one
    photo. Delete removed whichever copy the grouping happened to name first and
    left the other on disk, so the picture came straight back on the next
    refresh: a delete button that reported success and did nothing.
    """

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        p=Path(self.tmp.name)
        self.c=cc.Companion(profile='nova',agent='Nova',vault=p/'vault',hermes_root=p/'hermes',context_mode='fixed')
        self.c.home.mkdir(parents=True);self.c.soul_dir.mkdir(parents=True);self.c.save()
        self.client=TestClient(build(self.c.home,token='private',state_dir=p/'state'))
        self.headers={'x-companion-token':'private'}

    def both_copies(self,name='shot.png',colour='blue'):
        """The same bytes in both places, exactly as a generated picture lands."""
        from PIL import Image
        studio=self.c.data/'creations/image-studio'/name
        session=self.c.data/'image-timeline/images'/name
        studio.parent.mkdir(parents=True,exist_ok=True)
        session.parent.mkdir(parents=True,exist_ok=True)
        Image.new('RGB',(8,8),colour).save(studio)
        session.write_bytes(studio.read_bytes())
        return studio,session

    def listed(self):
        return self.client.get('/api/content?kind=image',headers=self.headers).json()['items']

    def test_one_photo_is_listed_for_the_two_copies(self):
        self.both_copies()
        items=self.listed()
        self.assertEqual(len(items),1)
        self.assertEqual({c['path'] for c in items[0]['copies']},
                         {'creations/image-studio/shot.png','image-timeline/images/shot.png'})

    def test_deleting_it_takes_both_copies_and_it_stays_gone(self):
        studio,session=self.both_copies()
        item=self.listed()[0]
        response=self.client.post('/api/content/delete',headers=self.headers,
                                  json={'path':item['path'],'etag':item['etag']})
        self.assertEqual(response.status_code,200,response.text)
        self.assertFalse(studio.exists(),'the studio copy survived')
        self.assertFalse(session.exists(),'the photo session copy survived, so it came back')
        self.assertEqual(self.listed(),[])

    def test_an_album_copy_is_left_alone_as_promised(self):
        """The confirmation says separate album copies are unaffected."""
        self.both_copies()
        kept=self.client.post('/api/content/album',headers=self.headers,
                              json={'path':'creations/image-studio/shot.png','album':'Favorites'})
        self.assertEqual(kept.status_code,200,kept.text)
        album=list((self.c.data/'albums/Favorites').glob('*.png'))
        self.assertEqual(len(album),1)
        item=next(x for x in self.listed() if any(c['source']!='album' for c in x['copies']))
        self.client.post('/api/content/delete',headers=self.headers,
                         json={'path':item['path'],'etag':item['etag']})
        self.assertTrue(album[0].exists(),'the album copy was collateral')

    def test_deleting_the_album_copy_leaves_the_original(self):
        studio,session=self.both_copies()
        self.client.post('/api/content/album',headers=self.headers,
                         json={'path':'creations/image-studio/shot.png','album':'Favorites'})
        album=list((self.c.data/'albums/Favorites').glob('*.png'))[0]
        rel='albums/Favorites/'+album.name
        stat=album.stat()
        response=self.client.post('/api/content/delete',headers=self.headers,
                                  json={'path':rel,'etag':f'{stat.st_mtime_ns}:{stat.st_size}'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertFalse(album.exists())
        self.assertTrue(studio.exists() and session.exists())

    def test_a_batch_delete_clears_every_copy_too(self):
        first=self.both_copies('one.png','blue')
        second=self.both_copies('two.png','red')
        items=self.listed()
        self.assertEqual(len(items),2)
        response=self.client.post('/api/content/batch-delete',headers=self.headers,
                                  json={'items':[{'path':x['path'],'etag':x['etag']} for x in items]})
        self.assertEqual(response.status_code,200,response.text)
        for path in (*first,*second):
            self.assertFalse(path.exists(),path)
        self.assertEqual(self.listed(),[])


class VariantsCarryTheirOwnReviewTests(unittest.TestCase):
    """A version in the preview strip must arrive with its own review attached.

    It did not, so the viewer read every variant as safe: the strip showed each
    one in the clear beneath a blurred picture, and picking one took the blur off
    the main image. The one action you might take precisely because you did not
    want to look at it was the action that showed it to you.
    """

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        p=Path(self.tmp.name)
        self.c=cc.Companion(profile='nova',agent='Nova',vault=p/'vault',hermes_root=p/'hermes',context_mode='fixed')
        self.c.home.mkdir(parents=True);self.c.soul_dir.mkdir(parents=True);self.c.save()

    def make(self,name,rating):
        from PIL import Image
        import companion_media_review as review
        path=self.c.data/'image-timeline/images'/name
        path.parent.mkdir(parents=True,exist_ok=True)
        Image.new('RGB',(8,8),'blue').save(path)
        if rating is not None:review.write_metadata(path,{'rating':rating})
        return path

    def variants(self,names):
        from kit.app.content import with_etags
        return with_etags(self.c,[{'filename':n} for n in names])

    def test_each_variant_carries_its_rating_and_blur(self):
        self.make('a.png','nsfw');self.make('b.png','safe')
        rows={v['filename']:v for v in self.variants(['a.png','b.png'])}
        self.assertEqual(rows['a.png']['rating'],'nsfw')
        self.assertTrue(rows['a.png']['blur'])
        self.assertEqual(rows['b.png']['rating'],'safe')
        self.assertFalse(rows['b.png']['blur'])

    def test_an_unreviewed_variant_is_unreviewed_rather_than_safe(self):
        self.make('c.png',None)
        row=self.variants(['c.png'])[0]
        self.assertNotEqual(row['rating'],'safe')
        self.assertTrue(row['blur'],'an unreviewed picture must not arrive already revealed')

    def test_a_variant_whose_file_is_gone_is_still_not_called_safe(self):
        row=self.variants(['missing.png'])[0]
        self.assertIsNone(row['etag'])
        self.assertTrue(row['blur'])
