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
