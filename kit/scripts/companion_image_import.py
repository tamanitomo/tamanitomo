"""Read a workflow back out of a picture.

Two dialects reach us. A ComfyUI render carries its whole API graph in a PNG
text chunk, which is everything we need. An image from Civitai is usually
Automatic1111's `parameters` block: a prompt, a negative prompt, and a line of
`Key: value` pairs. That is not a graph, so it is poured into our own modular
template instead.

Neither is guaranteed. Civitai strips metadata from some uploads, and a
screenshot has none at all, so this never fails outright — it reports what it
found and hands back a draft to finish by hand.
"""
from __future__ import annotations
import io, json, re


def _text_chunks(raw:bytes)->dict:
    from PIL import Image
    with Image.open(io.BytesIO(raw)) as im:
        im.load()
        info=dict(im.info)
        size=im.size
    return {k:v for k,v in info.items() if isinstance(v,str)},size


def _comfy_graph(chunks:dict):
    """ComfyUI writes the API graph under `prompt`, and the editor graph under
    `workflow`. Only the first is renderable."""
    raw=chunks.get('prompt')
    if not raw:return None
    try:graph=json.loads(raw)
    except ValueError:return None
    if not isinstance(graph,dict) or not graph:return None
    for node in graph.values():
        if not isinstance(node,dict) or 'class_type' not in node:return None
    return graph


A1111_TAIL=re.compile(r'^(?P<key>[A-Za-z][A-Za-z0-9 _+/-]*): (?P<value>"[^"]*"|[^,]*)(?:, |$)')


def _a1111(chunks:dict):
    """Split A1111's block into prompt, negative prompt and settings."""
    text=chunks.get('parameters') or chunks.get('Parameters') or ''
    if not text.strip():return None
    negative='';settings={}
    body=text
    marker=re.search(r'\nNegative prompt:\s*',body)
    if marker:
        positive=body[:marker.start()]
        rest=body[marker.end():]
    else:
        positive=body;rest=''
    # The settings line is the last line that parses as Key: value pairs.
    lines=[l for l in (rest or positive).split('\n') if l.strip()]
    tail=''
    for line in reversed(lines):
        if re.match(r'^[A-Za-z][A-Za-z0-9 _+/-]*: ',line.strip()):tail=line.strip();break
    if tail:
        if marker:negative=rest[:rest.rfind(tail)].strip()
        else:positive=positive[:positive.rfind(tail)].strip()
        remaining=tail
        while remaining:
            m=A1111_TAIL.match(remaining)
            if not m:break
            settings[m.group('key').strip().lower()]=m.group('value').strip().strip('"')
            remaining=remaining[m.end():]
    elif marker:
        negative=rest.strip()
    return {'positive':positive.strip(),'negative':negative.strip(),'settings':settings}


def _number(value,cast=float,default=None):
    try:return cast(str(value).strip())
    except (TypeError,ValueError):return default


def read_image_workflow(raw:bytes,name=''):
    """Everything we can recover, plus a plain account of what was missing."""
    if len(raw)>40_000_000:raise ValueError('That image is too large to read')
    try:chunks,size=_text_chunks(raw)
    except Exception:raise ValueError('That file is not an image this can read')

    found={};notes=[];draft=None
    graph=_comfy_graph(chunks)
    if graph:
        from companion_workflow import modular_template
        draft=modular_template()
        draft['workflow']=graph
        draft['mappings']=_infer_mappings(graph)
        found['source']='ComfyUI graph'
        found['nodes']=len(graph)
        found['loras']=[n['inputs'].get('lora_name') for n in graph.values()
                        if n.get('class_type')=='LoraLoader' and n.get('inputs',{}).get('lora_name')]
        found['checkpoints']=[n['inputs'].get('ckpt_name') for n in graph.values()
                              if n.get('class_type')=='CheckpointLoaderSimple' and n.get('inputs',{}).get('ckpt_name')]
        sampler=next((n for n in graph.values() if n.get('class_type')=='KSampler'),None)
        if sampler:
            for key,field in (('steps','steps'),('cfg','cfg'),('seed','seed')):
                value=sampler.get('inputs',{}).get(field)
                if isinstance(value,(int,float)):draft[key]=value;found[key]=value
        latent=next((n for n in graph.values() if n.get('class_type')=='EmptyLatentImage'),None)
        if latent:
            for key in ('width','height'):
                value=latent.get('inputs',{}).get(key)
                if isinstance(value,int):draft[key]=value;found[key]=value
        if not draft['mappings'].get('prompt') and not draft['mappings'].get('quality'):
            notes.append('The prompt node could not be identified, so the text boxes are not wired yet.')
    else:
        parsed=_a1111(chunks)
        if parsed:
            from companion_workflow import modular_template
            draft=modular_template()
            found['source']='Civitai / Automatic1111 parameters'
            s=parsed['settings']
            draft['parts']={**(draft.get('parts') or {}),'quality':parsed['positive']}
            draft['negative']=parsed['negative']
            found['prompt_chars']=len(parsed['positive'])
            steps=_number(s.get('steps'),int);cfg=_number(s.get('cfg scale'),float);seed=_number(s.get('seed'),int)
            if steps:draft['steps']=steps;found['steps']=steps
            if cfg is not None:draft['cfg']=cfg;found['cfg']=cfg
            if seed is not None:draft['seed']=seed;found['seed']=seed
            if s.get('size') and 'x' in s['size']:
                w,_,h=s['size'].partition('x')
                w=_number(w,int);h=_number(h,int)
                if w and h:draft['width'],draft['height']=w,h;found['width'],found['height']=w,h
            if s.get('model'):found['checkpoints']=[s['model']]
            hashes=s.get('lora hashes') or ''
            names=[part.split(':')[0].strip() for part in hashes.split(',') if part.strip()]
            if names:found['loras']=names
            notes.append('These are Automatic1111 settings, not a ComfyUI graph. '
                         'The prompt and numbers came across; the model and LoRAs are named but must be '
                         'picked from what this ComfyUI has.')
        else:
            notes.append('This image carries no generation data. Civitai strips it from some uploads, '
                         'and screenshots never have it.')

    if draft is None:
        from companion_workflow import modular_template
        draft=modular_template()
        found['source']='nothing recoverable'
    draft['name']=(name or 'Imported workflow').rsplit('.',1)[0][:80]
    draft['category']=''
    draft['incomplete']=not _is_renderable(draft,found)
    if draft['incomplete']:
        notes.append('Saved as a draft. It cannot be assigned to a lane until a checkpoint is chosen '
                     'and the prompt boxes are wired.')
    if size:found['image_size']=f'{size[0]}x{size[1]}'
    return {'preset':draft,'found':found,'notes':notes}


def _infer_mappings(graph):
    """Point the prompt, size and sampler controls at the nodes that own them."""
    mappings={}
    sampler=next((i for i,n in graph.items() if n.get('class_type')=='KSampler'),None)
    latent=next((i for i,n in graph.items() if n.get('class_type')=='EmptyLatentImage'),None)
    encoders=[i for i,n in graph.items() if n.get('class_type')=='CLIPTextEncode']
    if sampler:
        for key in ('seed','steps','cfg'):mappings[key]=[sampler,key]
        # The sampler names its own conditioning, so positive and negative are
        # not guesses from ordering.
        for field,key in (('positive','prompt'),('negative','negative')):
            ref=graph[sampler].get('inputs',{}).get(field)
            if isinstance(ref,list) and str(ref[0]) in graph and graph[str(ref[0])].get('class_type')=='CLIPTextEncode':
                mappings[key]=[str(ref[0]),'text']
    if latent:
        mappings['width']=[latent,'width'];mappings['height']=[latent,'height']
    if 'prompt' not in mappings and encoders:mappings['prompt']=[encoders[0],'text']
    return mappings


def _is_renderable(draft,found):
    if found.get('source')!='ComfyUI graph':return False
    graph=draft.get('workflow') or {}
    has_model=any(n.get('class_type')=='CheckpointLoaderSimple' and n.get('inputs',{}).get('ckpt_name')
                  for n in graph.values())
    wired=bool((draft.get('mappings') or {}).get('prompt'))
    return bool(has_model and wired)


# --------------------------------------------------------------- from a link

CIVITAI_IMAGE_URL=re.compile(r'^https?://(?:www\.)?civitai\.(?:com|red)/images/(\d+)',re.I)


def _civitai_meta_from_page(html:str):
    """Civitai's own page carries the generation data in its Next.js payload.

    The public API returns an empty `meta` for anonymous callers, so the page is
    the only route that needs no key. It is a rendering detail of someone else's
    site, so this fails quietly and lets the caller fall back.
    """
    match=re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',html,re.S)
    if not match:return None
    try:payload=json.loads(match.group(1))
    except ValueError:return None
    best=None
    def walk(node):
        nonlocal best
        if isinstance(node,dict):
            if node.get('prompt') and ('steps' in node or 'cfgScale' in node):
                if best is None or len(str(node))>len(str(best)):best=node
            for value in node.values():walk(value)
        elif isinstance(node,list):
            for value in node:walk(value)
    walk(payload)
    return best


RESOURCE_KINDS={'checkpoint':'checkpoint','lora':'lora','lycoris':'lycoris','locon':'locon',
               'embed':'embedding','embedding':'embedding','vae':'vae','textualinversion':'embedding'}


def _json_get(url):
    import urllib.request
    request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
    with urllib.request.urlopen(request,timeout=20) as response:
        return json.loads(response.read(2_000_000).decode('utf-8','replace'))


def resolve_resources(resources,fetch_json=None):
    """Turn Civitai's version ids into files, base models and download links.

    This endpoint answers without an API key. A key is still worth having for
    gated models and for a higher rate limit, so a failure here is reported per
    resource rather than sinking the whole import.
    """
    fetch_json=fetch_json or _json_get
    out=[]
    for entry in resources or []:
        if not isinstance(entry,dict):continue
        kind=RESOURCE_KINDS.get(str(entry.get('type','')).lower(),str(entry.get('type','')).lower())
        version=entry.get('modelVersionId') or entry.get('modelVersionID')
        row={'kind':kind,'weight':entry.get('weight'),'version_id':version,
             'name':'','file':'','base_model':'','download':'','size_kb':None,'error':''}
        if version:
            try:
                data=fetch_json(f'https://civitai.com/api/v1/model-versions/{int(version)}')
                model=data.get('model') or {}
                row['name']=' \u00b7 '.join(x for x in (model.get('name'),data.get('name')) if x)
                row['base_model']=data.get('baseModel') or ''
                files=data.get('files') or []
                primary=next((f for f in files if f.get('primary')),files[0] if files else {})
                row['file']=primary.get('name') or ''
                row['download']=primary.get('downloadUrl') or ''
                row['size_kb']=primary.get('sizeKB')
            except Exception:
                row['error']='Could not look this one up on Civitai.'
        out.append(row)
    return out


def read_image_url(url:str,fetch=None,fetch_json=None):
    """Import from a Civitai image page. civitai.red serves the same images."""
    url=(url or '').strip()
    match=CIVITAI_IMAGE_URL.match(url)
    if not match:
        raise ValueError('Paste the address of a Civitai image page, like '
                         'https://civitai.com/images/12345678')
    if fetch is None:
        import urllib.request
        def fetch(target):
            request=urllib.request.Request(target,headers={'User-Agent':'Mozilla/5.0'})
            with urllib.request.urlopen(request,timeout=25) as response:
                return response.read(4_000_000).decode('utf-8','replace')
    try:html=fetch(url)
    except Exception:
        raise ValueError('Could not reach that page. Check the link, or download the image and import the file.')
    meta=_civitai_meta_from_page(html)
    if not meta:
        raise ValueError('That page did not include its generation settings. '
                         'Some uploads have them stripped; downloading the image and importing '
                         'the file sometimes still works.')

    from companion_workflow import modular_template
    draft=modular_template()
    found={'source':'Civitai image page','image_id':match.group(1)}
    notes=[]
    draft['parts']={**(draft.get('parts') or {}),'quality':str(meta.get('prompt') or '')}
    draft['negative']=str(meta.get('negativePrompt') or '')
    found['prompt_chars']=len(draft['parts']['quality'])
    steps=_number(meta.get('steps'),int);cfg=_number(meta.get('cfgScale'),float);seed=_number(meta.get('seed'),int)
    if steps:draft['steps']=steps;found['steps']=steps
    if cfg is not None:draft['cfg']=cfg;found['cfg']=cfg
    if seed is not None:draft['seed']=seed;found['seed']=seed
    size=str(meta.get('Size') or '')
    if 'x' in size:
        w,_,h=size.partition('x')
        w=_number(w,int);h=_number(h,int)
        if w and h:draft['width'],draft['height']=w,h;found['width'],found['height']=w,h
    if meta.get('sampler'):found['sampler']=meta['sampler']
    model=meta.get('Model') or meta.get('model')
    if model:found['checkpoints']=[str(model)]
    clip_skip=_number(meta.get('clipSkip'),int)
    if clip_skip:found['clip_skip']=clip_skip
    # Civitai names its resources by version id, not by filename. Resolving them
    # gives the real file, the base model, and somewhere to download it from.
    found['resources']=resolve_resources(meta.get('civitaiResources') or meta.get('resources') or [],fetch_json)
    families={r['base_model'] for r in found['resources'] if r.get('base_model')}
    if families:found['base_model']=sorted(families)[0]
    checkpoint=next((r for r in found['resources'] if r['kind']=='checkpoint'),None)
    if checkpoint and checkpoint.get('file'):found['checkpoints']=[checkpoint['file']]
    loras=[r['file'] or r['name'] for r in found['resources'] if r['kind'] in ('lora','lycoris','locon')]
    if loras:found['loras']=loras
    notes.append('Read from the page, not from a file: this is a prompt and its settings, not a '
                 'ComfyUI graph. Pick the checkpoint from what this ComfyUI has before it can serve a lane.')
    draft['name']='Civitai image '+match.group(1)
    draft['category']=''
    draft['incomplete']=True
    return {'preset':draft,'found':found,'notes':notes}


# ------------------------------------------------------- what a family wants

"""Settings that suit each base model, so the fields can say what is usual.

These are the community's working consensus rather than anything published by
the model authors, and consensus moves. They are suggestions shown beside the
field, never applied on their own.
"""
MODEL_FAMILIES=[
    ('flux',    'Flux',        {'steps':(20,28),'cfg':(1.0,3.5),'clip_skip':(1,1),'size':(1024,1024)}),
    ('illustri','Illustrious', {'steps':(24,30),'cfg':(4.5,7.0),'clip_skip':(2,2),'size':(832,1216)}),
    ('noob',    'NoobAI',      {'steps':(24,30),'cfg':(4.0,6.0),'clip_skip':(2,2),'size':(832,1216)}),
    ('pony',    'Pony',        {'steps':(22,30),'cfg':(6.0,8.0),'clip_skip':(2,2),'size':(832,1216)}),
    ('animagine','Animagine',  {'steps':(24,30),'cfg':(5.0,7.0),'clip_skip':(2,2),'size':(832,1216)}),
    ('sd15',    'SD 1.5',      {'steps':(20,30),'cfg':(6.0,9.0),'clip_skip':(1,2),'size':(512,768)}),
    ('xl',      'SDXL',        {'steps':(25,35),'cfg':(5.0,8.0),'clip_skip':(1,2),'size':(832,1216)}),
]


def family_of(name:str):
    """The family a checkpoint belongs to, guessed from its filename.

    A guess, and labelled as one wherever it is shown: a checkpoint can be
    renamed to anything, and merges often are.
    """
    lowered=(name or '').lower()
    for token,label,_ in MODEL_FAMILIES:
        if token in lowered:return label
    return ''


def recommendations(name:str):
    label=family_of(name)
    for _,candidate,values in MODEL_FAMILIES:
        if candidate==label:return {'family':label,**values}
    return {'family':''}
