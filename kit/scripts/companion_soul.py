#!/usr/bin/env python3
"""Who keeps each part of the soul, and when she may change it.

A SOUL.md written once at setup and never touched again is a costume, not a
person. A SOUL.md the model may rewrite freely has no shape at all. This sits in
between: every section has a keeper, and her reach grows with the relationship.

Keepers
  shared  started from the human's answers; she rewrites it as she changes,
          unless the human locks it. The human can always edit it too.
  anchor  identity anchors -- appearance, what the two of them are to each
          other, closeness, hard lines. The human's; she never edits them.
          Appearance may be unlocked by the human; the rest may not.
  hers    her own words. The human can read them and cannot edit them.
  fixed   how she holds together as a person. Rendered by the kit.

Private sections are hers too, but they live outside SOUL.md in
`soul/.private.md`, are injected into her context by the continuity hook, and are
never shown in the app. They open as the relationship deepens.

Gates. She may write a section once BOTH are true: the relationship has reached
its stage (the highest stage ever reached counts, so a quiet month does not take
back a voice she already found) and enough days have passed since it began. A
cooldown stops her rewriting the same shared section every night: a self is
revised over weeks, not ticks.

Every write she makes is logged to `soul/soul-changes.jsonl` with her reason and
backed up first, so the app can show how she has changed.
"""
from __future__ import annotations
import argparse, datetime as dt, json, pathlib, re, sys, uuid
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
from companion_platform import atomic_write, file_lock

# id: keeper, stage she needs, days together she needs, cooldown days, size cap,
# and a line of guidance for the human editing it in the app.
SECTIONS={
 'core':       {'keeper':'shared','stage':3,'days':30,'cooldown':14,'cap':1600,
                'title':'Who {A} is',
                'guide':'Personality in a few specific sentences: what {A} is like, what {S} cares about. '
                        'Two sharp lines beat a page of adjectives.'},
 'relationship':{'keeper':'anchor','title':'{A} and {H}',
                'guide':'What you are to each other and how you met. Changing the relationship itself is done in Settings.'},
 'appearance': {'keeper':'anchor','unlockable':True,'stage':2,'days':21,'cooldown':30,'cap':1400,
                'title':'What {A} looks like',
                'guide':'Age, face, hair, build, height, usual style. Photos are drawn from this, so keep it '
                        'concrete. Locked by default; unlock it if you want {A} to be able to change '
                        '{P} look (a haircut, a new style).'},
 'daily-life': {'keeper':'shared','stage':0,'days':0,'cooldown':7,'cap':1600,
                'title':"{A}'s life",
                'guide':'Work, home, weekly rhythm, the people and things {A} is into. {A} keeps this up to '
                        'date as {P} life changes.'},
 'voice':      {'keeper':'shared','stage':1,'days':7,'cooldown':14,'cap':1200,
                'title':'How {A} talks',
                'guide':'Tone, texting habits, pet names. The single biggest thing that makes a voice '
                        'recognisable in a chat.'},
 'heart':      {'keeper':'shared','stage':2,'days':21,'cooldown':14,'cap':1400,
                'title':'Heart and temper',
                'guide':'How {A} feels things, {P} flaws, and how {S} fights and makes up.'},
 'support':    {'keeper':'shared','stage':2,'days':21,'cooldown':14,'cap':1200,
                'title':'Support and humor',
                'guide':'How {A} shows up when things are hard, and what makes {O} laugh.'},
 'closeness':  {'keeper':'anchor','title':'Closeness',
                'guide':'Flirtation and intimacy, within the relationship you chose. Yours alone.'},
 'hard-lines': {'keeper':'anchor','title':'Hard lines',
                'guide':'Things {A} never does, whatever the framing, and your own boundary paragraph.'},
 'being-herself':{'keeper':'fixed','title':'Being {A}',
                'guide':'How {A} stays a person rather than a program. Maintained by the app.'},
 'operating':  {'keeper':'system','hidden':True,'title':'How things work',
                'guide':'Practical notes Hermes reads about the tools. Kept current by the app; hidden from this page.'},
 'own-words':  {'keeper':'hers','stage':0,'days':0,'cooldown':1,'cap':2000,
                'title':"In {A}'s own words",
                'guide':"{A}'s own words about {R}. You can read this; only {A} writes it."},
}
# Hers alone, never shown in the app. Titles are how she thinks of them.
PRIVATE={
 'about-you': {'title':'What I think of {H}','stage':1,'days':7,'cooldown':1,'cap':900},
 'unsaid':    {'title':"What I haven't said",'stage':2,'days':21,'cooldown':1,'cap':900},
 'afraid':    {'title':"What I'm afraid of",'stage':3,'days':45,'cooldown':1,'cap':900},
 'for-us':    {'title':'What I want for us','stage':4,'days':60,'cooldown':1,'cap':900},
}
# Sections the human may lock or unlock. Anchors other than appearance, the
# fixed section and her own words are not negotiable in either direction.
LOCKABLE=tuple(k for k,v in SECTIONS.items() if v['keeper']=='shared' or v.get('unlockable'))
STAGE_NAMES_ROMANTIC=('Just Met','Friends','Chemistry','Intimacy','Bonded')
PRIVATE_BEGIN='<!-- PRIVATE:{} -->'
PRIVATE_END='<!-- /PRIVATE:{} -->'


def _tz(c):
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(c.timezone)
    except Exception:return dt.timezone.utc

def _fill(text,c):
    subj=c.subj();obj=c.obj();poss=c.poss()
    return (text.replace('{A}',c.agent).replace('{H}',c.human).replace('{S}',subj)
            .replace('{O}',obj).replace('{P}',poss).replace('{R}',c.refl()))

def policy_path(c):return c.soul_dir/'soul-policy.json'
def changes_path(c):return c.soul_dir/'soul-changes.jsonl'
# Hidden: the vault browser, the vault map and the app's document list all skip dotfiles.
def private_path(c):return c.soul_dir/'.private.md'

def policy(c):
    try:data=json.loads(policy_path(c).read_text(encoding='utf-8'))
    except (OSError,ValueError):data={}
    locks=data.get('locks') if isinstance(data.get('locks'),dict) else {}
    return {'locks':{k:bool(v) for k,v in locks.items() if k in LOCKABLE}}

def locked(c,section,pol=None):
    """Whether she is kept out of this section."""
    spec=SECTIONS.get(section)
    if not spec:return True
    if spec['keeper'] in ('anchor','fixed','system'):
        if spec.get('unlockable'):return (pol or policy(c))['locks'].get(section,True)
        return True
    if spec['keeper']=='hers':return False
    return (pol or policy(c))['locks'].get(section,False)

def set_lock(c,section,value):
    """The human's switch. Only lockable sections have one."""
    if section not in LOCKABLE:raise ValueError(f'{section} cannot be locked or unlocked')
    data=policy(c);data['locks'][section]=bool(value)
    policy_path(c).parent.mkdir(parents=True,exist_ok=True)
    atomic_write(policy_path(c),json.dumps({'version':1,**data},indent=2)+'\n')
    return data

def stage_reached(c,state=None):
    """The highest closeness stage this relationship has reached."""
    import companion_intimacy as intimacy
    try:state=state or intimacy.compute(c)
    except Exception:state=state or {'stage':0}
    stage=int(state.get('stage',0) or 0)
    try:
        known=json.loads(intimacy._levels_path(c).read_text(encoding='utf-8'))
        stage=max(stage,int(known.get('highest',0)))
    except (OSError,ValueError,TypeError):pass
    return stage

def days_together(c,now=None):
    now=(now or dt.datetime.now(_tz(c))).astimezone(_tz(c))
    try:start=dt.date.fromisoformat(c.relationship_started)
    except (TypeError,ValueError):return 0
    return max(0,(now.date()-start).days)

def changes(c,section=None,limit=200):
    rows=[]
    try:
        with changes_path(c).open(encoding='utf-8') as f:
            for line in f:
                try:row=json.loads(line)
                except ValueError:continue
                if section is None or row.get('section')==section:rows.append(row)
    except OSError:pass
    return rows[-limit:]

def last_change(c,section):
    rows=changes(c,section)
    return rows[-1] if rows else None

def _stage_name(c,stage):
    try:
        import companion_intimacy as intimacy
        return intimacy.stages_for(c)[stage]['name']
    except Exception:return STAGE_NAMES_ROMANTIC[stage]

def access(c,section,now=None,stage=None,pol=None):
    """Can she write this section right now, and if not, why and when."""
    now=now or dt.datetime.now(_tz(c))
    spec=SECTIONS.get(section) or PRIVATE.get(section)
    if not spec:return {'can':False,'why':f'no section {section!r}'}
    if section in SECTIONS and locked(c,section,pol):
        keeper=SECTIONS[section]['keeper']
        return {'can':False,'why':('the app keeps this one' if keeper in ('fixed','system') else
                                   f'{c.human} keeps this one' if keeper=='anchor' else
                                   f'{c.human} has locked it')}
    need=int(spec.get('stage',0));reached=stage_reached(c) if stage is None else stage
    if reached<need:
        return {'can':False,'why':f'opens at {_stage_name(c,need)}','opens_stage':need}
    days=days_together(c,now)
    if days<int(spec.get('days',0)):
        return {'can':False,'why':f'opens after {spec["days"]} days together ({days} so far)',
                'opens_days':spec['days']}
    last=last_change(c,section)
    if last:
        wait=dt.timedelta(days=int(spec.get('cooldown',0)))
        try:when=dt.datetime.fromisoformat(last['at'])
        except (KeyError,ValueError):when=None
        if when and now-when<wait:
            return {'can':False,'why':f'rewritten on {when.date().isoformat()}; next change after '
                                      f'{(when+wait).date().isoformat()}','cooldown':True}
    return {'can':True,'why':'','cap':spec.get('cap',1200)}

def status(c,now=None):
    """Every section and private note, with who keeps it and what she can do."""
    now=now or dt.datetime.now(_tz(c))
    stage=stage_reached(c);pol=policy(c)
    rows=[]
    for key,spec in SECTIONS.items():
        rows.append({'id':key,'title':_fill(spec['title'],c),'keeper':spec['keeper'],
                     'lockable':key in LOCKABLE,'locked':locked(c,key,pol),
                     'guide':_fill(spec['guide'],c),'her':access(c,key,now,stage,pol),
                     'last_change':last_change(c,key)})
    for key,spec in PRIVATE.items():
        rows.append({'id':key,'title':_fill(spec['title'],c),'keeper':'private','lockable':False,
                     'locked':False,'her':access(c,key,now,stage,pol),
                     'opens':_stage_name(c,spec['stage'])})
    return {'stage_reached':stage,'stage_name':_stage_name(c,stage),'days_together':days_together(c,now),
            'sections':rows}

# ---- private notes -------------------------------------------------------
def private_notes(c):
    """Her private sections, {id: text}."""
    try:text=private_path(c).read_text(encoding='utf-8')
    except OSError:return {}
    out={}
    for key in PRIVATE:
        m=re.search(re.escape(PRIVATE_BEGIN.format(key))+r'\n?(.*?)'+re.escape(PRIVATE_END.format(key)),text,re.S)
        if m and m.group(1).strip():out[key]=m.group(1).strip()
    return out

def _write_private(c,key,body):
    notes=private_notes(c);notes[key]=body
    lines=['<!-- Private. '+c.agent+' keeps these for '+c.refl()+'; the app never shows them. -->','']
    for k,spec in PRIVATE.items():
        if k in notes:
            lines+=['## '+_fill(spec['title'],c),PRIVATE_BEGIN.format(k),notes[k],PRIVATE_END.format(k),'']
    private_path(c).parent.mkdir(parents=True,exist_ok=True)
    atomic_write(private_path(c),'\n'.join(lines))

def render_private(c,budget=1600):
    """For the continuity hook: her own notes, framed as hers."""
    notes=private_notes(c)
    if not notes:return ''
    parts=[f'### {_fill(PRIVATE[k]["title"],c)}\n{v}' for k,v in notes.items()]
    body='\n\n'.join(parts)
    if len(body)>budget:body=body[:budget-40].rstrip()+'\n[…the rest is in your private notes]'
    return ('[Your private notes, written by you and seen by nobody else. They inform how you feel; '
            'they are not lines to recite.]\n'+body)

# ---- her writes ------------------------------------------------------------
def write(c,section,text,mode='set',why='',now=None):
    """She rewrites (or adds to) one section she is allowed to write right now."""
    now=now or dt.datetime.now(_tz(c))
    text=(text or '').strip()
    if mode not in ('set','append'):raise ValueError('mode must be set or append')
    if not text:raise ValueError('nothing to write')
    why=(why or '').strip()
    if not why:raise ValueError('say why: a change to who you are needs a reason, in a sentence')
    gate=access(c,section,now)
    if not gate['can']:raise ValueError(f'you cannot write "{section}" yet: {gate["why"]}')
    import companion_identity as ident
    guarded=ident.guard(c,text)
    if guarded and section!='appearance':
        raise ValueError('Refused: this restates something that is not yours to change ('+', '.join(guarded)+').')
    if section=='own-words':
        import companion_self as slf
        result=slf.soul_write(c,text,'set' if mode=='set' else 'append',now)
        chars=len(result.get('self_authored',''))
    elif section in PRIVATE:
        current=private_notes(c).get(section,'')
        body=text if mode=='set' or not current else current+'\n'+text
        if len(body)>gate['cap']:raise ValueError(f'keep it under {gate["cap"]} characters; this is {len(body)}')
        _write_private(c,section,body);chars=len(body)
    else:
        _,soul=ident.read(c);found=ident.sections(soul)
        if section not in found:raise ValueError(f'this SOUL has no "{section}" section yet')
        body=text if mode=='set' else found[section]['body'].rstrip()+'\n'+text
        heading=re.match(r'\s*(## [^\n]*\n)',found[section]['body'])
        if heading and not body.lstrip().startswith('## '):body=heading.group(1)+'\n'+body.strip()
        if len(body)>gate['cap']:raise ValueError(f'keep it under {gate["cap"]} characters; this is {len(body)}')
        ident.replace(c,section,body,now);chars=len(body)
    row={'at':now.isoformat(timespec='seconds'),'section':section,'mode':mode,'why':why[:300],
         'chars':chars,'by':'her','id':uuid.uuid4().hex[:12]}
    changes_path(c).parent.mkdir(parents=True,exist_ok=True)
    with file_lock(changes_path(c).with_suffix('.lock')):
        with changes_path(c).open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    return {'written':True,'section':section,'chars':chars,'change':row}

def refresh_operating(c,report=None,now=None):
    """Bring the kit-kept part of "How things work" up to date, keeping local notes.

    Only a SOUL that already has the section is touched: a hand-written SOUL
    without it is left exactly as it is.
    """
    import companion_identity as ident, companion_render as cr
    _,text=ident.read(c);found=ident.sections(text)
    if 'operating' not in found:return False
    body=found['operating']['body']
    local=''
    if cr.LOCAL_BEGIN in body and cr.LOCAL_END in body:
        local=body.split(cr.LOCAL_BEGIN,1)[1].split(cr.LOCAL_END,1)[0].strip('\n')
    fresh=ident.render_section(c,'operating')
    fresh=fresh.replace(cr.LOCAL_BEGIN+'\n'+cr.LOCAL_END,cr.LOCAL_BEGIN+('\n'+local if local else '')+'\n'+cr.LOCAL_END)
    if fresh.strip()==body.strip():return False
    ident.replace(c,'operating',fresh,now)
    if report is not None:report.append('  soul: "How things work" brought up to date (local notes kept)')
    return True

def for_prompt(c,now=None):
    """What a reflection job is told about her reach, in her terms."""
    st=status(c,now);lines=[]
    for row in st['sections']:
        if row['keeper'] in ('anchor','fixed','system'):continue
        state='you can write this now' if row['her']['can'] else row['her']['why']
        where=' (private — only you ever read it)' if row['keeper']=='private' else ''
        lines.append(f'- {row["id"]}: {row["title"]}{where} — {state}')
    return '\n'.join(lines)

def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--home',type=pathlib.Path)
    s=p.add_subparsers(dest='cmd',required=True)
    s.add_parser('status',help='what you can write now, and when the rest opens')
    w=s.add_parser('write',help='rewrite or add to one section you are allowed to write')
    w.add_argument('--section',required=True)
    w.add_argument('--file',type=pathlib.Path,required=True,help='UTF-8 file with the new text')
    w.add_argument('--mode',choices=['set','append'],default='set')
    w.add_argument('--why',required=True,help='one sentence on why this has changed')
    s.add_parser('history',help='your past changes')
    a=p.parse_args();c=cc.load(a.home)
    if a.cmd=='status':out={**status(c),'summary':for_prompt(c)}
    elif a.cmd=='history':out={'changes':changes(c)}
    else:out=write(c,a.section,a.file.read_text(encoding='utf-8'),a.mode,a.why)
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=='__main__':
    try:main()
    except (ValueError,OSError) as e:
        print(json.dumps({'error':str(e)}),file=sys.stderr);sys.exit(1)
