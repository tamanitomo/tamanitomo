#!/usr/bin/env python3
"""One day, one plan, one place — and nothing else allowed to claim the day.

What a companion was doing on a given date could be asserted from three stores
at once: an intended day in `tomorrow.json`, a dated commitment inside her
presence record, and an event a person had entered. Nothing compared them. Only
one pair was ever checked against each other, so all three could be true at the
same time and the model blended them: she was going to the beach, and getting
her hair cut, and renewing her licence.

So: one file per date, holding one ordered timeline. Two items may not occupy
the same minutes. Adding something that would overlap is refused unless it names
the item it displaces, and the displacement is recorded with a reason. A plan
does not drift; it changes on purpose, visibly.

An item remembers which kind of thing it is, because "something I promised" and
"something I fancied doing" are not the same and she should be able to tell them
apart when a day gets crowded.
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, pathlib, sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
from companion_platform import atomic_write, file_lock

KINDS=('commitment','idea','person','anchor','other')
STATUSES=('planned','done','moved','dropped')
# Something promised outranks something fancied when a day will not hold both.
PRECEDENCE={'commitment':0,'person':1,'anchor':2,'idea':3,'other':4}
FOLDER='plans'


def folder(c):return pathlib.Path(c.life)/FOLDER


def path_for(c,day):
    day=_date(day)
    return folder(c)/f'{day.isoformat()}.json'


def _date(day):
    if isinstance(day,dt.datetime):return day.date()
    if isinstance(day,dt.date):return day
    return dt.date.fromisoformat(str(day))


def _minutes(value):
    """HH:MM to minutes past midnight, or None when it is not a time at all."""
    try:t=dt.time.fromisoformat(str(value))
    except (TypeError,ValueError):return None
    return t.hour*60+t.minute


def _item_id(item):
    seed=f"{item.get('start','')}|{item.get('what','')}|{item.get('ref','')}"
    return 'i-'+hashlib.sha256(seed.encode('utf-8')).hexdigest()[:12]


def clean_item(raw):
    """One entry, checked. A malformed item is refused rather than stored."""
    if not isinstance(raw,dict):raise ValueError('An item must be an object')
    what=str(raw.get('what') or '').strip()
    if not what:raise ValueError('An item needs a `what`')
    kind=raw.get('kind') or 'other'
    if kind not in KINDS:raise ValueError(f'Unknown kind {kind!r}; expected one of {list(KINDS)}')
    status=raw.get('status') or 'planned'
    if status not in STATUSES:raise ValueError(f'Unknown status {status!r}; expected one of {list(STATUSES)}')
    start,end=str(raw.get('start') or ''),str(raw.get('end') or '')
    a,b=_minutes(start),_minutes(end)
    if a is None or b is None:raise ValueError(f'{what!r} needs a start and end as HH:MM')
    if b<=a:raise ValueError(f'{what!r} ends before it starts')
    item={'id':str(raw.get('id') or '').strip() or _item_id(raw),
          'start':start,'end':end,'what':what[:160],
          'where':str(raw.get('where') or '')[:160],
          'kind':kind,'ref':str(raw.get('ref') or '')[:80],
          'status':status,'reason':str(raw.get('reason') or '')[:300]}
    return item


def overlaps(one,other):
    return (_minutes(one['start'])<_minutes(other['end'])
            and _minutes(other['start'])<_minutes(one['end']))


def conflicts(items,candidate,ignore=()):
    """Which planned items the candidate would sit on top of."""
    return [x for x in items
            if x['status']=='planned' and x['id']!=candidate['id']
            and x['id'] not in ignore and overlaps(x,candidate)]


def empty(day,author='companion'):
    return {'date':_date(day).isoformat(),'author':author,'intent':'','theme':'custom',
            'items':[],'history':[],'settled_at':None}


def read(c,day):
    path=path_for(c,day)
    if not path.is_file():return None
    try:data=json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):return None
    if not isinstance(data,dict):return None
    data.setdefault('items',[]);data.setdefault('history',[])
    data['items']=sorted((x for x in data['items'] if isinstance(x,dict) and x.get('what')),
                         key=lambda x:(_minutes(x.get('start')) or 0,PRECEDENCE.get(x.get('kind'),9)))
    return data


def _write(c,day,plan,note=None,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    plan=dict(plan)
    plan['date']=_date(day).isoformat()
    plan['items']=sorted((clean_item(x) for x in plan.get('items',[])),
                         key=lambda x:(_minutes(x['start']),PRECEDENCE.get(x['kind'],9)))
    # The invariant the whole file exists for.
    for index,item in enumerate(plan['items']):
        clash=conflicts(plan['items'][:index],item)
        if item['status']=='planned' and clash:
            raise ValueError(f"{item['what']!r} overlaps {clash[0]['what']!r}; "
                             'move or drop one of them rather than planning both')
    if note:
        plan.setdefault('history',[]).append({'at':now.isoformat(),'change':str(note)[:300]})
        plan['history']=plan['history'][-200:]
    path=path_for(c,day);path.parent.mkdir(parents=True,exist_ok=True)
    atomic_write(path,json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    return plan


def settle(c,day,intent,theme='custom',items=(),author='companion',now=None):
    """Write the day's plan. Replaces whatever was there, keeping its history."""
    now=now or dt.datetime.now(dt.timezone.utc)
    previous=read(c,day)
    plan=empty(day,author)
    if previous:plan['history']=previous.get('history',[])
    plan.update(intent=str(intent or '').strip()[:300],theme=str(theme or 'custom'),
                items=list(items),settled_at=now.isoformat())
    if not plan['intent']:raise ValueError('A day needs an intent written as a sentence')
    with file_lock(folder(c)/'.lock'):
        return _write(c,day,plan,f'settled: {plan["intent"][:120]}',now)


def add(c,day,item,displaces=None,now=None):
    """Put one thing in a day.

    Refused if it would sit on top of something already planned, unless it names
    what it displaces -- which is then moved aside, with the reason recorded. A
    day cannot quietly hold two things at once.
    """
    now=now or dt.datetime.now(dt.timezone.utc)
    with file_lock(folder(c)/'.lock'):
        plan=read(c,day) or empty(day)
        candidate=clean_item(item)
        clash=conflicts(plan['items'],candidate,ignore={displaces} if displaces else ())
        if clash:
            raise ValueError(f"{candidate['what']!r} overlaps {clash[0]['what']!r} "
                             f"({clash[0]['start']}–{clash[0]['end']}). Name what it displaces, "
                             'or choose another time.')
        note=f"added {candidate['what'][:80]}"
        if displaces:
            found=[x for x in plan['items'] if x['id']==displaces]
            if not found:raise ValueError(f'Nothing here called {displaces!r} to displace')
            found[0]['status']='moved'
            found[0]['reason']=(candidate.get('reason') or f"displaced by {candidate['what'][:80]}")[:300]
            note=f"{candidate['what'][:60]} displaced {found[0]['what'][:60]}"
        plan['items']=[x for x in plan['items'] if x['id']!=candidate['id']]+[candidate]
        return _write(c,day,plan,note,now)


def amend(c,day,item_id,status=None,reason=None,now=None):
    """Mark something done, moved or dropped. Nothing is deleted."""
    now=now or dt.datetime.now(dt.timezone.utc)
    with file_lock(folder(c)/'.lock'):
        plan=read(c,day)
        if not plan:raise ValueError('No plan for that day')
        found=[x for x in plan['items'] if x['id']==item_id]
        if not found:raise ValueError(f'Nothing here called {item_id!r}')
        if status:
            if status not in STATUSES:raise ValueError(f'Unknown status {status!r}')
            found[0]['status']=status
        if reason is not None:found[0]['reason']=str(reason)[:300]
        return _write(c,day,plan,f"{found[0]['what'][:60]} -> {found[0]['status']}",now)


def timeline(c,day,routine=None):
    """The day as it stands: what is planned, and what merely recurs.

    Routine anchors are not items. They are the shape the day would have had if
    nothing else were decided, and they are shown as such so a planned thing is
    never confused with a habit.
    """
    day=_date(day)
    plan=read(c,day)
    planned=[x for x in (plan or {}).get('items',[]) if x['status']=='planned']
    busy=[(_minutes(x['start']),_minutes(x['end'])) for x in planned]
    anchors=[]
    for row in (routine or []):
        a,b=_minutes(row.get('start')),_minutes(row.get('end'))
        if a is None or b is None:continue
        anchors.append({**row,'free':not any(a<end and start<b for start,end in busy)})
    return {'date':day.isoformat(),'settled':bool(plan and plan.get('settled_at')),
            'intent':(plan or {}).get('intent',''),'theme':(plan or {}).get('theme','custom'),
            'items':(plan or {}).get('items',[]),'planned':planned,'anchors':anchors,
            'history':(plan or {}).get('history',[])[-20:]}


def _local_hhmm(value,tz):
    try:when=dt.datetime.fromisoformat(str(value))
    except (TypeError,ValueError):return None,None
    if when.tzinfo is None:when=when.replace(tzinfo=tz)
    local=when.astimezone(tz)
    return local.date(),local.strftime('%H:%M')


def migrate(c,apply=False,now=None):
    """Gather the three stores that could each claim a day into one plan per day.

    `tomorrow.json` held one intended day. Presence held dated commitments. Both
    described the same dates and neither knew about the other. Nothing is thrown
    away here: a commitment keeps its kind, so she can still tell a thing she
    promised from a thing she fancied.
    """
    from zoneinfo import ZoneInfo
    import companion_life as life
    import companion_presence as presence
    tz=ZoneInfo(getattr(c,'timezone','UTC') or 'UTC')
    now=now or dt.datetime.now(tz)
    days={}

    plan=life.read_tomorrow_plan(c.life,now)
    if plan and plan.get('date'):
        try:day=_date(plan['date'])
        except ValueError:day=None
        if day:
            days.setdefault(day,{'intent':'','theme':'custom','items':[]})
            days[day]['intent']=str(plan.get('intent') or '')
            days[day]['theme']=str(plan.get('theme') or 'custom')
            anchors=plan.get('anchors') or []
            for row in anchors:
                if not isinstance(row,dict):continue
                days[day]['items'].append({'start':row.get('start'),'end':row.get('end'),
                    'what':row.get('activity') or row.get('what') or '',
                    'where':row.get('setting') or '','kind':'anchor','ref':'intended'})

    state=(presence.current(c) or {}).get('state',{})
    for row in state.get('commitments') or []:
        if not isinstance(row,dict):continue
        if row.get('status') not in (None,'planned'):continue
        day,start=_local_hhmm(row.get('starts_at'),tz)
        _,end=_local_hhmm(row.get('ends_at'),tz)
        if not day or not start:continue
        if not end:
            end=(dt.datetime.combine(day,dt.time.fromisoformat(start))+dt.timedelta(hours=1)).strftime('%H:%M')
        days.setdefault(day,{'intent':'','theme':'custom','items':[]})
        days[day]['items'].append({'start':start,'end':end,'what':row.get('title') or '',
            'where':'','kind':'commitment','ref':str(row.get('id') or ''),
            'reason':str(row.get('reason') or '')})

    report={'days':[],'written':0,'skipped':[]}
    for day in sorted(days):
        body=days[day]
        items=[]
        for raw in body['items']:
            try:items.append(clean_item(raw))
            except ValueError as exc:
                report['skipped'].append({'day':day.isoformat(),'why':str(exc)});continue
        # Place the promises first, then the whims. Merging in clock order let a
        # long idea starting earlier claim the hours a commitment needed, so the
        # haircut lost to the beach purely because the beach began at ten.
        items.sort(key=lambda x:(PRECEDENCE.get(x['kind'],9),_minutes(x['start'])))
        kept=[]
        for item in items:
            clash=conflicts(kept,item)
            if clash:
                item=dict(item,status='moved',
                          reason=f"overlapped {clash[0]['what'][:80]} when the plans were merged")
                report['skipped'].append({'day':day.isoformat(),
                    'why':f"{item['what'][:60]} moved aside; it overlapped {clash[0]['what'][:60]}"})
            kept.append(item)
        existing=read(c,day)
        if existing and existing.get('settled_at'):
            report['skipped'].append({'day':day.isoformat(),'why':'already has a settled plan; left alone'})
            continue
        report['days'].append({'date':day.isoformat(),'intent':body['intent'][:80],
            'items':[{'start':x['start'],'what':x['what'][:60],'kind':x['kind'],'status':x['status']}
                     for x in kept]})
        if apply:
            plan_out=empty(day)
            plan_out.update(intent=body['intent'] or 'a day carried over from the older plan files',
                            theme=body['theme'],items=kept,
                            settled_at=dt.datetime.now(dt.timezone.utc).isoformat())
            with file_lock(folder(c)/'.lock'):
                _write(c,day,plan_out,'migrated from tomorrow.json and presence commitments')
            report['written']+=1
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--home',type=pathlib.Path)
    p.add_argument('action',choices=('show','migrate'))
    p.add_argument('--day');p.add_argument('--apply',action='store_true')
    a=p.parse_args();c=cc.load(a.home)
    if a.action=='migrate':
        print(json.dumps(migrate(c,apply=a.apply),ensure_ascii=False,indent=2));return
    print(json.dumps(timeline(c,a.day or dt.date.today()),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
