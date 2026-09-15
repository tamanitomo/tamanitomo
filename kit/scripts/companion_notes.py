#!/usr/bin/env python3
"""Two ledgers that the facts ledger has no room for.

**Standing instructions.** Things the human has said about how to work with
them: "don't write my homework for me", "tell me the answer first and the
reasoning after", "never call me at work". These are not facts about a person,
they are rules for dealing with one, and they belong beside the person rather
than beside the memories. When people-sharing is on, every agent here reads the
same ones, which is the point: being told twice is being told you were not
listening.

**The relationship.** Milestones, nicknames that stuck, running jokes, rituals,
firsts. This is private to each companion by definition — it is what happened
between these two, not a fact about the human — and it is most of what makes a
companion feel like it has been there rather than been briefed.

Both are append-only, both fold updates onto originals, and both render into a
compact block the hook can carry every turn.
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, pathlib, sys
from zoneinfo import ZoneInfo
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
import companion_self as slf

# Relationship entries are typed so the render can group them; the types are the
# shapes a shared history actually takes.
MOMENT_KINDS=('milestone','nickname','joke','ritual','first','note')
STATUSES=('active','retired')

def _tz(c):
    try:return ZoneInfo(c.timezone)
    except Exception:return ZoneInfo('UTC')

def standing_path(c):return c.human_dir/'standing.jsonl'
def moments_path(c):return c.life/'relationship.jsonl'

def _text(value,limit,label,required=True):
    value=(value or '').strip()
    if required and not value:raise ValueError(f'{label} required')
    if len(value)>limit:raise ValueError(f'{label} must be at most {limit} characters')
    return value

# ---- standing instructions ----------------------------------------------
def add_standing(c,entry,now):
    instruction=_text(entry.get('instruction'),400,'instruction')
    row={'id':entry.get('id') or 'rule-'+hashlib.sha256(instruction.lower().encode()).hexdigest()[:16],
         'kind':'standing','instruction':instruction,
         # Evidence, like the facts ledger. A rule nobody actually stated is a
         # rule the companion invented for them, which is worse than no rule.
         'evidence':_text(entry.get('evidence'),600,'evidence'),
         'scope':_text(entry.get('scope'),120,'scope',required=False),
         'status':'active','recorded_at':now.isoformat()}
    return slf._append(standing_path(c),row)

def retire_standing(c,ident,reason,now):
    if not any(r.get('id')==ident for r in slf._read(standing_path(c),kind='standing')):
        raise ValueError('unknown standing instruction id')
    return slf._append(standing_path(c),{'id':ident,'kind':'standing_update','status':'retired',
        'reason':_text(reason,300,'reason',required=False),'updated_at':now.isoformat()},dedupe_id=False)

def standing(c,status='active'):
    latest={}
    for row in slf._read(standing_path(c)):
        ident=row.get('id')
        if row.get('kind')=='standing':latest.setdefault(ident,dict(row))
        elif row.get('kind')=='standing_update' and ident in latest:
            latest[ident]['status']=row.get('status','active')
            latest[ident]['updated_at']=row.get('updated_at','')
    rows=sorted(latest.values(),key=lambda r:r['recorded_at'])
    return [r for r in rows if r['status']==status] if status else rows

# ---- the relationship ----------------------------------------------------
def add_moment(c,entry,now):
    kind=entry.get('moment','note')
    if kind not in MOMENT_KINDS:raise ValueError(f'moment must be one of {MOMENT_KINDS}')
    text=_text(entry.get('text'),500,'text')
    row={'id':entry.get('id') or 'rel-'+hashlib.sha256((kind+text.lower()).encode()).hexdigest()[:16],
         'kind':'moment','moment':kind,'text':text,
         'happened_on':_text(entry.get('happened_on'),20,'happened_on',required=False),
         'status':'active','recorded_at':now.isoformat()}
    return slf._append(moments_path(c),row)

def retire_moment(c,ident,reason,now):
    """A nickname that stopped landing, a ritual you no longer keep.

    Retired, never deleted: what you used to call each other is part of the
    history even after it stops being true.
    """
    if not any(r.get('id')==ident for r in slf._read(moments_path(c),kind='moment')):
        raise ValueError('unknown relationship entry id')
    return slf._append(moments_path(c),{'id':ident,'kind':'moment_update','status':'retired',
        'reason':_text(reason,300,'reason',required=False),'updated_at':now.isoformat()},dedupe_id=False)

def moments(c,status='active',moment=None):
    latest={}
    for row in slf._read(moments_path(c)):
        ident=row.get('id')
        if row.get('kind')=='moment':latest.setdefault(ident,dict(row))
        elif row.get('kind')=='moment_update' and ident in latest:
            latest[ident]['status']=row.get('status','active')
            latest[ident]['updated_at']=row.get('updated_at','')
    rows=sorted(latest.values(),key=lambda r:r['recorded_at'])
    if status:rows=[r for r in rows if r['status']==status]
    if moment:rows=[r for r in rows if r['moment']==moment]
    return rows

# ---- rendering -----------------------------------------------------------
LABELS={'milestone':'Milestones','nickname':'What you call each other','joke':'Running jokes',
        'ritual':'Rituals','first':'Firsts','note':'Other'}

def render_standing(c,limit=2000):
    rows=standing(c)
    if not rows:return ''
    lines=[f'{r["instruction"]}'+(f" ({r['scope']})" if r.get('scope') else '') for r in rows]
    out='\n'.join('- '+line for line in lines)
    return out if len(out)<=limit else out[:limit].rsplit('\n',1)[0]+f'\n[+{len(rows)} in total — companion_notes.py standing]'

def render_relationship(c,limit=2000):
    rows=moments(c)
    if not rows:return ''
    grouped={}
    for row in rows:grouped.setdefault(row['moment'],[]).append(row)
    out=[]
    for kind in MOMENT_KINDS:
        if kind not in grouped:continue
        out.append(LABELS[kind]+':')
        for row in grouped[kind]:
            out.append('- '+row['text']+(f" ({row['happened_on']})" if row.get('happened_on') else ''))
    text='\n'.join(out)
    return text if len(text)<=limit else text[:limit].rsplit('\n',1)[0]+f'\n[+more — companion_notes.py relationship]'

def batch(c,path,now):
    """One JSON file holding either kind, the same shape as every other ledger."""
    data=json.loads(pathlib.Path(path).read_text(encoding='utf-8'))
    if isinstance(data,dict):data=data.get('entries')
    if not isinstance(data,list) or not data:raise ValueError('file must hold a list of entries')
    if len(data)>50:raise ValueError('at most 50 entries at once')
    results=[]
    for i,entry in enumerate(data):
        if not isinstance(entry,dict):raise ValueError('each entry must be a JSON object')
        try:
            if entry.get('kind')=='standing':out=add_standing(c,entry,now)
            elif entry.get('kind')=='moment':out=add_moment(c,entry,now)
            elif entry.get('kind')=='retire_standing':out=retire_standing(c,entry.get('id',''),entry.get('reason',''),now)
            elif entry.get('kind')=='retire_moment':out=retire_moment(c,entry.get('id',''),entry.get('reason',''),now)
            else:raise ValueError("kind must be standing, moment, retire_standing or retire_moment")
        except (ValueError,OSError,TypeError) as exc:
            results.append({'index':i,'ok':False,'error':str(exc)})
            return {'applied':sum(1 for r in results if r.get('ok')),'failed_at':i,'results':results}
        results.append({'index':i,'ok':True,'id':out['entry']['id'],'written':out['written']})
    return {'applied':len(results),'failed_at':None,'results':results}

def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--home',type=pathlib.Path)
    s=p.add_subparsers(dest='cmd',required=True)
    b=s.add_parser('add',help='add or retire entries from one JSON file')
    b.add_argument('--file',type=pathlib.Path,required=True)
    st=s.add_parser('standing');st.add_argument('--status',choices=list(STATUSES)+['all'],default='active')
    rl=s.add_parser('relationship');rl.add_argument('--status',choices=list(STATUSES)+['all'],default='active')
    rl.add_argument('--moment',choices=MOMENT_KINDS)
    s.add_parser('render')
    a=p.parse_args();c=cc.load(a.home);now=dt.datetime.now(_tz(c))
    if a.cmd=='add':out=batch(c,a.file,now)
    elif a.cmd=='standing':out={'standing':standing(c,None if a.status=='all' else a.status)}
    elif a.cmd=='relationship':
        out={'relationship':moments(c,None if a.status=='all' else a.status,a.moment)}
    else:out={'standing':render_standing(c),'relationship':render_relationship(c)}
    print(json.dumps(out,ensure_ascii=False,indent=2))
    if out.get('failed_at') is not None:sys.exit(1)

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,json.JSONDecodeError) as e:
        print(json.dumps({'error':str(e)}),file=sys.stderr);sys.exit(1)
