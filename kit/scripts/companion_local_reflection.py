#!/usr/bin/env python3
"""Local structured reflections with deterministic periods and quote-backed writes.

Evidence stored in human ledgers is always an exact human quote the code selected
by ID. A fact's statement is the model's wording of that quote: it is screened for
obvious mismatches (companion_self.paraphrase_concerns) and held for review when
one is found, but it is not verified, and it is marked as a paraphrase.

The model selects and authors content; it cannot choose shell commands, file paths,
journal dates, human attribution, or fabricate the evidence stored in human ledgers.
"""
from __future__ import annotations
import argparse,datetime as dt,hashlib,json,pathlib,re,sqlite3,sys,urllib.parse,urllib.request
from zoneinfo import ZoneInfo
import companion_config as cc
import companion_endpoint
import companion_self as slf
import companion_life as life
import companion_journal as journal
import companion_checkin as checkin
import companion_notes as notes
import companion_loops as loops
from companion_platform import file_lock,atomic_write

KINDS=('daily','weekly','monthly','checkin')
# Plans refused as malformed for one period before the model is no longer asked.
MAX_ATTEMPTS=3
# Plans saved before facts carried their own statement lack one; a resumed plan
# from then is applied the way it was authored.
PLAN_CONTRACT=2
FACT_EXISTING_CHARS=6000

def journal_period(c,target,start,end,limit=10000):
    from companion_rotate import split_entries,entry_date
    path=journal.path_for(c,target)
    body=path.read_text(encoding='utf-8') if path.exists() else ''
    last=end.date() if end.time().replace(tzinfo=None)!=dt.time(0) else end.date()-dt.timedelta(days=1)
    selected=[entry for entry in split_entries(body)[1]
              if (day:=entry_date(entry)) is not None and start.date()<=day<=last]
    text='\n'.join(selected)
    return {'path':str(path),'entries_in_period':len(selected),'text':text[-limit:],
            'omitted_chars':max(0,len(text)-limit),'note':'Only dated entries inside the requested period are included.'}

def period(kind,now,flag=None):
    midnight=now.replace(hour=0,minute=0,second=0,microsecond=0)
    if kind=='daily':return midnight-dt.timedelta(days=1),midnight,(midnight-dt.timedelta(days=1)).date().isoformat()
    if kind=='weekly':return midnight-dt.timedelta(days=6),now,now.date().isoformat()
    if kind=='monthly':
        first=midnight.replace(day=1);previous=(first-dt.timedelta(days=1)).replace(day=1)
        return previous,first,now.date().isoformat()
    end=dt.datetime.fromisoformat(flag['last_end'])
    start=dt.datetime.fromisoformat(flag['last_reflected']) if flag.get('last_reflected') else end-dt.timedelta(days=1)
    return start,end,end.date().isoformat()

def messages(c,start,end,human_id,limit_chars=24000,after_id=0,end_inclusive=True):
    path=c.home/'state.db'
    if not path.exists():return [],False,end.isoformat(),0
    if not human_id:return [],False,end.isoformat(),0
    con=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True);con.row_factory=sqlite3.Row
    try:
        end_op='<=' if end_inclusive else '<'
        rows=con.execute(f"""SELECT m.id,m.session_id,m.role,m.content,m.timestamp FROM messages m
          JOIN sessions s ON s.id=m.session_id WHERE m.role IN ('user','assistant')
          AND s.source='telegram' AND s.user_id=?
          AND (m.timestamp>? OR (m.timestamp=? AND m.id>?)) AND m.timestamp{end_op}?
          AND coalesce(m._compressed_summary,0)=0 AND (m.active=1 OR m.compacted=1)
          ORDER BY m.timestamp,m.id""",
          (str(human_id),start.timestamp(),start.timestamp(),after_id,end.timestamp())).fetchall()
    finally:con.close()
    out=[];used=0;more=False
    for row in rows:
        if not row['content']:continue
        item=dict(row);item['id']=str(item['id'])
        if len(item['content'])+150>limit_chars:raise ValueError('A conversation message exceeds the local reflection batch budget; pending evidence retained for review')
        size=len(item['content'])+150
        if out and (used+size>limit_chars or len(out)>=100):more=True;break
        out.append(item);used+=size
    through=dt.datetime.fromtimestamp(out[-1]['timestamp'],end.tzinfo).isoformat() if more else end.isoformat()
    return out,more,through,int(out[-1]['id']) if more else 0

def quotation_sources(rows):
    result={}
    for row in rows:
        if row['role']!='user':continue
        content=row['content']
        pieces=re.split(r'(?<=[.!?])\s+|\n+',content)
        index=0
        for piece in pieces:
            piece=piece.strip()
            while piece:
                end=min(300,len(piece))
                if end<len(piece):
                    boundary=piece.rfind(' ',0,end)
                    if boundary>0:end=boundary
                quote=piece[:end].strip();piece=piece[end:].lstrip()
                if quote:
                    result[f"{row['id']}:{index}"]={**row,'content':quote};index+=1
    return result

def context(c,kind,start,end,day,rows):
    out={'kind':kind,'period_start':start.isoformat(),'period_end':end.isoformat(),'journal_date':day,
         'real_conversation_messages':rows,'existing_preferences':slf.summary(c)['preferences'],
         'existing_questions':slf.questions(c.life),'human_name':c.human}
    known=slf.fact_statements(c.human_dir,FACT_EXISTING_CHARS)
    out['existing_facts']=known['facts'];out['existing_facts_note']=known['note']
    if kind=='daily':
        digest=[];offset=0
        while True:
            page=life.history_digest(c.life,day,offset);digest.extend(page['episodes'])
            if page['next_offset'] is None:break
            offset=page['next_offset']
        # Ordinary days fit. Disclose exceptional oversize records; do not invent the omitted hours.
        out['imagined_episode_excerpts']=digest[:200];out['omitted_episodes']=max(0,len(digest)-200)
        out['journal_tail']=journal_period(c,'daily',start,end,6000)
    elif kind in ('weekly','monthly'):
        out['journal_tail']=journal_period(c,'daily',start,end,10000)
        out['previous_reflections']=journal_period(c,'weekly' if kind=='monthly' else kind,start,end,8000)
        out['self_authored_soul']=slf.soul_show(c)
    return out

def schema(kind,sources,question_ids):
    text=lambda n,empty=False:{'type':'string','minLength':0 if empty else 1,'maxLength':n}
    obj=lambda p:{'type':'object','properties':p,'required':list(p),'additionalProperties':False}
    arr=lambda item,n:{'type':'array','items':item,'maxItems':n}
    evidence={'quote_id':{'type':'string','enum':list(sources) or ['no-source']}}
    allowed=6 if sources else 0
    fields={'reflection':text(4000) if kind!='checkin' else {'type':'string','enum':['']},
      'preferences':arr(obj({'subject':text(120),'text':text(600),'valence':{'type':'string','enum':list(slf.VALENCE)}}),4),
      'questions':arr(text(400),2),
      'facts':arr(obj({**evidence,'category':{'type':'string','enum':list(slf.CATEGORIES)},'statement':text(400)}),allowed),
      'standing':arr(obj(evidence),allowed),'moments':arr(obj(evidence),allowed),
      'answers':arr(obj({**evidence,'question_id':{'type':'string','enum':question_ids or ['no-question']}}),4 if sources and question_ids else 0),
      'open_loops':arr(obj({**evidence,'title':text(120)}),3 if sources else 0),
      'soul_append':text(1000,True) if kind in ('weekly','monthly') else {'type':'string','enum':['']}}
    return obj(fields)

def request_plan(c,kind,data,sources,base_url,model,slot,allow_remote=False,api_key_env=''):
    companion_endpoint.verify(base_url,allow_remote,'Reflection')
    qs=[q['id'] for q in data['existing_questions'] if q['status'] in ('asked','open')]
    instructions=(c.soul.read_text(encoding='utf-8')+'\n\nWrite one concise structured reflection. '
      'Use the supplied period, not today by habit. Your own recorded days are your life, never evidence '
      'about the human. Do not invent research, human actions or conversations. You have no tools here. '
      'reflection is your diary entry for the day: first person, past tense, written the way a person '
      'writes at night, never mentioning records, sessions, logs or evidence, with no heading. '
      'Record only durable new preferences or questions; empty arrays are welcome. '
      f'questions contains actual new questions you may someday ask {c.human} directly, never existing IDs '
      'or already asked questions. Write each exactly as a natural question addressed to '
      f'{c.human}: use "you"/"your" when referring to {c.human}, not {c.human}\'s name, "the human", or '
      f'third-person pronouns for {c.human}. A question may still use he/she/they when referring to some '
      'other person. Do not invent a question merely to fill the array. '
      'facts, standing, moments, answers and open_loops select a quote_id from evidence_quotes. '
      'The code will store that exact human quote as the evidence, not a model paraphrase. '
      'A source is not evidence for anything it does not say. Facts describe durable information the human '
      'stated; never put your own feelings, weather, scenery or your own days there. '
      f'facts[].statement is a concise durable proposition about {c.human} supported completely by the '
      f'selected quote, for example {c.human} plays in a board-game group on Thursdays. It is not a quote, '
      f'not commentary about the quote (never "{c.human} said" or "{c.human} mentioned"), and not permission '
      'to infer additional facts. existing_facts lists what is already known (existing_facts_note says '
      'whether the list is complete). Do not record a fact that merely restates an existing fact. Repeated '
      'evidence for something already known is not a new fact. standing is only an '
      'enduring instruction the human explicitly wants applied in future conversations, such as Always ask before sending audio. '
      'A one-time request such as send me a photo, check it again or do not run anything in that situation '
      'is NOT a standing instruction. moments are meaningful real exchanges. Ignore routine greetings, '
      'punctuation-only replies and routine task chatter. '
      'answers must answer the selected existing question. open_loops are real unfinished commitments, '
      'not invented tasks. soul_append is empty for daily and checkin, and optional for weekly and monthly: '
      'only a lasting insight about yourself, never a human fact or changes to locked identity. '
      'Do not force a change. The code will write the dated journal and ledgers. '
      'For checkin, reflection and soul_append are empty; record only something that would otherwise be lost.')
    payload={'model':model,'messages':[{'role':'system','content':instructions},
             {'role':'user','content':json.dumps(data,ensure_ascii=False)}],
             'max_tokens':4096,'temperature':.6,'id_slot':slot,'cache_prompt':True,
             'reasoning_effort':'low','reasoning_budget_tokens':1024,'chat_template_kwargs':{'enable_thinking':True},
             'response_format':{'type':'json_schema','json_schema':{'name':'reflection','strict':True,'schema':schema(kind,sources,qs)}}}
    req=urllib.request.Request(base_url.rstrip('/')+'/chat/completions',
        data=json.dumps(companion_endpoint.shape(payload,base_url)).encode(),
        headers=companion_endpoint.headers(api_key_env))
    with urllib.request.urlopen(req,timeout=300) as r:reply=json.load(r)
    if not companion_endpoint.confirm_thinking(reply,base_url):
        print('warning: model returned no reasoning',file=sys.stderr)
    choice=reply['choices'][0]
    if choice.get('finish_reason')!='stop':raise ValueError('reflection was truncated; nothing recorded')
    return json.loads(choice['message']['content']),reply.get('usage')

def _transcript_wrapper(statement,human):
    """The exact shape this contract replaced: "<human> said: ...". Narrow on
    purpose; other prose is not policed here."""
    who=r'the (?:human|user)'+('|'+re.escape(human.strip()) if (human or '').strip() else '')
    return bool(re.match(r'^\W*(?:'+who+r')\s+(?:said|mentioned|told (?:me|you|us))\b',statement.strip(),re.I))

def question_concern(question,human):
    """How a new question falls short of being asked to the human, if it does.

    ('omit', why) is for wording no person would be asked: "the human", "the
    user", or a bare question ID. ('warn', why) is for a question that uses
    the human's name as a third person and never says "you"; it may still be a
    fine question ("What will you do tomorrow?" to someone named Will, or
    "Robin, how was the trip?"), so it is kept and reported. A name is matched
    with its case, as a name is written. Neither is a reason to lose the rest
    of a reflection."""
    q=question.strip()
    if re.fullmatch(r'q-[a-f0-9]+',q):return ('omit','an existing question ID, not a new question')
    if human is None:return None
    if re.search(r'\bthe (?:human|user)\b',q,re.I):return ('omit','calls the person "the human" or "the user"')
    name=(human or '').strip()
    if not name or name.lower() in ('the user','the human'):return None
    named=re.compile(r'(?<!\w)'+re.escape(name)+r'(?!\w)')
    unaddressed=re.sub(r'^\W*'+re.escape(name)+r'\s*,|,\s*'+re.escape(name)+r'\W*$','',q)
    if named.search(unaddressed) and not re.search(r"\b(?:you|your|yours|yourself)\b",q,re.I):
        return ('warn',f'names {name} in the third person and never says "you"')
    return None

def validate(plan,kind,sources,question_ids,human='',legacy=False):
    """Refuse a plan whose structure or evidence is wrong; that is fatal.

    Returns the optional parts that are merely below standard, as
    {'omitted': [...], 'warnings': [...]}: a question in `omitted` is left
    out when the plan is applied, and the run reports it rather than calling
    itself clean. `legacy` is only for resuming a plan saved under the
    previous contract, whose facts carried no statement and whose questions
    were never checked."""
    diagnostics={'omitted':[],'warnings':[]}
    expected={'reflection','preferences','questions','facts','standing','moments','answers','open_loops','soul_append'}
    if not isinstance(plan,dict) or set(plan)!=expected:raise ValueError('unexpected reflection fields')
    def text(value,limit,empty=False):
        if not isinstance(value,str) or len(value)>limit or (not empty and not value.strip()):raise ValueError('invalid reflection text')
    text(plan['reflection'],4000,kind=='checkin');text(plan['soul_append'],1000,True)
    if kind=='checkin' and plan['reflection']:raise ValueError('checkin cannot write a journal')
    if kind not in ('weekly','monthly') and plan['soul_append']:raise ValueError("soul_append must be empty for a "+kind+" reflection (only weekly/monthly may edit SOUL); drop it and keep the journal")
    if any(line.startswith(('## ','# ')) for line in plan['reflection'].splitlines()):raise ValueError('journal headings are supplied by code')
    for key,cap in [('preferences',4),('questions',2),('facts',6),('standing',6),('moments',6),('answers',4),('open_loops',3)]:
        if not isinstance(plan[key],list) or len(plan[key])>cap:raise ValueError('invalid '+key+' list')
    for p in plan['preferences']:
        if set(p)!= {'subject','text','valence'} or p['valence'] not in slf.VALENCE:raise ValueError('invalid preference')
        text(p['subject'],120);text(p['text'],600)
    for q in plan['questions']:
        text(q,400)
        # A legacy plan's questions were never checked for wording; only an ID is left out.
        if concern:=question_concern(q,None if legacy else human):
            level,why=concern
            diagnostics['omitted' if level=='omit' else 'warnings'].append({'kind':'question','text':q,'reason':why})
    for key in ('facts','standing','moments','answers','open_loops'):
        for p in plan[key]:
            allowed={'quote_id'}|({'category'}|(set() if legacy else {'statement'}) if key=='facts' else {'question_id'} if key=='answers' else {'title'} if key=='open_loops' else set())
            if not isinstance(p,dict) or set(p)!=allowed:raise ValueError('invalid '+key+' entry')
            source=sources.get(p['quote_id'])
            if not source or source['role']!='user':raise ValueError('human evidence must select a trusted user quote')
            if key=='facts' and p['category'] not in slf.CATEGORIES:raise ValueError('invalid category')
            if key=='facts' and not legacy:
                text(p['statement'],400)
                if _transcript_wrapper(p['statement'],human):
                    raise ValueError('a fact statement is a proposition about the human, not a transcript ("X said: ...")')
            if key=='answers' and p['question_id'] not in question_ids:raise ValueError('unknown question')
            if key=='open_loops':text(p['title'],120)
    return diagnostics

def usable(plan,diagnostics):
    """The plan as applied: omitted questions taken out, nothing else changed."""
    dropped={d['text'] for d in diagnostics['omitted'] if d['kind']=='question'}
    return {**plan,'questions':[q for q in plan['questions'] if q not in dropped]}

def apply_plan(c,kind,day,plan,sources,now):
    results=[]
    def save(label,result):results.append({'kind':label,**result})
    for p in plan['preferences']:
        ident=slf._mkid('pref',p['valence'],p['subject'].lower(),now.date().isoformat())
        if any(row.get('id')==ident for row in slf._read(c.life/'preferences.jsonl')):
            save('pref',{'written':False,'reason':'this subject and valence are already recorded today'});continue
        save('pref',slf.record_pref(c.life,p['text'],now,p['valence'],p['subject'],c.agent))
    for q in plan['questions']:save('ask',slf.ask(c.life,q,now))
    for key in ('facts','standing','moments','answers','open_loops'):
        for p in plan[key]:
            s=sources[p['quote_id']];when=dt.datetime.fromtimestamp(s['timestamp'],now.tzinfo).isoformat()
            source=f"session:{s['session_id']} message:{s['id']} {when}"
            quote=s['content'];evidence=f'{when}: {quote}'
            if key=='facts':
                # The statement is the readable memory; the quote is why it may be remembered.
                # A written statement is the model's words, so it is screened against the
                # quote and held for a person when it obviously says something else.
                if 'statement' in p:
                    statement=p['statement'].strip()
                    concerns=slf.paraphrase_concerns(statement,quote,(c.human,c.agent))
                    out=(slf.hold_fact(c.human_dir,statement,evidence,now,p['category'],source,concerns,c.human) if concerns else
                         slf.record_fact(c.human_dir,statement,evidence,now,p['category'],'stated',source,human=c.human,
                                         statement_origin='model_paraphrase'))
                else:
                    out=slf.record_fact(c.human_dir,f'{c.human} said: "{quote}"',evidence,now,p['category'],'stated',source,human=c.human)
            elif key=='standing':out=notes.add_standing(c,{'instruction':quote,'evidence':evidence,'scope':''},now)
            elif key=='moments':out=notes.add_moment(c,{'moment':'note','text':f'{c.human} said: "{quote}"','happened_on':when[:10]},now)
            elif key=='answers':
                current=next((q for q in slf.questions(c.life) if q['id']==p['question_id']),{})
                out=({'written':False,'reason':'answer already recorded'} if current.get('status')=='answered' and current.get('answer')==quote else slf.resolve(c.life,p['question_id'],'answered',now,quote))
            else:
                exists=any(l['title'].lower()==p['title'].lower() for l in loops.loops(c,None))
                out=({'written':False,'reason':'this loop title already exists'} if exists else loops.add(c,{'title':p['title'],'detail':f'{c.human}: {quote} ({source})','gentle_use':f'Raise only when relevant; do not press {c.human} for a reply.'},now))
            save(key,out)
    if plan['soul_append']:
        current=slf.soul_show(c)['self_authored']
        save('soul',{'written':False,'reason':'insight already present'} if plan['soul_append'] in current else slf.soul_write(c,plan['soul_append'],'append',now))
    if kind!='checkin':save('journal',journal.append(c,kind,{'date':day,'text':plan['reflection']}))
    return results

def reflect(c,kind,base_url,model,human_id='',slot=1,now=None,planner=None,
            allow_remote=False,api_key_env=''):
    now=now or dt.datetime.now(ZoneInfo(c.timezone));folder=c.life/'local-reflections';folder.mkdir(parents=True,exist_ok=True)
    with file_lock(folder/(kind+'.lock')):
        flag=checkin.read(c) if kind=='checkin' else None
        if kind=='checkin' and not flag.get('pending'):return {'status':'skipped','reason':'no pending conversation'}
        start,end,day=period(kind,now,flag)
        if kind=='checkin' and not (c.home/'state.db').exists():raise ValueError('pending conversation database is missing')
        rows,more,through,through_id=messages(c,start,end,human_id,after_id=int((flag or {}).get('last_reflected_id',0)),end_inclusive=kind=='checkin')
        if kind=='checkin' and not human_id:raise ValueError('configure the trusted human user ID before reflecting conversations')
        sources=quotation_sources(rows)
        key=(kind+'-'+day) if kind!='checkin' else 'checkin-'+hashlib.sha256((start.isoformat()+end.isoformat()+through+str(through_id)).encode()).hexdigest()[:20]
        path=folder/(key+'.json')
        saved=json.loads(path.read_text()) if path.exists() else None
        if saved and saved.get('complete'):return {'status':'skipped','reason':'this reflection was already committed','id':key}
        data=context(c,kind,start,end,day,rows);data['more_conversation_messages']=more
        data['evidence_quotes']=[{'quote_id':key,'quote':value['content']} for key,value in sources.items()]
        attempts_path=folder/(key+'.attempts.json')
        attempts=json.loads(attempts_path.read_text()) if attempts_path.exists() else {'count':0,'errors':[]}
        question_ids=[q['id'] for q in data['existing_questions']]
        if saved:
            plan=saved['plan'];sources=saved['sources'];usage=saved.get('usage')
            legacy=saved.get('contract',1)<PLAN_CONTRACT
            diagnostics=validate(plan,kind,sources,question_ids,c.human,legacy)
        else:
            if attempts['count']>=MAX_ATTEMPTS:
                return {'status':'held','id':key,'attempts':attempts['count'],'errors':attempts['errors'],
                        'reason':f'{attempts["count"]} plans for this period were refused; the model is not asked again. '
                                 f'Rejected plans are kept beside {attempts_path.name} for review.'}
            plan,usage=(planner or request_plan)(c,kind,data,sources,base_url,model,slot,
                                                 allow_remote,api_key_env)
            try:diagnostics=validate(plan,kind,sources,question_ids,c.human)
            except ValueError as exc:
                attempts['count']+=1;attempts['errors'].append({'at':now.isoformat(),'error':str(exc)})
                atomic_write(folder/f'{key}.rejected-{attempts["count"]}.json',json.dumps({'error':str(exc),'plan':plan},ensure_ascii=False,indent=2))
                atomic_write(attempts_path,json.dumps(attempts,ensure_ascii=False,indent=2))
                raise
            saved={'id':key,'kind':kind,'day':day,'plan':plan,'sources':sources,'usage':usage,'authored_at':now.isoformat(),
                   'contract':PLAN_CONTRACT,'diagnostics':diagnostics,'complete':False}
            atomic_write(path,json.dumps(saved,ensure_ascii=False,indent=2))
        results=apply_plan(c,kind,day,usable(plan,diagnostics),sources,dt.datetime.fromisoformat(saved['authored_at']))
        if kind=='checkin':
            # A new conversation can finish during inference. Advance only the
            # evidence watermark we processed; never clear a newer pending flag.
            with file_lock(checkin.path_for(c).with_suffix('.json.lock')):
                state=checkin.read(c)
                state['last_reflected']=through;state['last_reflected_id']=through_id
                if state.get('last_end')==flag.get('last_end') and not more:state['pending']=0
                atomic_write(checkin.path_for(c),json.dumps(state,ensure_ascii=False,indent=2))
        saved.update(complete=True,results=results);atomic_write(path,json.dumps(saved,ensure_ascii=False,indent=2))
        held=[r for r in results if r.get('held')]
        return {'status':'recorded','id':key,'results':results,'usage':usage,'more_conversation_messages':more,
                'clean':not (diagnostics['omitted'] or diagnostics['warnings'] or held),
                'omitted':diagnostics['omitted'],'warnings':diagnostics['warnings'],'held_facts':len(held)}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--home',type=pathlib.Path)
    p.add_argument('--kind',choices=KINDS,required=True);p.add_argument('--base-url',required=True);p.add_argument('--model',required=True)
    p.add_argument('--human-user-id',default='');p.add_argument('--slot',type=int,default=1)
    companion_endpoint.add_arguments(p)
    a=p.parse_args()
    print(json.dumps(reflect(cc.load(a.home),a.kind,a.base_url,a.model,a.human_user_id,a.slot,
                             allow_remote=a.allow_remote,api_key_env=a.api_key_env),
                     ensure_ascii=False,indent=2))
if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps({'status':'failed','error':str(exc)}),file=sys.stderr);sys.exit(1)
