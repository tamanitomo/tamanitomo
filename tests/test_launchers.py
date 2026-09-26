"""Bootstrap locks and portable entry points use only synthetic directories."""
import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import launch
import update_release


def test_bootstrap_lock_does_not_grow_on_repeated_launch(tmp_path):
    with patch.object(launch, 'ROOT', tmp_path):
        for _ in range(3):
            with launch.setup_lock():
                pass
    assert (tmp_path / '.bootstrap.lock').read_bytes() == b'0'


def test_update_lock_releases_and_does_not_grow(tmp_path):
    for _ in range(3):
        with update_release.runtime_lock(tmp_path):
            pass
    assert (tmp_path / '.runtime.lock').read_bytes() == b'0'


def test_bootstrap_forwards_unicode_and_spaced_arguments(tmp_path):
    import os
    requirements = b'\n'
    (tmp_path / 'requirements.txt').write_bytes(requirements)
    python = tmp_path / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    python.parent.mkdir(parents=True)
    python.touch()
    (tmp_path / '.venv/.tamanitomo-requirements').write_text(hashlib.sha256(requirements).hexdigest() + '\n')
    arguments = ['app', '--home', str(tmp_path / 'My companion 雪')]
    target = 'subprocess.call' if os.name == 'nt' else 'os.execv'
    with patch.object(launch, 'ROOT', tmp_path), patch('update_release.apply_pending'), patch.object(launch.subprocess, 'run') as install, patch('launch.' + target) as run:
        launch.bootstrap(arguments)
    install.assert_not_called()
    command = run.call_args.args[0] if os.name == 'nt' else run.call_args.args[1]
    assert command == [str(python), str(tmp_path / 'bin/tamanitomo'), *arguments]
