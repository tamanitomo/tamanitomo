"""The bridge preserves quiet CLI lifecycle while forwarding real callback events."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class StreamBridgeTests(unittest.TestCase):
    def test_callbacks_and_final_response_are_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'cli.py').write_text('''
from types import SimpleNamespace
def _configure_quiet_agent(agent):agent.configured=True
def _run_quiet_single_query(instance,query):
    assert instance.agent.configured
    instance.agent.stream_delta_callback('Hello ')
    instance.agent.stream_delta_callback(None)
    instance.agent.stream_delta_callback('there')
    print('Hello there')
    raise SystemExit(0)
''')
            (root/'hermes_cli').mkdir()
            (root/'hermes_cli/__init__.py').write_text('')
            (root/'hermes_cli/main.py').write_text('''
import cli
from types import SimpleNamespace
def main():
    agent=SimpleNamespace()
    cli._configure_quiet_agent(agent)
    cli._run_quiet_single_query(SimpleNamespace(agent=agent,session_id='own-session'),'hello')
''')
            result=subprocess.run([sys.executable,str(ROOT/'kit/app/hermes_stream.py'),'chat'],
                env={**os.environ,'PYTHONPATH':str(root)},capture_output=True,text=True,check=True)
            events=[json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual([r['text'] for r in events if r['event']=='delta'],['Hello ','there'])
            self.assertEqual(events[-2],{'event':'session','id':'own-session'})
            self.assertEqual(events[-1],{'event':'final','text':'Hello there\n'})

if __name__=='__main__':unittest.main()
