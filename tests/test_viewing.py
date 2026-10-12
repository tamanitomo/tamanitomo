"""What the human watches, from their own media server, and what the two of them watch together."""

import datetime as dt
import http.server
import json
import os
import pathlib
import sys
import threading
import urllib.parse

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "kit/scripts"))

import companion_config as cc  # noqa: E402
import companion_context as context  # noqa: E402
import companion_sensors as sensors  # noqa: E402
import companion_story as story  # noqa: E402
import companion_viewing as viewing  # noqa: E402
from tests.support import AppFixture  # noqa: E402

TZ = dt.timezone.utc
NIGHT = dt.datetime(2026, 10, 20, 20, 51, tzinfo=TZ)
TOKEN = "plex-token-123"


def epoch(when):
    return int(when.timestamp())


def plex_episode(show, season, episode, title, **extra):
    return {
        "type": "episode",
        "grandparentTitle": show,
        "parentIndex": season,
        "index": episode,
        "title": title,
        "ratingKey": f"{show}-{season}-{episode}",
        **extra,
    }


class FakeServer(http.server.BaseHTTPRequestHandler):
    """Plex and Jellyfin, as far as the viewing sensor asks either of them."""

    routes = {}
    seen = []
    status = 200

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        FakeServer.seen.append({"path": self.path, "headers": dict(self.headers)})
        token_ok = (
            self.headers.get("X-Plex-Token") == TOKEN
            or self.headers.get("X-Emby-Token") == TOKEN
        )
        body = FakeServer.routes.get(url.path)
        status = FakeServer.status if token_ok else 401
        if body is None and status == 200:
            status = 404
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if status == 200:
            self.wfile.write(json.dumps(body(url) if callable(body) else body).encode())

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    FakeServer.routes, FakeServer.seen, FakeServer.status = {}, [], 200
    httpd = http.server.HTTPServer(("127.0.0.1", 0), FakeServer)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


@pytest.fixture
def companion(tmp_path):
    c = cc.Companion(
        agent="Nova",
        human="Robin",
        hermes_root=tmp_path / "hermes",
        vault=tmp_path / "vault",
        timezone="UTC",
        soul_in_vault=False,
    )
    c.home.mkdir(parents=True)
    c.life.mkdir(parents=True)
    c.soul_dir.mkdir(parents=True, exist_ok=True)
    c.save()
    return c


def connect(c, url, kind="plex", user=""):
    token = c.home / "secrets" / "media.token"
    token.parent.mkdir(parents=True, exist_ok=True)
    token.write_text(TOKEN + "\n")
    c.media_server, c.media_kind, c.media_user = url, kind, user
    c.media_token_file = str(token)
    c.sensors = ["viewing"]
    c.save()
    return c


def plex(now_playing=(), history=(), accounts=None):
    FakeServer.routes.update(
        {
            "/status/sessions": {
                "MediaContainer": {
                    "size": len(now_playing),
                    "Metadata": list(now_playing),
                }
            },
            "/status/sessions/history/all": {
                "MediaContainer": {"size": len(history), "Metadata": list(history)}
            },
            "/accounts": {
                "MediaContainer": {
                    "Account": accounts
                    or [{"id": 1, "name": "robin"}, {"id": 7, "name": "guest"}]
                }
            },
        }
    )


def ambient(c):
    path = c.soul_dir / "ambient/viewing.md"
    return path.read_text() if path.exists() else None


class TestPlex:
    def test_silent_until_a_server_and_token_are_set(self, companion):
        companion.sensors = ["viewing"]
        result = sensors.run_one(companion, "viewing", NIGHT)
        assert result["wrote"] is False and "no media server" in result["reason"]
        companion.media_server = "http://127.0.0.1:9"
        result = sensors.run_one(companion, "viewing", NIGHT)
        assert result["wrote"] is False and "token" in result["reason"]
        assert ambient(companion) is None

    def test_what_is_on_and_what_was_finished_by_the_human_only(
        self, companion, server
    ):
        connect(companion, server)
        plex(
            now_playing=[
                plex_episode(
                    "Severance",
                    2,
                    3,
                    "Who Is Alive?",
                    viewOffset=24 * 60000,
                    duration=51 * 60000,
                    User={"id": "1", "title": "robin"},
                    Player={"state": "playing"},
                ),
                plex_episode(
                    "Bluey",
                    1,
                    1,
                    "Magic Xylophone",
                    User={"id": "7", "title": "guest"},
                ),
            ],
            history=[
                plex_episode(
                    "Severance",
                    2,
                    2,
                    "Goodbye, Mrs. Selvig",
                    accountID=1,
                    viewedAt=epoch(NIGHT - dt.timedelta(days=1)),
                ),
                {
                    "type": "movie",
                    "title": "Paddington 2",
                    "year": 2017,
                    "ratingKey": "p2",
                    "accountID": 1,
                    "viewedAt": epoch(NIGHT - dt.timedelta(days=3)),
                },
                plex_episode(
                    "Bluey",
                    1,
                    2,
                    "Hospital",
                    accountID=7,
                    viewedAt=epoch(NIGHT - dt.timedelta(hours=2)),
                ),
            ],
        )
        result = sensors.run_one(companion, "viewing", NIGHT)
        assert result["wrote"], result
        text = ambient(companion)
        assert (
            "At 20:51 Robin was watching Severance S2E3 “Who Is Alive?” on Plex, "
            "24 of 51 minutes in." in text
        )
        assert "Severance up to S2E2, last night" in text
        assert "Paddington 2 (2017), on Saturday" in text
        assert "Bluey" not in text
        assert "never a list to recite" in text
        history = next(r for r in FakeServer.seen if "history" in r["path"])
        assert "accountID=1" in history["path"] and "viewedAt>=" in history["path"]

    def test_the_token_travels_in_a_header_never_the_address(self, companion, server):
        connect(companion, server)
        plex()
        sensors.run_one(companion, "viewing", NIGHT)
        assert FakeServer.seen
        for request in FakeServer.seen:
            assert TOKEN not in request["path"]
            assert request["headers"]["X-Plex-Token"] == TOKEN
        assert TOKEN not in (companion.home / cc.CONFIG_NAME).read_text()

    def test_finished_viewing_is_kept_once_and_outlasts_the_server(
        self, companion, server
    ):
        connect(companion, server)
        episode = plex_episode(
            "Slow Horses",
            4,
            1,
            "Identity Theft",
            accountID=1,
            viewedAt=epoch(NIGHT - dt.timedelta(hours=1)),
        )
        plex(history=[episode])
        viewing.sync(companion, NIGHT)
        viewing.sync(companion, NIGHT + dt.timedelta(minutes=15))
        assert len(viewing.seen(companion)) == 1
        plex(history=[])  # the server forgot it
        sensors.run_one(companion, "viewing", NIGHT + dt.timedelta(days=1))
        assert "Slow Horses up to S4E1, last night" in ambient(companion)

    def test_a_server_that_cannot_be_read_says_nothing(self, companion, server):
        connect(companion, server)
        plex(
            history=[
                plex_episode("Severance", 2, 2, "x", accountID=1, viewedAt=epoch(NIGHT))
            ]
        )
        assert sensors.run_one(companion, "viewing", NIGHT)["wrote"]
        FakeServer.status = 500
        result = sensors.run_one(companion, "viewing", NIGHT)
        assert result["wrote"] is False and "answered 500" in result["reason"]
        assert ambient(companion) is None  # yesterday's picture is not kept as today's

    def test_a_refused_token_is_said_plainly(self, companion, server):
        connect(companion, server)
        pathlib.Path(companion.media_token_file).write_text("wrong")
        plex()
        with pytest.raises(ValueError, match="Plex refused the token"):
            viewing.check(companion, NIGHT)

    def test_a_named_account_is_looked_up(self, companion, server):
        connect(companion, server, user="Guest")
        plex(
            history=[
                plex_episode(
                    "Bluey", 1, 2, "Hospital", accountID=7, viewedAt=epoch(NIGHT)
                ),
                plex_episode(
                    "Severance", 2, 2, "x", accountID=1, viewedAt=epoch(NIGHT)
                ),
            ]
        )
        rows = viewing.history(companion, NIGHT - dt.timedelta(days=1))
        assert [r["show"] for r in rows] == ["Bluey"]
        companion.media_user = "nobody"
        with pytest.raises(ValueError, match="no account called 'nobody'"):
            viewing.check(companion, NIGHT)


class TestWatchingTogether:
    def test_explicit_server_mode_needs_a_server_first(self, companion):
        with pytest.raises(ValueError, match="no media server"):
            viewing.together(companion, "Severance", 3, NIGHT, mode="server")

    def test_she_is_told_what_it_is_about_and_it_is_remembered_as_together(
        self, companion, server
    ):
        connect(companion, server)
        start = NIGHT - dt.timedelta(minutes=30)
        assert viewing.together(companion, "severance", 3, start)["written"]
        again = viewing.together(companion, "Severance", 2, start)
        assert again["written"] is False and "already watching" in again["reason"]
        playing = plex_episode(
            "Severance",
            2,
            3,
            "Who Is Alive?",
            viewOffset=10 * 60000,
            duration=51 * 60000,
            summary="Mark and Helly go looking for a missing colleague.",
            User={"id": "1"},
        )
        plex(now_playing=[playing])
        sensors.run_one(companion, "viewing", NIGHT)
        text = ambient(companion)
        assert "You are watching this together (agreed at 20:21)." in text
        assert "Mark and Helly go looking for a missing colleague." in text
        assert "Synopsis only, not scene perception" in text
        assert "Avoid spoilers beyond the observed playhead" in text
        # The episode ends just after the agreed window, and is still theirs.
        finished = {
            **playing,
            "accountID": 1,
            "viewedAt": epoch(start + dt.timedelta(hours=3, minutes=20)),
        }
        plex(history=[finished])
        viewing.sync(companion, start + dt.timedelta(hours=4))
        (row,) = viewing.seen(companion)
        assert row["together"] is True
        assert viewing.lately(companion, start + dt.timedelta(hours=4)) == [
            "Severance up to S2E3, tonight (watched together)"
        ]

    def test_something_else_on_is_not_together(self, companion, server):
        connect(companion, server)
        viewing.together(companion, "Severance", 3, NIGHT)
        plex(now_playing=[plex_episode("The Bear", 3, 1, "Tomorrow", User={"id": "1"})])
        sensors.run_one(companion, "viewing", NIGHT + dt.timedelta(minutes=5))
        text = ambient(companion)
        assert "watching this together" not in text
        assert (
            "You agreed at 20:51 to watch Severance together; it is not on yet." in text
        )

    def test_stop_ends_it(self, companion, server):
        connect(companion, server)
        viewing.together(companion, "Severance", 3, NIGHT)
        assert viewing.stop(companion, NIGHT + dt.timedelta(hours=1)) == {
            "stopped": ["Severance"]
        }
        assert viewing.active(companion, NIGHT + dt.timedelta(hours=1, minutes=1)) == []

    def test_chat_refreshes_what_is_on_while_watching_together(self, companion, server):
        connect(companion, server)
        plex(
            now_playing=[
                plex_episode(
                    "Severance",
                    2,
                    3,
                    "Who Is Alive?",
                    viewOffset=33 * 60000,
                    duration=51 * 60000,
                    User={"id": "1"},
                )
            ]
        )
        viewing.together(companion, "Severance", 3)
        text = context.build(companion)
        assert "[What Robin is watching]" in text
        assert "33 of 51 minutes in" in text
        assert "You are watching this together" in text
        assert "viewing:" not in text  # not repeated in the ambient share

    def test_manual_sessions_are_offered_without_a_sensor_or_server(
        self, companion, server
    ):
        manual = story.instructions(companion)
        assert "companion_viewing.py" in manual
        assert "manual" in manual and "--evidence" in manual
        connect(companion, server)
        offered = story.instructions(companion)
        assert "companion_viewing.py" in offered and "together --title" in offered


class TestJellyfin:
    def test_reads_the_named_account(self, companion, server):
        connect(companion, server, kind="jellyfin", user="robin")
        FakeServer.routes.update(
            {
                "/Users": [
                    {"Name": "admin", "Id": "u0", "Policy": {"IsAdministrator": True}},
                    {"Name": "Robin", "Id": "u1", "Policy": {}},
                ],
                "/Sessions": [
                    {
                        "UserId": "u1",
                        "NowPlayingItem": {
                            "Type": "Movie",
                            "Name": "Arrival",
                            "ProductionYear": 2016,
                            "RunTimeTicks": 116 * 600_000_000,
                            "Id": "m1",
                        },
                        "PlayState": {
                            "PositionTicks": 40 * 600_000_000,
                            "IsPaused": True,
                        },
                    },
                    {
                        "UserId": "u0",
                        "NowPlayingItem": {"Type": "Movie", "Name": "Heat"},
                    },
                ],
                "/Users/u1/Items": {
                    "Items": [
                        {
                            "Type": "Episode",
                            "SeriesName": "Andor",
                            "ParentIndexNumber": 2,
                            "IndexNumber": 4,
                            "Name": "Ever Been to Ghorman?",
                            "Id": "e1",
                            "UserData": {
                                "LastPlayedDate": "2026-10-19T22:10:03.1234567Z",
                                "Played": True,
                            },
                        }
                    ]
                },
            }
        )
        result = sensors.run_one(companion, "viewing", NIGHT)
        assert result["wrote"], result
        text = ambient(companion)
        assert (
            "Robin was watching Arrival (2016) on Jellyfin, 40 of 116 minutes in, paused."
            in text
        )
        assert "Andor up to S2E4, last night" in text
        assert "Heat" not in text
        assert all(r["headers"]["X-Emby-Token"] == TOKEN for r in FakeServer.seen)


class TestTimeWords:
    @pytest.mark.parametrize(
        "at,words",
        [
            (NIGHT.replace(hour=19), "tonight"),
            (NIGHT.replace(hour=11), "today"),
            ((NIGHT - dt.timedelta(days=1)).replace(hour=22), "last night"),
            (NIGHT.replace(hour=1), "last night"),
            ((NIGHT - dt.timedelta(days=1)).replace(hour=13), "yesterday"),
            ((NIGHT - dt.timedelta(days=3)).replace(hour=21), "on Saturday"),
            (NIGHT - dt.timedelta(days=12), "on 8 Oct"),
        ],
    )
    def test_a_viewing_day_runs_to_four_in_the_morning(self, at, words):
        assert viewing._when(at, NIGHT) == words


class TestTheSetting:
    @pytest.mark.parametrize(
        "field,value,message",
        [
            ("media_server", "ftp://nas.invalid", "http"),
            ("media_server", "http://nas.invalid:32400/?X-Plex-Token=abc", "alone"),
            ("media_kind", "emby", "plex"),
        ],
    )
    def test_refuses_what_it_cannot_use(self, companion, field, value, message):
        setattr(companion, field, value)
        with pytest.raises(ValueError, match=message):
            companion.__post_init__()


class ViewingSettingsApiTests(AppFixture):
    def test_session_json_type_errors_are_bad_requests_without_writes(self):
        for payload in (
            {"title": 123},
            {"title": "Film", "mode": {}},
            {"title": "Film", "comments": ["quiet"]},
        ):
            response = self.client.post("/api/viewing/sessions", json=payload)
            self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(
            self.client.get("/api/viewing/sessions").json()["sessions"], []
        )

    def test_the_token_is_kept_privately_and_never_shown(self):
        r = self.client.post(
            "/api/settings",
            json={
                "media_server": "http://192.0.2.10:32400",
                "media_kind": "plex",
                "media_token": "s3cret-token",
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotIn("s3cret-token", r.text)
        c = cc.load(self.c.home)
        token = pathlib.Path(c.media_token_file)
        self.assertEqual(token.read_text().strip(), "s3cret-token")
        self.assertEqual(token.parent.name, "secrets")
        if os.name != "nt":
            self.assertEqual(token.stat().st_mode & 0o777, 0o600)
        self.assertNotIn("s3cret-token", (c.home / cc.CONFIG_NAME).read_text())
        got = self.client.get("/api/settings").json()
        self.assertIs(got["media_token_set"], True)
        self.assertEqual(got["media_server"], "http://192.0.2.10:32400")
        self.assertNotIn("s3cret-token", json.dumps(got))
        # Saving without retyping keeps it; removing the server forgets it.
        r = self.client.post("/api/settings", json={"media_user": "robin"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(token.exists())
        r = self.client.post("/api/settings", json={"media_server": ""})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(token.exists())
        self.assertEqual(cc.load(self.c.home).media_token_file, "")

    def test_check_says_what_is_wrong(self):
        got = self.client.post("/api/viewing/check").json()
        self.assertEqual(got, {"ok": False, "detail": "set the server address first"})
