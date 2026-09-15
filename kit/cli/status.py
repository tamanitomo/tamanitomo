"""`companion status` — how she is, right now, in one screen.

doctor answers "is this installed correctly". This answers "what is she doing,
when did anything last work, and is anything wrong" — the question you actually
have at 9am, and the one that had no answer at all when a rate limit quietly
stopped every scheduled job for two days.
"""
from __future__ import annotations
import argparse
import companion_wizard as wiz
import datetime as dt
import json
from zoneinfo import ZoneInfo
from .common import _read_jobs, load_manifest, print, resolve

def _tz(c):
    try:return ZoneInfo(c.timezone)
    except Exception:return ZoneInfo('UTC')

def collect(c,now=None):
    """Everything the screen shows, as data, so the app can show the same."""
    import companion_presence as presence, companion_loops as loops, companion_watch as watch
    import companion_context as context
    tz=_tz(c);now=now or dt.datetime.now(tz)
    scene=presence.current(c);anchor=presence.last_confirmed(c)
    jobs=[j for j in _read_jobs(c.home/'cron/jobs.json')['jobs']
          if j.get('name','').startswith(c.agent+' ')]
    return {'now':now.isoformat(timespec='minutes'),
            'state':scene,'confirmed_at':anchor['recorded_at'] if anchor else None,
            'state_age':context.age_phrase(dt.datetime.fromisoformat(scene['recorded_at']),now) if scene else None,
            'loops':loops.loops(c),
            'jobs':jobs,
            'problems':watch.problems(c,now)}

def render(c,data):
    out=[]
    out.append(f"{c.agent} · {data['now']} ({c.timezone})")
    scene=data['state']
    if not scene:
        out.append('  no lived state recorded yet')
    else:
        state=scene['state']
        confirmed=state.get('confirmed',True)
        out.append(f"  right now   {state.get('activity','')} at {state.get('location','')}"
                   f"   ({data['state_age']}{'' if confirmed else ', UNCONFIRMED'})")
        out.append(f"  mood        {state.get('mood','')}")
        if state.get('wants'):out.append('  wants       '+'; '.join(state['wants']))
        if not confirmed and data['confirmed_at']:
            out.append(f"  last seen   a model last confirmed the present at {data['confirmed_at'][:16]}")
    loops=data['loops']
    out.append(f"  open loops  {len(loops)}"+(': '+'; '.join(l['title'] for l in loops[:3]) if loops else ''))
    active=[j for j in data['jobs'] if j.get('enabled')]
    failing=[j for j in data['jobs'] if j.get('last_status')=='error']
    out.append(f"  jobs        {len(active)} of {len(data['jobs'])} running"
               +(f", {len(failing)} failing" if failing else ''))
    for job in data['jobs']:
        mark='·' if job.get('enabled') else 'paused'
        last=job.get('last_status') or 'not run yet'
        out.append(f"    {mark:<7}{job['name'][len(c.agent)+1:]:<30.29}{last:<12}next {job.get('next_run_at') or '—'}")
    if data['problems']:
        out.append('')
        out.append('  Not well:')
        for problem in data['problems']:out.append('    ! '+problem)
    else:
        out.append('')
        out.append('  Nothing is wrong that the health watch can see.')
    return '\n'.join(out)

def cmd_status(args):
    """How the companion is right now: state, loops, jobs and anything wrong."""
    c=resolve(args,require_config=True)
    data=collect(c)
    if getattr(args,'json',False):
        print(json.dumps(data,ensure_ascii=False,indent=2,default=str))
    else:
        print(render(c,data))
    return 1 if data['problems'] else 0
