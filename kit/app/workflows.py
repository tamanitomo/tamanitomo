"""Guided workflow composition and private Civitai downloads, scoped to a Hermes installation."""
import json
import math
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import urllib.parse
import uuid
import companion_media as media
import companion_platform as cp
from companion_model_download import open_url,SLOTS,MAX_BYTES
from companion_workflow import create_recipe


def family(label):
    v=str(label).lower()
    if any(s in v for s in ('sdxl','pony','illustrious','noobai')):return 'sdxl'
    if 'sd 1' in v or 'sd1' in v:return 'sd15'
    if 'krea 2' in v or 'krea2' in v:return 'krea2'
    if 'zimage' in v or 'z-image' in v or 'z image' in v:return 'zimage'
    return 'unknown'


def settings(root):
    p=root/'companion-comfy-private.json'
    if p.is_symlink():raise ValueError('Comfy settings must not be a symbolic link')
    return json.loads(p.read_text()) if p.exists() else {'mode':'local','host':'','directory':str(root/'companion-engines/comfyui'),'endpoint':'http://127.0.0.1:8188','api_key':''}


def public_settings(d):return {**{k:v for k,v in d.items() if k!='api_key'},'api_key_configured':bool(d.get('api_key'))}


def save_settings(root,payload):
    current=settings(root);mode=payload.get('mode',current['mode']);host=payload.get('host',current['host']);directory=payload.get('directory',current['directory'])
    if mode not in ('local','ssh'):raise ValueError('Choose local or SSH Comfy host')
    if mode=='ssh' and (not isinstance(host,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.@-]{0,150}',host)):raise ValueError('Use a configured SSH host alias')
    if not isinstance(directory,str) or not directory or '\0' in directory or '\n' in directory:raise ValueError('Choose a ComfyUI directory')
    if mode=='ssh' and not directory.startswith('/'):raise ValueError('Remote ComfyUI directory must be absolute')
    if mode=='local' and not Path(directory).expanduser().is_absolute():raise ValueError('ComfyUI directory must be absolute')
    key=payload.get('api_key')
    if key is not None and (not isinstance(key,str) or len(key)>2000 or any(ord(c)<32 for c in key)):raise ValueError('Invalid API key')
    current.update(mode=mode,host=host,directory=directory,endpoint=media.endpoint(payload.get('endpoint',current['endpoint'])))
    if key:current['api_key']=key
    if payload.get('clear_key'):current['api_key']=''
    path=root/'companion-comfy-private.json';cp.atomic_write(path,json.dumps(current,indent=2));path.chmod(0o600)
    return public_settings(current)


def api_json(path,key):
    try:
        with open_url('https://civitai.com/api/v1/'+path,key,30) as r:return json.load(r)
    except Exception as exc:raise ValueError('Civitai could not return this model. Check the URL, API key and access permissions.') from exc


def identify(url):
    if not isinstance(url,str):raise ValueError('Paste a Civitai model page URL')
    u=urllib.parse.urlsplit(url)
    if u.scheme!='https' or u.hostname not in ('civitai.com','www.civitai.com') or u.username or u.password:raise ValueError('Paste an HTTPS Civitai model page URL')
    match=re.fullmatch(r'/models/(\d+)(?:/[^/]*)?/?',u.path)
    if not match:raise ValueError('Use a Civitai /models/ page')
    version=urllib.parse.parse_qs(u.query).get('modelVersionId',[''])[0]
    if version and not version.isdigit():raise ValueError('Invalid model version')
    return int(match.group(1)),int(version) if version else None


def inspect_model(root,url,version_id=None):
    model_id,linked=identify(url);key=settings(root).get('api_key','');model=api_json('models/'+str(model_id),key)
    versions=model.get('modelVersions') or []
    wanted=version_id or linked
    selected=next((v for v in versions if v['id']==wanted),None) if wanted else next(iter(versions),None)
    if selected is None:raise ValueError('The selected model version is unavailable')
    files=[]
    for f in selected.get('files',[]):
        if f.get('type')!='Model' or Path(f.get('name','')).suffix.lower() not in ('.safetensors','.gguf'):continue
        sha=(f.get('hashes') or {}).get('SHA256','');size=float(f.get('sizeKB') or 0)*1024
        if not re.fullmatch('[a-fA-F0-9]{64}',sha) or not math.isfinite(size) or not 0<size<=MAX_BYTES:continue
        files.append({'id':f['id'],'name':f['name'],'size_bytes':int(size),'sha256':sha,'download_url':f.get('downloadUrl','')})
    return {'id':model_id,'name':model.get('name','Model'),'type':model.get('type',''),'version_id':selected['id'],
      'version':selected.get('name',''),'base_model':selected.get('baseModel','Unknown'),'family':family(selected.get('baseModel')),
      'versions':[{'id':v['id'],'name':v.get('name',''),'base_model':v.get('baseModel','')} for v in versions],
      'files':files,'trigger_words':selected.get('trainedWords') or [],
      'license':{k:model.get(k) for k in ('allowNoCredit','allowCommercialUse','allowDerivatives','allowDifferentLicense')},'page':url}


def download(root,payload,report):
    # Re-fetch the selected version; never trust browser-supplied file URLs or hashes.
    data=inspect_model(root,payload.get('url',''),payload.get('version_id'))
    f=next((f for f in data['files'] if f['id']==payload.get('file_id')),None)
    if f is None:raise ValueError('Choose an available weight file')
    slot=payload.get('slot')
    permitted={'Checkpoint':{'checkpoint','model'},'LORA':{'lora'},'LoCon':{'lora'},'VAE':{'vae'},'Text Encoder':{'clip'}}
    if slot not in permitted.get(data['type'],set()):raise ValueError('This Civitai model type does not fit the selected slot')
    config=settings(root)
    request={'root':config['directory'],'slot':slot,'filename':f['name'],'url':f['download_url'],'sha256':f['sha256'],
             'size_bytes':f['size_bytes'],'api_key':config.get('api_key',''),'family':data['family'],'base_model':data['base_model'],
             'model_id':data['id'],'version_id':data['version_id'],'file_id':f['id']}
    result=run_worker(config,request,report)
    return {**result,'name':data['name'],'trigger_words':data['trigger_words'],'note':'Verified weights installed. Refresh the model list before building.'}


def run_worker(config,request,report=lambda _:None):
    worker=Path(__file__).resolve().parents[1]/'scripts/companion_model_download.py'
    args=[sys.executable,str(worker)]
    if config['mode']=='ssh':args=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',config['host'],'python3 -c '+shlex.quote(worker.read_text())]
    proc=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
    result=None;error='Model downloader failed; check the Comfy path and SSH access'
    try:
        proc.stdin.write(json.dumps(request));proc.stdin.close()
        for line in proc.stdout:
            if line.startswith('PROGRESS='):report(line[9:].strip())
            elif line.startswith('RESULT='):result=json.loads(line[7:])
            elif line.startswith('ERROR='):error=line[6:].strip()
        code=proc.wait(timeout=10)
    finally:
        if proc.poll() is None:proc.kill();proc.wait()
    if code or result is None:raise ValueError(error)
    return result


def register(app,select,load):
    @app.get('/api/workflows')
    def get():
        rt,_=select();return {'settings':public_settings(settings(rt.root)),'families':{'sdxl':'SDXL / Pony / Illustrious','sd15':'SD 1.5','zimage':'Z-Image','krea2':'Krea 2'}}
    @app.get('/api/workflows/library')
    def library():
        rt,_=select();config=settings(rt.root)
        return run_worker(config,{'action':'library','root':config['directory']})
    @app.post('/api/workflows/settings')
    def save(payload:dict):
        rt,_=select();return save_settings(rt.root,payload)
    @app.post('/api/workflows/inspect')
    def inspect(payload:dict):
        rt,_=select();return inspect_model(rt.root,payload.get('url',''),payload.get('version_id'))
    @app.post('/api/workflows/download')
    def install(payload:dict):
        rt,p=select();return app.state.operations.submit(str(rt.root),'Download Comfy weights',lambda report:download(rt.root,payload,report),profile=p)
    @app.post('/api/workflows/build')
    def build(payload:dict):
        rt,_=select();p=create_recipe(payload);p['endpoint']=settings(rt.root)['endpoint']
        media.validate({'version':1,'presets':[p],'routes':{},'default_preset':p['id']})
        schema=media.request_json(p['endpoint']+'/object_info')
        for node in p['workflow'].values():
            if node['class_type'] not in schema:raise ValueError('Install the required Comfy node first: '+node['class_type'])
            for key,value in node['inputs'].items():
                spec=schema[node['class_type']].get('input',{}).get('required',{}).get(key)
                if spec and isinstance(spec[0],list) and isinstance(value,str) and value not in spec[0]:raise ValueError('Choose an installed '+key+': '+value)
        return p
