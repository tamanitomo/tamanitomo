"""A configured feature that stops working is reported, not just quietly absent.

Her photo setting once pointed at an image server that had stopped, and every
photo failed for a day; she said her camera was not answering, and nothing else
said anything. A sense whose source broke looked the same as one with nothing to
say. And her own log, read back on every run, kept handing the next run the last
one's reason for staying quiet.
"""

import datetime as dt
import json
import pathlib

import pytest

import companion_config as cc
import companion_preread as preread
import companion_sensors as sensors
import companion_watch as watch

NOW = dt.datetime(2026, 10, 12, 15, 30, tzinfo=dt.timezone.utc)
ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def companion(tmp_path):
    c = cc.Companion(
        agent="Nova",
        human="Robin",
        hermes_root=tmp_path / "home",
        vault=tmp_path / "vault",
    )
    c.home.mkdir(parents=True, exist_ok=True)
    watch._probes.clear()
    return c


def images(c, endpoint, provider="comfyui"):
    c.image_mode = "external"
    (c.home / "companion-images.json").write_text(
        json.dumps(
            {
                "version": 1,
                "presets": [
                    {"id": "look", "provider": provider, "endpoint": endpoint},
                    {"id": "unused", "provider": "comfyui", "endpoint": "http://spare:8188"},
                ],
                "routes": {"portrait": "look"},
                "default_preset": "look",
            }
        ),
        encoding="utf-8",
    )


def test_an_image_server_that_does_not_answer_is_reported(companion, monkeypatch):
    images(companion, "http://render-box:8188/")
    asked = []

    def probe(url):
        asked.append(url)
        return False, "[Errno 111] Connection refused"

    monkeypatch.setattr(watch, "_probe", probe)
    found = watch.check_photos(companion)
    # Only the server her routes use is asked, once, and the report names it.
    assert asked == ["http://render-box:8188/system_stats"]
    assert len(found) == 1 and "render-box:8188" in found[0]
    assert "Connection refused" in found[0]


def test_a_working_server_and_no_images_say_nothing(companion, monkeypatch):
    images(companion, "http://render-box:8188")
    monkeypatch.setattr(watch, "_probe", lambda url: (True, "HTTP 200"))
    assert watch.check_photos(companion) == []
    companion.image_mode = "none"
    monkeypatch.setattr(watch, "_probe", lambda url: pytest.fail("asked anyway"))
    assert watch.check_photos(companion) == []


def test_a_hosted_image_provider_is_not_probed(companion, monkeypatch):
    images(companion, "", provider="openai-codex")
    monkeypatch.setattr(watch, "_probe", lambda url: pytest.fail("asked anyway"))
    assert watch.check_photos(companion) == []


def test_a_failed_probe_is_asked_again_soon_and_a_good_one_is_reused(monkeypatch):
    import urllib.request

    calls = []

    class Answer:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def urlopen(url, timeout):
        calls.append(url)
        return Answer()

    watch._probes.clear()
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    assert watch._probe("http://box/system_stats") == (True, "HTTP 200")
    assert watch._probe("http://box/system_stats") == (True, "HTTP 200")
    assert len(calls) == 1


def test_a_broken_sense_is_kept_with_when_it_started_and_cleared_when_it_works(
    companion, monkeypatch
):
    monkeypatch.setattr(
        sensors, "weather", lambda c, now: (None, sensors.Broken("service down"))
    )
    companion.location = "Somewhere"
    sensors.run_one(companion, "weather", NOW)
    sensors.run_one(companion, "weather", NOW + dt.timedelta(hours=1))
    row = sensors.broken_senses(companion)["weather"]
    assert row["since"] == NOW.isoformat()
    assert row["reason"] == "service down"
    monkeypatch.setattr(sensors, "weather", lambda c, now: ("Sunny.", {"temp_c": "20"}))
    sensors.run_one(companion, "weather", NOW + dt.timedelta(hours=2))
    assert "weather" not in sensors.broken_senses(companion)


def test_nothing_to_report_is_not_broken(companion, monkeypatch):
    monkeypatch.setattr(sensors, "dates", lambda c, now: (None, "nothing this week"))
    sensors.run_one(companion, "dates", NOW)
    assert sensors.broken_senses(companion) == {}


def test_a_sense_broken_for_hours_is_a_problem_and_a_blip_is_not(companion, monkeypatch):
    companion.sensors = ["weather", "music"]
    monkeypatch.setattr(
        sensors, "music", lambda c, now: (None, sensors.Broken("sign-in stopped working"))
    )
    sensors.run_one(companion, "music", NOW)
    assert watch.check_senses(companion, NOW + dt.timedelta(hours=1)) == []
    found = watch.check_senses(companion, NOW + dt.timedelta(hours=4))
    assert len(found) == 1 and "music" in found[0] and "sign-in" in found[0]
    # A sense that is switched off is not reported, whatever its file says.
    companion.sensors = ["weather"]
    assert watch.check_senses(companion, NOW + dt.timedelta(hours=4)) == []


def test_spotify_connected_but_signed_out_is_broken(companion, monkeypatch):
    monkeypatch.setattr(sensors, "_spotify_state", lambda c: {"client_id": "x"})
    monkeypatch.setattr(sensors, "_spotify_token", lambda c, st: None)
    text, why = sensors.music(companion, NOW)
    assert text is None and isinstance(why, sensors.Broken)
    monkeypatch.setattr(sensors, "_spotify_state", lambda c: None)
    text, why = sensors.music(companion, NOW)
    assert text is None and not isinstance(why, sensors.Broken)


def outbox(c, *rows):
    path = c.life / "outbox.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for n, (status, hours_ago, detail) in enumerate(rows):
        at = (NOW - dt.timedelta(hours=hours_ago)).isoformat()
        ident = f"msg-{n}"
        lines.append({"id": ident, "kind": "outbox", "status": "queued", "queued_at": at})
        lines.append(
            {"id": ident, "kind": "outbox_update", "status": status, "detail": detail, "at": at}
        )
    path.write_text("".join(json.dumps(r) + "\n" for r in lines), encoding="utf-8")


def test_a_failed_message_with_nothing_through_since_is_a_problem(companion):
    outbox(companion, ("sent", 3, "sent"), ("failed", 1, "chat not found"))
    found = watch.check_delivery(companion, NOW)
    assert len(found) == 1 and "Robin" in found[0] and "chat not found" in found[0]


def test_a_failure_followed_by_a_delivery_is_not(companion):
    outbox(companion, ("failed", 3, "timeout"), ("sent", 1, "sent"))
    assert watch.check_delivery(companion, NOW) == []


def test_one_unconfirmed_photo_is_not_a_problem_but_two_are(companion):
    outbox(companion, ("unknown", 1, "upload timed out"))
    assert watch.check_delivery(companion, NOW) == []
    outbox(companion, ("unknown", 2, "upload timed out"), ("unknown", 1, "upload timed out"))
    assert len(watch.check_delivery(companion, NOW)) == 1


def test_old_failures_are_out_of_the_window(companion):
    outbox(companion, ("failed", 30, "long ago"))
    assert watch.check_delivery(companion, NOW) == []


def test_the_log_tail_is_not_a_precedent_for_staying_quiet(companion):
    log = companion.soul_dir / "continuity" / "Autonomy.md"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("## Cycle\n\nRead a chapter.\n", encoding="utf-8")
    text = preread.preread(companion, NOW, job="autonomy")
    assert "Read a chapter." in text
    assert "not a precedent" in text and "Robin" in text


def test_the_autonomy_prompt_lets_a_find_be_shared():
    text = (ROOT / "kit/templates/cron/autonomy.md.tmpl").read_text(encoding="utf-8")
    assert "do not turn them into outreach" not in text
    assert "telling {{HUMAN}} what you found" in text
    assert "not why you did not write to {{HUMAN}}" in text
