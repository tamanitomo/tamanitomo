"""Stage a trusted release ZIP; apply it only on the next launcher start."""
import hashlib,io,json,os,stat,zipfile
from pathlib import Path,PurePosixPath
from fastapi import Request,HTTPException
ROOT=Path(__file__).resolve().parents[2]
MAX_ZIP=25*1024**2

def stage(raw,root=ROOT):
    if len(raw)>MAX_ZIP:raise ValueError('Update package exceeds 25 MB')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        entries=z.infolist();names=[i.filename for i in entries]
        if len(names)!=len(set(names)) or len(names)>1000:raise ValueError('Invalid duplicate or oversized release')
        if sum(i.file_size for i in entries)>80*1024**2:raise ValueError('Expanded update is too large')
        files={}
        for i in entries:
            p=PurePosixPath(i.filename)
            if len(p.parts)<2 or p.parts[0]!='companion-kit' or '..' in p.parts or '\\' in i.filename or i.is_dir() or stat.S_ISLNK(i.external_attr>>16):raise ValueError('Unsafe release path')
            name='/'.join(p.parts[1:])
            if i.filename!='companion-kit/'+name or ':' in name or any(ord(c)<32 for c in name) or any(x.endswith(('.', ' ')) for x in p.parts) or name.casefold() in {n.casefold() for n in files}:raise ValueError('Ambiguous release path')
            if name.startswith('.') and name not in ('.gitignore','.github/workflows/test.yml'):raise ValueError('Private state cannot be included in an update')
            if any(x in p.parts for x in ('.env','.venv','__pycache__')) or name.endswith('companion.json'):raise ValueError('Release contains user state')
            files[name]=z.read(i)
        hashes=json.loads(files.pop('SHA256SUMS.json'))
        manifest=json.loads(files['release-files.json'])
        if set(manifest)!=set(files) or set(hashes)!=set(files):raise ValueError('Release manifest does not match package')
        for name,data in files.items():
            if hashes[name]!=hashlib.sha256(data).hexdigest():raise ValueError('Update integrity check failed: '+name)
            dest=root/name
            if any(p.is_symlink() for p in [dest,*dest.parents] if p!=root.parent):raise ValueError('Update destination contains a link')
        version=files.get('VERSION',b'Unversioned').decode().strip()
        # Never overwrite a modified installed release. Development trees need manual updates.
        current=root/'SHA256SUMS.json'
        if not current.is_file():raise ValueError('This is a development checkout. Install updates in an extracted release, not this working tree.')
        old=json.loads(current.read_text())
        if any((root/n).exists() and n not in old for n in files):raise ValueError('Update would overwrite an unmanaged local file; move it aside first')
        changed=[n for n,digest in old.items() if not (root/n).is_file() or hashlib.sha256((root/n).read_bytes()).hexdigest()!=digest]
        if changed:raise ValueError('Local code changes detected; keep them and update manually: '+', '.join(changed[:5]))
        folder=root/'.pending-update'
        if folder.exists():raise ValueError('An update is already staged; relaunch before staging another')
        folder.mkdir()
        if folder.is_symlink():raise ValueError('Invalid staging folder')
        for name,data in files.items():
            dest=folder/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
        (folder/'SHA256SUMS.json').write_text(json.dumps(hashes))
        return {'staged':True,'version':version,'files':len(files),'note':'Update verified and staged. Close Companion Kit, then launch it again to install. Your Hermes profiles and vault are untouched.'}

_UPDATE_CACHE = {'checked_at': 0, 'data': None}

def check_github_update(current_version: str) -> dict:
    import time, urllib.request, json
    now = time.time()
    cached = _UPDATE_CACHE.get('data')
    if cached and (now - _UPDATE_CACHE.get('checked_at', 0) < 3600):
        return cached

    res = {
        'has_update': False,
        'latest_version': current_version,
        'release_url': None,
        'release_notes': None
    }
    try:
        req = urllib.request.Request(
            'https://api.github.com/repos/nightspades/companion-kit/releases/latest',
            headers={'User-Agent': 'Companion-Kit-Updater', 'Accept': 'application/vnd.github.v3+json'}
        )
        with urllib.request.urlopen(req, timeout=3) as r:
            if r.status == 200:
                rel = json.loads(r.read().decode())
                tag = (rel.get('tag_name') or '').lstrip('v').strip()
                cur = current_version.lstrip('v').strip()
                if tag and tag != cur:
                    res = {
                        'has_update': True,
                        'latest_version': tag,
                        'release_url': rel.get('html_url'),
                        'release_notes': (rel.get('body') or '')[:200]
                    }
    except Exception:
        pass

    _UPDATE_CACHE['checked_at'] = now
    _UPDATE_CACHE['data'] = res
    return res

def register(app):
    @app.get('/api/updates')
    def status():
        version = (ROOT/'VERSION').read_text().strip() if (ROOT/'VERSION').exists() else '2.1.0'
        remote = check_github_update(version)
        return {
            'version': version,
            'release_install': (ROOT/'SHA256SUMS.json').is_file(),
            'pending': (ROOT/'.pending-update/SHA256SUMS.json').is_file(),
            **remote
        }
    @app.post('/api/updates/stage')
    async def upload(request:Request):
        chunks=[];size=0
        async for chunk in request.stream():
            size+=len(chunk)
            if size>MAX_ZIP:raise HTTPException(413,'Update package exceeds 25 MB')
            chunks.append(chunk)
        try:return stage(b''.join(chunks))
        except (zipfile.BadZipFile,KeyError,UnicodeError,json.JSONDecodeError):raise ValueError('Not a Companion Kit release package')
