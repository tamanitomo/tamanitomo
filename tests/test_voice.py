"""Voice notes synthesize with the provider Hermes is configured with."""

import pathlib
import tempfile
import unittest
from unittest.mock import patch

import companion_config as cc
import companion_tts_adapter as adapter
import companion_voice as voice


class SynthesizeTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        self.c = cc.Companion(agent="Nova", human="Alex", hermes_root=root / "home", vault=root / "vault")
        self.c.home.mkdir(parents=True, exist_ok=True)
        self.out = root / "note.wav"

    def configure(self, tts):
        import yaml

        (self.c.home / "config.yaml").write_text(yaml.safe_dump({"tts": tts}))

    def fake_audio(self, *args):
        pathlib.Path(args[-1]).write_bytes(b"RIFF" + b"\0" * 60)

    def test_a_command_provider_is_run_by_hermes_not_the_adapter(self):
        self.configure({"provider": "pockettts", "providers": {"pockettts": {"type": "command", "command": "say '{input_path}' '{output_path}'"}}})
        opus = self.out.with_suffix(".ogg")

        def hermes_writes_opus(c, text, path):
            self.fake_audio(opus)
            return opus

        with patch.object(voice, "hermes_tts", side_effect=hermes_writes_opus) as hermes, patch.object(adapter, "synthesize") as local:
            # The note is the file Hermes actually wrote, not the path it was offered.
            self.assertEqual(voice.synthesize(self.c, "hello", self.out), opus)
        hermes.assert_called_once_with(self.c, "hello", self.out)
        local.assert_not_called()

    def test_an_engine_the_adapter_runs_still_goes_to_the_adapter(self):
        self.configure({"provider": "pockettts", "pockettts": {"voice": "alba"}})
        with patch.object(voice, "hermes_tts") as hermes, patch.object(adapter, "synthesize", side_effect=self.fake_audio) as local:
            voice.synthesize(self.c, "hello", self.out)
        local.assert_called_once_with(self.c.home, "pockettts", "hello", self.out)
        hermes.assert_not_called()

    def test_no_audio_from_hermes_is_an_error_not_a_silent_note(self):
        self.configure({"provider": "mine", "providers": {"mine": {"type": "command", "command": "x"}}})
        with patch.object(voice, "hermes_tts", return_value=self.out):
            with self.assertRaisesRegex(ValueError, "did not produce"):
                voice.synthesize(self.c, "hello", self.out)


if __name__ == "__main__":
    unittest.main()
