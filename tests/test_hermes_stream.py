"""The streaming bridge wraps functions belonging to Hermes, not to us.

Hermes 0.21.3 grew an `emitter` argument on its quiet runner and passed it on
every call. The wrapper here named exactly two parameters, so every chat turn
from the web app raised TypeError while cron -- which does not come through
this bridge -- carried on working, which is a very confusing way to be broken.
Reported as issue #1 by erohtar, with the cause and the fix.

So the bridge is exercised against both signatures: the one that exists today
and the one that broke it.
"""
import io
import json
import pathlib
import sys
import types
import unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'kit/app'))


class Agent:
    def __init__(self):
        self.session_id = 'sess-1'
        self.stream_delta_callback = None


class StreamBridgeTests(unittest.TestCase):
    def run_bridge(self, quiet, configure=None):
        """Drive hermes_stream.main() against a stand-in Hermes."""
        import hermes_stream
        calls = {}
        cli = types.ModuleType('cli')
        cli._run_quiet_single_query = quiet
        if configure is not None:
            cli._configure_quiet_agent = configure
        hermes_cli = types.ModuleType('hermes_cli')
        main_mod = types.ModuleType('hermes_cli.main')

        def hermes_main():
            # What Hermes does with the seams once they are in place.
            agent = Agent()
            if hasattr(cli, '_configure_quiet_agent'):
                cli._configure_quiet_agent(agent)
            if agent.stream_delta_callback:
                agent.stream_delta_callback('hello ')
            calls['result'] = cli._run_quiet_single_query(agent, 'a question', emitter=None)

        main_mod.main = hermes_main
        hermes_cli.main = main_mod
        saved = {k: sys.modules.get(k) for k in ('cli', 'hermes_cli', 'hermes_cli.main')}
        sys.modules.update({'cli': cli, 'hermes_cli': hermes_cli, 'hermes_cli.main': main_mod})
        captured = io.StringIO()
        real_stdout = sys.stdout
        sys.stdout = captured
        try:
            hermes_stream.main()
        finally:
            sys.stdout = real_stdout
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
        events = [json.loads(line) for line in captured.getvalue().splitlines() if line.strip()]
        return events, calls

    def test_the_signature_that_broke_it(self):
        """Hermes 0.21.3: the runner takes an emitter and is always given one."""
        seen = {}

        def quiet(cli_obj, query, emitter=None):
            seen['query'] = query
            seen['emitter_passed'] = 'emitter' in seen or True
            return 'answered'

        events, calls = self.run_bridge(quiet)
        self.assertEqual(seen['query'], 'a question')
        self.assertEqual(calls['result'], 'answered')
        self.assertIn('session', [e['event'] for e in events])

    def test_the_session_event_still_reports_the_id(self):
        events, _ = self.run_bridge(lambda c, q, emitter=None: None)
        session = next(e for e in events if e['event'] == 'session')
        self.assertEqual(session['id'], 'sess-1')

    def test_deltas_still_stream(self):
        def configure(agent, *args, **kwargs):
            agent.configured = True

        events, _ = self.run_bridge(lambda c, q, emitter=None: None, configure=configure)
        deltas = [e for e in events if e['event'] == 'delta']
        self.assertEqual([d['text'] for d in deltas], ['hello '])

    def test_the_session_event_survives_a_failing_turn(self):
        """A turn that raises must still say which session it was."""
        def quiet(cli_obj, query, emitter=None):
            raise RuntimeError('model refused')

        with self.assertRaises(RuntimeError):
            self.run_bridge(quiet)


if __name__ == '__main__':
    unittest.main()
