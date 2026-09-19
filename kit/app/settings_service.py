"""Shared validation, human-record preservation, and routine synchronization."""
import contextlib
import shutil

import companion_platform as cp


def validate(c):
    c.__post_init__()
    import companion_render as render
    if c.image_style not in render.load_styles():
        raise ValueError('Unknown image style')
    if c.image_timeline and c.image_style in ('none', 'unset'):
        raise ValueError('Choose an image style before enabling the image timeline')


@contextlib.contextmanager
def preserve_human_records(old, updated):
    """Preserve facts when their location changes; never merge conflicting ledgers."""
    copied = []
    with cp.file_lock(old.vault / '.companion-human-migration.lock'):
        copies = []
        if old.human_dir != updated.human_dir and old.human_dir.exists():
            if old.human_dir.is_symlink():
                raise ValueError('Human records contain a link; move them explicitly first')
            for source in old.human_dir.rglob('*'):
                if source.is_symlink():
                    raise ValueError('Human records contain a link; move them explicitly first')
                if not source.is_file():
                    continue
                dest = updated.human_dir / source.relative_to(old.human_dir)
                for parent in (dest, *dest.parents):
                    if parent == updated.human_dir:
                        break
                    if parent.is_symlink():
                        raise ValueError('Human record destination contains a link')
                if dest.exists() and dest.read_bytes() != source.read_bytes():
                    raise ValueError('The new human-record location contains different records. Resolve them before changing sharing or the human name.')
                if not dest.exists():
                    copies.append((source, dest))
        try:
            for source, dest in copies:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)
                copied.append(dest)
            yield
        except Exception:
            for dest in copied:
                dest.unlink(missing_ok=True)
            raise


def synchronize(app, runtime, old, updated):
    """Queue the same job update regardless of which editor saved the settings."""
    cadence = {'quiet_start', 'quiet_end', 'autonomy_windows', 'image_timeline',
               'image_style', 'image_interval_minutes', 'outreach', 'outreach_per_day', 'timezone'}
    if not any(getattr(old, key) != getattr(updated, key) for key in cadence):
        return None
    if not (updated.home / 'cron/jobs.json').exists():
        return None

    def sync(report):
        from kit.cli.common import load_manifest, mapping, _read_jobs
        import companion_render as render
        from .runtime import redact
        before, after = mapping(old, {}), mapping(updated, {})
        specs = {render.render(spec['name'], before): spec
                 for spec in load_manifest(old)['jobs']}
        next_specs = {render.render(spec['name'], after): spec
                      for spec in load_manifest(updated)['jobs']}
        report('Preferences saved; updating background jobs')
        for job in _read_jobs(updated.home / 'cron/jobs.json')['jobs']:
            spec = specs.get(job.get('name'))
            next_spec = next_specs.get(job.get('name'))
            if spec and next_spec:
                was, now = render.render(spec['expr'], before), render.render(next_spec['expr'], after)
                if was != now and job.get('schedule', {}).get('expr') == was:
                    runtime.run(['cron', 'edit', job['id'], '--schedule', now], home=updated.home)
        result = runtime.run(['--home', str(updated.home), 'repair'], home=updated.home,
                             kit=True, timeout=600, check=False)
        if result.returncode:
            raise ValueError('Preferences were saved, but background jobs could not be updated. '
                             'Open Jobs & health and repair the routine. ' + redact(result.stderr or result.stdout)[-2000:])
        return {'output': redact(result.stdout or result.stderr),
                'note': 'Preferences saved and job synchronization completed. Review Jobs & health for any protected custom schedules.'}

    return app.state.operations.submit(str(runtime.root), 'Sync preferences to background jobs',
                                       sync, profile=updated.profile or 'default')
