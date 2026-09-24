"""C1 crash harness: an app controller in its own process (tests only; never shipped).

    python controller_proc.py <config.json>

Runs bootstrap -> accept -> launch with the PRODUCTION SendService, through a
test-only subclass whose `_hook(name)` SIGKILLs this process at the named boundary
(U6: the crash is injected by the harness, not by an environment variable read by
shipped code). `kill_at` may also be 'first_delta' (killed while streaming).
Before launching it writes {send_id, key, generation} to config['out'].
"""
import json
import os
import pathlib
import signal
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit' / 'scripts')]

from kit.app import chat_sends as cs            # noqa: E402
from tests.phase1b_c1 import harness            # noqa: E402


def main(path):
    cfg = json.loads(pathlib.Path(path).read_text())

    class Crashing(cs.SendService):
        def _hook(self, name):
            if name == cfg.get('kill_at'):
                os.kill(os.getpid(), signal.SIGKILL)

    ex = cs.ExecutorSpec(**cfg['executor'])
    svc = Crashing(cfg['home'], cfg['state'], ex, turn_timeout=cfg.get('turn_timeout', 60),
                   stop_grace=cfg.get('stop_grace', 15), watchdog_interval=cfg.get('poll', 0.2))
    scope = harness.scope_for(cfg['home'])
    generation = svc.bootstrap(scope)['generation']
    body = {'client_key': cfg['key'], 'generation': generation, 'conversation_id': scope.conversation_id,
            'message': cfg['message'], 'session': cfg.get('session')}
    status, payload = svc.accept(scope, body, lambda s, x: ('workspace', None))
    pathlib.Path(cfg['out']).write_text(json.dumps({'send_id': payload['send']['send_id'], 'status': status,
                                                    'generation': generation, 'controller': svc.controller}))
    def delta(text):
        if cfg.get('kill_at') == 'first_delta':
            os.kill(os.getpid(), signal.SIGKILL)
    svc.launch(payload['send']['send_id'], cfg['message'], delta)


if __name__ == '__main__':
    main(sys.argv[1])
