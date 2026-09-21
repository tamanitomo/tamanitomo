"""Profile-owned media labels, viewing preferences and pre-delivery image review."""
import json
import hashlib
import re
from pathlib import Path
from companion_platform import atomic_write

DEFAULTS={'blur_nsfw_initially':True,'blur_unknown_initially':True,'review_before_delivery':True,'review_provider':'','review_model':''}

def read_json(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size>1_000_000:return {}
    try:
        value=json.loads(path.read_text())
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):return {}

def preferences(c):return {**DEFAULTS,**read_json(c.home/'companion-media-preferences.json')}

def save_preferences(c,data):
    if (c.home/'companion-media-preferences.json').is_symlink():raise ValueError('Linked media preferences are not writable')
    if set(data)-set(DEFAULTS):raise ValueError('Unknown media preference')
    for key,value in data.items():
        if key in ('blur_nsfw_initially','blur_unknown_initially','review_before_delivery'):
            if not isinstance(value,bool):raise ValueError('Use a boolean media preference')
        elif not isinstance(value,str) or len(value)>150 or any(ord(x)<32 for x in value):raise ValueError('Invalid reviewer provider/model')
    value={**preferences(c),**data};atomic_write(c.home/'companion-media-preferences.json',json.dumps(value,indent=2));return value

def sidecar(path):return path.with_name('.'+path.name+'.companion.json')

def metadata(path):
    old=read_json(path.with_suffix('.json'))
    label=old.get('generation') or ('Workflow: '+str(old['preset']) if old.get('preset') else 'Generation source not recorded')
    title={}
    if re.fullmatch('[a-f0-9]{24,40}',path.stem):
        scene=(old.get('parts') or {}).get('scene','')
        title={'title':scene[:120] if isinstance(scene,str) and scene.strip() else 'Generated photo'}
    return {'generation':label,'rating':'unknown',**title,**read_json(sidecar(path))}

def write_metadata(path,data):
    target=sidecar(path)
    if target.is_symlink():raise ValueError('Linked media metadata is not writable')
    atomic_write(target,json.dumps({**metadata(path),**data},indent=2))

def should_blur(prefs,meta):
    rating=meta.get('rating','unknown')
    return (rating=='nsfw' and prefs['blur_nsfw_initially']) or (rating not in ('safe','nsfw') and prefs.get('blur_unknown_initially',True))


def inspect(c,path,prompt,allow_nsfw=False):
    from companion_media import hermes_bridge
    prefs=preferences(c)
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if prefs['review_provider']=='local-nsfw':
        from companion_nsfw import scan
        try:
            result=scan(c,path)
            if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('Image changed during review')
        except Exception:
            write_metadata(path,{'rating':'unknown','review':{'status':'unavailable','provider':'local-nsfw','scope':'nudity_only'}})
            raise ValueError('Local scan unavailable; image stays blurred. No remote reviewer was contacted.')
        rating=result.pop('rating')
        # 'unknown' is the detector's uncertain band (0.2 <= score < 0.5), not a safety verdict.
        # Treating it as permanently unsendable made mildly suggestive images harder to deliver
        # than explicit ones, which score >= 0.5 and are releasable with allow_nsfw. An uncertain
        # image is released only when adult content was intentional; the default still holds it.
        explicit_mode=getattr(c,'explicit',False)
        passed=rating=='safe' or (rating in ('nsfw','unknown') and (allow_nsfw or explicit_mode))
        result.update(status='passed' if passed else 'held',allow_nsfw=allow_nsfw or explicit_mode,sha256=digest)
        write_metadata(path,{'rating':rating,'review':result})
        return result
    result=hermes_bridge(c,'review',{'path':str(path),'prompt':prompt,'provider':prefs['review_provider'],'model':prefs['review_model']})
    if not isinstance(result,dict) or not all(isinstance(result.get(k),bool) for k in ('matches_request','nsfw')):raise ValueError('Image reviewer returned no valid decision')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('Image changed during review')
    explicit_mode=getattr(c,'explicit',False)
    passed=result['matches_request'] and (allow_nsfw or explicit_mode or not result['nsfw'])
    result={k:v for k,v in result.items() if k in ('matches_request','nsfw','reason','provider','model')}
    result.update(status='passed' if passed else 'held',allow_nsfw=allow_nsfw or explicit_mode,sha256=digest)
    write_metadata(path,{'rating':'nsfw' if result['nsfw'] else 'safe','review':result})
    return result


def ensure_delivery(c,path,prompt):
    path=Path(path)
    if not preferences(c)['review_before_delivery']:return
    decision=metadata(path).get('review',{})
    local=preferences(c)['review_provider']=='local-nsfw'
    if decision.get('status')=='passed' and (not local or decision.get('provider')=='local-nsfw') and decision.get('sha256')==hashlib.sha256(path.read_bytes()).hexdigest():return
    # A previously held image never becomes approved merely by entering the queue.
    if decision.get('status')=='held':raise ValueError('Image review held this image; regenerate or inspect it before sending')
    allow_nsfw=getattr(c,'explicit',False)
    decision=inspect(c,path,prompt,allow_nsfw)
    if decision['status']!='passed':raise ValueError('Image review held this image: '+str(decision.get('reason','request mismatch'))[:300])
