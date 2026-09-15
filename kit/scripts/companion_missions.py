#!/usr/bin/env python3
"""Things the human has asked for, waiting for a window in which to do them.

Not a task runner. The point is smaller and better than that: "research Airbnbs
for the weekend of the 28th", "find out whether that band is touring", "work out
what a replacement part costs". A companion that comes back with an answer
nobody had to chase is doing something a companion does; a companion that files
a status report is doing something else.

A mission is claimed before it is worked on and released if the work does not
finish, so two windows cannot quietly duplicate each other. Results come back
through the outbox like everything else, which means the dispatcher still
decides whether two in the morning is a reasonable time to hear about Airbnbs.
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, pathlib, sys
from zoneinfo import ZoneInfo
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
from companion_platform import file_lock
import companion_self as slf

STATUSES=('open','claimed','done','dropped')
CLAIM_EXPIRY_HOURS=6

def _tz(c):
    try:return ZoneInfo(c.timezone)
    except Exception:return ZoneInfo('UTC')

def path_for(c):return c.life/'missions.jsonl'

def _text(value,limit,label,required=True):
    value=(value or '').strip()
    if required and not value:raise ValueError(f'{label} required')
    if len(value)>limit:raise ValueError(f'{label} must be at most {limit} characters')
    return value

def add(c,entry,now):
    title=_text(entry.get('title'),200,'title')
    row={'id':entry.get('id') or 'mis-'+hashlib.sha256(title.lower().encode()).hexdigest()[:16],
         'kind':'mission','title':title,
         'detail':_text(entry.get('detail'),1500,'detail',required=False),
         'wanted_by':_text(entry.get('wanted_by'),20,'wanted_by',required=False),
         'status':'open','recorded_at':now.isoformat()}
    return slf._append(path_for(c),row)

def update(c,ident,status,detail='',now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    if status not in STATUSES:raise ValueError(f'status must be one of {STATUSES}')
    if not any(r.get('id')==ident for r in slf._read(path_for(c),kind='mission')):
        raise ValueError('unknown mission id')
    return slf._append(path_for(c),{'id':ident,'kind':'mission_update','status':status,
        'detail':_text(detail,1500,'detail',required=False),'updated_at':now.isoformat()},dedupe_id=False)

def missions(c,status='open',now=None):
    """Fold, and treat a stale claim as open again.

    A window that crashed halfway through a mission should not leave it claimed
    forever; six hours later it is simply unstarted work.
    """
    now=now or dt.datetime.now(_tz(c))
    latest={}
    for row in slf._read(path_for(c)):
        ident=row.get('id')
        if row.get('kind')=='mission':latest.setdefault(ident,dict(row))
        elif row.get('kind')=='mission_update' and ident in latest:
            item=latest[ident]
            item['status']=row.get('status',item['status'])
            item['updated_at']=row.get('updated_at','')
            if row.get('detail'):item['detail_update']=row['detail']
    rows=[]
    for item in latest.values():
        if item['status']=='claimed':
            try:since=(now-dt.datetime.fromisoformat(item.get('updated_at') or item['recorded_at'])).total_seconds()/3600
            except ValueError:since=0
            if since>CLAIM_EXPIRY_HOURS:
                item=dict(item,status='open',stale_claim=True)
        rows.append(item)
    rows.sort(key=lambda r:r['recorded_at'])
    return [r for r in rows if r['status']==status] if status else rows

def claim(c,now=None):
    """Take the oldest open mission, exclusively. Returns None when there is none."""
    now=now or dt.datetime.now(_tz(c))
    with file_lock(path_for(c).with_suffix('.jsonl.lock')):
        open_rows=missions(c,'open',now)
        if not open_rows:return None
        mission=open_rows[0]
        slf._append(path_for(c),{'id':mission['id'],'kind':'mission_update','status':'claimed',
            'detail':'','updated_at':now.isoformat()},dedupe_id=False)
        return {**mission,'status':'claimed'}

def render(c,now=None):
    rows=missions(c,'open',now)
    if not rows:return ''
    out=[]
    for row in rows:
        out.append(f"- {row['title']}"+(f" (wanted by {row['wanted_by']})" if row.get('wanted_by') else ''))
        if row.get('detail'):out.append(f"  {row['detail'][:300]}")
    return '\n'.join(out)

def batch(c,path,now):
    data=json.loads(pathlib.Path(path).read_text(encoding='utf-8'))
    if isinstance(data,dict):data=data.get('entries') or [data]
    if not isinstance(data,list) or not data:raise ValueError('file must hold a list of missions')
    if len(data)>20:raise ValueError('at most 20 missions at once')
    results=[]
    for i,entry in enumerate(data):
        try:
            if entry.get('kind')=='update':
                out=update(c,entry.get('id',''),entry.get('status','open'),entry.get('detail',''),now)
            else:out=add(c,entry,now)
        except (ValueError,OSError,TypeError) as exc:
            results.append({'index':i,'ok':False,'error':str(exc)})
            return {'applied':sum(1 for r in results if r.get('ok')),'failed_at':i,'results':results}
        results.append({'index':i,'ok':True,'id':out['entry']['id']})
    return {'applied':len(results),'failed_at':None,'results':results}

def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--home',type=pathlib.Path)
    s=p.add_subparsers(dest='cmd',required=True)
    a_=s.add_parser('add',help='add or update missions from one JSON file')
    a_.add_argument('--file',type=pathlib.Path,required=True)
    l=s.add_parser('list');l.add_argument('--status',choices=list(STATUSES)+['all'],default='open')
    s.add_parser('claim',help='take the oldest open mission for this window')
    d=s.add_parser('done');d.add_argument('--id',required=True);d.add_argument('--detail',default='')
    r=s.add_parser('release');r.add_argument('--id',required=True);r.add_argument('--detail',default='')
    a=p.parse_args();c=cc.load(a.home);now=dt.datetime.now(_tz(c))
    if a.cmd=='add':out=batch(c,a.file,now)
    elif a.cmd=='list':out={'missions':missions(c,None if a.status=='all' else a.status,now)}
    elif a.cmd=='claim':
        got=claim(c,now)
        out=got or {'claimed':None,'reason':'nothing open; this window is yours to spend on your own life'}
    elif a.cmd=='done':out=update(c,a.id,'done',a.detail,now)
    else:out=update(c,a.id,'open',a.detail or 'released without finishing',now)
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,json.JSONDecodeError) as e:
        print(json.dumps({'error':str(e)}),file=sys.stderr);sys.exit(1)
