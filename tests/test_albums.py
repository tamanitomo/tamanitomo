"""Timeline retention as a storage budget, and albums that survive it."""
import datetime as dt
import json
import pathlib,sys,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'kit/scripts'))
import companion_config as cc
import companion_timeline as tl

TZ=dt.timezone.utc

def png(size=1):
    """A real one-pixel PNG, repeated to reach a size."""
    from PIL import Image
    import io
    buf=io.BytesIO()
    Image.new('RGB',(size,size),(120,140,160)).save(buf,'PNG')
    return buf.getvalue()

class Base(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=pathlib.Path(self.tmp.name)
        self.c=cc.Companion(agent='Nova',human='Alex',hermes_root=root/'h',vault=root/'v',
                            image_timeline=True,timeline_budget_gb=0)
        (tl.root(self.c)/'captures').mkdir(parents=True,exist_ok=True)
        (tl.root(self.c)/'images').mkdir(parents=True,exist_ok=True)
        self.now=dt.datetime(2026,9,10,12,0,tzinfo=TZ)

    def capture(self,ident,when,size=40):
        data=png(size)
        name=ident+'.png'
        (tl.root(self.c)/'images'/name).write_bytes(data)
        row={'id':ident,'created_at':when.isoformat(),'status':'saved','filename':name,
             'scene':{'recorded_at':when.isoformat(),
                      'state':{'activity':'reading','location':'home','outfit':[
                          {'id':'x','description':'blue pajamas'}],'mood':'quiet'}},
             'image_style':'anime-modern','image_style_guidance':'x'}
        (tl.root(self.c)/'captures'/(ident+'.json')).write_text(json.dumps(row))
        return row


class BudgetTests(Base):
    def test_a_budget_drops_the_oldest_first_and_says_how_much_it_freed(self):
        ids=[f'{i:024x}' for i in range(5)]
        for n,ident in enumerate(ids):
            self.capture(ident,self.now-dt.timedelta(hours=10-n),size=60)
        used=tl.prune(self.c,self.now)['bytes_used']
        self.c.timeline_budget_gb=used/2/1_000_000_000
        report=tl.prune(self.c,self.now)
        self.assertGreater(report['removed'],0)
        self.assertGreater(report['freed_bytes'],0)
        self.assertLessEqual(report['bytes_used'],report['budget_bytes'])
        left={r['id'] for _,r in tl.records(self.c)}
        self.assertNotIn(ids[0],left)          # oldest went
        self.assertIn(ids[-1],left)            # newest stayed

    def test_with_no_budget_the_calendar_still_bounds_it(self):
        self.capture('a'*24,self.now-dt.timedelta(days=40))
        self.capture('b'*24,self.now-dt.timedelta(days=2))
        report=tl.prune(self.c,self.now)
        self.assertEqual(report['removed'],1)
        self.assertEqual(report['retention_days'],tl.DAYS)

    def test_a_capture_that_never_landed_is_marked_failed_not_kept_pending(self):
        row={'id':'c'*24,'created_at':(self.now-dt.timedelta(hours=2)).isoformat(),
             'status':'pending','scene':{},'image_style':'x','image_style_guidance':'y'}
        (tl.root(self.c)/'captures'/('c'*24+'.json')).write_text(json.dumps(row))
        tl.prune(self.c,self.now)
        after=json.loads((tl.root(self.c)/'captures'/('c'*24+'.json')).read_text())
        self.assertEqual(after['status'],'failed')

    def test_a_negative_budget_is_refused_at_configuration_time(self):
        with self.assertRaisesRegex(ValueError,'timeline_budget_gb'):
            cc.Companion(timeline_budget_gb=-1)


class AlbumTests(Base):
    def test_keeping_one_copies_it_and_leaves_the_original(self):
        ident='d'*24
        self.capture(ident,self.now)
        result=tl.favorite(self.c,ident)
        self.assertTrue(pathlib.Path(result['file']).is_file())
        self.assertTrue((tl.root(self.c)/'images'/(ident+'.png')).is_file())
        self.assertIn('Copied, not moved',result['note'])

    def test_an_album_copy_survives_the_budget_taking_the_original(self):
        ident='e'*24
        self.capture(ident,self.now-dt.timedelta(days=40))
        kept=pathlib.Path(tl.favorite(self.c,ident)['file'])
        tl.prune(self.c,self.now)
        self.assertFalse((tl.root(self.c)/'images'/(ident+'.png')).exists())
        self.assertTrue(kept.is_file())

    def test_the_copy_carries_the_moment_it_came_from(self):
        ident='f'*24
        self.capture(ident,self.now)
        result=tl.favorite(self.c,ident)
        caption=pathlib.Path(result['file']+'.txt').read_text()
        self.assertIn('reading at home',caption)

    def test_a_person_can_add_their_own_pictures(self):
        source=pathlib.Path(self.tmp.name)/'mine.png'
        source.write_bytes(png(8))
        result=tl.add_to_album(self.c,source,'Trip to Lisbon')
        self.assertTrue(pathlib.Path(result['file']).is_file())
        self.assertEqual([a['name'] for a in tl.albums(self.c)],['Trip to Lisbon'])

    def test_album_names_cannot_escape_the_vault(self):
        for bad in ('../escape','','.',' /etc'):
            with self.assertRaises(ValueError):tl.favorite(self.c,'a'*24,bad)

    def test_only_a_saved_capture_can_be_kept(self):
        ident='0'*24
        row={'id':ident,'created_at':self.now.isoformat(),'status':'failed','scene':{},
             'image_style':'x','image_style_guidance':'y'}
        (tl.root(self.c)/'captures'/(ident+'.json')).write_text(json.dumps(row))
        with self.assertRaisesRegex(ValueError,'saved'):tl.favorite(self.c,ident)


if __name__=='__main__':unittest.main()
