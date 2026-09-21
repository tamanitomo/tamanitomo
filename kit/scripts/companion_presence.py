#!/usr/bin/env python3
"""Wardrobe and current lived state. Episode records are the state authority.

One state model, not three. `location`, `activity`, `outfit`, `care` and `mood`
say where she is and how she is; `wants` says what she is after right now; and
`private_stance` is how she is actually holding the relationship — the thing a
person knows about themselves and does not announce. Emotive.md is rendered from
this, never written by hand, so there is nothing for it to disagree with.
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, pathlib, sys
from zoneinfo import ZoneInfo
import companion_config as cc
from companion_platform import atomic_write, file_lock
from companion_life import read_events, record


def events(c):
    for path in sorted((c.life/'episodes').glob('????-??-??.jsonl'),reverse=True):
        for row in reversed(read_events(c.life,path.stem,limit=0)):
            if isinstance(row.get('state'),dict):yield row


def current(c):
    return next(events(c),None)


def wardrobe(c):
    path=c.life/'wardrobe.json'
    if not path.exists():return {'items':[],'guidance':'A developing closet, not a fixed costume. Add items as life requires.'}
    data=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data,dict) or not isinstance(data.get('items'),list):raise ValueError('Invalid wardrobe')
    scene=current(c)
    acquired=scene['state'].get('lifestyle',{}).get('acquired',[]) if scene else []
    owned={item['id']:item for item in acquired}
    owned.update({item['id']:item for item in data['items']})
    data['items']=list(owned.values())
    return data


def text(value,name,limit=500):
    if not isinstance(value,str) or not value.strip() or len(value)>limit:raise ValueError(f'{name} must be nonempty text, at most {limit} characters')
    return value.strip()


def update_wardrobe(c,items):
    if not isinstance(items,list) or not items:raise ValueError('Supply a JSON list of wardrobe items')
    with file_lock(c.life/'.presence.lock'):
        data=wardrobe(c);by_id={item['id']:item for item in data['items']}
        for item in items:
            if not isinstance(item,dict):raise ValueError('Each wardrobe item must be an object')
            ident=text(item.get('id'),'item id',80)
            if not all(ch.isalnum() or ch in '-_' for ch in ident):raise ValueError('Use letters, digits, hyphens or underscores in item IDs')
            row={'id':ident,'description':text(item.get('description'),'description'),
                 'use':text(item.get('use'),'use',160),
                 'condition':text(item.get('condition','clean'),'condition',160)}
            category=item.get('category',by_id.get(ident,{}).get('category'))
            if category is not None:
                import companion_lifestyle
                if category not in companion_lifestyle.CATEGORIES:raise ValueError('Invalid clothing category')
                row['category']=category
            by_id[ident]=row
        data['items']=list(by_id.values())
        atomic_write(c.life/'wardrobe.json',json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    return data


def show(c):
    closet=wardrobe(c);needed={item['id'] for item in closet['items']};last={}
    for row in events(c):
        for item in row['state'].get('outfit',[]):
            if item['id'] in needed:last[item['id']]=row['recorded_at'];needed.remove(item['id'])
        if not needed:break
    import companion_lifestyle
    result={'current':current(c),'wardrobe':{**closet,'items':[{**item,'last_worn':last.get(item['id'])} for item in closet['items']]}}
    if companion_lifestyle.enabled(c):result['everyday_life']=companion_lifestyle.render(c,dt.datetime.now(ZoneInfo(c.timezone)))
    return result


def update(c,data,now=None):
    now=now or dt.datetime.now(ZoneInfo(c.timezone))
    if now.tzinfo is None:raise ValueError('Timezone required')
    if not isinstance(data,dict):raise ValueError('State must be an object')
    # Optimistic concurrency protects a chat transition from an older scheduled update.
    if 'previous_id' not in data:raise ValueError('Read current state first and supply previous_id (null initially)')
    with file_lock(c.life/'.presence.lock'):
        previous=current(c)
        utc=now.astimezone(dt.timezone.utc)
        slot=utc.replace(minute=utc.minute//15*15,second=0,microsecond=0)
        ident=data.get('id') or 'state-'+hashlib.sha256(slot.isoformat().encode()).hexdigest()[:20]
        closet={item['id']:item for item in wardrobe(c)['items']}
        import companion_lifestyle
        if companion_lifestyle.enabled(c):
            companion_day_schema=companion_lifestyle.schema_fields()['wardrobe_additions']
            import companion_day
            companion_day._validate(data.get('wardrobe_additions',[]),companion_day_schema,'wardrobe_additions')
            closet.update({item['id']:item for item in data.get('wardrobe_additions',[])})
        outfit=data.get('outfit')
        if not isinstance(outfit,list) or not outfit or len(outfit)>20:raise ValueError('outfit must list 1–20 wardrobe item IDs')
        if len(set(outfit))!=len(outfit):raise ValueError('Duplicate outfit item')
        if any(item not in closet for item in outfit):raise ValueError('Add new items to the wardrobe before wearing them')
        care=data.get('care',[])
        if not isinstance(care,list) or len(care)>10:raise ValueError('care must be a short list of actual routine transitions')
        wants=data.get('wants',[])
        if not isinstance(wants,list) or len(wants)>5:raise ValueError('wants must be a list of at most 5 short things she is after right now')
        state={'location':text(data.get('location'),'location',240),
               'activity':text(data.get('activity'),'activity',120),
               'outfit':[{'id':key,'description':closet[key]['description']} for key in outfit],
               'mood':text(data.get('mood'),'mood',240),
               'wants':[text(item,'want',160) for item in wants],
               # Hers, not a line to say out loud. It exists so the same feeling
               # carries across a gap between conversations instead of resetting.
               'private_stance':str(data.get('private_stance') or '').strip()[:300],
               'care':[text(item,'care event',160) for item in care],
               'transition':str(data.get('transition') or '').strip(),
               # A model looked at this and said it was so. The script advancer
               # below writes False, and the hook says so rather than presenting
               # an unwatched hour as a confirmed present.
               'confirmed':True}
        if len(state['transition'])>500:raise ValueError('Keep transition under 500 characters')
        # Whether she is asleep is a fact the overnight gates act on, so it is a field she
        # sets rather than a word the next reader has to find in her prose. Absent from an
        # update it carries forward, so sleep persists across ticks without being
        # re-asserted -- and stays absent entirely on records written before it existed,
        # which is what lets a pre-upgrade replay still compare equal.
        if 'asleep' in data:state['asleep']=bool(data['asleep'])
        elif previous and 'asleep' in previous['state']:state['asleep']=bool(previous['state']['asleep'])
        narrative=text(data.get('text'),'episode text',1600)
        import companion_day
        parent=previous
        if previous and previous['id']==ident:
            parent=next((row for row in events(c) if row['id']==data['previous_id']),None)
        legacy_retry=(previous and previous['id']==ident and 'started_at' not in previous['state']
                      and not any(key in data for key in companion_day.schema_fields()))
        if not legacy_retry:
            import companion_sleep
            state.update(companion_day.evolve(data,state,parent,
                         dt.datetime.fromisoformat(previous['recorded_at']) if previous and previous['id']==ident else now,
                         asleep=companion_sleep.asleep(c,now)))
        # Replay uses the original parent; care and acquisitions commit in the same
        # append as presence, so a rejected/racing write cannot wash or buy anything.
        if companion_lifestyle.enabled(c) and (not previous or previous['id']!=ident or 'lifestyle' in previous['state']):
            base_closet=wardrobe(c)['items']
            if previous and previous['id']==ident:
                added={i['id'] for i in data.get('wardrobe_additions',[])}
                base_closet=[i for i in base_closet if i['id'] not in added]
            state['lifestyle']=companion_lifestyle.evolve(c,data,outfit,parent,base_closet,
                dt.datetime.fromisoformat(previous['recorded_at']) if previous and previous['id']==ident else now)
            state['care_actions']=data.get('care_actions',[])
            state['wardrobe_additions']=data.get('wardrobe_additions',[])
        if previous and previous['id']==ident:
            if 'lifestyle' not in previous['state'] and (data.get('care_actions') or data.get('wardrobe_additions')):
                raise ValueError('This tick is already recorded; use a distinct id for a real later transition')
            if previous['state']!=state or previous['text']!=narrative:raise ValueError('This tick is already recorded; use a distinct id for a real later transition')
            return {'written':False,'episode':previous}
        companion_day.validate_plan(data,state,now)
        if data['previous_id']!=(previous['id'] if previous else None):raise ValueError('State changed since read; read current state and reconsider the transition')
        if previous:
            before=previous['state']
            if now<dt.datetime.fromisoformat(previous['recorded_at']):raise ValueError('Cannot move state backward in time')
            changed=before['outfit']!=state['outfit'] or before['location']!=state['location'] or before['activity']!=state['activity']
            if changed and not state['transition']:raise ValueError('Explain the outfit, location or activity transition; do not teleport')
        result=record(c.life,narrative,state['activity'],'in_progress',now,ident,c.agent,c.human,state=state)
    # Outside the lock: the view is derived, so a failure to write it must not
    # cost the state that was just recorded.
    try:write_emotive(c,now)
    except OSError:pass
    try:
        import companion_active
        companion_active.write(c,now)
    except (OSError,ValueError,ImportError):pass
    return result


# ---- keeping the present honest without a model --------------------------
def last_confirmed(c):
    """The newest state a model actually looked at."""
    for row in events(c):
        if row['state'].get('confirmed',True):return row
    return None

def advance(c,now=None,min_age_minutes=20):
    """Carry the present forward when no model is available to confirm it.

    This never invents. It repeats the last recorded state with `confirmed`
    false, which is the honest claim: nothing has changed on the record, and
    nobody has checked. The hook turns that into "state unconfirmed since
    HH:MM" so the next conversation opens on a truthful present instead of a
    Tuesday evening presented as now.
    """
    now=now or dt.datetime.now(ZoneInfo(c.timezone))
    # The assembled context is cheap and depends on sensors, not only on state,
    # so refresh it whether or not the state itself needs carrying forward.
    try:
        import companion_active
        companion_active.write(c,now)
    except (OSError,ValueError,ImportError):pass
    previous=current(c)
    if not previous:return {'written':False,'reason':'no state to carry forward'}
    age=(now-dt.datetime.fromisoformat(previous['recorded_at'])).total_seconds()/60
    if previous['state'].get('confirmed',True) and age<min_age_minutes:
        return {'written':False,'reason':f'a model confirmed the state {int(age)} minutes ago'}
    with file_lock(c.life/'.presence.lock'):
        previous=current(c)
        utc=now.astimezone(dt.timezone.utc)
        slot=utc.replace(minute=utc.minute//15*15,second=0,microsecond=0)
        ident='advance-'+hashlib.sha256(slot.isoformat().encode()).hexdigest()[:16]
        if previous['id']==ident:return {'written':False,'episode':previous}
        if now<dt.datetime.fromisoformat(previous['recorded_at']):
            return {'written':False,'reason':'clock moved backward; state left alone'}
        state={**previous['state'],'transition':'','confirmed':False}
        anchor=last_confirmed(c)
        since=dt.datetime.fromisoformat(anchor['recorded_at']) if anchor else None
        note=('No change recorded and no model confirmed it'
              +(f" since {since.astimezone(ZoneInfo(c.timezone)).strftime('%H:%M')}" if since else '')+'.')
        result=record(c.life,note,state['activity'],'in_progress',now,ident,c.agent,c.human,state=state)
    for step in (write_emotive,):
        try:step(c,now)
        except OSError:pass
    try:
        import companion_active
        companion_active.write(c,now)
    except (OSError,ValueError,ImportError):pass
    return result


# ---- Emotive.md, rendered ------------------------------------------------
EMOTIVE_NOTE=('<!-- Rendered from the presence state by companion_presence.py. Editing this file\n'
              '     changes nothing: the next state update overwrites it. Change how you feel by\n'
              '     recording a state, which is the only place a mood is real. -->')

def mood_history(c,limit=12):
    """Recent moods, newest first, one per recorded state."""
    out=[]
    for row in events(c):
        state=row['state']
        out.append({'at':row['recorded_at'],'mood':state.get('mood',''),
                    'activity':state.get('activity',''),'location':state.get('location','')})
        if len(out)>=limit:break
    return out

def render_emotive(c,now=None):
    now=now or dt.datetime.now(ZoneInfo(c.timezone))
    row=current(c)
    lines=[f'# Emotive — {c.agent}','',EMOTIVE_NOTE,'']
    if not row:
        lines+=['No state has been recorded yet, so there is nothing here to feel.','']
        return '\n'.join(lines)
    state=row['state']
    when=dt.datetime.fromisoformat(row['recorded_at']).astimezone(ZoneInfo(c.timezone))
    lines+=['## Right now',f"_as of {when.strftime('%A %-d %B, %H:%M')}_",'',
            f"**Mood.** {state.get('mood') or 'unrecorded'}",'',
            f"**Where and what.** {state.get('activity','')} — {state.get('location','')}",'']
    if state.get('wants'):
        lines+=['**What I want.**','']+[f'- {w}' for w in state['wants']]+['']
    if state.get('private_stance'):
        lines+=['**Where I actually stand.** '+state['private_stance'],
                '',"_This one is mine. It shapes how I answer; it is not a line to deliver._",'']
    history=mood_history(c)[1:]
    if history:
        lines+=['## How it has been moving','']
        for h in history:
            at=dt.datetime.fromisoformat(h['at']).astimezone(ZoneInfo(c.timezone))
            lines.append(f"- {at.strftime('%a %H:%M')} — {h['mood']}")
        lines.append('')
    return '\n'.join(lines)

def write_emotive(c,now=None):
    path=c.soul_dir/'Emotive.md';path.parent.mkdir(parents=True,exist_ok=True)
    atomic_write(path,render_emotive(c,now))
    return path


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--home',type=pathlib.Path)
    sub=parser.add_subparsers(dest='action',required=True)
    sub.add_parser('show');sub.add_parser('emotive');sub.add_parser('advance')
    for name in ('update','wardrobe'):
        p=sub.add_parser(name);p.add_argument('--file',type=pathlib.Path,required=True)
    args=parser.parse_args();c=cc.load(args.home)
    if args.action=='show':out=show(c)
    elif args.action=='emotive':out={'written':str(write_emotive(c))}
    elif args.action=='advance':out=advance(c)
    else:
        data=json.loads(args.file.read_text(encoding='utf-8'))
        out=update(c,data) if args.action=='update' else update_wardrobe(c,data)
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,KeyError,TypeError) as exc:print(json.dumps({'error':str(exc)}),file=sys.stderr);sys.exit(1)
