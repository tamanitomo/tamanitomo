"""Day-to-day operation: chat, schedule and gateway."""
from __future__ import annotations
import companion_platform as cp
import companion_render as cr
import json
import os
import subprocess
import sys
from .common import script_job_names, _read_jobs, load_manifest, print, resolve
from .scaffold import offer_multiplex

def cmd_chat(args):
    """Open Hermes chat in the selected profile, including custom home paths."""
    c=resolve(args,require_config=True)
    return subprocess.run(cp.hermes_command(),env={**os.environ,'HERMES_HOME':str(c.home),
                          'HERMES_TIMEZONE':c.timezone}).returncode
def cmd_schedule(args):
    """Inspect or authorize/pause the kit's recurring jobs through Hermes."""
    c=resolve(args,require_config=True)
    if args.state=='history':
        return subprocess.run(cp.hermes_command('cron','runs'),env={**os.environ,'HERMES_HOME':str(c.home),
                              'HERMES_TIMEZONE':c.timezone}).returncode
    names={cr.render(spec['name'],{'AGENT':c.agent}) for spec in load_manifest(c)['jobs']}
    jobs=[j for j in _read_jobs(c.home/'cron/jobs.json')['jobs'] if j.get('name') in names]
    if args.state=='status':
        for j in jobs:
            print(f"{'active' if j.get('enabled') else 'paused'}  {j['name']}")
            print(f"  next: {j.get('next_run_at') or 'not scheduled'} · last: {j.get('last_status') or 'not run yet'}")
        return 0
    if len(jobs)!=len(names) or {j['name'] for j in jobs}!=names:raise ValueError('Incomplete or duplicate job set; run doctor and repair first')
    action='resume' if args.state=='active' else 'pause'
    scripted=script_job_names(c)
    for job in jobs:
        if job['name'] in scripted:continue
        result=subprocess.run(cp.hermes_command('cron',action,job['id']),capture_output=True,text=True,encoding='utf-8',timeout=60,
            env={**os.environ,'HERMES_HOME':str(c.home),'HERMES_TIMEZONE':c.timezone})
        if result.returncode:raise ValueError(f"Could not {action} {job['name']}; inspect schedule status before retrying")
        print(f"{args.state}: {job['name']}")
    c.cron_active=args.state=='active';c.save()
    print('Jobs that run without a model stay active: they cost nothing and they are what keeps the\npresent honest and retention enforced while the schedule is paused.')
    print('This changes recurring scheduling only; it does not grant tool permissions or start a gateway.')
    return 0
def cmd_gateway(args):
    """Choose gateway ownership, configure bots, and manage the native service."""
    import companion_gateway as cg
    c=resolve(args)
    if args.action=='preflight':
        result=cg.preflight(c);print(json.dumps(result,indent=2));return 0 if result['ready'] else 1
    if args.mode:
        print(json.dumps(cg.configure(c,args.mode),indent=2))
    if args.action:
        return cg.native(c,args.action,args.root_restarted)
    if not args.mode and cp.is_terminal(sys.stdin):
        report=[];offer_multiplex(c,report);print('\n'.join(report))
    print(json.dumps(cg.status(c),indent=2))
    return 0
