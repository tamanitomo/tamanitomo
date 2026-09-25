"""The Vault editor bundle ships, is local, and matches its pinned build.

The bundle is built at development time (tools/editor/build.mjs) from a lockfile. A
release needs no Node and fetches nothing. When the build dependencies are installed
(`npm ci` in tools/editor) or TAMANITOMO_REQUIRE_EDITOR_BUILD=1, a fresh build must
equal the committed files byte for byte (drift check)."""
import hashlib, json, os, re, shutil, subprocess, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / 'kit/app/static'
EDITOR = ROOT / 'tools/editor'
SHIPPED = ['kit/app/static/vault-editor.bundle.js', 'kit/app/static/vault-editor.LICENSES.txt',
           'kit/app/static/vault-editor.js']


class VaultEditorBundle(unittest.TestCase):
    def test_bundle_script_and_licences_are_in_the_release_manifest(self):
        manifest = json.loads((ROOT / 'release-files.json').read_text())
        for name in SHIPPED:
            self.assertIn(name, manifest)
            self.assertTrue((ROOT / name).is_file(), name)

    def test_page_loads_the_local_bundle_before_the_editor_and_nothing_remote(self):
        html = (STATIC / 'index.html').read_text()
        order = [html.index(f'/static/{n}') for n in ('studios.js', 'vault-editor.bundle.js', 'vault-editor.js')]
        self.assertEqual(order, sorted(order))
        for name in ('vault-editor.bundle.js', 'vault-editor.js'):
            text = (STATIC / name).read_text()
            self.assertIsNone(re.search(r'''(?:import\(|from\s+['"]|src=['"])https?:''', text), name)

    def test_header_records_the_lockfile_it_was_built_from(self):
        if not (EDITOR / 'package-lock.json').exists():
            self.skipTest('tools/editor is not part of a release package')
        head = (STATIC / 'vault-editor.bundle.js').read_text()[:2000]
        lock = hashlib.sha256((EDITOR / 'package-lock.json').read_bytes()).hexdigest()
        self.assertIn('package-lock sha256 ' + lock, head, 'bundle is stale: run npm ci && node build.mjs')
        pinned = json.loads((EDITOR / 'package.json').read_text())
        for section in ('dependencies', 'devDependencies'):
            for name, version in pinned[section].items():
                self.assertRegex(version, r'^\d+\.\d+\.\d+$', f'{name} must be pinned exactly')
        licences = (STATIC / 'vault-editor.LICENSES.txt').read_text()
        for name in re.findall(r'^ \* (\S+)@\d', head, re.M):
            self.assertIn(f'==== {name}@', licences)

    def test_fresh_build_matches_the_committed_bundle(self):
        installed = (EDITOR / 'node_modules/@codemirror/state').is_dir()
        if os.environ.get('TAMANITOMO_REQUIRE_EDITOR_BUILD') == '1' and not installed:
            raise AssertionError('editor build dependencies are not installed (npm ci in tools/editor)')
        if not installed or not shutil.which('node'):
            self.skipTest('editor build dependencies not installed; run npm ci in tools/editor')
        r = subprocess.run(['node', 'build.mjs', '--check'], cwd=EDITOR, capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)

    def test_editor_script_parses(self):
        if not shutil.which('node'):
            if os.environ.get('TAMANITOMO_REQUIRE_NODE') == '1':raise AssertionError('node required')
            self.skipTest('node unavailable')
        r = subprocess.run(['node', '--check', str(STATIC / 'vault-editor.js')], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == '__main__':
    unittest.main()
