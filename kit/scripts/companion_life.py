#!/usr/bin/env python3
"""Append-only imagined-life ledger. Schedules are suggestions, never evidence.

Config-driven: paths and names come from companion_config, so this file contains
no agent name, no human name, and no absolute path.
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, os, pathlib, random, re, sys
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

CUSTOM_THEME='custom'


def themes(root):
    """The day-shapes this companion actually has, plus the open one.

    A theme is not a label on a plan: it replaces the whole day's anchors with a
    scripted set, so a wrong one rewrites her day. The valid names are hers, not
    a constant, which is why they are read rather than assumed.
    """
    root=pathlib.Path(root)
    try:catalog=json.loads((root/'routine.json').read_text(encoding='utf-8')).get('routines_catalog',{})
    except (OSError,ValueError):catalog={}
    return [CUSTOM_THEME]+sorted(k for k in catalog if isinstance(k,str))


# --- people ----------------------------------------------------------------
#
# `recurring_cast` has been in the routine file since the beginning, and the
# guidance has always told a companion to "develop recurring fictional friends
# gradually". Nothing ever wrote one, so every companion had an empty world: no
# one to meet, no one to cook for, nothing to come back to. Ideas give her
# things to do; a cast gives her people to do them with, which is the difference
# between varied and alive.
#
# Seeded, then hers. Someone she sees weekly should be mid-conversation rather
# than reintroduced, so a last-seen date is kept per person, by id.
CAST_FILE='cast.json'


def _seed_cast():
    path=pathlib.Path(__file__).resolve().parent.parent/'personas'/'recurring_cast.json'
    try:data=json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):return {}
    return data


def cast(root):
    """Everyone in her life: the seeded people plus anyone she has added."""
    root=pathlib.Path(root)
    try:own=json.loads((root/CAST_FILE).read_text(encoding='utf-8'))
    except (OSError,ValueError):own={}
    if not isinstance(own,dict):own={}
    people={x['id']:x for x in _seed_cast().get('cast',[]) if isinstance(x,dict) and x.get('id')}
    for row in own.get('added',[]) or []:
        if isinstance(row,dict) and row.get('id'):people[row['id']]={**row,'hers':True}
    for ident in own.get('removed',[]) or []:people.pop(ident,None)
    seen=own.get('last_seen',{}) if isinstance(own.get('last_seen'),dict) else {}
    for ident,person in people.items():
        person['last_seen']=seen.get(ident)
    return list(people.values())


def _write_cast(root,data):
    atomic_write(pathlib.Path(root)/CAST_FILE,json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    return data


def _cast_file(root):
    try:data=json.loads((pathlib.Path(root)/CAST_FILE).read_text(encoding='utf-8'))
    except (OSError,ValueError):data={}
    if not isinstance(data,dict):data={}
    data.setdefault('added',[]);data.setdefault('removed',[]);data.setdefault('last_seen',{})
    return data


def add_person(root,person):
    """Someone she met herself. They join the cast and recur like anyone else."""
    name=str(person.get('name') or '').strip()
    if not name:raise ValueError('A person needs a name')
    ident=str(person.get('id') or '').strip() or 'her-'+re.sub(r'[^a-z0-9]+','-',name.lower()).strip('-')[:32]
    data=_cast_file(root)
    data['added']=[x for x in data['added'] if x.get('id')!=ident]
    data['added'].append({'id':ident,'name':name[:80],
        'relation':str(person.get('relation') or 'friend')[:120],
        'met':str(person.get('met') or '')[:300],
        'traits':[str(t)[:32] for t in (person.get('traits') or [])][:6],
        'together':[str(t)[:80] for t in (person.get('together') or [])][:6],
        'cadence':person.get('cadence','fortnightly'),'note':str(person.get('note') or '')[:300]})
    data['removed']=[x for x in data['removed'] if x!=ident]
    _write_cast(root,data)
    return data['added'][-1]


def saw_person(root,ident,day=None):
    """Record that she spent time with someone, so the next meeting has a gap behind it."""
    day=day or dt.date.today().isoformat()
    dt.date.fromisoformat(day)
    if ident not in {p['id'] for p in cast(root)}:raise ValueError(f'Nobody called {ident!r} is in the cast')
    data=_cast_file(root)
    data['last_seen'][ident]=day
    _write_cast(root,data)
    return {'id':ident,'last_seen':day}


def drop_person(root,ident):
    """Take someone out of her life. Reversible by editing cast.json."""
    data=_cast_file(root)
    if ident not in data['removed']:data['removed'].append(str(ident)[:80])
    data['added']=[x for x in data['added'] if x.get('id')!=ident]
    _write_cast(root,data)
    return {'removed':data['removed']}


def people_due(root,day=None,count=3):
    """Who she has not seen in a while, longest gap first.

    Cadence is a rhythm rather than a rule: it decides who surfaces, never that
    a meeting happened. Nobody is 'overdue' in a way she owes anything about.
    """
    day=day or dt.date.today()
    if isinstance(day,str):day=dt.date.fromisoformat(day)
    spacing={'weekly':7,'fortnightly':14,'monthly':30}
    rows=[]
    for person in cast(root):
        want=spacing.get(person.get('cadence','fortnightly'),14)
        seen=person.get('last_seen')
        if seen:
            try:gap=(day-dt.date.fromisoformat(seen)).days
            except ValueError:gap=want*2
        else:
            gap=want*2   # never seen: as available as someone long overdue
        rows.append({**person,'days_since':None if not seen else gap,'due':gap>=want,
                     'overdue_by':max(0,gap-want)})
    rows.sort(key=lambda r:(-r['overdue_by'],r['name']))
    return rows[:count] if count else rows


# --- ideas for a day -------------------------------------------------------
#
# The complaint this answers: she stayed home and read, every day. Not because
# she had no options, but because nothing ever pushed against the safe answer.
# Seven generic anchors, five scripted days, and a one-in-a-hundred chance of a
# detour is not a life, and enumerating three hundred whole days to fix it would
# be unmaintainable and still fixed.
#
# So: a palette of ideas rather than a catalogue of days. A handful are offered
# each evening, weighted away from whatever she has done lately and toward the
# season and the day of the week. She takes one, or refuses them and writes her
# own, which then joins the palette. What she chose is recorded by id, so
# nothing here ever has to read what she wrote about it.
IDEAS_FILE='interests.json'
RECENT_DAYS=45


def _seed_ideas():
    path=pathlib.Path(__file__).resolve().parent.parent/'personas'/'activity_ideas.json'
    try:data=json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):return []
    return [x for x in data.get('ideas',[]) if isinstance(x,dict) and x.get('id')]


def interests(root):
    """Her own layer over the shipped palette: what she added, chose, or ruled out."""
    root=pathlib.Path(root)
    try:data=json.loads((root/IDEAS_FILE).read_text(encoding='utf-8'))
    except (OSError,ValueError):data={}
    if not isinstance(data,dict):data={}
    return {'added':[x for x in data.get('added',[]) if isinstance(x,dict) and x.get('id')],
            'chosen':[x for x in data.get('chosen',[]) if isinstance(x,dict) and x.get('id')],
            'declined':[x for x in data.get('declined',[]) if isinstance(x,str)]}


def _write_interests(root,data):
    atomic_write(pathlib.Path(root)/IDEAS_FILE,json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    return data


def add_idea(root,idea):
    """Something she thought of herself, kept so it can come round again."""
    ident=str(idea.get('id') or '').strip()
    title=str(idea.get('title') or '').strip()
    if not title:raise ValueError('An idea needs a title')
    if not ident:
        ident='her-'+re.sub(r'[^a-z0-9]+','-',title.lower()).strip('-')[:40]
    data=interests(root)
    data['added']=[x for x in data['added'] if x['id']!=ident]
    data['added'].append({'id':ident,'title':title[:160],
                          'tags':[str(t)[:24] for t in (idea.get('tags') or [])][:6],
                          'season':idea.get('season','any'),'energy':idea.get('energy','medium'),
                          'cost':idea.get('cost','low'),'social':idea.get('social','solo'),
                          'setting':idea.get('setting','local'),'hours':idea.get('hours',2),
                          'note':str(idea.get('note') or '')[:300],'hers':True})
    _write_interests(root,data)
    return data['added'][-1]


def record_choice(root,ids,day=None):
    """What she picked, by id. Recency is a fact about ids, never about wording."""
    day=day or dt.date.today().isoformat()
    dt.date.fromisoformat(day)
    data=interests(root)
    known={x['id'] for x in palette(root)}
    for ident in ([ids] if isinstance(ids,str) else list(ids or [])):
        ident=str(ident)
        if ident not in known:raise ValueError(f'Unknown idea {ident!r}')
        data['chosen']=[x for x in data['chosen'] if not (x['id']==ident and x.get('day')==day)]
        data['chosen'].append({'id':ident,'day':day})
    data['chosen']=data['chosen'][-400:]
    _write_interests(root,data)
    return data['chosen'][-1] if data['chosen'] else None


def decline_idea(root,ident):
    """Something she does not want offered again. Her call, and reversible."""
    data=interests(root)
    if ident not in data['declined']:data['declined'].append(str(ident)[:80])
    _write_interests(root,data)
    return data['declined']


def palette(root):
    """Every idea available to her: the shipped seeds plus her own, hers winning."""
    own=interests(root)['added']
    rows={x['id']:x for x in _seed_ideas()}
    rows.update({x['id']:x for x in own})
    return list(rows.values())


SEASONS=((3,'spring'),(6,'summer'),(9,'autumn'),(12,'winter'))


def season_of(day):
    return {3:'spring',4:'spring',5:'spring',6:'summer',7:'summer',8:'summer',
            9:'autumn',10:'autumn',11:'autumn',12:'winter',1:'winter',2:'winter'}[day.month]


def suggest(root,day=None,count=6,now=None):
    """A few ideas for a given day, weighted away from what she has just done.

    Deterministic for a given companion and date, so the evening's suggestions do
    not reshuffle if anything asks twice.
    """
    day=day or dt.date.today()
    if isinstance(day,str):day=dt.date.fromisoformat(day)
    data=interests(root)
    declined=set(data['declined'])
    last_done={}
    for row in data['chosen']:
        try:chosen_on=dt.date.fromisoformat(row['day'])
        except (ValueError,KeyError,TypeError):continue
        if row['id'] not in last_done or chosen_on>last_done[row['id']]:last_done[row['id']]=chosen_on
    season=season_of(day)
    weekend=day.weekday()>=5
    scored=[]
    for idea in palette(root):
        if idea['id'] in declined:continue
        weight=1.0
        # Recently chosen things fade out and come back, rather than being
        # banned: repeating something she liked a month ago is a life, and
        # repeating it three days running is a rut.
        done=last_done.get(idea['id'])
        if done is not None:
            age=(day-done).days
            if age<0:continue
            if age<RECENT_DAYS:weight*=max(0.02,age/RECENT_DAYS)
        wants=idea.get('season','any')
        if wants not in ('any',season):weight*=0.25
        # A day out needs a day to put it in.
        if float(idea.get('hours',2))>=5 and not weekend:weight*=0.3
        if idea.get('hers'):weight*=1.4
        if done is None:weight*=1.25
        scored.append((idea,weight))
    if not scored:return {'day':day.isoformat(),'season':season,'suggestions':[],
                          'note':'No ideas available; add some with add-idea.'}
    rng=random.Random(f'{root}|{day.isoformat()}')
    picks=[]
    pool=list(scored)
    for _ in range(min(count,len(pool))):
        total=sum(w for _,w in pool)
        if total<=0:break
        roll=rng.random()*total
        for index,(idea,weight) in enumerate(pool):
            roll-=weight
            if roll<=0:break
        picks.append(pool.pop(index)[0])
    return {'day':day.isoformat(),'season':season,'weekend':weekend,
            'suggestions':[{'id':x['id'],'title':x['title'],'tags':x.get('tags',[]),
                            'setting':x.get('setting'),'social':x.get('social'),
                            'hours':x.get('hours'),'note':x.get('note',''),
                            'last_done':last_done[x['id']].isoformat() if x['id'] in last_done else None}
                           for x in picks],
            'note':('Invitations, not obligations. Take one, combine two, or ignore them all and '
                    'record what you would rather do with add-idea.')}


def save_laid_out(root,day,items):
    """The clothes set out for a particular day.

    The only part of the old `tomorrow.json` that is not a plan: what she hung on
    the back of the door. It keeps its own small file so the plan stays a
    timeline and nothing else.
    """
    root=pathlib.Path(root)
    day=day.isoformat() if hasattr(day,'isoformat') else str(day)
    dt.date.fromisoformat(day)
    data={'date':day,'items':[str(i)[:80] for i in (items or [])][:20]}
    atomic_write(root/'laid-out.json',json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    return data


def laid_out(root,day=None):
    """What was set out, if it was set out for the day being asked about."""
    root=pathlib.Path(root)
    try:data=json.loads((root/'laid-out.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):return []
    if not isinstance(data,dict):return []
    if day is not None:
        want=day.isoformat() if hasattr(day,'isoformat') else str(day)
        if data.get('date')!=want:return []
    return [str(i) for i in (data.get('items') or [])]


def save_tomorrow_plan(root,plan):
    """Record what she means to do tomorrow.

    The theme has to be a name she chose from her own catalog. It used to be
    guessed from the wording of her intention by substring -- 'beach' in the
    sentence meant a beach day -- which read "I would rather not go to the beach"
    as a beach day, "an interest" as a rest day (it contains "rest"), and a
    workshop as a shopping trip. Wording may refuse a plan and ask for a better
    one; it may never decide what the plan is.
    """
    root=pathlib.Path(root)
    plan=dict(plan)
    intent=plan.get('intent')
    if not isinstance(intent,str) or not intent.strip():
        raise ValueError('An intended day needs an intent written as a sentence')
    plan['intent']=intent.strip()[:300]
    theme=plan.get('theme') or CUSTOM_THEME
    known=themes(root)
    if theme not in known:
        raise ValueError(f'Unknown theme {theme!r}. Choose one of: '+', '.join(known))
    plan['theme']=theme
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

def expected_day(root,day,now=None):
    """The shape the companion expects a given day to have.

    `routine` answers "what is she doing right now", which is what the prompt
    needs and no use at all for looking a week ahead. This answers the question a
    person actually asks of a calendar -- what does her Thursday look like -- so
    there is something to talk to her about before it happens.

    Nothing here is a commitment or a completed event. These are the anchors of an
    imagined life: recurring daily ones, the weekly ones that belong to that
    weekday, and, when the day is the one it was written for, whatever she
    actually intends to do instead.
    """
    root=pathlib.Path(root)
    try:data=json.loads((root/'routine.json').read_text(encoding='utf-8'))
    except (FileNotFoundError,ValueError):
        return {'day':day.isoformat(),'configured':False,'anchors':[],'intended_plan':None}
    if data.get('kind')!='imagined_routine':raise ValueError('routine must be imagined_routine')
    weekday=('monday','tuesday','wednesday','thursday','friday','saturday','sunday')[day.weekday()]

    catalog=data.get('routines_catalog',{})
    source='routine'
    plan=None
    # The plan for the day is the authority when there is one. `tomorrow.json` is
    # read only so an older install still answers while it is being migrated.
    try:
        import companion_plan
        settled=companion_plan.read_for(root,day)
    except Exception:
        settled=None
    if settled and settled.get('settled_at'):
        rows=[{'start':x['start'],'end':x['end'],'activity':x['what'],'setting':x.get('where',''),
               'id':x['id'],'recurrence':x['kind'],'status':x['status']}
              for x in settled['items'] if x.get('status')=='planned']
        plan={'intent':settled.get('intent',''),'theme':settled.get('theme','custom'),
              'date':day.isoformat(),'items':settled['items'],'history':settled.get('history',[])[-10:]}
        source='intended'
    else:
        plan=read_tomorrow_plan(root,now)
        if plan and plan.get('date') and plan['date']!=day.isoformat():plan=None
        if plan and plan.get('anchors'):
            rows=[dict(x) for x in plan['anchors'] if isinstance(x,dict)];source='intended'
        elif plan and plan.get('theme') in catalog:
            rows=[dict(x) for x in catalog[plan['theme']].get('anchors',[]) if isinstance(x,dict)];source='intended'
        else:
            rows=None
    if rows is None:
        rows=[dict(x,recurrence='weekly') for x in data.get('weekly',[])
              if isinstance(x,dict) and x.get('day')==weekday]
        rows+=[dict(x,recurrence='daily') for x in data.get('daily',[]) if isinstance(x,dict)]

    anchors=[]
    for index,row in enumerate(rows):
        start,end=str(row.get('start','')),str(row.get('end',''))
        try:
            dt.time.fromisoformat(start);dt.time.fromisoformat(end)
        except (ValueError,TypeError):
            # A hand-edited line missing a time is skipped rather than allowed to
            # take the whole day's schedule down with it.
            continue
        anchors.append({'id':row.get('id') or f'{source}-{index}','start':start,'end':end,
                        'activity':row.get('activity',''),'setting':row.get('setting',''),
                        'recurrence':row.get('recurrence',source),'source':source})
    anchors.sort(key=lambda r:r['start'])
    # What she picked, resolved to titles, so a day she chose reads as one.
    titles={x['id']:x for x in palette(root)}
    taken=[{'id':i,'title':titles[i]['title'],'tags':titles[i].get('tags',[])}
           for i in ((plan or {}).get('ideas') or []) if i in titles]
    return {'day':day.isoformat(),'weekday':weekday,'configured':True,'source':source,
            'anchors':anchors,'intended_plan':plan,'ideas':taken,
            'preferred_rhythm':data.get('preferred_rhythm',''),
            'note':'Anchors are the shape of an imagined day, not commitments or completed events.'}


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

# Which session sources mean a person was actually there. Everything else is the
# companion's own machinery talking to itself: scheduled jobs, tool runs,
# sub-agents, and the companion-to-companion dialogues two of them hold without
# the human present.
HUMAN_SOURCES=('cli','tui','telegram','discord','mobile','desktop','api_server','web')


def contact(c,day=None):
    """Did the human actually speak to her on this day, per the session record.

    A journal that asks the model to remember whether anyone spoke to it is
    asking the wrong thing: it will fill the silence, because filling silences
    is what it is for. The sessions table already knows. A day whose every
    session came from cron had nobody in it, and that is a fact a prompt can be
    held to rather than a judgement it has to make.
    """
    import datetime as dt, sqlite3
    tz=_tz(c)
    day=str(day or '') or dt.datetime.now(tz).date().isoformat()
    try:
        target=dt.date.fromisoformat(day)
    except ValueError:
        raise SystemExit('Use a date as YYYY-MM-DD')
    path=pathlib.Path(c.home)/'state.db'
    out={'day':target.isoformat(),'human_sessions':0,'sources':{},'titles':[],
         'evidence':str(path),'verdict':'no recorded contact'}
    if not path.is_file():
        out['verdict']='unknown: no session record on this host'
        return out
    try:
        con=sqlite3.connect(f'file:{path}?mode=ro',uri=True)
        rows=con.execute('select source,started_at,title from sessions').fetchall()
    except sqlite3.Error as exc:
        out['verdict']=f'unknown: session record unreadable ({exc})'
        return out
    finally:
        try:con.close()
        except Exception:pass
    for source,started,title in rows:
        if not started:continue
        try:when=dt.datetime.fromtimestamp(float(started),tz)
        except (TypeError,ValueError,OSError):continue
        if when.date()!=target:continue
        key=str(source or 'unknown')
        out['sources'][key]=out['sources'].get(key,0)+1
        if key in HUMAN_SOURCES:
            out['human_sessions']+=1
            if title:out['titles'].append(f'{when.strftime("%H:%M")} {title}'[:120])
    if out['human_sessions']:
        out['verdict']='contact recorded'
    out['titles']=out['titles'][:20]
    return out


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--home',type=pathlib.Path,help='companion home (default: $COMPANION_HOME/$HERMES_HOME)')
    s=p.add_subparsers(dest='cmd',required=True)
    s.add_parser('tick')
    s.add_parser('dates',help='Local today and yesterday, portable across operating systems')
    ct=s.add_parser('contact',help='Whether the human actually spoke to her on a day, from the session record')
    ct.add_argument('--day',help='YYYY-MM-DD; defaults to today')
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
    pt.add_argument('--theme',default=CUSTOM_THEME,
                    help='One of her routine archetypes, or custom. Names are listed by `themes`.')
    pt.add_argument('--anchors-file',type=pathlib.Path,help='Optional JSON file with custom anchors list')
    pt.add_argument('--notes',default='',help='Personal reflections or notes for tomorrow')
    s.add_parser('planned-tomorrow',help='Read the active intended plan and laid-out clothes')
    s.add_parser('themes',help='The day-shapes available to plan with, by name')
    s.add_parser('cast',help='The people in her life, and who she has not seen lately')
    ap=s.add_parser('add-person',help='Someone she met herself, kept so they recur')
    ap.add_argument('--name',required=True);ap.add_argument('--relation',default='friend')
    ap.add_argument('--met',default='');ap.add_argument('--traits',default='')
    ap.add_argument('--together',default='')
    ap.add_argument('--cadence',default='fortnightly',choices=['weekly','fortnightly','monthly'])
    ap.add_argument('--note',default='')
    sp=s.add_parser('saw',help='Record spending time with someone, by id')
    sp.add_argument('--person',required=True);sp.add_argument('--day')
    dp=s.add_parser('drop-person',help='Take someone out of the cast')
    dp.add_argument('--person',required=True)
    sg=s.add_parser('suggest',help='A few ideas for a day, weighted away from what you did lately')
    sg.add_argument('--day');sg.add_argument('--count',type=int,default=6)
    ai=s.add_parser('add-idea',help='Keep an idea of your own so it comes round again')
    ai.add_argument('--title',required=True);ai.add_argument('--tags',default='')
    ai.add_argument('--season',default='any',choices=['any','spring','summer','autumn','winter'])
    ai.add_argument('--energy',default='medium',choices=['low','medium','high'])
    ai.add_argument('--cost',default='low',choices=['none','low','moderate'])
    ai.add_argument('--social',default='solo',choices=['solo','cast','crowd'])
    ai.add_argument('--setting',default='local',choices=['home','local','city','outdoors','nature','water'])
    ai.add_argument('--hours',type=float,default=2);ai.add_argument('--note',default='')
    ch=s.add_parser('chose',help='Record which ideas you actually took, by id')
    ch.add_argument('--idea',action='append',required=True);ch.add_argument('--day')
    dc=s.add_parser('decline-idea',help='Stop offering an idea. Reversible by editing interests.json')
    dc.add_argument('--idea',required=True)
    a=p.parse_args()
    c=cc.load(a.home);tz=_tz(c);now=dt.datetime.now(tz);root=c.life
    if a.cmd=='contact':out=contact(c,getattr(a,'day',None))
    elif a.cmd=='dates':out={'today':now.date().isoformat(),'yesterday':(now.date()-dt.timedelta(days=1)).isoformat(),'timezone':c.timezone}
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
    elif a.cmd=='cast':
        out={'cast':people_due(root,now.date(),0)}
    elif a.cmd=='add-person':
        out=add_person(root,{'name':a.name,'relation':a.relation,'met':a.met,
                             'traits':[t.strip() for t in a.traits.split(',') if t.strip()],
                             'together':[t.strip() for t in a.together.split(',') if t.strip()],
                             'cadence':a.cadence,'note':a.note})
    elif a.cmd=='saw':
        out=saw_person(root,a.person,a.day or now.date().isoformat())
    elif a.cmd=='drop-person':
        out=drop_person(root,a.person)
    elif a.cmd=='suggest':
        out=suggest(root,a.day,max(1,min(20,a.count)),now)
    elif a.cmd=='add-idea':
        out=add_idea(root,{'title':a.title,'tags':[t.strip() for t in a.tags.split(',') if t.strip()],
                           'season':a.season,'energy':a.energy,'cost':a.cost,'social':a.social,
                           'setting':a.setting,'hours':a.hours,'note':a.note})
    elif a.cmd=='chose':
        out=record_choice(root,a.idea,a.day or now.date().isoformat())
    elif a.cmd=='decline-idea':
        out={'declined':decline_idea(root,a.idea)}
    elif a.cmd=='themes':
        out={'themes':themes(root),
             'note':'Pick the one that matches what you mean to do, or custom to keep your ordinary day.'}
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
