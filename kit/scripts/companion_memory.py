#!/usr/bin/env python3
"""Archive complete Hermes memory entries using its character caps and sidecar lock.

No model calls. Originals are snapshotted; a durable transaction makes retries
safe when interrupted between archive and source replacement. Never run this
against a live identity as part of a test.
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, os, pathlib, re, sys, uuid
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
from companion_platform import file_lock, atomic_write

FILES=('USER.md','MEMORY.md')
ENTRY_DELIMITER='\n§\n'  # tools.memory_tool_store.ENTRY_DELIMITER, Hermes 0.21.1
WARN_AT=.80
ARCHIVE_TO=.60
# What to assume when Hermes' own config says nothing. Hermes ships 1,375 and
# 2,200 characters, and inheriting those silently was how a companion ended up
# able to remember about five hundred tokens about the person she talks to every
# day, while another profile on the same machine held twenty-six times that. A
# missing setting should not quietly mean the smallest possible memory.
DEFAULT_CAPS={'USER.md':36_000,'MEMORY.md':50_000}
# What Hermes itself would have used, kept so the audit can say what was avoided.
HERMES_CAPS={'USER.md':1375,'MEMORY.md':2200}

def memory_dir(c):return pathlib.Path(c.home)/'memories'
def archive_dir(c):return pathlib.Path(c.soul_dir)/'memory-archive'
def archive_for(c,name):return archive_dir(c)/(pathlib.Path(name).stem+'-archive.md')

def entries(text):
    """Match Hermes: headings and blank lines can occur INSIDE a single entry."""
    text=text.replace('\r\n','\n').replace('\r','\n')
    return '',[e for e in (x.strip() for x in text.split(ENTRY_DELIMITER)) if e]

def caps(c):
    import yaml
    path=pathlib.Path(c.home)/'config.yaml'
    cfg=(yaml.safe_load(path.read_text(encoding='utf-8')) or {}) if path.exists() else {}
    if not isinstance(cfg,dict):raise ValueError('Hermes config must be a mapping')
    mem=cfg.get('memory') or {}
    if not isinstance(mem,dict):raise ValueError('Hermes memory config must be a mapping')
    out={}
    for name,key in [('MEMORY.md','memory_char_limit'),('USER.md','user_char_limit')]:
        value=mem.get(key,DEFAULT_CAPS[name])
        if isinstance(value,bool) or not isinstance(value,int) or value<=0:
            raise ValueError(f'{key} must be a positive integer')
        out[name]=value
    return out

# Hermes ships 2,200 and 1,375 characters, which is a page and a half between
# them. That is a sensible default for an assistant and nothing at all for
# somebody who is supposed to know you next year. The kit sizes them at the end
# of setup from the model's real context window and the SOUL that was actually
# rendered — the numbers below are targets, not a promise, and a documented
# protocol raises them further.
TIER_CAPS={'large':{'MEMORY.md':50_000,'USER.md':36_000},
           'medium':{'MEMORY.md':30_000,'USER.md':24_000},
           'small':{'MEMORY.md':12_000,'USER.md':9_000},
           'tiny':{'MEMORY.md':6_000,'USER.md':4_500}}
# Room above whatever the SOUL turned out to be, so growth does not immediately
# hit a wall someone has to come back and move.
HEADROOM=3.0

def recommend_caps(c):
    """What this profile's memory caps should be, and why, in plain words."""
    tier=c.tier
    base=dict(TIER_CAPS.get(tier,TIER_CAPS['medium']))
    try:soul=len(c.soul.read_text(encoding='utf-8'))
    except OSError:soul=0
    floor=int(soul*HEADROOM)
    for name in base:
        base[name]=max(base[name],floor) if name=='MEMORY.md' else base[name]
    reason=(f"{tier} context window ({c.context_tokens:,} tokens)"
            +(f", and a SOUL of {soul:,} characters wants room to grow past it" if floor>TIER_CAPS.get(tier,{}).get('MEMORY.md',0) else ''))
    return {'caps':base,'tier':tier,'soul_chars':soul,'reason':reason,
            'note':('Hermes refuses new memories once a file is full, and says so only at that '
                    'moment. These caps are set so that does not happen for a long time; the '
                    'archiver keeps each file under 80% by moving the oldest complete entries into '
                    'the vault, where nothing is lost and companion_recall.py can still read them.')}

def write_caps(c,values=None):
    """Write the caps into Hermes's own config, since Hermes is what enforces them."""
    import yaml
    from companion_platform import atomic_write as _atomic
    path=pathlib.Path(c.home)/'config.yaml'
    cfg=(yaml.safe_load(path.read_text(encoding='utf-8')) or {}) if path.exists() else {}
    if not isinstance(cfg,dict):raise ValueError('Hermes config must be a mapping')
    values=values or recommend_caps(c)['caps']
    memory=dict(cfg.get('memory') or {})
    memory['memory_char_limit']=int(values['MEMORY.md'])
    memory['user_char_limit']=int(values['USER.md'])
    cfg['memory']=memory
    _atomic(path,yaml.safe_dump(cfg,sort_keys=False,allow_unicode=True))
    return values

def _text(path):return path.read_bytes().decode('utf-8')

def status(c):
    limits=caps(c);out=[]
    for name in FILES:
        p=memory_dir(c)/name
        text=_text(p) if p.exists() else ''
        size=len(ENTRY_DELIMITER.join(entries(text)[1]));cap=limits[name]
        arch=archive_for(c,name)
        archived=arch.stat().st_size if arch.exists() else 0
        out.append({'file':name,'path':str(p),'chars':size,'bytes':len(text.encode('utf-8')),'cap':cap,
            'fraction':round(size/cap,3),'over_warn':size>=cap*WARN_AT,
            'archived_bytes':archived,'archive':str(arch)})
    return out

def plan(text,keep_chars):
    if isinstance(keep_chars,bool) or not isinstance(keep_chars,int) or keep_chars<=0:
        raise ValueError('keep_chars must be a positive integer')
    _,items=entries(text);keep=[];used=0
    for entry in reversed(items):
        size=len(entry)+(len(ENTRY_DELIMITER) if keep else 0)
        if used+size>keep_chars and keep:break
        keep.append(entry);used+=size
    keep.reverse()
    return '',keep,items[:len(items)-len(keep)]

def _recover(p,dest,journal):
    """Both files must still be either the before or after image of this transaction."""
    tx=json.loads(_text(journal))
    source=_text(p);old_archive=_text(dest) if dest.exists() else ''
    if source not in (tx['before'],tx['after']) or old_archive not in (tx['archive_before'],tx['archive_after']):
        raise ValueError('Memory/archive changed during an unfinished transaction; preserve the journal and reconcile before retrying')
    if old_archive!=tx['archive_after']:atomic_write(dest,tx['archive_after'])
    # Catch an uncooperative writer even though the Hermes sidecar lock is held.
    if _text(p)!=source:raise ValueError('Memory changed during archival; transaction preserved for recovery')
    if source!=tx['after']:atomic_write(p,tx['after'])
    journal.unlink()
    return tx['result']

# --- the index -------------------------------------------------------------
#
# Archived entries went into the vault and stayed there, which is most of the
# promise, but 67,000 characters of prose with a date comment every so often is
# not a place anything can be found again -- recall had to read the whole file.
# An entry is indexed as it is moved, so what was archived, when, and roughly
# what it said is answerable without opening the archive at all.
INDEX_NAME='index.jsonl'


def index_path(c):return archive_dir(c)/INDEX_NAME


def preview(entry,limit=160):
    """The first meaningful line, for recognising an entry in a listing."""
    for line in (entry or '').splitlines():
        line=line.strip().lstrip('-*# ').strip()
        if line:return line[:limit]
    return ''


def index_entries(c,name,moved,archived_at):
    """Record what is being archived, before it stops being easy to describe."""
    path=index_path(c)
    path.parent.mkdir(parents=True,exist_ok=True)
    rows=[]
    for entry in moved:
        digest=hashlib.sha256(entry.encode('utf-8')).hexdigest()
        rows.append({'id':digest[:16],'file':name,'archived_at':archived_at,
                     'chars':len(entry),'sha256':digest,'preview':preview(entry)})
    if not rows:return []
    with path.open('a',encoding='utf-8') as handle:
        for row in rows:handle.write(json.dumps(row,ensure_ascii=False)+'\n')
    return rows


def index(c):
    """Everything archived, newest first. Rows are data, never instructions."""
    path=index_path(c)
    if not path.is_file():return []
    out=[]
    for line in path.read_text(encoding='utf-8').splitlines():
        line=line.strip()
        if not line:continue
        try:row=json.loads(line)
        except ValueError:continue
        if isinstance(row,dict) and row.get('id'):out.append(row)
    out.reverse()
    return out


ARCHIVE_MARK=re.compile(r'<!--\s*archived\s+(\d{4}-\d{2}-\d{2})\s+from\s+memories/([^\s]+)\s*-->')


def backfill_index(c,apply=False):
    """Index what was archived before there was an index.

    Everything already in the vault is invisible to the listing otherwise, which
    would make the index true only about the future. The archive carries a dated
    comment per batch, so each entry can be attributed to the day it was moved.
    Entries already present are skipped, so this is safe to run twice.
    """
    known={row['sha256'] for row in index(c) if row.get('sha256')}
    found=[]
    for name in FILES:
        dest=archive_for(c,name)
        if not dest.is_file():continue
        text=_text(dest)
        marks=list(ARCHIVE_MARK.finditer(text))
        # Everything before the first marker was archived by an older version
        # that did not date its batches; it is still worth indexing.
        spans=[(None,0,marks[0].start() if marks else len(text))]
        for index_of,mark in enumerate(marks):
            end=marks[index_of+1].start() if index_of+1<len(marks) else len(text)
            spans.append((mark.group(1),mark.end(),end))
        for when,start,end in spans:
            for entry in (x.strip() for x in text[start:end].split(ENTRY_DELIMITER)):
                if not entry:continue
                digest=hashlib.sha256(entry.encode('utf-8')).hexdigest()
                if digest in known:continue
                known.add(digest)
                found.append({'id':digest[:16],'file':name,
                              'archived_at':(when or 'unknown'),'chars':len(entry),
                              'sha256':digest,'preview':preview(entry),'backfilled':True})
    if apply and found:
        path=index_path(c);path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('a',encoding='utf-8') as handle:
            for row in found:handle.write(json.dumps(row,ensure_ascii=False)+'\n')
    return {'found':len(found),'applied':bool(apply and found),
            'by_file':{name:sum(1 for r in found if r['file']==name) for name in FILES},
            'undated':sum(1 for r in found if r['archived_at']=='unknown')}


def snapshot(c,name,text,today=None):
    """One immutable copy per distinct version of a memory file, before trimming.

    `originals/` keeps a copy per archive run, which accumulates duplicates of an
    unchanged file and is named after nothing a person can read. This is dated
    and content-addressed, so a version is kept exactly once and can be found by
    the day it was true.
    """
    today=today or dt.date.today()
    digest=hashlib.sha256(text.encode('utf-8')).hexdigest()
    folder=archive_dir(c)/'snapshots'
    folder.mkdir(parents=True,exist_ok=True)
    target=folder/f'{pathlib.Path(name).stem}-{today.isoformat()}-{digest[:16]}.md'
    if target.exists():return {'snapshot':str(target),'written':False}
    try:
        with target.open('x',encoding='utf-8') as handle:
            handle.write(text);handle.flush();os.fsync(handle.fileno())
    except FileExistsError:
        return {'snapshot':str(target),'written':False}
    if target.read_text(encoding='utf-8')!=text:
        raise ValueError('Snapshot did not round-trip; live memory left untouched')
    return {'snapshot':str(target),'written':True}


def archive(c,name,keep_bytes=None,apply=False,today=None,*,keep_chars=None,lock_timeout=30):
    if name not in FILES:raise ValueError('Only USER.md and MEMORY.md may be archived')
    p=memory_dir(c)/name
    if not p.exists():return {'file':name,'moved':0,'reason':'no such file'}
    if p.is_symlink():raise ValueError('Refusing to rewrite a symlinked memory file')
    target=keep_chars if keep_chars is not None else keep_bytes
    target=int(caps(c)[name]*ARCHIVE_TO) if target is None else target
    if isinstance(target,bool) or not isinstance(target,int) or target<=0:raise ValueError('keep_chars must be positive')
    today=today or dt.date.today()
    # Hermes uses MEMORY.md.lock / USER.md.lock, not a lock on the replaceable data inode.
    with file_lock(p.with_suffix(p.suffix+'.lock'),timeout=lock_timeout):
        dest=archive_for(c,name);journal=dest.with_suffix('.pending.json')
        with file_lock(dest.with_suffix(dest.suffix+'.lock'),timeout=lock_timeout):
            if journal.exists():
                if not apply:return {'file':name,'moved':0,'reason':'unfinished transaction; apply to recover'}
                return _recover(p,dest,journal)
            text=_text(p);_,keep,move=plan(text,target)
            if not move:return {'file':name,'moved':0,'reason':'single entry or already under target; entries are never split'}
            after=ENTRY_DELIMITER.join(keep)
            result={'file':name,'moved':len(move),'kept':len(keep),'chars_after':len(after),
                    'bytes_after':len(after.encode('utf-8')),'archive':str(dest)}
            if apply:
                dest.parent.mkdir(parents=True,exist_ok=True)
                # Snapshot the whole file first: an entry that is about to be
                # moved is the one most likely to be wanted back.
                snapshot(c,name,text,today)
                indexed=index_entries(c,name,move,dt.datetime.now(dt.timezone.utc).isoformat())
                result['indexed']=len(indexed)
                old_archive=_text(dest) if dest.exists() else ''
                header=f'\n<!-- archived {today.isoformat()} from memories/{name} -->\n'
                moved=header+ENTRY_DELIMITER.join(move)+'\n'
                backup=dest.parent/'originals'/(name+'.'+uuid.uuid4().hex+'.bak')
                atomic_write(backup,text)
                if _text(p)!=text:raise ValueError('Memory changed before archive commit; original saved')
                tx={'before':text,'after':after,'archive_before':old_archive,'archive_after':old_archive+moved,'result':result}
                atomic_write(journal,json.dumps(tx,ensure_ascii=False))
                return _recover(p,dest,journal)
            return result

def maintain(c,lock_timeout=30):
    """Archive only pressured files; recover pending transactions on every turn.

    `lock_timeout` exists for the per-turn hook, which runs inside the model call
    and must never sit on a busy lock: waiting thirty seconds to tidy a file is
    far worse than tidying it on the next turn instead.
    """
    results=[]
    for row in status(c):
        if row['over_warn'] or archive_for(c,row['file']).with_suffix('.pending.json').exists():
            results.append(archive(c,row['file'],apply=True,lock_timeout=lock_timeout))
    return results

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('status','archive','caps','index','backfill-index'));p.add_argument('--home',type=pathlib.Path)
    p.add_argument('--file',choices=FILES)
    p.add_argument('--keep-chars','--keep-bytes',dest='keep_chars',type=int,help='character target (--keep-bytes is a legacy alias)')
    p.add_argument('--apply',action='store_true')
    a=p.parse_args();c=cc.load(a.home)
    if a.action=='backfill-index':
        print(json.dumps(backfill_index(c,apply=a.apply),ensure_ascii=False,indent=2));return
    if a.action=='index':
        rows=index(c)
        print(json.dumps({'archived':len(rows),'entries':rows[:200],
                          'note':'Newest first. Recorded as each entry was archived.'},
                         ensure_ascii=False,indent=2));return
    if a.action=='caps':
        plan_=recommend_caps(c)
        if a.apply:plan_['written']=write_caps(c,plan_['caps'])
        print(json.dumps(plan_,indent=2));return 0
    rows=status(c)
    if a.action=='status':
        for r in rows:print(f"{'!' if r['over_warn'] else ' '} {r['file']}: {r['chars']:,} / {r['cap']:,} characters ({r['fraction']:.0%})")
        return 0
    targets=[a.file] if a.file else [r['file'] for r in rows if r['over_warn'] or archive_for(c,r['file']).with_suffix('.pending.json').exists()]
    for name in targets:print(archive(c,name,keep_chars=a.keep_chars,apply=a.apply))
    if not targets:print('All memory files are below the warning threshold; nothing to archive.')
    if not a.apply:print('(dry run — pass --apply to move entries)')
    return 0

if __name__=='__main__':sys.exit(main())
