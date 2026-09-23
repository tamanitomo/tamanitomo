#!/usr/bin/env python3
"""A map of the vault: every note by name, and the sections inside as many of
them as the window can carry.

Without it an agent only knows the files something else happens to mention, and
"is there a note about X" becomes a guess. With it she can see the whole shape
of what she keeps and open the right file directly.

It is sent once per session, not once per turn. Hermes replays each turn's
injected context with the history, so a map sent every turn would be carried N
times over; sent once it rides in the cached prefix like a context file. The
hook looks for its own marker in the history and sends the map again only when
it is missing: the first turn, and the first turn after compression summarised
it away.

Tiering is by budget, never by folder name. Names come first, because a file
she cannot see cannot be opened. If even names overrun, the biggest folders
fold into a count with the command that lists them. Whatever room is left goes
to section headings, most recently changed notes first, since that is where
the living material is.
"""
from __future__ import annotations
import argparse, datetime as dt, json, os, pathlib, re, sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
from companion_platform import atomic_write

BEGIN='<!-- tamanitomo:vault-index:begin -->'
END='<!-- tamanitomo:vault-index:end -->'
# Rebuilt at most this often; a session start reads the cache in between.
FRESH_SECONDS=15*60
HEAD_BYTES=64_000
MAX_HEADINGS=6
HEADING_CHARS=48
HEADING=re.compile(r'^(#{1,2})\s+(.+?)\s*#*\s*$')
FENCE=re.compile(r'^\s*(```|~~~)')

def budget_chars(c)->int:
    """Chars the map may occupy; 0 means switched off."""
    return cc.vault_index_cap(c.context_tokens,c.vault_index_tokens)

def _excluded(c)->set:
    return {str(p).strip('/') for p in (c.vault_index_exclude or []) if str(p).strip('/')}

def _prune(c,rel:str,name:str,excluded:set)->bool:
    """True when a directory must not be walked."""
    if name.startswith('.'):return True
    path=f'{rel}/{name}' if rel else name
    if path in excluded:return True
    # Another agent's private life is not this one's to map. A profile sees its
    # own subtree; the root agent sees none of them.
    if rel=='agents' and name!=(c.profile or ''):return True
    return False

def headings(path:pathlib.Path)->list:
    try:
        with open(path,'rb') as fh:text=fh.read(HEAD_BYTES).decode('utf-8','replace')
    except OSError:return []
    out=[];fenced=False
    for line in text.splitlines():
        if FENCE.match(line):fenced=not fenced;continue
        if fenced:continue
        m=HEADING.match(line)
        if not m:continue
        h=m.group(2).strip()
        if len(h)>HEADING_CHARS:h=h[:HEADING_CHARS-1].rstrip()+'…'
        if h and h not in out:out.append(h)
        if len(out)>=MAX_HEADINGS:break
    return out

def scan(c)->list:
    """Every note under the vault as {dir, name, mtime, headings}."""
    root=c.vault;excluded=_excluded(c);notes=[]
    if not root.is_dir():return notes
    for dirpath,dirs,files in os.walk(root):
        rel=pathlib.Path(dirpath).relative_to(root).as_posix()
        rel='' if rel=='.' else rel
        dirs[:]=sorted(d for d in dirs if not _prune(c,rel,d,excluded))
        for f in sorted(files):
            if not f.lower().endswith('.md') or f.startswith('.'):continue
            p=pathlib.Path(dirpath)/f
            if f'{rel}/{f}'.strip('/') in excluded:continue
            try:mtime=p.stat().st_mtime
            except OSError:continue
            stem=f[:-3]
            hs=headings(p)
            # A lone title that only restates the file name says nothing.
            if len(hs)==1 and re.sub(r'[\W_]+','',hs[0].lower())==re.sub(r'[\W_]+','',stem.lower()):hs=[]
            notes.append({'dir':rel,'name':stem,'mtime':mtime,'headings':hs})
    return notes

def _line(note,with_headings):
    if with_headings and note['headings']:return '- '+note['name']+': '+' · '.join(note['headings'])
    return '- '+note['name']

def render(c,notes:list,budget:int,built:str='')->str:
    """The map, fitted to `budget` chars. Never silently partial: folded folders
    and notes shown without their sections are both counted in a notice."""
    dirs={}
    for n in notes:dirs.setdefault(n['dir'],[]).append(n)
    command=cc_command(c,'show')
    head=(f'[Vault index — {c.vault}: {len(notes)} notes in {len(dirs)} folders'
          +(f', built {built}' if built else '')+'. Each "- name" is <folder>/<name>.md; after ":" are its '
          'sections. Open any of them with your file tools. This map is a snapshot from the start of the '
          f'session: {command} [folder] lists the current state]')
    with_sections=sum(1 for n in notes if n['headings'])
    def compose(folded,shown):
        notice=[]
        if folded:notice.append(f'{len(folded)} folder(s) folded to a count')
        missing=sum(1 for n in notes if n['headings'] and id(n) not in shown and n['dir'] not in folded)
        if missing:notice.append(f'sections omitted for {missing} of {with_sections} notes (oldest first)')
        out=[head]
        if notice:out.append('[Partial for space, nothing hidden: '+'; '.join(notice)+'. The show command above lists any folder in full.]')
        for d in sorted(dirs):
            ns=dirs[d];out.append(f'{d or "(vault root)"}/ ({len(ns)})')
            if d in folded:out.append(f'- ({len(ns)} notes not listed for space: show {d or "."})')
            else:out.extend(_line(n,id(n) in shown) for n in ns)
        return '\n'.join(out)
    folded=set()
    # Fold the biggest folders first until names alone fit. Deeper wins a tie:
    # a nested archive is a better thing to fold than a top-level folder.
    while len(compose(folded,set()))>budget and len(folded)<len(dirs):
        folded.add(max((d for d in dirs if d not in folded),key=lambda d:(len(dirs[d]),d.count('/'))))
    if len(compose(folded,set()))>budget:
        # Too small a window for even folded folders: a tree of folder counts,
        # as deep as fits. Still a map, just a coarser one.
        def tree(depth):
            counts={}
            for d,ns in dirs.items():
                key='/'.join(d.split('/')[:depth]) if d else ''
                counts[key]=counts.get(key,0)+len(ns)
            return [f'- {k or "(vault root)"}/ ({v})' for k,v in sorted(counts.items())]
        note='[Folder note counts only for space; deepest shown include their subfolders. The show command above lists inside.]'
        depth=max((d.count('/')+1 for d in dirs if d),default=1)
        while depth>1 and len('\n'.join([head,note,*tree(depth)]))>budget:depth-=1
        return '\n'.join([head,note,*tree(depth)])[:max(budget,len(head))]
    candidates=[n for n in sorted(notes,key=lambda n:-n['mtime']) if n['headings'] and n['dir'] not in folded]
    text=compose(folded,{id(n) for n in candidates})
    if len(text)<=budget:return text
    # Sections, newest notes first, into whatever room names left. The base
    # already carries the notice at its longest, so every step stays in budget.
    total=len(compose(folded,set()));shown=set()
    for n in candidates:
        extra=len(_line(n,True))-len(_line(n,False))
        if total+extra<=budget:shown.add(id(n));total+=extra
    return compose(folded,shown)

def cc_command(c,action:str)->str:
    try:
        from companion_platform import terminal_python_command
        return terminal_python_command(pathlib.Path(__file__),'--home',c.home,action)
    except Exception:
        return f'companion_vault_index.py {action}'

def cache_path(c)->pathlib.Path:return c.home/'cache'/'vault-index.json'

def build(c,force:bool=False)->str:
    """The fitted map, from cache when fresh and built for the same budget."""
    budget=budget_chars(c)
    if budget<=0:return ''
    path=cache_path(c)
    try:
        cached=json.loads(path.read_text(encoding='utf-8'))
        age=dt.datetime.now().timestamp()-float(cached['built_at'])
        if not force and cached.get('budget')==budget and cached.get('vault')==str(c.vault) and 0<=age<FRESH_SECONDS:
            return cached['text']
    except (OSError,ValueError,KeyError,TypeError):pass
    now=dt.datetime.now().astimezone()
    text=render(c,scan(c),budget,now.strftime('%Y-%m-%d %H:%M'))
    try:
        path.parent.mkdir(parents=True,exist_ok=True)
        atomic_write(path,json.dumps({'built_at':now.timestamp(),'budget':budget,'vault':str(c.vault),'text':text},
                                     ensure_ascii=False))
    except OSError:pass
    return text

def in_history(history)->bool:
    """Whether a turn this session already carried the map."""
    for row in history or []:
        if isinstance(row,dict) and row.get('role')=='user':
            for key in ('api_content','content'):
                v=row.get(key)
                if isinstance(v,str) and BEGIN in v:return True
    return False

def for_prompt(c,payload)->str:
    """The fenced map when this turn should carry it, else ''."""
    if budget_chars(c)<=0:return ''
    extra=(payload or {}).get('extra') if isinstance(payload,dict) else None
    history=extra.get('conversation_history') if isinstance(extra,dict) else None
    if in_history(history):return ''
    text=build(c)
    return BEGIN+'\n'+text+'\n'+END if text else ''

def show(c,folder:str='')->str:
    """Unbudgeted listing of one folder (recursive), with every note's sections."""
    folder=folder.strip().strip('/')
    if folder=='.':folder=''
    notes=[n for n in scan(c) if not folder or n['dir']==folder or n['dir'].startswith(folder+'/')]
    if not notes:return f'No notes under {folder or "the vault root"}.'
    out=[];last=None
    for n in notes:
        if n['dir']!=last:out.append(f'{n["dir"] or "(vault root)"}/');last=n['dir']
        out.append(_line(n,True))
    return '\n'.join(out)

def main():
    p=argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    p.add_argument('--home',type=pathlib.Path)
    sub=p.add_subparsers(dest='cmd',required=True)
    sub.add_parser('build',help='rebuild the cached map and print it')
    s=sub.add_parser('show',help='list a folder with every note and its sections');s.add_argument('folder',nargs='?',default='')
    sub.add_parser('stats',help='size of the map against its budget')
    a=p.parse_args()
    c=cc.load(a.home)
    if a.cmd=='build':print(build(c,force=True) or 'Vault index is switched off (vault_index_tokens is 0).')
    elif a.cmd=='show':print(show(c,a.folder))
    else:
        notes=scan(c);text=build(c,force=True)
        print(json.dumps({'notes':len(notes),'with_sections':sum(1 for n in notes if n['headings']),
                          'budget_chars':budget_chars(c),'map_chars':len(text)},indent=1))

if __name__=='__main__':main()
