"""Shared validation, human-record preservation, and routine synchronization."""

import contextlib
import shutil

import companion_platform as cp


def validate(c):
    c.__post_init__()
    import companion_render as render

    if c.image_style not in render.load_styles():
        raise ValueError("Unknown image style")
    if c.image_timeline and c.image_style in ("none", "unset"):
        raise ValueError("Choose an image style before enabling the image timeline")


@contextlib.contextmanager
def preserve_human_records(old, updated):
    """Preserve facts when their location changes; never merge conflicting ledgers."""
    copied = []
    with cp.file_lock(old.vault / ".companion-human-migration.lock"):
        copies = []
        if old.human_dir != updated.human_dir and old.human_dir.exists():
            if old.human_dir.is_symlink():
                raise ValueError(
                    "Human records contain a link; move them explicitly first"
                )
            for source in old.human_dir.rglob("*"):
                if source.is_symlink():
                    raise ValueError(
                        "Human records contain a link; move them explicitly first"
                    )
                if not source.is_file():
                    continue
                dest = updated.human_dir / source.relative_to(old.human_dir)
                for parent in (dest, *dest.parents):
                    if parent == updated.human_dir:
                        break
                    if parent.is_symlink():
                        raise ValueError("Human record destination contains a link")
                if dest.exists() and dest.read_bytes() != source.read_bytes():
                    raise ValueError(
                        "The new human-record location contains different records. Resolve them before changing sharing or the human name."
                    )
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


def resume_timeline(c, runtime):
    """Resume the companion's photo timeline job if it is paused; returns a report line."""
    from kit.cli.common import _read_jobs

    path = c.home / "cron/jobs.json"
    jobs = _read_jobs(path).get("jobs", []) if path.exists() else []
    job = next((j for j in jobs if j.get("name") == c.agent + " image timeline"), None)
    if job is None:
        return "  photos on; the timeline job will be added by repair"
    if job.get("enabled"):
        return "  photos on; the timeline job is already running"
    result = runtime.run(["cron", "resume", job["id"]], home=c.home, check=False)
    if result.returncode:
        return "  ! photos on, but the timeline job could not be resumed; run repair"
    return "  photos on; the timeline job is running again"


def synchronize(app, runtime, old, updated):
    """Queue the same job update regardless of which editor saved the settings."""
    cadence = {
        "quiet_start",
        "quiet_end",
        "autonomy_windows",
        "image_timeline",
        "image_style",
        "image_interval_minutes",
        "outreach",
        "outreach_per_day",
        "timezone",
        # The outreach policy her prompts quote says whether she can reach a watch.
        "device_bridge_url",
    }
    if not any(getattr(old, key) != getattr(updated, key) for key in cadence):
        return None
    if not (updated.home / "cron/jobs.json").exists():
        return None

    def sync(report):
        from kit.cli.scaffold import refresh_schedules
        from .runtime import redact

        report("Preferences saved; updating background jobs")
        sync_report = []
        refresh_schedules(old, updated, sync_report, run_cmd=runtime.run)
        if updated.image_timeline and not old.image_timeline and updated.cron_active:
            # Switching photos off pauses the timeline job (scaffold.install_jobs), so
            # switching them back on has to resume it, as the CLI toggle always did.
            # Only on this edge: a photo job someone paused by hand while photos were on
            # stays paused through every other save.
            sync_report.append(resume_timeline(updated, runtime))
        for line in sync_report:
            report(line.strip())
        result = runtime.run(
            ["--home", str(updated.home), "repair"],
            home=updated.home,
            kit=True,
            timeout=600,
            check=False,
        )
        # Repair ends with a full health check, which flags standing advisories that
        # have nothing to do with this save. Only exit code 1 means a job or schedule
        # is actually wrong; 2 means the jobs are fine and something else needs eyes.
        if result.returncode == 1:
            raise ValueError(
                "Preferences were saved, but background jobs could not be updated. "
                "Open Jobs & health and repair the routine. "
                + redact(result.stderr or result.stdout)[-2000:]
            )
        note = "Preferences saved and job synchronization completed. Review Jobs & health for any protected custom schedules."
        if result.returncode:
            note = (
                "Preferences saved and background jobs updated. The health check flagged "
                "unrelated items — see Jobs & health when convenient."
            )
        return {"output": redact(result.stdout or result.stderr), "note": note}

    return app.state.operations.submit(
        str(runtime.root),
        "Sync preferences to background jobs",
        sync,
        profile=updated.profile or "default",
    )
