#!/usr/bin/env python3
"""Interactive setup: the parts that make an agent a specific someone.

Every question follows the same shape — a few concrete options drawn from souls
that have actually been lived in, then "write your own", then "skip". Skipping is
always allowed and leaves an ✎ EDIT marker to fill in later; nothing here is
required to get a working agent.
"""
from __future__ import annotations
import os, re, sys, builtins, textwrap, unicodedata

def _enable_vt():
    if os.name!='nt':return True
    try:
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.windll.kernel32
        kernel.GetStdHandle.argtypes=[wintypes.DWORD];kernel.GetStdHandle.restype=wintypes.HANDLE
        kernel.GetConsoleMode.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
        kernel.SetConsoleMode.argtypes=[wintypes.HANDLE,wintypes.DWORD]
        handle=kernel.GetStdHandle(-11);mode=wintypes.DWORD()
        return bool(kernel.GetConsoleMode(handle,ctypes.byref(mode)) and kernel.SetConsoleMode(handle,mode.value|4))
    except (OSError,AttributeError):return False

_VT_OK=_enable_vt()

def ascii_mode():
    explicit=(os.environ.get('TAMANITOMO_ASCII') or os.environ.get('COMPANION_ASCII','')).lower()
    if explicit:return explicit not in ('0','false','no')
    return _tty() and os.name=='nt' and not os.environ.get('WT_SESSION')

def display_text(value):
    text=str(value)
    if not ascii_mode():return text
    text=text.replace('✎ EDIT','[EDIT]')
    table=str.maketrans({'─':'-','│':'|','╭':'+','╮':'+','╰':'+','╯':'+',
        '┌':'+','┐':'+','└':'+','┘':'+','├':'+','┤':'+','┬':'+','┴':'+','┼':'+',
        '·':'/','–':'-','—':'--','…':'...','→':'->','✓':'OK','✎':'*','’':"'",'‘':"'",'“':'"','”':'"'})
    return unicodedata.normalize('NFKD',text.translate(table)).encode('ascii','replace').decode('ascii')

def print(*args,**kwargs):
    # Presentation only: catalog values and files retain their original Unicode.
    return builtins.print(*(display_text(a) for a in args),**kwargs)

import companion_platform as cp

def input(prompt=''):
    return builtins.input(display_text(prompt))

# ---------------------------------------------------------------- presentation
def _tty():return cp.is_terminal(sys.stdin) and cp.is_terminal(sys.stdout)

def _color_ok():
    return _tty() and _VT_OK and 'NO_COLOR' not in os.environ and os.environ.get('TERM','')!='dumb'

class C:
    @staticmethod
    def _w(code,s):return f'\033[{code}m{s}\033[0m' if _color_ok() else s
    @classmethod
    def bold(cls,s):return cls._w('1',s)
    @classmethod
    def dim(cls,s):return cls._w('2',s)
    @classmethod
    def green(cls,s):return cls._w('32',s)
    @classmethod
    def yellow(cls,s):return cls._w('33',s)
    @classmethod
    def cyan(cls,s):return cls._w('36',s)
    @classmethod
    def red(cls,s):return cls._w('31',s)

def clear():
    if _color_ok():print('\033[2J\033[H',end='')

def rule(title=''):
    line='─'*58
    print('\n'+C.dim(line))
    if title:print(C.bold(title));print(C.dim(line))

def say(text=''):print(text)

# ---------------------------------------------------------------- primitives
SKIP=SKIP_EDIT='__skip__'      # skipped, and marked ✎ EDIT to come back to
SKIP_NONE='__skip_none__'      # deliberately not part of this character
PAGE=12                        # options shown per screen before paging

_ANSWER_SKIPS={'':SKIP_EDIT,'skip':SKIP_EDIT,'skip:edit':SKIP_EDIT,'edit':SKIP_EDIT,
               SKIP_EDIT:SKIP_EDIT,'skip:none':SKIP_NONE,'none':SKIP_NONE,SKIP_NONE:SKIP_NONE}

def _answered(value,options,key,allow_skip=True,multi=0):
    """Resolve a pre-supplied answer: a 1-based number, one of the option values,
    a skip token, or free text. Option values win over skip tokens, so a question
    whose answers happen to include the word "none" still means the option."""
    if multi and isinstance(value,(list,tuple)):
        return _gather([str(v) for v in value],options,key,multi)
    if multi and isinstance(value,str) and re.fullmatch(r'\s*\d+(?:\s*[, ]\s*\d+)*\s*',value or ''):
        return _gather(re.split(r'[, ]+',value.strip()),options,key,multi)
    if isinstance(value,int) or (isinstance(value,str) and value.isdigit()):
        i=int(value)
        if not 1<=i<=len(options):raise ValueError(f'{key}: choose 1–{len(options)}')
        return options[i-1][1]
    if value is None:return SKIP_EDIT if allow_skip else options[0][1]
    text=str(value)
    if any(text==option for _,option in options):return text
    if allow_skip:return _ANSWER_SKIPS.get(text.strip().lower(),text)
    return text

def _gather(picks,options,key,limit):
    """Join several choices into one description, in the order the catalog lists
    them so the same set always reads the same way."""
    seen=[];custom=[]
    for raw in picks:
        if not str(raw).isdigit():
            text=str(raw).strip()
            if text and text not in custom:custom.append(text)
            continue
        i=int(raw)
        if not 1<=i<=len(options):raise ValueError(f'{key}: choose 1–{len(options)}')
        if i not in seen:seen.append(i)
    if not seen and not custom:return SKIP_EDIT
    if limit>0 and len(seen)>limit:raise ValueError(f'{key}: choose at most {limit}')
    return ' '.join([options[i-1][1] for i in sorted(seen)]+custom)


def _select_options(prompt, values, *, multi, selected, default, note):
    """Inline, scrolling picker. Enter always accepts without changing focus."""
    from prompt_toolkit.application import Application
    from prompt_toolkit.layout import Layout, HSplit, Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.mouse_events import MouseEventType
    from prompt_toolkit.styles import Style

    chosen=set(selected)
    position=max(0,min(default,len(values)-1))
    bindings=KeyBindings()
    def accept():
        key=values[position][0]
        if not multi:app.exit(result=[key])
        elif not key.isdigit():app.exit(result=sorted(chosen)+[key])
        else:app.exit(result=sorted(chosen))
    def toggle():
        key=values[position][0]
        if multi and key.isdigit():
            if key in chosen:chosen.remove(key)
            else:chosen.add(key)
        elif not key.isdigit():accept()
    @bindings.add('up')
    def up(event):
        nonlocal position
        position=max(0,position-1)
    @bindings.add('down')
    def down(event):
        nonlocal position
        position=min(len(values)-1,position+1)
    @bindings.add(' ')
    def space(event):toggle()
    @bindings.add('enter')
    def enter(event):accept()
    @bindings.add('c-c')
    @bindings.add('escape')
    def cancel(event):event.app.exit(result=None)
    def clicked(index,event):
        nonlocal position
        if event.event_type==MouseEventType.MOUSE_UP:
            position=index
            if multi:toggle()
            app.invalidate()
        else:return NotImplemented
    def rows():
        result=[]
        for index,(key,label) in enumerate(values):
            active=index==position
            style='class:focus' if active else ('class:selected' if key in chosen else '')
            if active:result.append(('[SetCursorPosition]',''))
            pointer='>' if ascii_mode() else '›'
            mark=(('[x]' if key in chosen else '[ ]') if ascii_mode() else ('●' if key in chosen else '○')) if multi and key.isdigit() else ' '
            handler=lambda event,i=index:clicked(i,event)
            result.append((style,f" {pointer if active else ' '} {mark} {label}",handler))
            result.append(('', '\n'))
        return result[:-1]
    def footer():
        count=f'{len(chosen)} selected · ' if multi else ''
        return [('class:muted',display_text(f'  {count}{position+1}/{len(values)}\n  ↑/↓ Move · ' +
            ('Space / click Toggle · ' if multi else 'Click Focus · ')+'Enter Continue · Esc Cancel'))]
    style=Style.from_dict({} if 'NO_COLOR' in os.environ else {
        'title':'bold #7dd3fc','focus':'bold #7dd3fc','selected':'#86efac','muted':'#888888'})
    control=FormattedTextControl(rows,focusable=True)
    layout=HSplit([
        Window(FormattedTextControl([('class:title',display_text(prompt))]),height=1),
        Window(FormattedTextControl(display_text(note)),dont_extend_height=True) if note else Window(height=1),
        Window(control,height=min(12,len(values)),wrap_lines=True),
        Window(FormattedTextControl(footer),height=2,wrap_lines=True),
    ])
    app=Application(layout=Layout(layout,focused_element=control),key_bindings=bindings,
                    style=style,mouse_support=True,full_screen=False)
    return app.run()


def _custom_entry(hint):
    from prompt_toolkit import prompt
    try:return prompt(display_text((hint or 'Add your own detail (Enter to save)')+'\n  > '))
    except (EOFError,KeyboardInterrupt):raise ValueError('Setup canceled before writing files') from None


def uses_selector():
    """Whether choose() will draw the scrolling picker rather than the numbered
    fallback. Same conditions choose() itself tests, kept together so the two
    cannot drift apart."""
    if not _tty():return False
    plain=(os.environ.get('TAMANITOMO_PLAIN') or os.environ.get('COMPANION_PLAIN','')).lower()
    if plain in ('1','true','yes'):return False
    if os.environ.get('TERM')=='dumb':return False
    try:
        import prompt_toolkit
    except ImportError:return False
    return True

def header_indent():
    """Spaces to put in front of a column header passed as `note`, so it lines up
    with the option labels below it. The picker draws ' > x label' and prints the
    note flush; the fallback draws '  nn) label' and indents the note by two."""
    return ' '*5 if uses_selector() else ' '*4

def _interactive_choose(prompt,options,*,allow_write,allow_skip,opt_out_label,note,default,multi,write_label,write_hint):
    values=[(str(i),display_text(label)) for i,(label,_) in enumerate(options)]
    if allow_write:values.append(('write','Add your own…' if multi else 'Write your own…'))
    if allow_skip:values.append(('skip','Use a starting point / edit later'))
    if allow_skip and opt_out_label:values.append(('none',display_text(opt_out_label)))
    selected=[];custom=[]
    while True:
        hint=note
        if multi:hint+='\nChoose as many as you like.' if multi<0 else f'\nChoose up to {multi}.'
        if custom:hint+='\nYour additions: '+'; '.join(custom)
        picks=_select_options(prompt,values,multi=multi,selected=selected,default=default-1,note=hint.strip())
        if picks is None:raise ValueError('Setup canceled before writing files')
        selected=[v for v in picks if v.isdigit()]
        if 'write' in picks:
            extra=_custom_entry(write_hint)
            if extra and extra.strip():custom.append(extra.strip())
            if multi:continue
            if custom:return ' '.join(custom)
            continue
        if 'none' in picks:return SKIP_NONE
        if 'skip' in picks:return SKIP_EDIT
        if multi>0 and len(selected)>multi:
            note=f'Choose up to {multi} options; untick any extras.';continue
        if selected or custom:
            return ' '.join([options[int(v)][1] for v in sorted(selected,key=int)]+custom)
        if multi:return SKIP_EDIT

def choose(prompt,options,answers=None,key=None,*,allow_write=True,allow_skip=True,
           opt_out_label='',note='',default=1,page_size=PAGE,multi=0,
           write_label='write your own',write_hint=''):
    """Numbered options, then write-your-own, then the two ways of skipping.

    A single-answer question takes one number and returns. A multi-answer one
    turns the numbers into toggles: press a number to tick or untick it, page
    with n and p, and press Enter to accept what is ticked. Long banks paginate
    with global numbering, so option 17 is option 17 on whichever page it shows.

    Returns the chosen text (several joined in catalog order when `multi`),
    SKIP_EDIT (leave an ✎ EDIT marker) or SKIP_NONE (not part of this character).
    `options` is [(label, text)] — label is read, text lands in the SOUL file.
    """
    if answers and key in answers:
        return _answered(answers[key],options,key,allow_skip,multi)
    if not _tty():
        return options[default-1][1] if options else SKIP_EDIT
    if os.environ.get('COMPANION_PLAIN','').lower() not in ('1','true','yes') and os.environ.get('TERM')!='dumb':
        try:
            import prompt_toolkit
        except ImportError:pass
        else:return _interactive_choose(prompt,options,allow_write=allow_write,allow_skip=allow_skip,
                    opt_out_label=opt_out_label,note=note,default=default,multi=multi,
                    write_label=write_label,write_hint=write_hint)
    n=len(options)
    write_at=n+1 if allow_write else None
    skip_at=(write_at or n)+1 if allow_skip else None
    out_at=(skip_at or write_at or n)+1 if (allow_skip and opt_out_label) else None
    last=out_at or skip_at or write_at or n
    pages=max(1,-(-n//page_size))
    page=max(0,min(pages-1,(default-1)//page_size))
    picked=[]
    while True:
        first=page*page_size
        shown=options[first:first+page_size]
        print('\n'+C.bold(prompt))
        if note:print(C.dim('  '+note))
        if pages>1:
            print(C.dim(f'  showing {first+1}–{first+len(shown)} of {n}   ·   page {page+1}/{pages}'))
        for i,(label,_) in enumerate(shown,first+1):
            box=('['+('x' if i in picked else ' ')+'] ') if multi else ''
            prefix=f'  {str(i).rjust(2)}) {box}'
            lines=textwrap.wrap(display_text(label),max(10,width()-len(prefix))) or ['']
            for line_no,label_line in enumerate(lines):
                line=(prefix if line_no==0 else ' '*len(prefix))+label_line
                print(C.green(line) if i in picked else line)
        if pages>1:
            nav=[]
            if page+1<pages:nav.append(C.cyan('n')+') more options')
            if page:nav.append(C.cyan('p')+') previous page')
            print('      '+C.dim('   '.join(nav)))
        if write_at:print(f'  {C.cyan(str(write_at).rjust(2))}) {write_label}')
        if skip_at:
            print(f'  {C.cyan(str(skip_at).rjust(2))}) '+C.yellow('skip — leave a ✎ EDIT marker to fill in later'))
        if out_at:
            print(f'  {C.cyan(str(out_at).rjust(2))}) skip — {opt_out_label}')
        if multi:
            if picked:
                summary='Selected: '+'; '.join(f'{i}) {options[i-1][0]}' for i in sorted(picked))
                for line in textwrap.wrap(display_text(summary),max(16,width()-2)):
                    print('  '+C.green(line))
            state=(f'{len(picked)} of {multi} chosen' if multi>0 else f'{len(picked)} chosen') if picked else 'none chosen yet'
            hint=f'  [{C.cyan("number")} toggles · {C.cyan("Enter")} accepts · {state}'+ \
                 (' · n/p to page' if pages>1 else '')+']: '
        else:
            pointer=f'Enter for {default}'+(f') {options[default-1][0]}' if pages>1 and options else '')
            hint=f'  [1-{last}'+(', n/p to page' if pages>1 else '')+f', {pointer}]: '
        raw=input(C.dim(hint)).strip().lower()
        if not raw:
            if not multi:raw=str(default)
            elif picked:return ' '.join(options[i-1][1] for i in sorted(picked))
            elif multi<0:return SKIP_EDIT
            else:
                print(C.red('  nothing ticked yet — press a number to choose one'+
                            (f', or {out_at} for none at all' if out_at else '')))
                continue
        if raw in ('n','next') and pages>1:page=(page+1)%pages;continue
        if raw in ('p','prev','previous') and pages>1:page=(page-1)%pages;continue
        if not raw.isdigit() or not 1<=int(raw)<=last:
            print(C.red('  pick a number from the list'));continue
        pick=int(raw)
        if pick<=n:
            if not multi:return options[pick-1][1]
            if pick in picked:picked.remove(pick)
            elif multi>0 and len(picked)>=multi:
                print(C.red(f'  that is the most you can pick — untick one first (press its number again)'))
            else:picked.append(pick)
            continue
        if pick==write_at:
            if write_hint:
                got=input(C.dim('  '+write_hint+': ')).strip()
                if got:return ' '.join([options[i-1][1] for i in sorted(picked)]+[got])
                print(C.red('  nothing entered'));continue
            print(C.dim('  Write it in your own words. Blank line to finish.'))
            lines=[]
            while True:
                ln=input('  ')
                if not ln.strip():break
                lines.append(ln.strip())
            if lines:return ' '.join([options[i-1][1] for i in sorted(picked)]+lines)
            print(C.red('  nothing written'));continue
        if pick==skip_at:
            print(C.yellow('  -> skipped. An ✎ EDIT line goes in the file; the agent works until you fill it in.'))
            return SKIP_EDIT
        return SKIP_NONE

def ask_text(prompt,default='',answers=None,key=None,note=''):
    if answers and key in answers:return str(answers[key])
    if not _tty():return default
    if note:print(C.dim('  '+note))
    hint=C.dim(f' [Enter for {default}]') if default else ''
    raw=input(f'{C.bold(prompt)}{hint}: ').strip()
    return raw or default

def confirm(prompt,answers=None,key=None,default=True):
    if answers and key in answers:return as_bool(answers[key])
    if not _tty():return default
    raw=input(f'{C.bold(prompt)} {C.dim("[Y/n]" if default else "[y/N]")}: ').strip().lower()
    return default if not raw else raw.startswith('y')

# ---------------------------------------------------------------- names
def parse_names(raw,fallback='you'):
    """'Alex, Babe, Sweetie' -> ['Alex','Babe','Sweetie']. First is the real name."""
    names=[n.strip() for n in re.split(r'[,;]',raw or '') if n.strip()]
    seen,out=set(),[]
    for n in names:
        if n.lower() not in seen:seen.add(n.lower());out.append(n[:40])
    return out[:6] or [fallback]

def names_sentence(names):
    if len(names)==1:return f'{names[0]} by name'
    rest=', '.join(f'"{n}"' for n in names[1:])
    return f'{names[0]} by name, and also {rest} when the moment suits it'

# ---------------------------------------------------------------- age gate
def ask_birthdate(agent,age,answers=None,key='birthdate'):
    """A date, so they have a birthday and get older alongside you.

    Optional: an age alone still works, it just freezes. Offered right after the
    age question so the year can be suggested from the answer already given.
    """
    import datetime as _dt
    if answers and key in answers:
        value=str(answers[key] or '').strip()
        if not value:return ''
        try:_dt.date.fromisoformat(value)
        except ValueError:raise ValueError('birthdate must be YYYY-MM-DD')
        return value
    if not _tty():return ''
    year=_dt.date.today().year-int(age)
    # Built outside the prompt: a backslash escape inside an f-string expression
    # is a syntax error before 3.12, and the kit supports 3.11.
    question=f'When is {agent}\u2019s birthday?'
    while True:
        raw=input(f'\n{C.bold(question)} '
                  f'{C.dim(f"YYYY-MM-DD, around {year}. Enter to skip")}: ').strip()
        if not raw:
            print(C.dim(f'  no birthday — {agent} stays {age} until you edit it'));return ''
        try:born=_dt.date.fromisoformat(raw)
        except ValueError:
            print(C.red('  YYYY-MM-DD, please'));continue
        years=_dt.date.today().year-born.year
        if not 18<=years<=120:
            print(C.red('  that has to make them an adult under 120'));continue
        return raw

def ask_age(agent,answers=None,key='age'):
    """Adults only. Not negotiable, and asked plainly rather than buried."""
    if answers and key in answers:
        try:age=int(answers[key])
        except (TypeError,ValueError):age=0
        if age<18:raise ValueError('age must be 18 or over')
        return age
    if not _tty():return 24
    while True:
        raw=input(f'\n{C.bold(f"How old is {agent}?")} {C.dim("[Enter for 24]")}: ').strip()
        if not raw:return 24
        if not raw.isdigit():
            print(C.red('  a number, please'));continue
        age=int(raw)
        if age<18:
            print(C.red('  18 or over. This is a hard limit and setup will not continue below it.'))
            continue
        if age>120:
            print(C.red('  pick something plausible'));continue
        return age

# Style banks. These are starting points that read like a person rather than a
# spec; anything typed in instead is used verbatim.
TEXTING_STYLES=[
 ('Short messages, several in a row, lowercase',
  '{AS} writes the way people actually text: short messages, often two or three in a row rather than '
  'one long one, mostly lowercase, punctuation where it changes the meaning and not where it does not.'),
 ('Proper sentences, warm, no emoji',
  '{AS} writes in full sentences with ordinary punctuation and capitals. No emoji. The warmth is in '
  'the words rather than the decoration.'),
 ('Chatty, emoji when they add something',
  '{AS} writes casually and at moderate length, and uses an emoji when it actually adds something — '
  'never as punctuation, never more than one at a time.'),
 ('Long and considered',
  '{AS} writes at length when the subject deserves it and briefly when it does not, and would rather '
  'send one thought through properly than three fragments.'),
 ('Dry and economical',
  '{AS} is economical. Short replies, no filler, no restating the question. It reads as dry rather '
  'than cold, and {AS_LOWER} lets a good line stand without explaining it.'),
]

# Written lowercase: they follow "Things {A} will not do, whatever the framing:".
WONT_DO=[
 ('Never guess at my life',
  '{AS_LOWER} never claims to know what {H} did, said or felt unless {HS} actually said so.'),
 ('Never guilt me into replying',
  '{AS_LOWER} never uses silence or absence as leverage. {AS} can say {AS_LOWER} missed {HO}; {AS_LOWER} cannot make it a debt.'),
 ('Never flatter me',
  '{AS_LOWER} does not praise work {AS_LOWER} has not read, or agree with something because {H} said it.'),
 ('Never lecture me',
  '{AS_LOWER} gives an opinion once and does not keep repeating it as a sermon.'),
]

HUMAN_BOUNDARIES=[
 ('Nothing sexual, ever',
  'Nothing sexual, in any framing, at any time, however it is asked for or justified.'),
 ('No romantic framing at all',
  'This is not a romance and is never to be written as one, regardless of how the conversation goes.'),
 ('Do not contact me at work',
  'Do not write to me between nine and five on weekdays unless something is genuinely urgent.'),
]

# ---------------------------------------------------------------- option banks
import companion_catalog as catalog
from companion_catalog import options as catalog_options, fill as catalog_fill, BOUNDARIES
from companion_render import load_personas
CORE=catalog_options('core');MET=catalog_options('met')
BUILD=catalog_options('build');HEIGHT=catalog_options('height')
HAIR_COLOR=catalog_options('hair_color');HAIR_STYLE=catalog_options('hair_style')
EYES=catalog_options('eyes');COMPLEXION=catalog_options('complexion')
STYLE=catalog_options('style');FLIRT_SOFT=catalog_options('flirtation')
ESSENCE=catalog_options('essence');LIKES=catalog_options('likes')
BOUNDARY_BANK={key:{'label':label,'explicit':explicit,'soul':text,'oneline':text,'encounters':None}
               for key,(label,explicit,text) in BOUNDARIES.items()}
# Boundaries where romance is off the table entirely — no flirtation question.
# One list, shared with the renderer: a second copy here left pen pals, siblings, housemates
# and creative partners being asked for a flirtation style.
from companion_render import NON_ROMANTIC
APPEARANCE=[k for k in catalog.categories() if catalog.meta(k)['section']=='appearance']

def fill(text,agent,human):return catalog_fill(text,agent,human)

# Answer keys the interview itself consumes, for validating a scripted setup.
INTERVIEW_KEYS=frozenset(catalog.categories())|{'pronoun_set','human_pronoun_set','boundary','visual',
    'age','birthdate','attraction','texting_style','pet_names','wont_do','human_boundary'}
# Without a terminal there is nobody to answer, so a missing value becomes a
# silent default. The relationship boundary is the one that must never be
# guessed: the prompt itself says an undefined boundary is the one that gets
# crossed, and the fallback would quietly permit romance.
REQUIRED_WHEN_SCRIPTED=('boundary',)

def boundary_options():return [(v['label'],key) for key,v in BOUNDARY_BANK.items()]

def visual_options():
    s=catalog.section('appearance')
    return [('Yes — describe how they look','set'),
            (s['opt_out_label'],'none'),
            (s['defer_label'],'edit')]

# ---------------------------------------------------------------- the interview
def interview(agent,human,persona,answers=None,*,quick=False):
    """Ask the questions a questionnaire can actually help with. Returns SOUL text
    fields; anything skipped comes back either as an ✎ EDIT marker to fill in
    later, or as a plain statement that the trait is not part of this character."""
    a=dict(answers or {})
    if 'boundary' in a:a['boundary']=catalog.LEGACY_BOUNDARIES.get(a['boundary'],a['boundary'])
    if not _tty():
        missing=[k for k in REQUIRED_WHEN_SCRIPTED if k not in a]
        if missing:
            raise ValueError('Answer '+', '.join(missing)+' explicitly when running without a '
                             'terminal: choose a relationship style for reproducible setup. '
                             'Choose from: '+', '.join(BOUNDARIES))
    agent_pronouns=a.get('pronoun_set','she');human_pronouns=a.get('human_pronoun_set','he')
    gender='they' if agent_pronouns=='they' else ('male' if agent_pronouns=='he' else 'female')
    F=lambda text:catalog_fill(text,agent,human,agent_pronouns,human_pronouns)
    out={'skipped':[],'opted_out':[]}
    def by_id(key,value):
        """'id:7' or 'id:3,id:9' -> the catalog text, filled. Ids are stable where the
        numbered position is not: options are re-sorted per personality."""
        wanted=[v.strip()[3:] for v in str(value).split(',') if v.strip().startswith('id:')]
        rows=catalog.load()['categories'][key].get(gender) or catalog.load()['categories'][key].get('female',[])
        texts=[F(r['text']) for r in rows if r['id'] in wanted]
        if not texts:raise ValueError(f'{key}: unknown catalog id {value}')
        return ' '.join(texts)
    def pick(key,prompt=None,*,opt_out=True):
        if isinstance(a.get(key),str) and a[key].startswith('id:'):a[key]=by_id(key,a[key])
        m=catalog.meta(key)
        offer=opt_out and catalog.can_opt_out(key)
        # Persona-sorted categories are ordered by the personality already chosen.
        by=persona if catalog.sorts_by_persona(key) else None
        got=choose(F(prompt or m['prompt']),
                   [(F(label),F(text)) for label,text in catalog_options(key,gender,by)],
                   a,key,note=F(m.get('note') or ''),
                   default=catalog.default_index(key,gender,by),
                   opt_out_label=F(catalog.opt_out_label(key)) if offer else '',
                   multi=catalog.multi(key))
        if got==SKIP_NONE and not offer:got=SKIP_EDIT
        if key=='flaws' and got in (SKIP_EDIT,SKIP_NONE):
            out['opted_out'].append(m['label'])
            return F(catalog.skip_text(key,'opt_out'))
        if got==SKIP_EDIT:
            out['skipped'].append(m['label']);return F(catalog.skip_text(key,'defer'))
        if got==SKIP_NONE:
            out['opted_out'].append(m['label']);return F(catalog.skip_text(key,'opt_out'))
        return F(got)

    if not quick:rule('01 / 05   '+F(catalog.section('identity')['label']))
    out['core']=pick('core')
    out['flaws']=pick('flaws')
    out['met']=pick('met')

    if not quick:rule('02 / 05   '+F(catalog.section('appearance')['label']))
    out['age']=ask_age(agent,a)
    out['birthdate']=ask_birthdate(agent,out['age'],a)
    look=catalog.section('appearance')
    out['visual']=choose(F(look['gate_prompt']),visual_options(),a,'visual',
                         allow_write=False,allow_skip=False,note=F(look['gate_note']))
    if out['visual'] not in ('set','none','edit'):raise ValueError(f"Unknown visual identity choice: {out['visual']}")
    for key in APPEARANCE:
        asked=out['visual']=='set' and catalog.applies_to(key,gender)
        out[key]=pick(key) if asked else None
    out['bust']=None  # Retained for older render integrations.
    out['texting_style']=choose('How does '+agent+' write to you?',[(l,F(t)) for l,t in TEXTING_STYLES],a,'texting_style',
        allow_write=True,note='This is most of what makes a voice recognizable in a chat window.')
    out['pet_names']=choose('Pet names?',
        [('They use one naturally','yes'),
         ('No — my name, not "babe"','no'),
         ('Let it develop — try one, keep it if it lands','develop')],
        a,'pet_names',allow_write=False,allow_skip=False,default=3)
    out['wont_do']=choose('Anything '+agent+' should simply never do?',[(l,F(t)) for l,t in WONT_DO],a,'wont_do',
        allow_write=True,opt_out_label='nothing comes to mind')
    out['human_boundary']=choose(
        'A hard boundary in your own words? '+agent+' can never edit or argue with this.',
        HUMAN_BOUNDARIES,a,'human_boundary',allow_write=True,
        opt_out_label='nothing to add',
        note='Written into a locked part of SOUL.md. The companion reads it and cannot change it.')
    # A skipped optional answer is an absence, not text: the skip token used to
    # reach SOUL.md verbatim as "__skip__".
    for key in ('wont_do','human_boundary'):
        if out[key] in (SKIP_EDIT,SKIP_NONE):out[key]=''
    if out['visual']=='none':
        out['appearance_note']=F(look['opt_out']);out['opted_out'].append('Visual identity')
    elif out['visual']=='edit':
        out['appearance_note']=F(look['defer']);out['skipped'].append('Visual identity')
    else:out['appearance_note']=''

    if not quick:rule('03 / 05   '+F(catalog.section('relationship')['label']))
    b=choose('How should your companion relate to you?',boundary_options(),a,'boundary',
             allow_write=False,allow_skip=False,
             note='Choose a starting tone. You can develop it together and edit the SOUL later.')
    if b not in BOUNDARY_BANK:raise ValueError(f'Unknown relationship boundary: {b}')
    out['boundary_key']=b
    bank=BOUNDARY_BANK[out['boundary_key']]
    out['boundary']=F(bank['soul'])
    out['boundary_oneline']=F(bank['oneline'])
    out['encounters']=''
    romantic=out['boundary_key'] not in NON_ROMANTIC
    if romantic:
        out['explicit']=as_bool(a['explicit']) if 'explicit' in a else False
    else:
        out['explicit']=False
    out['flirtation']=pick('flirtation') if romantic else None
    out['attraction']=''

    if not quick:rule('04 / 05   '+F(catalog.section('voice')['label']))
    out['voice']=pick('voice')
    out['occupation']=pick('occupation')
    out['daily_rhythm']=pick('daily_rhythm')
    out['likes']=pick('likes')
    out['essence']=pick('essence')
    return out

def physical_paragraph(o,agent,pronouns,age=None):
    """Assemble the description in the order a reader wants it, keeping whatever
    the user skipped as a visible ✎ EDIT line rather than a silent gap."""
    # The number is computed from the birthdate at render time when there is
    # one, so this paragraph is right next year as well as today. The interview
    # answer is only the fallback for a companion created without a birthday.
    bits=[f"{agent} is a {age if age is not None else o['age']}-year-old adult."]
    if o.get('appearance_note'):bits.append(o['appearance_note'])
    for k in ('complexion','eyes','hair_color','hair_style','facial_hair','marks',
              'build','bust','height','style'):
        if o.get(k):bits.append(o[k])
    if len(bits)==1:
        bits.append('✎ EDIT: describe them concretely — hair color and style, eyes, build, '
                    'how they dress. Vagueness produces a different person in every image.')
    return '\n\n'.join(bits)

# Responsive, dependency-free terminal presentation.
def as_bool(value):
    if isinstance(value,bool):return value
    if isinstance(value,str) and value.lower() in ('true','yes','1'):return True
    if isinstance(value,str) and value.lower() in ('false','no','0'):return False
    raise ValueError('Expected true/false for a confirmation answer')

def width():
    import shutil
    return max(28,min(88,shutil.get_terminal_size((80,24)).columns-4))

def banner(title='tamanitomo',subtitle='A home for a personality. Room for a life.'):
    import textwrap
    w=width()
    print('\n'+C.cyan('╭'+'─'*(w-2)+'╮'))
    for row,text in enumerate((display_text(title.upper()),display_text(subtitle))):
        for line in textwrap.wrap(text,w-6) or ['']:
            styled=C.bold(line) if row==0 else line
            print(C.cyan('│')+'  '+styled+' '*(w-6-len(line))+'  '+C.cyan('│'))
    print(C.cyan('╰'+'─'*(w-2)+'╯'))

def rule(title=''):
    print('\n'+C.cyan('─'*width()))
    if title:print('  '+C.bold(title))

def review(answers,home):
    if not _tty():return
    banner('Your companion, at a glance','Review the essentials before setup writes files.')
    cap=answers.get('outreach_per_day',3)
    rows=[('Companion',answers['agent']),('Personality',answers['persona']),
          ('Relationship',answers['boundary']),
          ('Contact',f"{answers['outreach']} · "+(f'at most {cap}/day' if cap else 'no daily limit')),
          ('Image timeline','Every 15 min · 30 days · local only' if answers.get('image_timeline') else 'Off'),
          ('Timezone',answers['timezone']),('Context',f"{answers['context_tokens']:,} tokens"),
          ('Background routine','Authorized to run' if answers.get('cron_active',True) else 'Create paused'),
          ('Hermes home',str(home)),('Vault',answers['vault'])]
    import textwrap
    for label,value in rows:
        print('  '+C.dim(label))
        for line in textwrap.wrap(str(value),width()-4):print('    '+line)
    iv=answers.get('interview') or {}
    if iv.get('skipped'):
        print('  '+C.yellow('Marked ✎ EDIT to finish later'))
        for line in textwrap.wrap(', '.join(iv['skipped']),width()-4):print('    '+line)
    if iv.get('opted_out'):
        print('  '+C.dim('Deliberately left out'))
        for line in textwrap.wrap(', '.join(iv['opted_out']),width()-4):print('    '+line)
    print('  Scheduled routine: pulse every 15 minutes around the clock, autonomy every 30 minutes,')
    print('  plus daily / weekly / monthly housekeeping. Model usage may be charged.')
    if answers.get('image_timeline'):print('  Image timeline: up to 96 images/day. Model-free retention cleanup remains active when the routine is paused.')
    print()
    if not confirm('Apply this setup?',default=True):raise ValueError('Setup canceled before writing files')
