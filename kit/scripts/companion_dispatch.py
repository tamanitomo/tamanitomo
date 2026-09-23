#!/usr/bin/env python3
"""The only thing that sends. No model, no judgement, no retries.

Runs as a no-agent cron job every few minutes. It takes at most one message off
the outbox per run and asks the questions a prompt cannot be trusted with:

  Is it past its expiry?          Drop it. Never send a stale message late.
  Is it too early?                Leave it queued.
  Is she asleep?                  Leave it — unless the human has written in the
                                  last few minutes, in which case they are
                                  visibly awake and the window is a description
                                  of a night, not a gate.
  Is this kind of content allowed? A photo nobody asked for is not the same as a
                                  sentence.
  Is there a slot left today?     The counter is on disk, not in a prompt.

One message per run, deliberately. A dispatcher that drains a queue is how five
messages arrive at once, which is alarming in a way that five messages spread
over an hour is not.

A send that fails or cannot be confirmed keeps its slot and is never retried:
"probably delivered" retried is a double message, and a double message is worse
than a missing one.
"""
from __future__ import annotations
import argparse, datetime as dt, json, os, pathlib, subprocess, sys
from zoneinfo import ZoneInfo
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
import companion_outbox as outbox
import companion_outreach as outreach
from companion_platform import hermes_command

def _tz(c):
    try:return ZoneInfo(c.timezone)
    except Exception:return ZoneInfo('UTC')

def recently_active(c,now,minutes=None):
    """Did the human write in the last few minutes?

    Read from the relationship-thread sensor when one is installed. Absent, the
    honest answer is "we do not know", which means the sleep window stands.
    """
    minutes=c.sleep_grace_minutes if minutes is None else minutes
    if not minutes:return False
    path=c.soul_dir/'ambient/relationship-thread.json'
    try:data=json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):return False
    last=data.get('last_from_human')
    if not last:return False
    try:when=dt.datetime.fromisoformat(str(last))
    except ValueError:return False
    if when.tzinfo is None:when=when.replace(tzinfo=_tz(c))
    return (now-when).total_seconds()<=minutes*60

def verdict(c,entry,now):
    """Whether this message goes now, and if not, what becomes of it."""
    if outbox.expired(entry,now):
        return {'action':'expire','reason':'past its expiry; a stale message is never sent late'}
    if outbox.held_until(entry,now):
        return {'action':'hold','reason':f"not before {entry['not_before'][11:16]}"}
    permission=c.may_send(entry.get('content','text'))
    if permission=='no':
        return {'action':'withhold',
                'reason':f"unprompted {entry.get('content')} is switched off for this companion"}
    if permission=='ask' and entry.get('content')!='text':
        return {'action':'withhold',
                'reason':f"{entry.get('content')} is set to ask: offer it in words, do not attach it unasked"}
    asleep=outreach.in_quiet_hours(c,now)
    awake=asleep and recently_active(c,now)
    if asleep and entry.get('priority')!='high' and not awake:
        return {'action':'hold','reason':f'quiet hours until {c.quiet_end}'}
    # The quiet-hours bypass is exactly that. The daily cap still applies, because
    # a cap the user set is not a bedtime and being awake does not raise it.
    urgent=entry.get('priority')=='high' or awake
    decision=outreach.decide(c,now,urgent=urgent)
    if not decision['allowed']:
        # A cap reached today is a hold, not a drop: it may still be in time
        # tomorrow, and the expiry decides that rather than this code.
        return {'action':'hold','reason':decision['reason'],'urgent':urgent}
    return {'action':'send','reason':decision['reason'],'urgent':urgent}

def review_hold(c,entry):
    """Why an image may not go, or '' when it may. Never claims a slot."""
    if not pathlib.Path(entry['media_path']).exists():return ''  # deliver() reports this
    from companion_media_review import ensure_delivery
    try:ensure_delivery(c,entry['media_path'],entry.get('body',''))
    except Exception as exc:return 'image held by pre-delivery review: '+str(exc)[:200]
    return ''

def deliver(c,entry):
    """Hand it to Hermes exactly once."""
    body=entry['body']
    if entry.get('media_path'):
        if not pathlib.Path(entry['media_path']).exists():
            return False,'the file to send is gone'
        if entry.get('content')=='image':
            from companion_media_review import ensure_delivery
            try:ensure_delivery(c,entry['media_path'],body)
            except Exception:return False,'image held: pre-delivery review did not pass; inspect it in Photos'
        body=f"MEDIA:{entry['media_path']}\n{body}"
    return hermes_send(c,body,entry.get('target') or 'telegram')

def hermes_send(c,body,target='telegram'):
    """One native Hermes send with this profile's own credentials. (ok, detail)."""
    env={**os.environ,'HERMES_HOME':str(c.home),'PYTHONUTF8':'1'}
    if c.profile:
        prefixes=('TELEGRAM_','DISCORD_','SLACK_','SIGNAL_','WHATSAPP_','MATRIX_',
                  'WEIXIN_','FEISHU_','DINGTALK_','NTFY_','SIMPLEX_','QQBOT_','YUANBAO_')
        env={k:v for k,v in env.items() if not k.startswith(prefixes)}
    try:
        proc=subprocess.run(hermes_command('send','--to',target,'--json'),
            input=body,capture_output=True,text=True,encoding='utf-8',timeout=120,env=env)
        try:payload=json.loads(proc.stdout)
        except ValueError:payload={}
        ok=(proc.returncode==0 and isinstance(payload,dict) and payload.get('success') is True
            and not payload.get('error') and not payload.get('skipped'))
        return ok,('sent' if ok else 'delivery failed or unconfirmed; the slot is kept and it is not retried')
    except (OSError,subprocess.SubprocessError) as exc:
        return False,f'delivery failed: {exc}; the slot is kept and it is not retried'

def run(c,now=None,send=True):
    now=(now or dt.datetime.now(_tz(c))).astimezone(_tz(c))
    handled=[]
    for entry in outbox.waiting(c,now):
        call=verdict(c,entry,now)
        if call['action']=='hold':
            handled.append({'id':entry['id'],**call});continue
        if call['action'] in ('expire','withhold'):
            outbox.mark(c,entry['id'],'expired' if call['action']=='expire' else 'withheld',
                        call['reason'],now)
            handled.append({'id':entry['id'],**call});continue
        # A dry run decides and stops: claiming first used up a real daily slot for a
        # message it never sent.
        if not send:
            handled.append({'id':entry['id'],'action':'would-send','reason':call['reason']});break
        # A picture is reviewed BEFORE a slot is claimed. A review that holds it is a
        # verdict about the picture, not a delivery that failed, so it withholds the
        # message and leaves today's allowance alone.
        if entry.get('content')=='image' and entry.get('media_path'):
            held=review_hold(c,entry)
            if held:
                outbox.mark(c,entry['id'],'withheld',held,now)
                handled.append({'id':entry['id'],'action':'withhold','reason':held});continue
        # One send per run, and the slot is claimed before delivery so a crash
        # mid-send cannot hand back a free slot.
        claim=outreach.claim(c,entry.get('reason') or 'outbox',now=now,urgent=call.get('urgent',False))
        if not claim['allowed']:
            handled.append({'id':entry['id'],'action':'hold','reason':claim['reason']});break
        ok,detail=deliver(c,entry)
        outbox.mark(c,entry['id'],'sent' if ok else 'failed',detail,now)
        handled.append({'id':entry['id'],'action':'sent' if ok else 'failed','reason':detail})
        break
    return {'at':now.isoformat(timespec='minutes'),'handled':handled,
            'still_waiting':len(outbox.waiting(c,now))}

def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--home',type=pathlib.Path)
    p.add_argument('--dry-run',action='store_true',help='decide, expire and withhold, but send nothing')
    p.add_argument('--json',action='store_true',help='print the whole decision, not just problems')
    a=p.parse_args();c=cc.load(a.home)
    result=run(c,send=not a.dry_run)
    if a.json:print(json.dumps(result,ensure_ascii=False,indent=2))
    else:
        # As a no-agent job, stdout is delivered. Stay silent unless something
        # went wrong: a dispatcher narrating every quiet tick is the noise this
        # whole design exists to stop.
        bad=[h for h in result['handled'] if h['action'] in ('failed','expire')]
        for item in bad:print(f"{item['action']}: {item['reason']}")
    return 0

if __name__=='__main__':
    try:sys.exit(main() or 0)
    except (ValueError,OSError) as e:
        print(f'{e}',file=sys.stderr);sys.exit(1)
