"""Stage a trusted release ZIP; apply it only on the next launcher start."""
import hashlib,io,json,os,stat,zipfile
from pathlib import Path,PurePosixPath
from fastapi import Request,HTTPException
ROOT=Path(__file__).resolve().parents[2]
MAX_ZIP=25*1024**2
import uuid
INSTANCE_ID = uuid.uuid4().hex

def stage(raw,root=ROOT):
    if len(raw)>MAX_ZIP:raise ValueError('Update package exceeds 25 MB')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        entries=z.infolist();names=[i.filename for i in entries]
        if len(names)!=len(set(names)) or len(names)>1000:raise ValueError('Invalid duplicate or oversized release')
        if sum(i.file_size for i in entries)>80*1024**2:raise ValueError('Expanded update is too large')
        files={}; modes={}
        for i in entries:
            p=PurePosixPath(i.filename)
            if len(p.parts)<2 or p.parts[0] not in ('tamanitomo','companion-kit') or '..' in p.parts or '\\' in i.filename or i.is_dir() or stat.S_ISLNK(i.external_attr>>16):raise ValueError('Unsafe release path')
            name='/'.join(p.parts[1:])
            if i.filename!=p.parts[0]+'/'+name or ':' in name or any(ord(c)<32 for c in name) or any(x.endswith(('.', ' ')) for x in p.parts) or name.casefold() in {n.casefold() for n in files}:raise ValueError('Ambiguous release path')
            if name.startswith('.') and name not in ('.gitignore','.github/workflows/test.yml'):raise ValueError('Private state cannot be included in an update')
            if any(x in p.parts for x in ('.env','.venv','__pycache__')) or name.endswith('companion.json'):raise ValueError('Release contains user state')
            files[name]=z.read(i)
            modes[name]=0o755 if (i.external_attr>>16)&0o111 else 0o644
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
            dest=folder/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data);dest.chmod(modes[name])
        (folder/'SHA256SUMS.json').write_text(json.dumps(hashes))
        return {'staged':True,'version':version,'files':len(files),'note':'Update verified and staged. Close Tamanitomo, then launch it again to install. Your Hermes profiles and vault are untouched.'}

_UPDATE_CACHE = {'checked_at': 0, 'data': None, 'version': None}
RELEASE_API = 'https://api.github.com/repos/tamanitomo/tamanitomo/releases/latest'
ASSET_NAME = 'tamanitomo-release.zip'


def _version(value):
    import re
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', value.strip())
    if not match:
        raise ValueError('Expected a stable release version, such as 2.2.2')
    return tuple(map(int, match.groups()))


def check_github_update(current_version: str, force: bool = False) -> dict:
    import time, urllib.request, urllib.error
    now = time.time()
    cached = _UPDATE_CACHE.get('data')
    if not force and cached and _UPDATE_CACHE.get('version') == current_version and now - _UPDATE_CACHE['checked_at'] < 3600:
        return cached
    result = {'has_update': False, 'latest_version': None, 'release_url': None,
              'release_notes': None, 'download_url': None, 'checked': False, 'error': None}
    try:
        request = urllib.request.Request(RELEASE_API, headers={
            'User-Agent': 'Tamanitomo-Updater', 'Accept': 'application/vnd.github+json'})
        with urllib.request.urlopen(request, timeout=15) as response:
            release = json.loads(response.read(1024 * 1024))
        tag = release['tag_name']
        latest = tag.removeprefix('v')
        asset = next((a for a in release.get('assets', []) if a.get('name') == ASSET_NAME), None)
        if release.get('draft') or release.get('prerelease') or not asset:
            raise ValueError('The latest release has no installable Tamanitomo ZIP yet.')
        url = asset.get('browser_download_url', '')
        expected = f'https://github.com/tamanitomo/tamanitomo/releases/download/{tag}/{ASSET_NAME}'
        if url != expected:
            raise ValueError('The release asset is not on the official download URL.')
        notes = (release.get('body') or '').strip()
        if len(notes) > 12000:
            notes = notes[:12000].rstrip() + '\n\n…'
        result.update(has_update=_version(latest) > _version(current_version),
                      latest_version=latest, release_url=release.get('html_url'),
                      release_notes=notes, download_url=url,
                      digest=asset.get('digest'), tag=tag, checked=True)
    except urllib.error.HTTPError as exc:
        result['error'] = ('No published release is available yet.' if exc.code == 404
                           else f'GitHub update check failed (HTTP {exc.code}). Try again later.')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result['error'] = f'Could not check for updates: {exc}'
    # Failures remain retryable; do not claim that an offline host is up to date.
    if result['checked']:
        _UPDATE_CACHE.update(checked_at=now, data=result, version=current_version)
    else:
        _UPDATE_CACHE.clear()
    return result


def _delayed_restart():
    """Restart this workspace, without restarting unrelated workspaces or Hermes."""
    import time, shutil, subprocess, sys
    time.sleep(2)
    if shutil.which('systemctl'):
        for unit in ('tamanitomo.service', 'companion-workspace.service'):
            try:
                result = subprocess.run(['systemctl', '--user', 'show', unit, '--property=MainPID', '--value'],
                                        capture_output=True, text=True, timeout=5)
                if result.returncode == 0 and result.stdout.strip() == str(os.getpid()):
                    subprocess.run(['systemctl', '--user', 'restart', '--no-block', unit], check=True, timeout=5)
                    return
            except (OSError, subprocess.SubprocessError):
                pass
    # Works for terminal launches and runit too; exec keeps the supervised PID.
    os.execv(sys.executable, [sys.executable, *sys.orig_argv[1:]])


def _install_dependencies(root, requirements):
    import subprocess, sys
    installed = root / 'requirements.txt'
    if installed.exists() and installed.read_bytes() == requirements.read_bytes():
        return
    result = subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', str(requirements)],
                            cwd=root, capture_output=True, text=True, timeout=600)
    if result.returncode:
        raise ValueError('Dependency installation failed; application code was not replaced. ' + result.stderr[-1500:])


def perform_in_app_update(report, root=ROOT):
    """Install the latest published release; never read or upload companion data."""
    import subprocess, shutil, threading, urllib.request
    version = (root / 'VERSION').read_text().strip()
    report({'stage': 'Checking the official release...', 'percent': 10})
    info = check_github_update(version, force=True)
    if not info.get('checked'):
        raise ValueError(info.get('error') or 'Could not check the official release.')
    if not info['has_update']:
        return {'success': True, 'restarting': False, 'version': version,
                'message': 'You already have the latest stable release.'}
    latest = info['latest_version']
    if (root / '.git').exists() and shutil.which('git'):
        def git(*args):
            result = subprocess.run(['git', *args], cwd=root, capture_output=True, text=True, timeout=120)
            if result.returncode:
                raise ValueError('Git update failed: ' + (result.stderr or result.stdout).strip())
            return result.stdout.strip()
        if git('status', '--porcelain'):
            raise ValueError('Local code changes detected. Commit or move them before updating.')
        report({'stage': 'Fetching the published release tag...', 'percent': 35})
        git('fetch', 'https://github.com/tamanitomo/tamanitomo.git', 'tag', info['tag'])
        if git('show', info['tag'] + ':VERSION') != latest:
            raise ValueError('Release tag and VERSION do not match.')
        # Check fast-forward feasibility before installing dependencies or changing code.
        git('merge-base', '--is-ancestor', 'HEAD', info['tag'])
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            requirements = Path(tmp) / 'requirements.txt'
            requirements.write_text(git('show', info['tag'] + ':requirements.txt') + '\n')
            _install_dependencies(root, requirements)
        git('merge', '--ff-only', info['tag'])
    elif (root / 'SHA256SUMS.json').is_file():
        report({'stage': 'Downloading the official release ZIP...', 'percent': 35})
        request = urllib.request.Request(info['download_url'], headers={'User-Agent': 'Tamanitomo-Updater'})
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read(MAX_ZIP + 1)
        if len(data) > MAX_ZIP:
            raise ValueError('Update package exceeds 25 MB')
        digest = info.get('digest')
        if digest and digest != 'sha256:' + hashlib.sha256(data).hexdigest():
            raise ValueError('Downloaded ZIP does not match the GitHub release digest.')
        report({'stage': 'Verifying the release and preparing dependencies...', 'percent': 60})
        stage(data, root=root)
        try:
            staged = root / '.pending-update'
            if (staged / 'VERSION').read_text().strip() != latest:
                raise ValueError('Release version does not match the published tag.')
            _install_dependencies(root, staged / 'requirements.txt')
            report({'stage': 'Installing application files with rollback backup...', 'percent': 85})
            from update_release import _apply_pending
            _apply_pending(root)
        except Exception:
            shutil.rmtree(root / '.pending-update', ignore_errors=True)
            raise
    else:
        raise ValueError('This source copy is not a release installation. Extract the official release ZIP to install updates.')
    report({'stage': f'Tamanitomo v{latest} installed. Restarting workspace...', 'percent': 100})
    threading.Thread(target=_delayed_restart, daemon=True).start()
    return {'success': True, 'restarting': True, 'version': latest,
            'message': f'Tamanitomo updated to v{latest}. Workspace is restarting.'}


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
            'instance_id': INSTANCE_ID,
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
