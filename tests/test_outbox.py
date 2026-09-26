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
        self.assertIn("thinking about you", (self.c.life / "outbox.jsonl").read_text())

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
        (thread / "relationship-thread.json").write_text(
            json.dumps(
                {"last_from_human": (self.night - dt.timedelta(minutes=5)).isoformat()}
            )
        )
        result, sent = self.dispatch(self.night)
        self.assertEqual(result["handled"][0]["action"], "sent")

    def test_being_awake_does_not_raise_the_daily_cap(self):
        thread = self.c.soul_dir / "ambient"
        thread.mkdir(parents=True, exist_ok=True)
        (thread / "relationship-thread.json").write_text(
            json.dumps(
                {"last_from_human": (self.night - dt.timedelta(minutes=5)).isoformat()}
            )
        )
        for i in range(3):
            self.q(body=f"thought {i}", now=self.evening)
        for _ in range(2):
            self.dispatch(self.night)
        result, sent = self.dispatch(self.night)
        self.assertEqual(result["handled"][0]["action"], "hold")
        self.assertIn("Daily limit", result["handled"][0]["reason"])

    def test_an_old_message_from_the_human_does_not_count_as_awake(self):
        self.q(body="me too", now=self.evening)
        thread = self.c.soul_dir / "ambient"
        thread.mkdir(parents=True, exist_ok=True)
        (thread / "relationship-thread.json").write_text(
            json.dumps(
                {"last_from_human": (self.night - dt.timedelta(hours=5)).isoformat()}
            )
        )
        result, _ = self.dispatch(self.night)
        self.assertEqual(result["handled"][0]["action"], "hold")

    def test_a_photo_set_to_ask_is_withheld_with_a_reason_she_can_act_on(self):
        self.c.content_permissions = {"image": "ask"}
        self.q(kind="image", body="the light in the kitchen", media_path="/tmp/x.png")
        result, sent = self.dispatch(self.day)
        self.assertEqual(result["handled"][0]["action"], "withhold")
        self.assertIn("offer it in words", result["handled"][0]["reason"])
        sent.assert_not_called()

    def test_a_photo_set_to_no_never_goes(self):
        self.c.content_permissions = {"image": "no"}
        self.q(kind="image", body="look", media_path="/tmp/x.png")
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
        "## Right now\nAt the desk.\n\n## Active open loops\n### Porch light\n- waiting on the switch\n### Dentist\n- open since Tuesday\n\n## Ignore me\nnot injected\n"
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
            out.path(self.c).write_text(content)
            self.assertFalse(out.claim(self.c, "test", self.noon)["allowed"])
            self.assertEqual(out.path(self.c).read_text(), content)

    def test_simultaneous_processes_cannot_overbook_the_daily_cap(self):
        import json
        import subprocess

        c = cc.dataclasses.replace(self.c, quiet_start="00:00", quiet_end="00:00")
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


def test_maintenance_wrappers_dispatch_six_helpers_without_model_calls(tmp_path):
    """The scheduler runs deterministic helpers against the selected profile."""
    import runpy

    import companion_worker_model as worker

    from kit.cli.scaffold import write_job_script

    manifest = json.loads((ROOT / "kit/templates/cron/manifest.json").read_text())
    specs = {row["key"]: row for row in manifest["jobs"]}
    expected = {
        "timeline_cleanup": ("companion_timeline", ["prune"]),
        "watch": ("companion_watch", []),
        "dispatch": ("companion_dispatch", []),
        "sensors": ("companion_sensors", []),
        "quiet": ("companion_quiet", ["--apply"]),
        "vault": ("companion_vault", ["commit"]),
    }
    assert len(expected) == 6
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
    assert len(calls) == 6
