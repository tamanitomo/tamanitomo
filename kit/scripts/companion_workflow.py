"""Portable structured Comfy recipes; no companion identity or credentials embedded."""
from __future__ import annotations
import copy

PROMPT_NODES={'quality':'101','identity':'102','wardrobe':'103','scene':'104','lighting':'105','camera':'106'}


def modular_template():
    """A standard-node SDXL scaffold with stable semantic slots."""
    graph={
      '1':{'class_type':'CheckpointLoaderSimple','inputs':{'ckpt_name':'CHOOSE_YOUR_CHECKPOINT.safetensors'}},
      '8':{'class_type':'CLIPSetLastLayer','inputs':{'clip':['1',1],'stop_at_clip_layer':-2}},
      '201':{'class_type':'CLIPTextEncode','inputs':{'clip':['8',0],'text':''}},
      '301':{'class_type':'EmptyLatentImage','inputs':{'width':832,'height':1216,'batch_size':1}},
      '302':{'class_type':'KSampler','inputs':{'model':['1',0],'positive':['115',0],'negative':['201',0],'latent_image':['301',0],'seed':0,'steps':22,'cfg':5.,'sampler_name':'euler_ancestral','scheduler':'normal','denoise':1.}},
      '303':{'class_type':'VAEDecode','inputs':{'samples':['302',0],'vae':['1',2]}},
      '304':{'class_type':'SaveImage','inputs':{'images':['303',0],'filename_prefix':'Companion'}}}
    for node in PROMPT_NODES.values():graph[node]={'class_type':'CLIPTextEncode','inputs':{'clip':['8',0],'text':''}}
    for index,node in enumerate(['102','103','104','105','106']):
        graph[str(111+index)]={'class_type':'ConditioningConcat','inputs':{'conditioning_to':['101' if index==0 else str(110+index),0],'conditioning_from':[node,0]}}
    return {'id':'modular-sdxl','name':'Structured SDXL workflow','category':'portrait','provider':'comfyui',
      'endpoint':'http://127.0.0.1:8188','family':'sdxl','parts':{'quality':'high quality, detailed'},
      'negative':'low quality, blurry, malformed hands','width':832,'height':1216,'steps':22,'cfg':5,'seed':-1,
      'workflow':graph,'mappings':{**{k:[v,'text'] for k,v in PROMPT_NODES.items()},'negative':['201','text'],
        'width':['301','width'],'height':['301','height'],'seed':['302','seed'],'steps':['302','steps'],'cfg':['302','cfg']}}


def image_to_image(preset,denoise=.35):
    """Derive a separate image-to-image recipe, retaining its model and conditioning."""
    if preset.get('provider')!='comfyui':raise ValueError('Choose a ComfyUI recipe')
    if isinstance(denoise,bool) or not isinstance(denoise,(int,float)) or not 0<denoise<=1:raise ValueError('Denoise must be above 0 and at most 1')
    p=copy.deepcopy(preset);graph=p.get('workflow',{})
    samplers=[(k,n) for k,n in graph.items() if n.get('class_type')=='KSampler']
    decoders=[n for n in graph.values() if n.get('class_type')=='VAEDecode']
    if len(samplers)!=1 or len(decoders)!=1:raise ValueError('Automatic conversion requires one KSampler and one VAEDecode; use an architecture-specific template for multi-stage workflows')
    sid,sampler=samplers[0];latent=sampler.get('inputs',{}).get('latent_image')
    if not isinstance(latent,list) or graph.get(str(latent[0]),{}).get('class_type') not in ('EmptyLatentImage','EmptySD3LatentImage'):
        raise ValueError('This recipe does not begin with a plain empty latent')
    vae=decoders[0]['inputs'].get('vae')
    if not isinstance(vae,list):raise ValueError('The decoder must have a connected VAE')
    next_id=max([int(k) for k in graph if str(k).isdigit()]+[400])+1
    load,scale,encode=map(str,range(next_id,next_id+3))
    graph[load]={'class_type':'LoadImage','inputs':{'image':'reference-portrait.png'}}
    graph[scale]={'class_type':'ImageScale','inputs':{'image':[load,0],'upscale_method':'lanczos','width':p.get('width',832),'height':p.get('height',1216),'crop':'center'}}
    graph[encode]={'class_type':'VAEEncode','inputs':{'pixels':[scale,0],'vae':copy.deepcopy(vae)}}
    sampler['inputs'].update(latent_image=[encode,0],denoise=float(denoise))
    p.setdefault('mappings',{}).update(reference_image=[load,'image'],width=[scale,'width'],height=[scale,'height'],denoise=[sid,'denoise'])
    p.update(id=p['id'][:52]+'-img2img',name=(p['name'][:75]+' · Image to image'),denoise=float(denoise),requires_reference=True)
    return p


def create_recipe(spec):
    """Build known architectures from explicit slots; never infer family from a filename."""
    import math
    import uuid
    from pathlib import PurePosixPath
    family=spec.get('family','sdxl')
    if family not in ('sdxl','sd15','zimage','krea2'):raise ValueError('Choose a supported architecture')
    def weight(item,label):
        if not isinstance(item,dict):raise ValueError('Choose '+label)
        name=item.get('filename','')
        if not isinstance(name,str) or not name or len(name)>300 or name.startswith('/') or '\\' in name or '..' in PurePosixPath(name).parts or '\0' in name:raise ValueError('Choose an installed '+label+' filename')
        tagged=item.get('family','unknown')
        if tagged not in ('unknown',family):raise ValueError(label+' belongs to '+str(tagged)+', not '+family)
        if tagged=='unknown' and not item.get('confirm_family'):raise ValueError('Confirm the model card family for '+label+'; filename alone is not compatibility evidence')
        return name
    model=weight(spec.get('model'),'model');p=modular_template();p['family']=family;g=p['workflow']
    p['id']='workflow-'+uuid.uuid4().hex[:12]
    name=spec.get('name','Structured workflow')
    if not isinstance(name,str) or not 1<=len(name.strip())<=100:raise ValueError('Name the workflow')
    p['name']=name.strip();p['parts']['quality']=spec.get('quality','high quality, detailed');model_ref=['1',0];clip_ref=['8',0]
    if family in ('sdxl','sd15'):
        if not model.endswith('.safetensors'):raise ValueError('Checkpoint templates require safetensors weights')
        g['1']['inputs']['ckpt_name']=model
        skip=spec.get('clip_skip',-2)
        if isinstance(skip,bool) or not isinstance(skip,int) or not -24<=skip<=-1:raise ValueError('CLIP last layer must be -24 to -1')
        g['8']['inputs']['stop_at_clip_layer']=skip
        if family=='sd15':p.update(width=512,height=768,cfg=7.)
    else:
        encoder=weight(spec.get('clip'),'text encoder');vae=weight(spec.get('vae'),'VAE')
        g['1']={'class_type':'UnetLoaderGGUF','inputs':{'unet_name':model}} if model.endswith('.gguf') else {'class_type':'UNETLoader','inputs':{'unet_name':model,'weight_dtype':'default'}}
        del g['8'];g['9']={'class_type':'CLIPLoader','inputs':{'clip_name':encoder,'type':'krea2' if family=='krea2' else 'lumina2','device':'default'}}
        g['10']={'class_type':'VAELoader','inputs':{'vae_name':vae}}
        g['307']={'class_type':'ModelSamplingAuraFlow','inputs':{'model':model_ref,'shift':3.}}
        model_ref=['307',0];clip_ref=['9',0]
        g['301']['class_type']='EmptySD3LatentImage';g['303']['inputs']['vae']=['10',0]
        p.update(width=1024,height=1024,steps=9,cfg=1.)
        g['302']['inputs'].update(sampler_name='dpmpp_2m_sde',scheduler='beta')
    loras=spec.get('loras',[])
    if not isinstance(loras,list) or len(loras)>24:raise ValueError('At most 24 LoRAs')
    for index,item in enumerate(loras):
        if not isinstance(item,dict) or not isinstance(item.get('enabled',True),bool):raise ValueError('Invalid LoRA slot')
        if not item.get('enabled',True):continue
        filename=weight(item,'LoRA')
        if not filename.endswith('.safetensors'):raise ValueError('Use safetensors LoRA weights')
        strengths={key:item.get(key,1.) for key in ('strength_model','strength_clip')}
        if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not -5<=v<=5 for v in strengths.values()):raise ValueError('LoRA strengths must be between -5 and 5')
        node=str(500+index);g[node]={'class_type':'LoraLoader','inputs':{'model':model_ref,'clip':clip_ref,'lora_name':filename,**strengths}}
        model_ref=[node,0];clip_ref=[node,1]
    for node in [*PROMPT_NODES.values(),'201']:g[node]['inputs']['clip']=copy.deepcopy(clip_ref)
    g['302']['inputs'].update(model=model_ref,steps=p['steps'],cfg=p['cfg'])
    g['301']['inputs'].update(width=p['width'],height=p['height'])
    p['builder']=copy.deepcopy(spec)
    return p
