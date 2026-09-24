#!/usr/bin/env python3
"""Deterministic gate on unprompted messages. No model is consulted.

SOUL.md asks the agent not to message during quiet hours and not to overdo it.
That is a prompt, and a prompt is a request: one enthusiastic model, one bad
retry loop, and the human gets twenty messages at 3am. This decides the same
question in code, from the clock and a counter on disk, so the limit holds even
for callers using this helper; it is not a restriction on arbitrary network tools.

    companion_outreach.py send --message-file f   QUEUE a message on the outbox (never delivers)
    companion_outreach.py claim              reserve a send atomically, exit 1 if denied
    companion_outreach.py record --reason x  count a message that was sent
    companion_outreach.py status             today's tally as JSON

`send` on the command line queues. It used to deliver directly, which gave a
model two ways out of the house -- the outbox and this -- and a thought sent both
ways arrived twice, with no expiry, no pacing and no record in the queue she
reads back. The dispatcher is the only thing that delivers; `send()` below is the
transport it shares, kept for callers that have already been through the gate.
"""
from __future__ import annotations
import argparse, datetime as dt, json, pathlib, sys, os, subprocess
from zoneinfo import ZoneInfo
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
from companion_platform import file_lock, hermes_command, is_terminal


LEDGER='outreach.jsonl'
UNLIMITED=0

def _tz(c):
    try:return ZoneInfo(c.timezone)
    except Exception:return ZoneInfo('UTC')

def _minutes(hhmm,fallback):
    try:
        t=dt.time.fromisoformat(hhmm if len(hhmm)==5 else hhmm+':00')
        return t.hour*60+t.minute
    except (ValueError,TypeError):return fallback

def in_quiet_hours(c,now):
    """Quiet hours wrap midnight, so 23:00-08:00 is one window, not two."""
    start=_minutes(c.quiet_start,23*60);end=_minutes(c.quiet_end,8*60)
    minute=now.hour*60+now.minute
    if start==end:return False
    return minute>=start or minute<end if start>end else start<=minute<end

def path(c):return pathlib.Path(c.data)/LEDGER

def sent_today(c,now):
    day=now.date().isoformat();n=0
    try:
        with path(c).open(encoding='utf-8') as f:
            for line in f:
                line=line.strip()
                if not line:continue
                try:row=json.loads(line)
                except ValueError as exc:raise ValueError('Corrupt outreach ledger; reconcile before sending') from exc
                if not isinstance(row,dict) or row.get('kind')!='outreach':raise ValueError('Invalid outreach ledger entry')
                dt.date.fromisoformat(str(row.get('day','')))
                if row['day']==day:n+=1
    except FileNotFoundError:pass
    return n

def decide(c,now=None,urgent=False):
    """Whether an unprompted message may go out right now, and why not."""
    now=(now or dt.datetime.now(_tz(c))).astimezone(_tz(c))
    limit=max(0,int(getattr(c,'outreach_per_day',3) or 0))
    try:used=sent_today(c,now)
    except (OSError,ValueError) as exc:return {'allowed':False,'reason':'Outreach ledger is unreadable or corrupt; repair it before sending','storage_error':True}
    out={'now':now.isoformat(timespec='minutes'),'policy':c.outreach,'urgent':bool(urgent),
         'sent_today':used,'limit':limit or None,
         'quiet_hours':f'{c.quiet_start}-{c.quiet_end} {c.timezone}',
         'in_quiet_hours':in_quiet_hours(c,now)}
    if c.outreach=='never':
        return {**out,'allowed':False,'reason':'This companion does not message first. Reply only.'}
    if out['in_quiet_hours'] and not urgent:
        return {**out,'allowed':False,
                'reason':f'Quiet hours ({out["quiet_hours"]}). Hold it until after {c.quiet_end}.'}
    if limit and used>=limit:
        return {**out,'allowed':False,
                'reason':f'Daily limit reached ({used} of {limit} today). Wait for tomorrow, '
                         f'or for {c.human} to write first.'}
    return {**out,'allowed':True,
            'reason':'Outside quiet hours and within the daily limit.' if limit else 'No daily limit set.'}

def _append(c,reason,now,attempt=None):
    p=path(c);p.parent.mkdir(parents=True,exist_ok=True)
    row={'kind':'outreach','day':now.date().isoformat(),'at':now.isoformat(timespec='seconds'),
         'reason':str(reason)[:200]}
    # The dispatcher's attempt identity (PHASE1B_DESIGN 7.2 step 3b): a crashed run's
    # charge is then found by lookup, never inferred from the outbox marker alone.
    if attempt:row['attempt']=str(attempt)[:80]
    with p.open('a',encoding='utf-8') as f:
        f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())

def record(c,reason='',now=None):
    """Legacy accounting for a message already sent; new sends must use claim."""
    now=(now or dt.datetime.now(_tz(c))).astimezone(_tz(c))
    with file_lock(path(c).with_suffix('.jsonl.lock')):
        sent_today(c,now)  # Do not append over a corrupt ledger.
        _append(c,reason,now)
        return sent_today(c,now)

def claim(c,reason='',now=None,urgent=False,attempt=None):
    """Atomically reserve one send before delivery; failed sends still consume the slot.
    `attempt` (the dispatcher's attempt id) is stored on the charge row for charges_for().
    A refusal appends nothing."""
    now=(now or dt.datetime.now(_tz(c))).astimezone(_tz(c))
    with file_lock(path(c).with_suffix('.jsonl.lock')):
        result=decide(c,now,urgent)
        if result['allowed']:
            _append(c,reason,now,attempt)
            result['sent_today']+=1
            result['reserved']=True
        return result

def charges_for(c,attempt):
    """How many charge rows carry this attempt id, read under the outreach lock.

    Raises ValueError when the ledger cannot be read in full (a torn or invalid line):
    an unreadable ledger is never evidence that no charge happened (PHASE1B_DESIGN 7.3).
    A missing ledger is a readable empty one."""
    if not attempt:raise ValueError('an attempt id is required')
    found=0
    with file_lock(path(c).with_suffix('.jsonl.lock')):
        try:
            with path(c).open(encoding='utf-8') as f:
                for line in f:
                    line=line.strip()
                    if not line:continue
                    try:row=json.loads(line)
                    except ValueError as exc:raise ValueError('Corrupt outreach ledger; the charge cannot be established') from exc
                    if not isinstance(row,dict) or row.get('kind')!='outreach':
                        raise ValueError('Invalid outreach ledger entry; the charge cannot be established')
                    if row.get('attempt')==attempt:found+=1
        except FileNotFoundError:return 0
        except UnicodeError as exc:raise ValueError('Unreadable outreach ledger') from exc
    return found

def send(c,message,reason='',target='telegram',now=None):
    """Reserve and deliver through the profile's native Hermes CLI; never auto-retry."""
    if not message or not message.strip():
        return {'allowed':False,'delivered':False,'reason':'Empty message'}
    result=claim(c,reason,now=now)
    if not result['allowed']:return {**result,'delivered':False}
    env={**os.environ,'HERMES_HOME':str(c.home),'PYTHONUTF8':'1'}
    if c.profile:
        # A multiplex worker may inherit the root bot's credentials. Native send loads
        # this profile's own .env; never silently borrow another companion's bot.
        prefixes=('TELEGRAM_','DISCORD_','SLACK_','SIGNAL_','WHATSAPP_','MATRIX_',
                  'WEIXIN_','FEISHU_','DINGTALK_','NTFY_','SIMPLEX_','QQBOT_','YUANBAO_')
        env={k:v for k,v in env.items() if not k.startswith(prefixes)}
    try:
        proc=subprocess.run(hermes_command('send','--to',target,'--json'),
            input=message,capture_output=True,text=True,encoding='utf-8',timeout=90,env=env)
        try:payload=json.loads(proc.stdout)
        except ValueError:payload={}
        delivered=isinstance(payload,dict) and proc.returncode==0 and payload.get('success') is True and not payload.get('error') and not payload.get('skipped')
        return {**result,'delivered':delivered,
            'delivery_status':'sent' if delivered else 'failed_or_unconfirmed; slot retained; do not retry'}
    except (OSError,subprocess.SubprocessError):
        return {**result,'delivered':False,'delivery_status':'failed_or_unconfirmed; slot retained; do not retry'}

def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('action',choices=('check','claim','send','record','status'))
    p.add_argument('--home',type=pathlib.Path)
    p.add_argument('--reason',default='')
    message_input=p.add_mutually_exclusive_group()
    message_input.add_argument('--message',help='Message text for send; otherwise read stdin')
    message_input.add_argument('--message-file',type=pathlib.Path,help='Read literal UTF-8 message text from a file')
    p.add_argument('--to',default='telegram',help='Hermes delivery target (default: telegram home channel)')
    p.add_argument('--ttl-hours',type=float,default=4,help='how long the message is still worth sending')
    p.add_argument('--urgent',action='store_true',
                   help='Something time-critical. Bypasses quiet hours, never the daily limit.')
    a=p.parse_args()
    c=cc.load(a.home)
    if a.action=='send':
        try:
            message=a.message if a.message is not None else (a.message_file.read_text(encoding='utf-8') if a.message_file else (sys.stdin.read() if not is_terminal(sys.stdin) else ''))
        except (OSError,UnicodeError):
            print(json.dumps({'allowed':False,'delivered':False,'reason':'Message input file could not be read'}));return 1
        if c.outreach=='never':
            print(json.dumps({'queued':False,'reason':'This companion does not message first. Reply only.'}));return 1
        import companion_outbox as outbox
        try:
            result=outbox.queue(c,{'kind':'text','body':message,'reason':a.reason or 'outreach',
                                   'priority':'high' if a.urgent else 'normal','ttl_hours':a.ttl_hours,
                                   'target':a.to})
        except ValueError as exc:
            print(json.dumps({'queued':False,'reason':str(exc)},ensure_ascii=False));return 1
        print(json.dumps({'queued':True,'id':result['entry']['id'],'already_waiting':not result.get('written',True),
                          'note':'Queued, not sent. The dispatcher decides when it goes, within quiet hours '
                                 'and the daily limit. Do not queue it again.'},ensure_ascii=False))
        return 0
    if a.action=='claim':
        result=claim(c,a.reason,urgent=a.urgent)
        print(json.dumps(result,ensure_ascii=False));return 0 if result['allowed'] else 1
    if a.action=='record':
        print(json.dumps({'recorded':True,'sent_today':record(c,a.reason)},ensure_ascii=False));return 0
    d=decide(c,urgent=a.urgent)
    print(json.dumps(d,ensure_ascii=False,indent=2))
    return 0 if (d['allowed'] or a.action=='status') else 1

if __name__=='__main__':sys.exit(main())
