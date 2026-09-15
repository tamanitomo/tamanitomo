#!/usr/bin/env python3
"""The queue every outbound message passes through, and nothing bypasses.

Deciding to say something and saying it are two different acts, and the second
one is where a limit can actually be enforced. The lesson is on the record: a
companion whose restraint lived only in a prompt sent the same pulse-tick
report four to six times a day for a week, held a backlog through quiet hours,
and then flushed the whole thing at ten past midnight.

So: a job may only ever *queue*. A dispatcher that runs without a model decides
whether anything leaves, one message at a time. Queue entries carry a priority,
an earliest time, and an expiry — and an expired message is dropped, never sent
late. Something worth saying at 9pm is not worth saying at 2am, and a backlog
delivered at once is the single most alarming thing a companion can do.

Append-only, like every ledger here: queueing appends an entry, every decision
about it appends another, and the current state is the fold.
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, pathlib, sys
from zoneinfo import ZoneInfo
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
from companion_platform import file_lock
import companion_self as slf

KINDS=('text','image','voice')
PRIORITIES=('normal','high')
STATUSES=('queued','sent','expired','failed','withheld')
DEFAULT_TTL_HOURS=8
MAX_QUEUED=20

def _tz(c):
    try:return ZoneInfo(c.timezone)
    except Exception:return ZoneInfo('UTC')

def path_for(c):return c.life/'outbox.jsonl'

def _iso(value,tz,label):
    if not value:return ''
    try:
        when=dt.datetime.fromisoformat(str(value))
        return (when if when.tzinfo else when.replace(tzinfo=tz)).isoformat()
    except ValueError:raise ValueError(f'{label} must be an ISO timestamp')

def queue(c,entry,now=None):
    """Put one message in the queue. Nothing is sent here."""
    now=now or dt.datetime.now(_tz(c));tz=_tz(c)
    kind=entry.get('kind','text')
    if kind not in KINDS:raise ValueError(f'kind must be one of {KINDS}')
    body=(entry.get('body') or '').strip()
    if not body:raise ValueError('body required')
    if len(body)>4000:raise ValueError('body must be at most 4000 characters')
    priority=entry.get('priority','normal')
    if priority not in PRIORITIES:raise ValueError(f'priority must be one of {PRIORITIES}')
    media=(entry.get('media_path') or '').strip()
    if kind in ('image','voice') and not media:
        raise ValueError(f'a {kind} needs media_path pointing at the file to send')
    if media and not pathlib.Path(media).is_absolute():
        raise ValueError('media_path must be absolute')
    ttl=entry.get('ttl_hours',DEFAULT_TTL_HOURS)
    if not isinstance(ttl,(int,float)) or not 0<ttl<=168:
        raise ValueError('ttl_hours must be a positive number of hours, at most a week')
    with file_lock(path_for(c).with_suffix('.jsonl.lock')):
        history=fold(c)
        waiting=[e for e in history if e['status']=='queued']
        if len(waiting)>=MAX_QUEUED:
            raise ValueError(f'{len(waiting)} messages are already waiting; the queue is full, '
                             f'which means nothing is going out and something is wrong')
        for prior in waiting:
            if prior.get('content')==kind and prior.get('body','').strip()==body.strip():
                return {'written':False,'entry':prior}
        row={'id':entry.get('id') or 'msg-'+hashlib.sha256(
                (body+kind+now.date().isoformat()).encode()).hexdigest()[:16],
             'kind':'outbox','content':kind,'body':body,'media_path':media,
             'priority':priority,'reason':(entry.get('reason') or '')[:200],
             'not_before':_iso(entry.get('not_before'),tz,'not_before'),
             'expires_at':(now+dt.timedelta(hours=ttl)).isoformat(),
             'target':(entry.get('target') or 'telegram')[:40],
             'status':'queued','queued_at':now.isoformat()}
        return slf._append(path_for(c),row)

def mark(c,ident,status,detail='',now=None):
    now=now or dt.datetime.now(_tz(c))
    if status not in STATUSES:raise ValueError(f'status must be one of {STATUSES}')
    return slf._append(path_for(c),{'id':ident,'kind':'outbox_update','status':status,
                                    'detail':str(detail)[:300],'at':now.isoformat()},dedupe_id=False)

def fold(c):
    """Current state of every message ever queued, oldest first."""
    latest={}
    for row in slf._read(path_for(c)):
        ident=row.get('id')
        if row.get('kind')=='outbox':latest.setdefault(ident,dict(row))
        elif row.get('kind')=='outbox_update' and ident in latest:
            item=latest[ident]
            item['status']=row.get('status',item['status'])
            item['decided_at']=row.get('at','')
            if row.get('detail'):item['detail']=row['detail']
    return sorted(latest.values(),key=lambda e:e['queued_at'])

def waiting(c,now=None):
    """Queued messages in the order a dispatcher should consider them."""
    now=now or dt.datetime.now(_tz(c))
    rows=[e for e in fold(c) if e['status']=='queued']
    order={'high':0,'normal':1}
    return sorted(rows,key=lambda e:(order.get(e['priority'],1),e['queued_at']))

def expired(entry,now):
    try:return dt.datetime.fromisoformat(entry['expires_at'])<now
    except (ValueError,KeyError):return False

def held_until(entry,now):
    if not entry.get('not_before'):return False
    try:return dt.datetime.fromisoformat(entry['not_before'])>now
    except ValueError:return False

def render(c,now=None):
    rows=waiting(c,now)
    if not rows:return ''
    return '\n'.join(f"- {e['content']}: {e['body'][:120]}"
                     +(f" (not before {e['not_before'][11:16]})" if e.get('not_before') else '')
                     for e in rows)

def batch(c,path,now=None):
    data=json.loads(pathlib.Path(path).read_text(encoding='utf-8'))
    if isinstance(data,dict) and 'entries' in data:data=data['entries']
    if isinstance(data,dict):data=[data]
    if not isinstance(data,list) or not data:raise ValueError('file must hold one message or a list of them')
    if len(data)>5:raise ValueError('queue at most five messages at once')
    out=[]
    for i,entry in enumerate(data):
        try:out.append({'index':i,'ok':True,'id':queue(c,entry,now)['entry']['id']})
        except (ValueError,OSError) as exc:
            out.append({'index':i,'ok':False,'error':str(exc)})
            return {'queued':sum(1 for r in out if r['ok']),'failed_at':i,'results':out}
    return {'queued':len(out),'failed_at':None,'results':out}

def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--home',type=pathlib.Path)
    s=p.add_subparsers(dest='cmd',required=True)
    q=s.add_parser('queue',help='queue one or more messages from a JSON file')
    q.add_argument('--file',type=pathlib.Path,required=True)
    l=s.add_parser('list');l.add_argument('--status',choices=list(STATUSES)+['all'],default='queued')
    d=s.add_parser('drop',help='withdraw a queued message');d.add_argument('--id',required=True)
    a=p.parse_args();c=cc.load(a.home)
    if a.cmd=='queue':out=batch(c,a.file)
    elif a.cmd=='drop':out=mark(c,a.id,'withheld','withdrawn by hand')
    else:
        rows=fold(c)
        out={'messages':rows if a.status=='all' else [r for r in rows if r['status']==a.status]}
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,json.JSONDecodeError) as e:
        print(json.dumps({'error':str(e)}),file=sys.stderr);sys.exit(1)
