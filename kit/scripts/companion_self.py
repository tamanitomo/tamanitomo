#!/usr/bin/env python3
"""Reflection stores: evidence-backed facts about the human, the agent's own
preferences, its curiosity queue, and the block of SOUL.md it writes itself.

Three ledgers, separated by provenance and never merged:
  <people>/<human>/facts.jsonl        claims about the human; evidence REQUIRED
  <life>/preferences.jsonl            what the agent likes/dislikes/feels; no evidence needed
  <life>/questions.jsonl              things it wonders, and the answers it actually got

Append-only. Sizes come from the model's context window, so nothing is ever cut
without saying so.
"""
from __future__ import annotations
import uuid
import argparse, datetime as dt, hashlib, json, os, pathlib, re, sys, unicodedata
from zoneinfo import ZoneInfo
from companion_platform import file_lock, atomic_write
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc

BEGIN='<!-- COMPANION-SELF-AUTHORED:BEGIN -->'
END='<!-- COMPANION-SELF-AUTHORED:END -->'
CATEGORIES=('likes','dislikes','people','places','work','school','health','history','logistics','other')
VALENCE=('like','dislike','curious','mixed')
CONFIDENCE=('stated','observed','inferred')
MIN_USEFUL=90

def _tz(c):
    try:return ZoneInfo(c.timezone)
    except Exception:return ZoneInfo('UTC')

def _now(tz,now=None):
    now=now or dt.datetime.now(tz)
    if now.tzinfo is None:raise ValueError('timezone required')
    return now.astimezone(tz)

def _read(path,kind=None):
    rows=[]
    try:
        with pathlib.Path(path).open(encoding='utf-8') as f:
            for line in f:
                line=line.strip()
                if not line:continue
                try:row=json.loads(line)
                except ValueError:continue
                if kind and row.get('kind')!=kind:continue
                rows.append(row)
    except FileNotFoundError:pass
    return rows

def _append(path,row,dedupe_id=True,guard=None):
    """Append one row. `guard` runs under the same lock after the ID check; a
    dict it returns is the answer instead of a write."""
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with file_lock((path.parent/('.'+path.name+'.lock'))):
        if dedupe_id:
            for e in _read(path):
                if e.get('id')==row['id']:
                    ignored={'recorded_at','provenance'}
                    if {k:v for k,v in e.items() if k not in ignored}!={k:v for k,v in row.items() if k not in ignored}:
                        raise ValueError('Entry ID already exists with different content; original retained')
                    return {'written':False,'entry':e}
        if guard and (refused:=guard()):return refused
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
        with os.fdopen(fd,'a', encoding='utf-8') as f:
            f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
    return {'written':True,'entry':row}

def _mkid(prefix,*parts):return prefix+'-'+hashlib.sha256('|'.join(parts).encode()).hexdigest()[:16]

def _text(value,limit,label):
    value=(value or '').strip()
    if not value or len(value)>limit:raise ValueError(f'{label} required, max {limit} chars')
    return value

# ---- ledgers -------------------------------------------------------------
_QUOTES=str.maketrans({'\u2018':"'",'\u2019':"'",'\u201a':"'",'\u201b':"'",'\u2032':"'",
                       '\u201c':'"','\u201d':'"','\u201e':'"','\u201f':'"','\u2033':'"'})

def canonical_statement(text):
    """The form two fact statements must share to be the same proposition.

    Only differences that cannot change meaning are erased: Unicode form, case,
    whitespace, quote style, and punctuation that is not inside a word or
    number ("tea." == "tea", but "4.5" != "45" and "Robin's" keeps its
    apostrophe). Anything more generous would merge different memories.
    """
    text=unicodedata.normalize('NFKC',str(text or '')).translate(_QUOTES).casefold()
    text=re.sub(r"(?<!\w)[^\w\s]+|[^\w\s]+(?!\w)",' ',text)
    return ' '.join(text.split())
def record_fact(root,statement,evidence,now,category='other',confidence='stated',
                source='',supersedes='',human='the human'):
    if category not in CATEGORIES:raise ValueError(f'category must be one of {CATEGORIES}')
    if confidence not in CONFIDENCE:raise ValueError(f'confidence must be one of {CONFIDENCE}')
    statement=_text(statement,400,'statement');evidence=_text(evidence,600,'evidence')
    urls_only = re.sub(r'https?://\S+', '', evidence).strip()
    if not urls_only or urls_only in (';', ',', '-', '.', '|'):
        raise ValueError(f'evidence cannot be only web URLs; facts about {human} require actual interaction or observation')
    row={'id':_mkid('fact',category,statement.lower(),evidence,confidence,source,supersedes),'kind':'human_fact','category':category,
         'statement':statement,'evidence':evidence,'source':(source or '').strip()[:200],
         'confidence':confidence,'status':'active','supersedes':(supersedes or '').strip()[:80],
         'recorded_at':now.isoformat(),
         'provenance':f'Recorded from stated or observed evidence about {human}; not imagined'}
    if supersedes and not any(f['id']==supersedes for f in facts(root)):
        raise ValueError('supersedes must refer to an active fact')
    key=canonical_statement(statement)
    def already_known():
        # The same proposition is one memory whatever its category, source or
        # evidence. A correction may restate the fact it replaces. Only an exact
        # canonical match is refused; near-matches are for duplicate_facts().
        for f in facts(root):
            if f['id']!=row['supersedes'] and canonical_statement(f.get('statement'))==key:
                return {'written':False,'reason':'fact already recorded','duplicate_of':f['id']}
        return None
    return _append(pathlib.Path(root)/'facts.jsonl',row,guard=already_known)

def record_pref(root,text,now,valence='like',subject='',agent='the companion'):
    if valence not in VALENCE:raise ValueError(f'valence must be one of {VALENCE}')
    text=_text(text,600,'text');subject=(subject or text)[:120].strip()
    # Pref IDs are keyed on (valence, subject, day) -- so two different feelings filed under the
    # same subject on the same day silently collapse into one row: the first stands, the second is
    # dropped with written:false and no error. Make the collision visible rather than silent.
    row={'id':_mkid('pref',valence,subject.lower(),now.date().isoformat()),
         'kind':'companion_preference','valence':valence,'subject':subject,'text':text,
         'recorded_at':now.isoformat(),'provenance':f"{agent}'s own authored preference or feeling"}
    return _append(pathlib.Path(root)/'preferences.jsonl',row)

def ask(root,text,now):
    text=_text(text,400,'question')
    has_qmark = '?' in text
    has_qword = any(text.lower().startswith(w) for w in ('who','what','when','where','why','how','is','are','can','could','would','do','does','did','will','should','have','has','if','whether'))
    if not (has_qmark or has_qword):
        raise ValueError('curiosity questions must be an inquiry (end in ? or begin with a question word)')
    row={'id':_mkid('q',text.lower()),'kind':'curiosity_question','text':text,'status':'open',
         'asked_at':'','answered_at':'','answer':'','recorded_at':now.isoformat()}
    return _append(pathlib.Path(root)/'questions.jsonl',row)

def resolve(root,qid,status,now,answer=''):
    if status not in ('asked','answered','dropped'):raise ValueError('invalid status')
    if status=='answered':answer=_text(answer,800,'answer')
    path=pathlib.Path(root)/'questions.jsonl'
    if not any(r.get('id')==qid for r in _read(path,kind='curiosity_question')):
        raise ValueError('unknown question id')
    return _append(path,{'id':qid,'kind':'curiosity_question_update','status':status,
                         'answer':(answer or '').strip(),'updated_at':now.isoformat()},dedupe_id=False)

def questions(root,status=None):
    """Fold updates onto originals so the latest status wins."""
    latest={}
    for r in _read(pathlib.Path(root)/'questions.jsonl'):
        qid=r.get('id')
        if r.get('kind')=='curiosity_question':latest.setdefault(qid,dict(r))
        elif r.get('kind')=='curiosity_question_update' and qid in latest:
            q=latest[qid];q['status']=r.get('status',q['status'])
            if r.get('answer'):q['answer']=r['answer']
            if r.get('status')=='asked':q['asked_at']=r.get('updated_at','')
            if r.get('status')=='answered':q['answered_at']=r.get('updated_at','')
    out=list(latest.values())
    return [q for q in out if q['status']==status] if status else out

def facts(root,category=None):
    """Active facts only; corrections and retractions retain the original history."""
    history=_read(pathlib.Path(root)/'facts.jsonl')
    rows=[r for r in history if r.get('kind')=='human_fact']
    dead={r['supersedes'] for r in rows if r.get('supersedes')}
    dead.update(r['fact_id'] for r in history if r.get('kind')=='human_fact_retraction')
    seen={}
    for r in rows:
        if r['id'] in dead or r.get('status','active')!='active':continue
        seen[r['id']]=r
    rows=list(seen.values())
    return [r for r in rows if r['category']==category] if category else rows

def fact_statements(root,limit_chars=6000):
    """Active fact statements, newest first, within a character budget, so a
    reflection can tell whether something is actually new. Evidence is left out
    on purpose; the statement is what would be restated."""
    rows=sorted(facts(root),key=lambda f:f.get('recorded_at',''),reverse=True)
    kept,used=[],0
    for f in rows:
        item={'id':f['id'],'category':f.get('category','other'),'statement':f.get('statement','')}
        size=len(item['statement'])+len(item['category'])+40
        if used+size>limit_chars:break
        kept.append(item);used+=size
    omitted=len(rows)-len(kept)
    return {'facts':kept,'omitted':omitted,
            'note':(f'{omitted} older facts are not listed here for space; this list is not everything already known.'
                    if omitted else 'This is every fact currently recorded.')}

_FILLER=frozenset('a an the to in into for of on at by from with and his her their its my your'.split())
_DISTINCT=re.compile(r"^(\d.*|no|not|never|none|nor|doesn't|don't|didn't|isn't|wasn't|won't|can't|cannot|"
                     r"first|second|third|fourth|fifth|last|next|previous|other|another|former|latter|"
                     r"one|two|three|four|five|six|seven|eight|nine|ten)$")

def _words(statement):
    return {w for w in re.sub(r"'s\b",'',canonical_statement(statement)).split() if w not in _FILLER}

def duplicate_facts(root,threshold=.6):
    """Pairs of active facts that may say the same thing, for a person to review.

    Report only: nothing is retracted, superseded or merged. A pair whose words
    differ by a number, an ordinal or a negation is flagged as such rather than
    hidden, because "likes"/"dislikes" and "first"/"second" are the cases where
    a guess would be worst.
    """
    rows=facts(root);words=[_words(f.get('statement')) for f in rows];out=[]
    for i in range(len(rows)):
        for j in range(i+1,len(rows)):
            a,b=words[i],words[j]
            if not a or not b:continue
            shared=len(a&b);score=shared/len(a|b)
            contained=a<=b or b<=a
            if score<threshold and not (contained and score>=.5 and min(len(a),len(b))>=4):continue
            differ=sorted(a^b)
            reason=('identical wording' if not differ else
                    'one statement contains every word of the other' if contained else
                    f'{round(score*100)}% of content words shared')
            if any(_DISTINCT.match(w) for w in differ):reason+='; differs by a number, ordinal or negation -- probably distinct'
            out.append({'similarity':round(score,3),'reason':reason,'differing_words':differ,
                        'facts':[{k:rows[x].get(k) for k in ('id','category','statement','evidence','recorded_at')} for x in (i,j)]})
    out.sort(key=lambda p:-p['similarity'])
    return {'candidates':out,'count':len(out),
            'note':'Candidates only. Nothing has been changed; retract or correct a fact yourself if it is really a duplicate.'}

def retract_fact(root,fact_id,reason,now):
    """Withdraw a mistaken claim without inventing a replacement claim."""
    reason=_text(reason,600,'reason')
    path=pathlib.Path(root)/'facts.jsonl'
    if not any(r.get('id')==fact_id for r in _read(path,kind='human_fact')):
        raise ValueError('unknown fact id')
    return _append(path,{'id':_mkid('retract',fact_id),'kind':'human_fact_retraction',
                        'fact_id':fact_id,'reason':reason,'recorded_at':now.isoformat()})

def _budget(items,limit,noun,how):
    """Fit what we can, then say plainly what is held back. Never a silent cut."""
    if limit<MIN_USEFUL:
        return f'[{len(items)} {noun} recorded; no room in this context window — read with {how}]' if items else ''
    kept,used=[],0
    for line in items:
        if used+len(line)+1>limit:break
        kept.append(line);used+=len(line)+1
    hidden=len(items)-len(kept)
    text='\n'.join(kept)
    if hidden:text+=f'\n[+{hidden} more {noun} not shown here — all of it is kept; read it with {how}]'
    return text

def summary(c,budgets=None):
    b=budgets or c.budgets()
    rows=facts(c.human_dir)
    order={k:i for i,k in enumerate(CATEGORIES)}
    rows.sort(key=lambda f:(order.get(f['category'],99),f['recorded_at']),reverse=True)
    prof=_budget([f"{f['category']} [{f['confidence']}]: {f['statement']} (evidence: {f['evidence']}; source: {f.get('source') or 'ledger'})" for f in rows],b['facts'],'facts',
                 'companion_self.py profile')
    prefs=_read(c.life/'preferences.jsonl',kind='companion_preference')
    pref=_budget([f"{p['valence']}: {p['subject']} — {p['text']}" for p in reversed(prefs)],
                 b['preferences'],'recorded feelings','companion_self.py pref-history')
    openq=[q['text'] for q in questions(c.life,'open')]
    qs=_budget(list(reversed(openq)),b['questions'],'open questions',
               'companion_self.py wonder --status open')
    return {'human_profile':prof,'preferences':pref,'open_questions':qs,
            'counts':{'facts':len(rows),'preferences':len(prefs),'open_questions':len(openq)}}

# ---- the block of SOUL.md the agent owns ---------------------------------
def _split_soul(path):
    text=pathlib.Path(path).read_text(encoding='utf-8')
    if text.count(BEGIN)!=1 or text.count(END)!=1:
        raise ValueError('SOUL.md needs exactly one self-authored block; run: companion_self.py soul --init')
    head,rest=text.split(BEGIN,1);body,tail=rest.split(END,1)
    if not head.endswith('\n'):raise ValueError('malformed block start')
    return head,body,tail

def soul_show(c):
    size=len(c.soul.read_text(encoding='utf-8'));_,body,_=_split_soul(c.soul)
    return {'self_authored':body.strip('\n'),'soul_chars':size,'warn_at':c.soul_warn,
            'hard_cap':c.soul_cap,'headroom':c.soul_warn-size}

def soul_write(c,text,mode='append',now=None,backups=None):
    """Rewrite ONLY the self-authored block; everything else is verified unchanged."""
    now=now or dt.datetime.now(_tz(c))
    text=(text or '').strip()
    if mode not in ('append','set'):raise ValueError('mode must be append or set')
    if mode=='append' and not text:raise ValueError('nothing to append')
    # Resolve first: an atomic os.replace() onto a symlink path replaces the LINK
    # with a regular file, orphaning the canonical copy in the vault.
    path=pathlib.Path(c.soul).resolve();backups=pathlib.Path(backups or c.soul_backups)
    backups.mkdir(parents=True,exist_ok=True)
    with file_lock(path.parent/('.'+path.name+'.lock')):
        original=path.read_text(encoding='utf-8')
        head,body,tail=_split_soul(path);body=body.strip('\n')
        new=(body+'\n'+text).strip('\n') if mode=='append' else text
        if BEGIN in new or END in new:raise ValueError('Self-authored text cannot contain block markers')
        # Some things are not hers to change. Restating them in her own block is
        # the same thing as editing them, so it is refused there too.
        try:
            import companion_identity
            tripped=companion_identity.guard(c,new)
        except (OSError,ValueError,ImportError):tripped=[]
        if tripped:
            raise ValueError('Refused: this block restates something that is not yours to change ('
                             +', '.join(tripped)+'). Those live in locked sections of SOUL.md. '
                             'Write about who you are becoming instead.')
        out=head+BEGIN+'\n'+new+'\n'+END+tail
        backup=backups/('SOUL.md.'+now.strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8])
        atomic_write(backup,original)
        if path.read_text(encoding='utf-8')!=original:raise ValueError('SOUL changed during editing; retry')
        atomic_write(path,out)
    h2,b2,t2=_split_soul(path)
    if (h2,t2)!=(head,tail):raise ValueError('refused: content outside the self-authored block changed')
    size=len(path.read_text(encoding='utf-8'))
    warn=''
    if size>c.soul_warn:
        warn=(f'SOUL.md is {size} chars; this model truncates a context file past {c.soul_cap}. '
              'Consolidate the block — sharpen lines rather than dropping them, the detail is safe in the ledgers.')
    return {'written':True,'mode':mode,'self_authored':b2.strip('\n'),'soul_chars':size,
            'warn_at':c.soul_warn,'warning':warn}

def soul_init(c,anchor=None,backups=None):
    """Open a block the agent owns without altering a word of the existing text."""
    path=pathlib.Path(c.soul).resolve()
    with file_lock(path.parent/('.'+path.name+'.lock')):
        text=path.read_text(encoding='utf-8')
        if BEGIN in text or END in text:
            _split_soul(path)
            return {'written':False,'reason':'block already present'}
        block=BEGIN+'\n'+f'_{c.agent} writes this part {c.refl()}. {c.human} does not edit it._\n'+END+'\n\n'
        i=text.find(anchor) if anchor else -1
        out=(text[:i]+block+text[i:]) if i>=0 else text+'\n\n'+block
        backups=pathlib.Path(backups or c.soul_backups);backups.mkdir(parents=True,exist_ok=True)
        backup=backups/'SOUL.md.pre-init'
        if backup.exists():backup=backup.with_name(backup.name+'-'+uuid.uuid4().hex[:8])
        atomic_write(backup,text)
        if path.read_text(encoding='utf-8')!=text:raise ValueError('SOUL changed during initialization; retry')
        atomic_write(path,out)
    return {'written':True,'soul_chars':len(out),'appended':i<0}


# ---- batch input ---------------------------------------------------------
LEDGER_KINDS=('fact','retract_fact','pref','ask','resolve','soul')

def _entries(data):
    """Accept a bare list or {"entries": [...]}, and nothing else."""
    if isinstance(data,dict):data=data.get('entries')
    if not isinstance(data,list):raise ValueError('batch file must hold a list of entries, or {"entries": [...]}')
    if not data:raise ValueError('batch file holds no entries')
    if len(data)>200:raise ValueError('batch file holds more than 200 entries; split it')
    return data

def _apply(c,entry,now):
    """One batch entry through the same code paths the flags use."""
    if not isinstance(entry,dict):raise ValueError('each entry must be a JSON object')
    kind=(entry.get('kind') or '').strip()
    if kind not in LEDGER_KINDS:raise ValueError(f'kind must be one of {LEDGER_KINDS}')
    if kind=='retract_fact':
        return retract_fact(c.human_dir,entry.get('id',''),entry.get('reason'),now)
    if kind=='fact':
        return record_fact(c.human_dir,entry.get('statement'),entry.get('evidence'),now,
                           entry.get('category','other'),entry.get('confidence','stated'),
                           entry.get('source',''),entry.get('supersedes',''),c.human)
    if kind=='pref':
        return record_pref(c.life,entry.get('text'),now,entry.get('valence','like'),
                           entry.get('subject',''),c.agent)
    if kind=='ask':
        return ask(c.life,entry.get('text'),now)
    if kind=='resolve':
        return resolve(c.life,entry.get('id',''),entry.get('status',''),now,entry.get('answer',''))
    mode=entry.get('mode','append')
    return soul_write(c,entry.get('text'),mode,now)

def ledger_batch(c,path,now):
    """Record a whole reflection from one JSON file.

    Prose written by the model never goes through a shell argument this way, so
    apostrophes and newlines survive. Entries are applied in order and every
    ledger here is append-only with de-duplicating ids, so re-running the same
    file after a partial failure records nothing twice.
    """
    entries=_entries(json.loads(pathlib.Path(path).read_text(encoding='utf-8')))
    results=[]
    for i,entry in enumerate(entries):
        try:
            out=_apply(c,entry,now)
        except (ValueError,OSError,TypeError,KeyError) as exc:
            results.append({'index':i,'kind':(entry.get('kind') if isinstance(entry,dict) else None),
                            'ok':False,'error':str(exc)})
            return {'applied':sum(1 for r in results if r.get('ok')),'failed_at':i,
                    'results':results,
                    'note':'Stopped at the first bad entry. Fix it and re-run the same file; '
                           'entries already recorded are not recorded twice.'}
        results.append({'index':i,'kind':entry['kind'],'ok':True,
                        'id':(out.get('entry') or {}).get('id') if 'entry' in out else None,
                        'written':out.get('written',True)})
    return {'applied':len(results),'failed_at':None,'results':results}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--home',type=pathlib.Path)
    s=p.add_subparsers(dest='cmd',required=True)
    f=s.add_parser('fact');f.add_argument('--statement',required=True);f.add_argument('--evidence',required=True)
    f.add_argument('--category',default='other',choices=CATEGORIES)
    f.add_argument('--confidence',default='stated',choices=CONFIDENCE)
    f.add_argument('--source',default='');f.add_argument('--supersedes',default='')
    rf=s.add_parser('retract-fact');rf.add_argument('--id',required=True);rf.add_argument('--reason',required=True)
    pr=s.add_parser('pref');pr.add_argument('--text',required=True)
    pr.add_argument('--valence',default='like',choices=VALENCE);pr.add_argument('--subject',default='')
    a_=s.add_parser('ask');a_.add_argument('--text',required=True)
    r=s.add_parser('resolve');r.add_argument('--id',required=True)
    r.add_argument('--status',required=True,choices=['asked','answered','dropped']);r.add_argument('--answer',default='')
    s.add_parser('profile');s.add_parser('summary')
    df=s.add_parser('duplicate-facts',help='List likely duplicate facts for review; changes nothing')
    df.add_argument('--threshold',type=float,default=.6)
    w=s.add_parser('wonder');w.add_argument('--status',choices=['open','asked','answered','dropped'])
    ph=s.add_parser('pref-history');ph.add_argument('--valence',choices=VALENCE)
    so=s.add_parser('soul');so.add_argument('--show',action='store_true');so.add_argument('--init',action='store_true')
    so.add_argument('--append');so.add_argument('--set',dest='set_',action='store_true')
    lg=s.add_parser('ledger',help='Record many entries from one JSON file')
    lg.add_argument('--file',type=pathlib.Path,required=True)
    x=p.parse_args()
    c=cc.load(x.home);tz=_tz(c);now=_now(tz)
    if x.cmd=='fact':out=record_fact(c.human_dir,x.statement,x.evidence,now,x.category,x.confidence,x.source,x.supersedes,c.human)
    elif x.cmd=='retract-fact':out=retract_fact(c.human_dir,x.id,x.reason,now)
    elif x.cmd=='pref':out=record_pref(c.life,x.text,now,x.valence,x.subject,c.agent)
    elif x.cmd=='ask':out=ask(c.life,x.text,now)
    elif x.cmd=='resolve':out=resolve(c.life,x.id,x.status,now,x.answer)
    elif x.cmd=='profile':out={'facts':facts(c.human_dir)}
    elif x.cmd=='duplicate-facts':out=duplicate_facts(c.human_dir,x.threshold)
    elif x.cmd=='wonder':out={'questions':questions(c.life,x.status)}
    elif x.cmd=='pref-history':
        rows=_read(c.life/'preferences.jsonl',kind='companion_preference')
        out={'preferences':[r for r in rows if not x.valence or r['valence']==x.valence]}
    elif x.cmd=='ledger':out=ledger_batch(c,x.file,now)
    elif x.cmd=='soul':
        if x.init:out=soul_init(c)
        elif x.append:out=soul_write(c,x.append,'append',now)
        elif x.set_:out=soul_write(c,sys.stdin.read(20000),'set',now)
        else:out=soul_show(c)
    else:out=summary(c)
    print(json.dumps(out,ensure_ascii=False,indent=2))
    if out.get('failed_at') is not None:sys.exit(1)

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,json.JSONDecodeError) as e:
        print(json.dumps({'error':str(e)}),file=sys.stderr);sys.exit(1)
