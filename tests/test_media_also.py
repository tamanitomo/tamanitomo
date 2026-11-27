"""Two media servers at once (a Plex and a Jellyfin): what is on and what was finished come from both, each item
knows its server, one server down leaves the other standing, watching together follows the film on whichever
server it is on, and Settings keeps the second server's token as privately as the first's.
"""

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
sys.path[:0] = [str(ROOT), str(ROOT / "kit" / "scripts"), str(ROOT / "tests")]

import companion_config as cc  # noqa: E402
import companion_viewing as viewing  # noqa: E402
import companion_watchalong as watchalong  # noqa: E402
from test_viewing import NIGHT, TOKEN, FakeServer, plex, plex_episode  # noqa: E402
from tests.support import AppFixture  # noqa: E402


class OtherServer(FakeServer):
    """A second fake server with its own routes (FakeServer's handler reads FakeServer's own)."""

    routes = {}
    seen = []
    status = 200

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        OtherServer.seen.append({"path": self.path, "headers": dict(self.headers)})
        token_ok = (
            self.headers.get("X-Plex-Token") == TOKEN
            or self.headers.get("X-Emby-Token") == TOKEN
        )
        body = OtherServer.routes.get(url.path)
        status = OtherServer.status if token_ok else 401
        if body is None and status == 200:
            status = 404
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if status == 200:
            self.wfile.write(json.dumps(body(url) if callable(body) else body).encode())


def start(handler):
    handler.routes, handler.seen, handler.status = {}, [], 200
    httpd = http.server.HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


@pytest.fixture
def two(tmp_path):
    plex_httpd, plex_url = start(FakeServer)
    jelly_httpd, jelly_url = start(OtherServer)
    c = cc.Companion(agent="Nova", human="Robin", hermes_root=tmp_path / "hermes", vault=tmp_path / "vault",
                     timezone="UTC", soul_in_vault=False)  # fmt: skip
    c.home.mkdir(parents=True)
    c.life.mkdir(parents=True)
    c.soul_dir.mkdir(parents=True, exist_ok=True)
    token = c.home / "secrets" / "media.token"
    token.parent.mkdir(parents=True, exist_ok=True)
    token.write_text(TOKEN + "\n", encoding="utf-8")
    c.media_server, c.media_kind, c.media_token_file = plex_url, "plex", str(token)
    c.media_also = [
        {
            "server": jelly_url,
            "kind": "jellyfin",
            "user": "robin",
            "token_file": str(token),
        }
    ]
    c.sensors = ["viewing"]
    c.save()
    yield c, plex_url, jelly_url
    plex_httpd.shutdown()
    jelly_httpd.shutdown()


def jellyfin_routes(playing=True, finished=True):
    OtherServer.routes.update(
        {
            "/Users": [{"Name": "Robin", "Id": "u1", "Policy": {}}],
            "/Sessions": [
                {
                    "UserId": "u1",
                    "NowPlayingItem": {"Type": "Movie", "Name": "Tidewater", "ProductionYear": 2021, "Id": "m9",
                                       "RunTimeTicks": 100 * 600_000_000},
                    "PlayState": {"PositionTicks": 30 * 600_000_000, "IsPaused": False},
                }
            ]
            if playing
            else [],
            "/Users/u1/Items": {
                "Items": [
                    {"Type": "Movie", "Name": "Clockmakers", "ProductionYear": 2020, "Id": "m7",
                     "UserData": {"LastPlayedDate": "2026-10-19T22:10:03.1234567Z", "Played": True}}
                ]
                if finished
                else []
            },
        }
    )  # fmt: skip


def test_both_servers_are_read_and_each_item_knows_its_own(two):
    c, plex_url, jelly_url = two
    plex(now_playing=[plex_episode("Severance", 2, 3, "Who Is Alive?", viewOffset=60000, duration=3000000,
                                   User={"id": "1"})],
         history=[plex_episode("Severance", 2, 2, "Goodbye", viewedAt=int(NIGHT.timestamp()) - 7200, accountID=1)])  # fmt: skip
    jellyfin_routes()
    on = viewing.now_playing(c)
    assert sorted((i["source"], i["base"]) for i in on) == [
        ("jellyfin", jelly_url),
        ("plex", plex_url),
    ]
    assert (
        viewing.server_for(
            c, next(i for i in on if i["source"] == "jellyfin")
        ).media_server
        == jelly_url
    )
    viewing.sync(c, NIGHT)
    rows = [
        json.loads(line)
        for line in viewing.path_for(c).read_text(encoding="utf-8").splitlines()
    ]
    assert sorted(r["source"] for r in rows) == ["jellyfin", "plex"]
    text, facts = viewing.sense(c, NIGHT)
    assert (
        "Severance" in text and "on Plex" in text
    )  # one thing on at a time in the text, named by its server
    assert facts["source"] == "plex,jellyfin"
    assert sorted(facts["playing"]) == [
        "Severance S2E3 “Who Is Alive?”",
        "Tidewater (2021)",
    ]


def test_a_film_on_the_other_server_is_named_by_it(two):
    c, _plex_url, _jelly_url = two
    plex(now_playing=[])
    jellyfin_routes()
    text, _facts = viewing.sense(c, NIGHT)
    assert "watching Tidewater (2021) on Jellyfin" in text


def test_one_server_down_leaves_the_other(two):
    c, _plex_url, _jelly_url = two
    plex(
        now_playing=[plex_episode("Severance", 2, 3, "Who Is Alive?", User={"id": "1"})]
    )
    jellyfin_routes()
    OtherServer.status = 500
    on = viewing.now_playing(c)
    assert [i["source"] for i in on] == ["plex"]
    FakeServer.status = 500
    with pytest.raises(ValueError):
        viewing.now_playing(c)  # nothing readable is an error, never "nothing on"


def test_watching_together_follows_the_film_on_its_own_server(two):
    c, plex_url, jelly_url = two
    plex(now_playing=[])
    jellyfin_routes()
    rows = watchalong.playing(c)
    assert [(r["server"], r["base"], r["title"]) for r in rows] == [
        ("jellyfin", jelly_url, "Tidewater")
    ]
    asked = []

    def fetch(view, current):
        asked.append(view.media_server)
        return {"raw": None, "why": "no subtitles", "read": None}

    follower = watchalong.Follower(c, read=watchalong.playing, fetch=fetch, speak=lambda *a: None,
                                   send=lambda *a: [])  # fmt: skip
    follower.tick()
    assert asked == [jelly_url]  # the subtitles were asked of the server the film is on
    assert follower.view.media_kind == "jellyfin"


class MediaAlsoSettingsTests(AppFixture):
    def test_the_second_server_and_its_token(self):
        r = self.client.post("/api/settings", json={"media_also_server": "http://192.0.2.20:8096/",
                                                    "media_also_kind": "jellyfin", "media_also_user": "robin",
                                                    "media_also_token": "other-s3cret"})  # fmt: skip
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotIn("other-s3cret", r.text)
        c = cc.load(self.c.home)
        self.assertEqual(
            {k: c.media_also[0][k] for k in ("server", "kind", "user")},
            {"server": "http://192.0.2.20:8096", "kind": "jellyfin", "user": "robin"},
        )
        token = pathlib.Path(c.media_also[0]["token_file"])
        self.assertEqual(token.read_text(encoding="utf-8").strip(), "other-s3cret")
        if os.name != "nt":
            self.assertEqual(token.stat().st_mode & 0o777, 0o600)
        got = self.client.get("/api/settings").json()
        self.assertEqual(got["media_also"], [{"server": "http://192.0.2.20:8096", "kind": "jellyfin",
                                              "user": "robin", "token_set": True}])  # fmt: skip
        self.assertNotIn("other-s3cret", json.dumps(got))
        # Saving without retyping keeps it; an empty address forgets the server and its token.
        r = self.client.post(
            "/api/settings",
            json={
                "media_also_server": "http://192.0.2.20:8096",
                "media_also_user": "robin",
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(token.exists())
        r = self.client.post("/api/settings", json={"media_also_server": ""})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(token.exists())
        self.assertEqual(cc.load(self.c.home).media_also, [])

    def test_a_token_needs_an_address(self):
        r = self.client.post(
            "/api/settings", json={"media_also_token": "tok-without-address"}
        )
        self.assertEqual(r.status_code, 400, r.text)
        bad = self.client.post(
            "/api/settings", json={"media_also_server": "ftp://nope"}
        )
        self.assertEqual(bad.status_code, 400, bad.text)


def test_one_server_still_works_as_before(tmp_path):
    c = cc.Companion(
        agent="Nova", human="Robin", hermes_root=tmp_path / "h", vault=tmp_path / "v"
    )
    assert viewing.servers(c) == []
    c.media_server = "http://127.0.0.1:9"
    assert [v.media_server for v in viewing.servers(c)] == ["http://127.0.0.1:9"]
    assert viewing.server_for(c, {"base": "http://elsewhere"}) is c
    _ = dt  # kept for symmetry with the other viewing tests
