"""The image-timeline command."""

from __future__ import annotations
import companion_platform as cp
import companion_render as cr
import json
import os
import subprocess
import companion_wizard as wiz
from .common import _read_jobs, mapping, print, resolve
from .questions import pick_key
from .scaffold import install_jobs


def cmd_timeline(args):
    """Opt in/out of local images, inspect captures, or prune expired timeline files."""
    import companion_timeline as timeline

    c = resolve(args, require_config=True)
    if args.state in ("on", "off"):
        if args.state == "on" and c.image_style in ("none", "unset"):
            if not wiz._tty():
                raise ValueError(
                    "Set an image style in companion.json before enabling the timeline"
                )
            c.image_style = pick_key(
                "Choose a timeline image style",
                [
                    (key, value["label"] + " — " + value["blurb"])
                    for key, value in cr.load_styles().items()
                    if key not in ("none", "unset")
                ],
            )
        c.image_timeline = args.state == "on"
        c.save()
        if c.image_timeline:
            (c.data / "image-timeline").mkdir(parents=True, exist_ok=True)
            timeline.prune(c)
        report = []
        install_jobs(c, mapping(c, {}), report)
        for line in report:
            print(line)
        if c.image_timeline:
            jobs = _read_jobs(c.home / "cron/jobs.json")["jobs"]
            job = next(
                (j for j in jobs if j.get("name") == c.agent + " image timeline"), None
            )
            if job and bool(job.get("enabled")) != c.cron_active:
                result = subprocess.run(
                    cp.hermes_command(
                        "cron", "resume" if c.cron_active else "pause", job["id"]
                    ),
                    capture_output=True,
                    text=True,
                    timeout=30,
                    env={**os.environ, "HERMES_HOME": str(c.home)},
                )
                if result.returncode:
                    raise ValueError(
                        "Could not update image timeline schedule; run repair"
                    )
    result = timeline.prune(c)
    captures = [row for _, row in timeline.records(c)]
    counts = {
        status: sum(row.get("status") == status for row in captures)
        for status in ("saved", "pending", "failed")
    }
    failures = sorted(
        (row for row in captures if row.get("status") == "failed"),
        key=lambda row: row["created_at"],
    )
    jobs = _read_jobs(c.home / "cron/jobs.json")["jobs"]
    generation = next(
        (job for job in jobs if job.get("name") == c.agent + " image timeline"), {}
    )
    cleanup = next(
        (job for job in jobs if job.get("name") == c.agent + " image timeline cleanup"),
        {},
    )
    print(
        json.dumps(
            {
                "enabled": c.image_timeline,
                "generation_scheduled": bool(generation.get("enabled")),
                "cleanup_scheduled": bool(cleanup.get("enabled")),
                "maximum_image_requests_per_day": 96,
                "retention_days": 30,
                "gallery": str(c.data / "image-timeline/index.html"),
                "captures": counts,
                "latest_failure": failures[-1].get("error") if failures else None,
                "cleanup": result,
            },
            indent=2,
        )
    )
    bad = bool(generation.get("enabled")) != (c.image_timeline and c.cron_active)
    if c.image_timeline:
        bad = bad or not cleanup.get("enabled") or not cleanup.get("no_agent")
    return 1 if bad or (c.home / "companion-pending-jobs.json").exists() else 0
