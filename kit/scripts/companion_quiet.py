#!/usr/bin/env python3
"""Let the sleep window drift toward the hours actually kept. Opt-in, evidence-only.

A do-not-disturb window set once at setup describes the night someone imagined
having. If they are visibly writing at one in the morning, week after week, the
window is wrong — and the cost of it being wrong is a companion holding
something back from a person who is plainly awake.

The rules here are deliberately timid, because getting this wrong means messages
at an hour someone is asleep:

  - Evidence only. It moves on messages the human actually sent, never on a
    guess, a preference or a mood.
  - A fortnight of it, not a night. One late evening is a late evening.
  - Half an hour at a time. Never a jump.
  - Never below six hours of quiet, whatever the evidence says.
  - It tells you once, each time it moves. A window that changes silently is a
    window you cannot trust.
"""
from __future__ import annotations
import argparse, datetime as dt, json, pathlib, sqlite3, sys
from zoneinfo import ZoneInfo
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
from companion_platform import atomic_write

LOOKBACK_DAYS=14
MIN_NIGHTS=5            # nights out of the fortnight that must show the pattern
STEP_MINUTES=30
MIN_QUIET_MINUTES=6*60
EDGE_MINUTES=90         # only messages within this much of an edge count

def _tz(c):
    try:return ZoneInfo(c.timezone)
    except Exception:return ZoneInfo('UTC')

def _minutes(hhmm,fallback):
    try:
        t=dt.time.fromisoformat(hhmm if len(hhmm)==5 else hhmm+':00')
        return t.hour*60+t.minute
    except (ValueError,TypeError):return fallback

def _hhmm(minutes):
    minutes%=24*60
    return f'{minutes//60:02d}:{minutes%60:02d}'

def quiet_length(start,end):
    return (end-start)%(24*60) or 24*60

def human_messages(c,now,days=LOOKBACK_DAYS):
    """When the human wrote, over the lookback window. Their own profile only."""
    db=c.home/'state.db'
    if not db.exists():return []
    con=None
    try:
        resolved=db.resolve()
        if c.is_root and resolved.is_relative_to((c.hermes_root/'profiles').resolve()):return []
        if c.is_root:scope="lower(coalesce(s.profile_name,'')) IN ('','default')";params=()
        else:scope="lower(coalesce(s.profile_name,'')) IN ('','default',?)";params=(c.profile.lower(),)
        since=(now-dt.timedelta(days=days)).timestamp()
        con=sqlite3.connect(resolved.as_uri()+'?mode=ro',uri=True,timeout=1)
        con.execute('PRAGMA query_only=ON')
        rows=list(con.execute(f"""SELECT m.timestamp FROM messages m JOIN sessions s ON s.id=m.session_id
            WHERE m.role='user' AND {scope} AND m.timestamp>=?""",params+(since,)))
    except (sqlite3.Error,OSError):return []
    finally:
        if con:con.close()
    out=[]
    for (stamp,) in rows:
        try:out.append(dt.datetime.fromtimestamp(float(stamp),dt.timezone.utc).astimezone(_tz(c)))
        except (TypeError,ValueError,OverflowError):continue
    return out

def evidence(c,now,messages=None):
    """Nights showing activity just inside each edge of the window."""
    messages=human_messages(c,now) if messages is None else messages
    start=_minutes(c.quiet_start,23*60);end=_minutes(c.quiet_end,8*60)
    late,early=set(),set()
    for when in messages:
        minute=when.hour*60+when.minute
        after_start=(minute-start)%(24*60)
        before_end=(end-minute)%(24*60)
        # A night is dated by the evening it began, so 01:00 counts toward the
        # night before rather than reading as a brand-new day of evidence.
        night=(when-dt.timedelta(hours=12)).date()
        if 0<after_start<=EDGE_MINUTES:late.add(night)
        if 0<before_end<=EDGE_MINUTES:early.add(night)
    return {'late_nights':len(late),'early_mornings':len(early),
            'start':start,'end':end,'messages':len(messages)}

def propose(c,now=None,messages=None):
    """What the window should become, if anything. Never applies it."""
    now=now or dt.datetime.now(_tz(c))
    if not c.adaptive_quiet:
        return {'change':False,'reason':'adaptive quiet hours are switched off for this companion'}
    facts=evidence(c,now,messages)
    start,end=facts['start'],facts['end']
    new_start,new_end=start,end
    notes=[]
    if facts['late_nights']>=MIN_NIGHTS:
        new_start=(start+STEP_MINUTES)%(24*60)
        notes.append(f"{c.human} wrote after {_hhmm(start)} on {facts['late_nights']} nights")
    if facts['early_mornings']>=MIN_NIGHTS:
        new_end=(end-STEP_MINUTES)%(24*60)
        notes.append(f"{c.human} wrote before {_hhmm(end)} on {facts['early_mornings']} mornings")
    if (new_start,new_end)==(start,end):
        return {'change':False,'reason':'no consistent pattern in the last fortnight','evidence':facts}
    if quiet_length(new_start,new_end)<MIN_QUIET_MINUTES:
        return {'change':False,'evidence':facts,
                'reason':f'that would leave less than {MIN_QUIET_MINUTES//60} hours of quiet, '
                         f'so the window stays where it is'}
    return {'change':True,'quiet_start':_hhmm(new_start),'quiet_end':_hhmm(new_end),
            'was':{'quiet_start':_hhmm(start),'quiet_end':_hhmm(end)},
            'why':'; '.join(notes),'evidence':facts}

def apply(c,now=None,messages=None):
    """Move the window, record it, and leave a note for the companion to mention."""
    now=now or dt.datetime.now(_tz(c))
    plan=propose(c,now,messages)
    if not plan.get('change'):return plan
    c.quiet_start=plan['quiet_start'];c.quiet_end=plan['quiet_end'];c.save()
    path=c.soul_dir/'ambient/quiet-hours.md'
    path.parent.mkdir(parents=True,exist_ok=True)
    atomic_write(path,
        f"Your quiet hours moved to {plan['quiet_start']}–{plan['quiet_end']} "
        f"(from {plan['was']['quiet_start']}–{plan['was']['quiet_end']}), because {plan['why']}.\n\n"
        f"Mention it once, in passing, the next time it is natural — {c.human} should know the window "
        f"changed and can move it back. Do not raise it again after that.\n")
    log=c.data/'quiet-hours-history.jsonl'
    with log.open('a',encoding='utf-8') as f:
        f.write(json.dumps({'at':now.isoformat(),**{k:v for k,v in plan.items() if k!='evidence'}},
                           ensure_ascii=False)+'\n')
    return {**plan,'applied':True}

def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--home',type=pathlib.Path)
    p.add_argument('--apply',action='store_true',help='without this, only reports what it would do')
    a=p.parse_args();c=cc.load(a.home)
    result=apply(c) if a.apply else propose(c)
    if result.get('change') or result.get('applied'):print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__':
    try:sys.exit(main() or 0)
    except (ValueError,OSError) as e:
        print(f'{e}',file=sys.stderr);sys.exit(1)
