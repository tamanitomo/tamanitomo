"""Launcher-time release update with rollback; runs before importing application code."""
import hashlib,json,os,shutil,uuid,contextlib
from pathlib import Path

@contextlib.contextmanager
def runtime_lock(root):
    with (root/'.runtime.lock').open('a+b') as f:
        f.write(b'0');f.flush();f.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:raise ValueError('Close the running Tamanitomo host (Ctrl-C in its launcher window), then launch again to update.')
        try:yield
        finally:
            if os.name=='nt':f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(f.fileno(),fcntl.LOCK_UN)

def apply_pending(root):
    if not (root/'.pending-update/SHA256SUMS.json').exists():return
    with runtime_lock(root):_apply_pending(root)

def _apply_pending(root):
    folder=root/'.pending-update';manifest=folder/'SHA256SUMS.json'
    if not manifest.exists():return
    hashes=json.loads(manifest.read_text());old=json.loads((root/'SHA256SUMS.json').read_text())
    for name,digest in hashes.items():
        path=Path(name)
        if path.is_absolute() or '..' in path.parts or '\\' in name:raise ValueError('Unsafe staged path')
        p=folder/name
        if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:raise ValueError('Staged update changed; reinstall a trusted package')
    for name,digest in old.items():
        if not (root/name).is_file() or hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:raise ValueError('Installed code changed after staging; update stopped')
    backup=root/'.update-backups'/uuid.uuid4().hex;backup.mkdir(parents=True)
    names=set(old)|set(hashes)|{'SHA256SUMS.json'};written=[]
    try:
        for name in names:
            dest=root/name
            if dest.exists():b=backup/name;b.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dest,b)
        for name in [*hashes,'SHA256SUMS.json']:
            dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True);temp=dest.with_name('.'+dest.name+'.update');shutil.copy2(folder/name,temp);os.replace(temp,dest);written.append(name)
        for name in set(old)-set(hashes):(root/name).unlink(missing_ok=True)
    except Exception:
        for name in names:
            saved=backup/name;dest=root/name
            if saved.exists():dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(saved,dest)
            elif name in written:dest.unlink(missing_ok=True)
        raise
    shutil.rmtree(folder)
    print('Tamanitomo updated. Previous code is in '+str(backup))
