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
            if len(p.parts)<2 or p.parts[0] not in ('tamanitomo','companion-kit') or '..' in p.parts or '\\' in i.filename or i.is_dir() or stat.S_ISLNK(i.external_attr>>16):raise ValueError('Unsafe release path')
            name='/'.join(p.parts[1:])
            if i.filename!=p.parts[0]+'/'+name or ':' in name or any(ord(c)<32 for c in name) or any(x.endswith(('.', ' ')) for x in p.parts) or name.casefold() in {n.casefold() for n in files}:raise ValueError('Ambiguous release path')
            if name.startswith('.') and name not in ('.gitignore','.github/workflows/test.yml'):raise ValueError('Private state cannot be included in an update')
            if any(x in p.parts for x in ('.env','.venv','__pycache__')) or name.endswith('companion.json'):raise ValueError('Release contains user state')
            files[name]=z.read(i)
        hashes=json.loads(files.pop('SHA256SUMS.json'))
        manifest=json.loads(files['release-files.json'])
        if set(manifest)!=set(files) or set(hashes)!=set(files):raise ValueError('Release manifest does not match package')
        for name,data in files.items():
            if hashes[name]!=hashlib.sha256(data).hexdigest():raise ValueError('Update integrity check failed: '+name)
            dest=root/name
            for p in [dest,*dest.parents]:
                if p==root:break
                if p.is_symlink():raise ValueError('Update destination contains a link')
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
        return {'staged':True,'version':version,'files':len(files),'note':'Update verified and staged. Close Tamanitomo, then launch it again to install. Your Hermes profiles and vault are untouched.'}

_UPDATE_CACHE = {'checked_at': 0, 'data': None}

def check_github_update(current_version: str, force: bool = False) -> dict:
    import time, urllib.request, json
    now = time.time()
    cached = _UPDATE_CACHE.get('data')
    if not force and cached and (now - _UPDATE_CACHE.get('checked_at', 0) < 3600):
        return cached

    res = {
        'has_update': False,
        'latest_version': current_version,
        'release_url': None,
        'release_notes': None
    }
    try:
        req = urllib.request.Request(
            'https://api.github.com/repos/tamanitomo/tamanitomo/releases/latest',
            headers={'User-Agent': 'Tamanitomo-Updater', 'Accept': 'application/vnd.github.v3+json'}
        )
        with urllib.request.urlopen(req, timeout=4) as r:
            if r.status == 200:
                rel = json.loads(r.read().decode())
                tag = (rel.get('tag_name') or '').lstrip('v').strip()
                cur = current_version.lstrip('v').strip()
                if tag and tag != cur:
                    res = {
                        'has_update': True,
                        'latest_version': tag,
                        'release_url': rel.get('html_url'),
                        'release_notes': (rel.get('body') or '')[:300]
                    }
    except Exception:
        pass

    _UPDATE_CACHE['checked_at'] = now
    _UPDATE_CACHE['data'] = res
    return res


def _delayed_restart():
    """Trigger graceful service restart after HTTP response is returned to browser."""
    import time, shutil, subprocess, os
    time.sleep(1.5)
    # 1. Restart gateway background workers if active
    if shutil.which('systemctl'):
        for gw in ('tamanitomo-gateway', 'companion-gateway'):
            try:
                chk = subprocess.run(['systemctl', '--user', 'is-active', gw], capture_output=True)
                if chk.returncode == 0:
                    subprocess.run(['systemctl', '--user', 'restart', gw], check=False)
            except Exception:
                pass
    if shutil.which('sv'):
        for gw in ('tamanitomo-gateway', 'companion-gateway'):
            try:
                res = subprocess.run(['sv', 'status', gw], capture_output=True, text=True)
                if res.returncode == 0 and 'run:' in res.stdout:
                    subprocess.run(['sv', 'restart', gw], check=False)
            except Exception:
                pass

    # 2. Restart workspace web server
    if shutil.which('systemctl'):
        for unit in ('tamanitomo', 'tamanitomo.service', 'companion-workspace', 'companion-workspace.service'):
            try:
                chk = subprocess.run(['systemctl', '--user', 'is-active', unit], capture_output=True)
                if chk.returncode == 0:
                    subprocess.run(['systemctl', '--user', 'restart', unit], check=False)
                    return
            except Exception:
                pass
    if shutil.which('sv'):
        for svc in ('tamanitomo-workspace', 'companion-workspace'):
            try:
                res = subprocess.run(['sv', 'status', svc], capture_output=True, text=True)
                if res.returncode == 0 and 'run:' in res.stdout:
                    subprocess.run(['sv', 'restart', svc], check=False)
                    return
            except Exception:
                pass

    # 3. Fallback: exit process so supervisor/service manager restarts it
    os._exit(0)


def perform_in_app_update(report, root=ROOT):
    """Execute update for Tamanitomo only (leaving Hermes completely untouched)."""
    import subprocess, sys, shutil, threading
    report({'stage': 'Checking local installation type...', 'percent': 10})

    if (root / '.git').is_dir() and shutil.which('git'):
        # Git-based installation (Linux / Termux / macOS / dev checkouts)
        status_res = subprocess.run(['git', 'status', '--porcelain'], cwd=root, capture_output=True, text=True)
        stashed = False
        if status_res.stdout.strip():
            report({'stage': 'Safeguarding local changes...', 'percent': 20})
            stash_res = subprocess.run(
                ['git', 'stash', 'save', 'Auto-stashed before Tamanitomo update'],
                cwd=root, capture_output=True, text=True
            )
            if stash_res.returncode == 0 and 'Saved working directory' in stash_res.stdout:
                stashed = True

        try:
            report({'stage': 'Fetching latest Tamanitomo release from GitHub...', 'percent': 40})
            fetch_res = subprocess.run(
                ['git', 'fetch', 'origin', 'main'],
                cwd=root, capture_output=True, text=True
            )
            if fetch_res.returncode != 0:
                raise ValueError(f"Failed to fetch updates from GitHub: {fetch_res.stderr.strip() or fetch_res.stdout.strip()}")

            req_file = root / 'requirements.txt'
            req_before = req_file.read_bytes() if req_file.exists() else b''

            report({'stage': 'Applying latest Tamanitomo code...', 'percent': 65})
            pull_res = subprocess.run(
                ['git', 'pull', '--ff-only', 'origin', 'main'],
                cwd=root, capture_output=True, text=True
            )
            if pull_res.returncode != 0:
                raise ValueError(f"Failed to apply updates (git pull failed): {pull_res.stderr.strip() or pull_res.stdout.strip()}")

            req_after = req_file.read_bytes() if req_file.exists() else b''
            if req_before != req_after and req_file.exists():
                report({'stage': 'Updating Tamanitomo Python dependencies...', 'percent': 85})
                subprocess.run(
                    [sys.executable, '-m', 'pip', 'install', '-r', str(req_file), '--quiet'],
                    cwd=root, capture_output=True
                )

            if stashed:
                subprocess.run(['git', 'stash', 'pop'], cwd=root, capture_output=True)

            ver_file = root / 'VERSION'
            new_version = ver_file.read_text().strip() if ver_file.exists() else '2.2.1'
            report({'stage': f'Tamanitomo v{new_version} installed! Restarting workspace...', 'percent': 100})
            threading.Thread(target=_delayed_restart, daemon=True).start()
            return {
                'success': True,
                'restarting': True,
                'version': new_version,
                'message': f'Tamanitomo successfully updated to v{new_version}. Workspace is restarting...'
            }
        except Exception:
            if stashed:
                subprocess.run(['git', 'stash', 'pop'], cwd=root, capture_output=True)
            raise

    elif (root / 'SHA256SUMS.json').is_file():
        # Packaged ZIP installation
        report({'stage': 'Querying latest release bundle...', 'percent': 20})
        cur_version = (root / 'VERSION').read_text().strip() if (root / 'VERSION').exists() else '2.2.1'
        info = check_github_update(cur_version, force=True)
        latest_tag = info.get('latest_version') or cur_version
        download_url = f"https://github.com/tamanitomo/tamanitomo/releases/download/v{latest_tag}/tamanitomo-release.zip"

        report({'stage': f'Downloading Tamanitomo v{latest_tag} release bundle...', 'percent': 45})
        import urllib.request
        req = urllib.request.Request(download_url, headers={'User-Agent': 'Tamanitomo-Updater'})
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = resp.read()
        except Exception as exc:
            raise ValueError(f"Failed to download release bundle: {exc}")

        report({'stage': 'Verifying release integrity and staging files...', 'percent': 75})
        stage(data, root=root)

        report({'stage': 'Applying release updates...', 'percent': 90})
        from update_release import _apply_pending
        _apply_pending(root)

        ver_file = root / 'VERSION'
        new_version = ver_file.read_text().strip() if ver_file.exists() else latest_tag
        report({'stage': f'Tamanitomo v{new_version} installed! Restarting workspace...', 'percent': 100})
        threading.Thread(target=_delayed_restart, daemon=True).start()
        return {
            'success': True,
            'restarting': True,
            'version': new_version,
            'message': f'Tamanitomo successfully updated to v{new_version}. Workspace is restarting...'
        }
    else:
        raise ValueError('Cannot auto-update: neither a git repository nor a release bundle installation was detected.')


def register(app):
    @app.get('/api/updates')
    def status(force: bool = False):
        version = (ROOT/'VERSION').read_text().strip() if (ROOT/'VERSION').exists() else '2.2.1'
        remote = check_github_update(version, force=force)
        return {
            'version': version,
            'release_install': (ROOT/'SHA256SUMS.json').is_file(),
            'is_git': (ROOT/'.git').is_dir(),
            'pending': (ROOT/'.pending-update/SHA256SUMS.json').is_file(),
            **remote
        }

    @app.post('/api/updates/check')
    def check_now():
        version = (ROOT/'VERSION').read_text().strip() if (ROOT/'VERSION').exists() else '2.2.1'
        return check_github_update(version, force=True)

    @app.post('/api/updates/apply')
    def apply_update_route(request: Request):
        if not hasattr(app.state, 'operations'):
            raise HTTPException(500, 'Operations manager not initialized')

        prof = request.query_params.get('profile') or 'default'

        def run(report):
            return perform_in_app_update(report, root=ROOT)

        return app.state.operations.submit(
            str(ROOT),
            'Update Tamanitomo',
            run,
            profile=prof
        )

    @app.post('/api/updates/stage')
    async def upload(request:Request):
        chunks=[];size=0
        async for chunk in request.stream():
            size+=len(chunk)
            if size>MAX_ZIP:raise HTTPException(413,'Update package exceeds 25 MB')
            chunks.append(chunk)
        try:return stage(b''.join(chunks))
        except (zipfile.BadZipFile,KeyError,UnicodeError,json.JSONDecodeError):raise ValueError('Not a Tamanitomo release package')

