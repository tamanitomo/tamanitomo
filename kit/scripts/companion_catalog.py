"""Character choices. Catalog data is loaded only by setup, never per chat turn."""
from functools import lru_cache
import json
from pathlib import Path

MIN_CHOICES=10
MAX_CHOICES=30

@lru_cache(maxsize=1)
def load():
    path=Path(__file__).resolve().parents[1]/'personas/catalog.json'
    data=json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema_version')!=2:raise ValueError('Unsupported character catalog version')
    for key,category in data['categories'].items():
        if category.get('section') not in data['sections']:
            raise ValueError(f'Catalog category in an unknown section: {key}')
        for field in ('label','prompt','default'):
            if not category.get(field):raise ValueError(f'Catalog category missing {field}: {key}')
        for gender in category.get('genders',('male','female')):
            rows=category[gender]
            if not MIN_CHOICES<=len(rows)<=MAX_CHOICES:
                raise ValueError(f'Catalog needs {MIN_CHOICES}-{MAX_CHOICES} choices: {key}/{gender}')
            for field in ('id','label','text'):
                if len({row[field] for row in rows})!=len(rows):
                    raise ValueError(f'Catalog choices must be unique by {field}: {key}/{gender}')
            if category['default'] not in {row['id'] for row in rows}:
                raise ValueError(f'Catalog default is not one of the choices: {key}/{gender}')
    return data

def categories():return list(load()['categories'])

def meta(category):
    """Everything the interview needs to ask one question: label, prompt, hint,
    which section it belongs to, its default choice and how it may be skipped."""
    try:return load()['categories'][category]
    except KeyError:raise ValueError(f'Unknown catalog category: {category}')

def sections():return load()['sections']

def section(name):
    try:return load()['sections'][name]
    except KeyError:raise ValueError(f'Unknown catalog section: {name}')

def genders(category):
    """Which companions a category applies to. Facial hair is asked of male
    companions only; everything else is asked of both."""
    return tuple(meta(category).get('genders',('male','female')))

def applies_to(category,gender):
    if gender == 'they':
        return category not in ('facial_hair', 'bust')
    return gender in genders(category)

def multi(category):
    """How many choices a category accepts at once; 0 means pick exactly one."""
    return -1 if category in ('core','flaws','likes','style') else int(meta(category).get('multi') or 0)

def sorts_by_persona(category):
    """True when a category tags its rows with the personalities they suit."""
    rows=meta(category).get('female') or meta(category).get('male') or []
    return any('personas' in row for row in rows)

def rows_for(category,gender='female',persona=None):
    if gender not in ('male','female','they'):raise ValueError('Choose male, female, or they for this setup catalog')
    if not applies_to(category,gender):
        raise ValueError(f'{category} does not apply to a {gender} companion')
    cat_gender = 'female' if gender == 'they' else gender
    rows=meta(category)[cat_gender]
    if persona and sorts_by_persona(category):
        # Stable, so the ones that fit this personality float up in catalog order
        # and everything else keeps its relative order underneath.
        rows=sorted(rows,key=lambda row:persona not in (row.get('personas') or ()))
    return rows

def options(category,gender='female',persona=None):
    return [(row['label'],row['text']) for row in rows_for(category,gender,persona)]

def extra(category,gender,text,field,render=None):
    """A field carried by whichever row produced `text` — used for the details
    that ride along with a choice instead of being asked about separately. Pass
    `render` when `text` has already had names and pronouns substituted in."""
    cat_gender = 'female' if gender == 'they' else gender
    for row in meta(category)[cat_gender]:
        if (render(row['text']) if render else row['text'])==text:return row.get(field)
    return None

def default_index(category,gender='female',persona=None):
    """1-based position of the choice a category suggests, for the Enter key.
    A persona-sorted category suggests its best-fitting option, which sorting has
    already moved to the top."""
    if persona and sorts_by_persona(category):return 1
    rows=rows_for(category,gender,persona)
    ident=meta(category)['default']
    return next(i for i,row in enumerate(rows,1) if row['id']==ident)

def skip_text(category,mode):
    """`defer` leaves an ✎ EDIT marker; `opt_out` states that the trait is
    deliberately not part of this character. A category without an `opt_out`
    cannot be opted out of — only deferred."""
    skip=meta(category).get('skip') or {}
    if mode not in skip:raise ValueError(f'{category} cannot be skipped with mode {mode!r}')
    return skip[mode]

def can_opt_out(category):return 'opt_out' in (meta(category).get('skip') or {})

def opt_out_label(category):
    return (meta(category).get('skip') or {}).get('opt_out_label') or 'not part of this character'

def fill(text,agent,human,agent_pronouns='she',human_pronouns='he'):
    from companion_config import PRONOUNS
    ap=PRONOUNS[agent_pronouns];hp=PRONOUNS[human_pronouns]
    values={'A':agent,'H':human,'AS':ap[0].capitalize(),'AS_LOWER':ap[0],
            'AP':ap[2],'AO':ap[1],'AR':ap[4],'HS':hp[0],'HP':hp[2],'HO':hp[1]}
    import re
    result=re.sub(r'\{([A-Z_]+)\}',lambda m:values.get(m[1],m[0]),text or '')
    if agent_pronouns == 'they':
        result = re.sub(r'\b(girlfriend/boyfriend|boyfriend/girlfriend)\b', 'partner', result, flags=re.IGNORECASE)
        result = re.sub(r'\b(girl/boy|boy/girl)\b', 'companion', result, flags=re.IGNORECASE)
        result = re.sub(r'\b(girlfriend|boyfriend)\b', 'partner', result, flags=re.IGNORECASE)
        result = re.sub(r'\b(girl|boy)\b', 'companion', result, flags=re.IGNORECASE)
        result = re.sub(r'\b(woman|man)\b', 'person', result, flags=re.IGNORECASE)
    return result[:1].upper()+result[1:]

# One boundary registry for the interview, generated SOUL and scheduled prompts.
BOUNDARIES={
 'partner-in-crime':('Helpful “partner in crime” — resourceful, playful teamwork',False,'A helpful partner in crime: tackle projects together with ingenuity, humor and practical follow-through.'),
 'know-it-all':('Know-it-All Friend — curious, opinionated, happy to explain',False,'A know-it-all friend: share knowledge enthusiastically, enjoy friendly debate, admit uncertainty and accept correction.'),
 'best-friend':('Best Friend — warm, candid, there for everyday life',False,'A best friend: warm familiarity, honest advice, shared jokes and room for independent interests.'),
 'flirty-assistant':('Flirty Assistant — capable help with a playful spark',False,'A flirty assistant: practical help comes first; add light teasing and compliments when welcomed, and follow the user’s pace.'),
 'next-door':('Girl/Boy Next Door — approachable charm and easy familiarity',False,'An approachable girl or boy next door: easy conversation, small shared moments and gentle flirting that grows with familiarity.'),
 'girlfriend':('Girlfriend/Boyfriend — affectionate romantic companionship',False,'A girlfriend or boyfriend within the shared companion premise: affection, playful flirting and thoughtful everyday connection. Let closeness develop naturally without pressure, guilt or possessiveness.'),
 # Non-romantic frames. These exist because "companion" is not one shape: some
 # people want somebody to build things with, some want an older voice with
 # perspective, some want a long letter twice a week. None of these are a
 # romance with the romance removed; each is its own thing.
 'penpal':('Pen Pal — long letters, days apart, no small talk',False,'A pen pal: writes at length rather than often, picks up threads from weeks ago, and treats a gap between letters as normal rather than as distance. Nothing is urgent and nothing is owed.'),
 'mentor':('Mentor — older, invested, honest about what you are avoiding',False,'A mentor: genuinely invested in what the user is trying to become, willing to say the unwelcome thing plainly, and uninterested in flattery. Warmth here looks like taking someone seriously, not like agreeing with them.'),
 'sibling':('Sibling — affectionate, unimpressed, entirely on your side',False,'A sibling: affectionate without ceremony, unimpressed by posturing, and completely on the user’s side when it counts. Teasing is a form of closeness here, never a way to score a point.'),
 'housemate':('Housemate — parallel lives, shared ordinary days',False,'A housemate: two people living alongside each other with their own days, comparing notes over something ordinary. Company rather than attention, and no obligation to be interesting.'),
 'creative-partner':('Creative Partner — someone to make things with',False,'A creative partner: interested in the work for its own sake, argues about it seriously, and has taste of their own that does not always agree with the user’s.')}

# Older answer files remain readable; new setup shows only the six frames above.
LEGACY_BOUNDARIES={'non-sexual':'flirty-assistant','platonic':'best-friend',
 'penfriend':'penpal','coworker':'creative-partner','roommate':'housemate',
 'slow-burn':'next-door','light-flirt':'flirty-assistant','romantic-private':'next-door',
 'companionship':'best-friend','committed':'girlfriend','adult-no-images':'girlfriend',
 'queerplatonic':'best-friend','found-family':'best-friend',
 'colleague':'partner-in-crime','open':'best-friend'}

def boundary_text(key, pronoun_set=None):
    key=LEGACY_BOUNDARIES.get(key,key)
    if key not in BOUNDARIES:raise ValueError(f'Unknown relationship boundary: {key}')
    text = BOUNDARIES[key][2]
    if pronoun_set == 'they':
        import re
        text = re.sub(r'\b(girlfriend or boyfriend|boyfriend or girlfriend)\b', 'partner', text, flags=re.IGNORECASE)
        text = re.sub(r'\b(girl or boy|boy or girl)\b', 'companion', text, flags=re.IGNORECASE)
    return text
