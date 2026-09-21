#!/usr/bin/env python3
"""The declared night. One place that answers "is she asleep, and until when?".

A sleep window was previously only a clock — the quiet hours someone set at
setup — and every job re-derived it from whatever it happened to be looking at.
That is how a night ends up with thirty photographs of the same dark bedroom:
nothing was actually asserting "asleep until seven", so each tick was free to
treat the scene as new.

So sleep is declared, once, before it starts. Wind-down writes down how long the
night is meant to be; everything overnight reads that one answer instead of
guessing. A declaration is a plan, not a cage — `wake` ends it early, and the
plan simply expires on its own at the hour it named.

Three rules, because a wrong answer here is either a companion who vanishes for
a day or one who narrates a night nobody watched:

  - Declared beats derived. A written plan wins over the quiet-hours clock.
  - Absent a plan, fall back to quiet hours. A night with no declaration is
    still a night; this is never the reason images appear at 03:00.
  - A plan expires. It is bounded to a plausible night and never outlives one,
    so a stale file cannot keep someone asleep through a Tuesday.
"""
from __future__ import annotations
import argparse, datetime as dt, json, pathlib, sys
from zoneinfo import ZoneInfo
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
from companion_platform import atomic_write

# A declared night is bounded at both ends. Below the floor it is a nap and the
# jobs should keep running; above the ceiling something wrote a bad plan and the
# fallback clock is the safer answer.
MIN_HOURS=1
MAX_HOURS=14

def _tz(c):
    try:return ZoneInfo(c.timezone)
    except Exception:return ZoneInfo('UTC')

def path(c):return c.life/'sleep.json'

def _minutes(hhmm,fallback):
    try:
        t=dt.time.fromisoformat(hhmm if len(hhmm)==5 else hhmm+':00')
        return t.hour*60+t.minute
    except (ValueError,TypeError):return fallback

def _next_at(now,hhmm):
    """The next time today or tomorrow that reads HH:MM, in the local zone."""
    minute=_minutes(hhmm,None)
    if minute is None:raise ValueError('Give the time as HH:MM, e.g. 07:00')
    target=now.replace(hour=minute//60,minute=minute%60,second=0,microsecond=0)
    return target+dt.timedelta(days=1) if target<=now else target

def messaged_recently(c,now):
    """Did the human write within the grace window? The dispatcher owns this question."""
    try:
        import companion_dispatch
        return companion_dispatch.recently_active(c,now)
    except (ImportError,OSError,ValueError):return False

def presence_asleep(c):
    """Her own recorded state, read from a CODE-OWNED field rather than prose.

    `activity` is a sentence someone writes fresh every tick, so sniffing it for
    the word "asleep" both misses ("dozing off", "asleep," with a comma) and
    over-matches ("sleeping in late", "reading about sleep"). A boolean she sets
    deliberately is the only version of this that holds still.
    """
    try:
        import companion_presence
        scene=companion_presence.current(c)
        return bool(scene and scene['state'].get('asleep'))
    except (ImportError,OSError,ValueError):return False

def read(c,now=None):
    """The declared plan as written. Malformed or implausible reads as none.

    An expired plan is still returned: "she declared she would be up at seven"
    is an answer, and a useful one, right up until the next night is declared.
    """
    try:data=json.loads(path(c).read_text(encoding='utf-8'))
    except (OSError,ValueError):return None
    if not isinstance(data,dict):return None
    try:
        start=dt.datetime.fromisoformat(str(data['from']))
        until=dt.datetime.fromisoformat(str(data['until']))
    except (KeyError,TypeError,ValueError):return None
    if start.tzinfo is None or until.tzinfo is None:return None
    if not dt.timedelta(hours=MIN_HOURS)<=until-start<=dt.timedelta(hours=MAX_HOURS):return None
    return {**data,'from':start,'until':until}

def status(c,now=None):
    """Is she asleep right now, until when, and on whose authority?

    `declared` is a plan she wrote. `quiet-hours` is the configured clock, used
    only when nothing was declared — so the overnight gates hold on the very
    first night, before any wind-down has run.
    """
    now=now or dt.datetime.now(_tz(c))
    now=now.astimezone(_tz(c))
    # Being written to wakes her. Someone typing at two in the morning is not an
    # argument for staying asleep, and a companion who sleeps through being spoken
    # to is worse than one who is up late.
    if messaged_recently(c,now):
        return {'asleep':False,'source':'messaged',
                'note':'The human wrote recently, so she is awake whatever the hour.'}
    plan=read(c,now)
    if plan:
        if plan['from']<=now<plan['until']:
            return {'asleep':True,'source':'declared','until':plan['until'].isoformat(timespec='minutes'),
                    'until_local':plan['until'].strftime('%H:%M'),
                    'minutes_left':int((plan['until']-now).total_seconds()//60),
                    'note':plan.get('note',''),'declared_at':plan.get('declared_at')}
        # Declared beats the clock in BOTH directions. Someone who wrote down a six o'clock
        # start is awake at six, even though the quiet-hours setting still reads 08:00 — and
        # falling back to that setting here would quietly overrule the plan it just kept.
        # The declaration governs its own night and no longer, so a plan is honoured until
        # the night it belongs to is over rather than forever.
        if now<plan['until']+dt.timedelta(hours=MAX_HOURS):
            return {'asleep':False,'source':'declared','starts':plan['from'].isoformat(timespec='minutes'),
                    'until':plan['until'].isoformat(timespec='minutes'),
                    'expired':now>=plan['until']}
    # No live declaration, so her own recorded state answers. Quiet hours deliberately
    # do NOT appear here: they are a rule about not CONTACTING the human, not a claim
    # that she has stopped living. Treating the two as one thing is what made a night
    # of quiet hours shut down her whole life rather than just her outbox.
    if presence_asleep(c):
        return {'asleep':True,'source':'presence',
                'note':'She recorded herself as asleep; no length was declared, so this ends when she wakes.'}
    return {'asleep':False,'source':'awake'}

def asleep(c,now=None):
    """The one-line question every overnight job actually asks."""
    return bool(status(c,now).get('asleep'))

def declare(c,until,note='',now=None):
    """Write the night down before it starts."""
    now=(now or dt.datetime.now(_tz(c))).astimezone(_tz(c))
    end=_next_at(now,until)
    span=end-now
    if span<dt.timedelta(hours=MIN_HOURS):
        raise ValueError(f'A declared night runs at least {MIN_HOURS} hour; for a nap, just stay awake on the record')
    if span>dt.timedelta(hours=MAX_HOURS):
        raise ValueError(f'A declared night runs at most {MAX_HOURS} hours; {until} is too far off')
    plan={'declared_at':now.isoformat(timespec='minutes'),'from':now.isoformat(timespec='minutes'),
          'until':end.isoformat(timespec='minutes'),'hours':round(span.total_seconds()/3600,2),
          'note':str(note or '').strip()[:300]}
    path(c).parent.mkdir(parents=True,exist_ok=True)
    atomic_write(path(c),json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    return plan

def wake(c,now=None):
    """End the declared night, early or on time. Getting up early is allowed.

    This shortens the night rather than deleting it. A deleted plan would hand
    the answer back to the quiet-hours clock, which is how someone who got up at
    six would be told they are still asleep until eight — the exact overruling
    the declaration exists to prevent.
    """
    now=(now or dt.datetime.now(_tz(c))).astimezone(_tz(c))
    plan=read(c,now)
    if not plan:return {'woke':True,'was':None,'note':'No night was declared; nothing to end.'}
    was=plan['until']
    # Below the minimum night the plan stops being plausible and read() would discard
    # it, so a night cut very short is simply cleared instead.
    if now-plan['from']<dt.timedelta(hours=MIN_HOURS):
        try:path(c).unlink()
        except OSError:pass
    else:
        ended={**{k:v for k,v in plan.items() if k not in ('from','until')},
               'from':plan['from'].isoformat(timespec='minutes'),
               'until':now.isoformat(timespec='minutes'),
               'hours':round((now-plan['from']).total_seconds()/3600,2),
               'woke_early_from':was.isoformat(timespec='minutes')}
        atomic_write(path(c),json.dumps(ended,ensure_ascii=False,indent=2)+'\n')
    return {'woke':True,'was':was.isoformat(timespec='minutes'),'at':now.isoformat(timespec='minutes')}

def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--home',type=pathlib.Path)
    s=p.add_subparsers(dest='cmd',required=True)
    d=s.add_parser('declare',help='Declare how long tonight is meant to be, before sleeping')
    d.add_argument('--until',required=True,help='Intended wake time as HH:MM, e.g. 07:00')
    d.add_argument('--note',default='',help='Anything worth knowing about tonight')
    s.add_parser('status',help='Is she asleep right now, and until when')
    s.add_parser('wake',help='End the declared night early')
    a=p.parse_args();c=cc.load(a.home)
    if a.cmd=='declare':out=declare(c,a.until,a.note)
    elif a.cmd=='wake':out=wake(c)
    else:out=status(c)
    print(json.dumps(out,ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__':
    try:sys.exit(main() or 0)
    except (ValueError,OSError) as e:
        print(f'{e}',file=sys.stderr);sys.exit(1)
