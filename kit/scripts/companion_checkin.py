#!/usr/bin/env python3
"""Reflect within minutes of a conversation, not at four in the morning.

The daily job is the right place for the shape of a day. It is the wrong place
for "he mentioned his sister is called Bee" — twelve hours later, that detail is
competing with everything else that happened, and the session it came from may
already have been compacted.

So: when a session ends, Hermes runs `session_end` and this writes a flag. A
cron job gated by `--monitor-script` on that flag then runs a small reflection
within a few minutes, and is suppressed entirely the rest of the time. Nothing
runs when nothing has been said.

Two modes, matching the two things Hermes needs:

  flag        called from the session_end hook; records that a session ended
  fingerprint printed for --monitor-script; changes only when a new session has
              ended since the last reflection, so the job runs once per
              conversation rather than every tick
"""
from __future__ import annotations
import argparse, datetime as dt, json, pathlib, sys
from zoneinfo import ZoneInfo
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
from companion_platform import atomic_write, file_lock

def _tz(c):
    try:return ZoneInfo(c.timezone)
    except Exception:return ZoneInfo('UTC')

def path_for(c):return c.life/'session-flag.json'

def read(c):
    try:return json.loads(path_for(c).read_text(encoding='utf-8'))
    except (OSError,ValueError):return {'pending':0,'last_end':'','last_reflected':''}

# The same owner-facing surfaces the trusted Chat reader treats as the owner's
# conversation (chat_sources.session_kind: LOCAL_SOURCES plus telegram). Cron,
# subagent, tool turns and anything unrecognised are internal, never owner speech.
OWNER_PLATFORMS=frozenset({'cli','desktop','tui','telegram'})

def flag(c,now=None,session_id='',platform='',trusted=False):
    """A session ended. Cheap, and safe to call from a hook.

    Only a session Hermes attributes to an owner-facing platform re-arms the
    job. Without this, the check-in's own reflection turn ends on platform
    'cron' and its session_end flags a new conversation, so the job re-arms
    itself and never goes quiet -- it was never told the difference between a
    real conversation ending and its own turn ending. An unset or unrecognised
    platform is treated as internal, not guessed as owner speech.

    `trusted=True` is for the rare internal caller (nightly rollover) that has
    already established real human activity by reading the session DB itself,
    rather than relaying an on_session_end payload; it is never set from hook
    input.
    """
    if not trusted and str(platform or '') not in OWNER_PLATFORMS:return read(c)
    now=now or dt.datetime.now(_tz(c))
    with file_lock(path_for(c).with_suffix('.json.lock')):
        state=read(c)
        state['pending']=int(state.get('pending',0))+1
        state['last_end']=now.isoformat()
        if session_id:state['last_session']=str(session_id)[:120]
        atomic_write(path_for(c),json.dumps(state,ensure_ascii=False,indent=2))
    return state

def clear(c,now=None):
    """A reflection happened. Called by the job itself once it has recorded.

    It clears the sessions the job was started for -- the count its monitor tick
    saw -- not whatever is pending by the time it finishes. Zeroing the counter
    erased a conversation that ended while the reflection was running, and nothing
    would ever look at it.
    """
    now=now or dt.datetime.now(_tz(c))
    with file_lock(path_for(c).with_suffix('.json.lock')):
        state=read(c)
        pending=int(state.get('pending',0) or 0)
        claimed=state.pop('claimed',None)
        state['pending']=0 if claimed is None else max(0,pending-int(claimed))
        state['last_reflected']=now.isoformat()
        atomic_write(path_for(c),json.dumps(state,ensure_ascii=False,indent=2))
    return state

def fingerprint(c):
    """Stable bytes for --monitor-script. Changes only when there is something to do.

    No clock in here at all: this is the one gate that should stay silent
    indefinitely when nobody is talking. It notes how many sessions it has seen,
    so the run it triggers clears exactly those.
    """
    with file_lock(path_for(c).with_suffix('.json.lock')):
        state=read(c)
        pending=int(state.get('pending',0) or 0)
        if pending and state.get('claimed')!=pending:
            state['claimed']=pending
            atomic_write(path_for(c),json.dumps(state,ensure_ascii=False,indent=2))
    return f"pending {pending}\nlast_end {state.get('last_end','') if pending else ''}\n"

def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--home',type=pathlib.Path)
    p.add_argument('--platform',default='')
    p.add_argument('mode',choices=['flag','fingerprint','clear','status'],nargs='?',default='fingerprint')
    a=p.parse_args();c=cc.load(a.home)
    if a.mode=='fingerprint':sys.stdout.write(fingerprint(c))
    elif a.mode=='flag':
        # Called from a Hermes hook: say nothing, ever. A hook that prints is a
        # hook that ends up in somebody's chat.
        try:flag(c,platform=a.platform)
        except (OSError,ValueError):pass
        print(json.dumps({}))
    elif a.mode=='clear':print(json.dumps(clear(c),ensure_ascii=False))
    else:print(json.dumps(read(c),ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__':
    try:sys.exit(main() or 0)
    except (ValueError,OSError) as e:
        print(json.dumps({'error':str(e)}),file=sys.stderr);sys.exit(1)
