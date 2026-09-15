#!/usr/bin/env python3
"""Append-only imagined-life ledger. Schedules are suggestions, never evidence.

Config-driven: paths and names come from companion_config, so this file contains
no agent name, no human name, and no absolute path.
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, os, pathlib, sys
from zoneinfo import ZoneInfo
from companion_platform import file_lock, atomic_write
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc

STATUSES=('planned','in_progress','completed','skipped')

def _tz(c):
    try:return ZoneInfo(c.timezone)
    except Exception:return ZoneInfo('UTC')

def read_events(root,day=None,limit=20,tz=None):
    """Daily files make today cheap; older history is requested explicitly."""
    tz=tz or ZoneInfo('UTC')
    day=day or dt.datetime.now(tz).date().isoformat()
    dt.date.fromisoformat(day)
    events=[]
    try:
        with (pathlib.Path(root)/'episodes'/f'{day}.jsonl').open(encoding='utf-8') as f:
            for line in f:
                line=line.strip()
                if not line:continue
                try:row=json.loads(line)
                except ValueError:continue
                if row.get('kind')=='imagined_episode':events.append(row)
    except FileNotFoundError:pass
    return events[-limit:] if limit else events

def history_page(root,day,offset=0,limit=8,compact=False,tz=None):
    """Page chronologically without hiding earlier episodes behind the latest N."""
    if offset<0 or not 1<=limit<=200:raise ValueError('offset must be nonnegative; limit must be 1–200')
    rows=read_events(root,day,limit=0,tz=tz)
    selected=rows[offset:offset+limit]
    if compact:
        selected=[{'id':r['id'],'recorded_at':r['recorded_at'],'activity':r['activity'],
                   'status':r['status'],'text':r['text'][:400],'text_truncated':len(r['text'])>400,
                   'location':r.get('state',{}).get('location'),
                   'mood':r.get('state',{}).get('mood'),
                   'confirmed':r.get('state',{}).get('confirmed',True),
                   'outfit':[x['id'] for x in r.get('state',{}).get('outfit',[])],
                   'care':r.get('state',{}).get('care',[])} for r in selected]
    end=offset+len(selected)
    return {'kind':'imagined_history','day':day,'total':len(rows),'offset':offset,
            'next_offset':end if end<len(rows) else None,'episodes':selected,
            'detail':'For full records, repeat this offset/limit without --compact.' if compact else ''}

def history_digest(root,day,offset=0,tz=None):
    """Mechanical excerpts of a whole day, bounded before tool-output spillover."""
    if offset<0:raise ValueError('offset must be nonnegative')
    rows=read_events(root,day,limit=0,tz=tz);entries=[];used=0
    for index,row in enumerate(rows[offset:offset+64],offset):
        state=row.get('state',{})
        excerpt={'offset':index,'time':row['recorded_at'][11:16],
                 'activity':row['activity'][:80],'mood':str(state.get('mood',''))[:80],
                 'text_excerpt':row['text'][:120],
                 'confirmed':state.get('confirmed',True)}
        prior=rows[index-1].get('state',{}) if index else {}
        if state.get('outfit')!=prior.get('outfit'):
            excerpt['outfit']=[item['id'] for item in state.get('outfit',[])]
        if state.get('care'):excerpt['care_excerpt']='; '.join(state['care'])[:160]
        size=len(json.dumps(excerpt,ensure_ascii=False))+80
        if entries and used+size>22000:break
        entries.append(excerpt);used+=size
    end=offset+len(entries)
    return {'kind':'imagined_history_digest','day':day,'total':len(rows),'offset':offset,
            'next_offset':end if end<len(rows) else None,'episodes':entries,
            'detail':'These are shortened excerpts, not a new summary or evidence of human exchanges. '
                     'For a full episode use history --day '+day+' --offset <its offset> --limit 1.'}

def save_tomorrow_plan(root,plan):
    root=pathlib.Path(root)
    path=root/'tomorrow.json'
    atomic_write(path,json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    return plan

def read_tomorrow_plan(root,now=None):
    root=pathlib.Path(root)
    path=root/'tomorrow.json'
    if not path.exists():return None
    try:
        data=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data,dict) or not data.get('intent'):return None
        if now:
            today_str=now.date().isoformat()
            tomorrow_str=(now.date()+dt.timedelta(days=1)).isoformat()
            plan_date=data.get('date')
            if plan_date and plan_date not in (today_str,tomorrow_str):return None
        return data
    except (ValueError,OSError):return None

def routine(root,now,agent='the companion'):
    root=pathlib.Path(root)
    try:data=json.loads((root/'routine.json').read_text(encoding='utf-8'))
    except FileNotFoundError:return {'status':'no routine configured','active_suggestions':[],
                                     'later_today':[],'recurring_cast':[],'current_books':[]}
    if data.get('kind')!='imagined_routine':raise ValueError('routine must be imagined_routine')
    today=('monday','tuesday','wednesday','thursday','friday','saturday','sunday')[now.weekday()];minute=now.hour*60+now.minute
    def mins(value):
        """None for anything unparseable. A hand-edited routine entry missing its
        start or end used to raise straight through the context hook, taking the
        whole injection with it over one malformed line."""
        try:t=dt.time.fromisoformat(str(value))
        except (ValueError,TypeError):return None
        return t.hour*60+t.minute
    plan=read_tomorrow_plan(root,now)
    catalog=data.get('routines_catalog',{})
    if plan and plan.get('anchors'):
        items=[dict(x,id=x.get('id',f'intended-{i}')) for i,x in enumerate(plan['anchors']) if isinstance(x,dict)]
    elif plan and plan.get('theme') in catalog:
        chosen_anchors=catalog[plan['theme']].get('anchors',[])
        items=[dict(x,id=f"intended-{i}") for i,x in enumerate(chosen_anchors)]
    else:
        items=[dict(x,id=x.get('id',f'weekly-{i}')) for i,x in enumerate(data.get('weekly',[])) if isinstance(x,dict) and x.get('day')==today]
        items += [dict(x,id=x.get('id',f'daily-{i}')) for i,x in enumerate(data.get('daily',[])) if isinstance(x,dict)]
    windows=[(x,mins(x.get('start')),mins(x.get('end'))) for x in items]
    malformed=[x.get('activity') or '(unnamed)' for x,a,b in windows if a is None or b is None]
    windows=[(x,a,b) for x,a,b in windows if a is not None and b is not None]
    return {'kind':'suggestions_not_completed_events','local_time':now.isoformat(),
            'active_suggestions':[x for x,a,b in windows if a<=minute<b],
            'later_today':[x for x,a,b in windows if a>minute],
            'earlier_today':[x for x,a,b in windows if b<=minute],
            'preferred_rhythm':data.get('preferred_rhythm',''),
            'intended_plan':plan,
            **({'malformed_entries':malformed} if malformed else {}),
            'guidance':data.get('guidance',''),
            'recurring_cast':data.get('recurring_cast',[]),
            'current_books':data.get('current_books',[]),
            'routines_catalog':catalog}

def record(root,text,activity,status,now,event_id=None,agent='companion',human='the human',*,state=None):
    root=pathlib.Path(root)
    if now.tzinfo is None:raise ValueError('timezone required')
    if status not in STATUSES:raise ValueError(f'status must be one of {STATUSES}')
    text=(text or '').strip();activity=(activity or '').strip()
    if not text or len(text)>1600 or not activity or len(activity)>120:
        raise ValueError('episode requires a concise activity and text')
    slot=now.replace(minute=now.minute//15*15,second=0,microsecond=0).isoformat()
    # A retried pulse cannot manufacture a second episode. No backdating from the CLI.
    event_id=event_id or 'pulse-'+hashlib.sha256(slot.encode()).hexdigest()[:20]
    if len(event_id)>100 or not all(ch.isalnum() or ch in '-_.' for ch in event_id):
        raise ValueError('invalid id')
    episode={'id':event_id,'kind':'imagined_episode','subject':agent,
             'recorded_at':now.isoformat(),'status':status,'activity':activity,'text':text,
             'provenance':f'Authored by {agent} as companion fiction; not evidence about {human} or physical events'}
    if state is not None:episode['state']=state
    folder=root/'episodes';folder.mkdir(parents=True,exist_ok=True)
    path=folder/f'{now.date().isoformat()}.jsonl'
    with file_lock((folder/'.write.lock')):
        for e in read_events(root,now.date().isoformat(),limit=0):
            if e['id']==event_id:
                if (e['text'],e['activity'],e['status'],e.get('state'))!=(text,activity,status,state):
                    raise ValueError('id already exists with different content; original retained')
                return {'written':False,'episode':e}
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
        with os.fdopen(fd,'a', encoding='utf-8') as f:
            f.write(json.dumps(episode,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
    return {'written':True,'episode':episode}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--home',type=pathlib.Path,help='companion home (default: $COMPANION_HOME/$HERMES_HOME)')
    s=p.add_subparsers(dest='cmd',required=True)
    s.add_parser('tick')
    s.add_parser('dates',help='Local today and yesterday, portable across operating systems')
    h=s.add_parser('history');h.add_argument('--day');h.add_argument('--limit',type=int,default=20)
    h.add_argument('--offset',type=int,help='Read a chronological page instead of the latest N')
    h.add_argument('--compact',action='store_true',help='Short, paged records for model context')
    h.add_argument('--digest',action='store_true',help='Bounded chronological excerpts, up to 64 per page')
    r=s.add_parser('record')
    r.add_argument('--activity',required=True);r.add_argument('--status',choices=STATUSES,required=True)
    text_input=r.add_mutually_exclusive_group()
    text_input.add_argument('--text',help='read from stdin if omitted')
    text_input.add_argument('--text-file',type=pathlib.Path,help='Read literal UTF-8 prose from a file')
    r.add_argument('--id')
    pt=s.add_parser('plan-tomorrow',help='Author intended routine and lay out clothes for tomorrow')
    pt.add_argument('--intent',required=True,help='Loose intention for tomorrow')
    pt.add_argument('--outfit',help='Comma-separated clothing IDs to lay out for tomorrow')
    pt.add_argument('--theme',default='custom',help='Theme or routine archetype name (or custom)')
    pt.add_argument('--anchors-file',type=pathlib.Path,help='Optional JSON file with custom anchors list')
    pt.add_argument('--notes',default='',help='Personal reflections or notes for tomorrow')
    s.add_parser('planned-tomorrow',help='Read the active intended plan and laid-out clothes')
    a=p.parse_args()
    c=cc.load(a.home);tz=_tz(c);now=dt.datetime.now(tz);root=c.life
    if a.cmd=='dates':out={'today':now.date().isoformat(),'yesterday':(now.date()-dt.timedelta(days=1)).isoformat(),'timezone':c.timezone}
    elif a.cmd=='plan-tomorrow':
        target_date=(now.date()+dt.timedelta(days=1)).isoformat()
        outfit_list=[x.strip() for x in (a.outfit or '').split(',') if x.strip()]
        custom_anchors=[]
        if a.anchors_file and a.anchors_file.exists():
            try:
                ad=json.loads(a.anchors_file.read_text(encoding='utf-8'))
                if isinstance(ad,list):custom_anchors=ad
                elif isinstance(ad,dict) and 'anchors' in ad:custom_anchors=ad['anchors']
            except Exception:pass
        plan_dict={
            'date':target_date,'created_at':now.isoformat(),
            'intent':a.intent,'laid_out_outfit':outfit_list,
            'theme':a.theme,'notes':a.notes or ''}
        if custom_anchors:plan_dict['anchors']=custom_anchors
        out=save_tomorrow_plan(root,plan_dict)
    elif a.cmd=='planned-tomorrow':
        out=read_tomorrow_plan(root,now) or {'status':'no plan recorded yet'}
    elif a.cmd=='tick':
        from companion_presence import current
        out={'current_state':current(c),'routine':routine(root,now,c.agent),'recent_episodes':read_events(root,limit=4,tz=tz),
             'instruction':('Confirm the current outfit, setting and activity through companion_presence.py. '
                            'Continue unchanged scenes briefly; record meaningful transitions without sending tick messages.')}
    elif a.cmd=='history':
        if a.digest:
            out=history_digest(root,a.day or now.date().isoformat(),a.offset or 0,tz)
        elif a.compact or a.offset is not None:
            out=history_page(root,a.day or now.date().isoformat(),a.offset or 0,
                             min(a.limit,8) if a.compact else a.limit,a.compact,tz)
        else:
            out={'kind':'imagined_history','day':a.day or now.date().isoformat(),
                 'episodes':read_events(root,a.day,min(max(a.limit,1),200),tz=tz)}
    else:
        text=a.text if a.text is not None else (a.text_file.read_text(encoding='utf-8') if a.text_file else sys.stdin.read(2000))
        out=record(root,text,
                   a.activity,a.status,now,a.id,c.agent,c.human)
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,json.JSONDecodeError) as e:
        print(json.dumps({'error':str(e)}),file=sys.stderr);sys.exit(1)
