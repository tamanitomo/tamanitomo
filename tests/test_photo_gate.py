"""A photo that cannot render, or that the job would only decline, never wakes the model.

Before the gate, every capture during one ComfyUI outage was a whole model run that
could only fail: 29 of them over three days on one install."""

import http.server
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import companion_config as cc
import companion_timeline as tl
from kit.cli import scaffold

ROOT = pathlib.Path(__file__).resolve().parents[1]


class ComfyStats(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200 if self.path == "/system_stats" else 404)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):
        pass


class PhotoGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        self.c = cc.Companion(
            agent="Nova",
            human="Robin",
            hermes_root=root / "home",
            vault=root / "vault",
            timezone="UTC",
        )
        self.c.home.mkdir(parents=True)
        self.c.life.mkdir(parents=True)
        self.c.image_timeline = False
        self.c.save()

    def serve(self):
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), ComfyStats)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        return server, f"http://127.0.0.1:{server.server_address[1]}"

    def preset(self, endpoint, provider="comfyui"):
        recipe = {
            "presets": [{"id": "p", "provider": provider, "endpoint": endpoint}],
            "routes": {"portrait": "p"},
            "default_preset": "p",
        }
        return patch("companion_media.effective", return_value=recipe)

    def test_a_comfyui_that_stops_answering_pauses_photos_until_it_answers(self):
        server, url = self.serve()
        with self.preset(url):
            self.assertIsNone(tl.provider_down(self.c))
            self.assertIsNone(tl.provider_status(self.c))
            server.shutdown()
            server.server_close()
            reason = tl.provider_down(self.c, timeout=1)
            self.assertEqual(
                reason,
                f"ComfyUI at 127.0.0.1:{server.server_address[1]} is not answering",
            )
            first = tl.provider_status(self.c)
            self.assertEqual(first["paused"], reason)
            tl.provider_down(self.c, timeout=1)
            self.assertEqual(tl.provider_status(self.c)["since"], first["since"])

    def test_an_error_page_still_counts_as_answering(self):
        _, url = self.serve()
        with self.preset(url + "/not-comfy"):
            self.assertIsNone(tl.provider_down(self.c))

    def test_a_hosted_provider_is_never_asked(self):
        with (
            self.preset("", provider="hermes"),
            patch("urllib.request.urlopen") as opened,
        ):
            self.assertIsNone(tl.provider_down(self.c))
        opened.assert_not_called()

    def test_a_run_that_could_only_decline_is_skipped_without_asking_comfyui(self):
        with patch.object(tl, "provider_down") as probe:
            verdict = tl.gate(self.c)
        self.assertEqual(
            verdict, {"wakeAgent": False, "reason": "Image timeline is off"}
        )
        probe.assert_not_called()
        ready = (None, {"state": {}}, {"soul": ""})
        with (
            patch.object(tl, "_refusal", return_value=ready),
            patch.object(
                tl,
                "_taken",
                return_value="The current visible moment already has an image",
            ),
            patch.object(tl, "provider_down") as probe,
        ):
            verdict = tl.gate(self.c)
        self.assertEqual(
            verdict["reason"], "The current visible moment already has an image"
        )
        probe.assert_not_called()

    def test_a_photo_whose_service_is_down_never_wakes_the_model(self):
        ready = (None, {"state": {}}, {"soul": ""})
        with (
            patch.object(tl, "_refusal", return_value=ready),
            patch.object(tl, "_taken", return_value=None),
            patch.object(
                tl, "provider_down", return_value="ComfyUI at h:1 is not answering"
            ),
        ):
            self.assertEqual(
                tl.gate(self.c),
                {
                    "wakeAgent": False,
                    "reason": "Photos paused: ComfyUI at h:1 is not answering",
                },
            )
        with (
            patch.object(tl, "_refusal", return_value=ready),
            patch.object(tl, "_taken", return_value=None),
            patch.object(tl, "provider_down", return_value=None),
        ):
            self.assertIsNone(tl.gate(self.c))

    def test_the_fingerprint_changes_when_photos_pause_and_again_when_they_resume(self):
        self.c.image_timeline = True
        self.c.image_style = "soft-film"
        scene = {"state": {"confirmed": True}}
        with (
            patch("companion_sleep.status", return_value={}),
            patch.object(tl, "current", return_value=scene),
            patch.object(tl, "private_reason", return_value=None),
            patch("companion_day.visual_key", return_value="kitchen"),
            patch.object(
                tl,
                "provider_down",
                side_effect=["ComfyUI at h:1 is not answering", None],
            ),
        ):
            paused, back = tl.fingerprint(self.c), tl.fingerprint(self.c)
        self.assertEqual(paused, "photos paused: ComfyUI at h:1 is not answering\n")
        self.assertTrue(back.startswith("style soft-film scene kitchen"))

    def test_the_generated_gate_script_speaks_hermess_wake_contract(self):
        spec = {"key": "timeline", "monitor_module": "companion_timeline", "gate": True}
        path = scaffold.write_preread_script(self.c, spec, "gate")
        self.assertEqual(path.name, "companion-timeline-gate.py")
        run = subprocess.run(
            [sys.executable, str(path)], capture_output=True, text=True, timeout=60
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        # Hermes skips the agent only when the last non-empty line is this JSON.
        last = [line for line in run.stdout.splitlines() if line.strip()][-1]
        self.assertEqual(
            json.loads(last), {"wakeAgent": False, "reason": "Image timeline is off"}
        )

    def test_a_photo_that_should_go_ahead_says_so(self):
        # Hermes skips a run whose pre-run script printed nothing, so a silent "go"
        # was a skip too: no timeline photo was taken once the gate shipped.
        out = io.StringIO()
        with (
            patch.object(
                sys, "argv", ["companion_timeline.py", "--home", str(self.c.home), "gate"]
            ),
            patch.object(tl, "gate", return_value=None),
            redirect_stdout(out),
        ):
            tl.main()
        last = [line for line in out.getvalue().splitlines() if line.strip()][-1]
        self.assertEqual(json.loads(last), {"wakeAgent": True})

    def test_the_photo_job_is_gated_in_place_of_a_pre_read(self):
        specs = json.loads((ROOT / "kit/templates/cron/manifest.json").read_text())[
            "jobs"
        ]
        timeline = next(s for s in specs if s["key"] == "timeline")
        self.assertTrue(timeline["gate"])
        self.assertFalse(timeline.get("preread"))


if __name__ == "__main__":
    unittest.main()
