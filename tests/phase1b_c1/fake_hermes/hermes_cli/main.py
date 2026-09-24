"""TEST DOUBLE of `hermes chat --quiet --oneshot -q <message> [--resume S]`. Never shipped.

The scenario comes from $HERMES_HOME/fake_scenario.json (a synthetic test home):
  reply        text streamed and stored (default a fixed sentence)
  finish       finish_reason of the reply row (default 'stop')
  exit         exit code after the turn (default 0)
  hang         sleep this long before replying (an interrupt ends it: exit 130)
  kill_at      SIGKILL this process at: before_owner_row | inside_owner_write |
               after_owner_row | after_reply_row
  owner        'normal' | 'hidden' | 'summary' | 'twice' | 'none'
  clone        True: after the reply, a tail clone into a fresh session (unidentified rows)
  fail_receipt_for  write number whose write_committed receipt fails (receipt gap)
  child        'group' | 'escape': start a sleeping descendant before replying
  child_pid_file    where to write the descendant's pid
  ignore_interrupt  True: the hang swallows KeyboardInterrupt (only a kill ends it)
"""
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

import cli
import hermes_state


class Agent:
    stream_delta_callback = None


def _die():
    os.kill(os.getpid(), signal.SIGKILL)


def main():
    home = Path(os.environ['HERMES_HOME'])
    scenario = json.loads((home / 'fake_scenario.json').read_text()) if (home / 'fake_scenario.json').exists() else {}
    args = sys.argv[1:]
    message = args[args.index('-q') + 1]
    resume = args[args.index('--resume') + 1] if '--resume' in args else None
    if scenario.get('fail_receipt_for'):
        main_mod = sys.modules['__main__']
        original, target = main_mod.Facts._insert, int(scenario['fail_receipt_for'])
        def failing(self, kind, data):
            if kind == 'write_committed' and data.get('wid') == target:
                raise __import__('sqlite3').OperationalError('injected receipt failure')
            return original(self, kind, data)
        main_mod.Facts._insert = failing
    db = hermes_state.SessionDB(home / 'state.db')
    agent = Agent()
    cli._configure_quiet_agent(agent)
    try:
        session = resume or time.strftime('%Y%m%d_%H%M%S_') + uuid.uuid4().hex[:6]
        db.create_session(session)
        if scenario.get('kill_at') == 'before_owner_row':
            _die()
        owner = scenario.get('owner', 'normal')
        if scenario.get('kill_at') == 'inside_owner_write':
            def write(conn):
                conn.execute('INSERT INTO messages (session_id, role, content, timestamp) VALUES (?,?,?,?)',
                             (session, 'user', message, time.time()))
                _die()
            def append_message():          # the executor names the write after its caller
                return db._execute_write(write)
            append_message()
        if owner in ('normal', 'twice'):
            db.append_message(session, 'user', message)
        if owner == 'twice':
            db.append_message(session, 'user', message)
        if owner == 'hidden':
            db.append_message(session, 'user', message, display_kind='notice')
        if owner == 'summary':
            db.append_message(session, 'user', message, summary=1)
        if scenario.get('kill_at') == 'after_owner_row':
            _die()
        if scenario.get('child'):
            code = 'import os,time\n' + ('os.setsid()\n' if scenario['child'] == 'escape' else '') + 'time.sleep(60)'
            child = subprocess.Popen([sys.executable, '-c', code], close_fds=True)
            if scenario.get('child_pid_file'):
                Path(scenario['child_pid_file']).write_text(str(child.pid))
        if scenario.get('hang'):
            end = time.monotonic() + float(scenario['hang'])
            while time.monotonic() < end:
                try:
                    time.sleep(0.05)
                except KeyboardInterrupt:
                    if not scenario.get('ignore_interrupt'):
                        raise
        reply = scenario.get('reply', 'A synthetic reply.')
        for i in range(0, len(reply), 5):
            if agent.stream_delta_callback:
                agent.stream_delta_callback(reply[i:i + 5])
        db.append_message(session, 'assistant', reply, finish_reason=scenario.get('finish', 'stop'))
        if scenario.get('clone'):
            db.clone_tail(session, session + '_c')
        if scenario.get('kill_at') == 'after_reply_row':
            _die()
    except KeyboardInterrupt:
        sys.exit(130)
    sys.exit(int(scenario.get('exit', 0)))
