"""C2 crash harness: the PRODUCTION dispatcher in its own process (tests only; never shipped).

    python dispatch_proc.py <config.json>

Runs companion_dispatch.run() unmodified except for two test doubles installed here, never
through an environment variable read by shipped code (U6):
  * `_invoke` (the one call that can reach a platform) is replaced by a delivery double that
    appends one line to config['deliveries'] per call and returns config['reply'];
  * `_hook(name)` SIGKILLs this process when name == config['kill_at'] (process death: the
    OS releases the run lock and every file lock, exactly as after a real crash).
Prints the run result as one JSON line when it is not killed.
"""
import datetime as dt
import json
import os
import pathlib
import signal
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'kit' / 'scripts')]

import companion_config as cc          # noqa: E402
import companion_dispatch as dispatch  # noqa: E402


def companion(cfg):
    kw = dict(cfg['companion'])
    for key in ('hermes_root', 'vault'):
        kw[key] = pathlib.Path(kw[key])
    return cc.Companion(**kw)


def main(path):
    cfg = json.loads(pathlib.Path(path).read_text())
    reply = cfg.get('reply', {'returncode': 0, 'stdout': json.dumps({'success': True, 'message_id': 'm-1'})})

    def invoke(c, body, target):
        with open(cfg['deliveries'], 'a', encoding='utf-8') as f:
            f.write(json.dumps({'target': target, 'pid': os.getpid()}) + '\n')
        if cfg.get('hold_file'):                      # keep the "network call" open until released
            while not pathlib.Path(cfg['hold_file']).exists():
                __import__('time').sleep(0.01)
        return subprocess.CompletedProcess([], reply['returncode'], reply.get('stdout', ''), reply.get('stderr', ''))

    def hook(name):
        if name == cfg.get('kill_at'):
            os.kill(os.getpid(), signal.SIGKILL)

    dispatch._invoke = invoke
    dispatch._hook = hook
    now = dt.datetime.fromisoformat(cfg['now'])
    print(json.dumps(dispatch.run(companion(cfg), now), default=str))


if __name__ == '__main__':
    main(sys.argv[1])
