"""Constrained vault browsing and optimistic writes to user-owned notes."""
from __future__ import annotations
import hashlib
import json
import datetime as dt
import uuid
import os
from pathlib import Path
import companion_platform as cp
import companion_peer as peer

MAX_TEXT=2_000_000
TEXT={'.md','.txt','.json','.jsonl','.yaml','.yml','.csv'}

def resolve(c, relative=''):
    if not isinstance(relative,str) or '\\' in relative or '\x00' in relative:
        raise ValueError('Use a relative vault path')
    rel=Path(relative)
    if rel.is_absolute() or any(p in ('..','.') or p.startswith('.') for p in rel.parts):
        raise ValueError('Path must stay inside the vault; hidden files are excluded')
    if peer.is_secret(rel): raise ValueError('Credential files are not served by the vault browser')
    root=c.vault.resolve()
    path=(root/rel).resolve()
    if path!=root and root not in path.parents: raise ValueError('Path leaves the vault')
    if any(p.startswith('.') for p in path.relative_to(root).parts): raise ValueError('Hidden files are excluded')
    return path

def editable(c, relative):
    rel=Path(relative)
    return rel.suffix.lower()=='.md' and not protected(c,relative)

def protected(c, relative):
    """Protect runtime state and identity for every companion in a shared vault."""
    path=resolve(c,relative)
    parts={p.lower() for p in path.relative_to(c.vault.resolve()).parts}
    critical={'soul.md','agents.md','user.md','memory.md','config.yaml','config.yml',
              'companion.json','profile.yaml','requirements.txt','pyproject.toml','package.json','package-lock.json','uv.lock'}
    return (path.name.lower() in critical or bool(parts & {'companion-life','soul','hooks','scripts','hermes-agent'})
            or path.suffix.lower() in {'.db','.db-wal','.db-shm','.sqlite','.sqlite3','.py','.sh','.ps1','.cmd'}
            or path==c.soul.resolve() or path==c.canonical_soul.resolve()
            or path==c.home.resolve() or c.home.resolve() in path.parents)

def metadata(c,relative):
    locked=protected(c,relative)
    return {'protected':locked,'editable':editable(c,relative),
            'deletable':not locked and resolve(c,relative).is_file(),
            'protection_reason':'Installation or companion state. Read-only in Vault; use its dedicated settings editor.' if locked else ''}

def listing(c, relative=''):
    path=resolve(c,relative)
    if not path.is_dir(): raise ValueError('Vault folder does not exist')
    rows=[]
    for p in sorted(path.iterdir(),key=lambda p:(not p.is_dir(),p.name.lower())):
        rel=p.relative_to(c.vault.resolve()).as_posix()
        try:
            target=resolve(c,rel)
            if p.is_symlink(): continue
            stat=target.stat()
        except (ValueError,OSError): continue
        rows.append({'name':p.name,'path':rel,'directory':target.is_dir(),
                     'bytes':stat.st_size,'modified':stat.st_mtime,**metadata(c,rel)})
        if len(rows)>=2000: break
    return {'path':relative,'entries':rows,'root':str(c.vault),'limit':2000}

def read(c, relative):
    path=resolve(c,relative)
    if not path.is_file() or path.suffix.lower() not in TEXT: raise ValueError('Select a text or Markdown file')
    if path.stat().st_size>MAX_TEXT: raise ValueError('This file is too large for the editor (2 MB limit)')
    data=path.read_bytes()
    return {'path':relative,'text':data.decode('utf-8'),'revision':hashlib.sha256(data).hexdigest(),
            **metadata(c,relative)}

def trash(c,relative,revision=None):
    path=resolve(c,relative)
    if not path.is_file() or protected(c,relative):raise ValueError('This file is protected or is not a regular file')
    with cp.file_lock(c.vault/'.companion-editor.lock'):
        if revision is not None and hashlib.sha256(path.read_bytes()).hexdigest()!=revision:
            raise FileExistsError('This file changed since you opened it. Reload before moving it to trash.')
        ident=uuid.uuid4().hex
        folder=c.vault/'.trash'/'tamanitomo'/ident
        if (c.vault/'.trash').is_symlink() or (c.vault/'.trash'/'tamanitomo').is_symlink():
            raise ValueError('Trash must not be a symbolic link')
        folder.mkdir(parents=True)
        cp.atomic_write(folder/'metadata.json',json.dumps({'id':ident,'path':relative,'deleted_at':dt.datetime.now(dt.timezone.utc).isoformat()}))
        os.replace(path,folder/'file')
    return {'trashed':relative,'id':ident}

def trash_list(c):
    rows=[]
    for sub in ('tamanitomo','companion-kit'):
        root=c.vault/'.trash'/sub
        if root.exists():
            if root.is_symlink() or root.parent.is_symlink():raise ValueError('Trash must not be a symbolic link')
            if root.is_dir():
                for folder in root.iterdir():
                    if folder.is_symlink() or not (folder/'file').is_file():continue
                    try:rows.append(json.loads((folder/'metadata.json').read_text()))
                    except (OSError,ValueError):continue
    return {'files':sorted(rows,key=lambda r:r['deleted_at'],reverse=True)}

def restore(c,ident):
    if not isinstance(ident,str) or not __import__('re').fullmatch('[a-f0-9]{32}',ident):raise ValueError('Invalid trash entry')
    folder=c.vault/'.trash'/'tamanitomo'/ident
    if not folder.exists():
        folder=c.vault/'.trash'/'companion-kit'/ident
    if any(p.is_symlink() for p in (folder,folder.parent,folder.parent.parent,folder/'file',folder/'metadata.json')):raise ValueError('Invalid trash entry')
    with cp.file_lock(c.vault/'.companion-editor.lock'):
        row=json.loads((folder/'metadata.json').read_text())
        dest=resolve(c,row['path'])
        if protected(c,row['path']):raise ValueError('The restore destination is protected')
        if dest.exists():raise FileExistsError('A file already exists at the original path. Rename it before restoring.')
        dest.parent.mkdir(parents=True,exist_ok=True)
        os.replace(folder/'file',dest)
        (folder/'metadata.json').unlink();folder.rmdir()
    return {'restored':row['path']}

def write(c,relative,text,revision):
    path=resolve(c,relative)
    if not editable(c,relative): raise ValueError('The document editor writes Markdown files only.')
    if not isinstance(text,str) or len(text.encode('utf-8'))>MAX_TEXT: raise ValueError('Note exceeds 2 MB')
    with cp.file_lock(c.vault/'.companion-editor.lock'):
        current=hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ''
        if current!=revision: raise FileExistsError('This file changed since you opened it. Reload before saving.')
        if path.exists():
            import uuid
            backup=c.vault/'.companion-editor-backups'/uuid.uuid4().hex
            cp.atomic_write(backup,path.read_text(encoding='utf-8'))
        cp.atomic_write(path,text)
    return read(c,relative)

def files(c,limit=20000):
    import os
    count=0
    for directory,dirs,names in os.walk(c.vault,followlinks=False):
        dirs[:]=[name for name in dirs if not name.startswith('.') and not (Path(directory)/name).is_symlink()]
        for name in names:
            candidate=Path(directory)/name
            if candidate.is_symlink():continue
            rel=candidate.relative_to(c.vault).as_posix()
            try:path=resolve(c,rel)
            except ValueError:continue
            if not path.is_file():continue
            count+=1
            if count>limit:raise ValueError(f'The vault has more than {limit:,} files; use the vault folder directly for a full export.')
            yield path,rel

def search(c,query):
    if not isinstance(query,str) or not 2<=len(query)<=200:raise ValueError('Search for 2–200 characters')
    matches=[];scanned=0;needle=query.casefold()
    for path,rel in files(c):
        if path.suffix.lower() not in TEXT or path.stat().st_size>MAX_TEXT:continue
        scanned+=1
        try:body=path.read_text(encoding='utf-8')
        except (OSError,UnicodeError):continue
        index=body.casefold().find(needle)
        if index>=0 or needle in rel.casefold():
            matches.append({'path':rel,'excerpt':body[max(0,index-80):max(0,index)+200]})
        if len(matches)>=50 or scanned>=2000:break
    return {'matches':matches,'scanned':scanned,'limited':len(matches)>=50 or scanned>=2000}
