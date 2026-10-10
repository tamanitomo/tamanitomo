"""Setup retries recover the original attempt without creating another companion."""

import dataclasses
import json
import io
import os
import runpy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tests.support import WorkspaceFixture


class SetupRecoveryTests(WorkspaceFixture):
    payload = {
        "profile": "iris",
        "answers": {"boundary": "friends", "agent": "Iris"},
        "request_id": "01234567-89ab-cdef-0123-456789abcdef",
    }

    def run_create(self, argv, **kwargs):
        c = dataclasses.replace(self.c, profile="iris", agent="Iris")
        c.save()
        return SimpleNamespace(stdout="Created synthetic profile")

    def test_retry_after_lost_response_returns_original_operation(self):
        with patch("kit.app.runtime.Runtime.run", side_effect=self.run_create) as run:
            first = self.wait(self.post("/api/profiles", self.payload))
            retry = self.post("/api/profiles", self.payload).json()
            self.assertEqual(first["status"], "complete")
            self.assertEqual(retry["id"], first["id"])
            self.assertEqual(run.call_count, 1)
        state = self.get("/api/onboarding/attempt/" + self.payload["request_id"]).json()
        self.assertTrue(state["created"])
        self.assertEqual(state["profile"], "iris")

    def test_creation_cannot_start_before_its_recovery_journal_is_durable(self):
        from kit.app import manage

        write = manage.cp.atomic_write

        def fail_journal(path, content):
            if "setup" in Path(path).parts and '"operation"' in content:
                raise ValueError("Synthetic journal write failure")
            return write(path, content)

        with (
            patch.object(manage.cp, "atomic_write", side_effect=fail_journal),
            patch("kit.app.runtime.Runtime.run") as run,
        ):
            result = self.post("/api/profiles", self.payload)
        self.assertEqual(result.status_code, 400)
        run.assert_not_called()
        self.assertFalse(self.app.state.operations.busy)
        with patch("kit.app.runtime.Runtime.run", side_effect=self.run_create):
            self.assertEqual(
                self.wait(self.post("/api/profiles", self.payload))["status"],
                "complete",
            )

    def test_initial_operation_write_failure_clears_busy_without_starting_creation(
        self,
    ):
        with (
            patch.object(
                self.app.state.operations,
                "_save",
                side_effect=ValueError("Synthetic operation disk failure"),
            ),
            patch("kit.app.runtime.Runtime.run") as run,
        ):
            result = self.post("/api/profiles", self.payload)
        self.assertEqual(result.status_code, 400)
        run.assert_not_called()
        self.assertFalse(self.app.state.operations.busy)
        self.assertEqual(
            next(iter(self.app.state.operations.rows.values()))["status"], "failed"
        )
        with patch("kit.app.runtime.Runtime.run", side_effect=self.run_create):
            self.assertEqual(
                self.wait(self.post("/api/profiles", self.payload))["status"],
                "complete",
            )

    def test_partial_profile_is_reported_without_repeating_creation(self):
        def fail(argv, **kwargs):
            self.run_create(argv, **kwargs)
            raise ValueError("Synthetic interrupted setup")

        with patch("kit.app.runtime.Runtime.run", side_effect=fail) as run:
            first = self.wait(self.post("/api/profiles", self.payload))
            retry = self.post("/api/profiles", self.payload).json()
            self.assertEqual(first["status"], "failed")
            self.assertEqual(retry["id"], first["id"])
            self.assertEqual(run.call_count, 1)
        state = self.get("/api/onboarding/attempt/" + self.payload["request_id"]).json()
        self.assertTrue(state["created"])

    def test_failed_attempt_without_profile_can_retry_saved_choices(self):
        with patch(
            "kit.app.runtime.Runtime.run",
            side_effect=ValueError("Temporary setup failure"),
        ):
            first = self.wait(self.post("/api/profiles", self.payload))
        with patch("kit.app.runtime.Runtime.run", side_effect=self.run_create) as run:
            retry = self.wait(self.post("/api/profiles", self.payload))
            self.assertNotEqual(first["id"], retry["id"])
            self.assertEqual(retry["status"], "complete")
            self.assertEqual(run.call_count, 1)

    def test_recovery_is_profile_scoped_and_choices_cannot_change_under_request_id(
        self,
    ):
        with patch("kit.app.runtime.Runtime.run", side_effect=self.run_create):
            self.wait(self.post("/api/profiles", self.payload))
        other = self.get(
            "/api/onboarding/attempt/" + self.payload["request_id"], "rowan"
        ).json()
        self.assertFalse(other["created"])
        changed = {
            **self.payload,
            "answers": {"boundary": "friends", "agent": "Different"},
        }
        self.assertEqual(self.post("/api/profiles", changed).status_code, 400)
        # The request journal stores only a digest, never the setup's answer text.
        saved = list((self.app.state.operations.directory / "setup").rglob("*.json"))
        self.assertEqual(len(saved), 1)
        self.assertEqual(
            set(json.loads(saved[0].read_text())), {"profile", "digest", "operation"}
        )

    def test_hermes_folder_without_companion_config_requires_inspection_not_replay(
        self,
    ):
        def partial(argv, **kwargs):
            (self.root / "profiles/iris").mkdir()
            raise ValueError("Scaffolding interrupted")

        with patch("kit.app.runtime.Runtime.run", side_effect=partial) as run:
            first = self.wait(self.post("/api/profiles", self.payload))
            retry = self.post("/api/profiles", self.payload).json()
        self.assertEqual(first["id"], retry["id"])
        self.assertEqual(run.call_count, 1)
        state = self.get("/api/onboarding/attempt/" + self.payload["request_id"]).json()
        self.assertFalse(state["created"])
        self.assertTrue(state["profile_exists"])

    def test_failed_uncreated_attempt_can_review_choices_without_losing_connections(
        self,
    ):
        self.stage_inference()
        with patch(
            "kit.app.runtime.Runtime.run", side_effect=ValueError("Temporary failure")
        ):
            self.wait(self.post("/api/profiles", self.payload))
        changed = {
            **self.payload,
            "answers": {
                **self.payload["answers"],
                "hope": "Revised synthetic preference",
            },
        }
        with patch("kit.app.runtime.Runtime.run", side_effect=self.run_create):
            result = self.wait(self.post("/api/profiles", changed))
        self.assertEqual(result["status"], "complete")
        self.assertIn(
            "synthetic-private-key", (self.root / "profiles/iris/.env").read_text()
        )

    def stage_inference(self):
        with patch("kit.app.runtime.Runtime.info", return_value={"available": False}):
            response = self.post(
                "/api/onboarding/inference",
                {
                    "request_id": self.payload["request_id"],
                    "provider": "openai",
                    "api_key": "synthetic-private-key",
                    "model": "synthetic-model",
                },
            )
        self.assertEqual(response.status_code, 200, response.text)

    def test_connection_staging_does_not_change_existing_profiles_or_installation(self):
        for home in (self.root, self.c.home, self.other.home):
            (home / ".env").write_text(
                'OPENAI_API_KEY="original"\nTELEGRAM_BOT_TOKEN="original-bot"\n'
            )
            (home / "config.yaml").write_text(
                "model:\n  default: original-model\n  provider: original-provider\n"
            )
        originals = {
            path: path.read_bytes()
            for home in (self.root, self.c.home, self.other.home)
            for path in (home / ".env", home / "config.yaml")
        }
        self.stage_inference()
        response = self.post(
            "/api/onboarding/telegram",
            {
                "request_id": self.payload["request_id"],
                "token": "1234:abcdefghijklmnopqrstuvwxyz",
                "user_id": "12345",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(originals, {path: path.read_bytes() for path in originals})
        with patch("kit.app.runtime.Runtime.run", side_effect=self.run_create):
            self.assertEqual(
                self.wait(self.post("/api/profiles", self.payload))["status"],
                "complete",
            )
        target = self.root / "profiles/iris"
        self.assertIn("synthetic-private-key", (target / ".env").read_text())
        self.assertIn("1234:abcdefghijklmnopqrstuvwxyz", (target / ".env").read_text())
        self.assertIn("synthetic-model", (target / "config.yaml").read_text())
        self.assertEqual(originals, {path: path.read_bytes() for path in originals})
        self.assertFalse(
            list((self.app.state.operations.directory / "setup").rglob("*.connections"))
        )
        journal = next(
            (self.app.state.operations.directory / "setup").rglob("*.json")
        ).read_text()
        self.assertNotIn("synthetic-private-key", journal)

    def test_staged_connections_cannot_be_applied_from_another_owner_profile(self):
        self.stage_inference()
        with patch("kit.app.runtime.Runtime.run", side_effect=self.run_create):
            result = self.wait(
                self.post("/api/profiles", self.payload, "rowan"), "rowan"
            )
        self.assertEqual(result["status"], "complete")
        self.assertFalse((self.root / "profiles/iris/.env").exists())
        self.assertTrue(
            list(
                (self.app.state.operations.directory / "setup").rglob(
                    "*.connections/.env"
                )
            )
        )

    def test_adoption_applies_staging_only_to_selected_profile(self):
        (self.root / ".env").write_text('OPENAI_API_KEY="root-original"\n')
        self.stage_inference()
        payload = {
            key: value for key, value in self.payload.items() if key != "profile"
        }
        with patch(
            "kit.app.runtime.Runtime.run",
            return_value=SimpleNamespace(stdout="Synthetic adoption"),
        ):
            result = self.wait(self.post("/api/adopt", payload))
        self.assertEqual(result["status"], "complete")
        self.assertIn("synthetic-private-key", (self.c.home / ".env").read_text())
        self.assertEqual(
            (self.root / ".env").read_text(), 'OPENAI_API_KEY="root-original"\n'
        )
        self.assertFalse((self.other.home / ".env").exists())

    def test_oauth_uses_private_home_and_status_is_owner_scoped(self):
        captured = {}

        def start(argv, **kwargs):
            self.assertEqual(kwargs["env"]["HERMES_HOME"], str(self.root))

            def auth_main(name, *args, **kwargs):
                self.assertEqual(name, "hermes_cli.main")
                captured.update(os.environ)
                Path(captured["HERMES_HOME"], "auth.json").write_text(
                    json.dumps(
                        {"providers": {"xai-oauth": {"tokens": "synthetic-oauth"}}}
                    )
                )

            with (
                patch.dict(os.environ, kwargs["env"], clear=True),
                patch.object(runpy, "run_module", side_effect=auth_main),
            ):
                exec(argv[3], {})
            return SimpleNamespace(
                stdout=io.StringIO(""),
                stderr=io.StringIO(""),
                wait=lambda: 0,
                terminate=lambda: None,
            )

        bootstrap = f"import os, runpy; assert os.environ['HERMES_HOME'] == {str(self.root)!r}; runpy.run_module('hermes_cli.main', run_name='__main__')"
        runtime = SimpleNamespace(
            stdout=json.dumps(["synthetic-python", "-I", "-c", bootstrap])
        )
        with (
            patch("kit.app.manage.subprocess.Popen", side_effect=start),
            patch("kit.app.runtime.Runtime.run", return_value=runtime),
        ):
            response = self.post(
                "/api/onboarding/oauth/start",
                {"request_id": self.payload["request_id"], "provider": "xai-oauth"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        sid = response.json()["session_id"]
        self.assertTrue(
            Path(captured["HERMES_HOME"]).is_relative_to(
                self.app.state.operations.directory
            )
        )
        self.assertTrue(
            Path(captured["HOME"]).is_relative_to(Path(captured["HERMES_HOME"]))
        )
        self.assertEqual(
            self.get("/api/onboarding/oauth/poll/" + sid, "rowan").status_code, 404
        )
        self.assertEqual(
            self.post(
                "/api/onboarding/oauth/cancel/" + sid, profile="rowan"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.get("/api/onboarding/oauth/poll/" + sid).json()["status"], "approved"
        )
        with patch("kit.app.runtime.Runtime.run", side_effect=self.run_create):
            self.assertEqual(
                self.wait(self.post("/api/profiles", self.payload))["status"],
                "complete",
            )
        self.assertIn(
            "synthetic-oauth", (self.root / "profiles/iris/auth.json").read_text()
        )
        self.assertFalse((self.root / "auth.json").exists())
        self.assertFalse((self.c.home / "auth.json").exists())

    def test_start_over_discards_private_credentials_only_in_selected_scope(self):
        self.stage_inference()
        stages = list(
            (self.app.state.operations.directory / "setup").rglob("*.connections")
        )
        self.assertEqual(len(stages), 1)
        route = "/api/onboarding/attempt/" + self.payload["request_id"] + "/discard"
        self.assertEqual(self.post(route, profile="rowan").status_code, 200)
        self.assertTrue(stages[0].exists())
        self.assertEqual(self.post(route).status_code, 200)
        self.assertFalse(stages[0].exists())

    def test_private_staging_expires_after_seven_days_on_recovery(self):
        self.stage_inference()
        stage = next(
            (self.app.state.operations.directory / "setup").rglob("*.connections")
        )
        import time

        old = time.time() - 8 * 86400
        os.utime(stage, (old, old))
        self.get("/api/onboarding/attempt/" + self.payload["request_id"])
        self.assertFalse(stage.exists())

    def test_local_model_selection_stages_profile_overrides(self):
        model_path = self.root.parent / "synthetic.gguf"
        model_path.write_bytes(b"synthetic")
        before = (self.c.home / "companion.json").read_bytes()
        with (
            patch(
                "kit.app.local_models.get_host_memory",
                return_value={"is_mobile": False},
            ),
            patch(
                "kit.app.local_models.validate_model_safety", return_value=(True, "")
            ),
            patch("kit.app.local_models.status", return_value={"online": True}),
        ):
            result = self.wait(
                self.post(
                    "/api/onboarding/local-setup",
                    {
                        "request_id": self.payload["request_id"],
                        "type": "disk",
                        "path": str(model_path),
                        "model_id": "synthetic",
                    },
                )
            )
        self.assertEqual(result["status"], "complete")
        self.assertEqual((self.c.home / "companion.json").read_bytes(), before)
        self.assertFalse((self.root / "config.yaml").exists())
        with patch("kit.app.runtime.Runtime.run", side_effect=self.run_create):
            self.assertEqual(
                self.wait(self.post("/api/profiles", self.payload))["status"],
                "complete",
            )
        target = json.loads((self.root / "profiles/iris/companion.json").read_text())
        self.assertEqual(target["models"]["chat"]["model"], "synthetic")
