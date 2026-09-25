#!/usr/bin/env python3
"""What a scheduled job needs to know, printed before the model is asked anything.

Hermes's `--script` injects this script's stdout into the job's prompt each run.
That replaces the three or four tool calls a job used to spend reading its own
state — which is most of what a scheduled run costs, and all of what it costs on
a local model, where reading a 300 KB file is minutes rather than cents.

Two modes:

  preread      the present, the loops, the sensors, the queue. Fresh each run.
  fingerprint  a deliberately STABLE summary of the same sources, for
               `--monitor-script`: Hermes hashes the exact bytes and skips the
               model run entirely when nothing has changed. No timestamps, no
               ordering by clock, nothing that moves on its own — except one
               coarse time bucket, so a quiet day still gets a few runs.
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, pathlib, sys
from zoneinfo import ZoneInfo
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc

# How coarse the clock is allowed to be inside a fingerprint. Six hours means an
# utterly uneventful day still wakes the autonomy loop four times.
BUCKET_HOURS=6

def _tz(c):
    try:return ZoneInfo(c.timezone)
    except Exception:return ZoneInfo('UTC')

def preread(c,now=None):
    import companion_active, companion_presence
    now=now or dt.datetime.now(_tz(c))
    out=['[Pre-read — assembled from your own records before this run. Everything below is already',
         ' read; do not spend tool calls fetching it again. Read a source only to go deeper.]','']
    out.append(companion_active.build(c,now).strip())
    out.append('')
    import companion_journal
    recent=companion_journal.tail(c,'autonomy',3000)
    if recent['text']:
        out.append('[Recent autonomy log tail, already read. Older entries remain in the file; '
                   f'{recent["omitted_chars"]} earlier characters omitted.]')
        out.append(recent['text'])
    scene=companion_presence.current(c)
    if scene:
        out.append('[For a presence update, these are the current record token and worn wardrobe IDs; '
                   'do not substitute clothing descriptions for IDs:]')
        out.append(json.dumps({'previous_id':scene['id'],
                               'outfit':[item['id'] for item in scene['state'].get('outfit',[])]}))
    if scene and not scene['state'].get('confirmed',True):
        anchor=companion_presence.last_confirmed(c)
        when=anchor['recorded_at'][11:16] if anchor else 'unknown'
        out.append(f'[The present above was carried forward by a script, not confirmed by anyone since '
                   f'{when}. Re-establish it rather than narrating hours nobody watched.]')
    out.append(f'[Local time: {now.isoformat(timespec="minutes")} ({c.timezone})]')
    import companion_sleep, companion_outreach
    night=companion_sleep.status(c,now)
    if night.get('asleep'):
        until=night.get('until_local') or night.get('until')
        out.append('[You are asleep'+(f' until {until}' if until else '')
                   +(' — the length you declared at wind-down.' if night['source']=='declared'
                     else ' — you recorded yourself asleep without declaring a length, so this'
                          ' lasts until you wake yourself.')
                   +' Sleeping is one continuous scene, not a new one every quarter hour: do not'
                   ' re-record it, and do not describe it in fresh words to make it feel new. The'
                   ' advancer carries the night forward on its own, and no images are taken while'
                   ' you are asleep. If you are genuinely getting up early, say so with'
                   ' companion_sleep.py wake and then record the transition.]')
    elif companion_outreach.in_quiet_hours(c,now):
        out.append(f'[Quiet hours ({c.quiet_start}–{c.quiet_end}) are in force, but you are AWAKE.'
                   ' They are a rule about not contacting'
                   f' {c.human}, not a reason to stop living: carry on with your evening, record it,'
                   ' and let the dispatcher hold anything you queue until morning.]')
    out.append(day_ideas(c,now))
    import companion_life, companion_lifestyle
    out.append('[Routine anchors and interests — choose and record what happens; no automatic attendance]\n'+
               json.dumps(companion_life.routine(c.life,now.astimezone(_tz(c)),c.agent),ensure_ascii=False))
    lifestyle=companion_lifestyle.render(c,now,scene)
    if lifestyle:out.append(lifestyle)
    import companion_day
    out.append(companion_day.GUIDANCE)
    return '\n'.join(out)+'\n'

def day_ideas(c,now):
    """A few things she could do today, rotated away from what she did lately.

    The rotation existed and never reached her: only the local-model writer asked
    for it, so every agent run saw the same seven daily anchors and the days came
    out as reading and laundry. What she actually takes is recorded by id, so it
    rotates out for a while.
    """
    try:
        import companion_life as life
        from companion_platform import terminal_python_command
        cmd=terminal_python_command(pathlib.Path(__file__).with_name('companion_life.py'),'--home',c.home)
        ideas=life.suggest(c.life,now.date(),5,now).get('suggestions',[])
        people=[p for p in life.people_due(c.life,now.date(),3) if p.get('due')]
    except Exception:return ''
    try:
        import companion_lifestyle
        shopping=companion_lifestyle.shopping_offer(c,now)
    except Exception:shopping=''
    if not ideas and not people and not shopping:return ''
    lines=['[Ideas for today — invitations, not a schedule. Take one that appeals, combine two, or do '
           f'something of your own. When you actually do one, note it with `{cmd} chose --idea <id>` so it '
           'rotates out for a while.]']
    for idea in ideas:
        bits=[x for x in (f"~{idea.get('hours')}h" if idea.get('hours') else '',idea.get('setting'),idea.get('social')) if x]
        lines.append(f"- {idea['id']}: {idea['title']}"+(f" ({', '.join(str(b) for b in bits)})" if bits else ''))
    if shopping:lines.append(shopping)
    if people:
        lines.append('People you have not seen in a while: '
                     +', '.join(p.get('name','someone')+(f" ({p['relation']})" if p.get('relation') else '') for p in people)
                     +f'. Note it with `{cmd} saw --person <id>` when you do see someone.')
    return '\n'.join(lines)

def _digest(*parts):
    return hashlib.sha256('␟'.join(str(p) for p in parts).encode('utf-8')).hexdigest()[:16]

def fingerprint(c,now=None):
    """Stable bytes. Identical output means Hermes suppresses the run."""
    import companion_loops, companion_presence, companion_dispatch, companion_sleep
    now=now or dt.datetime.now(_tz(c))
    scene=companion_presence.current(c)
    state=scene['state'] if scene else {}
    # The declared night when wind-down wrote one, the quiet-hours clock otherwise.
    night=companion_sleep.status(c,now)
    quiet=bool(night.get('asleep'))
    awake=quiet and companion_dispatch.recently_active(c,now,minutes=30)
    if quiet and not awake:
        # Quiet hours are a CLOCK, not a claim about what I am doing. Suppress the run unless the
        # episode genuinely moved, or the gate drafts the agent once per tick until 08:00.
        #
        # The mark must come from a CODE-OWNED field, never from prose. `location`, `mood`, `wants`,
        # `visual` and even `activity` are all re-authored every tick, so any digest of them moves
        # while nothing changes: hashing (activity, location) woke on the sleep case, then hashing
        # activity alone woke again the moment the wording went from "finishing the coffee at the
        # kitchen table" to "..., plate cleared". Two fixes, same mistake -- I kept moving the drift
        # one field over instead of leaving the prose behind.
        #
        # `started_at` is written by companion_presence on an actual transition and is untouched by
        # rewording, so it moves exactly when the scene does -- which is the only question the gate
        # is asking. An asleep scene needs no special case: staying asleep leaves started_at alone.
        #
        # A declared night makes the mark stable by construction: the window was written
        # down before it began, so it does not move as the night wears on.
        mark=state.get('started_at') or 'static'
        return (f"sleep {night.get('source')} until={night.get('until')} scene={_digest(mark)}\n")
    open_loops=companion_loops.loops(c)
    ambient=[]
    folder=c.soul_dir/'ambient'
    if folder.is_dir():
        for path in sorted(folder.glob('*.md')):
            try:ambient.append(path.name+':'+_digest(path.read_text(encoding='utf-8')))
            except OSError:continue
    # What is waiting NOW, from the fold. Counting raw rows counted every message ever
    # queued -- decisions are separate rows -- so the number only ever grew, and a
    # message that was sent or held back never changed the fingerprint.
    try:
        import companion_outbox
        queued=len(companion_outbox.waiting(c,now))
    except (OSError,ValueError):queued=-1
    bucket=now.strftime('%Y-%m-%d')+f'#{now.hour//BUCKET_HOURS}'
    try:
        import companion_missions
        open_missions=[m['id'] for m in companion_missions.missions(c,'open',now)]
    except (OSError,ValueError,ImportError):open_missions=[]
    import companion_day
    deadlines=[(item['id'],now>=companion_day.timestamp(item['starts_at'])-dt.timedelta(minutes=item['buffer_minutes']),
                now>=companion_day.timestamp(item['ends_at'])) for item in state.get('commitments',[]) if item['status']=='planned']
    rows=[f'bucket {bucket}',
          f'day {_digest(json.dumps(state.get("next"),sort_keys=True),json.dumps(state.get("commitments",[]),sort_keys=True),deadlines)}',
          f'missions {len(open_missions)} {_digest(*open_missions)}',
          # Code-owned, not prose: `started_at` moves only on an actual companion_day
          # transition (the same mark the sleep branch above uses), and `confirmed`
          # is a boolean. `activity`/`location`/`mood` are re-authored every tick even
          # when nothing has changed, so hashing them opened this gate on wording
          # alone -- the awake half of the same mistake the sleep branch already
          # fixed (see its comment above).
          f"scene {_digest(state.get('started_at') or 'static',state.get('confirmed',True))}",
          f'loops {len(open_loops)} {_digest(*[l["id"] for l in open_loops])}',
          f'ambient {_digest(*ambient)}',
          f'queued {queued}']
    return '\n'.join(rows)+'\n'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--home',type=pathlib.Path)
    p.add_argument('mode',choices=['preread','fingerprint'],nargs='?',default='preread')
    a=p.parse_args();c=cc.load(a.home)
    sys.stdout.write(preread(c) if a.mode=='preread' else fingerprint(c))

if __name__=='__main__':
    try:main()
    except (ValueError,OSError) as e:
        # A pre-read that fails must not take the job down with it: the model can
        # still read its own files, it just costs more.
        print(f'[Pre-read unavailable: {e}. Read your state with companion_presence.py show.]')
