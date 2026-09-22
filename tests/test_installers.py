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


def termux_helpers():
    """The venv/pip helpers from setup-termux.sh, runnable on their own."""
    text = (ROOT/'setup-termux.sh').read_text()
    start = text.index('python_missing_error() {')
    end = text.index('\n}\n', text.index('pip_install() {')) + 3
    return text[start:end]


@unittest.skipUnless(os.name == 'posix' and shutil.which('bash'), 'POSIX installer contracts')
class TermuxPythonTests(unittest.TestCase):
    """The aarch64 wheelhouse is cp311-only; any other venv Python means maturin builds."""

    def run_helpers(self, root, script, python311=True):
        tools = root/'tools'
        tools.mkdir()
        for name in ('find', 'wc', 'rm', 'mktemp', 'tail', 'sed', 'mkdir', 'cat', 'chmod', 'dirname'):
            (tools/name).symlink_to(shutil.which(name))
        if python311:
            # `python3.11 -m venv DIR` makes a venv whose python reports 3.11
            # and whose pip fails with a recognisable message.
            fake = tools/'python3.11'
            fake.write_text('#!' + shutil.which('bash') + '\n'
                            'mkdir -p "$3/bin"\n'
                            "printf '#!%s\\n' \"$BASH\" > \"$3/bin/python\"\n"
                            "cat >> \"$3/bin/python\" <<'PY'\n"
                            'if [ "$1" = -c ]; then echo 3.11; exit 0; fi\n'
                            'if [ "$3" = install ] && [ "$4" != --upgrade ]; then echo "wheel is not supported on this platform" >&2; exit 1; fi\n'
                            'PY\n'
                            'chmod +x "$3/bin/python"\n')
            fake.chmod(0o755)
        prelude = ("set -euo pipefail\nIS_TERMUX=1\nWHEELHOUSE_PY=3.11\nRED= YELLOW= RESET=\n"
                   f"WHEELS_DIR='{root}/wheels'\n")
        return subprocess.run([shutil.which('bash'), '-c', prelude + termux_helpers() + script],
                              env={'PATH': str(tools), 'HOME': str(root)},
                              capture_output=True, text=True, timeout=10)

    def test_missing_python311_stops_with_the_fix(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_helpers(Path(directory), f'ensure_venv "{directory}/venv"', python311=False)
            self.assertEqual(result.returncode, 1)
            self.assertIn('pkg install python3.11', result.stderr)
            self.assertFalse((Path(directory)/'venv').exists())

    def test_venv_left_on_another_python_is_rebuilt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stale = root/'venv'/'bin'/'python'
            stale.parent.mkdir(parents=True)
            stale.write_text('#!' + shutil.which('bash') + '\necho 3.13\n')
            stale.chmod(0o755)
            result = self.run_helpers(root, f'ensure_venv "{root}/venv"; venv_python_version "{root}/venv"')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('uses Python 3.13', result.stdout)
            self.assertTrue(result.stdout.strip().endswith('3.11'))

    def test_wheelhouse_failure_is_shown_not_swallowed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'wheels').mkdir()
            for n in range(10):
                (root/'wheels'/f'pkg{n}-1.0-cp311-cp311-linux_aarch64.whl').touch()
            result = self.run_helpers(root, f'ensure_venv "{root}/venv"; install_wheelhouse "{root}/venv"')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('wheel is not supported on this platform', result.stdout)

    def test_pip_failure_explains_maturin_prerequisites(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_helpers(root, f'ensure_venv "{root}/venv"; pip_install "{root}/venv" -r req.txt')
            self.assertEqual(result.returncode, 1)
            self.assertIn('maturin', result.stderr)
            self.assertIn('ANDROID_API_LEVEL', result.stderr)

    def test_package_install_is_not_all_or_nothing(self):
        installer = (ROOT/'setup-termux.sh').read_text()
        self.assertNotIn('libheif || true', installer)
        self.assertIn('FAILED_PACKAGES+=("$package")', installer)
        self.assertNotIn('*.whl >/dev/null 2>&1 || true', installer)
        self.assertNotIn('python3 -m venv', installer)
