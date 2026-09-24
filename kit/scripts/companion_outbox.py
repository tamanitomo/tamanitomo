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
STATUSES=('queued','sent','expired','failed','withheld')     # what mark() may write
# Phase 1B C2 (PHASE1B_DESIGN.md 7): an attempt in progress, and what can end one.
# An entry in a PHASE is owned by exactly one attempt; only that attempt's guarded
# transition() moves it on, and a dispatcher that died mid-attempt is resolved by the
# next run under the run lock (companion_dispatch.recover).
PHASES=('dispatching','reserving_slot','slot_reserved','sending')
OUTCOMES=('sent','failed','unknown','withheld','expired','reservation_unresolved')
ALL_STATUSES=('queued',)+PHASES+OUTCOMES
DEFAULT_TTL_HOURS=8
# Hermes delivery platforms. A target is where a message goes, never who it is for:
# a model that wrote "target": "<the human's name>" queued messages Hermes could only
# refuse ("Unknown or unregistered plugin platform"), and they failed at send time.
PLATFORMS=('telegram','discord','slack','signal','whatsapp','matrix','weixin','feishu',
           'dingtalk','ntfy','simplex','qqbot','yuanbao','email','sms')

def check_target(value,human='the human'):
    """'telegram' when absent; a platform or platform:chat_id when given; else refused."""
    target=str(value or '').strip() or 'telegram'
    platform=target.split(':',1)[0].lower()
    if platform not in PLATFORMS or len(target)>80:
        raise ValueError(f'target must be a delivery platform such as "telegram", not a person. '
                         f'Leave target out and it reaches {human} on the usual channel.')
    return target
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
             'target':check_target(entry.get('target'),getattr(c,'human','the human')),
             'status':'queued','queued_at':now.isoformat()}
        return slf._append(path_for(c),row)

def mark(c,ident,status,detail='',now=None):
    """Decide a QUEUED entry by hand (or from older code). Guarded like every write here:
    an entry an attempt currently owns, or one already decided, is refused and unchanged."""
    now=now or dt.datetime.now(_tz(c))
    if status not in STATUSES:raise ValueError(f'status must be one of {STATUSES}')
    def guard():
        entry=current(c,ident)
        if entry is not None and entry['status']!='queued':
            return {'written':False,'refused':f"the message is {entry['status']}; only a queued message can be marked"}
        return None
    return slf._append(path_for(c),{'id':ident,'kind':'outbox_update','status':status,
                                    'detail':str(detail)[:300],'at':now.isoformat()},dedupe_id=False,guard=guard)

def current(c,ident):
    """The folded entry, or None."""
    return next((e for e in fold(c) if e.get('id')==ident),None)

def transition(c,ident,status,attempt,run_id,expect,now=None,detail='',**extra):
    """The guarded append of PHASE1B_DESIGN 7.2. Under the outbox lock, re-read the fold and
    write only if the entry's status is exactly `expect` and, from any phase, its current
    attempt is `attempt`. Otherwise nothing is written: {'written': False, 'refused': why}.
    A stale snapshot, a second dispatcher, or a late update for another attempt changes nothing."""
    if status not in ALL_STATUSES:raise ValueError(f'status must be one of {ALL_STATUSES}')
    if not attempt:raise ValueError('an attempt id is required')
    now=now or dt.datetime.now(_tz(c))
    def guard():
        entry=current(c,ident)
        if entry is None:return {'written':False,'refused':'no such message'}
        if entry['status']!=expect:return {'written':False,'refused':f"status is {entry['status']}, not {expect}"}
        if expect!='queued' and entry.get('attempt')!=attempt:
            return {'written':False,'refused':'the message belongs to a different attempt'}
        return None
    row={'id':ident,'kind':'outbox_update','status':status,'attempt':attempt,'run_id':run_id,
         'detail':str(detail)[:300],'at':now.isoformat(),**extra}
    return slf._append(path_for(c),row,dedupe_id=False,guard=guard)

def resolve_unknown(c,ident,attempt,outcome,delivery,run_id='reconciler',now=None,detail=''):
    """PHASE1B_DESIGN 7.4: an `unknown` outcome may be replaced only by the SAME attempt with
    positive evidence (a message_id or an explicit platform result). Nothing is ever resent."""
    if outcome not in ('sent','failed'):raise ValueError('a late outcome is sent or failed')
    delivery=dict(delivery or {})
    if not (delivery.get('message_id') or delivery.get('platform_result')):
        return {'written':False,'refused':'a late outcome needs evidence: a message_id or a platform result'}
    return transition(c,ident,outcome,attempt,run_id,'unknown',now,detail,delivery=delivery,late=True)

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
            # Attempt ownership follows the latest row (absent on pre-1B rows).
            item['attempt']=row.get('attempt');item['run_id']=row.get('run_id')
            for key in ('delivery','not_dispatched','release_reason','error_code'):
                item.pop(key,None)                       # never carried over from an earlier attempt
                if key in row:item[key]=row[key]
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
    l=s.add_parser('list');l.add_argument('--status',choices=list(ALL_STATUSES)+['all'],default='queued')
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
