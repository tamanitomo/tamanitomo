"""Execute installer contracts with disposable paths and mocked package installs."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == 'posix' and shutil.which('bash'), 'POSIX installer contracts')
class InstallerTests(unittest.TestCase):
    def test_piped_linux_dry_run_does_not_create_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = subprocess.run(['bash', '-s', '--', '--dry-run', '--hermes-home', str(root/'state'),
                                     '--install-dir', str(root/'install')],
                                    input=(ROOT/'setup-linux.sh').read_text(), text=True,
                                    cwd=root, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_invalid_pin_fails_closed_on_both_installers(self):
        for name in ('setup-linux.sh', 'setup-termux.sh'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                result = subprocess.run(['bash', str(ROOT/name), '--dry-run', '--remote-pin', '123'],
                                        cwd=directory, capture_output=True, text=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('four digits', result.stderr + result.stdout)

    def test_linux_provision_preserves_config_and_saves_access_before_launch(self):
        import shlex
        import yaml
        with tempfile.TemporaryDirectory(prefix="tamanitomo's install ") as directory:
            root = Path(directory)
            kit = root/'kit'; home = root/'state'
            (kit/'kit').mkdir(parents=True)
            (kit/'.venv/bin').mkdir(parents=True)
            (kit/'launch.py').write_text('raise RuntimeError("installer must not launch the app")')
            (kit/'requirements.txt').write_text('')
            # Only package installation is mocked. The provisioner's Python runs.
            python = kit/'.venv/bin/python'
            python.write_text('#!/bin/sh\nif [ "$1" = "-m" ] && [ "$2" = "pip" ]; then exit 0; fi\nexec '+shlex.quote(sys.executable)+' "$@"\n')
            python.chmod(0o755)
            home.mkdir()
            original = {'model': {'default': 'my-local-model', 'provider': 'custom'},
                        'terminal': {'backend': 'docker'}, 'custom': {'keep': True}}
            (home/'config.yaml').write_text(yaml.safe_dump(original))
            result = subprocess.run(['bash', str(ROOT/'setup-linux.sh'), '--non-interactive', '--no-service', '--skip-hermes',
                                     '--install-dir', str(kit), '--hermes-home', str(home), '--remote-pin', '2468'],
                                    text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(yaml.safe_load((home/'config.yaml').read_text()), original)
            self.assertEqual(json.loads((home/'.tamanitomo-access.json').read_text()), {'remote_pin': '2468'})
            self.assertFalse((home/'companion.json').exists(), 'install must leave companion creation to onboarding')
            self.assertNotIn('2468', result.stdout)

    def test_termux_compatibility_entrypoint_matches_root_dry_run(self):
        with tempfile.TemporaryDirectory() as directory:
            for script in ('setup-termux.sh', 'kit/scripts/setup-termux.sh'):
                result = subprocess.run(['bash', str(ROOT/script), '--dry-run', '--upgrade'],
                                        cwd=directory, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('Dry run completed', result.stdout)

    def test_termux_installer_records_package_baseline_for_uninstall(self):
        installer = (ROOT/'setup-termux.sh').read_text()
        uninstaller = (ROOT/'uninstall-termux.sh').read_text()
        self.assertIn('.tamanitomo-termux-baseline-packages', installer)
        self.assertIn('comm -13 "$BASELINE_FILE" "$CURRENT_FILE"', uninstaller)
        self.assertNotIn('PACKAGES_TO_PURGE=(\n    python3.11', uninstaller)
