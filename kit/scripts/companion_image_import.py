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
