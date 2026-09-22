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
    """One entry, checked. A malformed item is refused rather than stored.

    `activity` and `setting` are accepted as names for `what` and `where`,
    because that is what routine anchors have always called them and a companion
    reads those all day. Asking her to use one vocabulary here and another there
    was our inconsistency, not hers. Times are never inferred: a plan without
    hours is the ambiguity this whole file exists to remove.
    """
    if not isinstance(raw,dict):raise ValueError('An item must be an object')
    what=str(raw.get('what') or raw.get('activity') or '').strip()
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
          'where':str(raw.get('where') or raw.get('setting') or '')[:160],
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


def read_for(root,day):
    """Read a plan from a life directory, for callers that hold a path not a companion."""
    path=pathlib.Path(root)/FOLDER/f'{_date(day).isoformat()}.json'
    if not path.is_file():return None
    try:data=json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):return None
    if not isinstance(data,dict):return None
    data.setdefault('items',[]);data.setdefault('history',[])
    data['items']=sorted((x for x in data['items'] if isinstance(x,dict) and x.get('what')),
                         key=lambda x:(_minutes(x.get('start')) or 0,PRECEDENCE.get(x.get('kind'),9)))
    return data


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


def reconcile(c,day=None,tz=None,now=None):
    """Retire commitments whose time has simply gone past.

    A day that is not lived exactly as written leaves items sitting at
    'planned' hours after their window closed -- a host asleep through the
    morning, a quiet stretch with no pulse, a person busy elsewhere. The plan
    then disagrees with the clock, and she reads her own morning walk at four in
    the afternoon as something still ahead of her, which is how a companion ends
    up talking about a thing that never happened as though it were about to.

    Nothing is deleted and nothing is marked done: an item nobody recorded is
    not an item anybody completed. It becomes 'moved' with the reason saying
    plainly that its time passed unrecorded, which is the truth and reads as one
    in the history. Only whole past windows are touched, so the thing she is in
    the middle of right now is left alone. Idempotent: a second sweep over the
    same day changes nothing.
    """
    from zoneinfo import ZoneInfo
    tz=tz or ZoneInfo(getattr(c,'timezone','UTC') or 'UTC')
    now=now or dt.datetime.now(tz)
    if now.tzinfo is None:now=now.replace(tzinfo=tz)
    local=now.astimezone(tz)
    day=_date(day or local.date())
    # Only today and the days behind it. Tomorrow's plan is not late.
    if day>local.date():return []
    cutoff=24*60 if day<local.date() else local.hour*60+local.minute
    with file_lock(folder(c)/'.lock'):
        plan=read(c,day)
        if not plan:return []
        stale=[]
        for item in plan['items']:
            end=_minutes(item.get('end'))
            if item.get('status')=='planned' and end is not None and end<=cutoff:
                item['status']='moved'
                item['reason']=(item.get('reason') or 'its time passed with nothing recorded against it')[:300]
                stale.append(item)
        if not stale:return []
        note=('past their window, unrecorded: '+', '.join(x['what'][:40] for x in stale[:4]))[:300]
        _write(c,day,plan,note,now)
        return stale


def displacements(c,day=None,limit=4):
    """What changed about today, in her own recorded reasons.

    The plan already records every displacement instead of quietly deleting the
    loser, and then nothing ever read it back. A moved item with a reason is
    exactly the kind of small, true, specific thing that makes a day sound
    lived -- "I pushed my walk to four to help with the deploy" -- so it belongs
    in the context she thinks with, not only in a file.
    """
    plan=read(c,day or dt.date.today())
    if not plan:return []
    out=[]
    for item in plan['items']:
        if item.get('status') not in ('moved','dropped'):continue
        out.append({'what':item.get('what',''),'start':item.get('start',''),
                    'end':item.get('end',''),'status':item['status'],
                    'reason':str(item.get('reason') or '').strip()})
    return out[-max(int(limit),1):]


def render_displacements(rows):
    """One short block for the prompt, or '' when the day went as written."""
    if not rows:return ''
    lines=[]
    for row in rows:
        verb='moved' if row['status']=='moved' else 'dropped'
        line=f"{row['what'][:80]} ({row['start']}–{row['end']}) was {verb}"
        if row['reason']:line+=': '+row['reason'][:120]
        lines.append(line+'.')
    return ('[How today actually went — your own changes, already recorded. '
            'Speak to these as things you did and decided, not as things that failed]\n'+'\n'.join(lines))


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


def sync_commitments(c,commitments,tz=None,now=None):
    """Fold the commitments on a presence record into the days they belong to.

    A commitment is how the model says "I have promised to be somewhere". It
    arrives on the presence record as a patch, which is a fine way to express a
    change and a poor place to keep one: it was a second store of dated plans
    that nothing compared against the first. The plan is the store; this is the
    channel.

    A promise displaces a whim, because that is what a promise is for, and the
    displacement is written into the day's history rather than happening quietly.
    Two promises in the same hours is a real conflict and is left for her to
    resolve -- code should not pick which one she breaks.
    """
    from zoneinfo import ZoneInfo
    tz=tz or ZoneInfo(getattr(c,'timezone','UTC') or 'UTC')
    now=now or dt.datetime.now(dt.timezone.utc)
    touched=[]
    for row in (commitments or []):
        if not isinstance(row,dict):continue
        day,start=_local_hhmm(row.get('starts_at'),tz)
        _,end=_local_hhmm(row.get('ends_at'),tz)
        if not day or not start:continue
        if not end:
            end=(dt.datetime.combine(day,dt.time.fromisoformat(start))+dt.timedelta(hours=1)).strftime('%H:%M')
        title=str(row.get('title') or '').strip()
        if not title:continue
        ref=str(row.get('id') or '')
        status=row.get('status') or 'planned'
        wanted='planned' if status=='planned' else ('done' if status=='completed' else 'dropped')
        try:
            candidate=clean_item({'start':start,'end':end,'what':title,'kind':'commitment',
                                  'ref':ref,'status':wanted,'reason':str(row.get('reason') or '')})
        except ValueError:
            continue
        with file_lock(folder(c)/'.lock'):
            plan=read(c,day) or empty(day)
            existing=[x for x in plan['items'] if x['kind']=='commitment' and ref and x['ref']==ref]
            if existing:
                existing[0].update(start=candidate['start'],end=candidate['end'],
                                   what=candidate['what'],status=candidate['status'],
                                   reason=candidate['reason'])
                note=f"{title[:60]} -> {candidate['status']}"
            else:
                clash=conflicts(plan['items'],candidate)
                promises=[x for x in clash if x['kind']=='commitment']
                if promises and wanted=='planned':
                    # Two things promised at once. Record it, do not choose.
                    candidate=dict(candidate,status='moved',
                        reason=f"clashes with {promises[0]['what'][:80]}; needs resolving")
                    note=f"{title[:50]} clashes with {promises[0]['what'][:50]}"
                else:
                    for other in clash:
                        other['status']='moved'
                        other['reason']=f'displaced by {title[:80]}, which was promised'
                    note=(f"{title[:60]} took the slot"+
                          (f", moving {clash[0]['what'][:50]}" if clash else ''))
                plan['items']=plan['items']+[candidate]
            if not plan.get('intent'):
                plan['intent']='a day with something promised in it'
            touched.append({'date':day.isoformat(),'what':title[:60],'note':note})
            _write(c,day,plan,note,now)
    return touched


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--home',type=pathlib.Path)
    p.add_argument('action',choices=('show','migrate','reconcile'))
    p.add_argument('--day');p.add_argument('--apply',action='store_true')
    a=p.parse_args();c=cc.load(a.home)
    if a.action=='migrate':
        print(json.dumps(migrate(c,apply=a.apply),ensure_ascii=False,indent=2));return
    if a.action=='reconcile':
        print(json.dumps(reconcile(c,a.day),ensure_ascii=False,indent=2));return
    print(json.dumps(timeline(c,a.day or dt.date.today()),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
