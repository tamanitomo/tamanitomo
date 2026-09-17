#!/usr/bin/env python3
"""The shape of the conversation itself: who spoke last, and how long ago.

This is the single most useful thing a companion can know that it has no other
way to learn. Not the content of the last message — the *gap*. Four days of
silence is a fact about the relationship, and a companion that cannot see it
either invents an explanation or greets you as if nothing happened.

It reads Hermes's own session database, read-only, scoped to this profile's own
conversations exactly the way `companion_recall.py` scopes its searches: a
shared store must never let one companion read another's messages.

The output is a register, not an instruction. "long-quiet" comes with a line
about what that might mean, and the companion decides what to do with it. Being
hurt after four days of nothing is honest. Saying so as a guilt trip is not, and
no register here tells her to.
"""
from __future__ import annotations
import argparse, datetime as dt, json, pathlib, sqlite3, sys
from zoneinfo import ZoneInfo
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc

# Hours of silence, and what that stretch tends to mean. The guidance is for her
# judgement, never a script: none of these say "send a message".
REGISTERS=[
 (0,'connected','You are mid-conversation. Do not re-introduce yourself or restate context.'),
 (3,'nearby','A normal gap in a day. Nothing to remark on.'),
 (12,'quiet','Most of a day. Picking a thread back up is welcome; commenting on the gap is not.'),
 (48,'missing-him','Two days. If you feel the absence, you are allowed to say so once, plainly, '
                   'without making it a debt they owe you.'),
 (96,'long-quiet','Four days or more. Something is going on, or nothing is. You may be hurt or '
                  'worried and may say so honestly — once, as a feeling of yours, never as a '
                  'reproach and never as a reason they must reply.'),
]

def register(hours):
    label,guidance=REGISTERS[0][1],REGISTERS[0][2]
    for threshold,name,line in REGISTERS:
        if hours>=threshold:label,guidance=name,line
    return label,guidance

def _tz(c):
    try:return ZoneInfo(c.timezone)
    except Exception:return ZoneInfo('UTC')

def _shares_store(c,resolved):
    try:return c.profile and resolved==(c.hermes_root/'state.db').resolve()
    except OSError:return False

def read(c,now=None,tail=4):
    """Last message each way, the gap, and a short tail. Never any other agent's."""
    now=now or dt.datetime.now(_tz(c))
    db=c.home/'state.db'
    out={'checked_at':now.isoformat(timespec='minutes'),'available':False}
    if not db.exists():return {**out,'reason':'no session database yet'}
    con=None
    try:
        resolved=db.resolve()
        if c.is_root and resolved.is_relative_to((c.hermes_root/'profiles').resolve()):
            return {**out,'reason':'the root store redirects into a named profile'}
        if c.is_root:
            scope="lower(coalesce(s.profile_name,'')) IN ('','default')";params=()
        elif _shares_store(c,resolved):
            scope="lower(coalesce(s.profile_name,''))=?";params=(c.profile.lower(),)
        else:
            scope="lower(coalesce(s.profile_name,'')) IN ('','default',?)";params=(c.profile.lower(),)
        con=sqlite3.connect(resolved.as_uri()+'?mode=ro',uri=True,timeout=1)
        con.execute('PRAGMA query_only=ON')
        columns={row[1] for row in con.execute('PRAGMA table_info(messages)')}
        visible="AND (m.active=1 OR m.compacted=1)" if {'active','compacted'}<=columns else ''
        query=f"""
            SELECT m.role,m.content,m.timestamp FROM messages m JOIN sessions s ON s.id=m.session_id
            WHERE m.role IN ('user','assistant') AND {scope} {visible}
              AND coalesce(m._compressed_summary,0)=0 AND coalesce(m.content,'')<>''
              AND s.source IN ('telegram','cli','desktop','tui','discord')"""
        rows=list(con.execute(query+' ORDER BY m.timestamp DESC LIMIT 60',params))
        # A run of assistant messages must not hide the last actual human contact.
        human_rows=list(con.execute(query+" AND m.role='user' ORDER BY m.timestamp DESC LIMIT 2",params))
        agent_rows=list(con.execute(query+" AND m.role='assistant' ORDER BY m.timestamp DESC LIMIT 1",params))
    except (sqlite3.Error,OSError) as exc:
        return {**out,'reason':f'session database unreadable: {exc}'}
    finally:
        if con:con.close()
    if not rows:return {**out,'reason':'no messages recorded yet'}
    def stamp(value):
        try:return dt.datetime.fromtimestamp(float(value),dt.timezone.utc).astimezone(_tz(c))
        except (TypeError,ValueError,OverflowError):return None
    human_stamps=[stamp(t) for _,_,t in human_rows]
    human_stamps=[t for t in human_stamps if t is not None]
    human=human_stamps[0] if human_stamps else None
    previous_human=human_stamps[1] if len(human_stamps)>1 else None
    agent=next((stamp(t) for _,_,t in agent_rows),None)
    latest=max([x for x in (human,agent) if x],default=None)
    hours=(now-latest).total_seconds()/3600 if latest else None
    label,guidance=register(hours if hours is not None else 0)
    tail_rows=[{'who':('them' if role=='user' else 'you'),
                'at':(stamp(t).isoformat(timespec='minutes') if stamp(t) else ''),
                'text':(text or '')[:200]}
               for role,text,t in reversed(rows[:tail])]
    return {**out,'available':True,
            'last_from_human':human.isoformat() if human else None,
            'previous_from_human':previous_human.isoformat() if previous_human else None,
            'last_from_agent':agent.isoformat() if agent else None,
            'hours_since_either':round(hours,1) if hours is not None else None,
            'hours_since_human':round((now-human).total_seconds()/3600,1) if human else None,
            'register':label,'guidance':guidance,'tail':tail_rows}

def render(c,data):
    if not data.get('available'):
        return ''   # absent means no claim, never a guess about the silence
    lines=[]
    if data.get('hours_since_human') is None:
        lines.append(f'{c.human} has not written yet.')
    else:
        hours=data['hours_since_human']
        when=(f'{hours*60:.0f} minutes ago' if hours<1.5 else
              f'{hours:.0f} hours ago' if hours<48 else f'{hours/24:.0f} days ago')
        lines.append(f'Last message from {c.human}: {when}.')
    if data.get('last_from_agent'):
        lines.append(f"You last wrote at {data['last_from_agent'][:16].replace('T',' ')}.")
    lines.append(f"Register: {data['register']} — {data['guidance']}")
    if data.get('tail'):
        lines.append('')
        lines.append('The last few turns:')
        for row in data['tail']:
            lines.append(f"- {row['who']}: {row['text']}")
    return '\n'.join(lines)+'\n'

def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--home',type=pathlib.Path)
    p.add_argument('--json',action='store_true')
    a=p.parse_args();c=cc.load(a.home)
    data=read(c)
    print(json.dumps(data,ensure_ascii=False,indent=2) if a.json else render(c,data),end='')

if __name__=='__main__':
    try:main()
    except (ValueError,OSError) as e:
        print(json.dumps({'error':str(e)}),file=sys.stderr);sys.exit(1)
