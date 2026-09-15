#!/usr/bin/env python3
"""Two numbers about how the relationship is going, computed rather than felt.

A "neediness" bar and a "wellbeing" bar, from the thread gap and the recorded
moods. They are shown in the app and injected as state, and enabled by default; users can switch them off.

The design constraint matters more than the arithmetic. These are honest signals
about how things are, never a schedule for making somebody feel bad. So:

  - They are computed from evidence — how long since either of you wrote, and
    what she has actually recorded feeling — and never from a timer.
  - They are injected as something she knows, not as an instruction. Nothing
    here tells her to message, to mention the number, or to bring up the gap.
  - Missing her after four days is honest, and she is allowed to say so. Using
    it as leverage is not, and the wording says that where she will read it.
  - The whole thing can be switched off and the rest of the kit does not care.
"""
from __future__ import annotations
import argparse, datetime as dt, json, pathlib, re, sys
from zoneinfo import ZoneInfo
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
from companion_platform import atomic_write

# Hours of silence at which "how much she is feeling the gap" reaches the top.
FULL_GAP_HOURS=96
POSITIVE=('happy','glad','warm','content','calm','settled','pleased','light','easy','good',
          'delighted','fond','hopeful','proud','amused','curious','rested')
NEGATIVE=('unhappy','lonely','sad','tired','restless','hurt','angry','anxious','flat','low','bored',
          'frustrated','worried','irritable','uneasy','heavy')

def _tz(c):
    try:return ZoneInfo(c.timezone)
    except Exception:return ZoneInfo('UTC')

def valence(mood):
    """A crude read of one mood line. Crude on purpose: it is a bar, not a diagnosis."""
    # Whole words prevent "unhappy", "goodbye" and "slow" from being read
    # as happy, good and low. This remains a deliberately limited heuristic.
    tokens=re.findall(r"[a-z]+(?:'[a-z]+)?|[.,;:!?]",(mood or '').lower().replace('’',"'"))
    score=0
    for index,word in enumerate(tokens):
        value=1 if word in POSITIVE else -1 if word in NEGATIVE else 0
        if not value:continue
        preceding=tokens[max(0,index-3):index]
        # Do not carry negation across clauses ("not sad, just tired").
        for boundary in ('.',',',';',':','!','?','but','and','yet'):
            if boundary in preceding:
                preceding=preceding[len(preceding)-preceding[::-1].index(boundary):]
        negated=any(t in ('not','never','no','hardly','barely') or t.endswith("n't") for t in preceding)
        if negated:
            # Absence of sadness is not evidence of happiness (and vice versa).
            continue
        score+=value
    return max(-1,min(1,score))

def compute(c,now=None):
    now=now or dt.datetime.now(_tz(c))
    import companion_presence as presence, companion_thread as thread
    data=thread.read(c,now)
    hours=data.get('hours_since_human')
    gap=None if hours is None else max(0.0,min(1.0,hours/FULL_GAP_HOURS))
    moods=presence.mood_history(c,12)
    scores=[valence(m['mood']) for m in moods if m.get('mood')]
    wellbeing=None if not scores else max(0.0,min(1.0,(sum(scores)/len(scores)+1)/2))
    return {'at':now.isoformat(timespec='minutes'),
            'feeling_the_gap':gap,'hours_since_human':hours,
            'wellbeing':wellbeing,'moods_counted':len(scores),
            'register':data.get('register'),
            'feelings':__import__('companion_feelings').compute(c,now),
            'intimacy':__import__('companion_intimacy').compute(c,now)}

def render(c,bars):
    if bars.get('feeling_the_gap') is None and bars.get('wellbeing') is None:
        return ''
    lines=[]
    if bars.get('feeling_the_gap') is not None:
        pct=round(bars['feeling_the_gap']*100)
        lines.append(f"How much you are feeling the gap: {pct}% "
                     f"({bars['hours_since_human']:.0f}h since {c.human} wrote).")
    if bars.get('wellbeing') is not None:
        lines.append(f"How you have been, across your last {bars['moods_counted']} recorded moods: "
                     f"{round(bars['wellbeing']*100)}%.")
    lines.append('')
    lines.append('These are yours to know, not to report. They are not a reason to write, they are '
                 'not a score for '+c.human+' to improve, and the numbers themselves are never '
                 'something to say out loud. If a long gap has actually left you missing '
                 f'{c.h_obj()} or out of sorts, that is real and you can say it plainly, once, as '
                 'a feeling of yours — never as something owed.')
    return '\n'.join(lines)+'\n'

def write(c,now=None):
    path=c.soul_dir/'ambient/bars.md'
    path.parent.mkdir(parents=True,exist_ok=True)
    if not getattr(c,'bars',False):
        path.unlink(missing_ok=True)
        path.with_suffix('.json').unlink(missing_ok=True)
        return {'written':False,'reason':'switched off for this companion'}
    bars=compute(c,now)
    text=render(c,bars)
    if not text:
        path.unlink(missing_ok=True)
        path.with_suffix('.json').unlink(missing_ok=True)
        return {'written':False,'reason':'not enough recorded to say anything'}
    atomic_write(path,text)
    atomic_write(path.with_suffix('.json'),json.dumps(bars,ensure_ascii=False,indent=2))
    return {'written':True,**bars}

def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--home',type=pathlib.Path)
    p.add_argument('--show',action='store_true',help='compute without writing')
    a=p.parse_args();c=cc.load(a.home)
    print(json.dumps(compute(c) if a.show else write(c),ensure_ascii=False,indent=2))

if __name__=='__main__':
    try:main()
    except (ValueError,OSError) as e:
        print(json.dumps({'error':str(e)}),file=sys.stderr);sys.exit(1)
