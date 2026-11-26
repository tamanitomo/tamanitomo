"""Every local conversation gets a window Hermes will run: it refuses anything under 64K.

The kit used to set up local models at 8,192 tokens (4,096 on a phone), and the model
switcher's --ctx-size is shared by two slots, so most of its choices left a conversation
with 8K to 32K. Hermes stops at agent start below 64,000, so none of those could run.
"""

import os
import pathlib
import sys
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "kit/scripts"))

from kit.app import local_models as lm  # noqa: E402


def switch(tmp_path, mobile, ctx_size):
    model = tmp_path / "nova-7b.gguf"
    model.write_bytes(b"gguf")
    # The switcher writes a systemd drop-in under the home folder and restarts the
    # service: keep both away from the real machine.
    with (
        mock.patch.object(lm.Path, "home", return_value=tmp_path),
        mock.patch.object(lm, "get_host_memory", return_value={"is_mobile": mobile}),
        mock.patch.object(lm, "validate_model_safety", return_value=(True, "")),
        mock.patch.object(lm.shutil, "which", return_value=None),
        mock.patch.object(lm, "request", return_value={"data": [{}]}),
        mock.patch.object(lm.time, "sleep"),
        mock.patch.dict(os.environ, {"TAMANITOMO_LLAMA_SERVICE": "test-llama"}),
    ):
        lm.switch_model(None, str(model), "nova", ctx_size)
    unit = (
        tmp_path / ".config/systemd/user/test-llama.service.d/98-companion-model.conf"
    )
    return unit.read_text(encoding="utf-8")


def test_each_of_the_two_desktop_slots_gets_at_least_64k(tmp_path):
    assert "--ctx-size 131072 --parallel 2" in switch(tmp_path, False, 131072)
    assert "--ctx-size 131072 --parallel 2" in switch(tmp_path, False, 32768)
    assert "--ctx-size 262144 --parallel 2" in switch(tmp_path, False, 262144)


def test_a_phone_runs_one_conversation_at_64k(tmp_path):
    assert "--ctx-size 65536 --parallel 1" in switch(tmp_path, True, 4096)


def test_the_window_a_server_reports_is_read_from_llama_cpp_props():
    props = {"default_generation_settings": {"n_ctx": 8192}}
    with mock.patch.object(lm, "request", return_value=props):
        assert lm.served_window() == 8192
    with mock.patch.object(lm, "request", side_effect=OSError("refused")):
        assert lm.served_window() == 0


def test_ollama_starts_with_at_least_64k_and_keeps_a_larger_choice():
    for chosen, expected in (("", "65536"), ("8192", "65536"), ("junk", "65536")):
        with mock.patch.dict(os.environ, {"OLLAMA_CONTEXT_LENGTH": chosen}):
            assert lm.ollama_context() == expected
    with mock.patch.dict(os.environ, {"OLLAMA_CONTEXT_LENGTH": "131072"}):
        assert lm.ollama_context() == "131072"
