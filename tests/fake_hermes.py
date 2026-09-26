"""Local contract double. Never calls a model, gateway, or actual Hermes CLI."""
import datetime as dt
import json
import os
import pathlib
import sys
import uuid

home=pathlib.Path(os.environ['HERMES_HOME'])
args=sys.argv[1:]
if not args or args[:2]==['cron','runs']:
    print('Hermes home: '+str(home))
elif args[:2]==['profile','create']:
    dest=home/'profiles'/args[2];dest.mkdir(parents=True,exist_ok=False)
    for d in ('skills','memories','sessions'):(dest/d).mkdir()
    (dest/'.env').touch(mode=0o600)
    (dest/'config.yaml').write_text('model:\n  default: test-model\n  provider: test-provider\n',encoding='utf-8')
elif args[:3]==['cron','create','--help']:
    print('usage: cron create --toolsets TOOLSETS --name NAME --paused schedule prompt')
elif args[:2]==['cron','create']:
    path=home/'cron/jobs.json';path.parent.mkdir(parents=True,exist_ok=True)
    data=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'jobs':[]}
    data['jobs'].append({'id':uuid.uuid4().hex[:12],'name':args[args.index('--name')+1],
        'prompt':args[3],'no_agent':'--no-agent' in args,'script':args[args.index('--script')+1] if '--script' in args else None,'schedule':{'kind':'cron','expr':args[2]},'enabled':'--paused' not in args,
        'next_run_at':None if '--paused' in args else (dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=1)).isoformat(),
        'enabled_toolsets':(args[args.index('--toolsets')+1].split(',')
                            if '--toolsets' in args else None)})
    path.write_text(json.dumps(data),encoding='utf-8')
elif args[:2]==['cron','edit']:
    path=home/'cron/jobs.json';data=json.loads(path.read_text(encoding='utf-8'))
    job=next(j for j in data['jobs'] if j['id']==args[2])
    if '--prompt' in args:job['prompt']=args[args.index('--prompt')+1]
    if '--schedule' in args:job['schedule']['expr']=args[args.index('--schedule')+1]
    path.write_text(json.dumps(data),encoding='utf-8')
elif args[:2] in (['cron','pause'],['cron','resume']):
    path=home/'cron/jobs.json';data=json.loads(path.read_text(encoding='utf-8'))
    job=next(j for j in data['jobs'] if j['id']==args[2]);job['enabled']=args[1]=='resume'
    job['next_run_at']=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=1)).isoformat() if job['enabled'] else None
    path.write_text(json.dumps(data),encoding='utf-8')
elif args[:2]==['cron','list']:
    print((home/'cron/jobs.json').read_text(encoding='utf-8'))
elif args and args[0]=='chat':
    # Preview-only reply. The real app uses the Hermes streaming bridge.
    print('Welcome back. I was thinking about our garden plan. Shall we start with tea?')
else:sys.exit(2)
