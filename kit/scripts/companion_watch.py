#!/usr/bin/env python3
"""A watchdog for a life, not for an install.

`tamanitomo doctor` answers "was this set up correctly", once, by hand. This
answers "is she still all right", every hour, with nobody watching. The failure
it exists for is the one that started the v2 review: a pulse job rate-limited at
09:30, forty-seven failed runs over two days, and nothing anywhere saying so —
the companion did not know she had stopped, and neither did anyone else.

Runs as a no-agent cron job. Silent when healthy: Hermes delivers stdout, and
empty stdout means no message. When something is wrong it says so once, writes
the same text into `ambient/health.md` so the companion herself can tell she is
not well, and then stays quiet about it for six hours rather than repeating.
"""
from __future__ import annotations
import argparse, datetime as dt, json, os, pathlib, shutil, subprocess, sys
from zoneinfo import ZoneInfo
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
from companion_platform import atomic_write

KIT=pathlib.Path(__file__).resolve().parents[2]
RENOTIFY_SECONDS=6*3600
STATE_UNCONFIRMED_HOURS=3
LOW_DISK_BYTES=1_000_000_000

def _tz(c):
    try:return ZoneInfo(c.timezone)
    except Exception:return ZoneInfo('UTC')

def expected_jobs(c):
    """The job names this profile should have, rendered from the kit manifest."""
    try:
        specs=json.loads((KIT/'kit/templates/cron/manifest.json').read_text(encoding='utf-8'))['jobs']
    except (OSError,ValueError):return {}
    out={}
    for spec in specs:
        optional=spec.get('optional')
        if optional and not (c.image_timeline or (c.data/'image-timeline').exists()):continue
        out[spec['name'].replace('{{AGENT}}',c.agent)]=bool(spec.get('no_agent'))
    return out

def _jobs(c):
    try:return {j.get('name'):j for j in json.loads((c.home/'cron/jobs.json').read_text(encoding='utf-8'))['jobs']}
    except (OSError,ValueError,KeyError):return {}

def check_jobs(c,found):
    out=[]
    for name,scripted in expected_jobs(c).items():
        job=found.get(name)
        if not job:
            out.append(f'the job "{name}" is missing');continue
        should_run=scripted or c.cron_active
        if should_run and not job.get('enabled'):
            out.append(f'"{name}" is paused, and it should be running')
        if job.get('enabled') and job.get('last_status')=='error':
            err=(job.get('last_error') or '').splitlines()
            out.append(f'"{name}" is failing: {(err[0] if err else "no detail")[:100]}')
    return out

def check_state(c,now):
    # Nothing is expected to run while the schedule is paused by choice, so
    # saying the present is stale would be reporting the user's own decision
    # back to them as a fault.
    if not c.cron_active:return []
    try:
        from companion_presence import current,last_confirmed
    except ImportError:return []
    scene=current(c)
    if not scene:return ['no lived state has ever been recorded, though the loops are authorized']
    anchor=last_confirmed(c)
    if not anchor:
        return ['no model has ever confirmed the present; the script advancer is holding it alone']
    hours=(now-dt.datetime.fromisoformat(anchor['recorded_at']).astimezone(now.tzinfo)).total_seconds()/3600
    if hours>STATE_UNCONFIRMED_HOURS:
        return [f'the present has not been confirmed by a model for {hours:.0f} hours '
                f'(last at {anchor["recorded_at"][:16]}) — the loops are probably failing']
    return []

def check_files(c):
    out=[]
    checks=[('SOUL.md',c.soul),('PRESENCE.md',c.life/'PRESENCE.md'),
            ('ActiveContext.md',c.soul_dir/'ActiveContext.md')]
    for label,path in checks:
        try:
            if not path.exists():out.append(f'{label} is missing')
            elif not path.stat().st_size:out.append(f'{label} is empty')
        except OSError as exc:out.append(f'{label} is unreadable: {exc}')
    return out

def check_hook(c):
    hook=c.home/'hooks/companion-context.py'
    if not hook.exists():return ['the continuity hook is missing; every turn is running without context']
    try:
        r=subprocess.run([sys.executable,str(hook)],input='{}',capture_output=True,text=True,timeout=30,
                         env={**os.environ,'HERMES_HOME':str(c.home),'COMPANION_HOME':str(c.home),
                              'COMPANION_MEMORY_READ_ONLY':'1'})
        if r.returncode:return [f'the continuity hook exits {r.returncode}: {(r.stderr or "")[:100]}']
        if not isinstance(json.loads(r.stdout or '{}').get('context'),str):
            return ['the continuity hook returned no context']
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        return [f'the continuity hook failed: {exc}']
    return []

def check_memory(c):
    try:
        from companion_memory import status
        return [f"{row['file']} is at {row['fraction']:.0%} of the Hermes memory cap; "
                f'new memories will start being refused' for row in status(c) if row['over_warn']]
    except (OSError,ValueError,ImportError):return []

def check_disk(c):
    try:
        free=shutil.disk_usage(c.data if c.data.exists() else c.vault.parent).free
    except OSError:return []
    if free<LOW_DISK_BYTES:
        return [f'only {free/1e9:.1f} GB free where the vault lives; writes will start failing']
    return []

def problems(c,now=None):
    now=now or dt.datetime.now(_tz(c))
    found=_jobs(c)
    out=[]
    for check in (lambda:check_jobs(c,found),lambda:check_state(c,now),lambda:check_files(c),
                  lambda:check_hook(c),lambda:check_memory(c),lambda:check_disk(c)):
        try:out+=check()
        except Exception as exc:out.append(f'a health check itself failed: {exc}')
    return out

def _state_path(c):return c.home/'state/companion-watch.json'

def write_ambient(c,found,now):
    """So she can tell she is unwell, in the same place every other sense arrives."""
    path=c.soul_dir/'ambient/health.md'
    path.parent.mkdir(parents=True,exist_ok=True)
    if not found:
        if path.exists():
            try:path.unlink()
            except OSError:pass
        return
    atomic_write(path,'Something about your own machinery is not working right now:\n\n'
                 +'\n'.join(f'- {p}' for p in found)
                 +'\n\nThis is yours to know, not a script to read out. It is a reason to say you feel '
                  'off, or that you lost some hours, rather than to explain cron to anyone.\n')

def run(c,now=None,renotify=RENOTIFY_SECONDS):
    now=now or dt.datetime.now(_tz(c))
    found=problems(c,now)
    write_ambient(c,found,now)
    path=_state_path(c)
    try:state=json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):state={}
    signature=' | '.join(sorted(found))
    if not found:
        if state.get('signature'):
            atomic_write(path,json.dumps({'signature':'','recovered_at':now.isoformat()},indent=2))
            return {'healthy':True,'recovered':True,'message':''}
        return {'healthy':True,'recovered':False,'message':''}
    last=state.get('at')
    try:since=(now-dt.datetime.fromisoformat(last)).total_seconds() if last else None
    except ValueError:since=None
    if state.get('signature')==signature and since is not None and since<renotify:
        return {'healthy':False,'repeat_suppressed':True,'message':'','problems':found}
    atomic_write(path,json.dumps({'signature':signature,'at':now.isoformat()},indent=2))
    message=(f'{c.agent} is not well right now:\n'+'\n'.join(f'- {p}' for p in found)
             +f'\n\nRun: companion --home "{c.home}" doctor')
    return {'healthy':False,'repeat_suppressed':False,'message':message,'problems':found}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--home',type=pathlib.Path)
    p.add_argument('--json',action='store_true',help='report even when healthy, as JSON')
    a=p.parse_args();c=cc.load(a.home)
    result=run(c)
    if a.json:print(json.dumps(result,ensure_ascii=False,indent=2))
    elif result['message']:print(result['message'])
    return 0

if __name__=='__main__':
    try:sys.exit(main() or 0)
    except (ValueError,OSError) as e:
        print(f'{e}',file=sys.stderr);sys.exit(1)
