"""Hermes integration boundary. CLI writes, read-only session access, explicit homes.

No Hermes package is imported into the app's interpreter. Optional catalog discovery
runs in Hermes's interpreter and fails independently when its API changes.
"""
from __future__ import annotations
import base64
import math
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor

import companion_config as cc
import companion_platform as cp

KIT = Path(__file__).resolve().parents[2]
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')

def app_directory():
    if os.environ.get('COMPANION_APP_STATE'):
        return Path(os.environ['COMPANION_APP_STATE']).expanduser().absolute()
    base = Path(os.environ.get('LOCALAPPDATA', str(Path.home()/'AppData/Local'))) if os.name == 'nt' else Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share')))
    return base/'companion-kit'


def read_json(path, default):
    if not Path(path).exists(): return default
    return json.loads(Path(path).read_text(encoding='utf-8'))


def redact(text):
    text = ANSI.sub('', str(text))
    text = re.sub(r'(?i)((?:api[_ -]?key|token|secret|password|authorization)\s*[=:]\s*)[^\s,;]+', r'\1[redacted]', text)
    return re.sub(r'\b(?:sk-|sk-or-|ghp_|gho_)[A-Za-z0-9_-]{12,}', '[redacted]', text)


class Runtime:
    def __init__(self, root, managed=False):
        self.root = Path(root).expanduser().absolute()
        self.managed = managed

    def command(self):
        override = os.environ.get('COMPANION_HERMES_COMMAND')
        if override and not self.managed:
            prefix = json.loads(override)
        else:
            binary = self.root/'hermes-agent'/'venv'/('Scripts/hermes.exe' if os.name == 'nt' else 'bin/hermes')
            if binary.is_file(): return [str(binary)]
            if self.managed: raise ValueError('Install the kit-managed Hermes runtime first.')
            binary = shutil.which('hermes')
            if not binary:
                candidate = Path.home()/'.local/bin/hermes'
                if candidate.is_file(): binary = str(candidate)
            if not binary: raise ValueError('Hermes is not installed or cannot be found. Choose Install Hermes.')
            prefix = [binary]
        if not isinstance(prefix,list) or not prefix or not all(isinstance(s,str) and s for s in prefix):
            raise ValueError('Invalid Hermes command configuration')
        return prefix

    def env(self, home=None):
        env = dict(os.environ)
        for key in ('HERMES_PROFILE','COMPANION_HOME','HERMES_INFERENCE_MODEL','HERMES_INFERENCE_PROVIDER'):
            env.pop(key, None)
        env.update(HERMES_HOME=str(home or self.root), PYTHONUTF8='1', PYTHONIOENCODING='utf-8',
                   COMPANION_HERMES_COMMAND=json.dumps(self.command()), COMPANION_APP_CLIENT='1')
        # The managed runtime's tools must resolve beside its executable after updates.
        bindirs = [self.root/'bin', self.root/'node'/('' if os.name=='nt' else 'bin'),
                   self.root/'hermes-agent'/'venv'/('Scripts' if os.name=='nt' else 'bin')]
        if os.name == 'nt': bindirs += [self.root/'git/bin', self.root/'git/cmd']
        env['PATH'] = os.pathsep.join(str(p) for p in bindirs if p.is_dir()) + os.pathsep + env.get('PATH','')
        return env

    def run(self, args, home=None, timeout=120, kit=False, check=True, input=None):
        argv = ([sys.executable,str(KIT/'bin/companion')] if kit else self.command()) + list(args)
        try:
            result = subprocess.run(argv, env=self.env(home), cwd=str(KIT), input=input,
                stdin=subprocess.DEVNULL if input is None else None,
                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise ValueError(f'Hermes did not finish within {timeout}s. Inspect its job/session status before retrying.') from exc
        if check and result.returncode:
            raise ValueError(redact(result.stderr or result.stdout or f'Command exited {result.returncode}')[-6000:])
        return result

    def chat(self,args,home,report):
        binary=Path(self.command()[0])
        python=binary.parent/('python.exe' if os.name=='nt' else 'python')
        if not python.is_file():python=binary.resolve().parent/'python'
        if len(self.command())!=1 or not python.is_file():return self.run(args,home=home,timeout=600)
        import queue
        events=queue.Queue(maxsize=1024)
        # Stderr is kept out of the browser stream; only explicit JSON events cross it.
        with tempfile.TemporaryFile(mode='w+',encoding='utf-8') as errors:
            proc=subprocess.Popen([str(python),str(KIT/'kit/app/hermes_stream.py'),*args],env=self.env(home),
                cwd=str(KIT),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=errors,text=True,encoding='utf-8',errors='replace')
            def read():
                for line in proc.stdout:events.put(line)
                events.put(None)
            threading.Thread(target=read,daemon=True).start()
            import time
            deadline=time.monotonic()+600;final='';session=None
            try:
                while True:
                    if time.monotonic()>deadline:raise ValueError('Hermes chat timed out. Inspect the session before retrying.')
                    try:line=events.get(timeout=.5)
                    except queue.Empty:continue
                    if line is None:break
                    try:event=json.loads(line)
                    except ValueError:continue
                    if event.get('event')=='delta':report.stream(event.get('text',''))
                    elif event.get('event')=='final':final=event.get('text','')
                    elif event.get('event')=='session':session=event.get('id')
                code=proc.wait(timeout=5)
                errors.seek(0);error=errors.read()[-6000:]
                if code:raise ValueError(redact(error or final or 'Hermes chat failed'))
                result=subprocess.CompletedProcess(args,code,final,error);result.session=session
                return result
            finally:
                if proc.poll() is None:proc.kill();proc.wait()
                proc.stdout.close()

    def home(self, profile):
        if profile in ('', 'default', None): return self.root
        path = cp.profile_path(self.root,profile)
        if not path.is_dir(): raise ValueError('Profile does not exist')
        return path

    def info(self):
        try:
            command = self.command()
            available = True
            error = ''
        except ValueError as exc:
            command=[]; available=False; error=str(exc)
        return {'root':str(self.root),'managed':self.managed,'available':available,'error':error,
                'command':command,'data_separate_from_code':True}

    def catalog(self):
        # This optional adapter is isolated from chat/config functionality. The
        # protocol is a JSON list, never an arbitrary module provided by a client.
        command = self.command()
        binary = Path(command[0])
        python = binary.parent/('python.exe' if os.name=='nt' else 'python')
        if not python.is_file():
            try: python = binary.resolve().parent/'python'
            except OSError: pass
        if not python.is_file(): return []
        source = ('import dataclasses,json; from hermes_cli.provider_catalog import provider_catalog; '
                  'print(json.dumps([dataclasses.asdict(p) for p in provider_catalog()]))')
        try:
            r = subprocess.run([str(python),'-c',source],env=self.env(),capture_output=True,text=True,timeout=30)
            rows=json.loads(r.stdout)
            return rows if r.returncode==0 and isinstance(rows,list) else []
        except (OSError,ValueError,subprocess.SubprocessError): return []

    def install(self, report):
        """Run official staged installer, omitting its global command/PATH stage.

        Both data and runtime are in the selected installation root. Existing
        external installations are never updated by an Install operation.
        """
        if not self.managed:
            try:
                self.command()
            except ValueError: pass
            else: raise ValueError('An existing Hermes installation was found. Use its Update action instead.')
        if (self.root/'.companion-runtime.json').is_file() and (self.root/'hermes-agent'/'venv'/('Scripts/hermes.exe' if os.name=='nt' else 'bin/hermes')).exists():
            return {'installed':True,'already_installed':True}
        self.root.mkdir(parents=True,exist_ok=True)
        ext='ps1' if os.name=='nt' else 'sh'
        url=f'https://hermes-agent.nousresearch.com/install.{ext}'
        report('Downloading the official Hermes installer')
        with urllib.request.urlopen(url,timeout=60) as response:
            content=response.read(4_000_001)
        if len(content)>4_000_000: raise ValueError('Unexpected installer size')
        installer=self.root/f'.companion-install.{ext}'
        installer.write_bytes(content)
        env=dict(os.environ,HERMES_HOME=str(self.root),PYTHONUTF8='1')
        env.pop('HERMES_PROFILE',None)
        stages=(('uv','git','node','system-packages','repository','python','venv','dependencies',
                 'node-deps','config-templates','platform-sdks','bootstrap-marker') if os.name=='nt' else
                ('prerequisites','repository','venv','python-deps','node-deps','config','complete'))
        manifest_args=(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(installer),'-Manifest']
                       if os.name=='nt' else ['bash',str(installer),'--manifest'])
        manifest_result=subprocess.run(manifest_args,env=env,stdin=subprocess.DEVNULL,capture_output=True,
                                       text=True,encoding='utf-8',errors='replace',timeout=60)
        try:
            manifest=json.loads(manifest_result.stdout)
            available={s['name'] for s in manifest['stages']}
            compatible=manifest_result.returncode==0 and manifest['protocol_version']==1 and set(stages)<=available
        except (ValueError,KeyError,TypeError):compatible=False
        if not compatible:raise ValueError('The official installer interface changed. No install stages were run; update the kit or install Hermes separately.')
        for stage in stages:
            report('Installing Hermes: '+stage)
            if os.name=='nt':
                argv=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(installer),
                      '-HermesHome',str(self.root),'-InstallDir',str(self.root/'hermes-agent'),
                      '-Stage',stage,'-NonInteractive','-SkipSetup']
            else:
                argv=['bash',str(installer),'--hermes-home',str(self.root),'--dir',str(self.root/'hermes-agent'),
                      '--stage',stage,'--non-interactive','--skip-setup']
            try:
                r=subprocess.run(argv,env=env,stdin=subprocess.DEVNULL,capture_output=True,text=True,
                                 encoding='utf-8',errors='replace',timeout=1800)
            except subprocess.TimeoutExpired as exc:
                raise ValueError(f'Installer stage {stage} timed out; rerun installation to recover.') from exc
            if r.returncode: raise ValueError(f'Installer stage {stage} failed:\n'+redact(r.stderr or r.stdout)[-6000:])
        command=self.command()
        cp.atomic_write(self.root/'.companion-runtime.json',json.dumps({'command':command}))
        return {'installed':True,'installer_sha256':hashlib.sha256(content).hexdigest(),'root':str(self.root)}


class Operations:
    """Bounded, durable status records; one mutation per installation at a time."""
    def __init__(self, directory):
        self.directory=Path(directory)
        self.pool=ThreadPoolExecutor(max_workers=4,thread_name_prefix='companion')
        self.lock=threading.Lock()
        self.rows={}
        self.busy=set()

    def submit(self, scope, label, action, *, profile="default"):
        with self.lock:
            if scope in self.busy: raise ValueError('Another action is still running for this installation.')
            self.busy.add(scope)
            ident=uuid.uuid4().hex
            row={'id':ident,'scope':scope,'profile':profile or 'default','label':label,'status':'running','progress':'Starting',
                 'started_at':dt.datetime.now(dt.timezone.utc).isoformat()}
            self.rows[ident]=row
            self._save(row)
        def report(message):
            with self.lock:
                row['progress']=redact(message); self._save(row)
        def stream(delta):
            with self.lock:row['stream_text']=(row.get('stream_text','')+str(delta))[-1000000:]
        report.stream=stream
        def work():
            try:
                result=action(report)
                with self.lock: row.update(status='complete',result=result,progress='Complete')
            except Exception as exc:
                with self.lock: row.update(status='failed',error=redact(exc),progress='Needs attention')
            finally:
                with self.lock:
                    row['finished_at']=dt.datetime.now(dt.timezone.utc).isoformat()
                    self.busy.discard(scope); self._save(row)
        self.pool.submit(work)
        return dict(row)

    def _save(self,row):
        self.directory.mkdir(parents=True,exist_ok=True)
        cp.atomic_write(self.directory/(row['id']+'.json'),json.dumps(row,ensure_ascii=False))

    def get(self, ident):
        if not re.fullmatch('[a-f0-9]{32}',ident): raise ValueError('Unknown operation')
        with self.lock:
            if ident in self.rows: return dict(self.rows[ident])
        row=read_json(self.directory/(ident+'.json'),None)
        if row is None: raise ValueError('Unknown operation')
        if row['status']=='running':
            row.update(status='interrupted',error='The app stopped before this action completed. Inspect the current state before retrying.')
        return row


@contextlib.contextmanager
def session_db(c):
    path=c.home/'state.db'
    if not path.exists(): yield None; return
    resolved=path.resolve()
    shared=bool(c.profile and resolved==(c.hermes_root/'state.db').resolve())
    if c.is_root and resolved.is_relative_to(c.hermes_root/'profiles'):
        raise ValueError('The root session store redirects into a named profile')
    con=sqlite3.connect(resolved.as_uri()+'?mode=ro',uri=True,timeout=3)
    con.row_factory=sqlite3.Row
    try:
        con.execute('PRAGMA query_only=ON')
        columns={r[1] for r in con.execute('PRAGMA table_info(sessions)')}
        if not {'id','source','started_at'}<=columns: raise ValueError('Unsupported Hermes sessions schema. Vault access remains available.')
        if 'profile_name' not in columns:
            if shared: raise ValueError('Cannot safely scope this shared session store')
            scope='1=1';params=()
        elif c.is_root:
            scope="lower(coalesce(profile_name,'')) IN ('','default')";params=()
        elif shared:
            scope="lower(coalesce(profile_name,''))=?";params=(c.profile.lower(),)
        else:
            scope="lower(coalesce(profile_name,'')) IN ('','default',?)";params=(c.profile.lower(),)
        yield con,columns,scope,params
    except sqlite3.Error as exc:
        raise ValueError('Hermes session history is temporarily unavailable or its schema changed.') from exc
    finally: con.close()


def _page_cursor(value):
    if not value:return None
    try:
        if len(value)>300:raise ValueError()
        row=json.loads(base64.urlsafe_b64decode(value+'='*(-len(value)%4)))
        if not isinstance(row,list) or len(row)!=2 or isinstance(row[0],bool) or not isinstance(row[0],(int,float)) or not math.isfinite(row[0]):raise ValueError()
        return row
    except (ValueError,TypeError,UnicodeError):raise ValueError('Invalid history cursor')


def _encode_cursor(stamp,ident):
    return base64.urlsafe_b64encode(json.dumps([stamp,ident],separators=(',',':')).encode()).decode().rstrip('=')


def sessions_page(c, limit=100, before=None):
    if type(limit)!=int or not 1<=limit<=200:raise ValueError('History page size must be 1–200')
    cursor=_page_cursor(before)
    with session_db(c) as state:
        if state is None:return {'sessions':[],'next_cursor':None}
        con,columns,scope,params=state
        fields=[f for f in ('id','source','title','started_at','last_activity_at','model','message_count') if f in columns]
        if 'source' in columns:
            scope+=" AND lower(coalesce(source,'')) NOT IN ('cron','subagent','tool','config-audit','local-default-audit','local-tool-proof')"
        if cursor:
            if not isinstance(cursor[1],str):raise ValueError('Invalid session cursor')
            scope+=' AND (coalesce(started_at,0),id)<(?,?)';params=(*params,*cursor)
        rows=[dict(r) for r in con.execute(f"SELECT {','.join(fields)} FROM sessions WHERE {scope} ORDER BY coalesce(started_at,0) DESC,id DESC LIMIT ?",(*params,limit+1))]
        more=len(rows)>limit;rows=rows[:limit]
        return {'sessions':rows,'next_cursor':_encode_cursor(rows[-1]['started_at'] or 0,rows[-1]['id']) if more else None}


def sessions(c, limit=100):
    return sessions_page(c,limit)['sessions']


def messages_page(c, session, limit=200, before=None):
    if type(limit)!=int or not 1<=limit<=200:raise ValueError('History page size must be 1–200')
    cursor=_page_cursor(before)
    with session_db(c) as state:
        if state is None:raise ValueError('Session does not exist')
        con,_,scope,params=state
        if not con.execute(f'SELECT id FROM sessions WHERE id=? AND {scope}',(session,*params)).fetchone():
            raise ValueError('Session does not belong to this companion')
        cols={r[1] for r in con.execute('PRAGMA table_info(messages)')}
        if not {'role','content','timestamp','session_id'}<=cols:raise ValueError('Unsupported Hermes messages schema')
        conditions="session_id=? AND role IN ('user','assistant')";values=(session,)
        if '_compressed_summary' in cols:conditions+=' AND coalesce(_compressed_summary,0)=0'
        if {'active','compacted'}<=cols:conditions+=' AND (active=1 OR compacted=1)'
        if cursor:
            if type(cursor[1])!=int:raise ValueError('Invalid message cursor')
            conditions+=' AND (coalesce(timestamp,0),rowid)<(?,?)';values+=tuple(cursor)
        rows=[dict(r) for r in con.execute(f'SELECT rowid AS _cursor_id,role,content,timestamp FROM messages WHERE {conditions} ORDER BY coalesce(timestamp,0) DESC,rowid DESC LIMIT ?',(*values,limit+1))]
        more=len(rows)>limit;rows=rows[:limit]
        next_cursor=_encode_cursor(rows[-1]['timestamp'] or 0,rows[-1]['_cursor_id']) if more else None
        for row in rows:del row['_cursor_id']
        return {'messages':list(reversed(rows)),'next_cursor':next_cursor}


def messages(c, session, limit=200):
    return messages_page(c,session,limit)['messages']
