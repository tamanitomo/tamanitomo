"""Download a pinned Civitai artifact on a configured Comfy host. Standard library only."""
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import shutil
import socket
import sys
import urllib.parse
import urllib.request
import uuid

SLOTS={'checkpoint':'checkpoints','model':'diffusion_models','lora':'loras','vae':'vae','clip':'text_encoders'}
MAX_BYTES=60*1024**3


def public_https(url):
    u=urllib.parse.urlsplit(url)
    if u.scheme!='https' or not u.hostname or u.username or u.password or u.port not in (None,443):raise ValueError('Download requires a public HTTPS URL')
    for row in socket.getaddrinfo(u.hostname,443,type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(row[4][0]).is_global:raise ValueError('Private download destinations are refused')
    return u


class Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        target=public_https(newurl)
        result=super().redirect_request(req,fp,code,msg,headers,newurl)
        if result and target.hostname!=urllib.parse.urlsplit(req.full_url).hostname:
            result.remove_header('Authorization')
        return result


def open_url(url,key='',timeout=60):
    parsed=public_https(url)
    headers={'User-Agent':'CompanionKit/1.0'}
    if key and parsed.hostname in ('civitai.com','www.civitai.com'):headers['Authorization']='Bearer '+key
    return urllib.request.build_opener(Redirects()).open(urllib.request.Request(url,headers=headers),timeout=timeout)


def download(payload,report=lambda _:None):
    root=Path(payload['root']).expanduser().resolve()
    if not (root/'main.py').is_file():raise ValueError('Choose the ComfyUI root directory containing main.py')
    slot=SLOTS.get(payload.get('slot'))
    if not slot:raise ValueError('Unknown model slot')
    name=payload.get('filename','')
    if not name or len(name)>220 or Path(name).name!=name or any(c in name for c in '/\\\0') or name.startswith('.') or Path(name).suffix.lower() not in ('.safetensors','.gguf'):
        raise ValueError('Only named safetensors and GGUF weight files are accepted')
    digest=payload.get('sha256','').lower()
    if not re.fullmatch('[a-f0-9]{64}',digest):raise ValueError('A publisher SHA-256 is required')
    size=payload.get('size_bytes')
    if isinstance(size,bool) or not isinstance(size,(int,float)) or not math.isfinite(size) or not 0<size<=MAX_BYTES:raise ValueError('Invalid or oversized model file')
    url=payload['url'];host=urllib.parse.urlsplit(url).hostname
    if host not in ('civitai.com','www.civitai.com'):raise ValueError('Downloads must originate at Civitai')
    folder=root/'models'/slot
    # A user can configure the root itself on another disk; individual slot symlinks
    # are refused so a downloaded filename cannot escape that configured root.
    for p in [root/'models',folder]:
        if p.is_symlink():raise ValueError('Use a real model folder beneath the configured Comfy root')
    folder.mkdir(parents=True,exist_ok=True);dest=folder/name
    if dest.is_symlink():raise ValueError('Destination is a symbolic link')
    if dest.exists():
        with dest.open('rb') as f:existing=hashlib.file_digest(f,'sha256').hexdigest()
        if existing!=digest:raise ValueError('A different file already has this name; it was not replaced')
        return {**record_metadata(root,payload),'reused':True}
    if shutil.disk_usage(folder).free<size+512*1024**2:raise ValueError('Not enough free disk space for these weights')
    temporary=folder/('.'+name+'.'+uuid.uuid4().hex+'.partial');count=0;sha=hashlib.sha256();last=0
    try:
        with open_url(url,payload.get('api_key','')) as response,temporary.open('xb') as output:
            while chunk:=response.read(1024**2):
                count+=len(chunk)
                if count>min(MAX_BYTES,max(size*1.02,size+1024**2)):raise ValueError('Download is larger than the published file size')
                sha.update(chunk);output.write(chunk)
                if count-last>=16*1024**2:report(f'Downloaded {count/1024**2:.0f} / {size/1024**2:.0f} MB');last=count
            output.flush();os.fsync(output.fileno())
        if sha.hexdigest()!=digest:raise ValueError('SHA-256 mismatch; incomplete or changed weights were discarded')
        # Hard-link commits without overwriting a concurrent download.
        os.link(temporary,dest)
    finally:temporary.unlink(missing_ok=True)
    return {**record_metadata(root,payload),'bytes':count,'reused':False}


def record_metadata(root,payload):
    meta={k:payload.get(k) for k in ('filename','slot','sha256','family','base_model','model_id','version_id','file_id')}
    manifest=root/'models'/'.companion-library'
    if manifest.is_symlink():raise ValueError('Library metadata must stay beneath the Comfy root')
    manifest.mkdir(exist_ok=True)
    record=manifest/(payload['sha256'].lower()+'.json')
    if record.is_symlink():raise ValueError('Library metadata cannot be a symbolic link')
    temporary=manifest/(uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_text(json.dumps(meta,indent=2));os.replace(temporary,record)
    finally:temporary.unlink(missing_ok=True)
    return meta


def library(payload):
    root=Path(payload['root']).expanduser().resolve()
    if not (root/'main.py').is_file():raise ValueError('Choose the ComfyUI root containing main.py')
    result=[]
    for path in (root/'models/.companion-library').glob('*.json'):
        if path.is_symlink():continue
        try:
            row=json.loads(path.read_text())
            if row.get('slot') in SLOTS and (root/'models'/SLOTS[row['slot']]/row['filename']).is_file():result.append(row)
        except (OSError,ValueError,KeyError):continue
    return {'models':result}


if __name__=='__main__':
    try:
        payload=json.load(sys.stdin)
        result=library(payload) if payload.get('action')=='library' else download(payload,lambda value:print('PROGRESS='+value,flush=True))
        print('RESULT='+json.dumps(result),flush=True)
    except Exception as exc:
        # URLs may contain signed CDN credentials; never echo exception URLs.
        message=str(exc) if isinstance(exc,ValueError) else type(exc).__name__+': model download failed'
        print('ERROR='+message,flush=True);sys.exit(1)
