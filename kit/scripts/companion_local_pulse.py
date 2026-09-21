#!/usr/bin/env python3
"""One local structured-model request, followed by a validated presence update.

The model authors the companion's state. Code supplies the concurrency token,
validates the record and writes it; a fluent answer alone is never success.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
import urllib.parse
import urllib.request

import companion_endpoint
from zoneinfo import ZoneInfo

import companion_config as cc
import companion_presence as presence
import companion_preread as preread
import companion_day as day
import companion_lifestyle as lifestyle


def schema(wardrobe,care_enabled=False):
    def text(limit):return {'type':'string','minLength':1,'maxLength':limit}
    fields={key:text(limit) for key,limit in [('location',240),('activity',120),
             ('mood',240),('private_stance',300),('text',1600),('transition',500)]}
    fields['outfit']={'type':'array','minItems':0,'maxItems':20,
                      'items':{'type':'string','enum':[item['id'] for item in wardrobe]+['nude','undressed','bathing','towel']}}
    for key,limit in [('care',10),('wants',5)]:
        fields[key]={'type':'array','maxItems':limit,'items':text(160)}
    fields.update(day.schema_fields())
    if care_enabled:
        fields.update(lifestyle.schema_fields())
        # New acquisitions are validated atomically against the same update.
        fields['outfit']['items']={'type':'string','minLength':1,'maxLength':80}
    return {'type':'object','properties':fields,'required':list(fields),'additionalProperties':False}


def pulse(c,base_url,model,slot=1,now=None,apply=True,phase="pulse",
          allow_remote=False,api_key_env=''):
    if phase not in ('pulse','morning','winddown'):raise ValueError('Unknown presence phase')
    # Loopback unless this job was explicitly told otherwise.
    companion_endpoint.verify(base_url,allow_remote,'Local pulse')
    now=now or dt.datetime.now(ZoneInfo(c.timezone))
    previous=presence.current(c)
    if not previous:raise ValueError('Initialize companion presence before enabling the local pulse')
    closet=presence.wardrobe(c)['items']
    if not closet:raise ValueError('Initialize the companion wardrobe first')
    utc=now.astimezone(dt.timezone.utc)
    prior_time=dt.datetime.fromisoformat(previous['recorded_at']).astimezone(dt.timezone.utc)
    interval=utc.replace(minute=utc.minute//15*15,second=0,microsecond=0)
    phase_id=f'state-{phase}-{now.date().isoformat()}' if phase!='pulse' else None
    if phase_id and any(row.get('id')==phase_id for row in presence.read_events(c.life,now.date().isoformat(),limit=0)):
        return {'status':'skipped','reason':'This daily phase is already recorded'}
    if apply and phase=='pulse' and previous['state'].get('confirmed',True) and prior_time>=interval:
        return {'status':'skipped','reason':'This interval already has a model-confirmed state'}
    system=(c.soul.read_text(encoding='utf-8')+'\n\n'
            'You are authoring one short presence record for your ongoing imagined companion life. '
            'Return only the requested JSON. Keep elapsed time, ordinary routines, sleep and existing '
            'plans coherent. Do not invent human messages, actions or participation. A quiet interval '
            'may continue the same activity; do not manufacture drama. Express your own mood, wants '
            'and private stance. Select outfit IDs from the supplied wardrobe. Explain any transition. '
            'This record is local only: no messages, bookings, tools or external actions happen here. '
            'Use concise descriptions within the schema limits. Existing facts take precedence over '
            'examples in the personality. Clothing can change for a believable reason.')
    system+='\n'+day.GUIDANCE
    if phase=='morning':system+=' This is the morning checkpoint: reflect waking, rest and the start of the day. If already awake, continue coherently; do not rewind to bed.'
    elif phase=='winddown':system+=' This is the bedtime checkpoint: reflect how the day ends and preparations for rest, without inventing resolved feelings or finished commitments. Author your loose intended plan for tomorrow in next (e.g. walking along the beach and lunch at the pier, going to the library to research cooking ramen, shopping to surprise your human, or taking a slow rest day).'
    if lifestyle.enabled(c):
        # A life checkpoint needs current facts, not a second copy of an old
        # autonomy diary that anchors a small model to yesterday's scene.
        import companion_active, companion_life
        user=(companion_active.build(c,now)+'\nRoutine anchors:\n'+
              json.dumps(companion_life.routine(c.life,now,c.agent),ensure_ascii=False)+
              '\n'+lifestyle.render(c,now,previous)+
              '\nCurrent record (historical input; previous_id supplied by code):\n'+json.dumps(previous,ensure_ascii=False))
    else:
        user=(preread.preread(c,now)+'\nCurrent record (previous_id is supplied by code):\n'
              +json.dumps(previous,ensure_ascii=False)+'\nAvailable wardrobe:\n'
              +json.dumps(closet,ensure_ascii=False))
    user+=f'\nCHECKPOINT TO WRITE NOW: {phase}, local time {now.isoformat()}. The current record above is historical input. Reconsider its activity, time references, lighting and ongoing appliances against the elapsed time. Write this checkpoint, not another copy of the old scene.'
    roll=((abs(hash((now.date().isoformat(),c.agent)))%100)+1)
    if roll==1:
        user+=f'\n★ SPONTANEITY ROLL: 1/100 roll triggered for today! You have natural freedom to take an unplanned detour, break your scheduled routine, follow an unexpected creative whim or leisurely impulse, and defer routine anchors (decision="defer") with your spontaneous reason.'
    user+='\nAUTONOMY & USER INFLUENCE: If recent conversation with the human suggests an activity, or you agreed on something in chat, honoring that takes priority over routine anchors! Defer conflicting routine anchors (decision="defer") and fulfill what was agreed in chat.'
    state=previous['state'];started=day.timestamp(state.get('started_at',previous['recorded_at']))
    elapsed=(now-started).total_seconds()/60
    if lifestyle.enabled(c) and state.get('duration_minutes') and elapsed>=state['duration_minutes']:
        user+=('\nPRIORITY: the old activity "'+state['activity']+f'" has lasted {elapsed:.0f} minutes against an estimate of {state["duration_minutes"]}. '
               'Choose what you are actually doing NEXT as the new activity, with activity_change="transition", a matching location and visual. '
               'Do not only put it in next while repeating the old activity. If a specific obstacle really delays you, '
               'you must put that obstacle in delay_reason. Increasing duration_minutes with an empty delay_reason will be rejected.')
    payload={'model':model,'messages':[{'role':'system','content':system},{'role':'user','content':user}],
             'max_tokens':3600,'reasoning_effort':'low','reasoning_budget_tokens':1024,'chat_template_kwargs':{'enable_thinking':True},'temperature':0.6,'id_slot':slot,'cache_prompt':True,
             'response_format':{'type':'json_schema','json_schema':{'name':'presence',
                                'strict':True,'schema':schema(closet,lifestyle.enabled(c))}}}
    for attempt in range(2):
        request=urllib.request.Request(base_url.rstrip('/')+'/chat/completions',
                  data=json.dumps(companion_endpoint.shape(payload,base_url)).encode(),
                  headers=companion_endpoint.headers(api_key_env))
        with urllib.request.urlopen(request,timeout=300) as response:reply=json.load(response)
        if not companion_endpoint.confirm_thinking(reply,base_url):
            print('warning: model returned no reasoning; routine and wardrobe rules are easy to miss without it',
                  file=sys.stderr)
        choice=reply['choices'][0]
        if choice.get('finish_reason')!='stop':raise ValueError('Local pulse response was incomplete')
        data=json.loads(choice['message']['content'])
        candidate={**previous['state'],**{key:data[key] for key in ('activity','location') if key in data}}
        import companion_sleep
        candidate.update(day.evolve(data,candidate,previous,now,asleep=companion_sleep.asleep(c,now)))
        try:
            day.validate_plan(data,candidate,now)
            lifestyle.evolve(c,data,data.get('outfit',[]),previous,closet,now)
        except ValueError as exc:
            if attempt:raise
            payload['messages'] += [{'role':'assistant','content':choice['message']['content']},{'role':'user','content':
                'The proposed record was NOT saved. '+str(exc)+' Return the full corrected JSON record for the same checkpoint.'}]
            continue
        break
    # Never let model output bypass optimistic concurrency or choose a stale tick ID.
    data.pop('id',None)
    data['previous_id']=previous['id']
    if phase_id:data['id']=phase_id
    if not apply:return {'status':'preview','record':data,'planning_attempts':attempt+1,'usage':reply.get('usage')}
    result=presence.update(c,data,now)
    if phase=='winddown' and data.get('next'):
        import companion_life
        target_date=(now.date()+dt.timedelta(days=1)).isoformat()
        text_lower=data.get('next','').lower()
        theme='custom'
        if 'beach' in text_lower or 'swim' in text_lower:theme='beach_day'
        elif 'ramen' in text_lower or 'library' in text_lower:theme='library_and_ramen'
        elif 'shop' in text_lower or 'surprise' in text_lower:theme='shopping_and_surprise'
        elif 'studio' in text_lower or 'creative' in text_lower or 'paint' in text_lower or 'photo' in text_lower:theme='creative_studio'
        elif 'rest' in text_lower or 'slow' in text_lower or 'relax' in text_lower:theme='slow_rest_day'
        clean_clothes=[item['id'] if isinstance(item,dict) else str(item) for item in data.get('outfit',[]) if 'pajama' not in str(item).lower() and 'sleep' not in str(item).lower()]
        companion_life.save_tomorrow_plan(c.life,{
            'date':target_date,'created_at':now.isoformat(),
            'intent':data['next'],'laid_out_outfit':clean_clothes,
            'theme':theme,'source':'pulse_winddown'
        })
    return {'status':'recorded','written':result.get('written',True),
            'previous_id':previous['id'],'planning_attempts':attempt+1,'usage':reply.get('usage')}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home',type=pathlib.Path)
    parser.add_argument('--base-url',required=True)
    parser.add_argument('--model',required=True)
    parser.add_argument('--slot',type=int,default=1)
    parser.add_argument('--preview',action='store_true')
    parser.add_argument('--phase',choices=['pulse','morning','winddown'],default='pulse')
    companion_endpoint.add_arguments(parser)
    args=parser.parse_args()
    print(json.dumps(pulse(cc.load(args.home),args.base_url,args.model,args.slot,
                           apply=not args.preview,phase=args.phase,
                           allow_remote=args.allow_remote,api_key_env=args.api_key_env),
                     ensure_ascii=False,indent=2))


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps({'status':'failed','error':str(exc)}),file=sys.stderr)
        sys.exit(1)
