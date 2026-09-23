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


def shell_function(name, function):
    """One function from an installer, runnable on its own."""
    text = (ROOT/name).read_text()
    start = text.index(function+'() {')
    return text[start:text.index('\n}\n', start)+3]


def sync_function(name):
    return shell_function(name, 'sync_to_release')


@unittest.skipUnless(os.name == 'posix' and shutil.which('bash'), 'POSIX installer contracts')
class InstallChoiceTests(unittest.TestCase):
    """Finding an existing install asks upgrade-or-fresh rather than needing a flag."""

    FUNCTIONS = ('sync_to_release', 'choose_install_mode', 'set_aside_install')

    def choose(self, answer, non_interactive=0):
        script = (shell_function('setup-termux.sh', 'choose_install_mode')
                  + f'CYAN=; RESET=; NON_INTERACTIVE={non_interactive}; DRY_RUN=0\n'
                  + 'exec 3<<<"$1"\nchoose_install_mode /somewhere\necho "MODE=$INSTALL_MODE"\n')
        result = subprocess.run(['bash', '-c', script, 'choose', answer], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip().splitlines()[-1]

    def test_both_installers_share_the_same_functions(self):
        for function in self.FUNCTIONS:
            with self.subTest(function=function):
                self.assertEqual(shell_function('setup-linux.sh', function),
                                 shell_function('setup-termux.sh', function))

    def test_the_answer_picks_the_mode_and_upgrade_is_the_default(self):
        self.assertEqual(self.choose('2'), 'MODE=fresh')
        self.assertEqual(self.choose('1'), 'MODE=upgrade')
        self.assertEqual(self.choose(''), 'MODE=upgrade')
        self.assertEqual(self.choose('2', non_interactive=1), 'MODE=upgrade', 'unattended runs never start over')

    def test_a_fresh_install_sets_the_old_copy_aside_and_deletes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            kit = Path(directory)/'tamanitomo'; kit.mkdir(); (kit/'keep.txt').write_text('mine')
            script = shell_function('setup-linux.sh', 'set_aside_install') + 'set_aside_install "$1"\n'
            result = subprocess.run(['bash', '-c', script, 'aside', str(kit)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(kit.exists())
            old = [p for p in Path(directory).iterdir() if p.name.startswith('tamanitomo.old-')]
            self.assertEqual(len(old), 1); self.assertEqual((old[0]/'keep.txt').read_text(), 'mine')


@unittest.skipUnless(os.name == 'posix' and shutil.which('bash') and shutil.which('git'), 'POSIX installer contracts')
class ReleaseSyncTests(unittest.TestCase):
    """Running an installer again must bring an old checkout to the newest release."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.origin = root/'origin'
        env = {**os.environ, 'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@t', 'GIT_COMMITTER_NAME': 't',
               'GIT_COMMITTER_EMAIL': 't@t', 'GIT_CONFIG_GLOBAL': os.devnull}
        self.env = env
        self.git('init', '-q', '-b', 'main', str(self.origin))
        for version in ('1.0.0', '1.1.0'):
            (self.origin/'VERSION').write_text(version+'\n')
            self.git('-C', str(self.origin), 'add', 'VERSION')
            self.git('-C', str(self.origin), 'commit', '-q', '-m', version)
            self.git('-C', str(self.origin), 'tag', 'v'+version)
        (self.origin/'VERSION').write_text('unreleased\n')
        self.git('-C', str(self.origin), 'commit', '-qam', 'work in progress on main')

    def git(self, *args):
        return subprocess.run(['git', *args], check=True, capture_output=True, text=True, env=self.env).stdout

    def clone(self, at):
        kit = Path(self.tmp.name)/'kit'
        self.git('clone', '-q', str(self.origin), str(kit))
        self.git('-C', str(kit), 'reset', '-q', '--hard', at)
        return kit

    def sync(self, name, kit, fresh=0):
        script = sync_function(name) + f'DIM=; YELLOW=; RESET=\nsync_to_release "$1" "$2" {fresh}\n'
        return subprocess.run(['bash', '-c', script, 'sync', str(kit), str(self.origin)],
                              capture_output=True, text=True, env=self.env, timeout=30)

    def version(self, kit):
        return (kit/'VERSION').read_text().strip()

    def test_fresh_install_gets_the_newest_release_not_main(self):
        kit = self.clone('HEAD')
        result = self.sync('setup-linux.sh', kit, fresh=1)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.version(kit), '1.1.0')

    def test_rerun_updates_an_old_install(self):
        kit = self.clone('v1.0.0')
        result = self.sync('setup-termux.sh', kit)
        self.assertIn('Updated to release v1.1.0', result.stdout)
        self.assertEqual(self.version(kit), '1.1.0')
        self.assertIn('Already on release v1.1.0', self.sync('setup-termux.sh', kit).stdout)

    def test_local_changes_and_newer_checkouts_are_left_alone(self):
        kit = self.clone('v1.0.0')
        (kit/'VERSION').write_text('mine\n')
        self.assertIn('has local changes', self.sync('setup-linux.sh', kit).stdout)
        self.assertEqual(self.version(kit), 'mine')
        self.git('-C', str(kit), 'checkout', '-q', '--', 'VERSION')
        self.git('-C', str(kit), 'reset', '-q', '--hard', 'origin/main')
        self.assertIn('Already on release v1.1.0 or newer', self.sync('setup-linux.sh', kit).stdout)
        self.assertEqual(self.version(kit), 'unreleased')

    def test_a_release_zip_install_is_pointed_at_the_in_app_updater(self):
        kit = Path(self.tmp.name)/'zip'; kit.mkdir(); (kit/'SHA256SUMS.json').write_text('{}')
        result = self.sync('setup-linux.sh', kit)
        self.assertEqual(result.returncode, 0)
        self.assertIn('Settings > Updates', result.stdout)


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
