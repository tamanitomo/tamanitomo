"""How long one photo may take (issue #5): automatic, chosen, or from the environment."""

import dataclasses
import os
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock

import companion_config as cc
import companion_media as media


class ImageTimeoutTests(unittest.TestCase):
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
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("COMPANION_IMAGE_TIMEOUT", None)

    def image_server(self, url):
        (self.c.home / "config.yaml").write_text(
            "image_gen:\n  provider: openai\n  openai:\n"
            f"    base_url: {url}\n    model: some-model\n",
            encoding="utf-8",
        )

    def test_a_hosted_service_keeps_ten_minutes(self):
        self.assertEqual(media.image_timeout(self.c), 600)
        self.image_server("https://api.example.com/v1")
        self.assertEqual(media.image_timeout(self.c), 600)

    def test_an_image_server_on_your_own_network_gets_thirty_minutes(self):
        for url in (
            "http://127.0.0.1:7860/v1",
            "http://localhost:8080",
            "http://[::1]:8080/v1",
            "http://192.168.1.50:8080/v1",
            "http://10.0.0.4/v1",
            "http://100.101.102.103:7860",
            "http://gpu-box:8080/v1",
            "http://render.local:8080",
            "https://gpu.tail1234.ts.net/v1",
        ):
            with self.subTest(url=url):
                self.image_server(url)
                self.assertEqual(media.image_timeout(self.c), 1800)

    def test_a_public_address_is_not_mistaken_for_a_local_one(self):
        for url in ("http://[2001:4860:4860::8888]/v1", "http://8.8.8.8/v1"):
            with self.subTest(url=url):
                self.image_server(url)
                self.assertEqual(media.image_timeout(self.c), 600)

    def test_comfyui_keeps_its_ten_minutes_unless_a_time_is_chosen(self):
        self.image_server("http://192.168.1.50:8080/v1")
        self.assertEqual(media.image_timeout(self.c, comfyui=True), 600)
        chosen = dataclasses.replace(self.c, image_timeout_seconds=1200)
        self.assertEqual(media.image_timeout(chosen, comfyui=True), 1200)

    def test_a_chosen_time_wins_over_automatic(self):
        self.image_server("http://192.168.1.50:8080/v1")
        chosen = dataclasses.replace(self.c, image_timeout_seconds=300)
        self.assertEqual(media.image_timeout(chosen), 300)

    def test_the_environment_wins_and_is_kept_in_range(self):
        chosen = dataclasses.replace(self.c, image_timeout_seconds=300)
        for raw, expected in (("900", 900), ("10", 60), ("99999", 7200)):
            with self.subTest(raw=raw):
                os.environ["COMPANION_IMAGE_TIMEOUT"] = raw
                self.assertEqual(media.image_timeout(chosen), expected)
        os.environ["COMPANION_IMAGE_TIMEOUT"] = "soon"
        self.assertEqual(media.image_timeout(chosen), 300)

    def test_only_automatic_or_a_sane_range_can_be_saved(self):
        for good in (0, 60, 1800, 7200):
            dataclasses.replace(self.c, image_timeout_seconds=good)
        for bad in (30, 7201, -1, "600", 600.0):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                dataclasses.replace(self.c, image_timeout_seconds=bad)

    def test_the_bridge_waits_as_long_and_tells_the_provider(self):
        self.image_server("http://192.168.1.50:8080/v1")
        python = pathlib.Path(self.tmp.name) / "python"
        python.write_text("")
        seen = {}

        def run(args, **kwargs):
            seen.update(kwargs)
            return subprocess.CompletedProcess(
                args, 0, 'COMPANION_IMAGE={"ok": 1}\n', ""
            )

        with (
            mock.patch.object(media.cp, "venv_executable", return_value=python),
            mock.patch("companion_gateway._env_values", return_value={}),
            mock.patch("subprocess.run", side_effect=run),
        ):
            self.assertEqual(media.hermes_bridge(self.c, "generate", {}), {"ok": 1})
            self.assertEqual(seen["timeout"], 1800)
            self.assertEqual(seen["env"]["COMPANION_IMAGE_TIMEOUT"], "1800")
            media.hermes_bridge(self.c, "catalog")
            self.assertEqual(seen["timeout"], 30)


if __name__ == "__main__":
    unittest.main()
