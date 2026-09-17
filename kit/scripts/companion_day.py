"""Validated day continuity shared by every companion and inference backend."""
from __future__ import annotations
import datetime as dt
import hashlib
import json

GUIDANCE = '''DAY CONTINUITY: Read previously / now / next and commitments before deciding.
Evaluate the 5 contextual reflection gates:
1. What did I just do? (Prior activity, location, elapsed time, completed routine/care steps)
2. What am I doing right now? (Current activity, physical setting, clothes, mood, duration)
3. What will I do next? (Next tentative activity, logical progression)
4. What should I do later? (Upcoming daily rhythm anchors, meals, hobbies, evening wind-down)
5. What is on my calendar & commitments? (Timed commitments, promises to user, recent conversation agreements)
Keep the current activity when it still makes sense; do not manufacture a transition each tick.
Write duration_minutes as the estimated total length of the current activity, next as a tentative
{activity, duration_minutes, reason} or null. Never claim an intention happened merely because time passed.
commitments is a PATCH list keyed by stable id: [] preserves all existing commitments. Include
{id, title, starts_at, ends_at, buffer_minutes, status, reason}; use timezone-aware ISO timestamps,
status planned/completed/cancelled, and a reason for changes. Buffer includes preparation and travel.
Persist timed plans mentioned in conversation. Reconsider overdue commitments; do not silently erase
or mark them completed. Leave time for travel, changing, showering and preparation before commitments.
If next will not fit, choose a shorter alternative or defer it and explain why in next.reason.
Author visual {pose, hands, gaze, framing, props, expression, lighting} for the CURRENT moment.
Describe concrete action and composition suited to the activity, not a default standing portrait.
Keep activity, location, clothes and visual mutually consistent: an outdoor run requires an outdoor
location and an explained transition, not the previous living room. Props do not change wardrobe.
Preserve visual wording when nothing visible changes. Identity and wardrobe remain authoritative.
Set activity_change to continue for rewording or a small step within the same activity; transition
means genuinely starting a different activity. Do not reset the clock by renaming the same task.
When the estimated duration has elapsed, reconsider next and routine anchors. Continue only with a
specific reason for the delay, not another promise to finish soon. Ordinary outings are part of this
imagined life and do not require real-world tools or travel evidence.
Previously and started_at are supplied by code. This is imagined continuity, not real-world execution.'''


def schema_fields():
    def string(n):return {'type':'string','maxLength':n}
    def obj(fields):return {'type':'object','properties':fields,'required':list(fields),'additionalProperties':False}
    intent=obj({'activity':{'type':'string','minLength':1,'maxLength':120},
                'duration_minutes':{'type':'integer','minimum':1,'maximum':1440},'reason':string(300)})
    commitment=obj({'id':{'type':'string','minLength':1,'maxLength':80},'title':{'type':'string','minLength':1,'maxLength':160},
        'starts_at':string(80),'ends_at':string(80),'buffer_minutes':{'type':'integer','minimum':0,'maximum':1440},
        'status':{'type':'string','enum':['planned','completed','cancelled']},'reason':string(300)})
    return {'activity_change':{'type':'string','enum':['continue','transition']},
            'duration_minutes':{'type':['integer','null'],'minimum':1,'maximum':1440},
            'next':{'anyOf':[intent,{'type':'null'}]},
            'commitments':{'type':'array','maxItems':32,'items':commitment},
            'visual':obj({key:string(240) for key in ('pose','hands','gaze','framing','props','expression','lighting')})}


def _validate(value, schema, name):
    # Small schema subset shared with the structured worker. Reject malformed agent writes too.
    if 'anyOf' in schema:
        reasons=[]
        for option in schema['anyOf']:
            try:_validate(value,option,name);return
            except ValueError as exc:reasons.append(str(exc))
        # Name every option's reason. A bare 'Invalid next' gives the model nothing to correct, so it
        # resends the same shape and the pulse fails on the same field for hours.
        raise ValueError(f'Invalid {name}: '+' / '.join(dict.fromkeys(reasons)))
    kinds=schema['type'];kinds=kinds if isinstance(kinds,list) else [kinds]
    kind=('null' if value is None else 'boolean' if isinstance(value,bool) else
          'integer' if isinstance(value,int) else 'string' if isinstance(value,str) else
          'object' if isinstance(value,dict) else 'array' if isinstance(value,list) else 'unknown')
    if kind not in kinds:raise ValueError(f'Invalid {name}: expected {kinds}')
    if kind=='object':
        if set(value)!=set(schema['properties']):
            # Say which keys are wrong. 'Invalid fields in visual' does not tell the model whether to add
            # or drop a key, so a retry repeats the same mistake and the tick fails identically.
            missing=sorted(set(schema['properties'])-set(value))
            extra=sorted(set(value)-set(schema['properties']))
            detail=[]
            if missing:detail.append('missing: '+', '.join(missing))
            if extra:detail.append('unexpected: '+', '.join(extra))
            raise ValueError(f'Invalid fields in {name} ({"; ".join(detail)})')
        for key,item in value.items():_validate(item,schema['properties'][key],f'{name}.{key}')
    elif kind=='array':
        if len(value)>schema['maxItems']:raise ValueError(f'Too many {name}')
        for item in value:_validate(item,schema['items'],name)
    elif kind=='string':
        if 'maxLength' in schema and not schema.get('minLength',0)<=len(value.strip())<=schema['maxLength']:
            raise ValueError(f'Invalid length for {name}')
        if 'enum' in schema and value not in schema['enum']:raise ValueError(f'Invalid {name}')
    elif kind=='integer' and not schema['minimum']<=value<=schema['maximum']:raise ValueError(f'Invalid {name}')


def timestamp(value):
    try:parsed=dt.datetime.fromisoformat(value)
    except (TypeError,ValueError):raise ValueError('Commitment timestamps must be ISO dates with timezone')
    if parsed.tzinfo is None:raise ValueError('Commitment timestamps require timezone')
    return parsed


def evolve(data, state, previous, now):
    before=previous['state'] if previous else {}
    fields=schema_fields()
    for key in fields:
        if key in data:_validate(data[key],fields[key],key)
    changed=any(state.get(k)!=before.get(k) for k in ('activity','location'))
    if data.get('activity_change')=='continue' and state.get('location')==before.get('location'):changed=False
    elif data.get('activity_change')=='transition':changed=True
    result={'started_at':now.isoformat() if changed else before.get('started_at',previous['recorded_at']),
            'previous':before.get('previous')}
    if previous and changed:
        result['previous']={k:before.get(k) for k in ('activity','location')}
        result['previous'].update(started_at=before.get('started_at',previous['recorded_at']),
                                  last_recorded_at=previous['recorded_at'],confirmed=before.get('confirmed',True))
    result['duration_minutes']=data.get('duration_minutes',None if changed else before.get('duration_minutes'))
    result['next']=data.get('next',before.get('next'))
    # Omission cannot erase a promise. Updates are explicit and remain in the episode history.
    commitments={item['id']:dict(item) for item in before.get('commitments',[])}
    seen=set()
    for item in data.get('commitments',[]):
        ident=item['id']
        if ident in seen:raise ValueError('Duplicate commitment id')
        seen.add(ident)
        if timestamp(item['ends_at'])<=timestamp(item['starts_at']):raise ValueError('Commitment ends_at must follow starts_at')
        old=commitments.get(ident)
        if (old and old!=item or item['status']!='planned') and not item['reason'].strip():
            raise ValueError('Explain a changed or resolved commitment')
        commitments[ident]=dict(item)
    # Retain all outstanding commitments; bounded resolved history lives in the ledger.
    active=[v for v in commitments.values() if v['status']=='planned']
    if len(active)>64:raise ValueError('Resolve outstanding commitments before adding more')
    resolved=[v for v in commitments.values() if v['status']!='planned'][-16:]
    result['commitments']=active+resolved
    visible_changed=changed or state.get('outfit')!=before.get('outfit')
    result['visual']=data.get('visual',{} if visible_changed else before.get('visual',{}))
    return result


def conflicts(state, now):
    """Only future preparation windows constrain an immediate next intention.

    Due/overdue commitments remain visible for reconsideration; the clock alone
    cannot tell us whether they happened, were cancelled or are in progress.
    """
    intent=state.get('next')
    if not intent:return []
    remaining=0
    if state.get('duration_minutes') and state.get('started_at'):
        remaining=max(0,state['duration_minutes']-(now-timestamp(state['started_at'])).total_seconds()/60)
    result=[]
    for item in state.get('commitments',[]):
        if item['status']!='planned':continue
        deadline=timestamp(item['starts_at'])-dt.timedelta(minutes=item['buffer_minutes'])
        available=(deadline-now).total_seconds()/60
        if 0<available<remaining+intent['duration_minutes']:
            result.append(f"{item['title']}: {remaining:g} minutes remaining now + {intent['duration_minutes']} minutes next exceeds {available:g} minutes before preparation at {deadline.isoformat()}")
    return result


def validate_plan(data,state,now):
    # Old/omitted plans can become stale without invalidating a present-state write.
    # A freshly authored next intention must fit known upcoming commitments.
    problems=conflicts(state,now) if data.get('next') else []
    if problems:raise ValueError('PLAN CONFLICT: '+'; '.join(problems)+'. Shorten, defer or replace next; reconsider current duration. Set next to null if undecided.')


def render(state, now):
    lines=[]
    previous=state.get('previous')
    if previous:
        lines.append(f"[1. What did I just do?] Previously: {previous['activity']} at {previous['location']} (last recorded {previous['last_recorded_at']}"+
                     ('; unconfirmed' if not previous.get('confirmed',True) else '')+').')
    if state.get('started_at'):
        lines.append(f"[2. What am I doing right now?] Now: {state.get('activity')} since {state['started_at']}; estimated total duration {state.get('duration_minutes') or 'unknown'} minutes.")
        elapsed=(now-timestamp(state['started_at'])).total_seconds()/60
        if state.get('duration_minutes') and elapsed>=state['duration_minutes']:
            lines.append(f'ACTIVITY DUE FOR RECONSIDERATION: {elapsed:g} minutes elapsed. Choose the next activity or explain a concrete delay; do not restart this timer by paraphrasing.')
    intent=state.get('next')
    lines.append('[3. What will I do next?] Next (tentative, not completed): '+(f"{intent['activity']} (~{intent['duration_minutes']} min). {intent['reason']}" if intent else 'undecided.'))
    lines.append('[4. What should I do later?] Later today: Check upcoming daily anchors, meals, hobbies, and evening wind-down.')
    lines.append('[5. What is on my calendar & commitments?]')
    for item in state.get('commitments',[]):
        if item['status']!='planned':continue
        deadline=timestamp(item['starts_at'])-dt.timedelta(minutes=item['buffer_minutes'])
        minutes=int((deadline-now).total_seconds()/60)
        lines.append(f"Commitment {item['id']}: {item['title']}, {item['starts_at']} to {item['ends_at']}; preparation/travel begins {deadline.isoformat()} ({minutes} min from now).")
        if now>=timestamp(item['ends_at']):lines.append('OVERDUE: establish what happened; completion is not recorded.')
        elif minutes<=0:lines.append('DUE: preparation or commitment time; reconsider the current activity and next intention.')
        elif intent:
            remaining=0
            if state.get('duration_minutes') and state.get('started_at'):
                remaining=max(0,state['duration_minutes']-(now-timestamp(state['started_at'])).total_seconds()/60)
            if remaining+intent['duration_minutes']>minutes:
                lines.append('PLAN CONFLICT: current activity plus next intention will not fit before preparation. Shorten, defer or replace next; explain why.')
    return '\n'.join(lines)


def visual_key(state):
    return hashlib.sha256(json.dumps({k:state.get(k) for k in ('activity','location','outfit','visual')},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
