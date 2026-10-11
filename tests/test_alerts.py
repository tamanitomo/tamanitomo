"""Health alerts reach the human, not the companion's conversation."""

import datetime as dt
import http.server
import json
import pathlib
import sys
import threading
from unittest.mock import patch

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "kit/scripts"))

import companion_config as cc  # noqa: E402
import companion_watch as watch  # noqa: E402
from tests.support import AppFixture  # noqa: E402

NOON = dt.datetime(2026, 10, 20, 12, tzinfo=dt.timezone.utc)
TROUBLE = ['"Nova companion pulse" is failing: the model could not be reached']


@pytest.fixture
def companion(tmp_path):
    c = cc.Companion(
        agent="Nova",
        human="Robin",
        hermes_root=tmp_path / "hermes",
        vault=tmp_path / "vault",
        timezone="UTC",
        quiet_start="23:00",
        quiet_end="07:00",
        soul_in_vault=False,
    )
    c.home.mkdir(parents=True)
    c.life.mkdir(parents=True)
    c.save()
    return c


class Receiver(http.server.BaseHTTPRequestHandler):
    received = []
    status = 200

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        Receiver.received.append({"headers": dict(self.headers), "body": body})
        self.send_response(Receiver.status)
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def receiver():
    Receiver.received, Receiver.status = [], 200
    server = http.server.HTTPServer(("127.0.0.1", 0), Receiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/push"
    server.shutdown()


def trouble():
    return patch.object(watch, "problems", return_value=list(TROUBLE))


class TestWhereAlertsGo:
    def test_by_default_only_the_app_shows_them(self, companion):
        assert companion.alerts == "app"
        assert watch.notifier(companion) is None
        with trouble():
            result = watch.run(companion, NOON, notify=watch.notifier(companion))
        assert result["problems"] == TROUBLE and "delivered" not in result
        health = (companion.soul_dir / "ambient/health.md").read_text()
        assert "not a script to read out" in health

    def test_her_chat_only_when_chosen(self, companion):
        companion.alerts = "chat"
        sent = []
        with patch(
            "companion_dispatch.hermes_send",
            side_effect=lambda c, m: sent.append(m) or (True, "sent"),
        ):
            with trouble():
                result = watch.run(companion, NOON, notify=watch.notifier(companion))
        assert result["delivered"] and sent[0].startswith("Nova is not well")

    def test_a_webhook_gets_json_with_its_token(self, companion, receiver, tmp_path):
        token = tmp_path / "push.token"
        token.write_text("s3cret\n")
        companion.alerts_webhook = receiver
        companion.alerts_webhook_token_file = str(token)
        with trouble():
            result = watch.run(companion, NOON, notify=watch.notifier(companion))
        assert result["delivered"]
        (got,) = Receiver.received
        assert got["headers"]["Authorization"] == "Bearer s3cret"
        payload = json.loads(got["body"])
        assert payload["title"] == "Nova needs a look"
        assert TROUBLE[0] in payload["body"] and payload["message"] == payload["body"]
        assert payload["data"] == {"kind": "tamanitomo-health", "agent": "Nova"}

    def test_text_for_ntfy(self, companion, receiver):
        companion.alerts_webhook = receiver
        companion.alerts_webhook_format = "text"
        with trouble():
            watch.run(companion, NOON, notify=watch.notifier(companion))
        (got,) = Receiver.received
        assert got["headers"]["Title"] == "Nova needs a look"
        assert got["body"].decode().startswith("Nova is not well right now:")

    def test_a_failed_push_is_tried_again_next_run(self, companion, receiver):
        companion.alerts_webhook = receiver
        Receiver.status = 500
        with trouble():
            first = watch.run(companion, NOON, notify=watch.notifier(companion))
            Receiver.status = 200
            second = watch.run(
                companion,
                NOON + dt.timedelta(hours=1),
                notify=watch.notifier(companion),
            )
        assert not first["delivered"] and second["delivered"]
        assert len(Receiver.received) == 2

    def test_quiet_hours_hold_a_push_too(self, companion, receiver):
        companion.alerts_webhook = receiver
        with trouble():
            result = watch.run(
                companion,
                NOON.replace(hour=2),
                notify=watch.notifier(companion),
            )
        assert result["held"] and Receiver.received == []


class TestTheSetting:
    @pytest.mark.parametrize(
        "field,value",
        [
            ("alerts", "phone"),
            ("alerts_webhook", "ftp://example.invalid/x"),
            ("alerts_webhook_format", "xml"),
        ],
    )
    def test_refuses_what_it_cannot_do(self, companion, field, value):
        setattr(companion, field, value)
        with pytest.raises(ValueError, match=field):
            companion.__post_init__()


class AlertSettingsApiTests(AppFixture):
    def test_the_page_can_send_alerts_to_the_chat_and_back(self):
        got = self.client.get("/api/settings").json()
        self.assertEqual(got["alerts"], "app")
        self.assertIs(got["alerts_webhook"], False)
        r = self.client.post("/api/settings", json={"alerts": "chat"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(cc.load(self.c.home).alerts, "chat")
        r = self.client.post("/api/settings", json={"alerts": "phone"})
        self.assertEqual(r.status_code, 400)

    def test_a_webhook_address_is_never_shown(self):
        c = cc.load(self.c.home)
        c.alerts_webhook = "https://ntfy.example.invalid/private-topic"
        c.save()
        got = self.client.get("/api/settings").json()
        self.assertIs(got["alerts_webhook"], True)
        self.assertNotIn("private-topic", json.dumps(got))
