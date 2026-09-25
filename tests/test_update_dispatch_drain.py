"""REL-03/ACT-04: the in-app updater pauses every profile's outbox dispatcher and
waits for it to go quiet before any file on disk changes, and resumes it afterward
-- on every exit path, including a failed update. See kit/app/updates.py's
_drain_dispatchers/_resume_dispatchers/_dispatch_running/_dispatch_job_ids.
"""
import json, subprocess, sys, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts')]

import companion_config as cc
from kit.app import updates


def companion(root, **kw):
    c = cc.Companion(agent='Nova', profile='nova', hermes_root=root / 'hermes', vault=root / 'vault',
                     soul_in_vault=False, context_mode='fixed', **kw)
    c.home.mkdir(parents=True, exist_ok=True)
    c.soul_dir.mkdir(parents=True, exist_ok=True)
    c.save()
    return c


def write_dispatch_job(home, job_id='job_dispatch_1'):
    """A synthetic jobs.json with exactly one job whose rendered name matches the
    manifest's 'dispatch' key (companion_dispatch.py), the same identification
    kit/cli/scaffold.py's own refresh logic uses."""
    from kit.cli.common import load_manifest
    import companion_render as cr
    c = cc.load(home)
    manifest = load_manifest(c)
    spec = next(s for s in manifest['jobs'] if s.get('key') == 'dispatch')
    name = cr.render(spec['name'], {'AGENT': c.agent})
    (home / 'cron').mkdir(parents=True, exist_ok=True)
    (home / 'cron/jobs.json').write_text(json.dumps({'jobs': [
        {'id': job_id, 'name': name, 'schedule': {'expr': spec['expr']}, 'enabled': True}]}))
    return job_id


class DispatchJobIdentificationTests(unittest.TestCase):
    def test_the_dispatch_job_is_identified_by_manifest_key_not_a_guessed_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); c = companion(root)
            job_id = write_dispatch_job(c.home)
            self.assertEqual(updates._dispatch_job_ids(c.home), [job_id])

    def test_a_non_dispatch_job_is_not_picked_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); c = companion(root)
            (c.home / 'cron').mkdir(parents=True, exist_ok=True)
            (c.home / 'cron/jobs.json').write_text(json.dumps({'jobs': [
                {'id': 'job_pulse', 'name': 'Nova companion pulse', 'schedule': {}, 'enabled': True}]}))
            self.assertEqual(updates._dispatch_job_ids(c.home), [])

    def test_missing_or_corrupt_jobs_file_is_empty_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); c = companion(root)
            self.assertEqual(updates._dispatch_job_ids(c.home), [])

    def test_all_dispatch_jobs_covers_the_root_profile_and_sub_profiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            c = companion(root)
            job_root = write_dispatch_job(c.home)
            sub_home = root / 'hermes/profiles/rowan'
            rowan = cc.Companion(agent='Rowan', profile='rowan', hermes_root=root / 'hermes',
                                 vault=root / 'vault-rowan', context_mode='fixed')
            rowan.home.mkdir(parents=True, exist_ok=True); rowan.soul_dir.mkdir(parents=True, exist_ok=True); rowan.save()
            job_sub = write_dispatch_job(rowan.home, job_id='job_dispatch_2')
            pairs = updates._all_dispatch_jobs(root / 'hermes')
            self.assertEqual({jid for _home, jid in pairs}, {job_root, job_sub})


class DispatchRunningTests(unittest.TestCase):
    """Against the real /proc, not a mock -- the whole point is proving the process
    is genuinely observed, the same way send_quiescence.py's own tests do."""

    def test_a_real_process_with_the_marker_in_its_cmdline_is_detected(self):
        proc = subprocess.Popen([sys.executable, '-c',
            "import time; companion_dispatch_marker=1; time.sleep(5)"], cwd=str(ROOT))
        try:
            deadline = time.monotonic() + 3
            seen = False
            while time.monotonic() < deadline:
                if updates._dispatch_running():
                    seen = True
                    break
                time.sleep(0.05)
            self.assertTrue(seen, "a running process naming companion_dispatch_marker was not observed")
        finally:
            proc.kill(); proc.wait(timeout=5)
        # Give the kernel a moment to reap /proc/<pid>; then it must read as gone.
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and updates._dispatch_running():
            time.sleep(0.05)
        self.assertFalse(updates._dispatch_running())

    def test_unreadable_proc_reads_as_unknown_not_as_not_running(self):
        with patch('os.scandir', side_effect=OSError('no /proc here')):
            self.assertIsNone(updates._dispatch_running())


class DrainAndResumeTests(unittest.TestCase):
    def test_drain_pauses_waits_for_the_real_process_then_returns_and_resume_undoes_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); c = companion(root)
            job_id = write_dispatch_job(c.home)
            calls = []

            class FakeRuntime:
                def __init__(self, root): pass
                def run(self, args, home=None, timeout=None):
                    calls.append((tuple(args), home))

            proc = subprocess.Popen([sys.executable, '-c',
                "import time; companion_dispatch_marker=1; time.sleep(1.5)"], cwd=str(ROOT))
            try:
                reports = []
                paused, rt = updates._drain_dispatchers(c.hermes_root, reports.append,
                                                         runtime_cls=FakeRuntime, wait_seconds=5)
            finally:
                proc.wait(timeout=5)
            self.assertEqual(paused, [(c.home, job_id)])
            self.assertIn((('cron', 'pause', job_id), c.home), calls)
            self.assertTrue(any('Pausing' in r.get('stage', '') for r in reports))
            # The process must have actually finished before _drain_dispatchers returned.
            self.assertFalse(updates._dispatch_running())

            updates._resume_dispatchers(paused, rt)
            self.assertIn((('cron', 'resume', job_id), c.home), calls)

    def test_no_dispatch_jobs_means_no_pause_calls_and_no_wait(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); c = companion(root)
            calls = []

            class FakeRuntime:
                def __init__(self, root): pass
                def run(self, args, home=None, timeout=None): calls.append(args)

            t0 = time.monotonic()
            paused, rt = updates._drain_dispatchers(c.hermes_root, lambda r: None,
                                                     runtime_cls=FakeRuntime, wait_seconds=5)
            self.assertEqual(paused, [])
            self.assertEqual(calls, [])
            self.assertLess(time.monotonic() - t0, 1)   # nothing to wait for: must not sleep

    def test_a_pause_failure_for_one_profile_does_not_stop_the_others(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); c = companion(root)
            job_id = write_dispatch_job(c.home)

            class FailingRuntime:
                def __init__(self, root): pass
                def run(self, args, home=None, timeout=None):
                    raise ValueError('Hermes is not installed or cannot be found.')

            paused, rt = updates._drain_dispatchers(c.hermes_root, lambda r: None,
                                                     runtime_cls=FailingRuntime, wait_seconds=1)
            self.assertEqual(paused, [])   # the failed pause is never counted as paused
            updates._resume_dispatchers(paused, rt)   # must not raise: nothing to resume


class PerformUpdateDrainOrderingTests(unittest.TestCase):
    """perform_in_app_update must drain before any file changes and resume on every
    exit path, including a failed update -- verified by call order, not by re-running
    the whole download/apply flow (already covered in tests/test_updates.py)."""

    def _patched(self, root, fail_apply=False):
        order = []

        def fake_drain(root_, report, runtime_cls=None, wait_seconds=60):
            order.append('drain')
            return [('home', 'job1')], object()

        def fake_resume(paused, rt):
            order.append('resume')

        def fake_apply_pending(root_):
            order.append('apply')
            if fail_apply:
                raise ValueError('simulated apply failure')

        return order, fake_drain, fake_resume, fake_apply_pending

    def test_git_flow_drains_before_the_merge_and_resumes_after(self):
        from unittest.mock import MagicMock
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '.git').mkdir()
            (root / 'VERSION').write_text('2.2.1\n')
            (root / 'requirements.txt').write_text('fastapi\n')
            order, fake_drain, fake_resume, _ = self._patched(root)

            def fake_run(cmd, **kwargs):
                res = MagicMock(); res.returncode = 0; res.stdout = ''; res.stderr = ''
                if cmd[:2] == ['git', 'show']:
                    res.stdout = '2.3.0' if cmd[-1].endswith(':VERSION') else 'fastapi'
                elif cmd[:2] == ['git', 'merge']:
                    order.append('merge')
                return res

            with patch('subprocess.run', side_effect=fake_run), \
                 patch('kit.app.updates.check_github_update',
                       return_value={'checked': True, 'has_update': True, 'latest_version': '2.3.0', 'tag': 'v2.3.0'}), \
                 patch('kit.app.updates._drain_dispatchers', side_effect=fake_drain), \
                 patch('kit.app.updates._resume_dispatchers', side_effect=fake_resume), \
                 patch('threading.Thread'):
                updates.perform_in_app_update(lambda r: None, root=root)
            self.assertEqual(order, ['drain', 'merge', 'resume'])

    def test_a_failed_apply_still_resumes_the_dispatcher(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            order, fake_drain, fake_resume, fake_apply = self._patched(root, fail_apply=True)
            with patch('kit.app.updates.check_github_update',
                       return_value={'checked': True, 'has_update': True, 'latest_version': '2.3.0',
                                    'tag': 'v2.3.0', 'download_url': 'https://x', 'digest': None}), \
                 patch('kit.app.updates._drain_dispatchers', side_effect=fake_drain), \
                 patch('kit.app.updates._resume_dispatchers', side_effect=fake_resume), \
                 patch('kit.app.updates.stage', return_value=None), \
                 patch('update_release._apply_pending', side_effect=lambda r: fake_apply(r)), \
                 patch('urllib.request.urlopen'), \
                 patch('kit.app.updates._install_dependencies'):
                (root / 'VERSION').write_text('2.2.1\n')
                (root / 'SHA256SUMS.json').write_text('{}')
                (root / '.pending-update').mkdir()
                (root / '.pending-update/VERSION').write_text('2.3.0')
                with self.assertRaises(ValueError):
                    updates.perform_in_app_update(lambda r: None, root=root)
            self.assertEqual(order, ['drain', 'apply', 'resume'])


if __name__ == '__main__':
    unittest.main()
