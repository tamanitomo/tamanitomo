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

PARTS=('quality','identity','wardrobe','scene','feeling','lighting','camera')
CATEGORIES=('portrait','anime','realistic','landscape','other')
CONFIG='companion-images.json'

# Negatives that hold on every render, in every lane, at every relationship
# stage. They are not a preset field, not a setting and not editable from the
# interface, because the whole point of them is that no code path can drop
# them: not an imported workflow, not a cleared box, not the intimate switch
# below. A preset's own `negative` adds to this floor; nothing subtracts from
# it.
SAFETY_FLOOR=('child','children','kid','toddler','infant','baby','loli','shota',
  'preteen','pre-teen','teen','teenager','adolescent','underage','minor','childlike',
  'young girl','young boy','school child','age regression','de-aged','shrunken adult',
  'flat chest on a minor','infantilised')

# The bucket a companion may set aside, and the only one. New workflows start
# with this; an existing workflow without one simply has nothing to set aside.
MODESTY_DEFAULT='nude, topless, nsfw, explicit, nipples, genitalia'


# Terms that belong to the modesty bucket rather than the quality one, used to
# sort a workflow's single negative prompt into the two buckets. Matching is on
# the bare term with any weight stripped, so `(nsfw:1.2)` sorts like `nsfw`.
MODESTY_TERMS={'nsfw','nude','nudity','naked','topless','bottomless','nipples','areola',
  'lingerie','underwear only','see-through','see-through clothing','sheer clothing',
  'fetish','erotic','erotica','explicit','sexual','sex','genitalia','genitals','pubic hair',
  'suggestive','suggestive pose','provocative','seductive','seductive pose','bedroom eyes',
  'pinup','pin-up','cleavage focus','breast focus','ass focus','crotch focus','revealing clothing'}


def bare_term(term):
    """A term with its weight and brackets stripped, for comparison only."""
    t=str(term or '').strip()
    while t.startswith(('(','[')) and t.endswith((')',']')):t=t[1:-1].strip()
    if ':' in t:
        head,_,tail=t.rpartition(':')
        if head and tail.replace('.','',1).replace('-','',1).isdigit():t=head.strip()
    return t.strip().lower()


def sort_negative(text):
    """Sort one negative prompt into (always-on, modesty), dropping the floor.

    Terms the safety floor already carries are dropped rather than copied, since
    the floor applies to every render anyway and a duplicate in a preset only
    invites someone to edit the copy and believe they changed something.
    """
    floor={t.lower() for t in SAFETY_FLOOR}
    always,modesty=[],[]
    for term in split_terms(text):
        bare=bare_term(term)
        if bare in floor:continue
        (modesty if bare in MODESTY_TERMS else always).append(term)
    return ', '.join(always),', '.join(modesty)


def split_terms(text):
    """Split a prompt into terms on commas, without cutting inside a weight.

    `(white dress, ivory dress:1.3)` is one weighted group that happens to
    contain commas. Splitting on every comma would leave unbalanced brackets
    that ComfyUI reads as literal punctuation, so depth is tracked.
    """
    terms=[];depth=0;current=''
    for ch in str(text or ''):
        if ch in '([':depth+=1
        elif ch in ')]':depth=max(0,depth-1)
        if ch==',' and depth==0:
            terms.append(current.strip());current=''
        else:current+=ch
    terms.append(current.strip())
    return [t for t in terms if t]


def negative_prompt(preset,intimate=False):
    """Every negative that applies to a render, joined into one string.

    Three sources, and exactly one of them is ever set aside:

    - `SAFETY_FLOOR`, above, which always applies and is not a preset field;
    - `negative`, the workflow's own always-on terms — quality, anatomy,
      wardrobe and whatever else the person wants held on every render;
    - `modesty_negative`, which a companion who has reached full intimacy
      readiness may set aside, and which nothing else may.

    Order matters only for readability; a negative prompt is a bag of terms.
    """
    parts=[', '.join(SAFETY_FLOOR),str(preset.get('negative','') or '')]
    if not intimate:parts.append(str(preset.get('modesty_negative','') or ''))
    seen=[];known=set()
    for chunk in parts:
        for term in split_terms(chunk):
            if term.lower() not in known:
                known.add(term.lower());seen.append(term)
    return ', '.join(seen)


def intimacy_gate(c):
    """Whether the companion is free to choose an intimate render right now.

    The judgement already exists and is not re-made here: `companion_intimacy`
    weighs stage, opt-in, trust, unresolved hurt and boundary history, and this
    only asks it. One place decides, so there are never two that disagree.
    """
    try:
        import companion_intimacy as intimacy
        state=intimacy.compute(c)
    except Exception as exc:
        return False,['The closeness state could not be read: '+str(exc)[:200]]
    return bool(state.get('intimacy_ready')),list(state.get('intimacy_blockers') or [])

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
        own_source=data.get('identity_source')
        data=copy.deepcopy(load(cc.load(c.hermes_root)))
        data['identity_override']=own_identity
        if own_source is not None:data['identity_source']=own_source
        else:data.pop('identity_source',None)
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
    if 'identity_source' in data and not isinstance(data['identity_source'],str):raise ValueError('Invalid identity source marker')
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
        if p.get('provider') not in ('comfyui','openai','hermes','mistral'):raise ValueError('Choose ComfyUI, Hermes, Mistral, or an OpenAI-compatible image API')
        if p['provider']=='hermes' and not re.fullmatch('[a-z0-9][a-z0-9_-]{0,55}|',p.get('hermes_provider','')):raise ValueError('Invalid Hermes image provider')
        if not isinstance(p.get('model',''),str) or len(p.get('model',''))>300:raise ValueError('Invalid image model')
        if p['provider'] not in ('hermes','mistral') or (p['provider']=='mistral' and p.get('endpoint')):endpoint(p.get('endpoint','https://api.mistral.ai/v1' if p['provider']=='mistral' else ''))
        if not isinstance(p.get('include_identity',True),bool):raise ValueError('Include identity must be true or false')
        if p.get('category') not in CATEGORIES:raise ValueError('Choose an image category')
        for k,v in p.get('parts',{}).items():
            if k not in PARTS or not isinstance(v,str) or len(v)>20000:raise ValueError('Invalid prompt component')
        for key,label in (('negative','negative prompt'),('modesty_negative','modesty negative prompt')):
            if not isinstance(p.get(key,''),str) or len(p.get(key,''))>20000:raise ValueError('Invalid '+label)
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
      'negative':'low quality, blurry, malformed hands',
      'modesty_negative':MODESTY_DEFAULT,
      'width':832,'height':1216,'steps':18,'cfg':5,'seed':-1,
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

def compile(c,preset_id='',category='portrait',overrides=None,draft=None,intimate=False):
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
    # Default every box from the same split, so the scene box is not handed a joined
    # line that already contains the wardrobe and lighting sitting next to it.
    recorded=portrait.recorded_parts(c)
    parts['identity']=(parts.get('identity') or recorded['identity']) if p.get('include_identity',True) else ''
    for key in ('scene','wardrobe','feeling','lighting','camera'):
        if not parts.get(key):parts[key]=recorded.get(key,'')
    overrides=overrides or {}
    for k in PARTS:
        if k in overrides:parts[k]=str(overrides[k])
    prompt=', '.join(parts.get(k,'').strip().rstrip(',') for k in PARTS if parts.get(k,'').strip())
    if not prompt:raise ValueError('Write a scene or identity before generating')
    # Hosted multimodal providers understand prose and headings better than a
    # diffusion-style comma bag. Keep `prompt` for ComfyUI compatibility, but
    # give GPT/xAI/Mistral and other Hermes providers the same explicit contract
    # so identity, clothing and emotional intent cannot blur into one another.
    labels={'quality':'VISUAL QUALITY','identity':'IDENTITY — KEEP CONSISTENT',
            'wardrobe':'WARDROBE — SHOW EXACTLY','scene':'SCENE AND ACTION',
            'feeling':'EMOTIONAL TONE','lighting':'LIGHTING','camera':'CAMERA AND FRAMING'}
    preamble='Create one coherent image. Treat every section below as a separate visual constraint.'
    # An appearance description often mentions what someone usually wears, which then
    # argues with the wardrobe recorded for this particular moment. Rather than
    # guessing which sentences of someone's own description are about clothes, say
    # plainly which section wins.
    if parts.get('identity','').strip() and parts.get('wardrobe','').strip():
        preamble+=(' Where IDENTITY mentions clothing in general, WARDROBE is what she is'
                   ' wearing now and overrides it.')
    structured=preamble+'\n\n'+\
        '\n\n'.join(f'{labels[k]}:\n{parts[k].strip()}' for k in PARTS if parts.get(k,'').strip())
    # A seed asked for at the call site is the point of asking: "generate with a new
    # random seed" had no effect, because only the PARTS keys were read out of the
    # overrides and a preset that pins a seed then returned the same picture forever.
    seed=overrides.get('seed',p.get('seed',-1))
    try:seed=int(seed)
    except (TypeError,ValueError):seed=-1
    if seed==-1:seed=int.from_bytes(os.urandom(6),'big')
    # The gate is checked here rather than at each caller, because this is the
    # one function every render passes through.
    if intimate:
        allowed,blockers=intimacy_gate(c)
        if not allowed:
            raise ValueError('An intimate render is not available yet: '+
                (' '.join(blockers) if blockers else 'closeness has not reached that point.'))
        if 'negative' not in p.get('mappings',{}) and p['provider']=='comfyui':
            raise ValueError('This workflow has no negative prompt input, so the always-on '
                             'negatives cannot reach it. Map one before rendering intimately.')
    values={**parts,'prompt':prompt,'negative':negative_prompt(p,intimate),'seed':seed,
            **{k:p.get(k,d) for k,d in [('width',832),('height',1216),('steps',18),('cfg',5),('denoise',1.)]}}
    workflow=copy.deepcopy(p.get('workflow',{}))
    for key,(node,field) in p.get('mappings',{}).items():
        if key in values:workflow[str(node)]['inputs'][field]=values[key]
    reference=portrait.portrait_path(c)
    if p.get('requires_reference') and not reference.is_file():raise ValueError('Add a reference portrait before using this image-to-image preset')
    # Name each form for what it is. `prompt` is the comma-joined tag bag a diffusion
    # model wants; `structured` is the labelled-section text hosted models read. They
    # were previously filed as 'structured' and 'prose' respectively -- each under the
    # other's name -- so the viewer showed the two prompts with their labels swapped.
    return {'preset':p,'parts':parts,'prompt':prompt,'structured_prompt':structured,
            'prompts':{'structured':structured,'tags':prompt},
            'negative':values['negative'],'seed':seed,
            'intimate':bool(intimate),'workflow':workflow,
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


def generate(c,preset_id='',category='portrait',overrides=None,report=lambda x:None,allow_nsfw=False,draft=None,intimate=False,purpose='creation'):
    """Render an image, optionally as an intimate one the companion has chosen.

    `intimate` sets the preset's modesty negatives aside and, because such a
    render is adult content on purpose, carries its own `allow_nsfw` — holding
    an image the companion deliberately asked for would only strand it. The
    scanner still rates and records it; the safety floor still applies; and
    `compile` refuses the whole thing unless the closeness gate is open.
    """
    if intimate or getattr(c,'adult_images_allowed',False):allow_nsfw=True
    if purpose not in PURPOSES:raise ValueError('A render is either a creation or a capture')
    try:return _generate(c,preset_id,category,overrides,report,allow_nsfw,draft,intimate,purpose)
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
            replacement=_generate(c,preset_id,category,retry,report,False,draft,False,purpose)
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


# Where a render lands, and why it is a question at all.
#
# Everything used to be written into Creations, and the timeline then copied what
# it needed into its own folder, so every automatic capture existed twice: once as
# something the companion had made, and once as a moment from her day. They are
# not the same thing. A picture she made because you asked her for one -- show me
# your favourite animal at the zoo -- is a creation. A picture from the capture
# routine is a look at what she is doing, which belongs to the timeline and to
# whatever albums you put it in, and has no business in Creations at all.
#
# It also made deleting one a mess: two byte-identical files, grouped into one
# photo, of which a delete removed whichever the grouping happened to name first.
PURPOSES = ('creation', 'capture')
SCRATCH = '.rendering'


def scratch_dir(c):
    """Where a capture is rendered before the timeline takes ownership of it.

    A dot folder, so the library never walks it: an in-flight render is not yet a
    photo, and a discarded one never becomes one.
    """
    return c.data/'image-timeline'/SCRATCH


def discard_scratch(path):
    """Drop a scratch render and everything written beside it."""
    import companion_media_review as review
    path=Path(path)
    if path.parent.name!=SCRATCH:return False
    for victim in (path,review.sidecar(path),path.with_suffix('.json')):
        try:victim.unlink()
        except OSError:pass
    return True


def prune_scratch(c,now=None,max_age_hours=6):
    """Clear renders abandoned by an interrupted capture.

    Nothing here is owed to anyone: a scratch file the timeline never took is a
    render that failed on its way somewhere, and keeping it would be hoarding
    pictures in a folder built precisely so that nobody sees them.
    """
    folder=scratch_dir(c)
    if not folder.is_dir():return 0
    cutoff=(now or time.time())-max_age_hours*3600
    removed=0
    for entry in folder.iterdir():
        try:
            if entry.is_file() and entry.stat().st_mtime<cutoff:
                entry.unlink();removed+=1
        except OSError:pass
    return removed


def _comfy_progress(base,client_id,ident,report):
    """Follow a ComfyUI render step by step, for as long as it will tell us.

    Polling `/history` says nothing at all until the picture exists, so a two
    minute render was reported as one unchanging line -- which reads exactly like
    a job that has hung. ComfyUI publishes step progress on its websocket, so we
    listen where we can and fall back to the queue position, which is plain HTTP
    and always there. Neither is allowed to fail the render: this is commentary,
    not the result.
    """
    try:
        from websockets.sync.client import connect
    except Exception:
        return None
    url=base.replace('https://','wss://',1).replace('http://','ws://',1)+'/ws?clientId='+client_id
    def follow():
        try:
            with connect(url,open_timeout=5,close_timeout=1) as socket:
                while True:
                    try:raw=socket.recv(timeout=60)
                    except Exception:return
                    if isinstance(raw,(bytes,bytearray)):continue
                    try:event=json.loads(raw)
                    except ValueError:continue
                    data=event.get('data') or {}
                    if data.get('prompt_id') not in (None,ident):continue
                    if event.get('type')=='progress':
                        value,total=data.get('value'),data.get('max')
                        report(f'Rendering step {value} of {total}')
                        getattr(report,'percent',lambda *a:None)(value,total)
                    elif event.get('type')=='executing' and data.get('node') is None and data.get('prompt_id')==ident:
                        getattr(report,'percent',lambda *a:None)(1,1)
                        return
        except Exception:
            return
    import threading
    thread=threading.Thread(target=follow,daemon=True)
    thread.start()
    return thread


def _surface_held(c,path):
    """Move a held capture into Creations so Photos can still show it.

    Everything else about a capture is deliberately out of sight, but a picture
    withheld for review is exactly the one a person has to be able to find.
    """
    import companion_media_review as review
    path=Path(path)
    if path.parent.name!=SCRATCH:return path
    folder=c.data/'creations'/'image-studio';folder.mkdir(parents=True,exist_ok=True)
    target=folder/path.name
    try:
        os.replace(path,target)
        for extra in (review.sidecar(path),path.with_suffix('.json')):
            if extra.is_file():os.replace(extra,folder/extra.name)
    except OSError:
        return path
    return target


def _generate(c,preset_id='',category='portrait',overrides=None,report=lambda x:None,allow_nsfw=False,draft=None,intimate=False,purpose='creation'):
    result=compile(c,preset_id,category,overrides,draft,intimate);p=result['preset'];base=endpoint(p['endpoint']) if p['provider']!='hermes' else ''
    provider_prompt=result['prompt'] if p['provider']=='comfyui' else result['structured_prompt']
    report('Generating with '+p['name'])
    if p['provider']=='hermes':
        reply=hermes_bridge(c,'generate',{'prompt':provider_prompt,'hermes_provider':p.get('hermes_provider',''),
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
        client_id=uuid.uuid4().hex
        queued=request_json(base+'/prompt',{'prompt':graph,'client_id':client_id})
        if queued.get('node_errors'):raise ValueError('Workflow validation failed: '+json.dumps(queued['node_errors'])[:3000])
        ident=queued.get('prompt_id')
        if not ident:raise ValueError('ComfyUI did not return a prompt ID')
        _comfy_progress(base,client_id,str(ident),report)
        deadline=time.monotonic()+600;history={};waited=0
        while time.monotonic()<deadline:
            history=request_json(base+'/history/'+str(ident)).get(str(ident),{})
            if history.get('status',{}).get('status_str')=='error':raise ValueError('ComfyUI generation failed: '+json.dumps(history.get('status'))[:2000])
            if history.get('outputs'):break
            # Queue position is the one progress signal that is always available,
            # and it is the answer to the only question worth asking while nothing
            # is happening yet: is it stuck, or is something else in front of it?
            if waited and waited%3==0:
                try:
                    pending=request_json(base+'/queue')
                    ahead=sum(1 for row in pending.get('queue_pending',[]) if row and str(row[1])!=str(ident))
                    if not any(str(row[1])==str(ident) for row in pending.get('queue_running',[]) if row):
                        report(f'Waiting in the ComfyUI queue; {ahead} ahead' if ahead else 'Waiting for ComfyUI to start')
                except Exception:pass
            waited+=1
            time.sleep(1)
        images=[im for output in history.get('outputs',{}).values() for im in output.get('images',[]) if im.get('type')=='output']
        if not images:raise ValueError('No saved image returned; the job may still be queued. Check ComfyUI before retrying.')
        url=base+'/view?'+urllib.parse.urlencode(images[0])
        with urllib.request.urlopen(url,timeout=60) as response:raw=response.read(40_000_001)
    elif p['provider']=='mistral':
        from companion_gateway import _env_values
        keys=_env_values(c.home)
        key=keys.get(p.get('api_key_env','') or 'MISTRAL_API_KEY') or os.environ.get(p.get('api_key_env','') or 'MISTRAL_API_KEY')
        if not key:raise ValueError('No MISTRAL_API_KEY found in .env or environment')
        aspect='landscape' if category=='landscape' else 'portrait'
        aspect_text=f' (aspect ratio {aspect})' if aspect!='1:1' else ''
        conv_model=p.get('model') or 'mistral-small-latest'
        if not conv_model.startswith('mistral-') and not conv_model.startswith('ministral-'):
            conv_model='mistral-small-latest'
        payload={'model':conv_model,
                 'tools':[{'type':'image_generation'}],
                 'inputs':[{'role':'user','content':f"Generate an image using this specification:{aspect_text}\n\n{provider_prompt}"}]}
        headers={'Authorization':'Bearer '+key}
        reply=request_json('https://api.mistral.ai/v1/conversations',payload,headers)
        image_url=None
        for entry in (reply.get('outputs') or []):
            if entry.get('type')=='tool.execution' and entry.get('name')=='image_generation':
                info=entry.get('info') or {}
                res_str=info.get('result') or '{}'
                try:
                    res_json=json.loads(res_str) if isinstance(res_str,str) else res_str
                    image_url=res_json.get('url')
                except Exception:pass
                if image_url:break
        if not image_url:raise ValueError('Mistral Conversations API returned no image')
        with urllib.request.urlopen(image_url,timeout=60) as response:raw=response.read(40_000_001)
    else:
        from companion_gateway import _env_values
        keys=_env_values(c.home)
        key=keys.get(p.get('api_key_env','')) or os.environ.get(p.get('api_key_env',''))
        headers={'Authorization':'Bearer '+key} if key else {}
        reply=request_json(base+'/images/generations',{'model':p.get('model',''),'prompt':provider_prompt,'size':f'{p.get("width",1024)}x{p.get("height",1024)}','n':1},headers)
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
    # A capture is rendered out of sight and handed straight to the timeline; only
    # a creation is something the companion made, and only that belongs in Creations.
    if purpose=='capture':
        prune_scratch(c)
        folder=scratch_dir(c)
    else:
        folder=c.data/'creations'/'image-studio'
    folder.mkdir(parents=True,exist_ok=True)
    ident=uuid.uuid4().hex;path=folder/(ident+ext);path.write_bytes(raw)
    active_type='tags' if p['provider']=='comfyui' else 'structured'
    atomic_write(folder/(ident+'.json'),json.dumps({'prompt':provider_prompt,'prompts':result['prompts'],'active_prompt_type':active_type,'parts':result['parts'],'preset':p['name'],'seed':result['seed']},indent=2))
    import companion_media_review as review
    generation=('ComfyUI' if p['provider']=='comfyui' else 'Mistral' if p['provider']=='mistral' else p.get('hermes_provider') or p['provider'])+' · '+p['name']
    review.write_metadata(path,{'generation':generation,'preset_id':p['id'],'seed':result['seed'],'rendered_with':generation,'active_prompt_type':active_type,'prompts':result['prompts']})
    if review.preferences(c)['review_before_delivery']:
        report('Reviewing the actual image before releasing it for delivery')
        try:decision=review.inspect(c,path,provider_prompt,allow_nsfw)
        except Exception:
            review.write_metadata(path,{'review':{'status':'unavailable'}})
            raise ValueError('Image saved for inspection in Photos, but review is unavailable. Do not send it; check the reviewer in Media preferences.')
        if decision['status']!='passed':
            # Held images are the one case where a capture is kept. The scratch
            # folder is deliberately invisible, so leaving it there would quietly
            # bin the very picture somebody has to look at and decide about.
            path=_surface_held(c,path)
            raise ImageHeld('Image held for inspection in Photos; do not send it. '+str(decision.get('reason','It did not match the intended image.'))[:400],path,review.metadata(path)['rating'])
    meta=review.metadata(path)
    return {'path':str(path),'file':path.name,'provider':generation,'prompt':provider_prompt,
            'prompts':result['prompts'],'active_prompt_type':active_type,'seed':result['seed'],
            'rating':meta['rating'],'blur':review.should_blur(review.preferences(c),meta),'review':meta.get('review')}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--home',type=Path)
    parser.add_argument('command',choices=['generate','prompt']);parser.add_argument('--category',default='portrait',choices=CATEGORIES)
    parser.add_argument('--preset',default='');parser.add_argument('--scene')
    parser.add_argument('--allow-nsfw',action='store_true',help='This image intentionally requests adult content')
    parser.add_argument('--intimate',action='store_true',
        help="Set this workflow's modesty negatives aside. Yours to choose, and only "
             'once closeness has reached Bonded readiness; the always-on negatives still apply.')
    args=parser.parse_args();c=cc.load(args.home)
    kwargs={'allow_nsfw':args.allow_nsfw,'intimate':args.intimate} if args.command=='generate' else {'intimate':args.intimate}
    print(json.dumps((generate if args.command=='generate' else compile)(c,args.preset,args.category,{'scene':args.scene} if args.scene else None,**kwargs),indent=2))
