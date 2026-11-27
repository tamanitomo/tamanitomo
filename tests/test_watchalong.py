"""Watching together, live: she follows the dialogue of what the human plays and may say something now and then.

Subtitles are read once, the playhead is carried forward between the server's reports, a seek skips lines without
reacting to them, she never sees a line past the playhead, the pace setting decides how often she is asked, silence
is a fine answer, and what she says reaches the human where they last talked, the device bridge, a chat or the TV.
"""

import datetime as dt
import http.server
import json
import pathlib
import sys
import threading
import urllib.parse

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "kit/scripts"), str(ROOT)]

import companion_config as cc  # noqa: E402
import companion_context as context  # noqa: E402
import companion_watchalong as wa  # noqa: E402

TOKEN = "media-token-xyz"
BRIDGE = "bridge-token-abc"
SRT = """﻿1
00:00:05,000 --> 00:00:07,000
<i>[distant thunder]</i>

2
00:02:30,000 --> 00:02:32,000
Pass the salt, would you?

3
00:41:30,000 --> 00:41:33,200
I'll always love you,
no matter what.

4
00:43:00,000 --> 00:43:02,000
Promise me you won't leave.

5
00:44:10,000 --> 00:44:12,000
The ferry leaves at noon.

6
00:58:00,000 --> 00:58:03,000
Will you marry me?

7
01:20:00,000 --> 01:20:02,000
Goodbye, captain.
"""
VTT = """WEBVTT

00:01.000 --> 00:02.500 align:start
<v Captain>Hold fast!</v>

1:02:03.400 --> 1:02:05.000
We reached the shore.
"""


class Fake(http.server.BaseHTTPRequestHandler):
    """Plex, Jellyfin and a device bridge, as far as the follower asks them."""

    routes = {}
    posts = []

    def _ok(self):
        auth = self.headers.get("Authorization", "")
        return (
            self.headers.get("X-Plex-Token") == TOKEN
            or (
                auth.startswith("MediaBrowser ")
                and f'Token="{TOKEN}"' in auth
                and 'DeviceId="' in auth
            )
            or auth == f"Bearer {BRIDGE}"
        )

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        body = Fake.routes.get(url.path)
        if not self._ok():
            self.send_response(401)
            self.end_headers()
            return
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        data = body(url) if callable(body) else body
        raw = data if isinstance(data, str) else json.dumps(data)
        self.send_response(200)
        self.send_header(
            "Content-Type",
            "text/plain" if isinstance(data, str) else "application/json",
        )
        self.end_headers()
        self.wfile.write(raw.encode())

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        Fake.posts.append(
            {
                "path": self.path,
                "body": body,
                "auth": self.headers.get("Authorization", ""),
            }
        )
        if not self._ok():
            self.send_response(401)
            self.end_headers()
            return
        reply = (
            {"delivered": ["watch"], "id": body.get("id")}
            if self.path == "/knock"
            else {}
        )
        self.send_response(200 if self.path == "/knock" else 204)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if self.path == "/knock":
            self.wfile.write(json.dumps(reply).encode())

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    Fake.routes, Fake.posts = {}, []
    httpd = http.server.HTTPServer(("127.0.0.1", 0), Fake)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


@pytest.fixture
def companion(tmp_path):
    c = cc.Companion(
        agent="Nova", human="Robin", hermes_root=tmp_path / "hermes", vault=tmp_path / "vault",
        timezone="UTC", soul_in_vault=False,
    )  # fmt: skip
    c.home.mkdir(parents=True)
    c.life.mkdir(parents=True)
    c.soul_dir.mkdir(parents=True, exist_ok=True)
    (c.home / "SOUL.md").write_text(
        "Nova: warm, wry, quick to tease.", encoding="utf-8"
    )
    c.save()
    return c


def connect(c, url, kind="plex"):
    token = c.home / "secrets" / "media.token"
    token.parent.mkdir(parents=True, exist_ok=True)
    token.write_text(TOKEN + "\n", encoding="utf-8")
    c.media_server, c.media_kind, c.media_token_file = url, kind, str(token)
    c.sensors = ["viewing"]
    c.watchalong = "occasional"
    return c


# ---- subtitles --------------------------------------------------------------------------------------------------
def test_subrip_and_webvtt_become_clean_lines():
    cues = wa.parse_subtitles(SRT)
    assert cues[0].text == "[distant thunder]"
    assert cues[2] == wa.Cue(
        2_490_000, 2_493_200, "I'll always love you, no matter what."
    )
    vtt = wa.parse_subtitles(VTT)
    assert [c.text for c in vtt] == ["Hold fast!", "We reached the shore."]
    assert vtt[1].start == 3_723_400
    assert wa.parse_subtitles("garbage\n\n12\nnot a time\nwords") == []


def test_the_window_never_reaches_past_the_playhead():
    track = wa.Track(wa.parse_subtitles(SRT))
    at = 2_493_200
    assert [c.text for c in track.window(at)] == [
        "I'll always love you, no matter what."
    ]
    assert all(c.end <= at for c in track.window(at, span_ms=10**9))
    assert [c.text for c in track.ended_between(2_400_000, 2_500_000)] == [
        "I'll always love you, no matter what."
    ]


def test_what_lands_and_what_does_not():
    cues = {c.text: c for c in wa.parse_subtitles(SRT)}
    length = 7_200_000
    strong, _ = wa.score(
        cues["I'll always love you, no matter what."], 2_493_200, length
    )
    plain, _ = wa.score(cues["The ferry leaves at noon."], 2_652_000, length)
    proposal, kind = wa.score(cues["Will you marry me?"], 3_483_000, length)
    assert strong >= wa.PACE["occasional"]["threshold"] and plain == 0
    assert proposal >= wa.PACE["moments"]["threshold"] and "a proposal" in kind
    opening, _ = wa.score(cues["[distant thunder]"], 7_000, length)
    credits, _ = wa.score(cues["Goodbye, captain."], length - 60_000, length)
    assert opening == 0 and credits == 0


def test_the_playhead_runs_on_between_reports_and_a_jump_is_a_seek():
    head = wa.Playhead()
    assert head.update(60_000, "playing", 100.0) is True
    assert head.estimate(105.0) == 65_000
    assert (
        head.update(60_000, "playing", 108.0) is False
    )  # the player has not reported since: no jump back
    assert head.estimate(108.0) == 68_000
    assert (
        head.update(66_000, "playing", 110.0) is False
    )  # a report two seconds old: the estimate stands
    assert head.estimate(110.0) == 70_000
    assert (
        head.update(71_000, "playing", 110.0) is False
        and head.estimate(110.0) == 71_000
    )  # ahead: taken
    assert (
        head.update(71_500, "paused", 120.0) is False and head.estimate(500.0) == 71_500
    )  # paused: frozen
    assert head.update(2_400_000, "playing", 501.0) is True
    assert head.update(2_380_000, "playing", 510.0) is True  # well behind: a seek back
    head.update(2_390_000, "playing", 520.0)
    assert (
        head.update(2_393_000, "playing", 523.0) is False
    )  # a short skip back shows twice running
    assert (
        head.update(2_394_000, "playing", 524.0) is False
        and head.estimate(524.0) == 2_394_000
    )


# ---- the follower ------------------------------------------------------------------------------------------------
class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def playing_at(position_ms, state="playing", key="film-1", can_message=False):
    return {
        "server": "plex", "key": key, "what": "movie", "show": None, "season": None, "episode": None,
        "title": "Harbor Lights", "year": 2019, "position_ms": position_ms, "length_ms": 7_200_000,
        "state": state, "session": "s1", "client": "Den", "can_message": can_message,
        "subtitle_stream": None, "media_source": None, "summary": "Two clockmakers fall out.",
    }  # fmt: skip


def follower(c, script, replies=None):
    """A follower on fakes: `script` maps clock time to what the server reports."""
    clock = Clock()
    asked, sent = [], []

    def read(_c):
        # Like a server: the player reports every ten seconds, so the position it gives is up to that stale.
        current, since = None, None
        for t in sorted(script):
            if t <= clock.t:
                current, since = script[t], t
        if not current:
            return []
        if current["state"] == "playing":
            reported = since + ((clock.t - since) // 10) * 10
            return [
                {
                    **current,
                    "position_ms": current["position_ms"]
                    + int((reported - since) * 1000),
                }
            ]
        return [current]

    def speak(_c, messages):
        asked.append(messages)
        answer = (
            (replies or []).pop(0) if replies else '{"say": "aww, same", "buzz": "tap"}'
        )
        return answer, "test-model"

    def send(_c, now_playing, said):
        sent.append(said)
        return ["watch"]

    f = wa.Follower(
        c,
        clock=clock,
        read=read,
        fetch=lambda _c, _p: (SRT, "1"),
        speak=speak,
        send=send,
    )
    return f, clock, asked, sent


def run_until(f, clock, until):
    while clock.t < until:
        wait = f.tick()
        clock.t += min(wait, 1.0)


def test_she_says_something_at_a_line_that_lands_and_never_sees_ahead(
    companion, server
):
    c = connect(companion, server)
    c.device_bridge_url = server + "/knock"
    f, clock, asked, sent = follower(c, {1000.0: playing_at(2_480_000)})
    run_until(f, clock, 1030.0)
    assert len(asked) == 1 and sent == [{"say": "aww, same", "buzz": "tap"}]
    user = asked[0][1]["content"]
    assert ">> [41:30] I'll always love you, no matter what." in user
    assert (
        "Promise me" not in user and "marry" not in user
    )  # what comes later is never shown
    assert "Harbor Lights" in user and "Robin" in asked[0][0]["content"]
    rows = [
        json.loads(line)
        for line in wa.log_path(c).read_text(encoding="utf-8").splitlines()
    ]
    said = [r for r in rows if r["event"] == "said"]
    assert said[0]["said"] == "aww, same" and said[0]["line"].startswith(
        "I'll always love you"
    )


def test_the_pace_keeps_her_from_talking_over_the_film(companion, server):
    c = connect(companion, server)
    # 41:30 lands, and 43:00 ("Promise me") lands too, inside the nine-minute gap: one call only.
    f, clock, asked, _sent = follower(c, {1000.0: playing_at(2_480_000)})
    run_until(f, clock, 1000.0 + 200)
    assert len(asked) == 1
    c.watchalong = "commentary"
    f2, clock2, asked2, _ = follower(c, {1000.0: playing_at(2_480_000)})
    run_until(f2, clock2, 1000.0 + 200)
    assert (
        len(asked2) == 1
    )  # commentary waits 150 s: the second line at +105 s is still too soon
    c.watchalong = "quiet"
    f3, clock3, asked3, _ = follower(c, {1000.0: playing_at(2_480_000)})
    run_until(f3, clock3, 1030.0)
    assert asked3 == [] and wa.scene_now(
        c
    )  # quiet: no word of her own, but she knows the scene


def test_a_seek_past_a_line_is_not_a_reaction(companion, server):
    c = connect(companion, server)
    f, clock, asked, _ = follower(
        c, {1000.0: playing_at(2_400_000), 1006.0: playing_at(2_700_000)}
    )
    run_until(f, clock, 1030.0)
    assert asked == []  # 41:30 was jumped over, never heard


def test_a_pause_holds_everything(companion, server):
    c = connect(companion, server)
    f, clock, asked, _ = follower(c, {1000.0: playing_at(2_480_000, state="paused")})
    run_until(f, clock, 1300.0)
    assert asked == []
    assert "paused at 41:20" in wa.scene_now(c)


def test_silence_is_an_answer(companion, server):
    c = connect(companion, server)
    f, clock, asked, sent = follower(
        c, {1000.0: playing_at(2_480_000)}, replies=['{"say": ""}']
    )
    run_until(f, clock, 1030.0)
    assert len(asked) == 1 and sent == []
    events = [
        json.loads(line)["event"]
        for line in wa.log_path(c).read_text(encoding="utf-8").splitlines()
    ]
    assert "silent" in events and "said" not in events


def test_replies_are_read_kindly():
    assert wa.parse_reply('Sure! {"say": "  oh   stop  ", "buzz": "nudge"}') == {
        "say": "oh stop",
        "buzz": "nudge",
    }
    assert wa.parse_reply("SILENT") is None
    assert wa.parse_reply('{"say": "hm", "buzz": "earthquake"}')["buzz"] == "message"
    assert len(wa.parse_reply(json.dumps({"say": "x" * 500}))["say"]) == wa.SAY_CHARS


# ---- her context ---------------------------------------------------------------------------------------------------
def test_her_context_has_the_scene_while_it_is_now(companion, server):
    c = connect(companion, server)
    f, clock, _asked, _sent = follower(c, {1000.0: playing_at(2_480_000)})
    run_until(f, clock, 1030.0)
    text = context.build(
        c, {"extra": {"user_message": "did you hear that?", "platform": "telegram"}}
    )
    assert "[On screen now" in text and "I'll always love you, no matter what." in text
    assert 'What you said during it: "aww, same"' in text
    data = json.loads(wa.scene_path(c).read_text(encoding="utf-8"))
    data["checked_at"] = (
        dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=10)
    ).isoformat()
    wa.scene_path(c).write_text(json.dumps(data), encoding="utf-8")
    assert wa.scene_now(c) == ""  # ten minutes old while playing: not now any more


# ---- reaching the human ----------------------------------------------------------------------------------------------
def test_reach_is_made_concrete(companion, server, monkeypatch):
    c = connect(companion, server)
    c.watchalong_reach = ["last", "watch", "screen"]
    monkeypatch.setattr(wa, "last_place", lambda _c: "wearable")
    assert (
        wa.targets(c, playing_at(0)) == []
    )  # no bridge: neither the wearable nor the watch
    c.device_bridge_url = server + "/knock"
    assert wa.targets(c, playing_at(0)) == [
        "watch"
    ]  # wearable and watch: one message, the bridge mirrors it
    assert wa.targets(c, playing_at(0, can_message=True)) == ["watch", "screen"]
    monkeypatch.setattr(wa, "last_place", lambda _c: "telegram")
    assert wa.targets(c, playing_at(0)) == ["telegram", "watch"]
    monkeypatch.setattr(wa, "last_place", lambda _c: "game")
    assert wa.targets(c, playing_at(0)) == [
        "watch"
    ]  # the game cannot be reached mid-film


def test_the_device_bridge_gets_a_short_knock(companion, server):
    c = connect(companion, server)
    token = c.home / "secrets" / "bridge.token"
    token.write_text(BRIDGE, encoding="utf-8")
    c.device_bridge_url, c.device_bridge_token_file = server + "/knock", str(token)
    assert wa.to_device(c, "aww, same", "tap", "auto", "w-1") == "watch"
    post = Fake.posts[-1]
    assert post["body"] == {
        "text": "aww, same",
        "kind": "tap",
        "surface": "auto",
        "id": "w-1",
    }
    assert post["auth"] == f"Bearer {BRIDGE}"
    c.device_bridge_token_file = str(c.home / "secrets" / "missing")
    assert wa.to_device(c, "aww, same", "tap", "auto", "w-2") == ""


# ---- the servers -----------------------------------------------------------------------------------------------------
def test_plex_playhead_and_a_sidecar_subtitle(companion, server):
    c = connect(companion, server)
    Fake.routes.update({
        "/status/sessions": {"MediaContainer": {"Metadata": [{
            "type": "movie", "title": "Harbor Lights", "year": 2019, "ratingKey": "77", "viewOffset": 2_480_000,
            "duration": 7_200_000, "User": {"id": "1", "title": "robin"}, "Player": {"state": "playing", "title": "TV"},
            "Session": {"id": "abc"}}]}},
        "/library/metadata/77": {"MediaContainer": {"Metadata": [{"Media": [{"Part": [{"Stream": [
            {"streamType": 3, "id": 5, "codec": "pgs", "languageCode": "eng"},
            {"streamType": 3, "id": 6, "codec": "srt", "languageCode": "eng", "forced": True, "key": "/library/streams/6"},
            {"streamType": 3, "id": 7, "codec": "srt", "languageCode": "eng", "key": "/library/streams/7"}]}]}]}]}},
        "/library/streams/7.srt": SRT,
    })  # fmt: skip
    now = wa.playing(c)
    assert (
        now[0]["position_ms"] == 2_480_000
        and now[0]["state"] == "playing"
        and now[0]["can_message"] is False
    )
    raw, stream = wa.subtitles(c, now[0])
    assert (
        stream == "7" and "no matter what" in raw
    )  # the full track, not the forced one, not the image one
    raw_again, _ = wa.subtitles(c, now[0])
    assert raw_again == raw and len(list(wa.cache_dir(c).glob("*.srt"))) == 1


def test_plex_embedded_subtitles_say_why_they_cannot_be_followed(companion, server):
    c = connect(companion, server)
    Fake.routes["/library/metadata/78"] = {"MediaContainer": {"Metadata": [{"Media": [{"Part": [{"Stream": [
        {"streamType": 3, "id": 9, "codec": "srt", "languageCode": "eng"}]}]}]}]}}  # fmt: skip
    raw, why = wa.subtitles(c, {**playing_at(0, key="78"), "server": "plex"})
    assert raw is None and "inside the video file" in why


def test_jellyfin_playhead_subtitles_and_the_tv_screen(companion, server):
    c = connect(companion, server, kind="jellyfin")
    Fake.routes.update({
        "/Users": [{"Id": "u1", "Name": "robin", "Policy": {"IsAdministrator": True}}],
        "/Sessions": [{"Id": "sess-9", "UserId": "u1", "DeviceName": "Den TV", "SupportsRemoteControl": True,
                       "NowPlayingItem": {"Id": "it1", "Name": "Harbor Lights", "Type": "Movie", "ProductionYear": 2019,
                                          "RunTimeTicks": 72_000_000_000, "MediaStreams": [
                                              {"Type": "Subtitle", "Index": 3, "IsTextSubtitleStream": True,
                                               "Language": "eng", "IsForced": False}]},
                       "PlayState": {"PositionTicks": 24_800_000_000, "IsPaused": False, "MediaSourceId": "ms1"}}],
        "/Videos/it1/ms1/Subtitles/3/Stream.srt": SRT,
    })  # fmt: skip
    now = wa.playing(c)
    assert (
        now[0]["position_ms"] == 2_480_000
        and now[0]["can_message"]
        and now[0]["session"] == "sess-9"
    )
    raw, stream = wa.subtitles(c, now[0])
    assert stream == "3" and "Will you marry me?" in raw
    assert wa.to_screen(c, now[0], "aww, same") == "screen"
    post = Fake.posts[-1]
    assert post["path"] == "/Sessions/sess-9/Message"
    assert post["body"] == {"Header": "Nova", "Text": "aww, same", "TimeoutMs": 9000}


def test_settings_are_checked(companion):
    for bad in ({"watchalong": "always"}, {"watchalong_reach": ["fax"]}, {"watchalong_reach": ["watch", "watch"]},
                {"watchalong_scope": "sometimes"}, {"device_bridge_url": "ftp://x"},
                {"device_bridge_url": "http://user@host/knock"}):  # fmt: skip
        with pytest.raises(ValueError):
            cc.Companion(agent="Nova", human="Robin", **bad)
    c = cc.Companion(
        agent="Nova",
        human="Robin",
        watchalong="auto",
        watchalong_reach=["screen", "last"],
    )
    assert c.watchalong_reach == ["screen", "last"]


# ---- reading the film itself ---------------------------------------------------------------------------------------
class Ranged(http.server.BaseHTTPRequestHandler):
    """A media server's file download: the token required, byte ranges served (ffmpeg seeks with them)."""

    files = {}
    seen = []

    def do_GET(self):
        Ranged.seen.append(dict(self.headers))
        if self.headers.get("X-Plex-Token") != TOKEN:
            self.send_response(401)
            self.end_headers()
            return
        data = Ranged.files.get(urllib.parse.urlsplit(self.path).path)
        if data is None:
            self.send_response(404)
            self.end_headers()
            return
        first, last = 0, len(data) - 1
        wanted = self.headers.get("Range", "")
        if wanted.startswith("bytes="):
            a, _, b = wanted[6:].partition("-")
            first, last = int(a or 0), min(
                int(b) if b else len(data) - 1, len(data) - 1
            )
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {first}-{last}/{len(data)}")
        else:
            self.send_response(200)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(last - first + 1))
        self.send_header("Content-Type", "video/x-matroska")
        self.end_headers()
        try:
            self.wfile.write(data[first : last + 1])
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *args):
        pass


def make_film(folder):
    """Forty seconds of test picture and tone with an embedded SubRip track."""
    import shutil
    import subprocess

    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg is not installed")
    subs = folder / "lines.srt"
    subs.write_text(
        "1\n00:00:05,000 --> 00:00:07,000\nThe ferry leaves at noon.\n\n"
        "2\n00:00:30,000 --> 00:00:33,000\nI'll always love you, no matter what.\n\n"
        "3\n00:00:36,000 --> 00:00:38,000\nPromise me.\n",
        encoding="utf-8",
    )
    film = folder / "film.mkv"
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=64x48:rate=5:duration=40",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=40", "-i", str(subs),
         "-map", "0:v", "-map", "1:a", "-map", "2:s", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
         "-c:s", "srt", str(film)],
        check=True,
    )  # fmt: skip
    return film.read_bytes()


@pytest.fixture
def ranged(tmp_path):
    Ranged.files, Ranged.seen = {"/library/parts/1/1/file.mkv": make_film(tmp_path)}, []
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Ranged)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def test_embedded_subtitles_are_read_from_the_film_itself(companion, ranged):
    c = connect(companion, ranged)
    track = wa.Track()
    track.live = True
    plan = {"read": {"path": "/library/parts/1/1/file.mkv", "index": 2, "kbps": 500}}
    reader = wa.Reader(c, plan, track, start_ms=0, realtime=False)
    reader.begin_ms = (
        25_000  # from just before the line, as the follower would with its lead
    )
    assert "-re" not in reader.command("http://x") and "0:2" in reader.command(
        "http://x"
    )
    reader.start()
    reader.join(60)
    assert not reader.error, reader.error
    texts = [(cue.end, cue.text) for cue in track.ended_between(0, 10**9)]
    assert (
        33_000,
        "I'll always love you, no matter what.",
    ) in texts  # on the film's own clock
    assert (38_000, "Promise me.") in texts
    assert all(
        h.get("X-Plex-Token") == TOKEN for h in Ranged.seen
    )  # the relay added the token itself
    assert all(
        TOKEN not in arg for arg in reader.command(reader.c.media_server)
    )  # never on a command line


def test_a_film_without_text_subtitles_is_listened_to(
    companion, ranged, tmp_path, monkeypatch
):
    c = connect(companion, ranged)
    # A stand-in for the speech model: one line per chunk, on the film's clock.
    fake = tmp_path / "fake_worker.py"
    fake.write_text(
        "import json, sys\n"
        "print(json.dumps({'ready': True}), flush=True)\n"
        "while True:\n"
        "    head = sys.stdin.buffer.readline()\n"
        "    if not head: break\n"
        "    meta = json.loads(head); sys.stdin.buffer.read(meta['bytes'])\n"
        "    cue = {'start': meta['offset_ms'] + 1000, 'end': meta['offset_ms'] + 2500, 'text': 'heard at %d' % meta['offset_ms']}\n"
        "    print(json.dumps({'offset_ms': meta['offset_ms'], 'cues': [cue]}), flush=True)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(wa, "WORKER", fake)
    transcriber = wa.Transcriber(sys.executable)
    track = wa.Track()
    track.live = True
    reader = wa.Reader(c, {"read": {"path": "/library/parts/1/1/file.mkv", "index": None}}, track, 0,
                       transcriber, realtime=False)  # fmt: skip
    reader.begin_ms = 4_000
    reader.start()
    reader.join(60)
    transcriber.close()
    assert not reader.error, reader.error
    texts = [cue.text for cue in track.ended_between(0, 10**9)]
    assert texts[:2] == [
        "heard at 4000",
        "heard at 16000",
    ]  # twelve-second chunks, from where it began


def test_the_real_speech_model_hears_nothing_in_a_tone(companion, ranged):
    c = connect(companion, ranged)
    python = wa.listen_python(c)
    if not python:
        pytest.skip("no interpreter with faster_whisper here")
    transcriber = wa.Transcriber(python)
    try:
        assert (
            transcriber(0, b"\0\0" * 16000 * 3) == []
        )  # three seconds of silence: no invented line
    finally:
        transcriber.close()


def test_reading_is_refused_when_it_would_crowd_the_network(
    companion, server, monkeypatch
):
    c = connect(companion, server)
    # ffmpeg is pinned both ways, so the answer never depends on what the test machine has installed.
    monkeypatch.setattr(wa.shutil, "which", lambda name, *a, **k: f"/usr/bin/{name}")
    ok, why = wa.can_read(
        c,
        {
            "why": "it has no text subtitles",
            "read": {"path": "/x", "index": 2, "kbps": 60_000},
        },
    )
    assert not ok and "too heavy" in why
    ok, _ = wa.can_read(
        c, {"why": "", "read": {"path": "/x", "index": 2, "kbps": 8_000}}
    )
    assert ok
    monkeypatch.setattr(wa, "listen_python", lambda _c: "")
    ok, why = wa.can_read(
        c,
        {
            "why": "it has no text subtitles",
            "read": {"path": "/x", "index": None, "kbps": 8000},
        },
    )
    assert not ok and "speech model" in why
    monkeypatch.setattr(wa.shutil, "which", lambda name, *a, **k: None)
    ok, why = wa.can_read(
        c,
        {
            "why": "it has no text subtitles",
            "read": {"path": "/x", "index": 2, "kbps": 8000},
        },
    )
    assert not ok and "ffmpeg is not installed" in why
