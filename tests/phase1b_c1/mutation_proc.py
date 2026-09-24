"""A second app process for the cross-process installation-guard tests (tests only).

    python mutation_proc.py hold   <root> <out> <release-file>
        take the production installation hold (chat_sends.hold_installation); write
        {"held": true} or {"refused": code} to <out>; keep the hold until <release-file> exists.
    python mutation_proc.py send   <home> <state> <out> [message]
        a separate controller: bootstrap, accept a new key (installation root = the parent of
        profiles/), write {"status", "send_id"} or {"refused": code}, then run the turn to
        settlement with the fake executor and write the final state.

No in-process lock is shared with the test: these are real OS processes (M-2d).
"""
import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[1]), str(HERE.parents[1] / 'kit' / 'scripts')]

from tests.phase1b_c1 import harness as h     # noqa: E402
from kit.app import chat_sends as cs           # noqa: E402


def write(path, payload):
    tmp = pathlib.Path(str(path) + '.tmp')
    tmp.write_text(json.dumps(payload))
    tmp.replace(path)


def main():
    mode = sys.argv[1]
    if mode == 'hold':
        root, out, release = sys.argv[2:5]
        try:
            hold = cs.hold_installation(root)
        except cs.Refused as exc:
            write(out, {'refused': exc.code})
            return 0
        write(out, {'held': True})
        end = time.monotonic() + 120
        while not pathlib.Path(release).exists() and time.monotonic() < end:
            time.sleep(0.02)
        hold.release()
        return 0
    if mode == 'send':
        home, state, out = sys.argv[2:5]
        message = sys.argv[5] if len(sys.argv) > 5 else 'A synthetic owner message from another process'
        home = pathlib.Path(home)
        root = home.parent.parent if home.parent.name == 'profiles' else home
        svc = cs.SendService(home, state, h.fake_executor(home), installation_root=root,
                             turn_timeout=60, stop_grace=1.0, watchdog_interval=0.1)
        scope = h.scope_for(home, installation='existing')
        try:
            generation = svc.bootstrap(scope)['generation']
            body = {'client_key': cs.new_ulid(), 'generation': generation,
                    'conversation_id': scope.conversation_id, 'message': message, 'session': None}
            status, payload = svc.accept(scope, body, h.workspace_only)
        except cs.Refused as exc:
            write(out, {'refused': exc.code})
            return 0
        send_id = payload['send']['send_id']
        write(out, {'status': status, 'send_id': send_id})
        row = svc.launch(send_id, message)
        write(out, {'status': status, 'send_id': send_id, 'final': row['state']})
        svc.close()
        return 0
    return 2


if __name__ == '__main__':
    sys.exit(main())
