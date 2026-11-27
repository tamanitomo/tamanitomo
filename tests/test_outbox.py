"""Deterministic queue expiry, daily quotas, quiet hours, and dispatch admission."""

import datetime as dt
import json
import pathlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import companion_config as cc
import companion_dispatch as dispatch
import companion_life as life
import companion_outbox as outbox
import companion_outreach as out
import companion_self as slf

ROOT = Path(__file__).resolve().parents[1]
OUTBOX_TZ = dt.timezone.utc


def past_just_met(test):
    """These tests are about the person's own limits, so the companion is past
    Just Met, whose one-message-a-day rule (companion_gates) is tested apart."""
    import companion_gates

    stage = patch.object(companion_gates, "stage_now", return_value=1)
    stage.start()
    test.addCleanup(stage.stop)


class OutboxFixture(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        self.c = cc.Companion(
            agent="Nova",
            human="Alex",
            hermes_root=root / "home",
            vault=root / "vault",
            timezone="UTC",
            quiet_start="23:00",
            quiet_end="08:00",
            outreach_per_day=2,
        )
        self.c.life.mkdir(parents=True, exist_ok=True)
        past_just_met(self)
        self.day = dt.datetime(2026, 9, 10, 14, 0, tzinfo=OUTBOX_TZ)
        self.night = dt.datetime(2026, 9, 11, 2, 0, tzinfo=OUTBOX_TZ)
        self.evening = dt.datetime(2026, 9, 10, 22, 30, tzinfo=OUTBOX_TZ)

    def q(self, **kw):
        now = kw.pop("now", self.day)
        entry = {"kind": "text", "body": "thinking about you", "reason": "test"}
        entry.update(kw)
        return outbox.queue(self.c, entry, now)["entry"]


class QueueTests(OutboxFixture):

    def test_a_message_carries_an_expiry_from_the_moment_it_is_queued(self):
        entry = self.q()
        self.assertEqual(entry["status"], "queued")
        self.assertTrue(entry["expires_at"] > entry["queued_at"])

    def test_media_needs_an_absolute_path_that_exists_by_send_time(self):
        with self.assertRaisesRegex(ValueError, "media_path"):
            self.q(kind="image")
        with self.assertRaisesRegex(ValueError, "absolute"):
            self.q(kind="image", media_path="pic.png")

    def test_a_full_queue_is_an_error_not_a_bigger_queue(self):
        for i in range(outbox.MAX_QUEUED):
            self.q(body=f"message {i}")
        with self.assertRaisesRegex(ValueError, "queue is full"):
            self.q(body="one too many")

    def test_the_fold_is_the_state_and_the_file_keeps_everything(self):
        entry = self.q()
        outbox.mark(self.c, entry["id"], "sent", "ok", self.day)
        self.assertEqual([e["status"] for e in outbox.fold(self.c)], ["sent"])
        self.assertEqual(outbox.waiting(self.c, self.day), [])
        self.assertIn(
            "thinking about you",
            (self.c.life / "outbox.jsonl").read_text(encoding="utf-8"),
        )

    def test_high_priority_goes_to_the_front(self):
        self.q(body="ordinary")
        self.q(body="urgent", priority="high")
        self.assertEqual(
            [e["body"] for e in outbox.waiting(self.c, self.day)],
            ["urgent", "ordinary"],
        )


class DispatcherTests(OutboxFixture):

    def dispatch(self, now, **kw):
        with patch.object(dispatch, "deliver", return_value=(True, "sent")) as sent:
            result = dispatch.run(self.c, now, **kw)
        return (result, sent)

    def test_an_expired_message_is_dropped_and_never_sent_late(self):
        """The 00:07 backlog flush, prevented: an afternoon thought does not
        arrive in the small hours because the queue finally opened."""
        self.q(body="want to say goodnight", ttl_hours=1)
        result, sent = self.dispatch(self.day + dt.timedelta(hours=4))
        self.assertEqual(result["handled"][0]["action"], "expire")
        sent.assert_not_called()
        self.assertEqual([e["status"] for e in outbox.fold(self.c)], ["expired"])

    def test_a_backlog_is_never_flushed_at_once(self):
        for i in range(3):
            self.q(body=f"thought {i}")
        result, sent = self.dispatch(self.day)
        self.assertEqual(sent.call_count, 1)
        self.assertEqual(result["still_waiting"], 2)

    def test_quiet_hours_hold_a_message_rather_than_dropping_it(self):
        self.q(body="awake and thinking", now=self.evening)
        result, sent = self.dispatch(self.night)
        self.assertEqual(result["handled"][0]["action"], "hold")
        self.assertIn("quiet hours", result["handled"][0]["reason"])
        sent.assert_not_called()

    def test_being_visibly_awake_beats_the_sleep_window(self):
        """A window describes someone's night. If they just wrote, they are up."""
        self.q(body="me too", now=self.evening)
        thread = self.c.soul_dir / "ambient"
        thread.mkdir(parents=True, exist_ok=True)
        (thread / "thread.json").write_text(
            json.dumps(
                {"last_from_human": (self.night - dt.timedelta(minutes=5)).isoformat()}
            ),
            encoding="utf-8",
        )
        result, sent = self.dispatch(self.night)
        self.assertEqual(result["handled"][0]["action"], "sent")

    def test_being_awake_does_not_raise_the_daily_cap(self):
        thread = self.c.soul_dir / "ambient"
        thread.mkdir(parents=True, exist_ok=True)
        (thread / "thread.json").write_text(
            json.dumps(
                {"last_from_human": (self.night - dt.timedelta(minutes=5)).isoformat()}
            ),
            encoding="utf-8",
        )
        for i in range(3):
            self.q(body=f"thought {i}", now=self.evening)
        for _ in range(2):
            self.dispatch(self.night)
        result, sent = self.dispatch(self.night)
        self.assertEqual(result["handled"][0]["action"], "hold")
        self.assertIn("Daily limit", result["handled"][0]["reason"])

    def test_the_older_file_name_still_counts(self):
        """Before 3.22 the dispatcher read a name nothing wrote; a file of that name
        written by hand (as these tests once did) still reads the same."""
        self.q(body="me too", now=self.evening)
        thread = self.c.soul_dir / "ambient"
        thread.mkdir(parents=True, exist_ok=True)
        (thread / "relationship-thread.json").write_text(
            json.dumps(
                {"last_from_human": (self.night - dt.timedelta(minutes=5)).isoformat()}
            ),
            encoding="utf-8",
        )
        result, _ = self.dispatch(self.night)
        self.assertEqual(result["handled"][0]["action"], "sent")

    def test_the_thread_sensor_itself_lifts_the_window(self):
        """The real thing: the thread sensor's own file, as the senses job writes it."""
        import companion_sensors

        self.q(body="me too", now=self.evening)
        thread = self.c.soul_dir / "ambient"
        thread.mkdir(parents=True, exist_ok=True)
        stamp = (self.night - dt.timedelta(minutes=5)).isoformat()
        (thread / "thread.json").write_text(
            json.dumps(
                {"checked_at": stamp, "available": True, "last_from_human": stamp}
            ),
            encoding="utf-8",
        )
        self.assertIn("thread", companion_sensors.REGISTRY)
        result, _ = self.dispatch(self.night)
        self.assertEqual(result["handled"][0]["action"], "sent")

    def test_an_old_message_from_the_human_does_not_count_as_awake(self):
        self.q(body="me too", now=self.evening)
        thread = self.c.soul_dir / "ambient"
        thread.mkdir(parents=True, exist_ok=True)
        (thread / "thread.json").write_text(
            json.dumps(
                {"last_from_human": (self.night - dt.timedelta(hours=5)).isoformat()}
            ),
            encoding="utf-8",
        )
        result, _ = self.dispatch(self.night)
        self.assertEqual(result["handled"][0]["action"], "hold")

    def test_a_photo_set_to_ask_is_withheld_with_a_reason_she_can_act_on(self):
        self.c.content_permissions = {"image": "ask"}
        self.q(
            kind="image",
            body="the light in the kitchen",
            media_path=str(self.c.vault / "x.png"),
        )
        result, sent = self.dispatch(self.day)
        self.assertEqual(result["handled"][0]["action"], "withhold")
        self.assertIn("offer it in words", result["handled"][0]["reason"])
        sent.assert_not_called()

    def test_a_photo_set_to_no_never_goes(self):
        self.c.content_permissions = {"image": "no"}
        self.q(kind="image", body="look", media_path=str(self.c.vault / "x.png"))
        result, sent = self.dispatch(self.day)
        self.assertEqual(result["handled"][0]["action"], "withhold")
        sent.assert_not_called()

    def test_the_daily_cap_holds_and_is_counted_on_disk(self):
        for i in range(3):
            self.q(body=f"thought {i}")
        for _ in range(2):
            self.dispatch(self.day)
        result, sent = self.dispatch(self.day)
        self.assertEqual(result["handled"][0]["action"], "hold")
        self.assertIn("Daily limit", result["handled"][0]["reason"])
        sent.assert_not_called()

    def test_a_failed_send_keeps_its_slot_and_is_not_retried(self):
        self.q(body="hello")
        with patch.object(dispatch, "deliver", return_value=(False, "unconfirmed")):
            dispatch.run(self.c, self.day)
        self.assertEqual([e["status"] for e in outbox.fold(self.c)], ["unknown"])
        self.q(body="again")
        result, _ = self.dispatch(self.day)
        self.assertEqual(result["handled"][0]["action"], "sent")
        self.q(body="third")
        result, _ = self.dispatch(self.day)
        self.assertEqual(result["handled"][0]["action"], "hold")

    def test_not_before_holds_without_burning_anything(self):
        self.q(
            body="morning", not_before=(self.day + dt.timedelta(hours=2)).isoformat()
        )
        result, sent = self.dispatch(self.day)
        self.assertEqual(result["handled"][0]["action"], "hold")
        result, sent = self.dispatch(self.day + dt.timedelta(hours=3))
        self.assertEqual(result["handled"][0]["action"], "sent")

    def test_a_dry_run_still_expires_but_sends_nothing(self):
        self.q(body="stale", ttl_hours=1)
        self.q(body="fresh")
        result, sent = self.dispatch(self.day + dt.timedelta(hours=4), send=False)
        actions = [h["action"] for h in result["handled"]]
        self.assertIn("expire", actions)
        self.assertIn("would-send", actions)
        sent.assert_not_called()


TZ = ZoneInfo("America/New_York")
WINDOWS = [4096, 8192, 16384, 32768, 65536, 131072, 272000]


def make(tmp, **kw):
    base = dict(
        agent="Nova",
        human="Alex",
        pronoun_set="she",
        timezone="America/New_York",
        hermes_root=tmp / ".hermes",
        vault=tmp / "vault",
    )
    base.update(kw)
    c = cc.Companion(**base)
    c.soul_dir.mkdir(parents=True, exist_ok=True)
    (c.soul_dir / "ActiveContext.md").write_text(
        "## Right now\nAt the desk.\n\n## Active open loops\n### Porch light\n- waiting on the switch\n### Dentist\n- open since Tuesday\n\n## Ignore me\nnot injected\n",
        encoding="utf-8",
    )
    return c


def seed(c, facts=25):
    now = dt.datetime.now(TZ)
    life.record(
        c.life,
        "Stayed too long in the bookstore.",
        "bookstore",
        "completed",
        now,
        agent=c.agent,
        human=c.human,
    )
    for i in range(facts):
        slf.record_fact(
            c.human_dir,
            f"Alex detail {i} recorded at some length",
            f"said it {i}",
            now,
            category="likes",
        )
    slf.record_pref(
        c.life, "The quiet before he wakes.", now, valence="like", agent=c.agent
    )
    slf.ask(c.life, "Has Alex ever lived abroad?", now)


class OutreachGateTests(unittest.TestCase):
    """Quiet hours and the daily cap decided in code, with no model involved."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        self.c = cc.Companion(
            agent="Nova",
            human="Alex",
            hermes_root=root / "h",
            vault=root / "v",
            timezone="UTC",
            outreach="free",
            outreach_per_day=3,
        )
        past_just_met(self)
        self.noon = dt.datetime(2026, 9, 9, 12, 0, tzinfo=dt.timezone.utc)
        self.night = dt.datetime(2026, 9, 9, 2, 0, tzinfo=dt.timezone.utc)

    def test_quiet_hours_wrap_midnight(self):
        self.assertTrue(out.in_quiet_hours(self.c, self.night))
        self.assertFalse(out.in_quiet_hours(self.c, self.noon))
        for hour in (23, 0, 3, 7):
            self.assertTrue(
                out.in_quiet_hours(self.c, self.noon.replace(hour=hour)), hour
            )
        for hour in (8, 12, 22):
            self.assertFalse(
                out.in_quiet_hours(self.c, self.noon.replace(hour=hour)), hour
            )

    def test_the_daily_cap_is_counted_not_trusted(self):
        self.assertTrue(out.decide(self.c, self.noon)["allowed"])
        for _ in range(3):
            out.record(self.c, "hello", self.noon)
        d = out.decide(self.c, self.noon)
        self.assertFalse(d["allowed"])
        self.assertIn("3 of 3", d["reason"])
        self.assertTrue(out.decide(self.c, self.noon + dt.timedelta(days=1))["allowed"])

    def test_quiet_hours_beat_a_free_policy_but_urgent_passes(self):
        self.assertFalse(out.decide(self.c, self.night)["allowed"])
        self.assertTrue(out.decide(self.c, self.night, urgent=True)["allowed"])
        for _ in range(3):
            out.record(self.c, "x", self.night)
        self.assertFalse(out.decide(self.c, self.night, urgent=True)["allowed"])

    def test_never_means_never_and_no_limit_means_only_quiet_hours(self):
        quiet = cc.dataclasses.replace(self.c, outreach="never")
        self.assertFalse(out.decide(quiet, self.noon)["allowed"])
        free = cc.dataclasses.replace(self.c, outreach_per_day=0)
        for _ in range(9):
            out.record(free, "x", self.noon)
        self.assertTrue(out.decide(free, self.noon)["allowed"])
        self.assertFalse(out.decide(free, self.night)["allowed"])

    def test_a_corrupt_ledger_line_does_not_unlock_the_gate(self):
        for _ in range(3):
            out.record(self.c, "x", self.noon)
        with out.path(self.c).open("a", encoding="utf-8") as f:
            f.write("{not json\n\n")
        self.assertFalse(out.decide(self.c, self.noon)["allowed"])

    def test_claim_reserves_once_and_refuses_after_cap(self):
        for i in range(3):
            self.assertTrue(out.claim(self.c, "test", self.noon)["allowed"])
        self.assertFalse(out.claim(self.c, "test", self.noon)["allowed"])
        self.assertEqual(out.sent_today(self.c, self.noon), 3)
        self.assertFalse(out.path(self.c).read_bytes().startswith(b"\x00"))
        self.assertTrue(out.path(self.c).with_suffix(".jsonl.lock").exists())

    def test_corruption_cannot_create_an_available_slot(self):
        out.path(self.c).parent.mkdir(parents=True, exist_ok=True)
        for content in ("{bad\n", "[]\n", '{"kind":"outreach","day":"bad"}\n'):
            out.path(self.c).write_text(content, encoding="utf-8")
            self.assertFalse(out.claim(self.c, "test", self.noon)["allowed"])
            self.assertEqual(out.path(self.c).read_text(encoding="utf-8"), content)

    def test_simultaneous_processes_cannot_overbook_the_daily_cap(self):
        import json
        import subprocess

        # The claims run in other processes, out of reach of a patched stage, so
        # the person's own cap is tested with the stage ladder switched off.
        c = cc.dataclasses.replace(
            self.c,
            quiet_start="00:00",
            quiet_end="00:00",
            relationship_progression="off",
        )
        c.save()
        script = pathlib.Path(out.__file__)
        children = [
            subprocess.Popen(
                [sys.executable, str(script), "claim", "--home", str(c.home)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for _ in range(8)
        ]
        results = []
        for child in children:
            stdout, stderr = child.communicate(timeout=30)
            self.assertIn(child.returncode, (0, 1), stderr)
            results.append(json.loads(stdout))
        self.assertEqual(sum((r["allowed"] for r in results)), 3)


def test_maintenance_wrappers_dispatch_seven_helpers_without_model_calls(tmp_path):
    """The scheduler runs deterministic helpers against the selected profile."""
    import runpy

    import companion_worker_model as worker

    from kit.cli.scaffold import write_job_script

    manifest = json.loads(
        (ROOT / "kit/templates/cron/manifest.json").read_text(encoding="utf-8")
    )
    specs = {row["key"]: row for row in manifest["jobs"]}
    expected = {
        "timeline_cleanup": ("companion_timeline", ["prune"]),
        "watch": ("companion_watch", []),
        "dispatch": ("companion_dispatch", []),
        "sensors": ("companion_sensors", []),
        "meters": ("companion_meters", ["tick"]),
        "quiet": ("companion_quiet", ["--apply"]),
        "vault": ("companion_vault", ["commit"]),
    }
    assert len(expected) == 7
    assert {key for key, spec in specs.items() if spec.get("no_agent")} == set(
        expected
    ) | {"rollover"}
    assert specs["rollover"]["no_agent"] is True
    assert specs["rollover"]["script"] == {"module": "companion_rollover", "args": []}
    companion = cc.Companion(
        hermes_root=tmp_path / "home with spaces 雪",
        vault=tmp_path / "vault",
        profile="nova",
    )
    calls = []

    def record(module, *, run_name):
        calls.append((module, run_name, list(sys.argv)))

    with (
        patch.object(
            worker, "complete", side_effect=AssertionError("Maintenance called a model")
        ) as complete,
        patch.object(runpy, "run_module", side_effect=record),
        patch.object(sys, "argv", ["maintenance-test"]),
        patch.object(sys, "path", list(sys.path)),
    ):
        for key, (module, arguments) in expected.items():
            spec = specs[key]
            assert spec["no_agent"] is True
            assert spec["toolsets"] == [] and spec["sensitivity"] == "none"
            wrapper = write_job_script(companion, spec)
            runpy.run_path(str(wrapper), run_name="__main__")
            assert calls[-1] == (
                module,
                "__main__",
                [module + ".py", "--home", str(companion.home), *arguments],
            )
        complete.assert_not_called()
    assert len(calls) == 7


def test_updater_drains_the_hermes_root_and_resumes_after_install_failure(tmp_path):
    from types import SimpleNamespace

    import pytest
    from kit.app import updates

    app_root = tmp_path / "application"
    app_root.mkdir()
    (app_root / "VERSION").write_text("3.5.0", encoding="utf-8")
    hermes_root = tmp_path / "separate Hermes home"
    paused = [(hermes_root, "dispatch-job")]
    runtime = object()
    with (
        patch.object(
            updates,
            "check_github_update",
            return_value={
                "checked": True,
                "has_update": True,
                "latest_version": "3.6.0",
            },
        ),
        patch.object(cc, "load", return_value=SimpleNamespace(hermes_root=hermes_root)),
        patch.object(
            updates, "_drain_dispatchers", return_value=(paused, runtime)
        ) as drain,
        patch.object(updates, "_resume_dispatchers") as resume,
    ):
        report = lambda progress: None
        with pytest.raises(ValueError, match="not a release installation"):
            updates.perform_in_app_update(report, root=app_root)
        drain.assert_called_once_with(hermes_root, report)
        resume.assert_called_once_with(paused, runtime)


def test_updater_only_pauses_and_resumes_enabled_dispatch_jobs(tmp_path):
    import companion_render as render
    from kit.app import updates
    from kit.cli.common import load_manifest

    companion = cc.Companion(
        agent="Nova",
        profile="nova",
        hermes_root=tmp_path / "hermes",
        vault=tmp_path / "vault",
        soul_in_vault=False,
    )
    companion.save()
    spec = next(
        row for row in load_manifest(companion)["jobs"] if row["key"] == "dispatch"
    )
    name = render.render(spec["name"], {"AGENT": companion.agent})
    cron = companion.home / "cron"
    cron.mkdir()
    (cron / "jobs.json").write_text(
        json.dumps(
            {
                "jobs": [
                    {"id": "active", "name": name, "enabled": True},
                    {"id": "disabled", "name": name, "enabled": False},
                    {"id": "unrelated", "name": "Other scheduled job", "enabled": True},
                ]
            }
        ),
        encoding="utf-8",
    )
    calls = []

    class Runtime:
        def __init__(self, root):
            assert root == companion.hermes_root

        def run(self, args, *, home, timeout):
            calls.append((args, home, timeout))

    with patch.object(updates, "_dispatch_running", return_value=False):
        paused, runtime = updates._drain_dispatchers(
            companion.hermes_root, lambda progress: None, runtime_cls=Runtime
        )
        updates._resume_dispatchers(paused, runtime)
    assert paused == [(companion.home, "active")]
    assert calls == [
        (["cron", "pause", "active"], companion.home, 15),
        (["cron", "resume", "active"], companion.home, 15),
    ]


def test_updater_process_observation_and_failed_drain_restore_paused_jobs(tmp_path):
    from types import SimpleNamespace
    from unittest.mock import Mock

    import pytest
    from kit.app import updates

    for platform, os_name, executable in (
        ("darwin", "posix", "ps"),
        ("win32", "nt", "powershell.exe"),
    ):
        with (
            patch.object(sys, "platform", platform),
            patch.object(updates.os, "name", os_name),
            patch("os.scandir", side_effect=AssertionError("Portable path read /proc")),
            patch("subprocess.run") as run,
        ):
            run.return_value = SimpleNamespace(returncode=0, stdout="python app.py")
            assert updates._dispatch_running() is False
            assert run.call_args.args[0][0] == executable
            run.return_value.stdout = "python companion_dispatch.py"
            assert updates._dispatch_running() is True
            run.return_value.stdout = "TAMANITOMO_UNREADABLE_PROCESS"
            assert updates._dispatch_running() is None
            run.side_effect = PermissionError("Process inspection unavailable")
            assert updates._dispatch_running() is None

    for running, error in ((None, "Cannot verify"), (True, "still running")):
        runtime = Mock()
        with (
            patch.object(
                updates, "_all_dispatch_jobs", return_value=[(tmp_path, "dispatch")]
            ),
            patch.object(updates, "_dispatch_running", return_value=running),
            patch("time.sleep") as sleep,
            pytest.raises(ValueError, match=error),
        ):
            updates._drain_dispatchers(
                tmp_path,
                lambda progress: None,
                runtime_cls=lambda root: runtime,
                wait_seconds=0,
            )
        assert [call.args[0] for call in runtime.run.call_args_list] == [
            ["cron", "pause", "dispatch"],
            ["cron", "resume", "dispatch"],
        ]
        sleep.assert_not_called()

    runtime = Mock()
    runtime.run.side_effect = [None, ValueError("Pause failed"), None]
    with (
        patch.object(
            updates,
            "_all_dispatch_jobs",
            return_value=[(tmp_path, "first"), (tmp_path, "second")],
        ),
        pytest.raises(ValueError, match="Pause failed"),
    ):
        updates._drain_dispatchers(
            tmp_path,
            lambda progress: None,
            runtime_cls=lambda root: runtime,
            wait_seconds=0,
        )
    assert [call.args[0] for call in runtime.run.call_args_list] == [
        ["cron", "pause", "first"],
        ["cron", "pause", "second"],
        ["cron", "resume", "first"],
    ]


class SentRecentlyTests(unittest.TestCase):
    """She knows what she sent even when the copy into her conversation failed."""

    def setUp(self):
        import companion_config as cc

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
        self.c.save()

    def test_a_delivered_message_is_listed_and_an_old_one_is_not(self):
        import companion_active as active
        import companion_outbox as outbox

        now = dt.datetime(2026, 10, 9, 22, 0, tzinfo=dt.timezone.utc)
        rows = []
        for ident, body, sent_at in (
            ("old", "A photo from last week.", now - dt.timedelta(days=2)),
            ("new", "The lake at dusk, just for you.", now - dt.timedelta(hours=3)),
            ("waiting", "Still in the queue.", None),
        ):
            rows.append(
                {
                    "kind": "outbox",
                    "id": ident,
                    "content": "image",
                    "body": body,
                    "status": "queued",
                    "priority": "normal",
                    "queued_at": (now - dt.timedelta(days=3)).isoformat(),
                }
            )
            if sent_at:
                rows.append(
                    {
                        "kind": "outbox_update",
                        "id": ident,
                        "status": "sent",
                        "at": sent_at.isoformat(),
                    }
                )
        outbox.path_for(self.c).write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
        )
        self.assertEqual(
            outbox.render_sent(self.c, now),
            "- Fri 19:00 image: The lake at dusk, just for you.\n"
            "Earlier these two weeks (say something new, not these again):\n"
            "- Wed 07 Oct image: A photo from last week.",
        )
        page = active.build(self.c, now)
        self.assertIn("## You already sent (last two weeks)", page)
        self.assertNotIn("Still in the queue.\nEarlier", page)


class SayingItAgainTests(unittest.TestCase):
    """Two weeks of what she said, so she does not say it again."""

    NOW = dt.datetime(2026, 10, 20, 12, 0, tzinfo=dt.timezone.utc)

    def setUp(self):
        import companion_outbox as outbox

        self.outbox = outbox
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.c = cc.Companion(
            agent="Nova",
            human="Robin",
            hermes_root=root / "h",
            vault=root / "v",
            timezone="UTC",
            soul_in_vault=False,
        )
        self.c.life.mkdir(parents=True)

    def said(self, body, days_ago, status="sent"):
        at = self.NOW - dt.timedelta(days=days_ago)
        ident = f"m{len(self.outbox.fold(self.c))}"
        rows = [
            {
                "kind": "outbox",
                "id": ident,
                "content": "text",
                "body": body,
                "status": "queued",
                "priority": "normal",
                "queued_at": at.isoformat(),
                "expires_at": (at + dt.timedelta(hours=8)).isoformat(),
                "target": "telegram",
            }
        ]
        if status != "queued":
            rows.append(
                {
                    "kind": "outbox_update",
                    "id": ident,
                    "status": status,
                    "at": at.isoformat(),
                }
            )
        with self.outbox.path_for(self.c).open("a", encoding="utf-8") as f:
            f.write("".join(json.dumps(r) + "\n" for r in rows))

    def queue(self, body):
        return self.outbox.queue(self.c, {"body": body}, self.NOW)

    def test_the_same_news_twice_is_refused_with_the_first(self):
        self.said(
            "I followed the lighthouse question a little further: the keeper's logs "
            "say the lamp was lit every night for ninety years.",
            2,
        )
        with self.assertRaisesRegex(
            ValueError, "you already said nearly this on Sun 18 Oct"
        ):
            self.queue(
                "I followed the lighthouse question further. The keeper's logs confirm "
                "the lamp was lit every single night for ninety years."
            )

    def test_two_weeks_on_it_is_news_again(self):
        self.said(
            "I followed the lighthouse question a little further: the keeper's logs "
            "say the lamp was lit every night for ninety years.",
            15,
        )
        self.assertTrue(
            self.queue(
                "I followed the lighthouse question further. The keeper's logs confirm "
                "the lamp was lit every single night for ninety years."
            )["written"]
        )

    def test_a_good_night_is_a_ritual_not_a_repeat(self):
        self.said("Good night, sleep well \u2764\ufe0f", 1)
        self.assertTrue(
            self.queue("Good night, sleep well, Robin \u2764\ufe0f")["written"]
        )

    def test_what_never_reached_him_can_be_said(self):
        body = (
            "The bakery on the corner finally reopened and the sourdough is back, "
            "still warm when I got there this morning."
        )
        self.said(body, 1, status="failed")
        self.assertTrue(self.queue(body)["written"])

    def test_the_same_opening_every_time_is_refused(self):
        for n, topic in enumerate(("tides", "kites", "bridges")):
            self.said(
                f"I followed a little {topic} curiosity today, about thing {n}.", n + 1
            )
        with self.assertRaisesRegex(ValueError, 'open with "i followed a"'):
            self.queue(
                "I followed a small curiosity about clocks this morning, it was fun."
            )


class UnconfirmedPhotoTests(unittest.TestCase):
    """A photo whose upload timed out usually arrived; she must not read it as unsent."""

    def test_an_upload_timeout_is_counted_as_sent_and_not_resent(self):
        payload = {
            "error": "No deliverable text or media remained after processing MEDIA tags",
            "warnings": ["Failed to send media /vault/a.png: Timed out"],
        }
        out = dispatch.classify("telegram", 1, json.dumps(payload), "")
        self.assertEqual(out["outcome"], "unknown")
        self.assertEqual(out["error_code"], "upload_timeout")
        self.assertIn("count it as sent and do not send it again", out["detail"])

    def test_any_other_unconfirmed_send_says_not_to_queue_it_again(self):
        out = dispatch.classify("telegram", 1, json.dumps({"error": "Bad Gateway"}), "")
        self.assertEqual(out["outcome"], "unknown")
        self.assertIn("do not queue it again", out["detail"])
        self.assertNotIn("failed", out["detail"])

    def test_she_sees_it_among_what_she_sent(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        c = cc.Companion(
            agent="Nova",
            human="Alex",
            hermes_root=Path(tmp.name) / "home",
            vault=Path(tmp.name) / "vault",
            timezone="UTC",
        )
        now = dt.datetime(2026, 10, 12, 15, 0, tzinfo=dt.timezone.utc)
        outbox.path_for(c).parent.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                "kind": "outbox",
                "id": "m1",
                "content": "image",
                "body": "Here it is.",
                "status": "queued",
                "priority": "normal",
                "queued_at": (now - dt.timedelta(minutes=20)).isoformat(),
            },
            {
                "kind": "outbox_update",
                "id": "m1",
                "status": "unknown",
                "at": (now - dt.timedelta(minutes=15)).isoformat(),
            },
        ]
        outbox.path_for(c).write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
        )
        self.assertEqual(
            outbox.render_sent(c, now),
            "- Mon 14:45 image: Here it is." + outbox.UNCONFIRMED,
        )


class WatchTouchHintTests(OutboxFixture):
    """The autonomy job may send a wordless "thinking of you" only as a touch on the watch, and only when a watch is
    connected: the hint renders with a device bridge and is absent without one, with no placeholder left behind.
    """

    def prompt(self):
        import companion_render as cr

        root = pathlib.Path(__file__).resolve().parents[1]
        return cr.render(
            (root / "kit/templates/cron/autonomy.md.tmpl").read_text(encoding="utf-8"),
            cr.mapping_for(self.c),
        )

    def test_with_and_without_a_watch(self):
        import companion_render as cr

        without = self.prompt()
        self.assertEqual(cr.unresolved(without), [])
        self.assertNotIn('"target":"watch"', without)
        self.c.device_bridge_url = "http://127.0.0.1:9/knock"
        with_watch = self.prompt()
        self.assertEqual(cr.unresolved(with_watch), [])
        self.assertIn('a touch there ("target":"watch", "buzz":"tap"', with_watch)
        self.assertIn("Not every day, never twice in one", with_watch)
        self.assertIn(f"{self.c.human}'s watch", with_watch)


class TouchTests(OutboxFixture):
    """A touch in the middle of a conversation ("oh stoppp" with a nudge): straight to the watch, never queued, never
    counted against her outreach, a few words only, at most six an hour, and offered only while they are talking.
    """

    def bridge(self):
        self.c.device_bridge_url = "http://127.0.0.1:9/knock"
        token = self.c.home / "secrets" / "device-bridge.token"
        token.parent.mkdir(parents=True, exist_ok=True)
        token.write_text("t0k", encoding="utf-8")
        self.c.device_bridge_token_file = str(token)

    def test_no_bridge_no_touch(self):
        with self.assertRaises(ValueError) as said:
            outbox.touch(
                self.c, "oh stoppp", "nudge", now=self.day, send=lambda *a: "watch"
            )
        self.assertIn("device bridge", str(said.exception))

    def test_a_nudge_goes_now_and_never_into_the_queue(self):
        self.bridge()
        calls = []

        def send(c, text, buzz, surface, ident):
            calls.append((text, buzz, surface))
            return "watch"

        out_ = outbox.touch(self.c, "oh stoppp", "nudge", now=self.day, send=send)
        self.assertEqual(out_, {"sent": True, "reached": "watch"})
        self.assertEqual(calls, [("oh stoppp", "nudge", "auto")])
        self.assertEqual(
            outbox.fold(self.c), []
        )  # not her outreach: the daily limit is untouched
        logged = [
            json.loads(line)
            for line in outbox.touches_path(self.c).read_text().splitlines()
        ]
        self.assertEqual(
            (logged[0]["text"], logged[0]["buzz"], logged[0]["reached"]),
            ("oh stoppp", "nudge", "watch"),
        )

    def test_a_few_words_and_not_too_often(self):
        self.bridge()
        send = lambda *a: "watch"  # noqa: E731
        for bad in (("", "tap"), ("x" * 61, "tap"), ("hi", "earthquake")):
            with self.assertRaises(ValueError):
                outbox.touch(self.c, *bad, now=self.day, send=send)
        for minute in range(6):
            outbox.touch(
                self.c,
                f"hey {minute}",
                "tap",
                now=self.day + dt.timedelta(minutes=minute),
                send=send,
            )
        with self.assertRaises(ValueError) as said:
            outbox.touch(
                self.c,
                "one more",
                "tap",
                now=self.day + dt.timedelta(minutes=7),
                send=send,
            )
        self.assertIn("enough touches", str(said.exception))
        later = self.day + dt.timedelta(minutes=61)
        self.assertTrue(
            outbox.touch(self.c, "later", "tap", now=later, send=send)["sent"]
        )

    def test_a_bridge_that_does_not_answer_says_so(self):
        self.bridge()
        out_ = outbox.touch(
            self.c, "psst over here", "tap", now=self.day, send=lambda *a: ""
        )
        self.assertFalse(out_["sent"])
        self.assertIn("in words", out_["detail"])

    def test_nothing_connected_is_said_plainly(self):
        self.bridge()
        out_ = outbox.touch(
            self.c, "psst over here", "tap", now=self.day, send=lambda *a: "nowhere"
        )
        self.assertFalse(out_["sent"])
        self.assertIn("nothing of theirs is connected", out_["detail"])

    def test_the_bridge_answer_is_read_for_where_it_went(self):
        import companion_watchalong as watchalong

        self.bridge()

        class Answer:
            def __init__(self, body):
                self.body = json.dumps(body).encode()

            def read(self, *_):
                return self.body

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

        with patch(
            "urllib.request.urlopen", return_value=Answer({"delivered": ["nowhere"]})
        ):
            self.assertEqual(
                watchalong.device_send(self.c, "hi", "tap", "auto", "t1"),
                ([], "nothing connected"),
            )
        with patch(
            "urllib.request.urlopen", return_value=Answer({"delivered": ["wearable"]})
        ):
            self.assertEqual(
                watchalong.device_send(self.c, "hi", "tap", "auto", "t2"),
                (["wearable"], ""),
            )
            self.assertEqual(
                watchalong.to_device(self.c, "hi", "tap", "auto", "t3"), "wearable"
            )
        with patch("urllib.request.urlopen", side_effect=OSError("down")):
            self.assertEqual(
                watchalong.device_send(self.c, "hi", "tap", "auto", "t4"),
                ([], "unreachable"),
            )

    def test_offered_in_a_conversation_never_in_a_scheduled_run(self):
        import companion_context as ctx

        self.bridge()
        talk = ctx.build(
            self.c,
            {"extra": {"user_message": "that hat is a lot", "platform": "telegram"}},
            now=self.day,
        )
        self.assertIn("To touch their watch right now:", talk)
        self.assertIn("companion_outbox.py", talk)
        job = ctx.build(
            self.c,
            {"extra": {"user_message": "[Scheduled run]", "platform": "cron"}},
            now=self.day,
        )
        self.assertNotIn("To touch their watch right now", job)


class WatchTests(OutboxFixture):
    """A touch rather than a text: a few words and a buzz on the human's watch, through the device bridge, under the
    same dispatcher (quiet hours, the daily limit) as any message."""

    def test_no_bridge_no_watch(self):
        with self.assertRaises(ValueError) as said:
            self.q(target="watch", body="hi")
        self.assertIn("device bridge", str(said.exception))

    def test_what_the_watch_takes(self):
        self.c.device_bridge_url = "http://127.0.0.1:9/knock"
        entry = self.q(target="watch", body="thinking of you")
        self.assertEqual((entry["target"], entry["buzz"]), ("watch", "message"))
        self.assertEqual(self.q(target="watch", body="here", buzz="tap")["buzz"], "tap")
        for bad in (
            {"body": "x" * 161},
            {"buzz": "earthquake"},
            {"kind": "voice", "media_path": "/tmp/a.ogg"},
        ):
            with self.assertRaises(ValueError):
                self.q(target="watch", **{"body": "short", **bad})
        with self.assertRaises(ValueError):
            self.q(body="a normal message", buzz="tap")  # a buzz needs the watch

    def test_the_dispatcher_hands_it_to_the_bridge(self):
        self.c.device_bridge_url = "http://127.0.0.1:9/knock"
        self.q(target="watch", body="here", buzz="tap")
        calls = []

        def to_device(c, text, buzz, surface, ident):
            calls.append((text, buzz, surface, ident))
            return "watch"

        with patch("companion_watchalong.to_device", side_effect=to_device):
            result = dispatch.run(self.c, self.day)
        self.assertEqual(result["handled"][0]["action"], "sent")
        self.assertEqual(calls[0][:3], ("here", "tap", "auto"))
        self.assertTrue(calls[0][3].startswith("msg-"))

    def test_a_bridge_that_does_not_take_it_is_a_failure_not_a_guess(self):
        self.c.device_bridge_url = "http://127.0.0.1:9/knock"
        self.q(target="watch", body="here")
        with patch("companion_watchalong.to_device", return_value=""):
            result = dispatch.run(self.c, self.day)
        self.assertNotEqual(result["handled"][0]["action"], "sent")

    def test_quiet_hours_hold_a_touch_too(self):
        self.c.device_bridge_url = "http://127.0.0.1:9/knock"
        self.q(target="watch", body="you up?", now=self.evening)
        with patch("companion_watchalong.to_device", return_value="watch") as bridge:
            result = dispatch.run(self.c, self.night)
        self.assertEqual(result["handled"][0]["action"], "hold")
        bridge.assert_not_called()
