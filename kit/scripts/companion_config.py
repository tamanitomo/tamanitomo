#!/usr/bin/env python3
"""Profile resolution and context budgeting.

Every other script in the kit asks this module where things live and how much room
it has. Nothing else may hardcode a path, a name, or a size.

Budgets are derived from the model's real context window rather than guessed, using
the same arithmetic Hermes uses to truncate context files (prompt_builder.py:
max_chars = clamp(context_length * 4 * 0.06, 20_000, 500_000)). That matters because
a companion running on an 8K local model and one on a 272K cloud model cannot carry
the same amount of context, and the small one must degrade by carrying less rather
than by being silently cut off mid-sentence.
"""
from __future__ import annotations
import dataclasses, json, os, pathlib
from typing import Optional
from companion_platform import default_home, atomic_write

CONFIG_NAME='companion.json'
DEFAULT_CONTEXT_TOKENS=32768
# detect_context_tokens returns this as its source when it found nothing to read.
# A guess must never be treated as evidence that a recorded window is now wrong.
FALLBACK_SOURCE='fallback default'

def detected_for_real(how:str)->bool:return not str(how).startswith(FALLBACK_SOURCE)
# Hermes' own context-file rule, reproduced so we can stay under it deliberately.
HERMES_CHARS_PER_TOKEN=4
HERMES_CONTEXT_FILE_FRACTION=0.06
HERMES_CONTEXT_FILE_FLOOR=20_000
HERMES_CONTEXT_FILE_CEILING=500_000
# The per-turn injection takes a smaller slice than a context file: it is paid on
# every single turn, where SOUL.md rides in the cached prefix.
INJECTION_FRACTION=0.03
INJECTION_MIN=1_200
INJECTION_MAX=9_000

# subject, object, possessive-determiner, possessive-pronoun, reflexive.
# Third-person singular only: setup asks whether the companion is male or female
# and every template, persona and catalog line is written to agree with a
# singular verb. A plural set would need a parallel set of verb forms.
# What a job is for, which is what decides how much thinking it is worth paying
# for. Named rather than numbered so the recommendation table can talk about them.
# What kind of agent this is. Not a personality setting — a decision about what
# machinery exists at all.
#
#   companion  a full life: a present, moods, a relationship, outreach.
#   colleague  a personality that grows and remembers, and no social outreach.
#              It speaks first only when something is actually broken. This is
#              what most people who like the idea but do not want a companion
#              are actually asking for.
#   worker     no relationship layer. It does work, keeps records, and stays
#              quiet. Missions and the vault, none of the inner life.
AGENT_TYPES={'companion':'A full life: a present, moods, a relationship, and permission to write first.',
             'colleague':'A personality that grows and remembers you, but never reaches out socially — '
                         'only when something is genuinely broken.',
             'worker':'No relationship layer at all. Work, records, and quiet.'}

JOB_TIERS={'loops':'the 15- and 30-minute loops that keep the present moving',
           'reflection':'the daily, weekly and monthly jobs that decide what lasts',
           'chat':'conversation itself, which Hermes owns'}
REASONING_EFFORTS=('none','low','medium','high')

# What an unprompted message may contain, and whether it may. "ask" is the
# middle setting that most people actually want: she may offer a photo, she may
# not attach one unasked.
CONTENT_KINDS=('text','image','voice')
PERMISSIONS=('yes','ask','no')

PRONOUNS={'she':('she','her','her','hers','herself'),
          'he':('he','him','his','his','himself'),
          'they':('they','them','their','theirs','themselves')}

def _clamp(v,lo,hi):return max(lo,min(int(v),hi))

def soul_cap(context_tokens:int)->int:
    """Chars at which Hermes head/tail-truncates a context file such as SOUL.md."""
    return _clamp(context_tokens*HERMES_CHARS_PER_TOKEN*HERMES_CONTEXT_FILE_FRACTION,
                  HERMES_CONTEXT_FILE_FLOOR,HERMES_CONTEXT_FILE_CEILING)

def injection_cap(context_tokens:int)->int:
    """Chars the per-turn continuity injection may occupy."""
    return _clamp(context_tokens*HERMES_CHARS_PER_TOKEN*INJECTION_FRACTION,
                  INJECTION_MIN,INJECTION_MAX)

def tier(context_tokens:int)->str:
    if context_tokens<=16_384:return 'tiny'
    if context_tokens<=65_536:return 'small'
    if context_tokens<=200_000:return 'medium'
    return 'large'

# Proportions of the injection budget left after the fixed rules and lookup tail.
# Open loops and the handoff earn the most because they are what the agent acts on.
# Weights descend in the same order as _PRIORITY below, so a section never gets
# a larger share than something the kit considers more important.
_WEIGHTS={'loops':0.22,'handoff':0.19,'standing':0.14,'facts':0.13,'relationship':0.10,
          'episodes':0.09,'preferences':0.06,'questions':0.04,'ambient':0.03}
# Degradation order for small windows: drop whole sections rather than starve every
# one of them into uselessness. Knowing the human outranks the agent's own fiction,
# and a rule the human gave outranks a fact about them: being told twice how to
# work with someone is being told you were not listening.
_PRIORITY=['loops','handoff','standing','facts','relationship','episodes',
           'preferences','questions','ambient']
_MIN_USEFUL=150

@dataclasses.dataclass
class Companion:
    """One agent. `profile` is '' for the root Hermes home, else profiles/<name>/."""
    persona:str='warm'
    cron_active:bool=True
    agent:str='Companion'
    pronoun_set:str='she'
    human_pronoun_set:str='he'
    human:str='the user'
    names:list=dataclasses.field(default_factory=list)
    age:int=24
    # A birthdate rather than an age, so the companion gets older with you and
    # has a birthday you can mark. `age` above is what setup recorded on the day
    # it ran; `current_age` below is what anything should actually use.
    birthdate:str=''
    explicit:bool=False
    remote_pin:str=''
    timezone:str='UTC'
    profile:str=''
    hermes_root:pathlib.Path=dataclasses.field(default_factory=default_home)
    vault:pathlib.Path=pathlib.Path.home()/'vault'
    context_tokens:int=DEFAULT_CONTEXT_TOKENS
    context_mode:str="auto"  # auto follows Hermes on each load; fixed is an intentional kit override
    image_interval_minutes:int=15
    schedule_offset_minutes:int=0
    image_timeline:bool=False
    image_mode:str='none'          # codex | local | none
    image_style:str='none'
    boundary:str='best-friend'
    soul_in_vault:bool=True
    quiet_start:str='23:00'
    quiet_end:str='08:00'
    outreach:str='updates_only'
    # Hard cap on unprompted messages per day, enforced by companion_outreach
    # without consulting a model. 0 means the user chose not to limit it.
    outreach_per_day:int=3
    # Where the human lives, in whatever form a weather service understands
    # ("Raleigh, NC"). Empty means the weather and daylight sensors stay silent
    # rather than guessing a location.
    location:str=''
    # Still up if they messaged this recently, even inside the sleep window. A
    # sleep window is a description of a person's night, not a gate that should
    # ignore them being visibly awake.
    sleep_grace_minutes:int=45
    # Per-content-type permission for unprompted sends: yes | ask | no.
    # "ask" means the companion may offer, never attach unasked.
    content_permissions:dict=dataclasses.field(default_factory=dict)
    # Let the sleep window drift toward the hours actually kept, from evidence,
    # by at most half an hour at a time, never below six hours. Opt-in.
    adaptive_quiet:bool=False
    # Whether what this agent learns about the human is shared with the other
    # agents on this machine, or kept to itself.
    #
    # Defaults to False so that adding this field cannot silently relocate an
    # existing companion's ledger. Setup asks, and the question defaults to
    # sharing: if one agent learns you are allergic to shellfish, the one
    # ordering dinner should know. Some people want the opposite — a new
    # companion who discovers them from nothing — and that is the setting.
    share_people:bool=False
    # When the companion gets an hour to herself: either to work on something
    # the human asked for, or to go and find something out because she wanted
    # to. Two a day by default. An empty list switches the windows off.
    autonomy_windows:list=dataclasses.field(default_factory=lambda:['10:20','20:20'])
    agent_type:str='companion'
    # How much disk the rolling image timeline may use, in gigabytes. When it is
    # over, the oldest captures go — never anything copied into an album, which
    # is the whole point of albums. 0 means keep everything and let the disk
    # decide, which the doctor will warn about rather than enforce.
    timeline_budget_gb:float=2.0
    # Computed relationship indicators, enabled by default and user-switchable.
    bars:bool=True
    relationship_progression:str='subtle'
    relationship_pace:str='natural'
    peer_interaction:bool=True
    # Which sensors this profile has switched on, by name.
    sensors:list=dataclasses.field(default_factory=list)
    # Per-job model choices, written by `tamanitomo models`. Empty means "whatever
    # the profile is configured with"; the kit never picks a model for anyone.
    #   {"loops":{"model":..,"provider":..,"reasoning_effort":".."}, "reflection":{...},
    #    "fallbacks":[{"provider":..,"model":..}, ...]}
    models:dict=dataclasses.field(default_factory=dict)

    def __post_init__(self):
        if self.relationship_progression not in ('off','subtle','milestones'):
            raise ValueError('relationship_progression must be off, subtle, or milestones')
        if self.relationship_pace not in ('slow','natural','quick'):
            raise ValueError('relationship_pace must be slow, natural, or quick')
        if not isinstance(self.peer_interaction,bool):raise ValueError('peer_interaction must be true or false')
        if not isinstance(self.explicit,bool):raise ValueError('explicit must be true or false')
        if self.explicit:
            from companion_render import NON_ROMANTIC
            if self.current_age()<18 or self.boundary in NON_ROMANTIC:
                raise ValueError('Adult themes require an adult companion and an eligible relationship frame')
        if not isinstance(self.location,str) or len(self.location)>120:
            raise ValueError('location must be a short piece of text, or empty')
        if not isinstance(self.remote_pin,str) or (self.remote_pin and (not self.remote_pin.isdigit() or len(self.remote_pin)!=4)):
            raise ValueError('remote_pin must be a 4-digit numeric PIN, or empty')
        if not isinstance(self.sleep_grace_minutes,int) or not 0<=self.sleep_grace_minutes<=240:
            raise ValueError('sleep_grace_minutes must be between 0 and 240')
        if not isinstance(self.adaptive_quiet,bool):raise ValueError('adaptive_quiet must be true or false')
        if not isinstance(self.content_permissions,dict):raise ValueError('content_permissions must be an object')
        for key,value in self.content_permissions.items():
            if key not in CONTENT_KINDS:raise ValueError(f'unknown content kind {key!r}; expected {sorted(CONTENT_KINDS)}')
            if value not in PERMISSIONS:raise ValueError(f'{key} permission must be one of {PERMISSIONS}')
        if self.birthdate:
            import datetime as _dt
            try:born=_dt.date.fromisoformat(self.birthdate)
            except (ValueError,TypeError):raise ValueError('birthdate must be YYYY-MM-DD')
            years=_dt.date.today().year-born.year
            if not 18<=years<=120:raise ValueError('birthdate must make the companion an adult under 120')
        if type(self.image_interval_minutes) is not int or self.image_interval_minutes not in (5,10,15,20,30,60,120,240,360,720,1440):
            raise ValueError('Choose a supported image interval between 5 minutes and 24 hours')
        if type(self.schedule_offset_minutes) is not int or not 0<=self.schedule_offset_minutes<15:
            raise ValueError('Schedule offset must be between 0 and 14 minutes')
        if not isinstance(self.bars,bool):raise ValueError('bars must be true or false')
        if isinstance(self.timeline_budget_gb,bool) or not isinstance(self.timeline_budget_gb,(int,float)) \
           or not 0<=self.timeline_budget_gb<=1000:
            raise ValueError('timeline_budget_gb must be a number of gigabytes between 0 and 1000')
        if self.agent_type not in AGENT_TYPES:
            raise ValueError(f'agent_type must be one of {sorted(AGENT_TYPES)}')
        if not isinstance(self.autonomy_windows,list) or len(self.autonomy_windows)>6:
            raise ValueError('autonomy_windows must be a list of at most six HH:MM times')
        for value in self.autonomy_windows:
            try:
                import datetime as _dt
                _dt.time.fromisoformat(str(value) if len(str(value))==5 else str(value)+':00')
            except (ValueError,TypeError):raise ValueError(f'{value!r} is not an HH:MM time')
        if not isinstance(self.share_people,bool):raise ValueError('share_people must be true or false')
        if not isinstance(self.sensors,list) or any(not isinstance(s,str) for s in self.sensors):
            raise ValueError('sensors must be a list of sensor names')
        if not isinstance(self.models,dict):raise ValueError('models must be an object')
        for key,value in self.models.items():
            if key=='fallbacks':
                if not isinstance(value,list) or len(value)>8:
                    raise ValueError('models.fallbacks must be a list of at most eight providers')
                continue
            if key not in JOB_TIERS:raise ValueError(f'unknown model tier {key!r}; expected {sorted(JOB_TIERS)}')
            if not isinstance(value,dict):raise ValueError(f'models.{key} must be an object')
            if set(value)-{'model','provider','reasoning_effort','base_url'}:raise ValueError('Unknown model tier field')
            if any(not isinstance(v,str) or len(v)>500 or any(ord(ch)<32 for ch in v) for v in value.values()):
                raise ValueError('Model tier values must be plain text')
            if value.get('base_url'):
                from urllib.parse import urlsplit
                endpoint=urlsplit(value['base_url'])
                if endpoint.scheme not in ('http','https') or not endpoint.hostname or endpoint.username or endpoint.password:
                    raise ValueError('Use an HTTP(S) model tier URL without credentials')
            effort=value.get('reasoning_effort')
            if effort not in (None,'') and effort not in REASONING_EFFORTS:
                raise ValueError(f'reasoning_effort must be one of {REASONING_EFFORTS}')
        self.hermes_root=pathlib.Path(self.hermes_root).expanduser().absolute()
        self.vault=pathlib.Path(self.vault).expanduser().absolute()
        if self.profile:
            from companion_platform import profile_name
            self.profile=profile_name(self.profile)
        if self.pronoun_set not in PRONOUNS or self.human_pronoun_set not in PRONOUNS:raise ValueError('Invalid pronouns')
        if not isinstance(self.image_timeline,bool):raise ValueError('image_timeline must be true or false')
        if self.context_mode not in ('auto','fixed'):raise ValueError('Invalid context mode')
        if not isinstance(self.context_tokens,int) or not 2048<=self.context_tokens<=10_000_000:raise ValueError('Invalid context window')
        if not isinstance(self.cron_active,bool):raise ValueError('cron_active must be true or false')
        if not isinstance(self.outreach_per_day,int) or not 0<=self.outreach_per_day<=100:
            raise ValueError('outreach_per_day must be a whole number of messages, 0 for no limit')
        if not isinstance(self.soul_in_vault,bool):raise ValueError('soul_in_vault must be true or false')

    # ---- per-job model choices -------------------------------------------
    def tier_model(self,tier:str)->dict:
        """What this tier of job should run on, or {} for the profile default."""
        value=self.models.get(tier) or {}
        return value if isinstance(value,dict) else {}

    # ---- age, computed rather than stored --------------------------------
    def born_on(self):
        try:
            import datetime as _dt
            return _dt.date.fromisoformat(self.birthdate) if self.birthdate else None
        except (ValueError,TypeError):return None

    def current_age(self,today=None)->int:
        """Age at `today`, from the birthdate. Falls back to the recorded number.

        Nothing stores an age. A companion created at 25 who is still 25 three
        years later is a companion who is not really there with you, and a
        number written down once is a number that quietly becomes wrong.
        """
        import datetime as _dt
        born=self.born_on()
        if not born:return int(self.age)
        today=today or _dt.date.today()
        return today.year-born.year-((today.month,today.day)<(born.month,born.day))

    def birthday_in(self,today=None):
        """Days until the next birthday, or None when no birthdate is set."""
        import datetime as _dt
        born=self.born_on()
        if not born:return None
        today=today or _dt.date.today()
        for year in (today.year,today.year+1):
            try:when=_dt.date(year,born.month,born.day)
            except ValueError:when=_dt.date(year,3,1) if born.month==2 else None
            if when and when>=today:return (when-today).days
        return None

    @property
    def has_inner_life(self)->bool:
        """Whether this agent has a present, moods and a relationship at all."""
        return self.agent_type in ('companion','colleague')

    def may_send(self,kind:str)->str:
        """Whether an unprompted message of this kind is allowed: yes, ask or no.

        Text defaults to yes because that is what outreach means; anything that
        arrives as a file defaults to ask, because a photo you did not request
        is a different kind of surprise from a sentence."""
        default={'text':'yes','image':'ask','voice':'ask'}.get(kind,'no')
        value=self.content_permissions.get(kind,default)
        return value if value in PERMISSIONS else default

    def fallbacks(self)->list:
        rows=self.models.get('fallbacks') or []
        return [r for r in rows if isinstance(r,dict) and r.get('model')][:2]

    # ---- locations -------------------------------------------------------
    @property
    def home(self)->pathlib.Path:
        """The agent's own Hermes home: root, or profiles/<name>/."""
        return self.hermes_root if not self.profile else self.hermes_root/'profiles'/self.profile

    @property
    def is_root(self)->bool:return not self.profile

    @property
    def soul(self)->pathlib.Path:
        """Where Hermes looks. This path is not configurable in Hermes (it is
        hardcoded as <hermes_home>/SOUL.md), so it stays put even when the real
        file lives in the vault behind a symlink."""
        return self.home/'SOUL.md'

    @property
    def canonical_soul(self)->pathlib.Path:
        """Where the file actually lives. In the vault by default, so the agent's
        identity is covered by the same backups and history as the rest of its
        life; ~/.hermes/SOUL.md then symlinks to it."""
        return (self.data/'soul'/'SOUL.md') if self.soul_in_vault else self.soul

    @property
    def soul_backups(self)->pathlib.Path:
        """Backups follow the canonical file so a vault restore brings them too."""
        return self.canonical_soul.parent/'soul-backups'

    @property
    def soul_linked(self)->bool:
        return self.soul.is_symlink() and self.soul.resolve()==self.canonical_soul.resolve()

    @property
    def data(self)->pathlib.Path:
        """Where this agent's life is stored. Profiles get their own subtree so two
        agents on one machine can never read or overwrite each other's history."""
        return self.vault if self.is_root else self.vault/'agents'/self.profile

    @property
    def life(self)->pathlib.Path:return self.data/'companion-life'
    @property
    def people(self)->pathlib.Path:
        """Where facts about the humans live: shared across agents, or this one's own."""
        return (self.vault/'people') if self.share_people else (self.data/'people')
    @property
    def human_dir(self)->pathlib.Path:return self.people/_slug(self.human)

    @property
    def all_names(self)->list:
        """Every name the agent may use for the human; the first is the real one."""
        return [n for n in (self.names or []) if n] or [self.human]
    @property
    def soul_dir(self)->pathlib.Path:return self.data/'soul'

    # ---- language --------------------------------------------------------
    @property
    def pronouns(self):
        return PRONOUNS.get(self.pronoun_set,PRONOUNS['she'])
    def subj(self):return self.pronouns[0]
    def obj(self):return self.pronouns[1]
    def poss(self):return self.pronouns[2]
    def refl(self):return self.pronouns[4]
    @property
    def human_pronouns(self):return PRONOUNS.get(self.human_pronoun_set,PRONOUNS['he'])
    def h_subj(self):return self.human_pronouns[0]
    def h_obj(self):return self.human_pronouns[1]
    def h_poss(self):return self.human_pronouns[2]

    # ---- budgets ---------------------------------------------------------
    @property
    def tier(self)->str:return tier(self.context_tokens)
    @property
    def soul_cap(self)->int:return soul_cap(self.context_tokens)
    @property
    def soul_warn(self)->int:return int(self.soul_cap*0.9)
    @property
    def injection_cap(self)->int:return injection_cap(self.context_tokens)
    @property
    def compact(self)->bool:
        """Small windows get a condensed rules block instead of losing sections."""
        return self.tier in ('tiny','small')

    def budgets(self)->dict:
        """Chars per injected section, scaled to the window. Rules and the lookup
        tail are reserved first and never sacrificed. On a small window whole
        sections are dropped (set to 0) in reverse priority order, because a
        90-character fragment of open loops helps nobody."""
        rules=380 if self.compact else 1450
        tail=260 if self.compact else 620
        free=max(0,self.injection_cap-rules-tail)
        keep=[k for i,k in enumerate(_PRIORITY) if (i+1)*_MIN_USEFUL<=free] or _PRIORITY[:1]
        wsum=sum(_WEIGHTS[k] for k in keep)
        out={k:0 for k in _WEIGHTS}
        for k in keep:out[k]=max(_MIN_USEFUL,int(free*_WEIGHTS[k]/wsum))
        # Rounding overshoot comes off the least important sections first, so the
        # highest-priority one is never the one that shrinks.
        over=sum(out.values())-free
        while over>0 and keep:
            # Shave the least important section that still has slack. Dropping a
            # whole section to absorb a few characters of rounding would be a poor
            # trade, so that is the last resort rather than the first move.
            slack=[k for k in reversed(keep) if out[k]>_MIN_USEFUL]
            if slack:
                k=slack[0];take=min(over,out[k]-_MIN_USEFUL)
                out[k]-=take;over-=take
            else:
                dropped=keep.pop();over-=out[dropped];out[dropped]=0
        out['rules'],out['tail'],out['total']=rules,tail,self.injection_cap
        return out

    # ---- io --------------------------------------------------------------
    def to_dict(self)->dict:
        d=dataclasses.asdict(self)
        d['hermes_root']=str(self.hermes_root);d['vault']=str(self.vault)
        return d

    def save(self,path:Optional[pathlib.Path]=None)->pathlib.Path:
        path=path or self.home/CONFIG_NAME
        path.parent.mkdir(parents=True,exist_ok=True)
        atomic_write(path,json.dumps(self.to_dict(),indent=2,ensure_ascii=False)+'\n')
        try:
            import companion_integrity
            if not companion_integrity.integrity_file_path(self).exists():
                companion_integrity.sign_creation(self)
        except Exception:
            pass
        return path

# A provider name alone does not identify a model's context window.

def detect_context_tokens(home:pathlib.Path,hermes_root:Optional[pathlib.Path]=None,model_name:Optional[str]=None)->tuple:
    """Work out the model's context window from Hermes itself.

    Returns (tokens, how). Nobody should have to know this number by hand, and a
    wrong answer silently changes how much the agent can carry, so we read it from
    the same places Hermes does rather than asking.
    """
    home=pathlib.Path(home);hermes_root=pathlib.Path(hermes_root or home)
    try:
        import yaml
    except ImportError:
        return DEFAULT_CONTEXT_TOKENS,FALLBACK_SOURCE+' (PyYAML unavailable)'
    cfg={}
    try:cfg=yaml.safe_load((home/'config.yaml').read_text(encoding='utf-8')) or {}
    except (OSError,Exception):cfg={}
    if not isinstance(cfg,dict):cfg={}
    model=cfg.get('model') if isinstance(cfg.get('model'),dict) else {}
    # 1. An explicit context_length in the agent's own config always wins.
    explicit=model.get('context_length')
    if isinstance(explicit,int) and not isinstance(explicit,bool) and 2048<=explicit<=10_000_000:
        return int(explicit),'config.yaml model.context_length'
    name=str(model_name or model.get('default') or model.get('model') or '').strip()
    base=str(model.get('base_url') or '').strip()
    provider=str(model.get('provider') or '').strip()
    # 2. Hermes' own measured cache, keyed model@base_url.
    cache={}
    for root in (hermes_root,home):
        try:
            data=yaml.safe_load((root/'context_length_cache.yaml').read_text(encoding='utf-8')) or {}
            cache.update(data.get('context_lengths') or {})
        except (OSError,Exception):continue
    if name:
        for key in (f'{name}@{base}',f'{name}@{base}/',f'{name}@{base.rstrip("/")}'):
            value=cache.get(key)
            if isinstance(value,int) and not isinstance(value,bool) and 2048<=value<=10_000_000:
                return value,'Hermes context_length_cache'
    # Read Hermes's local provider catalog without a network call on every turn.
    # Only use it for the provider's own endpoint: hosted variants may have smaller caps.
    from urllib.parse import urlparse
    for root in dict.fromkeys((home,hermes_root)):
        try:
            catalog=json.loads((root/'models_dev_cache.json').read_text(encoding='utf-8'))
            entry=catalog.get(provider,{})
            native=urlparse(entry.get('api','')).hostname
            if base and (not native or urlparse(base).hostname!=native):continue
            value=entry.get('models',{}).get(name,{}).get('limit',{}).get('context')
            if isinstance(value,int) and not isinstance(value,bool) and 2048<=value<=10_000_000:
                return value,'Hermes provider model catalog'
        except (OSError,ValueError,TypeError,AttributeError):continue
    return DEFAULT_CONTEXT_TOKENS,FALLBACK_SOURCE

def _slug(name:str)->str:
    keep=[c.lower() if c.isalnum() else '-' for c in (name or 'human').strip()]
    slug=''.join(keep).strip('-') or 'human'
    from companion_platform import WINDOWS_RESERVED
    return 'person-'+slug if slug in WINDOWS_RESERVED else slug

# Values written by an older version of this kit that the current one no longer
# accepts. The constructor stays strict — someone passing nonsense should hear
# about it — but a stored config is our own past output, and refusing to read it
# would take the agent's identity, hook and jobs down with it.
LEGACY_PRONOUNS=('it',)

def migrate(kwargs:dict)->dict:
    """Corrections applied when reading a config an older kit wrote. An
    unsupported pronoun set falls back to that field's current default rather
    than to a fixed one, so the companion and the human do not both become 'she'."""
    out={}
    for key,fallback in (('pronoun_set','she'),('human_pronoun_set','he')):
        value=kwargs.get(key)
        if isinstance(value,str) and value not in PRONOUNS:out[key]=fallback
    return out

def load(home:Optional[pathlib.Path]=None)->Companion:
    """Resolve the active companion: explicit home, else $TAMANITOMO_HOME, else
    $COMPANION_HOME, else $HERMES_HOME, else ~/.hermes. Missing config yields safe defaults."""
    home=pathlib.Path(home or os.environ.get('TAMANITOMO_HOME')
                      or os.environ.get('COMPANION_HOME')
                      or os.environ.get('HERMES_HOME') or default_home()).expanduser().absolute()
    path=home/CONFIG_NAME
    data={}
    if path.exists():
        try:data=json.loads(path.read_text(encoding='utf-8'))
        except ValueError as exc:raise ValueError(f'Invalid companion configuration: {path}') from exc
        if not isinstance(data,dict):raise ValueError(f'Configuration must be an object: {path}')
    fields={f.name for f in dataclasses.fields(Companion)}
    kwargs={k:v for k,v in data.items() if k in fields}
    for k in ('hermes_root','vault'):
        if k in kwargs:kwargs[k]=pathlib.Path(kwargs[k])
    kwargs.update(migrate(kwargs))
    c=Companion(**kwargs)
    # INVARIANT: the home we were asked for is the home we return. Deriving these
    # from the path rather than trusting stored/default values is what stops a
    # caller pointed at a sandbox from resolving to the real ~/.hermes and writing
    # there. load(X).home == X, always.
    if home.parent.name=='profiles':
        c=dataclasses.replace(c,profile=home.name,hermes_root=home.parent.parent)
    else:
        c=dataclasses.replace(c,profile='',hermes_root=home)
    if c.context_mode=='auto':
        tokens,source=detect_context_tokens(home,c.hermes_root)
        if detected_for_real(source) or (home/'config.yaml').exists():
            c=dataclasses.replace(c,context_tokens=tokens)
    assert c.home==home,f'home invariant violated: {c.home} != {home}'
    return c

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--home',type=pathlib.Path);a=p.parse_args()
    c=load(a.home)
    print(json.dumps({'agent':c.agent,'profile':c.profile or '(root)','home':str(c.home),
                      'data':str(c.data),'tier':c.tier,'context_tokens':c.context_tokens,
                      'soul_cap':c.soul_cap,'soul_warn':c.soul_warn,
                      'budgets':c.budgets()},indent=2))


def access_pin(root, fallback=''):
    """One host access policy, shared by all selectable profiles and the CLI.

    Older installs stored PINs in companion.json. Conflicting legacy PINs need
    a local reset rather than arbitrarily trusting an unprotected profile.
    """
    root = pathlib.Path(root)
    path = root / '.tamanitomo-access.json'
    if path.exists():
        value = json.loads(path.read_text(encoding='utf-8')).get('remote_pin', '')
    else:
        pins = {fallback} if fallback else set()
        for legacy in [root / CONFIG_NAME, *sorted((root / 'profiles').glob('*/' + CONFIG_NAME))]:
            if legacy.exists():
                pin = json.loads(legacy.read_text(encoding='utf-8')).get('remote_pin', '')
                if pin:pins.add(pin)
        if len(pins) > 1:
            raise ValueError('Conflicting legacy PINs. Set one workspace PIN locally.')
        value = next(iter(pins), '')
    if not isinstance(value, str) or (value and (len(value) != 4 or not value.isascii() or not value.isdigit())):
        raise ValueError('Invalid workspace access PIN')
    return value


def save_access_pin(root, pin):
    if not isinstance(pin, str) or (pin and (len(pin) != 4 or not pin.isascii() or not pin.isdigit())):
        raise ValueError('PIN must contain exactly four digits, or be empty')
    path = pathlib.Path(root) / '.tamanitomo-access.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps({'remote_pin': pin}) + '\n')
    path.chmod(0o600)
