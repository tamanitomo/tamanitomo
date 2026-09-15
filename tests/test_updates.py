import hashlib,io,json,tempfile,unittest,zipfile
from pathlib import Path
from kit.app.updates import stage
from update_release import apply_pending,runtime_lock

def package(files):
    files={**files,'release-files.json':json.dumps([*files,'release-files.json']).encode()}
    hashes={n:hashlib.sha256(v).hexdigest() for n,v in files.items()};files['SHA256SUMS.json']=json.dumps(hashes).encode()
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:
        for n,v in files.items():z.writestr('companion-kit/'+n,v)
    return b.getvalue(),files

class UpdateTests(unittest.TestCase):
    def test_verified_stage_apply_backup_and_preserve_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);_,old=package({'VERSION':b'1','README.md':b'old'})
            for n,v in old.items():(root/n).write_bytes(v)
            (root/'my-vault.txt').write_text('private')
            raw,_=package({'VERSION':b'2','README.md':b'new'})
            r=stage(raw,root);self.assertTrue(r['staged']);self.assertEqual((root/'README.md').read_text(),'old')
            with runtime_lock(root),self.assertRaises(ValueError):apply_pending(root)
            apply_pending(root);self.assertEqual((root/'README.md').read_text(),'new');self.assertEqual((root/'my-vault.txt').read_text(),'private')
            self.assertEqual(next((root/'.update-backups').glob('*/README.md')).read_text(),'old')
    def test_modified_install_and_path_traversal_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);raw,old=package({'VERSION':b'1'})
            for n,v in old.items():(root/n).write_bytes(v)
            (root/'VERSION').write_text('modified')
            with self.assertRaisesRegex(ValueError,'Local code'):stage(raw,root)
            bad,_=package({'../escape':b'x'})
            with self.assertRaises(ValueError):stage(bad,root)
            bad,_=package({'C:/escape':b'x'})
            with self.assertRaises(ValueError):stage(bad,root)
