"""Visual keepsakes tests."""
import datetime as dt, json, pathlib, sys, tempfile, unittest
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'kit/scripts'))
import companion_config as cc
import companion_keepsake as keepsake

class KeepsakeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = pathlib.Path(self.tmp.name)
        self.c = cc.Companion(agent='Nova', human='Alex',
                             hermes_root=self.folder / 'home',
                             vault=self.folder / 'vault',
                             content_permissions={'image': 'yes'})
        self.c.data.mkdir(parents=True, exist_ok=True)
        self.test_img = self.folder / 'test.png'
        Image.new('RGB', (32, 32), color='purple').save(self.test_img)
        self.now = dt.datetime(2026, 9, 14, 10, 0, tzinfo=dt.timezone.utc)

    def test_save_creates_files_and_index(self):
        res = keepsake.save(self.c, self.test_img, "Morning Coffee", "Saw this light and thought of you.", now=self.now)
        self.assertTrue(res['ok'])
        folder = keepsake.folder_for(self.c)
        self.assertTrue(folder.is_dir())
        self.assertEqual(folder.name, 'for-alex')
        self.assertTrue((folder / 'INDEX.md').is_file())
        index_text = (folder / 'INDEX.md').read_text()
        self.assertIn("Morning Coffee", index_text)
        self.assertIn("Saw this light", index_text)
        self.assertFalse(res['shared'])

    def test_save_and_share_queues_to_outbox(self):
        res = keepsake.save(self.c, self.test_img, "Sketch for you", "Drew this during my quiet window.", share=True, now=self.now)
        self.assertTrue(res['ok'])
        self.assertTrue(res['shared'])
        self.assertIsNotNone(res['outbox'])
        import companion_outbox as outbox
        queued = outbox.fold(self.c)
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0]['content'], 'image')
        self.assertIn("Sketch for you", queued[0]['body'])

    def test_share_respects_permissions_refusal(self):
        self.c.content_permissions = {'image': 'no'}
        res = keepsake.save(self.c, self.test_img, "Private Photo", "A private keepsake.", share=True, now=self.now)
        self.assertTrue(res['ok'])
        self.assertFalse(res['shared'])
        self.assertIn('share_error', res['outbox'] or {})

    def test_list_and_render(self):
        keepsake.save(self.c, self.test_img, "First", "First note", now=self.now)
        keepsake.save(self.c, self.test_img, "Second", "Second note", now=self.now + dt.timedelta(minutes=5))
        items = keepsake.list_keepsakes(self.c)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]['title'], "Second")
        rendered = keepsake.render(self.c)
        self.assertIn("Second", rendered)
        self.assertIn("First", rendered)

if __name__ == '__main__':
    unittest.main()
