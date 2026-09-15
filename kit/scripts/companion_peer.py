#!/usr/bin/env python3
"""Look at, and copy from, another agent on this machine — when asked to.

Agents are isolated by default: separate data trees, separate skills, separate
sessions. This tool is the deliberate exception. It is read-only on the peer and
writes only into the caller's own tree, it refuses anything that looks like a
credential, and it records every access so there is a trail.

It is never invoked automatically. An agent runs it because the human asked it to
look at, or borrow from, another agent.
"""
from __future__ import annotations
import argparse, datetime as dt, json, pathlib, re, shutil, sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc

MAX_READ=200_000
# Matched against a path's own segments, not as a substring of the whole path.
# "token" as a substring hid notes/tokenizer-comparison.md and skills/tokens-101.md
# from a peer that had every right to read them.
SECRET_NAMES=('.env','auth.json','.credentials','credentials','.netrc','id_rsa','.htpasswd',
              'secrets','tokens','token','secret','password','passwords')
SECRET_SUFFIXES=('.key','.pem','.p12','.pfx','.env')
# Singular only. A directory literally named "tokens" is caught by SECRET_NAMES;
# a file called tokens-101.md is a document about tokens and belongs to its owner.
SECRET_WORDS=('secret','token','credential','password','passwd','key','apikey')
SPLIT=re.compile(r'[^a-z0-9]+')

def is_secret(path:pathlib.Path)->bool:
    """True when some part of the path is itself a secret name, rather than merely
    containing one of these words inside a longer word."""
    parts=[p.lower() for p in pathlib.PurePath(path).parts]
    for part in parts:
        if part in SECRET_NAMES:return True
        if part.startswith('.env') or any(part.endswith(s) for s in SECRET_SUFFIXES):return True
        # A whole word inside a filename still counts: id_rsa, my-secret-note.txt.
        words=[w for w in SPLIT.split(part) if w]
        if any(w in SECRET_WORDS for w in words):return True
        # api_key and api-key split into two harmless-looking halves.
        if any(a+b in SECRET_WORDS for a,b in zip(words,words[1:])):return True
        if 'id' in words and 'rsa' in words:return True
    return False

def peers(c):
    """Every other agent under the same Hermes root."""
    out=[]
    root=c.hermes_root
    if c.profile and (root/'SOUL.md').exists():
        out.append(cc.load(root))
    pdir=root/'profiles'
    if pdir.is_dir():
        for d in sorted(pdir.iterdir()):
            if d.is_dir() and not d.is_symlink() and not d.name.startswith('.') and d.name!=c.profile:
                out.append(cc.load(d))
    return out

def find_peer(c,name):
    if not c.peer_interaction:raise ValueError('Peer interaction is switched off for this companion')
    name=(name or '').strip().lower()
    for p in peers(c):
        if (p.profile or 'root').lower()==name or p.agent.lower()==name:
            if not p.peer_interaction:raise ValueError('That companion has peer interaction switched off')
            return p
    raise ValueError(f'no peer agent named {name!r}; try: companion_peer.py list')

def roots(p):
    """What of a peer may be reached: their data tree and their skills."""
    return {'vault':p.data,'skills':p.home/'skills'}

def resolve_in(peer,rel):
    """Resolve <area>/<path> inside a peer, refusing escapes and secrets."""
    rel=(rel or '').strip().lstrip('/')
    area,_,rest=rel.partition('/')
    table=roots(peer)
    if area not in table:
        raise ValueError(f'path must start with one of {sorted(table)} (got {area!r})')
    base=table[area].resolve()
    target=(base/rest).resolve() if rest else base
    if target!=base and base not in target.parents:
        raise ValueError('path escapes the peer area')
    relative=target.relative_to(base)
    if area=='vault' and peer.is_root and relative.parts and relative.parts[0]=='agents':
        raise ValueError('Named agents must be accessed as their own peer, not through the root vault')
    if is_secret(relative):
        raise ValueError('refusing: that path looks like a credential store')
    return target

def log(c,action,detail):
    line={'at':dt.datetime.now().astimezone().isoformat(),'agent':c.agent,
          'action':action,'detail':detail}
    path=c.home/'peer-access.log'
    try:
        with path.open('a', encoding='utf-8') as f:f.write(json.dumps(line,ensure_ascii=False)+'\n')
    except OSError:pass

def cmd_list(c,a):
    return {'peers':[{'name':p.profile or 'root','agent':p.agent,
                      'vault':str(p.data),'skills':str(p.home/'skills'),
                      'readable':p.data.exists()} for p in peers(c)]}

def cmd_ls(c,a):
    p=find_peer(c,a.agent);target=resolve_in(p,a.path or 'vault')
    if not target.exists():raise ValueError(f'no such path: {target}')
    if target.is_file():
        entries=[{'name':target.name,'size':target.stat().st_size,'kind':'file'}]
    else:
        entries=[{'name':x.name+('/' if x.is_dir() else ''),
                  'size':(x.stat().st_size if x.is_file() else None),
                  'kind':'dir' if x.is_dir() else 'file'}
                 for x in sorted(target.iterdir()) if not x.is_symlink() and not is_secret(x.name) and not (p.is_root and target==p.data and x.name=='agents')][:400]
    log(c,'ls',str(target))
    return {'peer':p.profile or 'root','path':str(target),'entries':entries}

def cmd_read(c,a):
    p=find_peer(c,a.agent);target=resolve_in(p,a.path)
    if not target.is_file():raise ValueError('not a file')
    if target.stat().st_size>MAX_READ:
        raise ValueError(f'file is {target.stat().st_size} bytes; over the {MAX_READ} read cap')
    log(c,'read',str(target))
    return {'peer':p.profile or 'root','path':str(target),
            'note':"Another agent's material. Attribute it; do not adopt it as your own memory.",
            'content':target.read_text(encoding='utf-8',errors='replace')}

def cmd_copy(c,a):
    p=find_peer(c,a.agent);src=resolve_in(p,a.path)
    if not src.is_file():raise ValueError('only files can be copied')
    if src.stat().st_size>MAX_READ:raise ValueError('File exceeds copy size cap')
    area,_,rest=(a.dest or '').strip().lstrip('/').partition('/')
    mine={'vault':c.data,'skills':c.home/'skills'}
    if area not in mine:raise ValueError(f'--as must start with one of {sorted(mine)}')
    dest=((mine[area]/rest) if rest else (mine[area]/src.name)).resolve()
    base=mine[area].resolve()
    if dest!=base and base not in dest.parents:raise ValueError('destination escapes your own tree')
    relative=dest.relative_to(base)
    if is_secret(relative):raise ValueError('Refusing credential destination')
    if area=='vault' and c.is_root and relative.parts and relative.parts[0]=='agents':
        raise ValueError('Destination belongs to another agent')
    if dest==c.soul.resolve() or dest==c.canonical_soul.resolve():raise ValueError('Cannot overwrite identity through peer copy')
    if dest.exists() and not a.overwrite:
        raise ValueError(f'{dest} exists; pass --overwrite to replace it')
    dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(src,dest)
    log(c,'copy',f'{src} -> {dest}')
    return {'copied':str(src),'to':str(dest),
            'note':f"Borrowed from {p.agent}. Say so if you use it; it is not something you wrote."}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--home',type=pathlib.Path)
    s=ap.add_subparsers(dest='cmd',required=True)
    s.add_parser('list',help='which other agents exist here')
    l=s.add_parser('ls',help='list a path inside a peer (vault/... or skills/...)')
    l.add_argument('agent');l.add_argument('path',nargs='?')
    r=s.add_parser('read',help='read one file from a peer')
    r.add_argument('agent');r.add_argument('path')
    cp=s.add_parser('copy',help='copy one file from a peer into your own tree')
    cp.add_argument('agent');cp.add_argument('path')
    cp.add_argument('--as',dest='dest',required=True,help='vault/<path> or skills/<path>')
    cp.add_argument('--overwrite',action='store_true')
    a=ap.parse_args()
    c=cc.load(a.home)
    fn={'list':cmd_list,'ls':cmd_ls,'read':cmd_read,'copy':cmd_copy}[a.cmd]
    print(json.dumps(fn(c,a),ensure_ascii=False,indent=2))

if __name__=='__main__':
    try:main()
    except (ValueError,OSError) as e:
        print(json.dumps({'error':str(e)}),file=sys.stderr);sys.exit(1)
