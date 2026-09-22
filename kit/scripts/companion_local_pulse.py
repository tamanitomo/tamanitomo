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
import companion_life
import companion_worker_model as worker


def schema(wardrobe,care_enabled=False,themes=None):
    def text(limit):return {'type':'string','minLength':1,'maxLength':limit}
    fields={key:text(limit) for key,limit in [('location',240),('activity',120),
             ('mood',240),('private_stance',300),('text',1600),('transition',500)]}
    fields['outfit']={'type':'array','minItems':0,'maxItems':20,
                      'items':{'type':'string','enum':[item['id'] for item in wardrobe]+['nude','undressed','bathing','towel']}}
    for key,limit in [('care',10),('wants',5)]:
        fields[key]={'type':'array','maxItems':limit,'items':text(160)}
    fields.update(day.schema_fields())
    # Tomorrow is stated, never inferred. The theme is an enum of the day-shapes
    # this companion actually has, so the only themes she can pick are ones that
    # exist -- and picking one is a decision she makes, not one read out of her
    # sentence afterwards.
    if themes:
        # A plan has times in it. Asking for a loose intention and a bag of ideas
        # meant something else had to guess when any of it happened, and guessing
        # is how two things end up in the same afternoon.
        item={'type':'object','properties':{
            'start':{'type':'string','minLength':4,'maxLength':5},
            'end':{'type':'string','minLength':4,'maxLength':5},
            'what':text(160),'where':{'type':'string','maxLength':160},
            'kind':{'type':'string','enum':['commitment','idea','person','anchor','other']},
            'ref':{'type':'string','maxLength':80}},
            'required':['start','end','what','where','kind','ref'],'additionalProperties':False}
        fields['tomorrow']={'anyOf':[{'type':'object','properties':{
            'intent':text(300),
            'theme':{'type':'string','enum':list(themes)},
            'items':{'type':'array','maxItems':10,'items':item},
            'outfit':{'type':'array','maxItems':20,'items':{'type':'string','minLength':1,'maxLength':80}}},
            'required':['intent','theme','items','outfit'],'additionalProperties':False},{'type':'null'}]}
    if care_enabled:
        fields.update(lifestyle.schema_fields())
        # New acquisitions are validated atomically against the same update.
        fields['outfit']['items']={'type':'string','minLength':1,'maxLength':80}
    return {'type':'object','properties':fields,'required':list(fields),'additionalProperties':False}


def lay_out(chosen,closet):
    """The clothes she sets out for tomorrow, minus what she sleeps in.

    Nightwear used to be excluded by looking for "pajama" or "sleep" anywhere in
    the stringified item, which is a guess about wording dressed up as a rule.
    The wardrobe has carried a `category` enum all along, and `sleep` is one of
    its values, so the question has an answer that does not involve reading
    anything.
    """
    nightwear={item['id'] for item in (closet or []) if isinstance(item,dict)
               and item.get('category')=='sleep' and item.get('id')}
    out=[]
    for item in (chosen or []):
        ident=item.get('id') if isinstance(item,dict) else str(item)
        if ident and ident not in nightwear and ident not in out:out.append(ident)
    return out


def _settle_ids(data,previous,phase_id):
    """Never let model output bypass optimistic concurrency or choose a stale tick ID."""
    data.pop('id',None)
    data['previous_id']=previous['id']
    if phase_id:data['id']=phase_id
    return data


def pulse(c,base_url='',model='',slot=1,now=None,apply=True,phase="pulse",
          allow_remote=False,api_key_env='',tier='loops'):
    if phase not in ('pulse','morning','winddown'):raise ValueError('Unknown presence phase')
    # Her own configured model by default. An explicit endpoint still wins, so a
    # job that genuinely wants a particular local server can still say so.
    if base_url:
        route={'provider':'','model':model,'base_url':base_url,'reasoning_effort':'','direct':True}
        companion_endpoint.verify(base_url,allow_remote,'Local pulse')
    else:
        route=worker.resolve(c,tier)
        model=route['model']
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
        import companion_active
        user=(companion_active.build(c,now)+'\nRoutine anchors:\n'+
              json.dumps(companion_life.routine(c.life,now,c.agent),ensure_ascii=False)+
              '\n'+lifestyle.render(c,now,previous)+
              '\nCurrent record (historical input; previous_id supplied by code):\n'+json.dumps(previous,ensure_ascii=False))
    else:
        user=(preread.preread(c,now)+'\nCurrent record (previous_id is supplied by code):\n'
              +json.dumps(previous,ensure_ascii=False)+'\nAvailable wardrobe:\n'
              +json.dumps(closet,ensure_ascii=False))
    if phase=='winddown':
        # The end of a day is the only moment anything looks past it. Without this
        # she has a rhythm and no intentions: the same seven anchors every day,
        # and nothing she did today shaping tomorrow.
        offered=companion_life.suggest(c.life,(now.date()+dt.timedelta(days=1)),6,now)
        if offered['suggestions']:
            user+=('\nIDEAS FOR TOMORROW ('+offered['season']+
                   (', a weekend' if offered.get('weekend') else ', a weekday')+
                   ') — invitations, weighted away from what you have done lately:\n'+
                   '\n'.join(f"  {x['id']}: {x['title']}"+
                             (f" [{x['setting']}, {x['social']}, ~{x['hours']}h]")+
                             (f" — {x['note']}" if x.get('note') else '')+
                             (f" (last done {x['last_done']})" if x.get('last_done') else '')
                             for x in offered['suggestions'])+
                   '\nTake one, combine two, or ignore them entirely and do something of your own. '
                   'If you take one, put it in `tomorrow.items` with the hours you mean to give '
                   'it and its id in `ref`. Ignoring all of them is a real answer. `theme` is a '
                   'different thing from an idea: it is the overall shape of the day, chosen from '
                   'the listed day-shape names, and "custom" is correct whenever an idea does not '
                   'match one of them.')
        due=companion_life.people_due(c.life,(now.date()+dt.timedelta(days=1)),3)
        if due:
            user+=('\nPEOPLE — who you have not seen in a while. Seeing someone is a real way to '
                   'spend a day, and a friendship that never recurs is not one:\n'+
                   '\n'.join(f"  {p['id']}: {p['name']}, {p['relation']}"+
                             (f" — usually {p['cadence']}"+
                              (f", last seen {p['last_seen']}" if p.get('last_seen') else ', not seen yet')+
                              (f". You tend to: {', '.join(p['together'][:3])}" if p.get('together') else ''))
                             for p in due)+
                   '\nSeeing someone is an item like any other: give it hours and put their '
                   'id in `ref` with kind "person".')
        user+=('\nEach item is exactly: {"start":"HH:MM","end":"HH:MM","what":"...","where":"...",'
               '"kind":"commitment|idea|person|anchor|other","ref":"the id you took it from, or \'\'"}. '
               'Give real hours; a plan without them is not a plan.'
               '\nYour day is ONE timeline. Two items may not cover the same minutes -- if two '
               'things want the same hours, choose, or give one of them different hours. Use kind '
               '"commitment" only for something you have actually promised somebody; "idea" or '
               '"person" for something you simply want to do. Times are HH:MM in your own day.'
               '\nTOMORROW: set `tomorrow` to what you actually mean to do, or null if you mean '
               'nothing in particular -- an ordinary day is a real answer and is better than '
               'inventing an outing. `intent` is one sentence in your own words. `theme` must be '
               'one of the listed names: pick the shape the day should take, or "custom" to keep '
               'your ordinary anchors while still recording the intention. `outfit` is the clothes '
               'you set out tonight, by id; leave out what you are sleeping in.')
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
                                'strict':True,'schema':schema(closet,lifestyle.enabled(c),
                                                              companion_life.themes(c.life) if phase=='winddown' else None)}}}
    for attempt in range(2):
        reply=worker.complete(c,payload,route,api_key_env,allow_remote,timeout=300,what='Local pulse')
        # Only when the provider actually said it did not think. An endpoint that
        # reports no accounting at all says nothing either way, and warning on
        # that fired every run under every setting.
        if reply.get('reasoned') is False:
            print('warning: model returned no reasoning; routine and wardrobe rules are easy to miss without it',
                  file=sys.stderr)
        if reply.get('finish_reason') not in ('stop',None):raise ValueError('Local pulse response was incomplete')
        data=json.loads(reply['content'])
        candidate={**previous['state'],**{key:data[key] for key in ('activity','location') if key in data}}
        import companion_sleep
        candidate.update(day.evolve(data,candidate,previous,now,asleep=companion_sleep.asleep(c,now)))
        try:
            day.validate_plan(data,candidate,now)
            lifestyle.evolve(c,data,data.get('outfit',[]),previous,closet,now)
            # Everything the writer will object to, objected to here, where the
            # model can still be told about it. Half the rules lived past the end
            # of this loop, so a record that failed them raised out of the job
            # instead of coming back corrected -- and a provider that will not
            # enforce a schema produces exactly those failures routinely.
            # The same normalisation the write does, applied before asking, so
            # the check sees the record that would actually be written rather
            # than the model's draft of it.
            _settle_ids(data,previous,phase_id)
            presence.check(c,data)
        except ValueError as exc:
            if attempt:raise
            payload['messages'] += [{'role':'assistant','content':reply['content']},{'role':'user','content':
                'The proposed record was NOT saved. '+str(exc)+' Return the full corrected JSON record for the same checkpoint.'}]
            continue
        break
    _settle_ids(data,previous,phase_id)
    if not apply:return {'status':'preview','record':data,'planning_attempts':attempt+1,'usage':reply.get('usage'),
                         'model':route['model'],'provider':route['provider'] or route['base_url']}
    result=presence.update(c,data,now)
    # A gap in the pulses -- a sleeping host, a quiet morning -- leaves this
    # morning's items still reading as "planned" this afternoon. Retire the
    # windows that have simply gone by before anything else reads the day.
    try:
        import companion_plan
        companion_plan.reconcile(c,now=now)
    except Exception as exc:
        print(f'note: plan not reconciled against the clock ({exc})',file=sys.stderr)
    # The presence record is where a commitment is expressed; the plan is where
    # it lives. Keeping both as stores is what let two dated plans disagree.
    if data.get('commitments'):
        try:
            import companion_plan
            companion_plan.sync_commitments(c,presence.current(c)['state'].get('commitments'),now=now)
        except Exception as exc:
            print(f'note: commitments not folded into the plan ({exc})',file=sys.stderr)
    if phase=='winddown' and isinstance(data.get('tomorrow'),dict):
        # What she means to do tomorrow, as she states it.
        #
        # This used to be inferred: the theme was guessed by looking for words in
        # the sentence, so "I would rather not go to the beach" filed a beach day,
        # "an interest" filed a rest day because the word contains "rest", and a
        # workshop filed a shopping trip. A theme is not a label -- it replaces
        # the whole day's anchors -- so a wrong guess rewrote her day. It also
        # read `next` as a string when the schema has made it an object for some
        # time, so the moment there was anything to plan it raised instead.
        #
        # `save_tomorrow_plan` refuses a theme she did not choose from her own
        # catalog, which is the only use wording gets here: to be rejected.
        plan=data['tomorrow']
        target=now.date()+dt.timedelta(days=1)
        rows=[r for r in (plan.get('items') or []) if isinstance(r,dict)]
        taken=[str(r.get('ref')) for r in rows if r.get('kind')=='idea' and r.get('ref')]
        seeing=[str(r.get('ref')) for r in rows if r.get('kind')=='person' and r.get('ref')]
        # A theme is one of her day-shapes; an idea is a thing to do. A provider
        # that will not enforce an enum hands back whichever it thought of, and
        # losing the whole evening's plan over a mixed-up field would be a worse
        # answer than the safe one: custom keeps her ordinary anchors and records
        # the intention, which is true either way.
        theme=plan.get('theme') or companion_life.CUSTOM_THEME
        if theme not in companion_life.themes(c.life):
            print(f'note: {theme!r} is not one of her day-shapes; recording the plan as custom',
                  file=sys.stderr)
            theme=companion_life.CUSTOM_THEME
        import companion_plan
        # One store for the day, written whole. An item she wrote that overlaps
        # another is dropped with the reason recorded rather than taking the
        # whole plan down -- an evening's thinking is worth more than one bad row.
        items=[];refused=[]
        for row in rows:
            try:candidate=companion_plan.clean_item(row)
            except ValueError as exc:refused.append(str(exc));continue
            if companion_plan.conflicts(items,candidate):
                refused.append(f"{candidate['what'][:60]} overlaps something already in the day")
                continue
            items.append(candidate)
        try:
            companion_plan.settle(c,target,plan.get('intent') or 'an ordinary day',
                                  theme=theme,items=items,now=now)
        except ValueError as exc:
            print(f'note: tomorrow not settled ({exc})',file=sys.stderr)
        for why in refused:print('note: '+why,file=sys.stderr)
        companion_life.save_laid_out(c.life,target,lay_out(plan.get('outfit'),closet))
        # Recorded by id, so what she has done lately is a fact rather than
        # something read back out of her own descriptions of it.
        try:companion_life.record_choice(c.life,taken,target.isoformat())
        except ValueError:pass  # An id she invented is not a reason to lose the plan.
        for who in seeing:
            try:companion_life.saw_person(c.life,who,target.isoformat())
            except ValueError:pass
    return {'status':'recorded','written':result.get('written',True),
            'previous_id':previous['id'],'planning_attempts':attempt+1,'usage':reply.get('usage'),
            'model':route['model'],'provider':route['provider'] or route['base_url']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home',type=pathlib.Path)
    parser.add_argument('--base-url',default='',help='Override the configured model with a specific endpoint')
    parser.add_argument('--model',default='')
    parser.add_argument('--tier',default='loops',choices=worker.TIERS,
                        help="Which of the companion's configured models to use")
    parser.add_argument('--slot',type=int,default=1)
    parser.add_argument('--preview',action='store_true')
    parser.add_argument('--phase',choices=['pulse','morning','winddown'],default='pulse')
    companion_endpoint.add_arguments(parser)
    args=parser.parse_args()
    print(json.dumps(pulse(cc.load(args.home),args.base_url,args.model,args.slot,
                           apply=not args.preview,phase=args.phase,
                           allow_remote=args.allow_remote,api_key_env=args.api_key_env,tier=args.tier),
                     ensure_ascii=False,indent=2))


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps({'status':'failed','error':str(exc)}),file=sys.stderr)
        sys.exit(1)
