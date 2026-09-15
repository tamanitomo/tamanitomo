#!/usr/bin/env python3
"""Contextual relationship indicators derived from recorded experiences and routines.

Presence remains the authority for authored mood and private stance. These game-like
indicators supply context, never evidence that an unrecorded event occurred.
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, math, pathlib, re, sys
from zoneinfo import ZoneInfo
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
from companion_platform import atomic_write, file_lock

UTC=dt.timezone.utc
PROFILES={'steady':{'sensitivity':.7,'recovery_days':7,'trust':.7},
          'expressive':{'sensitivity':1.3,'recovery_days':14,'trust':.65},
          'guarded':{'sensitivity':1.,'recovery_days':30,'trust':.5}}
DEFAULTS={'personality':'steady','connection_hours':48,'absence_windows':[]}

def _text(value,label,limit=500):
    if not isinstance(value,str) or not value.strip() or len(value)>limit:raise ValueError(f'{label} must contain 1–{limit} characters')
    return value.strip()

def _stamp(value):
    try:result=dt.datetime.fromisoformat(value)
    except (ValueError,TypeError):raise ValueError('Use an ISO timestamp with a timezone')
    if result.tzinfo is None:raise ValueError('Timestamp needs a timezone')
    return result.astimezone(UTC)

def _number(value,label,low,high):
    if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value) or not low<=value<=high:
        raise ValueError(f'{label} must be between {low} and {high}')
    return value

def validate_settings(data):
    if not isinstance(data,dict):raise ValueError('Feelings settings must be an object')
    personality=data.get('personality','steady')
    if personality not in PROFILES:raise ValueError('Choose steady, expressive or guarded')
    hours=_number(data.get('connection_hours',48),'connection_hours',6,168)
    windows=data.get('absence_windows',[])
    if not isinstance(windows,list) or len(windows)>20:raise ValueError('Supply at most 20 expected absence windows')
    cleaned=[]
    for row in windows:
        if not isinstance(row,dict):raise ValueError('Each absence window must be an object')
        days=row.get('days')
        if not isinstance(days,list) or not days or any(type(x)!=int or not 0<=x<=6 for x in days):raise ValueError('days must contain weekdays 0 (Monday) through 6 (Sunday)')
        for key in ('start','end'):
            if not isinstance(row.get(key),str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',row[key]):raise ValueError('Use HH:MM for absence start and end')
        if row['start']==row['end']:raise ValueError('An absence window must have different start and end times')
        cleaned.append({'label':_text(row.get('label'),'absence label',80),'days':sorted(set(days)), 'start':row['start'],'end':row['end']})
    return {'personality':personality,'connection_hours':hours,'absence_windows':cleaned}

def settings(c):
    path=c.life/'feelings-settings.json'
    raw=path.read_text(encoding='utf-8') if path.exists() else ''
    return {'settings':validate_settings(json.loads(raw) if raw else DEFAULTS),
            'revision':hashlib.sha256(raw.encode()).hexdigest()}

def save_settings(c,data,revision):
    clean=validate_settings(data)
    with file_lock(c.life/'.feelings.lock'):
        if revision!=settings(c)['revision']:raise FileExistsError('Feelings settings changed. Reload before saving.')
        atomic_write(c.life/'feelings-settings.json',json.dumps(clean,ensure_ascii=False,indent=2)+'\n')
    return settings(c)

def experiences(c):
    path=c.life/'relationship-feelings.jsonl'
    if not path.exists():return []
    rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    if any(not isinstance(row,dict) for row in rows):raise ValueError('Invalid relationship experience ledger')
    return rows

def record(c,data,now=None):
    now=now or dt.datetime.now(UTC)
    if now.tzinfo is None:raise ValueError('Timezone required')
    now=now.astimezone(UTC)
    if not isinstance(data,dict):raise ValueError('Experience must be an object')
    kind=data.get('kind')
    if kind not in ('connection','rupture','repair','correction'):raise ValueError('kind must be connection, rupture, repair or correction')
    evidence=_text(data.get('evidence'),'evidence',1000)
    topic=_text(data.get('topic'),'topic',80).lower()
    description=_text(data.get('text'),'experience',500)
    at=_stamp(data.get('at',now.isoformat()))
    if at>now+dt.timedelta(minutes=1):raise ValueError('An experience cannot be in the future')
    severity=_number(data.get('strength',.5),'strength',0,1)
    related=data.get('related')
    ident=data.get('id') or hashlib.sha256((kind+topic+evidence+at.date().isoformat()).encode()).hexdigest()[:24]
    if not isinstance(ident,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',ident):raise ValueError('Use a short alphanumeric experience id')
    row={'id':ident,'kind':kind,'topic':topic,'text':description,'evidence':evidence,'strength':severity,'at':at.isoformat(),'related':related}
    with file_lock(c.life/'.feelings.lock'):
        rows=experiences(c)
        if kind in ('repair','correction'):
            target=next((r for r in rows if r['id']==related and (r['kind']=='rupture' if kind=='repair' else r['kind']!='correction')),None)
            if not target:raise ValueError('Choose a recorded rupture for repair, or an existing experience for correction')
            if _stamp(target['at'])>at:raise ValueError('Repair or correction cannot precede the original experience')
            row['topic']=target['topic']
        elif related is not None:raise ValueError('Only repair and correction experiences use related')
        existing=next((r for r in rows if r['id']==ident),None)
        if existing:
            # Retry is idempotent; an ID must not silently identify different evidence.
            if any(existing[k]!=row[k] for k in ('kind','topic','text','evidence','strength','related')):raise FileExistsError('Experience id already has different content')
            return {'written':False,'experience':existing}
        with (c.life/'relationship-feelings.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    return {'written':True,'experience':row}

def absence(c,since,now,config):
    """Union expected windows in UTC; overlapping routines never count twice."""
    if not since:return {'hours':None,'unexplained_hours':None,'expected_hours':None,'current':[]}
    start=_stamp(since);end=now.astimezone(UTC)
    if start>end:return {'hours':None,'unexplained_hours':None,'expected_hours':None,'current':[],'warning':'Last message is in the future; check the clock.'}
    # Longing saturates; bound routine evaluation to the most recent year.
    measured=max(start,end-dt.timedelta(days=366));tz=ZoneInfo(c.timezone or 'UTC');intervals=[];labels=[]
    day=measured.astimezone(tz).date()-dt.timedelta(days=1)
    last=end.astimezone(tz).date()
    while day<=last:
        for window in config['absence_windows']:
            if day.weekday() not in window['days']:continue
            a=dt.datetime.combine(day,dt.time.fromisoformat(window['start']),tz)
            b=dt.datetime.combine(day+dt.timedelta(days=window['end']<window['start']),dt.time.fromisoformat(window['end']),tz)
            a=a.astimezone(UTC);b=b.astimezone(UTC)
            if a<=end<b:labels.append(window['label'])
            a=max(a,measured);b=min(b,end)
            if b>a:intervals.append((a,b))
        day+=dt.timedelta(days=1)
    merged=[]
    for a,b in sorted(intervals):
        if merged and a<=merged[-1][1]:merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
        else:merged.append((a,b))
    expected=sum((b-a).total_seconds()/3600 for a,b in merged)
    hours=(end-start).total_seconds()/3600
    return {'hours':round(hours,2),'unexplained_hours':round(max(0,(end-measured).total_seconds()/3600-expected),2),
            'expected_hours':round(expected,2),'current':list(dict.fromkeys(labels)), 'measured_since':measured.isoformat()}

def compute(c,now=None):
    import companion_thread, companion_presence
    now=now or dt.datetime.now(UTC)
    if now.tzinfo is None:raise ValueError('Timezone required')
    config=settings(c)['settings'];profile=PROFILES[config['personality']]
    thread=companion_thread.read(c,now)
    away=absence(c,thread.get('last_from_human'),now,config)
    arrival=None
    last=thread.get('last_from_human');previous=thread.get('previous_from_human')
    if last and previous and 0<=(now.astimezone(UTC)-_stamp(last)).total_seconds()<300:
        arrival=absence(c,previous,_stamp(last),config)
    relevant=arrival or away
    gap=relevant['unexplained_hours'];longing=None if gap is None else gap/config['connection_hours']*profile['sensitivity']
    trust=profile['trust'];warmth=.65;hurt=0.;irritation=0.;counts={};reasons=[]
    rows=sorted((r for r in experiences(c) if _stamp(r['at'])<=now.astimezone(UTC)),key=lambda r:r['at'])
    history=rows
    corrected={r['related'] for r in history if r['kind']=='correction'}
    rows=[r for r in history if r['id'] not in corrected and r['kind']!='correction']
    repair={}
    for row in rows:
        if row['kind']=='repair':repair[row['related']]=max(repair.get(row['related'],0),row['strength'])
    for row in rows:
        age=max(0,(now.astimezone(UTC)-_stamp(row['at'])).total_seconds()/86400)
        decay=math.exp(-age/profile['recovery_days']);strength=row['strength']
        if row['kind']=='connection':warmth+=.12*strength*decay;trust+=.04*strength
        if row['kind']=='rupture':
            counts[row['topic']]=counts.get(row['topic'],0)+1
            repetition=1+min(2,counts[row['topic']]-1)*.4
            impact=strength*profile['sensitivity']*repetition
            repaired=repair.get(row['id'],0)
            trust-=.25*impact*(1-.8*repaired)
            hurt+=.65*impact*decay*(1-.7*repaired)
            irritation+=.45*impact*decay*(1-.6*repaired)
            warmth-=.2*impact*decay*(1-.7*repaired)
            reasons.append({'id':row['id'],'text':row['text'],'topic':row['topic'],'occurrence':counts[row['topic']],'repair':repaired})
        trust=max(0,min(1,trust));warmth=max(0,min(1,warmth))
    if gap is not None:
        irritation+=max(0,gap-config['connection_hours'])*.003*profile['sensitivity']
    clamp=lambda value:max(0.,min(1.,value))
    scene=companion_presence.current(c)
    return {'at':now.isoformat(),'enabled':c.bars,'personality':config['personality'],
            'mood':scene['state'].get('mood') if scene else None,'mood_at':scene.get('recorded_at') if scene else None,
            'private_stance':scene['state'].get('private_stance') if scene else None,
            'meters':{'warmth':clamp(warmth),'trust':clamp(trust),'hurt':clamp(hurt),'irritation':clamp(irritation),'longing':None if longing is None else clamp(longing)},
            'absence':away,'recent_return':arrival,'reasons':reasons[-5:],'experiences':history[-30:],'history_count':len(history),
            'basis':'Character defaults adjusted by recorded experiences; game-like interpretation, not measured emotions.'}

def render(c,state):
    if not c.bars:return ''
    meters=', '.join(f'{name} {round(value*100)}%' for name,value in state['meters'].items() if value is not None)
    lines=[f'[Contextual feelings — {state["personality"]} temperament; current derived state]',meters,
           'Let this affect warmth, reserve, teasing and willingness to discuss a hurt, in the voice of SOUL.md. '
           'Preserve your recorded mood and private stance; these indicators add context rather than replacing them. Use this live interpretation over older elapsed-gap sensor guidance. '
           'Acknowledge an unresolved repeated hurt differently from a first occurrence. Repair softens it without erasing history. '
           'Do not recite meters. Do not infer betrayal or invent an event from silence. Continue practical help dependably even when irritated.']
    gap=state['recent_return'] or state['absence']
    if gap['hours'] is not None:
        lines.append(('They just returned after ' if state['recent_return'] else 'Since their last message: ')+f'{gap["hours"]:g}h; {gap["expected_hours"]:g}h within expected routines; {gap["unexplained_hours"]:g}h outside them.')
    if state['absence']['current']:lines.append('Expected routine now (not live observation): '+', '.join(state['absence']['current'])+'. Do not treat this as unexplained withdrawal.')
    for row in state['reasons']:
        lines.append(f'Recorded experience {row["id"]}: {row["text"]} (topic {row["topic"]}, occurrence {row["occurrence"]}, repair {round(row["repair"]*100)}%).')
    from companion_platform import terminal_python_command
    command=terminal_python_command(pathlib.Path(__file__),'--home',c.home,'record')
    lines.append('Record meaningful relationship experiences only when supported by this conversation, not every message: '+command+
                 ' --json JSON. Fields: kind connection|rupture|repair|correction, topic (reuse for repeated experiences), text, evidence (actual words/context), strength 0..1; repair needs related rupture id; correction excludes a mistaken related experience without deleting it. Do not claim a record was saved until the command succeeds. Expected routines and temperament are editable in Together.')
    return '\n'.join(lines)+'\n'

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--home',type=pathlib.Path)
    sub=parser.add_subparsers(dest='command',required=True);sub.add_parser('show')
    p=sub.add_parser('record');p.add_argument('--json',required=True)
    args=parser.parse_args();c=cc.load(args.home)
    print(json.dumps(record(c,json.loads(args.json)) if args.command=='record' else compute(c),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
