"""Application management routes. Every mutation has an explicit installation/profile."""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import uuid
import yaml
import itertools
from fastapi import HTTPException, Request
from . import runtime as hr
import companion_config as cc
import companion_platform as cp

# Workspace appearance. Themes are defined in static/product.css; this list is the
# validation allowlist, and the two groups decide what "match system" switches between.
DARK_THEMES=['midnight','nord','ocean','emerald','amethyst','synthwave','ember','sakura','carbon']
LIGHT_THEMES=['daylight','parchment','mist']
THEMES=DARK_THEMES+LIGHT_THEMES
# Destinations a person may pin to the mobile bar. "more" is fixed and never pinned.
PINNABLE=['now','chat','timeline','photos','journals','creations','relationship','loops',
          'knows','vault','identity','settings','environment','health','roster',
          'image-studio','voice','local-models']
APPEARANCE_DEFAULT={'theme':'midnight','accent':'','follow_system':False,
                    'dark_theme':'midnight','light_theme':'daylight',
                    'nav_pins':['chat','now','photos','journals']}

FALLBACK_CATALOG=[
 {'slug':'openrouter','label':'OpenRouter','api_key_env_vars':['OPENROUTER_API_KEY'],'auth_type':'api_key'},
 {'slug':'deepseek','label':'DeepSeek','api_key_env_vars':['DEEPSEEK_API_KEY'],'auth_type':'api_key'},
 {'slug':'openai','label':'OpenAI','api_key_env_vars':['OPENAI_API_KEY'],'auth_type':'api_key'},
 {'slug':'anthropic','label':'Anthropic','api_key_env_vars':['ANTHROPIC_API_KEY'],'auth_type':'api_key'},
 {'slug':'ollama','label':'Ollama (local)','api_key_env_vars':[],'auth_type':'none'},
 {'slug':'custom','label':'OpenAI-compatible endpoint','api_key_env_vars':['OPENAI_API_KEY'],'auth_type':'api_key'},
]

INFERENCE_PRESETS=[
 {
  'id': 'openrouter_free',
  'name': 'OpenRouter Free Tier Cascade',
  'badge': 'Free Cloud',
  'description': 'Zero-cost inference via OpenRouter smart router with graceful failover across active free models (open-weights models).',
  'primary': {'provider': 'openrouter', 'model': 'openrouter/free'},
  'fallbacks': [
   {'provider': 'openrouter', 'model': 'google/gemma-4-26b-a4b-it:free'},
   {'provider': 'openrouter', 'model': 'nvidia/nemotron-3-super-120b-a12b:free'},
   {'provider': 'openrouter', 'model': 'inclusionai/ling-3.0-flash-sante:free'},
  ],
  'requires_env': ['OPENROUTER_API_KEY'],
 },
 {
  'id': 'deepseek_free_cascade',
  'name': 'DeepSeek Fast + OpenRouter Free Fallbacks',
  'badge': 'High Performance',
  'description': 'DeepSeek Flash primary for high responsiveness, backed by OpenRouter free cascade on rate-limits.',
  'primary': {'provider': 'deepseek', 'model': 'deepseek-flash'},
  'fallbacks': [
   {'provider': 'openrouter', 'model': 'openrouter/free'},
   {'provider': 'openrouter', 'model': 'google/gemma-4-26b-a4b-it:free'},
  ],
  'requires_env': ['DEEPSEEK_API_KEY', 'OPENROUTER_API_KEY'],
 },
 {
  'id': 'local_hardware_cloud_fallback',
  'name': 'Local Hardware (Vulkan/Ollama) + Cloud Fallback',
  'badge': 'Private Local',
  'description': 'Runs locally on hardware with automatic failover to DeepSeek / OpenRouter if busy or unavailable.',
  'primary': {'provider': 'custom', 'model': 'local-model', 'base_url': 'http://127.0.0.1:11434/v1'},
  'fallbacks': [
   {'provider': 'deepseek', 'model': 'deepseek-flash'},
   {'provider': 'openrouter', 'model': 'openrouter/free'},
  ],
  'requires_env': [],
 },
]

def text(value, name, maxlen=300, empty=False):
    if not isinstance(value,str) or len(value)>maxlen or any(ord(c)<32 for c in value) or (not empty and not value.strip()):
        raise ValueError(f'{name} must be plain text (maximum {maxlen} characters)')
    return value.strip()

def config(home):
    path=home/'config.yaml'
    value=yaml.safe_load(path.read_text(encoding='utf-8')) if path.exists() else {}
    if value is None: value={}
    if not isinstance(value,dict): raise ValueError('Hermes config.yaml must be a mapping')
    return value

def sensitive_key(key):
    # Token counts are model settings, whereas singular tokens are credentials.
    key=re.sub(r'(?i)\b(?:max_|input_|output_|context_|total_|budget_)?tokens\b','',str(key))
    return bool(re.search(r'(?i)(secret|password|token|api.?key|auth|credential|cookie|bearer)',key))

def public_config(value):
    if isinstance(value,dict):
        return {k:('[configured]' if sensitive_key(k) and v else public_config(v)) for k,v in value.items()}
    if isinstance(value,list):return [public_config(v) for v in value]
    if isinstance(value,str):
        from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode
        if value.startswith(('http://','https://')):
            try:
                url=urlsplit(value)
                host=url.netloc.rsplit('@',1)[-1]
                query=urlencode([(k,'[configured]' if re.search(r'(?i)(key|token|secret|auth|password)',k) else v) for k,v in parse_qsl(url.query)])
                return urlunsplit((url.scheme,host,url.path,query,''))
            except ValueError:return '[invalid URL]'
        return hr.redact(value)
    return value

def save_config(home, mutate):
    with cp.file_lock(home/'.companion-config.lock'):
        value=config(home)
        mutate(value)
        path=home/'config.yaml'
        if path.exists():
            backup=home/'companion-config-backups'/f'{dt.datetime.now().strftime("%Y%m%dT%H%M%S")}-{uuid.uuid4().hex[:8]}.yaml'
            backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,backup)
        cp.atomic_write(path,yaml.safe_dump(value,sort_keys=False,allow_unicode=True))


def register(app, select, load, operations):
    from .terminal import Consoles
    consoles=Consoles()
    app.state.consoles=consoles
    app.state.operations=operations
    def context():
        rt,profile=select()
        return rt,profile,rt.home(profile)
    def op(label,action):
        rt,profile,home=context()
        if any(c.scope[0]==str(rt.root) and not c.finished for c in consoles.rows.values()):
            raise ValueError('Close the native Hermes setup console before starting another action.')
        return operations.submit(str(rt.root),label,lambda report: action(rt,profile,home,report),profile=profile)

    @app.post('/api/terminal')
    def open_terminal(payload:dict):
        rt,p,h=context()
        if str(rt.root) in operations.busy:raise ValueError('Wait for the running action to finish first')
        return consoles.open(rt,h,payload.get('action')).read()

    @app.get('/api/terminal/{ident}')
    def read_terminal(ident:str):
        rt,p,h=context();return consoles.get(ident,rt,h).read()

    @app.post('/api/terminal/{ident}/input')
    def write_terminal(ident:str,payload:dict):
        rt,p,h=context();consoles.get(ident,rt,h).write(payload.get('data'));return {'sent':True}

    @app.post('/api/terminal/{ident}/close')
    def close_terminal(ident:str):
        rt,p,h=context();consoles.get(ident,rt,h).close();return {'closed':True}

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail':str(exc)},status_code=400)

    @app.get('/api/installations')
    def installations():
        return {'installations':[dict(id=k,**v.info()) for k,v in app.state.runtimes.items()]}

    @app.post('/api/install')
    def install(): return op('Install Hermes',lambda rt,p,h,report:rt.install(report))

    @app.get('/api/operations/{ident}')
    def operation(ident:str):
        row=operations.get(ident)
        rt,profile=select()
        if row['scope']!=str(rt.root) or row.get('profile')!=(profile or 'default'): raise HTTPException(404,'Unknown operation')
        return row

    @app.get('/api/profiles')
    def profiles():
        from kit.cli.roster import discover
        rt,selected_profile=select();rows=[]
        for name,home in discover(rt.root):
            if home.is_symlink(): continue
            try:
                c=cc.load(home)
                label_path=home/'companion-display-name.json'
                label=json.loads(label_path.read_text()).get('name') if label_path.is_file() and not label_path.is_symlink() else None
                rows.append({'id':name or 'default','name':label or (c.agent if (home/cc.CONFIG_NAME).exists() else (name or 'Default Hermes')),
                             'installed':(home/cc.CONFIG_NAME).exists(),'type':c.agent_type,'home':str(home),'vault':str(c.vault)})
            except (ValueError,OSError) as exc:
                rows.append({'id':name or 'default','name':name or 'Default Hermes','installed':False,'error':str(exc)})
        archives=[]
        archive_root=rt.root/'profiles-removed'
        if archive_root.is_dir():
            for p in sorted(archive_root.iterdir(),reverse=True):
                if p.is_dir() and not p.is_symlink():
                    archives.append({'id':p.name})
        return {'profiles':rows,'archives':archives,'runtime':rt.info(),'selected_profile':selected_profile}

    @app.post('/api/profile/display-name')
    def display_name(payload:dict):
        name=payload.get('name')
        if not isinstance(name,str) or not name.strip() or len(name)>100 or any(ord(c)<32 for c in name):
            raise ValueError('Choose a display name of 1–100 characters')
        def run(rt,p,h,report):
            target=h/'companion-display-name.json'
            if target.is_symlink():raise ValueError('Display-name file must not be a symlink')
            cp.atomic_write(target,json.dumps({'name':name.strip()},ensure_ascii=False)+'\n')
            return {'name':name.strip(),'note':'Workspace name saved. Hermes identity, profile paths, and jobs are unchanged.'}
        return op('Rename workspace profile',run)

    def appearance_file(home):
        target=home/'companion-appearance.json'
        if target.is_symlink():raise ValueError('Appearance file must not be a symlink')
        return target

    @app.get('/api/appearance')
    def appearance():
        rt,p,h=context()
        stored=hr.read_json(appearance_file(h),{})
        out=dict(APPEARANCE_DEFAULT)
        if isinstance(stored,dict):
            for k,v in stored.items():
                if k in out:out[k]=v
        return {'appearance':out,'themes':{'dark':DARK_THEMES,'light':LIGHT_THEMES},'pinnable':PINNABLE}

    @app.post('/api/appearance')
    def appearance_save(payload:dict):
        rt,p,h=context()
        if not isinstance(payload,dict):raise ValueError('Invalid appearance payload')
        current=hr.read_json(appearance_file(h),{})
        out=dict(APPEARANCE_DEFAULT)
        if isinstance(current,dict):
            for k,v in current.items():
                if k in out:out[k]=v
        for key in ('theme','dark_theme','light_theme'):
            if key in payload:
                value=payload[key]
                if value not in THEMES:raise ValueError(f'Unknown theme for {key}')
                if key=='dark_theme' and value not in DARK_THEMES:raise ValueError('Choose a dark theme')
                if key=='light_theme' and value not in LIGHT_THEMES:raise ValueError('Choose a light theme')
                out[key]=value
        if 'accent' in payload:
            accent=payload['accent'] or ''
            if accent and not re.fullmatch(r'#[0-9a-fA-F]{6}',str(accent)):
                raise ValueError('Accent must be a #rrggbb colour, or empty for the theme default')
            out['accent']=str(accent).lower()
        if 'follow_system' in payload:out['follow_system']=bool(payload['follow_system'])
        if 'nav_pins' in payload:
            pins=payload['nav_pins']
            if not isinstance(pins,list):raise ValueError('nav_pins must be a list')
            clean=[]
            for item in pins:
                if item not in PINNABLE:raise ValueError(f'Cannot pin unknown destination: {item}')
                if item not in clean:clean.append(item)
            if not 1<=len(clean)<=4:raise ValueError('Pin between 1 and 4 destinations')
            out['nav_pins']=clean
        cp.atomic_write(appearance_file(h),json.dumps(out,ensure_ascii=False,indent=2)+'\n')
        return {'appearance':out,'saved':True}

    @app.get('/api/catalog')
    def catalog():
        import companion_render as render
        import companion_wizard as wizard
        import companion_catalog as catalog
        from zoneinfo import available_timezones
        return {'timezones':sorted(available_timezones()),'personas':render.load_personas(),'image_styles':render.load_styles(),
                'boundaries':{k:{'label':v['label'],'description':v['oneline']} for k,v in wizard.BOUNDARY_BANK.items()},
                'catalog':catalog.load(),'answer_keys':sorted(__import__('kit.cli.questions',fromlist=['known_answer_keys']).known_answer_keys())}

    @app.post('/api/profiles')
    def create(payload:dict):
        name=cp.profile_name(payload.get('profile',''))
        answers=payload.get('answers')
        if not isinstance(answers,dict) or not answers.get('boundary'): raise ValueError('Choose a relationship frame')
        from kit.cli.questions import known_answer_keys
        if set(answers)-known_answer_keys(): raise ValueError('Unknown setup answers')
        rt,_=select()
        if cp.profile_path(rt.root,name).exists(): raise ValueError('Profile already exists. Choose Adopt or Repair.')
        answers={**answers,'gateway_mode':'later','gateway_action':'status','cron_active':False}
        if not answers.get('vault'):
            from kit.cli.roster import existing_vault
            answers['vault']=str(existing_vault(rt.root) or (rt.root.parent/'companion-vault' if rt.managed else Path.home()/'vault'))
        return op('Create '+name,lambda rt,p,h,report: {'output':hr.redact(rt.run(['--home',str(rt.root),'add',name,'--answers',json.dumps(answers)],home=rt.root,kit=True,timeout=600).stdout),'profile':name})

    @app.post('/api/adopt')
    def adopt(payload:dict):
        answers=payload.get('answers',{})
        if not isinstance(answers,dict) or not answers.get('boundary'): raise ValueError('Choose a relationship frame')
        return op('Adopt existing Hermes companion',lambda rt,p,h,report: {'output':hr.redact(rt.run(
            ['--home',str(h),'upgrade','--soul','keep','--answers',json.dumps({**answers,'cron_active':False,'gateway_mode':'later','gateway_action':'status'})],home=h,kit=True,timeout=600).stdout)})

    @app.post('/api/profile/archive')
    def archive(payload:dict):
        rt,profile,home=context()
        if profile in ('','default'): raise ValueError('The root installation cannot be archived as a profile')
        if payload.get('confirm')!=profile: raise ValueError('Type the profile name to confirm archiving')
        def action(rt,p,h,report):
            import companion_gateway as gateway
            state=gateway.status(cc.load(h))
            if state['pid_records']: raise ValueError('Stop the owning gateway before archiving this profile, then retry.')
            if gateway.service_units(h): raise ValueError('Uninstall this profile’s dedicated gateway service before archiving, then retry. Its vault will be preserved.')
            return {'output':hr.redact(rt.run(['--home',str(rt.root),'remove',p,'--force'],home=rt.root,kit=True).stdout)}
        return op('Archive '+profile,action)

    @app.post('/api/profile/restore')
    def restore(payload:dict):
        ident=text(payload.get('archive'),'archive',120)
        name=cp.profile_name(payload.get('profile',''))
        if '/' in ident or '\\' in ident or ident.startswith('.'): raise ValueError('Invalid archive')
        def action(rt,p,h,report):
            source=rt.root/'profiles-removed'/ident
            if not source.is_dir() or source.is_symlink(): raise ValueError('Archive not found')
            stored=hr.read_json(source/'companion.json',{})
            if stored.get('profile')!=name: raise ValueError('Restore using the original profile name to preserve vault paths')
            dest=cp.profile_path(rt.root,name)
            if dest.exists(): raise ValueError('Profile name is already in use')
            dest.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(source),str(dest))
            return {'restored':name,'note':'Profile restored with its original paths. Inspect Health before starting its gateway.'}
        return op('Restore '+name,action)

    @app.post('/api/profile/purge')
    def purge(payload:dict):
        # Permanent deletion is intentionally limited to already archived homes.
        ident=text(payload.get('archive'),'archive',120)
        if payload.get('confirm')!=ident or '/' in ident or '\\' in ident or ident.startswith('.'):
            raise ValueError('Type the complete archive name to permanently delete it')
        def action(rt,p,h,report):
            source=rt.root/'profiles-removed'/ident
            if not source.is_dir() or source.is_symlink(): raise ValueError('Archive not found')
            shutil.rmtree(source)
            return {'deleted':ident,'vault_preserved':True}
        return op('Delete archived profile',action)

    @app.get('/api/environment')
    def environment():
        rt,p,h=context();cfg=config(h)
        model=cfg.get('model') or {}
        if isinstance(model,str): model={'default':model}
        # Explicit allowlist: config can contain inline credentials anywhere else.
        public={k:model.get(k,'') for k in ('default','provider','base_url')}
        chain=[{k:r.get(k,'') for k in ('model','provider','base_url')} for r in (cfg.get('fallback_providers') or []) if isinstance(r,dict)]
        c=cc.load(h)
        return {'runtime':rt.info(),'model':public_config(public),'fallbacks':public_config(chain),'tiers':public_config(c.models),
                'timezone':cfg.get('timezone',c.timezone),'restart_note':'New sessions and job runs use updated settings; restart the gateway to reload persistent workers.'}

    @app.get('/api/voice')
    def voice_settings():
        from . import speech
        rt,p,h=context()
        return {'tts':public_config(config(h).get('tts') or {}),'fields':speech.FIELDS,'labels':speech.LABELS,
                'local':list(speech.LOCAL),'reference':sorted(speech.REFERENCE),
                'installed':{name:speech.engine_python(rt.root,name).is_file() for name in speech.LOCAL}}

    @app.post('/api/voice')
    def voice_save(payload:dict):
        from . import speech
        provider=payload.get('provider')
        controls=payload.get('controls',{})
        # Preserve the original workspace API for existing clients.
        if 'controls' not in payload:
            controls={k:payload[k] for k in ('speed','pitch') if k in payload and k in speech.FIELDS.get(provider,{})}
        controls=speech.validate(provider,controls)
        voice=text(payload.get('voice',''),'voice',200,empty=True)
        transcript=payload.get('transcript','')
        if not isinstance(transcript,str) or len(transcript)>10000:raise ValueError('Transcript is too long')
        def run(rt,p,h,report):
            if provider in speech.LOCAL:
                source=rt.root/'hermes-agent'/'tools'/'tts_command_provider.py'
                if not source.is_file():raise ValueError('Update Hermes to a version supporting tts.providers command adapters before selecting this engine.')
            save_config(h,lambda cfg:speech.configure(cfg,rt.root,h,provider,voice,controls,transcript))
            return {'note':'Voice saved in this companion’s Hermes config. New speech requests use these settings.'}
        return op('Save voice',run)

    @app.post('/api/voice/inherit')
    def voice_inherit():
        import shlex
        def run(rt,p,h,report):
            if h==rt.root:raise ValueError('The default profile cannot inherit from itself')
            root_tts=config(rt.root).get('tts') or {}
            if not root_tts.get('provider') or root_tts.get('provider')=='companion-default':raise ValueError('Configure a voice on the installation’s default profile first')
            python=rt.root/'hermes-agent'/'venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
            script=hr.KIT/'kit/scripts/companion_tts_inherit.py'
            if not python.is_file() or not (rt.root/'hermes-agent/tools/tts_command_provider.py').is_file():raise ValueError('Update Hermes for command-provider support first')
            args=[str(python),str(script),'--root',str(rt.root),'--input','{input_path}','--output','{output_path}']
            command=__import__('subprocess').list2cmdline(args) if os.name=='nt' else shlex.join(args)
            def change(cfg):
                tts=cfg.setdefault('tts',{});tts['provider']='companion-default'
                tts.setdefault('providers',{})['companion-default']={'type':'command','command':command,'output_format':'wav','timeout':660}
            save_config(h,change)
            return {'note':'This companion now uses the installation’s current voice settings for every speech request.'}
        return op('Use installation voice',run)

    @app.post('/api/voice/install')
    def install_voice(payload:dict):
        provider=payload.get('provider')
        from . import speech
        if provider in speech.LOCAL:return op('Install '+provider,lambda rt,p,h,report:speech.install(rt,provider,report))
        if provider not in ('piper','kittentts','neutts'):raise ValueError('Choose a local engine to install')
        def run(rt,p,h,report):
            import subprocess
            python=rt.root/'hermes-agent'/'venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
            if not python.is_file():raise ValueError('Use Full Hermes setup for this installation')
            script = "import sys, shutil, importlib; from hermes_cli import setup; from hermes_cli.tools_config import _pip_install; provider=sys.argv[1]; "
            script += "assert provider!='neutts' or shutil.which('espeak-ng') or shutil.which('espeak'), 'Install espeak-ng through Full Hermes setup first'; "
            script += "ok=(getattr(setup, '_install_kittentts_deps', None) or importlib.import_module('hermes_cli.setup_tts')._install_kittentts_deps)() if provider=='kittentts' else _pip_install(['piper-tts' if provider=='piper' else 'neutts[all]'], timeout=600).returncode==0; sys.exit(0 if ok else 1)"
            report('Installing '+provider+' into the Hermes environment. Models download on first use.')
            result=subprocess.run([str(python),'-c',script,provider],env=rt.env(h),stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=660)
            if result.returncode:raise ValueError(hr.redact(result.stderr or result.stdout)[-4000:])
            return {'note':'Engine installed. Save your voice and generate a preview to download its model and try it.'}
        return op('Install local speech engine',run)

    @app.post('/api/voice/reference')
    async def voice_reference(request:Request,provider:str="neutts"):
        from .speech import REFERENCE
        if provider not in REFERENCE:raise ValueError("This provider does not use reference clips")
        import io, wave
        data=await request.body()
        if len(data)>20_000_000:raise ValueError('Reference clip exceeds 20 MB')
        try:
            with wave.open(io.BytesIO(data)) as clip:
                duration=clip.getnframes()/clip.getframerate()
                if not 1<=duration<=30:raise ValueError('Choose a WAV clip between 1 and 30 seconds')
        except (wave.Error,EOFError):raise ValueError('Choose an uncompressed WAV audio clip')
        rt,p,h=context();c=cc.load(h)
        dest=(c.data/'voice'/'reference.wav') if provider=='neutts' else (c.data/'voice'/provider/'reference.wav');dest.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=dest.parent,delete=False) as handle:
            handle.write(data);temporary=handle.name
        os.replace(temporary,dest)
        save_config(h,lambda cfg:cfg.setdefault('tts',{}).setdefault(provider,{}).update(ref_audio=str(dest)))
        return {'saved':True}

    FORBIDDEN_VOICE_TERMS = {'sex', 'orgasm', 'moan', 'erotic', 'nsfw', 'pussy', 'penis', 'breasts', 'boobs', 'fuck', 'cum', 'whore', 'slut'}

    @app.post('/api/voice/preview')
    def voice_preview(payload:dict):
        sample=text(payload.get('text'),'preview text',1000)
        if any(term in sample.lower() for term in FORBIDDEN_VOICE_TERMS):
            raise HTTPException(400, 'Audio synthesis of sexual or intimate phrases without companion agency is strictly disallowed.')
        def run(rt,p,h,report):
            import subprocess
            command=Path(rt.command()[0]).resolve()
            python=rt.root/'hermes-agent'/'venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
            if not python.is_file():python=command.parent/('python.exe' if os.name=='nt' else 'python')
            if not python.is_file():raise ValueError('Cannot locate Hermes Python. Use Full Hermes setup to check this installation.')
            c=cc.load(h);dest=c.data/'voice'/'preview.mp3';dest.parent.mkdir(parents=True,exist_ok=True)
            script='from tools.tts_tool import text_to_speech_tool; import sys,json; print("COMPANION_VOICE_RESULT="+json.dumps(json.loads(text_to_speech_tool(sys.argv[1],sys.argv[2]))))' 
            result=subprocess.run([str(python),'-c',script,sample,str(dest)],env=rt.env(h),capture_output=True,text=True,timeout=660)
            if result.returncode:raise ValueError(hr.redact(result.stderr)[-3000:])
            try:response=json.loads(next(line.split('=',1)[1] for line in result.stdout.splitlines() if line.startswith('COMPANION_VOICE_RESULT=')))
            except (ValueError,IndexError,StopIteration):raise ValueError('Speech engine returned an unreadable response')
            if not response.get('success'):raise ValueError(hr.redact(str(response.get('error') or response)))
            actual=Path(response.get('file_path',str(dest))).resolve()
            if actual.parent!=dest.parent.resolve() or not actual.is_file() or actual.suffix not in ('.wav','.mp3','.ogg'):raise ValueError('Speech engine did not save a playable preview')
            cp.atomic_write(dest.parent/'preview-result.json',json.dumps({'file':actual.name}))
            return {'note':'Preview ready','audio':'/api/voice/preview-audio'}
        return op('Preview voice',run)

    @app.get('/api/voice/preview-audio')
    def voice_preview_audio():
        from fastapi.responses import FileResponse
        c=load();folder=(c.data/'voice').resolve()
        metadata=hr.read_json(folder/'preview-result.json',{})
        path=(folder/metadata.get('file','missing')).resolve()
        if path.parent!=folder or path.suffix not in ('.mp3','.wav','.ogg') or not path.is_file():raise HTTPException(404,'No preview yet')
        return FileResponse(path)

    @app.get('/api/config')
    def full_config():
        rt,p,h=context();return {'config':public_config(config(h))}

    @app.post('/api/config')
    def config_value(payload:dict):
        key=text(payload.get('key'),'configuration key',150)
        if not re.fullmatch(r'[a-z][a-z0-9_]*(?:\.[A-Za-z0-9_-]+)*',key):raise ValueError('Use a dotted Hermes config key such as terminal.backend')
        if sensitive_key(key):raise ValueError('Use the credential form or native provider setup for secrets')
        value=payload.get('value')
        encoded=value if isinstance(value,str) else json.dumps(value)
        if len(encoded)>20000:raise ValueError('Configuration value is too large')
        def run(rt,p,h,report):
            rt.run(['config','set',key,encoded,'--force'],home=h)
            return {'saved':key,'note':'Hermes saved the setting. Restart persistent workers when needed.'}
        return op('Save Hermes setting',run)

    @app.get('/api/inference/presets')
    def inference_presets():
        rt,_,h=context()
        from companion_gateway import _env_values
        values=_env_values(h)
        out=[]
        for p in INFERENCE_PRESETS:
            ready=all(bool(values.get(k) or os.environ.get(k)) for k in p['requires_env'])
            out.append({**p,'ready':ready})
        return {'presets':out}

    @app.post('/api/inference/apply-preset')
    def apply_inference_preset(payload:dict):
        preset_id=text(payload.get('id',''),'preset id',100)
        preset=next((p for p in INFERENCE_PRESETS if p['id']==preset_id),None)
        if not preset: raise ValueError('Unknown inference preset')
        rt,p,h=context()
        c=cc.load(h)
        primary=dict(preset['primary'])
        fallbacks=[dict(f) for f in preset['fallbacks']]
        def mutate(cfg):
            old=cfg.get('model') if isinstance(cfg.get('model'),dict) else {}
            cfg['model']={'default':primary['model'],'provider':primary['provider']}
            if 'base_url' in primary: cfg['model']['base_url']=primary['base_url']
            else: cfg['model'].pop('base_url',None)
            cfg['fallback_providers']=fallbacks
        save_config(h,mutate)
        for tier in ('chat','loops','reflection'):
            c.models[tier]={'provider':primary['provider'],'model':primary['model'],'reasoning_effort':'none'}
        c.models['fallbacks']=fallbacks
        c.save()
        return {'applied':True,'preset':preset['name'],'primary':primary,'fallbacks':fallbacks,
                'note':f"Applied {preset['name']}. Primary and fallback cascade saved to config."}

    @app.get('/api/providers')
    def providers():
        rt,_,h=context()
        rows=rt.catalog() if rt.info()['available'] else []
        from companion_gateway import _env_values
        values=_env_values(h)
        return {'providers':[{**row,'credential_configured':any(bool(values.get(k) or os.environ.get(k)) for k in row.get('api_key_env_vars',[]))} for row in (rows or FALLBACK_CATALOG)],
                'source':'installed Hermes catalog' if rows else 'basic compatibility catalog'}

    @app.post('/api/environment')
    def save_environment(payload:dict):
        rt,p,h=context()
        allowed={'model','fallbacks','tiers','timezone'}
        if set(payload)-allowed: raise ValueError('Unknown environment setting')
        def entry(row, primary=False):
            if not isinstance(row,dict) or set(row)-{'model','provider','base_url'}: raise ValueError('Invalid model entry')
            out={k:text(v,k,500,empty=True) for k,v in row.items()}
            if out.get('base_url'):
                from urllib.parse import urlsplit
                url=urlsplit(out['base_url'])
                if url.scheme not in ('http','https') or not url.hostname or url.username or url.password:
                    raise ValueError('Use an HTTP(S) provider URL without embedded credentials')
            if not out.get('model'): raise ValueError('Model name is required')
            if primary: out['default']=out.pop('model')
            return out
        model=entry(payload['model'],True) if 'model' in payload else None
        chain=payload.get('fallbacks')
        if chain is not None:
            if not isinstance(chain,list) or len(chain)>8: raise ValueError('Choose up to eight ordered fallbacks')
            chain=[entry(row) for row in chain]
        c=cc.load(h)
        if 'tiers' in payload:
            c.models=payload['tiers'];c.__post_init__()
        timezone=payload.get('timezone')
        if timezone is not None:
            from zoneinfo import ZoneInfo
            ZoneInfo(text(timezone,'timezone',100))
        def mutate(cfg):
            if model is not None:
                old=cfg.get('model') if isinstance(cfg.get('model'),dict) else {}
                cfg['model']={**old,**model}
                if 'base_url' not in model: cfg['model'].pop('base_url',None)
            if chain is not None: cfg['fallback_providers']=chain
            if timezone is not None: cfg['timezone']=timezone
        save_config(h,mutate)
        if 'tiers' in payload: c.save()
        return {'saved':True,'note':'Use Apply job models to update existing job pins; restart the gateway to reload persistent workers.'}

    @app.post('/api/credentials')
    def credential(payload:dict):
        rt,p,h=context()
        key=text(payload.get('name'),'credential name',100)
        value=text(payload.get('value'),'credential value',10000,empty=True)
        rows=rt.catalog() or FALLBACK_CATALOG
        allowed={v for row in rows for v in row.get('api_key_env_vars',[])}|{'TELEGRAM_BOT_TOKEN','TELEGRAM_ALLOWED_USERS','DISCORD_BOT_TOKEN','DISCORD_ALLOWED_USERS'}
        if key not in allowed: raise ValueError('Choose a credential from the provider or messaging catalog')
        path=h/'.env'
        with cp.file_lock(h/'.companion-env.lock'):
            lines=path.read_text(encoding='utf-8').splitlines() if path.exists() else []
            lines=[line for line in lines if not re.match(r'^\s*(?:export\s+)?'+re.escape(key)+r'\s*=',line)]
            if value: lines.append(key+'='+json.dumps(value))
            cp.atomic_write(path,'\n'.join(lines)+'\n')
            if os.name!='nt': path.chmod(0o600)
        return {'saved':key,'configured':bool(value)}

    @app.post('/api/models/probe')
    def probe(payload:dict):
        model=text(payload.get('model',''),'model',300,empty=True)
        provider=text(payload.get('provider',''),'provider',100,empty=True)
        def action(rt,p,h,report):
            report('Making one small inference request using Hermes')
            args=['chat','--quiet','--oneshot','--ignore-rules','--max-turns','1',
                  '-q','Reply with exactly: CONNECTION_OK. Do not use any tools.']
            if model: args+=['--model',model]
            if provider: args+=['--provider',provider]
            r=rt.run(args,home=h,timeout=180)
            return {'response':hr.redact(r.stdout)[-2000:],'tested_at':dt.datetime.now(dt.timezone.utc).isoformat(),
                    'model_requested':model or 'profile default','note':'A response proves this request worked; the configured fallback chain may have answered.'}
        return op('Test model response',action)

    @app.post('/api/jobs/apply-models')
    def apply_models():
        def action(rt,p,h,report):
            from kit.cli.models import apply_job_models
            c=cc.load(h)
            return apply_job_models(c,run=lambda args:rt.run(args,home=h))
        return op('Apply job models',action)

    @app.get('/api/jobs')
    def jobs():
        from kit.cli.common import _read_jobs
        rt,p,h=context()
        return {'timezone':cc.load(h).timezone,'jobs':[{k:row.get(k) for k in ('id','name','schedule','enabled','no_agent','model','model_provider','last_status','next_run_at')}
                        for row in _read_jobs(h/'cron/jobs.json')['jobs']]}

    @app.post('/api/jobs/{ident}/{action}')
    def job_action(ident:str,action:str,payload:dict):
        if action not in ('pause','resume','run','edit'):raise ValueError('Unknown job action')
        from kit.cli.common import _read_jobs
        rt,p,h=context()
        row=next((j for j in _read_jobs(h/'cron/jobs.json')['jobs'] if j.get('id')==ident),None)
        if not row:raise ValueError('Job not found in this profile')
        if row.get('no_agent') and action=='pause':raise ValueError('Model-free continuity and maintenance jobs remain active. Pause the model-backed routine instead.')
        args=['cron',action,ident]
        if action=='edit':args+=['--schedule',text(payload.get('schedule'),'schedule',120)]
        return op('Job '+action,lambda rt,p,h,report:{'output':hr.redact(rt.run(args,home=h).stdout),
            'note':'Run now queues a job for the next scheduler tick; the owning gateway must be running.' if action=='run' else 'Saved by Hermes.'})

    @app.post('/api/jobs/history')
    def job_history():
        return op('Recent scheduled runs',lambda rt,p,h,report:{'output':hr.redact(rt.run(['cron','runs'],home=h).stdout)})

    @app.post('/api/maintenance/{action}')
    def maintenance(action:str):
        if action not in ('doctor','repair','activate','pause','update','version'): raise ValueError('Unknown maintenance action')
        def run(rt,p,h,report):
            if action in ('update','version'):
                args=['--version'] if action=='version' else ['update','--yes']
                result=rt.run(args,home=rt.root,timeout=1800,check=False)
            else:
                args={'doctor':['doctor'],'repair':['repair'],'activate':['schedule','active'],'pause':['schedule','paused']}[action]
                result=rt.run(['--home',str(h),*args],home=h,kit=True,timeout=600,check=False)
            if result.returncode: raise ValueError(hr.redact(result.stderr or result.stdout)[-12000:])
            return {'output':hr.redact(result.stdout)[-20000:]}
        return op(action.title(),run)

    @app.get('/api/gateway')
    def gateway_status():
        import companion_gateway as gateway
        c=load()
        return {**gateway.status(c),'preflight':gateway.preflight(c)}

    @app.post('/api/gateway/{action}')
    def gateway_action(action:str,payload:dict):
        if action not in ('status','install','uninstall','start','stop','restart','shared','dedicated','restart-root'): raise ValueError('Unknown gateway action')
        def run(rt,p,h,report):
            import companion_gateway as gateway
            c=cc.load(h)
            if action in ('shared','dedicated'): return gateway.configure(c,action)
            state=gateway.status(c)
            owner=Path(state['owner_home'])
            if action=='uninstall':
                if state['mode']=='shared':raise ValueError('Select the root profile to uninstall its shared service.')
                return {'output':hr.redact(rt.run(['gateway','uninstall'],home=h).stdout)}
            if action=='restart-root':
                if not payload.get('affects_all_profiles'):raise ValueError('Confirm the root restart, which affects every shared profile.')
                args=['gateway','restart']
                if any(u['scope']=='system' for u in gateway.service_units(rt.root)):args+=['--system']
                result=rt.run(args,home=rt.root,timeout=180)
                plan=gateway.saved(c)
                if plan:
                    plan['restart_required']=False
                    cp.atomic_write(h/gateway.PLAN,json.dumps(plan,indent=2)+'\n')
                return {'output':hr.redact(result.stdout)}
            if action=='stop':
                if state['mode']=='shared' and not payload.get('affects_all_profiles'):
                    raise ValueError('Stopping the shared gateway affects all its profiles. Confirm this in the app.')
                return {'output':hr.redact(rt.run(['gateway','stop'],home=owner).stdout)}
            args=['--home',str(h),'gateway','--action',action]
            if payload.get('root_restarted'):args+=['--root-restarted']
            return {'output':hr.redact(rt.run(args,home=h,kit=True,timeout=180).stdout)}
        return op('Gateway '+action,run)

    @app.get('/api/sessions')
    def session_list(before:str|None=None,limit:int=100): return hr.sessions_page(load(),limit,before)

    @app.get('/api/sessions/{ident}')
    def session_messages(ident:str,before:str|None=None,limit:int=200):
        c=load();page=hr.messages_page(c,ident,limit,before);rows=page['messages']
        from .content import catalog
        references=[]
        for row in rows:
            content=row.get('content') or ''
            if not isinstance(content,str):content=json.dumps(content,ensure_ascii=False)
            row['content']=content
            matches=re.findall(r'!\[[^\]]*\]\(([^)]+)\)|MEDIA:\s*([^\s]+)',content)
            references.append({value.strip('"\'') for pair in matches for value in pair if value})
        paths=set().union(*references) if references else set()
        media=catalog(c,reference_paths=paths)['items'] if paths else []
        for row,paths in zip(rows,references):
            row['attachments']=[]
            for item in media:
                if item['kind'] not in ('image','audio','video'):continue
                copy=next((copy for copy in item.get('copies',[item]) if copy['path'] in paths or str(c.data/copy['path']) in paths),None)
                if copy:row['attachments'].append({**item,**copy})
                if len(row['attachments'])==12:break
        return {**page,'messages':rows,'session':ident}

    @app.get('/api/activity')
    def activity():
        from kit.cli.common import _read_jobs
        from .content import catalog
        c=load();rows=[]
        for job in _read_jobs(c.home/'cron/jobs.json')['jobs']:
            rows.append({'kind':'job','title':job.get('name','Scheduled job'),
                'status':job.get('last_status') or 'Not run yet','at':job.get('last_run_at'),
                'detail':hr.redact(str(job.get('last_error') or ''))[:1200],'next':job.get('next_run_at'),'enabled':bool(job.get('enabled')),'id':job.get('id')})
        for item in catalog(c)['items'][:60]:
            rows.append({'kind':'content','title':item['title'],'status':'Saved','at':item['at'],'media':item})
        def event_time(row):
            try:return dt.datetime.fromisoformat(str(row.get('at')).replace('Z','+00:00')).timestamp()
            except (ValueError,TypeError):return 0
        return {'events':sorted(rows,key=event_time,reverse=True)[:100]}


    @app.post('/api/chat')
    def chat(payload:dict):
        message=payload.get('message')
        if not isinstance(message,str) or not message.strip() or len(message)>30000: raise ValueError('Write a message (up to 30,000 characters)')
        session=payload.get('session')
        c=load()
        if session: hr.messages(c,text(session,'session',200))
        def run(rt,p,h,report):
            report('Waiting for '+c.agent)
            args=['chat','--quiet','--oneshot','-q',message]
            if session:args+=['--resume',session]
            # No auto-approval of arbitrary existing hooks. Setup has its own
            # explicit, reviewable hook approval action.
            before={r['id'] for r in hr.sessions(c)}
            r=rt.chat(args,home=h,report=report)
            after=hr.sessions(c)
            new=getattr(r,'session',None) or next((row['id'] for row in after if row['id'] not in before and row.get('source') in ('cli','desktop','tui')),session)
            return {'response':ANSI_TEXT(r.stdout),'session':new,
                    'messages':hr.messages(c,new) if new else [],
                    'note':'Hermes owns this conversation. All channels share this profile’s identity, memory, and lived state.'}
        return op('Chat with '+c.agent,run)

    @app.get('/api/hooks')
    def hooks():
        rt,p,h=context()
        # Present exactly what will be approved, including existing user hooks.
        hooks=config(h).get('hooks',{})
        return {'hooks':hooks,'digest':hashlib.sha256(json.dumps(hooks,sort_keys=True).encode()).hexdigest(),
                'note':'Approval executes configured shell hooks on subsequent Hermes turns.'}

    @app.post('/api/hooks/approve')
    def approve(payload:dict):
        rt,p,h=context()
        existing=config(h).get('hooks',{})
        digest=hashlib.sha256(json.dumps(existing,sort_keys=True).encode()).hexdigest()
        if payload.get('digest')!=digest: raise ValueError('Reload and review the current hooks before approving')
        # Hermes's native hook verifier writes approval state during chat. The
        # supplied message makes that first conversation an explicit user action.
        message=text(payload.get('message','Hello.'),'first message',1000)
        return op('Approve hooks and say hello',lambda rt,p,h,report:{'response':ANSI_TEXT(rt.run(
            ['chat','--quiet','--oneshot','--accept-hooks','-q',message],home=h,timeout=600).stdout)})

    @app.get('/api/vault')
    def vault_list(path:str=''):
        from . import vault
        return vault.listing(load(),path)

    @app.get('/api/vault/file')
    def vault_read(path:str):
        from . import vault
        return vault.read(load(),path)

    @app.get('/api/vault/search')
    def vault_search(q:str):
        from . import vault
        return vault.search(load(),q)

    @app.post('/api/vault/trash')
    def vault_trash(payload:dict):
        from . import vault
        try:return vault.trash(load(),payload.get('path'),payload.get('revision'))
        except FileExistsError as exc:raise HTTPException(409,str(exc))

    @app.get('/api/vault/trash')
    def vault_trash_list():
        from . import vault
        return vault.trash_list(load())

    @app.post('/api/vault/restore')
    def vault_restore(payload:dict):
        from . import vault
        try:return vault.restore(load(),payload.get('id'))
        except FileExistsError as exc:raise HTTPException(409,str(exc))

    @app.get('/api/vault/download')
    def vault_download(path:str):
        from . import vault
        from fastapi.responses import FileResponse
        target=vault.resolve(load(),path)
        if not target.is_file():raise ValueError('File not found')
        return FileResponse(target,filename=target.name,media_type='application/octet-stream')

    @app.get('/api/vault/export')
    def vault_export():
        from . import vault
        from fastapi.responses import FileResponse
        from starlette.background import BackgroundTask
        import zipfile
        handle=tempfile.NamedTemporaryFile(suffix='.zip',delete=False);target=Path(handle.name);handle.close()
        try:
            total=0
            with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED) as archive:
                for path,relative in vault.files(load()):
                    total+=path.stat().st_size
                    if total>2_000_000_000:raise ValueError('Use the vault folder directly for exports larger than 2 GB')
                    archive.write(path,relative)
            return FileResponse(target,filename='companion-vault.zip',media_type='application/zip',background=BackgroundTask(target.unlink))
        except Exception:
            target.unlink(missing_ok=True);raise

    @app.put('/api/vault/file')
    def vault_write(payload:dict):
        from . import vault
        try:return vault.write(load(),payload.get('path'),payload.get('text'),payload.get('revision'))
        except FileExistsError as exc: raise HTTPException(409,str(exc))

    @app.get('/api/feelings')
    def feelings_read():
        import companion_feelings as feelings
        import companion_integrity, companion_intimacy
        c=load()
        integrity=companion_integrity.verify_integrity(c)
        intimacy=companion_intimacy.compute(c)
        return {**feelings.settings(c),'state':feelings.compute(c),'integrity_lockout':False,'integrity_warning':None,'intimacy':intimacy}

    @app.put('/api/feelings/settings')
    def feelings_settings(payload:dict):
        import companion_feelings as feelings
        try:return feelings.save_settings(load(),payload.get('settings'),payload.get('revision'))
        except FileExistsError as exc:raise HTTPException(409,str(exc))

    @app.get('/api/feelings/experiences')
    def feelings_history(limit:int=30,before:str|None=None):
        import companion_feelings as feelings
        from .runtime import _page_cursor,_encode_cursor
        if not 1<=limit<=100:raise ValueError('Experience page size must be 1–100')
        cursor=_page_cursor(before)
        if cursor and not isinstance(cursor[1],str):raise ValueError('Invalid experience cursor')
        now=dt.datetime.now(dt.timezone.utc)
        rows=[r for r in feelings.experiences(load()) if feelings._stamp(r['at'])<=now]
        key=lambda row:(feelings._stamp(row['at']).timestamp(),row['id'])
        rows.sort(key=key,reverse=True);total=len(rows)
        if cursor:rows=[r for r in rows if key(r)<tuple(cursor)]
        more=len(rows)>limit;rows=rows[:limit]
        return {'experiences':rows,'total':total,'next_cursor':_encode_cursor(*key(rows[-1])) if more else None}

    @app.post('/api/feelings/experiences')
    def feelings_record(payload:dict):
        import companion_feelings as feelings
        try:return feelings.record(load(),payload)
        except FileExistsError as exc:raise HTTPException(409,str(exc))

    @app.get('/api/relationship')
    def relationship():
        import companion_notes as notes, companion_integrity, companion_intimacy
        c=load();rows=notes.moments(c,None)
        active=[r for r in rows if r.get('status')=='active']
        kinds={r['moment'] for r in active}
        integrity=companion_integrity.verify_integrity(c)
        intimacy=companion_intimacy.compute(c)
        return {'bars':(__import__('companion_bars').compute(c) if c.bars else None),'moments':rows,'kinds':notes.LABELS,'boundary':c.boundary,'settings':{k:getattr(c,k) for k in ('relationship_progression','relationship_pace','peer_interaction','bars','explicit')},
                'milestones':[{'label':label,'earned':kind in kinds} for kind,label in [('first','A first to remember'),('joke','An inside joke'),('ritual','A shared ritual'),('nickname','A name between you'),('milestone','A meaningful milestone')]],
                'intimacy':intimacy,
                'integrity_lockout':False,
                'integrity_warning':None,
                'note':'Milestones reflect saved shared history. Time away never removes progress.'}

    @app.post('/api/relationship')
    def relationship_add(payload:dict):
        import companion_notes as notes
        return notes.add_moment(load(),payload,dt.datetime.now(dt.timezone.utc))

    @app.post('/api/relationship/{ident}/retire')
    def relationship_retire(ident:str):
        import companion_notes as notes
        return notes.retire_moment(load(),ident,'Retired by the user in the app',dt.datetime.now(dt.timezone.utc))


def ANSI_TEXT(value):
    return hr.ANSI.sub('',value).strip()
