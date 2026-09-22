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
        installed=root/name
        installed_digest=(hashlib.sha256(installed.read_bytes()).hexdigest()
                          if installed.is_file() else None)
        # A bootstrap hot-fix may already equal the verified staged file. It is
        # safe to adopt; anything else is still an unrelated local change.
        if installed_digest!=digest and installed_digest!=hashes.get(name):
            raise ValueError('Installed code changed after staging; update stopped')
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
    _prune_backups(root,keep=3)
    print('Tamanitomo updated. Previous code is in '+str(backup))


KEEP_BACKUPS=3

def _prune_backups(root,keep=KEEP_BACKUPS):
    """Keep the newest few rollback copies; a phone does not have room for all of them.

    Every update snapshots the whole application, and nothing ever removed one,
    so a host that updates often quietly grows a full copy per release -- which
    matters most exactly where the kit is most likely to run out of room, a
    Termux server or a small mini-PC. Pruning happens only after the update has
    fully succeeded, and the copy just taken is by definition among the newest,
    so the rollback path for this update is never the one that gets deleted.
    A failure to tidy up is not a failure to update.
    """
    folder=root/'.update-backups'
    try:
        if not folder.is_dir() or folder.is_symlink():return []
        saved=sorted((d for d in folder.iterdir() if d.is_dir() and not d.is_symlink()),
                     key=lambda d:d.stat().st_mtime,reverse=True)
        removed=[]
        for old_backup in saved[max(int(keep),1):]:
            shutil.rmtree(old_backup,ignore_errors=True)
            removed.append(old_backup.name)
        if removed:print(f'Removed {len(removed)} older backup(s), keeping the newest {max(int(keep),1)}.')
        return removed
    except OSError:
        return []
