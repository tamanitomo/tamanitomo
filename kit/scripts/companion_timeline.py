#!/usr/bin/env python3
"""Optional rolling image timeline. Generation uses Hermes's configured provider.

This helper claims a current scene, imports the provider result, renders a local
contact sheet, and expires only its own managed files. It never sends a message.

Retention is a storage budget rather than a calendar. Images are the only thing
in the kit that can actually fill a disk, and "thirty days" is the wrong unit
for a person deciding how much of their disk a companion may have. Over budget,
the oldest captures go — except anything copied into an album, which is what
albums are for. The copy is a copy: favouriting never moves the original out of
the timeline, so the day it belonged to still reads correctly.
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, html, io, json, os, pathlib, re, sys, tempfile
import urllib.request
import companion_config as cc
from companion_platform import atomic_write, file_lock
from companion_presence import current

# Only used when no budget is set at all; a calendar is a poor way to bound a
# folder whose file sizes nobody controls.
DAYS=30
MAX_BYTES=32*1024*1024
ALBUM_NAME=re.compile(r'^[A-Za-z0-9][A-Za-z0-9 _-]{0,60}$')
ID=re.compile(r'^[a-f0-9]{24}$')
IMAGE=re.compile(r'^[a-f0-9]{24}\.(png|jpg|webp)$')

def now_utc():return dt.datetime.now(dt.timezone.utc)
def root(c):return c.data/'image-timeline'

def timestamp(value):
    stamp=dt.datetime.fromisoformat(value)
    if stamp.tzinfo is None:raise ValueError('Timeline timestamps require a timezone')
    return stamp.astimezone(dt.timezone.utc)


def records(c):
    for path in sorted((root(c)/'captures').glob('*.json')):
        if not ID.fullmatch(path.stem) or path.is_symlink():continue
        row=json.loads(path.read_text(encoding='utf-8'))
        if row.get('id')!=path.stem:raise ValueError('Capture id mismatch')
        yield path,row


def render_gallery(c):
    from companion_media_review import metadata,preferences,should_blur
    prefs=preferences(c)
    cards=[]
    for _,row in sorted(records(c),key=lambda item:item[1]['created_at'],reverse=True):
        filename=row.get('filename','')
        if row.get('status')!='saved' or not IMAGE.fullmatch(filename):continue
        scene=row['scene'];state=scene['state'];esc=html.escape
        caption=' · '.join([state['activity'],state['location'],', '.join(item['description'] for item in state['outfit'])])
        meta=metadata(root(c)/'images'/filename)
        conceal=' style="filter:blur(28px)" title="Sensitive or unreviewed image; click to reveal"' if should_blur(prefs,meta) else ''
        cards.append(f'<article><a href="images/{filename}"><img{conceal} loading="lazy" src="images/{filename}" alt="{esc(caption,quote=True)}"></a><a download href="images/{filename}">Save favorite</a><time>{esc(scene["recorded_at"])}</time><p>{esc(caption)}</p><p>{esc(str(meta.get("generation") or row.get("provider") or "Source not recorded"))}</p></article>')
    document='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Image timeline</title><style>body{margin:0;background:#101820;color:#edf3f7;font:16px system-ui;padding:32px}h1{margin-bottom:8px}header{max-width:850px;margin-bottom:32px}header p{color:#b4c5d0;line-height:1.6}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:20px}article{background:#1c2933;border-radius:12px;overflow:hidden}img{width:100%;aspect-ratio:4/5;object-fit:contain;background:#0b1117}time,p{display:block;margin:14px}time{font-size:13px;color:#88c9de}p{line-height:1.5}</style>
<header><h1>'''+html.escape(c.agent)+''' · Image timeline</h1><p>A glimpse of each recorded moment. Images are generated from the companion’s continuing authored life. This folder is bounded by a storage budget, and the oldest go first when it is full. Anything copied into an album is kept whatever happens here. An absent image means no successful capture, not an uneventful day.</p></header><main class="grid">'''+(''.join(cards) or '<p>No images yet. The first capture needs a current state and a working image provider.</p>')+'</main></html>'
    atomic_write(root(c)/'index.html',document)


def _size(c,row):
    name=row.get('filename','')
    if not name:return 0
    try:return (root(c)/'images'/name).stat().st_size
    except OSError:return 0

def _drop(c,path,row):
    name=row.get('filename','')
    if name:
        if not IMAGE.fullmatch(name) or not name.startswith(row['id']+'.'):
            raise ValueError('Unsafe managed image name')
        # Unlinking a symlink removes only the link, never its target.
        image=root(c)/'images'/name
        image.unlink(missing_ok=True)
        from companion_media_review import sidecar
        sidecar(image).unlink(missing_ok=True)
    path.unlink()

def _prune(c,now):
    rows=sorted(records(c),key=lambda item:item[1]['created_at'])
    removed=0
    # Validate every managed name on the way past, not only the ones about to be
    # removed. Corrupt metadata that is currently inside the budget is still
    # corrupt metadata, and finding it later is finding it too late.
    for _,row in rows:
        name=row.get('filename','')
        if name and (not IMAGE.fullmatch(name) or not name.startswith(row['id']+'.')):
            raise ValueError('Unsafe managed image name')
    # A pending capture that never landed is a failure, not a file to keep
    # waiting for.
    for path,row in rows:
        if row.get('status')=='pending' and now-timestamp(row['created_at'])>dt.timedelta(minutes=15):
            row.update(status='failed',error='Capture timed out before a successful save')
            atomic_write(path,json.dumps(row,ensure_ascii=False,indent=2))
    budget=int(float(getattr(c,'timeline_budget_gb',0) or 0)*1_000_000_000)
    total=sum(_size(c,row) for _,row in rows)
    freed=0
    if budget:
        for path,row in rows:
            if total<=budget:break
            size=_size(c,row)
            _drop(c,path,row);removed+=1;total-=size;freed+=size
    else:
        # No budget set: fall back to the old calendar so the folder is still
        # bounded by something.
        cutoff=now-dt.timedelta(days=DAYS)
        for path,row in rows:
            if timestamp(row['created_at'])>cutoff:continue
            freed+=_size(c,row);_drop(c,path,row);removed+=1
    for temp in (root(c)/'images').glob('.capture-*'):
        if temp.is_file() and dt.datetime.fromtimestamp(temp.lstat().st_mtime,dt.timezone.utc)<=now-dt.timedelta(days=1):
            temp.unlink()
    render_gallery(c)
    return {'removed':removed,'freed_bytes':freed,'bytes_used':total,
            'budget_bytes':budget or None,'retention_days':None if budget else DAYS,
            'gallery':str(root(c)/'index.html')}


# ---- albums ---------------------------------------------------------------
def albums_root(c):return c.data/'albums'

def albums(c):
    folder=albums_root(c)
    if not folder.is_dir():return []
    out=[]
    for path in sorted(folder.iterdir()):
        if not path.is_dir() or path.is_symlink():continue
        files=[f for f in path.iterdir() if f.is_file() and not f.name.startswith('.')]
        out.append({'name':path.name,'count':len(files),
                    'bytes':sum(f.stat().st_size for f in files),'path':str(path)})
    return out

def favorite(c,ident,album='Favorites'):
    """Copy a capture into an album. The original stays where it is.

    Moving it would take the image out of the day it belongs to, and the
    timeline would then be quietly wrong about that afternoon.
    """
    if not ALBUM_NAME.fullmatch(album):
        raise ValueError('album names are letters, digits, spaces, hyphens and underscores')
    path=capture_path(c,ident)
    row=json.loads(path.read_text(encoding='utf-8'))
    if row.get('status')!='saved':raise ValueError('only a saved capture can be kept')
    name=row['filename']
    if not IMAGE.fullmatch(name):raise ValueError('Unsafe managed image name')
    source=root(c)/'images'/name
    if not source.is_file():raise ValueError('the image is already gone')
    folder=albums_root(c)/album;folder.mkdir(parents=True,exist_ok=True)
    target=folder/name
    if not target.exists():
        import shutil as _shutil
        _shutil.copy2(source,target)
        scene=row.get('scene',{}).get('state',{})
        caption=(f"{row['scene'].get('recorded_at','')} — {scene.get('activity','')} at "
                 f"{scene.get('location','')}\n")
        (folder/(name+'.txt')).write_text(caption,encoding='utf-8')
    from companion_media_review import metadata,write_metadata
    write_metadata(target,metadata(source))
    return {'album':album,'file':str(target),'kept':True,
            'note':'Copied, not moved. The timeline still holds the original until retention takes it.'}

def add_to_album(c,source,album='Favorites'):
    """Put a file the human chose into an album, timeline or not."""
    if not ALBUM_NAME.fullmatch(album):
        raise ValueError('album names are letters, digits, spaces, hyphens and underscores')
    data,ext=load_image(str(source))
    digest=hashlib.sha256(data).hexdigest()[:24]
    folder=albums_root(c)/album;folder.mkdir(parents=True,exist_ok=True)
    target=folder/f'{digest}.{ext}'
    if not target.exists():target.write_bytes(data)
    from companion_media_review import metadata,write_metadata
    if pathlib.Path(str(source)).is_file():write_metadata(target,metadata(pathlib.Path(source)))
    return {'album':album,'file':str(target),'bytes':len(data)}


def prune(c,now=None):
    if root(c).is_symlink() or (root(c)/'images').is_symlink() or (root(c)/'captures').is_symlink():raise ValueError('Timeline directories must not be symlinks')
    if not root(c).exists():return {'removed':0,'retention_days':DAYS}
    with file_lock(root(c)/'.lock'):return _prune(c,now or now_utc())


def prepare(c,now=None):
    now=now or now_utc();prune(c,now)
    if not c.image_timeline:return {'ready':False,'reason':'Image timeline is off'}
    scene=current(c)
    now=now.astimezone(dt.timezone.utc)
    slot=now.replace(minute=now.minute//15*15,second=0,microsecond=0)
    if not scene or not scene['state'].get('confirmed',True) or not slot<=timestamp(scene['recorded_at'])<=now:
        return {'ready':False,'reason':'No confirmed state in this 15-minute interval; skip rather than invent a scene'}
    from companion_render import load_styles
    style=load_styles().get(c.image_style)
    if not style or c.image_style in ('none','unset'):return {'ready':False,'reason':'Choose a timeline image style first'}
    ident=hashlib.sha256(slot.isoformat().encode()).hexdigest()[:24]
    path=root(c)/'captures'/(ident+'.json')
    with file_lock(root(c)/'.lock'):
        if path.exists():return {'ready':False,'reason':'This interval has already been claimed','capture':json.loads(path.read_text(encoding='utf-8'))}
        from companion_day import visual_key
        saved=[row for _,row in records(c) if row.get('status')=='saved']
        latest=max(saved,key=lambda row:row['created_at'],default=None)
        if (latest and latest.get('image_style')==c.image_style
                and visual_key(latest['scene']['state'])==visual_key(scene['state'])):
            return {'ready':False,'reason':'The current visible moment already has an image'}
        row={'id':ident,'created_at':now.isoformat(),'status':'pending','scene':scene,'image_style':c.image_style,'image_style_guidance':style['soul']}
        atomic_write(path,json.dumps(row,ensure_ascii=False,indent=2))
    return {'ready':True,'capture_id':ident,'scene':scene,'image_style_guidance':style['soul'],'instruction':'Generate one image with the configured Hermes image provider, matching this saved scene and the SOUL visual identity. Import the actual returned local file or HTTPS URL with save. Do not send it to the user.'}


def capture_path(c,ident):
    if not ID.fullmatch(ident):raise ValueError('Invalid capture id')
    return root(c)/'captures'/(ident+'.json')


def load_image(source):
    if source.startswith('https://'):
        with urllib.request.urlopen(source,timeout=30) as response:
            if not response.geturl().startswith('https://'):raise ValueError('Image URL redirected away from HTTPS')
            data=response.read(MAX_BYTES+1)
    else:
        path=pathlib.Path(source)
        if not path.is_file() or path.stat().st_size>MAX_BYTES:raise ValueError('Source must be an image file under 32 MB')
        data=path.read_bytes()
    if len(data)>MAX_BYTES:raise ValueError('Image exceeds 32 MB')
    from PIL import Image
    with Image.open(io.BytesIO(data)) as image:
        ext={'PNG':'png','JPEG':'jpg','WEBP':'webp'}.get(image.format)
        if ext is None:raise ValueError('Use a PNG, JPEG or WebP image')
        image.verify()
    return data,ext


def save(c,ident,source,provider,now=None):
    now=now or now_utc();prune(c,now)
    if not c.image_timeline:raise ValueError('Image timeline is off')
    path=capture_path(c,ident)
    with file_lock(root(c)/'.lock'):
        row=json.loads(path.read_text(encoding='utf-8'))
        if row['status']=='saved':return row
        if row['status']!='pending':raise ValueError('Capture is not pending')
        if now-timestamp(row['created_at'])>dt.timedelta(minutes=15):raise ValueError('Capture expired; do not label a delayed image as current')
        if not isinstance(provider,str) or not provider.strip() or len(provider)>200:raise ValueError('Record the actual provider/model name')
        data,ext=load_image(source);name=ident+'.'+ext
        # Register the intended managed name first so an interrupted copy remains cleanable.
        row['filename']=name;atomic_write(path,json.dumps(row,ensure_ascii=False,indent=2))
        folder=root(c)/'images';folder.mkdir(parents=True,exist_ok=True)
        fd,temp=tempfile.mkstemp(prefix='.capture-',dir=folder)
        try:
            with os.fdopen(fd,'wb') as out:out.write(data);out.flush();os.fsync(out.fileno())
            os.replace(temp,folder/name)
        finally:
            if os.path.exists(temp):os.unlink(temp)
        from companion_media_review import metadata,write_metadata
        meta=metadata(pathlib.Path(source)) if not str(source).startswith(('http:','https:')) and pathlib.Path(source).is_file() else {}
        if meta.get('generation')=='Generation source not recorded':meta.pop('generation')
        write_metadata(folder/name,{'generation':provider,**meta})
        from companion_media_review import preferences,inspect
        if preferences(c)['review_provider']=='local-nsfw':
            decision=meta.get('review',{})
            if decision.get('provider')!='local-nsfw' or decision.get('sha256')!=hashlib.sha256(data).hexdigest():
                try:inspect(c,folder/name,'Local timeline capture')
                except ValueError:pass  # Keep the local capture; unavailable scans remain unknown and blurred.
        row.update(status='saved',saved_at=now.isoformat(),provider=provider,sha256=hashlib.sha256(data).hexdigest())
        atomic_write(path,json.dumps(row,ensure_ascii=False,indent=2));render_gallery(c)
    return row


def fail(c,ident,reason):
    path=capture_path(c,ident)
    with file_lock(root(c)/'.lock'):
        row=json.loads(path.read_text(encoding='utf-8'))
        if row['status']=='saved':raise ValueError('A saved capture cannot be marked failed')
        row.update(status='failed',error=str(reason)[:600]);atomic_write(path,json.dumps(row,ensure_ascii=False,indent=2))
    return row


def latest(c):
    saved=[row for _,row in records(c) if row.get('status')=='saved' and row.get('filename')]
    if not saved:return None
    latest_row=max(saved,key=lambda r:r['created_at'])
    img_path=root(c)/'images'/latest_row['filename']
    if not img_path.is_file():return None
    scene=latest_row.get('scene',{}).get('state',{})
    return {
        'id':latest_row['id'],
        'filename':latest_row['filename'],
        'path':str(img_path),
        'created_at':latest_row['created_at'],
        'activity':scene.get('activity',''),
        'location':scene.get('location',''),
        'outfit':[item['id'] if isinstance(item,dict) else item for item in scene.get('outfit',[])]
    }


def share(c,body,ident=None,reason='',priority='normal',ttl_hours=6,now=None):
    body=(body or '').strip()
    if not body:raise ValueError('body text required to share a photo')
    import companion_outbox as outbox
    target=None
    if ident:
        path=capture_path(c,ident)
        if not path.exists():raise ValueError('capture not found')
        row=json.loads(path.read_text(encoding='utf-8'))
        if row.get('status')!='saved':raise ValueError('only a saved capture can be shared')
        target=root(c)/'images'/row['filename']
    else:
        info=latest(c)
        if not info:raise ValueError('no saved timeline images available to share')
        target=pathlib.Path(info['path'])
        ident=info['id']
    if not target.is_file():raise ValueError('image file is missing')
    entry={
        'kind':'image',
        'body':body,
        'media_path':str(target),
        'reason':reason or f'sharing timeline photo {ident}',
        'priority':priority,
        'ttl_hours':ttl_hours
    }
    return outbox.queue(c,entry,now)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--home',type=pathlib.Path)
    sub=parser.add_subparsers(dest='action',required=True)
    for action in ('prepare','prune','status','latest'):sub.add_parser(action)
    p=sub.add_parser('save');p.add_argument('--id',required=True);p.add_argument('--source',required=True);p.add_argument('--provider',required=True)
    p=sub.add_parser('fail');p.add_argument('--id',required=True);p.add_argument('--reason',required=True)
    p=sub.add_parser('keep',help='copy a capture into an album; the original stays')
    p.add_argument('--id',required=True);p.add_argument('--album',default='Favorites')
    p=sub.add_parser('album-add',help='put any image file into an album')
    p.add_argument('--source',required=True);p.add_argument('--album',default='Favorites')
    sub.add_parser('albums')
    sh=sub.add_parser('share',help='queue a timeline photo to share with the human')
    sh.add_argument('--body',required=True,help='message to accompany the photo')
    sh.add_argument('--id',help='specific capture id (default: latest)')
    sh.add_argument('--reason',default='',help='reason for sharing')
    sh.add_argument('--priority',choices=['normal','high'],default='normal')
    args=parser.parse_args();c=cc.load(args.home)
    if args.action=='prepare':out=prepare(c)
    elif args.action=='prune':out=prune(c)
    elif args.action=='save':out=save(c,args.id,args.source,args.provider)
    elif args.action=='fail':out=fail(c,args.id,args.reason)
    elif args.action=='keep':out=favorite(c,args.id,args.album)
    elif args.action=='album-add':out=add_to_album(c,args.source,args.album)
    elif args.action=='albums':out={'albums':albums(c)}
    elif args.action=='latest':out=latest(c) or {'status':'no saved images'}
    elif args.action=='share':out=share(c,args.body,args.id,args.reason,args.priority)
    else:
        prune(c);out={'enabled':c.image_timeline,'gallery':str(root(c)/'index.html'),'captures':[{k:r.get(k) for k in ('id','created_at','status','error')} for _,r in records(c)]}
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,KeyError,TypeError) as exc:print(json.dumps({'error':str(exc)}),file=sys.stderr);sys.exit(1)
