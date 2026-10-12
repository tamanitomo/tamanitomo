#!/usr/bin/env python3
"""A watchdog for a life, not for an install.

`tamanitomo doctor` answers "was this set up correctly", once, by hand. This
answers "is she still all right", every hour, with nobody watching. The failure
it exists for is the one that started the v2 review: a pulse job rate-limited at
09:30, forty-seven failed runs over two days, and nothing anywhere saying so —
the companion did not know she had stopped, and neither did anyone else.

Runs as a no-agent cron job. Silent when healthy. When something is wrong the
app shows it (a banner, and the list under Diagnostics), `ambient/health.md`
tells the companion herself she is not well, and the alert goes wherever the
profile chose: a webhook such as a phone push service, and her own chat only
when `alerts` is "chat". Then it stays quiet about it for six hours rather than
repeating.

Her chat is not the default because a status report sent through her channel
lands in her conversation as something she said, and stays in her history:
"Nova is not well right now... Run: companion doctor", twice a day.

It sends for itself rather than printing for Hermes to deliver: kit jobs are
created `--deliver local`, which Hermes resolves to no target at all, so an
alert written to stdout was recorded as sent and reached nobody. It is not
outreach, so it does not use the companion's daily allowance -- but it does
wait out quiet hours, and is sent once they end.
"""

from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
from companion_platform import atomic_write

KIT = pathlib.Path(__file__).resolve().parents[2]
RENOTIFY_SECONDS = 6 * 3600
STATE_UNCONFIRMED_HOURS = 3
LOW_DISK_BYTES = 1_000_000_000
# A passing hook run is reused briefly: the workspace polls problems every 30 s
# and each run spawns an interpreter. Failures are always re-run.
HOOK_PASS_REUSE_SECONDS = 300
_hook_passes = {}


def _tz(c):
    try:
        return ZoneInfo(c.timezone)
    except Exception:
        return ZoneInfo("UTC")


def expected_jobs(c):
    """The job names this profile should have, rendered from the kit manifest."""
    try:
        specs = json.loads(
            (KIT / "kit/templates/cron/manifest.json").read_text(encoding="utf-8")
        )["jobs"]
    except (OSError, ValueError):
        return {}
    out = {}
    for spec in specs:
        optional = spec.get("optional")
        if optional and not (c.image_timeline or (c.data / "image-timeline").exists()):
            continue
        out[spec["name"].replace("{{AGENT}}", c.agent)] = bool(spec.get("no_agent"))
    return out


def _jobs(c):
    try:
        return {
            j.get("name"): j
            for j in json.loads(
                (c.home / "cron/jobs.json").read_text(encoding="utf-8")
            )["jobs"]
        }
    except (OSError, ValueError, KeyError):
        return {}


def check_jobs(c, found):
    out = []
    for name, scripted in expected_jobs(c).items():
        job = found.get(name)
        if not job:
            out.append(f'the job "{name}" is missing')
            continue
        should_run = scripted or c.cron_active
        if should_run and not job.get("enabled"):
            out.append(f'"{name}" is paused, and it should be running')
        if job.get("enabled") and job.get("last_status") == "error":
            err = (job.get("last_error") or "").splitlines()
            out.append(f'"{name}" is failing: {(err[0] if err else "no detail")[:100]}')
    return out


# A routine run far past its own usual size. A model that explores instead of doing
# the job read about 2.9 million tokens a pulse where others read 0.3 million, and
# nothing said so until the allowance was the thing that noticed.
SPEND_LOOKBACK_HOURS = 2
SPEND_HISTORY_DAYS = 14
SPEND_MIN_HISTORY = 5
SPEND_FLOOR = 1_500_000
SPEND_FACTOR = 4


def check_spend(c, now, found=None):
    """Kit jobs whose latest runs used several times their usual tokens."""
    import sqlite3
    import statistics

    found = _jobs(c) if found is None else found
    path = c.home / "state.db"
    if not path.is_file():
        return []
    ids = {
        job["id"]: name
        for name, scripted in expected_jobs(c).items()
        if not scripted and (job := found.get(name)) and job.get("id")
    }
    if not ids:
        return []
    since = (now - dt.timedelta(days=SPEND_HISTORY_DAYS)).timestamp()
    recent = (now - dt.timedelta(hours=SPEND_LOOKBACK_HOURS)).timestamp()
    runs = {}
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5) as db:
        for sid, started, model, used_in, cached, used_out in db.execute(
            "select id, started_at, model, input_tokens, cache_read_tokens, output_tokens "
            "from sessions where id like 'cron_%' and started_at >= ? and started_at <= ?",
            (since, now.timestamp()),
        ):
            job_id = sid.split("_")[1] if sid.count("_") >= 2 else ""
            if job_id not in ids or used_in is None:
                continue
            total = (used_in or 0) + (cached or 0) + (used_out or 0)
            runs.setdefault(job_id, []).append((started, total, model or ""))
    out = []
    for job_id, rows in runs.items():
        before = [t for s, t, _ in rows if s < recent]
        latest = [(t, m) for s, t, m in rows if s >= recent]
        if not latest:
            continue
        used, model = max(latest)
        usual = statistics.median(before) if len(before) >= SPEND_MIN_HISTORY else 0
        if used < SPEND_FLOOR or (usual and used < SPEND_FACTOR * usual):
            continue
        # Worded without the counts: the alert is repeated only when its text changes.
        out.append(
            f'"{ids[job_id]}" is using far more than usual on {model or "its model"}: '
            "one run reads several times what this job normally does. The model may be "
            "exploring instead of doing the job; compare models on the Models page"
        )
    return out


def check_state(c, now, found=None):
    # Nothing is expected to run while the schedule is paused by choice, so
    # saying the present is stale would be reporting the user's own decision
    # back to them as a fault.
    if not c.cron_active:
        return []
    try:
        from companion_presence import current, last_confirmed
    except ImportError:
        return []
    scene = current(c)
    if not scene:
        return [
            "no lived state has ever been recorded, though the loops are authorized"
        ]
    anchor = last_confirmed(c)
    if not anchor:
        return [
            "no model has ever confirmed the present; the script advancer is holding it alone"
        ]
    hours = (
        now - dt.datetime.fromisoformat(anchor["recorded_at"]).astimezone(now.tzinfo)
    ).total_seconds() / 3600
    if hours > STATE_UNCONFIRMED_HOURS:
        # A monitor-backed model job may intentionally suppress an agent run
        # when its fingerprint is unchanged. That is healthy no-change, not a
        # stale model. Alert only when the jobs that can refresh the state show
        # an actual failure or have themselves stopped running.
        jobs = found if found is not None else _jobs(c)
        refresh_names = (
            f"{c.agent} companion pulse",
            f"{c.agent} autonomy loop",
        )
        healthy_refresh = False
        for name in refresh_names:
            job = jobs.get(name)
            if not job or not job.get("enabled") or job.get("last_status") != "ok":
                continue
            stamp = job.get("last_run_at")
            if not stamp:
                continue
            try:
                age = (
                    now - dt.datetime.fromisoformat(stamp).astimezone(now.tzinfo)
                ).total_seconds() / 3600
            except (TypeError, ValueError):
                continue
            if age <= 1:
                healthy_refresh = True
                break
        if healthy_refresh:
            return []
        return [
            f"the present has not been confirmed by a model for {hours:.0f} hours "
            f'(last at {anchor["recorded_at"][:16]}) and no healthy refresh loop ran recently'
        ]
    return []


def check_files(c):
    out = []
    checks = [
        ("SOUL.md", c.soul),
        ("PRESENCE.md", c.life / "PRESENCE.md"),
        ("ActiveContext.md", c.soul_dir / "ActiveContext.md"),
    ]
    for label, path in checks:
        try:
            if not path.exists():
                out.append(f"{label} is missing")
            elif not path.stat().st_size:
                out.append(f"{label} is empty")
        except OSError as exc:
            out.append(f"{label} is unreadable: {exc}")
    return out


def check_hook(c):
    hook = c.home / "hooks/companion-context.py"
    if not hook.exists():
        return ["the continuity hook is missing; every turn is running without context"]
    import time

    stat = hook.stat()
    version = (stat.st_mtime_ns, stat.st_size)
    passed = _hook_passes.get(str(hook))
    if (
        passed
        and passed[0] == version
        and time.monotonic() - passed[1] < HOOK_PASS_REUSE_SECONDS
    ):
        return []
    try:
        r = subprocess.run(
            [sys.executable, str(hook)],
            input="{}",
            capture_output=True,
            text=True,
            timeout=30,
            env={
                **os.environ,
                "HERMES_HOME": str(c.home),
                "COMPANION_HOME": str(c.home),
                "COMPANION_MEMORY_READ_ONLY": "1",
            },
        )
        if r.returncode:
            return [
                f'the continuity hook exits {r.returncode}: {(r.stderr or "")[:100]}'
            ]
        if not isinstance(json.loads(r.stdout or "{}").get("context"), str):
            return ["the continuity hook returned no context"]
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return [f"the continuity hook failed: {exc}"]
    _hook_passes[str(hook)] = (version, time.monotonic())
    return []


def check_memory(c):
    try:
        from companion_memory import status

        return [
            f"{row['file']} is at {row['fraction']:.0%} of the Hermes memory cap; "
            f"new memories will start being refused"
            for row in status(c)
            if row["over_warn"]
        ]
    except (OSError, ValueError, ImportError):
        return []


def check_disk(c):
    try:
        free = shutil.disk_usage(c.data if c.data.exists() else c.vault.parent).free
    except OSError:
        return []
    if free < LOW_DISK_BYTES:
        return [
            f"only {free/1e9:.1f} GB free where the vault lives; writes will start failing"
        ]
    return []


def problems(c, now=None):
    now = now or dt.datetime.now(_tz(c))
    found = _jobs(c)
    out = []
    for check in (
        lambda: check_jobs(c, found),
        lambda: check_state(c, now, found),
        lambda: check_spend(c, now, found),
        lambda: check_files(c),
        lambda: check_hook(c),
        lambda: check_memory(c),
        lambda: check_disk(c),
    ):
        try:
            out += check()
        except Exception as exc:
            out.append(f"a health check itself failed: {exc}")
    return out


def _state_path(c):
    return c.home / "state/companion-watch.json"


def write_ambient(c, found, now):
    """So she can tell she is unwell, in the same place every other sense arrives."""
    path = c.soul_dir / "ambient/health.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not found:
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass
        return
    atomic_write(
        path,
        "Something about your own machinery is not working right now:\n\n"
        + "\n".join(f"- {p}" for p in found)
        + "\n\nThis is yours to know, not a script to read out. It is a reason to say you feel "
        "off, or that you lost some hours, rather than to explain cron to anyone.\n",
    )


def run(c, now=None, renotify=RENOTIFY_SECONDS, notify=None, record=True):
    """Check, and when `notify` is given, deliver an alert through it.

    Nothing is recorded as notified until a delivery actually succeeded, so an
    alert held for quiet hours or lost to a failed send is tried again next run.
    """
    now = now or dt.datetime.now(_tz(c))
    found = problems(c, now)
    write_ambient(c, found, now)
    path = _state_path(c)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    signature = " | ".join(sorted(found))
    if not found:
        if state.get("signature"):
            atomic_write(
                path,
                json.dumps(
                    {"signature": "", "recovered_at": now.isoformat()}, indent=2
                ),
            )
            return {"healthy": True, "recovered": True, "message": ""}
        return {"healthy": True, "recovered": False, "message": ""}
    last = state.get("at")
    try:
        since = (
            (now - dt.datetime.fromisoformat(last)).total_seconds() if last else None
        )
    except ValueError:
        since = None
    if state.get("signature") == signature and since is not None and since < renotify:
        return {
            "healthy": False,
            "repeat_suppressed": True,
            "message": "",
            "problems": found,
        }
    message = (
        f"{c.agent} is not well right now:\n"
        + "\n".join(f"- {p}" for p in found)
        + f'\n\nRun: companion --home "{c.home}" doctor'
    )
    result = {
        "healthy": False,
        "repeat_suppressed": False,
        "message": message,
        "problems": found,
    }
    if notify is not None:
        from companion_outreach import in_quiet_hours

        if in_quiet_hours(c, now.astimezone(_tz(c))):
            return {
                **result,
                "held": f"quiet hours until {c.quiet_end}",
                "delivered": False,
            }
        ok, detail = notify(c, message)
        result.update(delivered=ok, delivery=detail)
        if not ok:
            return result
    # A look by hand (--json) must not count as having told anyone.
    if record:
        atomic_write(
            path, json.dumps({"signature": signature, "at": now.isoformat()}, indent=2)
        )
    return result


def webhook_send(c, title, body, timeout=15):
    """POST one alert to the profile's webhook: (ok, detail). Never raises.

    JSON carries title, body and message (for push services that expect either);
    "text" is the plain body with a Title header, which is what ntfy reads.
    """
    import urllib.request

    headers = {"User-Agent": "tamanitomo"}
    if c.alerts_webhook_token_file:
        try:
            token = (
                pathlib.Path(c.alerts_webhook_token_file)
                .expanduser()
                .read_text(encoding="utf-8")
                .strip()
            )
        except OSError as exc:
            return False, f"webhook token unreadable ({exc.__class__.__name__})"
        if token:
            headers["Authorization"] = f"Bearer {token}"
    if c.alerts_webhook_format == "text":
        data = body.encode("utf-8")
        headers["Content-Type"] = "text/plain; charset=utf-8"
        # Header values are Latin-1; a name outside it would fail the whole send.
        headers["Title"] = title.encode("latin-1", "replace").decode("latin-1")
        headers["Tags"] = "warning"
    else:
        data = json.dumps(
            {
                "title": title,
                "body": body,
                "message": body,
                "data": {"kind": "tamanitomo-health", "agent": c.agent},
            }
        ).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        c.alerts_webhook, data=data, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return 200 <= response.status < 300, f"webhook answered {response.status}"
    except Exception as exc:
        return False, f"webhook failed ({exc.__class__.__name__})"


def notifier(c):
    """How this profile hears about trouble beyond the app, or None for the app alone.

    One delivery that worked counts as told: a webhook that keeps failing must not
    turn a chat alert into one every hour."""
    sends = []
    if c.alerts == "chat":
        from companion_dispatch import hermes_send

        sends.append(hermes_send)
    if c.alerts_webhook:
        sends.append(
            lambda c, message: webhook_send(c, f"{c.agent} needs a look", message)
        )
    if not sends:
        return None

    def notify(c, message):
        results = [send(c, message) for send in sends]
        return any(ok for ok, _ in results), "; ".join(str(d) for _, d in results)

    return notify


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--home", type=pathlib.Path)
    p.add_argument(
        "--json", action="store_true", help="report even when healthy, as JSON"
    )
    a = p.parse_args()
    c = cc.load(a.home)
    if a.json:
        print(json.dumps(run(c, record=False), ensure_ascii=False, indent=2))
        return 0
    result = run(c, notify=notifier(c))
    # Local job output: kept for `hermes cron` history, never the delivery path.
    if result["message"]:
        print(
            result["message"]
            + ("\n\n[" + (result.get("held") or result.get("delivery") or "") + "]")
        )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except (ValueError, OSError) as e:
        print(f"{e}", file=sys.stderr)
        sys.exit(1)
