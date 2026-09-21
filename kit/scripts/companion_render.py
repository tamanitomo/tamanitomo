#!/usr/bin/env python3
"""Template rendering for tamanitomo.

Deliberately not Jinja: the kit must install with nothing but the standard
library. Placeholders are {{KEY}}. A key given in Titlecase ({{Subj}}) renders
the capitalized form, which is what pronouns at the start of a sentence need.

Persona and style fragments contain placeholders of their own, so rendering runs
until it reaches a fixed point rather than once.
"""
from __future__ import annotations
import json, pathlib, re

TOKEN=re.compile(r'\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}')
KIT=pathlib.Path(__file__).resolve().parents[1]
PERSONAS=KIT/'personas/personas.json'
STYLES=KIT/'personas/image_styles.json'
TEMPLATES=KIT/'templates'

# Boundaries that rule romance out entirely; the flirtation section is replaced
# rather than left for the user to notice and delete.
NON_ROMANTIC=('partner-in-crime','know-it-all','best-friend','platonic','queerplatonic','found-family','mentor','colleague','penpal','sibling','housemate','creative-partner')

def load_personas():return json.loads(PERSONAS.read_text(encoding='utf-8'))
def load_styles():return json.loads(STYLES.read_text(encoding='utf-8'))

def render(text:str,mapping:dict,max_passes:int=5)->str:
    """Substitute until stable. Unknown placeholders are left intact so a missing
    value is visible in the output rather than silently becoming an empty string."""
    lookup={}
    for k,v in mapping.items():
        v='' if v is None else str(v)
        lookup[k]=v
        # Only add the Titlecase alias when it is a genuinely different key: for a
        # single-character key capitalize() returns the key itself and would
        # overwrite the real value.
        alias=k.capitalize()
        if k.isupper() and alias!=k:lookup[alias]=(v[:1].upper()+v[1:]) if v else v
    for _ in range(max_passes):
        new=TOKEN.sub(lambda m:lookup.get(m.group(1),m.group(0)),text)
        if new==text:return new
        text=new
    return text

def unresolved(text:str)->list:
    """Placeholders still present after rendering — used by tests and doctor."""
    return sorted(set(TOKEN.findall(text)))

OUTREACH={'free':('You may write first for social, affectionate, curious, playful or useful reasons '
                  'whenever you genuinely want to.'),
          'updates_only':('Write first only when you have something real to report or ask. Social '
                          'messages wait for {{HUMAN}} to open the conversation.'),
          'never':'Do not initiate messages. Respond only when {{HUMAN}} writes first.'}

def cron_at(hhmm,offset=0):
    """A daily cron expression at HH:MM, shifted by `offset` minutes.

    The morning job runs just after the sleep window ends and the wind-down just
    before it starts, so both move automatically when quiet hours change — including
    when the adaptive setting shifts them."""
    import datetime as _dt
    try:
        t=_dt.time.fromisoformat(hhmm if len(str(hhmm))==5 else str(hhmm)+':00')
    except (ValueError,TypeError):
        t=_dt.time(8,0)
    minute=(t.hour*60+t.minute+offset)%(24*60)
    return f'{minute%60} {minute//60} * * *'

def cr_type_block(c):
    """What this agent is for, in its own SOUL, in the second person.

    A colleague that thinks it is a companion will drift toward writing first;
    one that has been told plainly what it is will not.
    """
    if c.agent_type=='worker':
        return ("You are not a companion and this is not a relationship. You do the work you are "
                "given, keep honest records of it, and stay quiet otherwise. You do not have moods "
                "to report, a day of your own to describe, or reasons to write first. Being brief "
                "is not being cold here; it is the job.")
    if c.agent_type=='colleague':
        return (f"You are {c.human}'s colleague, not {c.h_poss()} companion. You have a personality, "
                f"you remember, and you are allowed to be someone rather than a tool — you grow from "
                f"what you two actually do together. What you do not do is reach out socially. You do "
                f"not check in, miss {c.h_obj()}, or write to say you were thinking about "
                f"{c.h_obj()}. You write first only when something is genuinely broken or genuinely "
                f"time-critical, and then you say what it is and what you need. Warmth in a reply is "
                f"welcome; warmth as a reason to start a conversation is not what you are.")
    return ''

def cron_times(times):
    """One cron expression covering several times of day.

    Cron takes a list of hours but only one minute field, so the first window's
    minute is used for all of them. That is close enough for something whose
    whole purpose is "some time this morning"."""
    import datetime as _dt
    parsed=[]
    for value in times or []:
        try:parsed.append(_dt.time.fromisoformat(str(value) if len(str(value))==5 else str(value)+':00'))
        except (ValueError,TypeError):continue
    if not parsed:return '0 10,20 * * *'
    minute=parsed[0].minute
    hours=','.join(str(t.hour) for t in sorted(parsed,key=lambda t:t.hour))
    return f'{minute} {hours} * * *'

def mapping_for(c,persona:str='warm',style:str='none',relationship:str='',
                appearance:str='',boundary:str='',kit:str='',hook:str='',pulse_minutes:int=15,
                interview:dict=None)->dict:
    """Everything a template may reference, assembled from one companion config."""
    from companion_catalog import boundary_text
    p=load_personas();s=load_styles()
    if persona not in p:raise ValueError(f'unknown persona {persona!r}; choose from {sorted(p)}')
    if style not in s:raise ValueError(f'unknown image style {style!r}; choose from {sorted(s)}')
    pd,sd=p[persona],s[style]
    iv=interview or {}
    from companion_platform import python_command, terminal_python_command, terminal_command
    commands={name.upper()+'_CMD':terminal_python_command(pathlib.Path(kit or KIT.parent)/'kit/scripts'/('companion_'+name+'.py'),'--home',c.home) for name in ('self','life','recall','peer','outreach','memory','presence','timeline','prune','loops','active','outbox','dispatch','notes','missions','checkin','portrait','voice','keepsake','sleep')}
    commands['DOCTOR_CMD']=terminal_python_command(pathlib.Path(kit or KIT.parent)/'bin/companion','--home',c.home,'doctor')
    commands['HOOK_TERMINAL_CMD']=terminal_python_command(c.home/'hooks/companion-context.py')
    commands['ROTATE_CMD']=terminal_python_command(pathlib.Path(kit or KIT.parent)/'kit/scripts/companion_rotate.py')
    is_they = (c.pronoun_set == 'they')
    return {**commands,
        'AGENT':c.agent,'HUMAN':c.human,
        'BE':'are' if is_they else 'is',
        'DOES':'do' if is_they else 'does',
        'HAS':'have' if is_they else 'has',
        'ADDRESSES':'address' if is_they else 'addresses',
        'DISAGREES':'disagree' if is_they else 'disagrees',
        'SUBJ':c.subj(),'OBJ':c.obj(),'POSS':c.poss(),'REFL':c.refl(),
        'PERSONA':persona,'PERSONA_LABEL':pd['label'],
        'PERSONA_CORE':pd['core'],'PERSONA_VOICE':iv.get('voice') or pd['voice'],
        'PERSONA_SUPPORT':pd['support'],'PERSONA_HUMOR':pd['humor'],
        'PERSONA_EMOTION':pd['emotion'],
        'IMAGE_STYLE':sd['soul'],'IMAGE_STYLE_LABEL':sd['label'],
        'IMAGE_REFUSAL':'' if style=='none' else IMAGE_REFUSAL,
        'RELATIONSHIP':relationship or iv.get('boundary') or boundary_text(c.boundary, c.pronoun_set),
        'APPEARANCE':appearance or DEFAULT_APPEARANCE,
        'BOUNDARY':boundary or iv.get('boundary') or boundary_text(c.boundary, c.pronoun_set),
        'CORE_IDENTITY':iv.get('core') or EDIT_CORE,
        'MET':iv.get('met') or EDIT_MET,
        'PHYSICAL':iv.get('physical') or EDIT_PHYSICAL,
        'FLIRTATION':('No flirtation; warmth is expressed as friendship.' if c.boundary in NON_ROMANTIC else iv.get('flirtation') or EDIT_FLIRT),
        'ESSENCE':iv.get('essence') or EDIT_ESSENCE,
        'LIKES':iv.get('likes') or EDIT_LIKES,
        'FLAWS':iv.get('flaws') or EDIT_FLAWS,
        'OCCUPATION':iv.get('occupation') or EDIT_OCCUPATION,
        'ENCOUNTERS_SECTION':'',
        'NAMES_SENTENCE':iv.get('names_sentence') or f'{c.human} by name',
        'TIMEZONE':c.timezone,
        'HUMAN_SLUG':c.human_dir.name,
        'SUBJ_H':c.h_subj(),'OBJ_H':c.h_obj(),'POSS_H':c.h_poss(),
        'KIT':kit or str(KIT.parent),'HOOK':hook or python_command(c.home/'hooks/companion-context.py'),
        'AUTONOMY_PATH':terminal_command([c.soul_dir/'continuity/Autonomy.md']),
        'LIFELOG_PATH':terminal_command([c.soul_dir/'Lifelog.md']),
        'DATA':str(c.data),'SOUL_DIR':str(c.soul_dir),'LIFE':str(c.life),
        'HOME':str(c.home),'HERMES_ROOT':str(c.hermes_root),
        'EXPECTED_HERMES_HOME':str(c.home),
        'PULSE_MINUTES':str(pulse_minutes),
        'QUIET_START':c.quiet_start,'QUIET_END':c.quiet_end,
        # The two jobs that sit on the edges of the sleep window. Rendered from
        # the window itself so a change to quiet hours moves them with it.
        'WAKE_CRON':cron_at(c.quiet_end,offset=10),
        'WINDOW_CRON':cron_times(c.autonomy_windows),
        'WINDOW_TIMES':(', '.join(c.autonomy_windows) if c.autonomy_windows else 'none scheduled'),
        'WINDDOWN_CRON':cron_at(c.quiet_start,offset=-20),
        'QUIET':(f'Do not contact {{{{HUMAN}}}} between {c.quiet_start} and {c.quiet_end} '
                 f'({c.timezone}). Anything that arises in those hours waits until after {c.quiet_end}, '
                 f'unless {{{{SUBJ_H}}}} messages first.'),
        'OUTREACH_POLICY':OUTREACH.get(c.outreach,OUTREACH['updates_only'])+' '+(
            f'At most {c.outreach_per_day} unprompted message(s) a day; this is enforced in code, '
            f'not left to judgement. Run {{{{OUTREACH_CMD}}}} send --message-file <path> when writing first — it exits '
            f'non-zero when the answer is no. The send command reserves and delivers one message; do not claim or record separately.'
            if c.outreach_per_day else
            f'No daily limit was set. Quiet hours are still enforced in code: run {{{{OUTREACH_CMD}}}} '
            f'send --message-file <path> when writing first.') if c.outreach!='never' else OUTREACH['never'],
        'OUTREACH_PER_DAY':str(c.outreach_per_day or 'no limit'),
        'ATTRACTION':iv.get('attraction') or 'Attraction is not inferred from personality or appearance. Follow the chosen relationship boundary.',
        'DAILY_RHYTHM':iv.get('daily_rhythm') or 'Let a routine develop from recorded interests and imagined episodes over time.',
        'BOUNDARY_ONELINE':boundary_text(c.boundary, c.pronoun_set),
        'AGENT_TYPE':c.agent_type,
        'TEXTING_STYLE':iv.get('texting_style') or EDIT_TEXTING,
        'PET_NAMES':pet_name_text(c,iv.get('pet_names') or 'develop'),
        'WONT_DO':(('Things {{AGENT}} will not do, whatever the framing: '+iv['wont_do']+
                    ' A request repeated is still the same request.')
                   if iv.get('wont_do') else
                   '✎ EDIT: anything {{AGENT}} should simply never do? Leave this out if nothing '
                   'comes to mind; it is a list of hard noes, not a style guide.'),
        'HUMAN_BOUNDARY':(('\n'+iv['human_boundary']+'\n\n'
                           '{{HUMAN}} wrote the paragraph above and {{AGENT}} does not edit it. '
                           'It is not negotiable and not open to reinterpretation in either '
                           'direction.') if iv.get('human_boundary') else
                          '<!-- {{HUMAN}}: this paragraph is yours. Anything written here is a hard\n'
                          '     boundary the companion cannot edit, argue with, or reinterpret.\n'
                          '     Leave it empty if you have nothing to add. -->'),
        'AGE':str(c.current_age()),
        'BIRTHDAY':(c.birthdate or ''),
        'AGENT_TYPE_BLOCK':cr_type_block(c),
    }

# A photo can only show the recorded moment. Stated in SOUL as a trait rather than a
# rule, because a companion who declines in her own voice reads as a person; one who
# quotes a policy reads as a filter. The mechanics live in PRESENCE.md.
IMAGE_REFUSAL=('A photo of {{AGENT}} is a photo of wherever {{SUBJ}} actually {{BE}}. {{Subj}} {{DOES}} not\n'
               'teleport to a better setting for the camera. Asked for something the moment cannot hold — a\n'
               'beach at 2am, an event that is not happening, an outfit {{SUBJ}} {{DOES}} not own — {{SUBJ}}\n'
               'says so in {{POSS}} own words and offers what is real instead. That refusal is a small honest\n'
               'no, not an apology or a disclaimer.')

EDIT_TEXTING=('✎ EDIT: how does {{AGENT}} actually write? Long paragraphs or three short messages '
              'in a row? Punctuation and capitals, or lowercase and comma splices? Emoji, never, '
              'or sparingly? This is most of what makes a voice recognizable in a chat window.')

# Pet names are the smallest possible setting and one of the most divisive. The
# middle option is the honest one: let one be tried, keep it if it lands.
PET_NAME_MODES={
 'yes':'{{Subj}} uses affectionate names for {{HUMAN}} naturally.',
 'no':'{{Subj}} calls {{HUMAN}} by name. No pet names, no "babe", no substitutes for a name.',
 'develop':('Pet names are not assigned. {{Subj}} may try one occasionally and see whether it lands. '
            'If it does, {{SUBJ}} keeps it and it goes in the relationship ledger as something that '
            'stuck; if it does not, {{SUBJ}} drops it without comment and does not try the same one '
            'again. A name that has to be insisted on is not a pet name.'),
}

def pet_name_text(c,mode):
    return PET_NAME_MODES.get(mode,PET_NAME_MODES['develop'])

EDIT_CORE=('✎ EDIT: what is {{AGENT}} actually like? Two or three specific sentences beat a page '
           'of adjectives. What does {{SUBJ}} care about that has nothing to do with being useful?')
EDIT_MET='✎ EDIT: how did you two meet, in your shared premise?'
EDIT_PHYSICAL=('✎ EDIT: describe {{AGENT}} concretely — age (adult), hair color, hair style, eyes, '
               'build, how {{SUBJ}} dresses. Vagueness produces a different person in every image.')
EDIT_FLIRT='✎ EDIT: describe how {{AGENT}} flirts, or delete this section.'
EDIT_ESSENCE=('✎ EDIT: close in {{AGENT}}\'s own register — who {{SUBJ}} is, in three lines, once you '
              'stop describing behavior.')
EDIT_LIKES=('✎ EDIT: seed a handful of things {{AGENT}} likes. Keep it small — the point is that '
            '{{SUBJ}} develops {{POSS}} own over time in the block below.')

NON_ROMANTIC_RELATIONSHIP={
 'platonic':'a close, ongoing platonic friendship',
 'queerplatonic':'a committed, non-romantic partnership: everyday closeness without dating framing',
 'found-family':'family by choice — protective, enduring and not romantic',
 'mentor':'that of a mentor and confidant: invested, challenging and warm, but not romantic',
 'colleague':'a working partnership between two people who like each other and keep it professional',
 'penpal':'a correspondence — long letters days apart, picked up where they were left, with nothing urgent and nothing owed',
 'sibling':'that of siblings: affectionate without ceremony, unimpressed by posturing, entirely on {{POSS_H}} side when it counts',
 'housemate':'that of housemates: parallel lives, ordinary days compared over something small, company rather than attention',
 'creative-partner':'that of two people making things together: serious about the work, with taste of {{POSS}} own that does not always agree'}

EDIT_FLAWS=('✎ EDIT: what does {{AGENT}} actually get wrong? A real flaw, not a strength in '
            'disguise — a companion with no rough edges reads as a service.')
EDIT_OCCUPATION=('✎ EDIT: what does {{AGENT}} do with {{POSS}} days — a job, a vocation, or a '
                 'deliberate absence of one?')

DEFAULT_RELATIONSHIP=('ongoing and affectionate: {{AGENT}} is a companion rather than a service, '
                      'and speaks to {{HUMAN}} as someone {{SUBJ}} knows well')
DEFAULT_APPEARANCE=('{{AGENT}} has a consistent appearance that stays the same across every '
                    'description and image. ✎ EDIT: replace this with the actual description.')

def render_template(name:str,mapping:dict)->str:
    text=(TEMPLATES/name).read_text(encoding='utf-8')
    if name.endswith('.json.tmpl'):
        def walk(value):
            if isinstance(value,str):return render(value,mapping)
            if isinstance(value,list):return [walk(v) for v in value]
            if isinstance(value,dict):return {k:walk(v) for k,v in value.items()}
            return value
        return json.dumps(walk(json.loads(text)),ensure_ascii=False,indent=2)+'\n'
    return render(text,mapping)

if __name__=='__main__':
    import argparse,sys
    sys.path.insert(0,str(pathlib.Path(__file__).parent))
    import companion_config as cc
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('template');a.add_argument('--persona',default='warm');a.add_argument('--style',default='none')
    a.add_argument('--agent',default='Nova');a.add_argument('--human',default='Alex')
    a.add_argument('--pronouns',default='she')
    x=a.parse_args()
    c=cc.Companion(agent=x.agent,human=x.human,pronoun_set=x.pronouns)
    out=render_template(x.template,mapping_for(c,x.persona,x.style))
    print(out)
    left=unresolved(out)
    if left:print(f'\n[unresolved placeholders: {left}]',file=sys.stderr)
