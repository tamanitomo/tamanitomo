"""The kit's Hermes bridges keep their request when Hermes re-runs them.

Hermes's bootstrap re-executes a script under its own managed interpreter, in
isolated mode, when it is imported from another one. Every bridge read stdin
before that, so the re-run found it empty: the model test, the studio's Hermes
images and the app's voice all failed with a JSON error. The fake bootstrap here
re-runs a script the same way, so an ordering slip shows up as a lost request."""

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import textwrap
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "kit/scripts"

FAKE = {
    "hermes_bootstrap.py": """
        import os, sys
        if not os.environ.get("FAKE_HERMES_RERUN"):
            os.environ["FAKE_HERMES_RERUN"] = "1"
            code = (
                "import sys, runpy; sys.path.insert(0, %r); sys.argv = %r; "
                "runpy.run_path(%r, run_name='__main__')"
                % (os.path.dirname(os.path.abspath(__file__)), sys.argv, sys.argv[0])
            )
            os.execv(sys.executable, [sys.executable, "-I", "-c", code])
    """,
    # Hermes's own provider and tool code reaches its bootstrap like this.
    "agent/__init__.py": "import hermes_bootstrap\n",
    "agent/auxiliary_client.py": """
        class _Message:
            def __init__(self, text):
                self.content = text

        class _Choice:
            def __init__(self, text):
                self.message = _Message(text)
                self.finish_reason = "stop"

        class _Reply:
            def __init__(self, text):
                self.choices = [_Choice(text)]
                self.usage = None

        class _Completions:
            def create(self, **request):
                return _Reply("heard: " + request["messages"][-1]["content"])

        class _Chat:
            completions = _Completions()

        class _Client:
            chat = _Chat()

        def resolve_provider_client(provider, model, **options):
            return _Client(), model
    """,
    # Hermes's own provider and tool code reaches its bootstrap like this.
    "tools/__init__.py": "import hermes_bootstrap\n",
    "tools/image_generation_tool.py": """
        import json

        def _read_image_gen_key(key):
            return None

        def _handle_image_generate(args):
            return json.dumps({"success": True, "prompt": args["prompt"]})
    """,
    "tools/tts_tool.py": """
        import json

        def text_to_speech_tool(text, path):
            return json.dumps({"success": True, "text": text, "file_path": path})
    """,
}


class BridgeRerunTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.hermes = pathlib.Path(tmp.name)
        for name, body in FAKE.items():
            path = self.hermes / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(textwrap.dedent(body), encoding="utf-8")

    def bridge(self, script, payload, *args):
        env = {k: v for k, v in os.environ.items() if k != "FAKE_HERMES_RERUN"}
        env["PYTHONPATH"] = str(self.hermes)
        run = subprocess.run(
            [sys.executable, str(SCRIPTS / script), *args],
            input=json.dumps(payload),
            env=env,
            cwd=self.hermes,
            capture_output=True,
            text=True,
            timeout=60,
        )
        line = next(
            line for line in run.stdout.splitlines() if line.startswith("COMPANION_")
        )
        return run.returncode, json.loads(line.split("=", 1)[1])

    def test_the_text_bridge_keeps_its_request(self):
        code, out = self.bridge(
            "companion_text_provider.py",
            {
                "provider": "fake",
                "model": "fake-1",
                "messages": [{"role": "user", "content": "are you there?"}],
            },
        )
        self.assertEqual(code, 0, out)
        self.assertEqual(out["content"], "heard: are you there?")

    def test_the_image_bridge_keeps_its_request(self):
        code, out = self.bridge(
            "companion_image_provider.py",
            {"prompt": "a lighthouse at dusk"},
            "generate",
        )
        self.assertEqual(code, 0, out)
        self.assertEqual(out["prompt"], "a lighthouse at dusk")

    def test_the_voice_bridge_keeps_its_request(self):
        code, out = self.bridge(
            "companion_voice_chat.py",
            {"text": "good morning", "path": str(self.hermes / "note.ogg")},
            "speak",
        )
        self.assertEqual(code, 0, out)
        self.assertEqual(out["text"], "good morning")


if __name__ == "__main__":
    unittest.main()
