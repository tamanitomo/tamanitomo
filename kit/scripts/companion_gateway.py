"""Profile gateway ownership and native Hermes service handoff.

Never prints credentials or starts a model. Preflight compares bot tokens locally. Shared profiles must not also have
standalone gateways. Routing changes require a gateway restart by the operator.
"""
from __future__ import annotations
import json,os,pathlib,shutil,subprocess,uuid,shlex,sys,sqlite3,time,contextlib
import yaml
import companion_platform as cp

PLAN='companion-gateway.json'

def read_config(path):
    if not path.exists():return {}
    data=yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    if not isinstance(data,dict):raise ValueError('Gateway config must be a mapping')
    return data

def routing(c):
    data=read_config(c.hermes_root/'config.yaml');gw=data.get('gateway') or {}
    if not isinstance(gw,dict):raise ValueError('gateway must be a mapping')
    enabled=data.get('multiplex_profiles',gw.get('multiplex_profiles',False))
    allowed=data.get('multiplex_profile_allowlist',gw.get('multiplex_profile_allowlist'))
    if not isinstance(enabled,bool):raise ValueError('multiplex_profiles must be true or false')
    if allowed is not None:
        if not isinstance(allowed,list) or any(not isinstance(x,str) for x in allowed):
            raise ValueError('multiplex_profile_allowlist must be a list of profile names')
        allowed=[cp.profile_name(x) for x in allowed]
    return data,enabled,allowed

def saved(c):
    p=c.home/PLAN
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}

def status(c):
    _,enabled,allowed=routing(c)
    shared=not c.is_root and enabled and (allowed is None or c.profile in allowed)
    owner=c.hermes_root if shared else c.home
    records=[]
    for home in dict.fromkeys([owner,c.home]):
        p=home/'gateway.pid'
        if p.exists():
            try:
                d=json.loads(p.read_text(encoding='utf-8'));pid=d.get('pid') if isinstance(d,dict) else d
                records.append({'home':str(home),'pid':pid})
            except (ValueError,OSError):records.append({'home':str(home),'pid':'unreadable'})
    return {'mode':'shared' if shared else 'dedicated','owner_home':str(owner),
            'pid_records':records,'plan':saved(c),
            'note':'PID records are clues, not a liveness check. Native gateway status verifies service state.'}

def configure(c,mode):
    if mode not in ('shared','dedicated','later'):raise ValueError('Unknown gateway mode')
    result={'mode':mode,'routing_changed':False,'restart_required':bool(saved(c).get('restart_required'))}
    if mode=='later':
        cp.atomic_write(c.home/PLAN,json.dumps(result,indent=2)+'\n');return result
    if os.environ.get('GATEWAY_MULTIPLEX_PROFILES','').strip():
        raise ValueError('GATEWAY_MULTIPLEX_PROFILES overrides routing; resolve that operator override first')
    with cp.file_lock(c.hermes_root/'.companion-gateway.lock'):
        result['restart_required']=bool(saved(c).get('restart_required'))
        data,enabled,allowed=routing(c)
        if c.is_root and mode=='dedicated' and enabled:
            raise ValueError('Root already multiplexes profiles. Keep its existing ownership or configure individual profiles; refusing to disable their gateway.')
        if mode=='shared' and not c.is_root and (c.home/'gateway.pid').exists():
            raise ValueError('Profile has a gateway PID record. Verify and stop its dedicated gateway before selecting shared ownership.')
        before=json.dumps(data,sort_keys=True)
        if mode=='shared':
            if not enabled:allowed=[]
            enabled=True
            if allowed is not None and not c.is_root:allowed=sorted(set(allowed+[c.profile]))
        elif not c.is_root and enabled:
            if allowed is None:
                # Preserve current peers, but make future enrollment explicit.
                allowed=[p.name for p in (c.hermes_root/'profiles').iterdir()
                         if p.is_dir() and not p.is_symlink() and not p.name.startswith('.') and p.name!=c.profile]
            else:allowed=[p for p in allowed if p!=c.profile]
        if mode=='shared' or enabled:
            gw=data.setdefault('gateway',{}) or {}
            gw['multiplex_profiles']=enabled;gw['multiplex_profile_allowlist']=allowed
            data['gateway']=gw
            # Hermes gives top-level compatibility keys precedence; keep them consistent.
            for key in ('multiplex_profiles','multiplex_profile_allowlist'):
                if key in data:data[key]=gw[key]
        changed=before!=json.dumps(data,sort_keys=True)
        if changed:
            path=c.hermes_root/'config.yaml'
            if path.exists():shutil.copy2(path,path.with_name('config.yaml.pre-gateway-'+uuid.uuid4().hex[:8]))
            cp.atomic_write(path,yaml.safe_dump(data,sort_keys=False,allow_unicode=True))
        result.update(routing_changed=changed,restart_required=changed or result['restart_required'])
        cp.atomic_write(c.home/PLAN,json.dumps(result,indent=2)+'\n')
    return result

def service_units(home):
    """Read service definitions, not secrets; find either Linux scope for this home."""
    found=[]
    if not sys.platform.startswith('linux'):return found
    for scope,base in [('system',pathlib.Path('/etc/systemd/system')),
                       ('user',pathlib.Path.home()/'.config/systemd/user')]:
        for p in base.glob('hermes-gateway*.service'):
            try:
                for line in p.read_text(encoding='utf-8').splitlines():
                    if not line.startswith('Environment='):continue
                    for field in shlex.split(line.split('=',1)[1]):
                        if field.startswith('HERMES_HOME=') and pathlib.Path(field.split('=',1)[1]).resolve()==pathlib.Path(home).resolve():
                            found.append({'scope':scope,'unit':p.name});break
            except (OSError,ValueError):continue
    return found

def _json(path):
    try:
        data=json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data,dict) else {}
    except (ValueError,OSError):return {}

def _alive(record):
    """Preserve process identity checks where supported; unknown is not dead."""
    return cp.process_matches(record.get('pid'), record.get('start_time'))

def _env_values(home):
    # Only used locally; values never enter a returned report or subprocess argv.
    out={}
    try:
        for line in (home/'.env').read_text(encoding='utf-8').splitlines():
            line=line.strip()
            if line.startswith('export '):line=line[7:].lstrip()
            if not line or line.startswith('#') or '=' not in line:continue
            key,value=line.split('=',1)
            try:parts=shlex.split(value,comments=True)
            except ValueError:continue
            out[key.strip()]=' '.join(parts)
    except OSError:pass
    return out

def preflight(c):
    """Read-only service, profile and Telegram readiness; no network or messages."""
    info=status(c);owner=pathlib.Path(info['owner_home'])
    record=_json(owner/'gateway.pid');runtime=_json(owner/'gateway_state.json')
    alive=_alive(record)
    running=alive is True and runtime.get('pid')==record.get('pid') and runtime.get('gateway_state')=='running'
    served=c.is_root or info['mode']=='dedicated' or c.profile in (runtime.get('served_profiles') or [])
    profile_state=_json(c.home/'gateway_state.json') if info['mode']=='shared' else runtime
    telegram=(profile_state.get('platforms') or {}).get('telegram') or {}
    connected=running and served and telegram.get('state')=='connected' and telegram.get('writer_pid')==record.get('pid')
    env=_env_values(c.home);token=env.get('TELEGRAM_BOT_TOKEN');duplicates=[]
    homes=[c.hermes_root]
    directory=c.hermes_root/'profiles'
    if directory.exists():homes.extend(p for p in directory.iterdir() if p.is_dir() and not p.is_symlink() and not p.name.startswith('.'))
    if token:
        duplicates=[p.name for p in homes if p.resolve()!=c.home.resolve() and _env_values(p).get('TELEGRAM_BOT_TOKEN')==token]
    exchanged=False;last=None;db=c.home/'state.db'
    if db.exists():
        try:
            with contextlib.closing(sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True,timeout=.1)) as con:
                con.execute('PRAGMA query_only=ON')
                deadline=time.monotonic()+1.0
                con.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
                row=con.execute("""SELECT max(s.started_at) FROM sessions s
                    WHERE s.source='telegram' AND EXISTS
                    (SELECT 1 FROM messages m WHERE m.session_id=s.id AND m.role='user')
                    AND EXISTS (SELECT 1 FROM messages m WHERE m.session_id=s.id AND m.role='assistant')""").fetchone()
                last=row[0] if row else None;exchanged=last is not None
        except sqlite3.Error:pass
    config=read_config(c.home/'config.yaml');model=config.get('model') or {}
    checks={'gateway_running':running,'profile_served':served,'telegram_configured':bool(token),
        'telegram_connected':connected,'telegram_exchange_recorded':exchanged,
        'unique_bot_token':bool(token) and not duplicates,
        'model_selected':bool(model.get('default')) if isinstance(model,dict) else bool(model)}
    notes=[]
    if alive is None:notes.append('Native process verification is unavailable here; use gateway --action status on this host.')
    if duplicates:notes.append('The same Telegram token is configured in other profiles: '+', '.join(duplicates))
    if not exchanged:notes.append('Send /start and get a reply from this bot before activating its routine.')
    if info['plan'].get('restart_required'):notes.append('Root routing restart still needs verification.')
    if not connected:notes.append('Telegram connection is not verified for this profile; inspect native gateway status.')
    if len(service_units(owner))>1:notes.append('Multiple service definitions target this home; choose one owner before continuing.')
    return {'ready':all(checks.values()) and not notes,'checks':checks,'notes':notes,
            'owner_home':str(owner),'mode':info['mode'],'last_recorded_telegram_session':last,
            'limits':'Retained exchange metadata is not proof of current delivery or model credentials. No test message or API call was sent.'}

def native(c,action,root_restarted=False):
    if action not in ('status','setup','install','start','restart'):raise ValueError('Unsupported gateway action')
    info=status(c);shared=info['mode']=='shared'
    # Configure messaging in the selected profile, inspect the actual service owner.
    home=pathlib.Path(info['owner_home']) if action in ('status','restart') else c.home
    if action in ('install','start'):
        if shared:raise ValueError('This profile belongs to the root multiplexer. Manage the root gateway; do not install another one.')
        plan=info['plan']
        if plan.get('restart_required') and not c.is_root and not root_restarted:
            raise ValueError('Restart the existing root gateway to apply changed routing before starting a dedicated profile gateway; then use --root-restarted.')
        if action=='install' and (info['pid_records'] or service_units(home)):
            raise ValueError('A gateway PID record or installed service already exists for this home. Run gateway status and preserve that service instead of installing another.')
    if action=='restart' and info['plan'].get('restart_required') and not c.is_root and not root_restarted:
        raise ValueError('Apply and verify the root routing restart first, then pass --root-restarted.')
    env={**os.environ,'HERMES_HOME':str(home),'PYTHONUTF8':'1'}
    # Avoid inherited profile selection overriding this exact home.
    env.pop('HERMES_PROFILE',None)
    cmd=cp.hermes_command('gateway',action)
    units=service_units(home)
    if action in ('status','start','restart') and any(u['scope']=='system' for u in units):cmd+=['--system']
    code=subprocess.run(cmd,env=env).returncode
    if code==0 and root_restarted:
        plan=saved(c)
        if plan:
            plan['restart_required']=False
            cp.atomic_write(c.home/PLAN,json.dumps(plan,indent=2)+'\n')
    return code
