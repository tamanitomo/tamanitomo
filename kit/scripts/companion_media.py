#!/usr/bin/env python3
"""Named, per-companion image recipes shared by the studio and Hermes jobs."""
from __future__ import annotations
import argparse
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.request
import urllib.parse
import uuid
import companion_config as cc
from companion_platform import atomic_write, file_lock

PARTS=('quality','identity','scene','wardrobe','lighting','camera')
CATEGORIES=('portrait','anime','realistic','landscape','other')
CONFIG='companion-images.json'

def load(c):
    path=c.home/CONFIG
    if path.exists():return json.loads(path.read_text())
    return {'version':1,'identity_override':None,'presets':[],'routes':{},'default_preset':'','inherit':False}

def hermes_bridge(c,command,payload=None):
    import subprocess
    from companion_gateway import _env_values
    checkout=c.hermes_root/'hermes-agent'
    python=checkout/'venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if not python.is_file():raise ValueError('Hermes Python is unavailable')
    env=dict(os.environ,**_env_values(c.home));env.update(HERMES_HOME=str(c.home),PYTHONPATH=str(checkout))
    env.pop('HERMES_PROFILE',None)
    run=subprocess.run([str(python),str(Path(__file__).with_name('companion_image_provider.py')),command],
        input=json.dumps(payload or {}),env=env,cwd=checkout,capture_output=True,text=True,timeout=30 if command=='catalog' else 600)
    try:reply=json.loads(next(line.split('=',1)[1] for line in run.stdout.splitlines() if line.startswith('COMPANION_IMAGE=')))
    except (StopIteration,ValueError):raise ValueError('Hermes image provider is unavailable; inspect its setup')
    if isinstance(reply,dict) and reply.get('error'):raise ValueError(str(reply['error']))
    if run.returncode:raise ValueError('Hermes image provider failed')
    return reply

def discovered_presets(c):
    rows=hermes_bridge(c,'catalog')
    if not isinstance(rows,list):raise ValueError('Hermes returned an invalid image provider catalog')
    return [dict(id='hermes-'+r['id'],name='ChatGPT (OAuth)' if r['id']=='openai-codex' else r['name'],provider='hermes',hermes_provider=r['id'],
                 model=r.get('model',''),category='realistic' if 'chatgpt' in r['id'] or 'openai' in r['id'] else 'portrait',
                 parts={},negative='',endpoint='',available=r.get('available',False),active=r.get('active',False))
            for r in rows if re.fullmatch('[a-z0-9][a-z0-9_-]{0,55}',r.get('id',''))]

def effective(c):
    data=load(c)
    if data.get('inherit') and c.profile:
        own_identity=data.get('identity_override')
        data=copy.deepcopy(load(cc.load(c.hermes_root)))
        data['identity_override']=own_identity
        for preset in data.get('presets',[]):
            preset.get('parts',{}).pop('identity',None)
    return data

def revision(c):
    path=c.home/CONFIG
    return hashlib.sha256(path.read_bytes() if path.exists() else b'').hexdigest()

def endpoint(value):
    url=urllib.parse.urlsplit(value)
    if url.scheme not in ('http','https') or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('Use an HTTP(S) endpoint without credentials, query, or fragment')
    return value.rstrip('/')

def validate(data):
    if not isinstance(data,dict) or data.get('version')!=1:raise ValueError('Expected image preset format version 1')
    if data.get('identity_override') is not None and (not isinstance(data['identity_override'],str) or len(data['identity_override'])>20000):raise ValueError('Identity prompt is too long')
    if not isinstance(data.get('inherit',False),bool):raise ValueError('Inheritance must be true or false')
    presets=data.get('presets',[])
    if not isinstance(presets,list) or len(presets)>100:raise ValueError('At most 100 presets are supported')
    ids=set()
    for p in presets:
        if not isinstance(p,dict):raise ValueError('Each preset must be an object')
        ident=p.get('id','')
        if not isinstance(ident,str) or not re.fullmatch('[a-z0-9][a-z0-9_-]{0,63}',ident) or ident in ids:raise ValueError('Preset IDs must be unique lowercase names')
        ids.add(ident)
        if not isinstance(p.get('name'),str) or not 1<=len(p['name'])<=100:raise ValueError('Name each preset')
        if p.get('provider') not in ('comfyui','openai','hermes'):raise ValueError('Choose ComfyUI, Hermes, or an OpenAI-compatible image API')
        if p['provider']=='hermes' and not re.fullmatch('[a-z0-9][a-z0-9_-]{0,55}|',p.get('hermes_provider','')):raise ValueError('Invalid Hermes image provider')
        if not isinstance(p.get('model',''),str) or len(p.get('model',''))>300:raise ValueError('Invalid image model')
        if p['provider']!='hermes':endpoint(p.get('endpoint',''))
        if not isinstance(p.get('include_identity',True),bool):raise ValueError('Include identity must be true or false')
        if p.get('category') not in CATEGORIES:raise ValueError('Choose an image category')
        for k,v in p.get('parts',{}).items():
            if k not in PARTS or not isinstance(v,str) or len(v)>20000:raise ValueError('Invalid prompt component')
        if not isinstance(p.get('negative',''),str) or len(p.get('negative',''))>20000:raise ValueError('Invalid negative prompt')
        if p['provider']=='comfyui':
            workflow=p.get('workflow',{})
            if not isinstance(workflow,dict) or not workflow or 'nodes' in workflow:raise ValueError('Import a ComfyUI API-format workflow, not the visual editor format. Use Export (API) in ComfyUI.')
            if len(workflow)>1000:raise ValueError('Workflow is too large')
            for node in workflow.values():
                if not isinstance(node,dict) or not isinstance(node.get('class_type'),str) or not isinstance(node.get('inputs'),dict):raise ValueError('Invalid ComfyUI API node')
            mappings=p.get('mappings',{})
            if 'prompt' not in mappings and 'identity' not in mappings:raise ValueError('Map a positive prompt or identity input')
            for key,target in mappings.items():
                if key not in (*PARTS,'prompt','negative','seed','width','height','steps','cfg','denoise','reference_image'):raise ValueError('Unknown workflow mapping')
                if not isinstance(target,list) or len(target)!=2 or str(target[0]) not in workflow or target[1] not in workflow[str(target[0])]['inputs']:raise ValueError('Each mapping must name an existing node ID and input')
        denoise=p.get('denoise',1.)
        if isinstance(denoise,bool) or not isinstance(denoise,(int,float)) or not 0<denoise<=1:raise ValueError('Denoise must be above 0 and at most 1')
        if not isinstance(p.get('requires_reference',False),bool):raise ValueError('Reference requirement must be true or false')
        key=p.get('api_key_env','')
        if key and (not isinstance(key,str) or not re.fullmatch('[A-Z][A-Z0-9_]{0,100}',key)):raise ValueError('Specify an environment variable name for the API key')
        for key,lo,hi in (('width',64,4096),('height',64,4096),('steps',1,150),('seed',-1,2**53-1)):
            v=p.get(key,{'width':832,'height':1216,'steps':18,'seed':-1}[key])
            if isinstance(v,bool) or not isinstance(v,int) or not lo<=v<=hi:raise ValueError(f'Invalid {key}')
        if not isinstance(p.get('cfg',5),(int,float)) or not 0<=p.get('cfg',5)<=50:raise ValueError('CFG must be 0–50')
    routes=data.get('routes',{})
    if not isinstance(routes,dict) or any(k not in CATEGORIES or v not in ids for k,v in routes.items()):raise ValueError('Category routes must reference saved presets')
    if data.get('default_preset') and data['default_preset'] not in ids:raise ValueError('Default preset does not exist')
    if len(json.dumps(data))>4_000_000:raise ValueError('Preset file exceeds 4 MB')
    return data

def save(c,data,expected):
    validate(data)
    with file_lock(c.home/'.companion-images.lock'):
        if revision(c)!=expected:raise FileExistsError('Image settings changed. Reload before saving.')
        path=c.home/CONFIG
        if path.exists():atomic_write(c.home/'companion-config-backups'/('images-'+uuid.uuid4().hex+'.json'),path.read_text())
        atomic_write(path,json.dumps(data,indent=2,ensure_ascii=False))

def template():
    # PlantMilk's separation of trigger/identity/scene/wardrobe/lighting/camera,
    # expressed using standard nodes so no custom extension is needed.
    return {'id':'comfy-plantmilk','name':'Comfy – PlantMilk','category':'anime','provider':'comfyui',
      'endpoint':'http://127.0.0.1:8188','parts':{'quality':'anime illustration, detailed','wardrobe':'','lighting':'soft light','camera':'portrait'},
      'negative':'low quality, blurry, malformed hands','width':832,'height':1216,'steps':18,'cfg':5,'seed':-1,
      'workflow':{
        '1':{'class_type':'CheckpointLoaderSimple','inputs':{'ckpt_name':'CHOOSE_YOUR_CHECKPOINT.safetensors'}},
        '3':{'class_type':'CLIPSetLastLayer','inputs':{'clip':['1',1],'stop_at_clip_layer':-2}},
        '4':{'class_type':'CLIPTextEncode','inputs':{'clip':['3',0],'text':''}},
        '5':{'class_type':'CLIPTextEncode','inputs':{'clip':['3',0],'text':''}},
        '7':{'class_type':'EmptyLatentImage','inputs':{'width':832,'height':1216,'batch_size':1}},
        '9':{'class_type':'KSampler','inputs':{'model':['1',0],'positive':['4',0],'negative':['5',0],'latent_image':['7',0],'seed':0,'steps':18,'cfg':5,'sampler_name':'euler_ancestral','scheduler':'normal','denoise':1}},
        '10':{'class_type':'VAEDecode','inputs':{'samples':['9',0],'vae':['1',2]}},
        '11':{'class_type':'SaveImage','inputs':{'images':['10',0],'filename_prefix':'Companion'}}},
      'mappings':{'prompt':['4','text'],'negative':['5','text'],'width':['7','width'],'height':['7','height'],'seed':['9','seed'],'steps':['9','steps'],'cfg':['9','cfg']}}

def compile(c,preset_id='',category='portrait',overrides=None,draft=None):
    import companion_portrait as portrait
    data=effective(c)
    if draft is not None:
        if not isinstance(draft,dict) or not draft.get('provider'):
            raise ValueError('That draft workflow is not complete enough to render')
        preset={**draft,'id':draft.get('id') or 'draft'}
    else:
        ident=preset_id or data.get('routes',{}).get(category) or data.get('default_preset')
        preset=next((p for p in data['presets'] if p['id']==ident),None)
    if not preset:raise ValueError('Choose and save an image preset first')
    p=copy.deepcopy(preset);parts=dict(p.get('parts',{}))
    parts['identity']=(parts.get('identity') or portrait.identity_block(c)) if p.get('include_identity',True) else ''
    scene,_=portrait.scene_block(c)
    parts['scene']=parts.get('scene') or scene
    overrides=overrides or {}
    for k in PARTS:
        if k in overrides:parts[k]=str(overrides[k])
    prompt=', '.join(parts.get(k,'').strip().rstrip(',') for k in PARTS if parts.get(k,'').strip())
    if not prompt:raise ValueError('Write a scene or identity before generating')
    seed=p.get('seed',-1)
    if seed==-1:seed=int.from_bytes(os.urandom(6),'big')
    values={**parts,'prompt':prompt,'negative':p.get('negative',''),'seed':seed,
            **{k:p.get(k,d) for k,d in [('width',832),('height',1216),('steps',18),('cfg',5),('denoise',1.)]}}
    workflow=copy.deepcopy(p.get('workflow',{}))
    for key,(node,field) in p.get('mappings',{}).items():
        if key in values:workflow[str(node)]['inputs'][field]=values[key]
    reference=portrait.portrait_path(c)
    if p.get('requires_reference') and not reference.is_file():raise ValueError('Add a reference portrait before using this image-to-image preset')
    return {'preset':p,'parts':parts,'prompt':prompt,'negative':values['negative'],'seed':seed,'workflow':workflow,
            'reference_image':str(reference) if reference.is_file() and p['provider']=='comfyui' and p.get('mappings',{}).get('reference_image') else None}

def request_json(url,payload=None,headers=None):
    import http.client
    req=urllib.request.Request(url,data=json.dumps(payload).encode() if payload is not None else None,
                               headers={'Content-Type':'application/json',**(headers or {})})
    # Polling a queued image is safe to retry; submitting it again is not.
    attempts=3 if payload is None else 1
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req,timeout=120) as r:return json.loads(r.read(16_000_001))
        except urllib.error.HTTPError as exc:
            raise ValueError(f'Image server returned {exc.code}: '+exc.read(3000).decode(errors='replace')) from exc
        except (urllib.error.URLError,ConnectionError,TimeoutError,http.client.RemoteDisconnected):
            if attempt+1==attempts:raise
            time.sleep(attempt+1)

class ImageHeld(ValueError):
    def __init__(self,message,path,rating):
        super().__init__(message);self.path=path;self.rating=rating


def generate(c,preset_id='',category='portrait',overrides=None,report=lambda x:None,allow_nsfw=False,draft=None):
    try:return _generate(c,preset_id,category,overrides,report,allow_nsfw,draft)
    except ImageHeld as held:
        # 'unknown' is the detector's uncertain band, and it earns the same one clothed retry as
        # a definite flag: without it an ambiguous image had no route to delivery at all.
        if allow_nsfw or held.rating not in ('nsfw','unknown'):raise
        import companion_media_review as review
        report(('Unintended nudity detected.' if held.rating=='nsfw' else 'The scan was uncertain about this image.')+
               ' Trying one clothed replacement; keeping the blurred original.')
        original=json.loads(held.path.with_suffix('.json').read_text())
        retry=dict(overrides or {})
        retry['scene']=(original.get('parts',{}).get('scene','')+
            '. Regenerate this same requested scene with every person fully clothed in the requested outfit. '
            'No exposed breasts, genitals, buttocks, or sexual activity. Preserve the requested subject count, setting and activity.')
        review.write_metadata(held.path,{'replacement_status':'retrying'})
        try:
            replacement=_generate(c,preset_id,category,retry,report,False,draft)
            target=Path(replacement['path']);meta=review.metadata(target)
            if meta.get('rating')!='safe' or meta.get('review',{}).get('status')!='passed':
                raise ValueError('Replacement did not pass scanning')
        except Exception:
            review.write_metadata(held.path,{'replacement_status':'failed'})
            raise ValueError(('Unintended nudity detected' if held.rating=='nsfw' else 'The scan was uncertain about this image')+
                '; one replacement attempt failed. The original remains held and blurred in Photos. '
                'Use --allow-nsfw if the adult content was intended.') from held
        review.write_metadata(held.path,{'replacement_status':'replaced','superseded_by':str(target.relative_to(c.data))})
        review.write_metadata(target,{'replaces':str(held.path.relative_to(c.data))})
        replacement['replaced_nsfw']=True
        return replacement


def _generate(c,preset_id='',category='portrait',overrides=None,report=lambda x:None,allow_nsfw=False,draft=None):
    result=compile(c,preset_id,category,overrides,draft);p=result['preset'];base=endpoint(p['endpoint']) if p['provider']!='hermes' else ''
    report('Generating with '+p['name'])
    if p['provider']=='hermes':
        reply=hermes_bridge(c,'generate',{'prompt':result['prompt'],'hermes_provider':p.get('hermes_provider',''),
            'image_url':result['reference_image'] if p.get('include_identity',True) else None,
            'model':p.get('model',''),'aspect_ratio':'landscape' if category=='landscape' else 'portrait'})
        if not reply.get('success'):raise ValueError(str(reply.get('error','Hermes returned no image')))
        from companion_timeline import load_image
        raw,_=load_image(reply['image'])
    elif p['provider']=='comfyui':
        graph=result['workflow']
        schema=request_json(base+'/object_info')
        for node_id,node in graph.items():
            if node['class_type'] not in schema:raise ValueError('Missing ComfyUI node: '+node['class_type'])
            for key,value in node['inputs'].items():
                spec=schema[node['class_type']].get('input',{}).get('required',{}).get(key)
                if p.get('mappings',{}).get('reference_image')==[node_id,key]:continue
                if spec and isinstance(spec[0],list) and isinstance(value,str) and value not in spec[0]:raise ValueError(f'Choose an installed value for {key}: {value}')
        if 'reference_image' in p.get('mappings',{}) and result['reference_image']:
            import mimetypes
            path=Path(result['reference_image']);boundary=uuid.uuid4().hex
            body=(f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{path.name}"\r\nContent-Type: {mimetypes.guess_type(path.name)[0]}\r\n\r\n').encode()+path.read_bytes()+f'\r\n--{boundary}--\r\n'.encode()
            req=urllib.request.Request(base+'/upload/image',data=body,headers={'Content-Type':'multipart/form-data; boundary='+boundary})
            with urllib.request.urlopen(req,timeout=30) as response:uploaded=json.load(response)
            node,field=p['mappings']['reference_image'];graph[str(node)]['inputs'][field]=uploaded['name']
        queued=request_json(base+'/prompt',{'prompt':graph,'client_id':uuid.uuid4().hex})
        if queued.get('node_errors'):raise ValueError('Workflow validation failed: '+json.dumps(queued['node_errors'])[:3000])
        ident=queued.get('prompt_id')
        if not ident:raise ValueError('ComfyUI did not return a prompt ID')
        deadline=time.monotonic()+600;history={}
        while time.monotonic()<deadline:
            history=request_json(base+'/history/'+str(ident)).get(str(ident),{})
            if history.get('status',{}).get('status_str')=='error':raise ValueError('ComfyUI generation failed: '+json.dumps(history.get('status'))[:2000])
            if history.get('outputs'):break
            time.sleep(1)
        images=[im for output in history.get('outputs',{}).values() for im in output.get('images',[]) if im.get('type')=='output']
        if not images:raise ValueError('No saved image returned; the job may still be queued. Check ComfyUI before retrying.')
        url=base+'/view?'+urllib.parse.urlencode(images[0])
        with urllib.request.urlopen(url,timeout=60) as response:raw=response.read(40_000_001)
    else:
        from companion_gateway import _env_values
        keys=_env_values(c.home)
        key=keys.get(p.get('api_key_env','')) or os.environ.get(p.get('api_key_env',''))
        headers={'Authorization':'Bearer '+key} if key else {}
        reply=request_json(base+'/images/generations',{'model':p.get('model',''),'prompt':result['prompt'],'size':f'{p.get("width",1024)}x{p.get("height",1024)}','n':1},headers)
        image=(reply.get('data') or [{}])[0]
        if image.get('b64_json'):raw=base64.b64decode(image['b64_json'],validate=True)
        elif image.get('url'):
            endpoint(image['url'])
            with urllib.request.urlopen(image['url'],timeout=60) as response:raw=response.read(40_000_001)
        else:raise ValueError('Image API did not return an image')
    if len(raw)>40_000_000:raise ValueError('Generated image exceeds 40 MB')
    import io
    from PIL import Image
    with Image.open(io.BytesIO(raw)) as image:
        image.verify();ext={'PNG':'.png','JPEG':'.jpg','WEBP':'.webp'}.get(image.format)
    if not ext:raise ValueError('Image must be PNG, JPEG or WebP')
    folder=c.data/'creations'/'image-studio';folder.mkdir(parents=True,exist_ok=True)
    ident=uuid.uuid4().hex;path=folder/(ident+ext);path.write_bytes(raw)
    atomic_write(folder/(ident+'.json'),json.dumps({'prompt':result['prompt'],'parts':result['parts'],'preset':p['name'],'seed':result['seed']},indent=2))
    import companion_media_review as review
    generation=('ComfyUI' if p['provider']=='comfyui' else p.get('hermes_provider') or p['provider'])+' · '+p['name']
    review.write_metadata(path,{'generation':generation,'preset_id':p['id'],'seed':result['seed']})
    if review.preferences(c)['review_before_delivery']:
        report('Reviewing the actual image before releasing it for delivery')
        try:decision=review.inspect(c,path,result['prompt'],allow_nsfw)
        except Exception:
            review.write_metadata(path,{'review':{'status':'unavailable'}})
            raise ValueError('Image saved for inspection in Photos, but review is unavailable. Do not send it; check the reviewer in Media preferences.')
        if decision['status']!='passed':raise ImageHeld('Image held for inspection in Photos; do not send it. '+str(decision.get('reason','It did not match the intended image.'))[:400],path,review.metadata(path)['rating'])
    meta=review.metadata(path)
    return {'path':str(path),'file':path.name,'provider':generation,'prompt':result['prompt'],'seed':result['seed'],
            'rating':meta['rating'],'blur':review.should_blur(review.preferences(c),meta),'review':meta.get('review')}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--home',type=Path)
    parser.add_argument('command',choices=['generate','prompt']);parser.add_argument('--category',default='portrait',choices=CATEGORIES)
    parser.add_argument('--preset',default='');parser.add_argument('--scene')
    parser.add_argument('--allow-nsfw',action='store_true',help='This image intentionally requests adult content')
    args=parser.parse_args();c=cc.load(args.home)
    kwargs={'allow_nsfw':args.allow_nsfw} if args.command=='generate' else {}
    print(json.dumps((generate if args.command=='generate' else compile)(c,args.preset,args.category,{'scene':args.scene} if args.scene else None,**kwargs),indent=2))
