#!/usr/bin/env python3
"""Watching together, live: she follows what the human is watching, line by line, and now and then says something.

Someone on the couch knows the scene: not the episode's synopsis, the line that was just said. While the human plays
a film or an episode on their own Plex or Jellyfin server, this follows its dialogue in step with playback:

- the title's text subtitles are read once (a sidecar file on Plex; any text track on Jellyfin, which extracts
  embedded ones itself) and cached;
- the playhead comes from the server every few seconds and is carried forward in between, so a line is known
  within a second or two of being spoken; a jump of more than a few seconds is a seek, and lines skipped over are
  never reacted to;
- what was just said (the last minute or so, never anything ahead of the playhead: she cannot spoil what she has
  not seen) is kept in `ambient/scene.json`, so whatever channel the human talks to her on, she knows the scene;
- at lines that land (a confession, a goodbye, a promise, a gasp in the audience track), and as often as the
  `watchalong` setting allows, she is asked, in a small call of her own chat model, whether she would say anything
  right now. She may stay silent. What she says reaches the human where `watchalong_reach` says: where they last
  talked, the watch or a wearable (a device bridge), a chat, or the TV itself on Jellyfin.

Every reaction is kept in `companion-life/watchalong.jsonl` and shown to her in later turns, so "remember when you
buzzed me during that scene" is something she knows. Nothing here writes to the media server except Jellyfin's own
on-screen message, and only when "screen" is chosen. Titles and lines reach her model provider like the rest of her
context, which the setting says.
"""

from __future__ import annotations
import argparse
import bisect
import dataclasses
import datetime as dt
import glob
import html
import http.server
import json
import os
import shutil
import subprocess
import pathlib
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

import companion_config as cc
import companion_platform as cp

MODES = ("off", "quiet", "moments", "occasional", "commentary", "auto")
REACH = ("last", "watch", "wearable", "telegram", "screen")
SCOPES = ("anything", "together")
# How often she may speak up on her own, by mode: the weakest line worth asking about, the shortest gap between two
# things she says, a ceiling per hour, and, when nothing has stood out for that long, a quieter line is enough.
PACE = {
    "moments": {"threshold": 6, "gap_s": 20 * 60, "per_hour": 2, "lull_s": None},
    "occasional": {"threshold": 4, "gap_s": 9 * 60, "per_hour": 4, "lull_s": 25 * 60},
    "commentary": {"threshold": 2, "gap_s": 150, "per_hour": 14, "lull_s": 6 * 60},
}
READ_PLAYING_S = 5  # how often the server is asked where the playhead is
READ_PAUSED_S = 20
READ_IDLE_S = 45
# Players report their position to the server every few seconds (about ten for most), so a report can be that
# stale. A jump past this from the carried-forward estimate is a seek; a smaller drift is resynchronised.
SEEK_MS = 15_000
BEHIND_MS = 3000  # the server behind the estimate by more than this, twice running: a short skip back
WINDOW_MS = 75_000  # what she is shown of what was just said
OPENING_MS = 120_000  # no reactions in the first two minutes (logos, cold opens)
CLOSING_MS = 360_000  # nor in the last six (credits)
SCENE_FRESH_S = 120  # older than this, the scene is not "now" any more
SCENE_PAUSED_FRESH_S = 20 * 60
SAY_CHARS = 120
BUZZES = ("tap", "message", "nudge")
SUB_CACHE_KEEP = 40
# Reading the film itself, for embedded subtitles or, with no text track at all, its sound: at the film's own pace,
# from a little ahead of the playhead (lines arrive before they are spoken and are handed out only once they have
# been). A heavier file than this (a 4K remux) would crowd the human's own stream on the network; it is not read.
MAX_READ_KBPS = 20_000
LEAD_MS = {"subtitles": 20_000, "listen": 26_000}
LISTEN_CHUNK_S = 12
PAUSE_STOP_S = (
    90  # paused this long, the reader stops; it starts again where the film resumes
)
WORKER = pathlib.Path(__file__).with_name("companion_listen_worker.py")
TEXT_CODECS = {
    "srt",
    "subrip",
    "ass",
    "ssa",
    "webvtt",
    "vtt",
    "mov_text",
    "text",
    "smi",
    "ttml",
}

# A line that lands, by what it is. Weights add up; a strong pattern alone reaches "occasional", two weak ones do not.
LANDS = [
    (re.compile(r"\bi love (you|u)\b", re.I), 6, "a confession"),
    (re.compile(r"\blove (you|u)\b", re.I), 3, "love"),
    (re.compile(r"\b(i'?ll|i will|i'?m going to) always\b", re.I), 4, "a promise"),
    (re.compile(r"\bno matter what\b", re.I), 4, "a promise"),
    (re.compile(r"\b(marry me|will you marry)\b", re.I), 7, "a proposal"),
    (re.compile(r"\b(promise me|i promise)\b", re.I), 4, "a promise"),
    (re.compile(r"\b(i'?m|i am) (so |really )?sorry\b", re.I), 3, "an apology"),
    (re.compile(r"\b(goodbye|farewell)\b", re.I), 3, "a goodbye"),
    (re.compile(r"\bdon'?t (leave|go)\b", re.I), 4, "a plea"),
    (re.compile(r"\b(i )?miss(ed)? you\b", re.I), 4, "longing"),
    (re.compile(r"\bi hate you\b", re.I), 4, "a fight"),
    (re.compile(r"\b(you complete me|you'?re the one|be mine)\b", re.I), 5, "romance"),
    (re.compile(r"\b(kiss|kissed|kissing)\b", re.I), 3, "a kiss"),
    (re.compile(r"\b(die|dying|dead|killed|kill)\b", re.I), 2, "death"),
    (re.compile(r"\b(trust me|believe me)\b", re.I), 2, "trust"),
    (re.compile(r"\b(beautiful|gorgeous|handsome)\b", re.I), 2, "admiration"),
    (re.compile(r"\b(forever|always|never)\b", re.I), 1, "forever"),
    (re.compile(r"\b(home|family)\b", re.I), 1, "home"),
    (
        re.compile(r"\b(oh my god|what the hell|holy (shit|crap)|no way)\b", re.I),
        2,
        "shock",
    ),
    (re.compile(r"!{2,}|\?!"), 1, "a shout"),
]
# What the hearing-impaired track says happened: often the best moment of all.
AUDIENCE = re.compile(
    r"^[\[(]\s*(laugh|laughs|laughing|screams?|screaming|gasps?|crying|sobbing|sobs|explosion|gunshots?|"
    r"thunder|crash|groans?|moans?|sighs?|whispers?|kiss(es|ing)?)\b",
    re.I,
)


@dataclasses.dataclass(frozen=True)
class Cue:
    start: int  # ms
    end: int
    text: str


def _ms(stamp):
    """00:01:02,345 / 01:02.345 / 1:02:03.4 -> milliseconds."""
    stamp = stamp.strip().replace(",", ".")
    parts = stamp.split(":")
    seconds = float(parts[-1])
    minutes = int(parts[-2]) if len(parts) > 1 else 0
    hours = int(parts[-3]) if len(parts) > 2 else 0
    return int(round(((hours * 60 + minutes) * 60 + seconds) * 1000))


_TIMING = re.compile(
    r"(?P<a>\d{1,2}:\d{2}(?::\d{2})?[.,]\d{1,3}|\d{1,2}:\d{2}:\d{2})\s*-->\s*"
    r"(?P<b>\d{1,2}:\d{2}(?::\d{2})?[.,]\d{1,3}|\d{1,2}:\d{2}:\d{2})"
)
_TAGS = re.compile(r"<[^>]{0,200}>|\{\\[^}]{0,200}\}")


def clean(text):
    """One cue's words: markup gone, entities read, a speaker's dash kept, one line."""
    text = html.unescape(_TAGS.sub("", text or ""))
    text = text.replace("\\N", " ").replace("\\n", " ")
    return " ".join(text.split())


def parse_subtitles(raw):
    """SubRip or WebVTT text -> sorted cues. Malformed blocks are skipped, never fatal."""
    raw = (raw or "").lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    cues = []
    for block in re.split(r"\n\s*\n", raw):
        lines = [line for line in block.split("\n") if line.strip()]
        for i, line in enumerate(lines):
            match = _TIMING.search(line)
            if not match:
                continue
            try:
                start, end = _ms(match["a"]), _ms(match["b"])
            except ValueError:
                break
            text = clean(" ".join(lines[i + 1 :]))
            if text and end >= start:
                cues.append(Cue(start, max(end, start + 1), text))
            break
    cues.sort(key=lambda cue: (cue.start, cue.end))
    return cues


class Track:
    """One title's dialogue, by the time each line ends. A reader may add lines while it is followed (they arrive a
    little ahead of the playhead); everything handed out stops at the playhead."""

    def __init__(self, cues=(), source="subtitles"):
        self.lock = threading.Lock()
        self.cues = sorted(cues, key=lambda cue: (cue.end, cue.start))
        self.ends = [cue.end for cue in self.cues]
        self.source = source if self.cues else ""
        self.live = False  # a reader is adding lines

    def __bool__(self):
        return bool(self.cues) or self.live

    def add(self, cues, source):
        with self.lock:
            for cue in cues:
                if cue.end in self.ends:
                    at = bisect.bisect_left(self.ends, cue.end)
                    if any(c.text == cue.text for c in self.cues[at : at + 4]):
                        continue  # a restarted reader repeats a line or two
                at = bisect.bisect_right(self.ends, cue.end)
                self.cues.insert(at, cue)
                self.ends.insert(at, cue.end)
            self.source = self.source or source

    def ended_between(self, after_ms, until_ms):
        """Lines that finished being said in (after, until]: what the human just heard."""
        with self.lock:
            lo = bisect.bisect_right(self.ends, after_ms)
            hi = bisect.bisect_right(self.ends, until_ms)
            return self.cues[lo:hi]

    def window(self, until_ms, span_ms=WINDOW_MS):
        """What was said in the last span, up to the playhead and never past it."""
        with self.lock:
            hi = bisect.bisect_right(self.ends, until_ms)
            out = []
            for cue in reversed(self.cues[:hi]):
                if cue.end < until_ms - span_ms:
                    break
                out.append(cue)
            return list(reversed(out))


def score(cue, position_ms, length_ms):
    """How much a just-heard line lands, and what it is. 0 inside the opening and the credits."""
    if position_ms < OPENING_MS or (length_ms and position_ms > length_ms - CLOSING_MS):
        return 0, ""
    text = cue.text
    total, kinds = 0, []
    if AUDIENCE.search(text):
        total += 3
        kinds.append("a reaction in the room")
    for pattern, weight, kind in LANDS:
        if pattern.search(text):
            total += weight
            if kind not in kinds:
                kinds.append(kind)
    words = len(re.findall(r"[\w']+", text))
    if words < 3 and total < 5 and not AUDIENCE.search(text):
        total = min(total, 1)
    return total, ", ".join(kinds[:2])


# ---- where things live -------------------------------------------------------------------------------------------
def scene_path(c):
    return c.soul_dir / "ambient" / "scene.json"


def scene_md_path(c):
    return c.soul_dir / "ambient" / "scene.md"


def log_path(c):
    return c.life / "watchalong.jsonl"


def cache_dir(c):
    return pathlib.Path(c.home) / "cache" / "watchalong"


def mode_of(c):
    """The pace in force: `auto` is "occasional" on a hosted chat model and "commentary" on a local one."""
    mode = getattr(c, "watchalong", "off") or "off"
    if mode != "auto":
        return mode
    try:
        import companion_inference as inference
        import companion_worker_model as worker_model

        return (
            "commentary"
            if inference.is_local(worker_model.resolve(c, "chat"))
            else "occasional"
        )
    except (ValueError, ImportError, OSError, KeyError):
        return "occasional"


def enabled(c):
    import companion_viewing as viewing

    return (
        (getattr(c, "watchalong", "off") or "off") != "off"
        and viewing.any_configured(c)
        and "viewing" in (c.sensors or [])
    )


# ---- the server: playhead and subtitles --------------------------------------------------------------------------
def _raw(c, path, timeout=20):
    """One GET of a non-JSON body (a subtitle file), the token in a header."""
    import companion_viewing as viewing

    token = viewing._token(c)
    if not token:
        raise ValueError("the media server token is missing or unreadable")
    headers = _headers(c, token)
    request = urllib.request.Request(
        c.media_server.rstrip("/") + path,
        headers={**headers, "User-Agent": "tamanitomo"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(8_000_000)
    except urllib.error.HTTPError as exc:
        raise ValueError(f"{viewing.source_name(c)} answered {exc.code}") from None
    except (urllib.error.URLError, OSError) as exc:
        raise ValueError(
            f"could not reach {viewing.source_name(c)}: {getattr(exc, 'reason', exc)}"
        ) from None
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return body.decode(encoding)
        except UnicodeDecodeError:
            continue
    return body.decode("utf-8", "replace")


def _headers(c, token):
    if c.media_kind == "plex":
        return {
            "X-Plex-Token": token,
            "X-Plex-Product": "Tamanitomo",
            "X-Plex-Client-Identifier": "tamanitomo",
        }
    # Jellyfin 12 turned the legacy token headers off by default: the full MediaBrowser form works everywhere.
    return {
        "Authorization": (
            f'MediaBrowser Client="Tamanitomo", Device="companion", DeviceId="tamanitomo", '
            f'Version="1", Token="{token}"'
        )
    }


def _post(c, path, body, timeout=8):
    """One POST (Jellyfin's on-screen message). Returns the HTTP status."""
    import companion_viewing as viewing

    token = viewing._token(c)
    if not token:
        raise ValueError("the media server token is missing or unreadable")
    request = urllib.request.Request(
        c.media_server.rstrip("/") + path,
        data=json.dumps(body).encode(),
        headers={
            **_headers(c, token),
            "Content-Type": "application/json",
            "User-Agent": "tamanitomo",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (urllib.error.URLError, OSError):
        return 0


def playing(c):
    """What the human plays now, on any server followed, with the playhead: a list of dicts (usually one), each
    tagged with the server it is on ("base"). A server that cannot be read leaves the others standing.
    """
    import companion_viewing as viewing

    out, errors, tried = [], [], 0
    for view in viewing.servers(c):
        if not viewing._token(view):
            continue
        tried += 1
        try:
            out += [{**row, "base": view.media_server} for row in _playing_one(view)]
        except ValueError as exc:
            errors.append(str(exc))
    if tried and len(errors) == tried:
        raise ValueError("; ".join(errors))
    return out


def _playing_one(c):
    """What the human plays now on one server."""
    import companion_viewing as viewing

    if c.media_kind == "plex":
        account = viewing._plex_account(c)
        container = (viewing._get(c, "/status/sessions") or {}).get(
            "MediaContainer"
        ) or {}
        out = []
        for row in container.get("Metadata") or []:
            user = row.get("User") or {}
            mine = str(user.get("id")) == account or (
                c.media_user
                and str(user.get("title") or "").casefold() == c.media_user.casefold()
            )
            item = viewing._plex_item(row) if mine else None
            if not item:
                continue
            player = row.get("Player") or {}
            state = str(player.get("state") or "playing")
            selected = None
            for media in row.get("Media") or []:
                for part in media.get("Part") or []:
                    for stream in part.get("Stream") or []:
                        if stream.get("streamType") == 3 and stream.get("selected"):
                            selected = str(stream.get("id"))
            out.append(
                {
                    **item,
                    "server": "plex",
                    "position_ms": int(row.get("viewOffset") or 0),
                    "length_ms": int(row.get("duration") or 0) or None,
                    "state": (
                        state
                        if state in ("playing", "paused", "buffering")
                        else "playing"
                    ),
                    "session": str(
                        (row.get("Session") or {}).get("id")
                        or row.get("sessionKey")
                        or ""
                    ),
                    "client": str(player.get("title") or player.get("product") or ""),
                    "can_message": False,
                    "subtitle_stream": selected,
                    "media_source": None,
                    "summary": str(row.get("summary") or "").strip(),
                }
            )
        return out
    user, _ = viewing._jellyfin_user(c)
    rows = viewing._get(c, "/Sessions", [("activeWithinSeconds", 120)]) or []
    out = []
    for row in rows:
        if str(row.get("UserId") or "") != str(user) or not row.get("NowPlayingItem"):
            continue
        now_item = row["NowPlayingItem"]
        item = viewing._jellyfin_item(now_item)
        if not item:
            continue
        play = row.get("PlayState") or {}
        commands = row.get("SupportedCommands") or []
        out.append(
            {
                **item,
                "server": "jellyfin",
                "position_ms": int(play.get("PositionTicks") or 0) // 10_000,
                "length_ms": int(now_item.get("RunTimeTicks") or 0) // 10_000 or None,
                "state": "paused" if play.get("IsPaused") else "playing",
                "session": str(row.get("Id") or ""),
                "client": str(row.get("DeviceName") or row.get("Client") or ""),
                "can_message": bool(row.get("SupportsRemoteControl"))
                or "DisplayMessage" in commands,
                "subtitle_stream": (
                    str(play["SubtitleStreamIndex"])
                    if isinstance(play.get("SubtitleStreamIndex"), int)
                    else None
                ),
                "media_source": str(
                    play.get("MediaSourceId") or now_item.get("Id") or ""
                ),
                "streams": now_item.get("MediaStreams") or [],
                "summary": str(now_item.get("Overview") or "").strip(),
            }
        )
    return out


def _choose(streams, selected, language="en"):
    """The subtitle stream to follow: the one being shown if it is text, else a full (not forced) track in the
    companion's language, else any full text track. A forced track carries only foreign-language lines.
    """

    def text(s):
        return s["text"]

    usable = [s for s in streams if text(s)]
    by_id = {s["id"]: s for s in usable}
    if selected and selected in by_id and not by_id[selected]["forced"]:
        return by_id[selected]
    lang = (language or "en")[:2].lower()
    full = [s for s in usable if not s["forced"]]
    for pool in (
        [s for s in full if s["lang"][:2] == lang and not s["hi"]],
        [s for s in full if s["lang"][:2] == lang],
        full,
    ):
        if pool:
            return pool[0]
    return None


def dialogue(c, now_playing):
    """How this title's dialogue can be followed:
    {"raw": subtitle text or None, "stream": its id, "why": why not, "read": a plan to read the film itself or None}.
    A read plan is {"path", "index"} (index: the container's subtitle stream, or None to listen) plus "kbps".
    """
    plan = {"raw": None, "stream": None, "why": "", "read": None}
    language = getattr(c, "language", "en")
    if now_playing["server"] == "plex":
        import companion_viewing as viewing

        container = (
            viewing._get(
                c, f"/library/metadata/{urllib.parse.quote(now_playing['key'])}"
            )
            or {}
        ).get("MediaContainer") or {}
        rows = container.get("Metadata") or [{}]
        medias = rows[0].get("Media") or [{}]
        media = medias[0]
        part = (media.get("Part") or [{}])[0]
        streams = []
        for s in part.get("Stream") or []:
            if s.get("streamType") != 3:
                continue
            streams.append(
                {
                    "id": str(s.get("id")),
                    "index": s.get("index"),
                    "text": str(s.get("codec") or "").lower() in TEXT_CODECS,
                    "sidecar": bool(s.get("key")),
                    "forced": bool(s.get("forced")),
                    "hi": bool(s.get("hearingImpaired")),
                    "lang": str(s.get("languageCode") or s.get("language") or ""),
                }
            )
        # Plex serves only sidecar text tracks as files; an embedded track answers 501.
        chosen = _choose(
            [s for s in streams if s["sidecar"]],
            now_playing.get("subtitle_stream"),
            language,
        )
        if chosen:
            plan["raw"] = _cached(
                c,
                f"plex-{now_playing['key']}-{chosen['id']}",
                lambda: _raw(c, f"/library/streams/{chosen['id']}.srt?format=srt"),
            )
            plan["stream"] = chosen["id"]
            return plan
        embedded = _choose(
            [s for s in streams if not s["sidecar"]],
            now_playing.get("subtitle_stream"),
            language,
        )
        kbps = int(media.get("bitrate") or 0)
        plan["why"] = (
            "its subtitles are inside the video file, which Plex does not hand out"
            if embedded
            else "it has no text subtitles"
        )
        if part.get("key"):
            index = embedded.get("index") if embedded else None
            plan["read"] = {
                "path": part["key"],
                "index": index if isinstance(index, int) else None,
                "kbps": kbps,
            }
        return plan
    streams = [
        {
            "id": str(s.get("Index")),
            "text": bool(s.get("IsTextSubtitleStream")),
            "sidecar": bool(s.get("IsExternal")),
            "forced": bool(s.get("IsForced")),
            "hi": bool(s.get("IsHearingImpaired")),
            "lang": str(s.get("Language") or ""),
        }
        for s in now_playing.get("streams") or []
        if s.get("Type") == "Subtitle" and s.get("Index") is not None
    ]
    item, source = (
        now_playing["key"],
        now_playing.get("media_source") or now_playing["key"],
    )
    chosen = _choose(streams, now_playing.get("subtitle_stream"), language)
    if chosen:
        path = f"/Videos/{urllib.parse.quote(item)}/{urllib.parse.quote(source)}/Subtitles/{chosen['id']}/Stream.srt"
        plan["raw"] = _cached(
            c, f"jellyfin-{item}-{chosen['id']}", lambda: _raw(c, path, timeout=60)
        )
        plan["stream"] = chosen["id"]
        return plan
    plan["why"] = "it has no text subtitles"
    plan["read"] = {
        "path": f"/Videos/{urllib.parse.quote(item)}/stream?static=true&mediaSourceId={urllib.parse.quote(source)}",
        "index": None,
        "kbps": int(now_playing.get("kbps") or 0),
    }
    return plan


def subtitles(c, now_playing):
    """(raw text, stream id) for the title being played, or (None, why not)."""
    plan = dialogue(c, now_playing)
    return (plan["raw"], plan["stream"]) if plan["raw"] else (None, plan["why"])


def _cached(c, name, fetch):
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", name)[:120] + ".srt"
    folder = cache_dir(c)
    path = folder / safe
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        pass
    text = fetch()
    try:
        folder.mkdir(parents=True, exist_ok=True)
        cp.atomic_write(path, text)
        old = sorted(folder.glob("*.srt"), key=lambda p: p.stat().st_mtime)
        for stale in old[:-SUB_CACHE_KEEP]:
            stale.unlink(missing_ok=True)
    except OSError:
        pass
    return text


# ---- reading the film itself ---------------------------------------------------------------------------------------
class _RelayHandler(http.server.BaseHTTPRequestHandler):
    def _forward(self, body):
        relay = self.server.relay
        if self.path != relay.secret:
            self.send_error(404)
            return
        headers = dict(relay.headers)
        if self.headers.get("Range"):
            headers["Range"] = self.headers["Range"]
        request = urllib.request.Request(
            relay.upstream, headers=headers, method="GET" if body else "HEAD"
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as upstream:
                self.send_response(upstream.status)
                for name in (
                    "Content-Type",
                    "Content-Length",
                    "Content-Range",
                    "Accept-Ranges",
                ):
                    if upstream.headers.get(name):
                        self.send_header(name, upstream.headers[name])
                self.end_headers()
                while body:
                    chunk = upstream.read(1 << 16)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except urllib.error.HTTPError as exc:
            self.send_error(exc.code)
        except (OSError, ConnectionError):
            pass

    def do_GET(self):
        self._forward(True)

    def do_HEAD(self):
        self._forward(False)

    def log_message(self, *args):
        pass


class Relay:
    """The film, on this machine only, for ffmpeg: it adds the server's token itself, so the token never sits in a
    process's arguments (which other users of the machine can read). A random path, gone when closed.
    """

    def __init__(self, upstream, headers):
        self.upstream, self.headers = upstream, headers
        self.secret = "/" + uuid.uuid4().hex
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _RelayHandler)
        self.httpd.daemon_threads = True
        self.httpd.relay = self
        threading.Thread(
            target=self.httpd.serve_forever, name="watchalong-relay", daemon=True
        ).start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.httpd.server_address[1]}{self.secret}"

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


_listen_python = {}


def listen_python(c):
    """An interpreter that has faster_whisper and numpy (Hermes installs one for its own voice transcription), or "".
    TAMANITOMO_LISTEN_PYTHON names one directly."""
    root = str(c.hermes_root)
    if root in _listen_python:
        return _listen_python[root]
    named = os.environ.get("TAMANITOMO_LISTEN_PYTHON", "")
    candidates = [named] if named else []
    candidates += sorted(
        glob.glob(
            os.path.join(
                root, "installs", "*", "environments", "*", "venv", "bin", "python"
            )
        ),
        key=lambda path: os.path.getmtime(path),
        reverse=True,
    )
    found = ""
    for python in candidates:
        try:
            done = subprocess.run(
                [python, "-c", "import faster_whisper, numpy"],
                capture_output=True,
                timeout=60,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if done.returncode == 0:
            found = python
            break
    _listen_python[root] = found
    return found


class Transcriber:
    """companion_listen_worker.py in its own process: PCM chunks in, lines on the film's clock out."""

    def __init__(self, python, model="small.en", language="en", timeout=180):
        self.proc = subprocess.Popen(
            [python, str(WORKER), model, language],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + timeout
        line = b""
        while time.time() < deadline and not line:
            line = self.proc.stdout.readline()
        if not line or not json.loads(line).get("ready"):
            self.close()
            raise ValueError("the speech model did not start")

    def __call__(self, offset_ms, pcm):
        header = (
            json.dumps({"offset_ms": int(offset_ms), "bytes": len(pcm)}).encode()
            + b"\n"
        )
        self.proc.stdin.write(header + pcm)
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise ValueError("the speech model stopped")
        rows = json.loads(line).get("cues") or []
        return [
            Cue(int(r["start"]), int(r["end"]), clean(r["text"]))
            for r in rows
            if clean(r.get("text"))
        ]

    def close(self):
        try:
            self.proc.kill()
        except OSError:
            pass


def can_read(c, plan):
    """(True, "") when the film itself can be read for this plan, else (False, why not)."""
    read = (plan or {}).get("read")
    if not read:
        return False, (plan or {}).get("why") or "it has no text subtitles"
    if not shutil.which("ffmpeg"):
        return False, plan["why"] + ", and ffmpeg is not installed here to read it"
    if read.get("kbps") and read["kbps"] > MAX_READ_KBPS:
        return (
            False,
            plan["why"]
            + ", and the file is too heavy to read alongside your own stream",
        )
    if read.get("index") is None and not listen_python(c):
        return False, plan["why"] + ", and no speech model is installed to listen to it"
    return True, ""


class Reader(threading.Thread):
    """ffmpeg reading the film at its own pace from a little ahead of the playhead: its embedded subtitle track, or
    its sound for the speech model. Lines go into the track as they come."""

    def __init__(self, c, plan, track, start_ms, transcriber=None, realtime=True):
        super().__init__(name="watchalong-reader", daemon=True)
        self.realtime = (
            realtime  # at the film's own pace; tests read as fast as they can
        )
        self.c, self.read, self.track = c, plan["read"], track
        self.mode = "subtitles" if self.read.get("index") is not None else "listen"
        self.begin_ms = max(0, int(start_ms) + LEAD_MS[self.mode])
        self.transcriber = transcriber
        self.proc = None
        self.stopped = threading.Event()
        self.error = ""

    def command(self, url):
        head = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", *(["-re"] if self.realtime else []),
                "-ss", f"{self.begin_ms / 1000:.3f}", "-i", url]  # fmt: skip
        if self.mode == "subtitles":
            # -copyts: lines keep the film's own clock. Without it, how far they are shifted depends on where
            # the seek landed (the keyframe before it), not on the position asked for.
            return head[:-2] + ["-copyts"] + head[-2:] + [
                "-map", f"0:{self.read['index']}", "-c:s", "srt", "-f", "srt", "pipe:1"]  # fmt: skip
        return head + [
            "-map",
            "0:a:0",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "s16le",
            "pipe:1",
        ]

    def run(self):
        import companion_viewing as viewing

        relay = None
        try:
            token = viewing._token(self.c)
            relay = Relay(
                self.c.media_server.rstrip("/") + self.read["path"],
                _headers(self.c, token),
            )
            self.proc = subprocess.Popen(
                self.command(relay.url),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            if self.mode == "subtitles":
                self._subtitles()
            else:
                self._listen()
        except (
            Exception
        ) as exc:  # noqa: BLE001 -- a reader that fails leaves the track as it is
            self.error = str(exc)[:200]
        finally:
            if self.proc and self.proc.poll() is None:
                self.proc.kill()
            if relay:
                relay.close()

    def _subtitles(self):
        block = []
        for raw in self.proc.stdout:
            if self.stopped.is_set():
                return
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if line.strip():
                block.append(line)
                continue
            if block:
                cues = parse_subtitles("\n".join(block))
                block = []
                self.track.add(
                    cues, "subtitles"
                )  # already on the film's clock (-copyts)

    def _listen(self):
        size = LISTEN_CHUNK_S * 16000 * 2
        offset = self.begin_ms
        while not self.stopped.is_set():
            pcm = b""
            while len(pcm) < size:
                chunk = self.proc.stdout.read(size - len(pcm))
                if not chunk:
                    break
                pcm += chunk
            if not pcm or self.stopped.is_set():
                return
            self.track.add(self.transcriber(offset, pcm), "listening")
            offset += len(pcm) // 32

    def stop(self):
        self.stopped.set()
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except OSError:
                pass


# ---- the clock between reads -------------------------------------------------------------------------------------
class Playhead:
    """Where the playhead is, carried forward between the server's reports; a jump is a seek.

    The server only knows what the player last told it, so the same position can come back several reads running
    while the film plays on: that is not a pause or a jump, and the estimate keeps running. A report ahead of the
    estimate is taken (the estimate was behind); one a little behind is an old report, unless it stays behind.
    """

    def __init__(self):
        self.reported_ms = 0
        self.reported_at = None
        self.state = "stopped"
        self.raw = None  # the last position the server said, as said
        self.behind = 0

    def _set(self, position_ms, state, at):
        self.reported_ms, self.reported_at, self.state = int(position_ms), at, state
        self.behind = 0

    def update(self, position_ms, state, at):
        """A fresh report. Returns True when it is a seek (or the first report)."""
        position_ms = int(position_ms)
        if self.reported_at is None:
            self.raw = position_ms
            self._set(position_ms, state, at)
            return True
        expected = self.estimate(at)
        unchanged = position_ms == self.raw
        self.raw = position_ms
        if state != "playing" or self.state != "playing":
            # Pausing, buffering, resuming: the server's position is exact at these moments.
            seek = abs(position_ms - expected) > SEEK_MS
            if not (unchanged and state == self.state == "playing"):
                self._set(position_ms, state, at)
            return seek
        if unchanged:
            return False  # nothing new from the player: keep running on
        delta = position_ms - expected
        if abs(delta) > SEEK_MS:
            self._set(position_ms, state, at)
            return True
        if delta >= 0:
            self._set(position_ms, state, at)
        elif -delta > BEHIND_MS:
            self.behind += 1
            if self.behind >= 2:
                self._set(position_ms, state, at)
        return False

    def estimate(self, at):
        if self.reported_at is None:
            return 0
        if self.state != "playing":
            return self.reported_ms
        return self.reported_ms + int(max(0.0, at - self.reported_at) * 1000)


# ---- her side: what she would say --------------------------------------------------------------------------------
def _mmss(ms):
    seconds = max(0, int(ms // 1000))
    hours, rest = divmod(seconds, 3600)
    return (
        f"{hours}:{rest // 60:02d}:{rest % 60:02d}"
        if hours
        else f"{rest // 60}:{rest % 60:02d}"
    )


def _who_she_is(c, limit=1600):
    """A short self: the start of her SOUL, her mood and stance now, and how close they are."""
    parts = []
    try:
        soul = (pathlib.Path(c.home) / "SOUL.md").read_text(encoding="utf-8")
        soul = re.sub(r"<!--.*?-->", "", soul, flags=re.S)
        parts.append(" ".join(soul.split())[:limit])
    except OSError:
        pass
    try:
        import companion_presence as presence

        scene = presence.current(c) or {}
        for key, label in (("mood", "Your mood"), ("stance", "Privately")):
            value = str(scene.get(key) or "").strip()
            if value:
                parts.append(f"{label}: {value[:240]}")
    except Exception:  # noqa: BLE001 -- a short self is still a self
        pass
    return "\n".join(parts)


def _title(now_playing):
    import companion_viewing as viewing

    return viewing.label(now_playing)


def prompt(c, now_playing, lines, trigger, said, reach_text):
    """The small request: who she is, what is on, what was just said, and the rule that silence is fine."""
    title = _title(now_playing)
    heard = "\n".join(
        (">> " if cue is trigger else "   ") + f"[{_mmss(cue.start)}] {cue.text}"
        for cue in lines
    )
    before = (
        "; ".join(
            f'"{row["said"]}" at {_mmss(row["position_ms"])}' for row in said[-3:]
        )
        or "nothing yet"
    )
    synopsis = (now_playing.get("summary") or "").strip()
    system = (
        f"You are {c.agent}. This is you:\n{_who_she_is(c)}\n\n"
        f"You and {c.human} are watching {title} together right now; you follow it line by line. Speak as yourself "
        f"to {c.human}, never as a narrator, a reviewer or an assistant."
    )
    user = (
        f"On now: {title}, {_mmss(now_playing.get('position_ms') or 0)}"
        + (
            f" of {_mmss(now_playing['length_ms'])}"
            if now_playing.get("length_ms")
            else ""
        )
        + (f". About it: {synopsis[:300]}" if synopsis else "")
        + f"\n\nJust said (oldest first; >> is the line that was just spoken"
        + (f", {trigger_kind(trigger)}" if trigger else "")
        + f"):\n{heard}\n\n"
        f"What you have said so far tonight: {before}.\n"
        f"It would reach {c.human} {reach_text}.\n\n"
        "Would you say something right now, as yourself, about what was just said? Only if you really would: "
        "most lines pass without a word. Never describe or guess what happens next; you only know what has been "
        "said up to this line. Keep it short and in your own voice (one line, "
        f"up to {SAY_CHARS} characters).\n"
        'Answer only JSON: {"say": "...", "buzz": "tap" | "message" | "nudge"} '
        "(tap: a light touch; message: an ordinary note; nudge: playful, an elbow in the ribs), "
        'or {"say": ""} to stay quiet.'
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def trigger_kind(cue):
    kind = score(cue, OPENING_MS, None)[1] if cue else ""
    return kind or "an ordinary line"


def parse_reply(content):
    """{"say", "buzz"} from her answer, or None for silence. Tolerates prose around the JSON."""
    content = (content or "").strip()
    if not content or content.upper().startswith("SILENT"):
        return None
    match = re.search(r"\{.*\}", content, re.S)
    try:
        data = json.loads(match.group(0)) if match else {}
    except ValueError:
        data = {}
    say = " ".join(str(data.get("say") or "").split()).strip().strip('"')[:SAY_CHARS]
    if not say or say.upper() == "SILENT":
        return None
    buzz = str(data.get("buzz") or "message").lower()
    return {"say": say, "buzz": buzz if buzz in BUZZES else "message"}


def ask(c, messages, timeout=45):
    """Her chat model, a small call: never Hermes's whole conversation, never a tool."""
    import companion_worker_model as worker_model

    route = worker_model.resolve(c, "chat")
    reply = worker_model.complete(
        c,
        {"messages": messages, "max_tokens": 200, "temperature": 0.8},
        route,
        timeout=timeout,
        what="Watching together",
        require_thinking=False,
    )
    return reply.get("content") or "", reply.get("model") or route.get("model")


# ---- reaching the human --------------------------------------------------------------------------------------------
def last_place(c):
    """Where the human last said something to her: "wearable" (a device keeping its own conversation through the
    app's chat, which names its place), "telegram", "app", "game" or "" (unknown). From the conversations her thread
    counts."""
    import companion_thread as thread

    found, _why = thread._store_scope(c)
    if not found:
        return ""
    resolved, scope, params = found
    try:
        con = sqlite3_connect(resolved)
        try:
            row = con.execute(
                thread._message_query(con, scope, "s.id,s.source,m.timestamp")
                + " AND m.role='user' ORDER BY m.timestamp DESC LIMIT 1",
                params,
            ).fetchone()
        finally:
            con.close()
    except Exception:  # noqa: BLE001 -- unknown is an answer
        return ""
    if not row:
        return ""
    session, source = str(row[0]), str(row[1] or "")
    try:
        sys.path.append(str(pathlib.Path(__file__).resolve().parents[2]))
        from kit.app import runtime

        placed = bool(runtime.read_workspace_places(c).get(session, ""))
    except Exception:  # noqa: BLE001
        placed = False
    if placed:
        return "wearable"
    if source == "telegram":
        return "telegram"
    if source == "api_server":
        return "game"
    return "app"


def sqlite3_connect(path):
    import sqlite3

    con = sqlite3.connect(
        pathlib.Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=1
    )
    con.execute("PRAGMA query_only=ON")
    return con


def targets(c, now_playing):
    """Where a reaction goes, in order, each at most once: the reach setting made concrete."""
    out = []
    for want in getattr(c, "watchalong_reach", None) or ["last", "watch"]:
        if want == "last":
            place = last_place(c)
            if place in ("wearable", "telegram"):
                want = place
            else:
                continue  # the game and the app's window have no way to be reached mid-film; the next choice does
        if want == "screen" and not now_playing.get("can_message"):
            continue
        if want in ("watch", "wearable") and not getattr(c, "device_bridge_url", ""):
            continue
        if want not in out:
            out.append(want)
    # A wearable's messages reach the watch too (the bridge mirrors them); asked for both, one to whichever is on.
    if "wearable" in out and "watch" in out:
        out.remove("wearable")
    return out


def reach_text(c, chosen):
    words = {
        "watch": "as a buzz and a few words on their watch",
        "wearable": "on the device they wear",
        "telegram": "as a chat message",
        "screen": "on the TV screen itself",
    }
    return (
        " and ".join(words[t] for t in chosen) or "nowhere (you can still say it later)"
    )


def _bridge_token(c):
    path = pathlib.Path(getattr(c, "device_bridge_token_file", "") or "")
    if not str(path):
        return ""
    if not path.is_absolute():
        path = pathlib.Path(c.home) / path
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def device_send(c, text, buzz, surface, ident):
    """POST {text, kind, surface, id} to the device bridge: (where it went, why not). Where is a list of places
    ("watch", "wearable"); why is "" when it went, "unreachable" when the bridge did not answer or refused, and
    "nothing connected" when it answered but had nothing of theirs to show it on."""
    url = getattr(c, "device_bridge_url", "")
    token = _bridge_token(c)
    if not url or not token:
        return [], "unreachable"
    request = urllib.request.Request(
        url,
        data=json.dumps(
            {"text": text, "kind": buzz, "surface": surface, "id": ident}
        ).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            body = json.loads(response.read(20000) or b"{}")
    except (urllib.error.URLError, OSError, ValueError):
        return [], "unreachable"
    places = [p for p in body.get("delivered") or [] if p != "nowhere"]
    return places, "" if places else "nothing connected"


def to_device(c, text, buzz, surface, ident):
    """POST {text, kind, surface, id} to the device bridge. Returns where it went, or ""."""
    return ",".join(device_send(c, text, buzz, surface, ident)[0])


def to_chat(c, text, platform="telegram"):
    """Right now through Hermes (`hermes send`), not the outbox: the outbox's dispatcher runs every five minutes,
    and a reaction five minutes late is about a different scene."""
    import companion_dispatch as dispatch

    try:
        ok, _detail = dispatch.hermes_send(c, text, platform)
    except (
        Exception
    ):  # noqa: BLE001 -- a failed send is reported, never raised into the follower
        return ""
    return platform if ok else ""


def to_screen(c, now_playing, text):
    status = _post(
        c,
        f"/Sessions/{urllib.parse.quote(now_playing['session'])}/Message",
        {"Header": c.agent, "Text": text, "TimeoutMs": 9000},
    )
    return "screen" if 200 <= status < 300 else ""


def deliver(c, now_playing, said):
    """Send what she said everywhere it goes. Returns the places it reached."""
    ident = "w-" + uuid.uuid4().hex[:12]
    reached = []
    for target in targets(c, now_playing):
        if target in ("watch", "wearable"):
            where = to_device(
                c,
                said["say"],
                said["buzz"],
                "auto" if target == "watch" else "wearable",
                ident,
            )
        elif target == "telegram":
            where = to_chat(c, said["say"])
        else:
            where = to_screen(c, now_playing, said["say"])
        if where:
            reached.append(where)
    return reached


# ---- the follower ------------------------------------------------------------------------------------------------
class Follower:
    """Follows one companion's human through whatever they play. `tick()` does one step and says when to come back."""

    def __init__(
        self, c, clock=time.time, read=playing, fetch=dialogue, speak=ask, send=deliver
    ):
        self.c = c
        self.clock = clock
        self.read, self.fetch, self.speak, self.send = read, fetch, speak, send
        self.item = None  # the title being followed: (kind, server address, key)
        self.view = c  # the companion as seen from the server that title is on
        self.track = Track([])
        self.track_note = ""
        self.head = Playhead()
        self.heard_ms = 0  # every line that ended at or before this has been considered
        self.now = None  # the latest report, with the carried-forward position
        self.said = []  # what she said during this title
        self.last_said_at = None
        self.loudest = (0, None)  # the best line since she last spoke: for a lull
        self.last_read = 0.0
        self.scene_written = 0.0
        self.plan = None  # how this title's dialogue is followed (dialogue())
        self.reader = None  # a Reader thread, while the film itself is read
        self.transcriber = None
        self.paused_since = None

    def pace(self):
        mode = mode_of(self.c)
        return mode, PACE.get(mode)

    def _together_ok(self, now_playing):
        if getattr(self.c, "watchalong_scope", "anything") != "together":
            return True
        import companion_viewing as viewing

        try:
            return any(
                s["state"] == "active"
                and viewing.matches(s.get("title") or "", now_playing)
                for s in viewing.active(self.c, dt.datetime.now(dt.timezone.utc))
            )
        except (OSError, ValueError, KeyError):
            return False

    def tick(self):
        at = self.clock()
        due = (
            READ_IDLE_S
            if self.now is None
            else (READ_PLAYING_S if self.head.state == "playing" else READ_PAUSED_S)
        )
        if at - self.last_read >= due or self.now is None:
            self.last_read = at
            try:
                rows = self.read(self.c)
            except ValueError:
                rows = []
            current = rows[0] if rows else None
            if not current:
                if self.now is not None:
                    self._finish()
                return READ_IDLE_S
            if (current["server"], current.get("base"), current["key"]) != self.item:
                self._start(current)
            first = self.head.reported_at is None
            seek = self.head.update(current["position_ms"], current["state"], at)
            self.now = current
            if seek:
                self.heard_ms = current[
                    "position_ms"
                ]  # lines skipped over are never reacted to
                if not first and self.reader is not None:
                    self._read_from(
                        current["position_ms"]
                    )  # read on from where the film is now
            self._mind_the_reader(at, current)
        if self.now is None:
            return READ_IDLE_S
        position = self.head.estimate(at)
        self.now = {**self.now, "position_ms": position, "state": self.head.state}
        fresh = (
            self.track.ended_between(self.heard_ms, position)
            if self.head.state == "playing"
            else []
        )
        self.heard_ms = (
            max(self.heard_ms, position)
            if self.head.state == "playing"
            else self.heard_ms
        )
        if fresh or at - self.scene_written >= 30:
            self._write_scene(at)
        if fresh:
            self._consider(fresh, at)
        return (
            1.0
            if self.head.state == "playing" and self.track
            else (READ_PLAYING_S if self.head.state == "playing" else READ_PAUSED_S)
        )

    def _start(self, current):
        self._stop_reader()
        self.item = (current["server"], current.get("base"), current["key"])
        import companion_viewing as viewing

        self.view = viewing.server_for(self.c, current)
        self.head = Playhead()
        self.said, self.last_said_at, self.loudest = [], None, (0, None)
        self.paused_since = None
        try:
            plan = self.fetch(self.view, current)
        except ValueError as exc:
            plan = {"raw": None, "why": str(exc), "read": None}
        if isinstance(plan, tuple):  # (raw, why), as a simple fetch says it
            plan = {"raw": plan[0], "why": "" if plan[0] else plan[1], "read": None}
        self.plan = plan
        self.track = Track(
            parse_subtitles(plan["raw"]) if plan.get("raw") else [], "subtitles"
        )
        self.track_note = ""
        how = "subtitles" if self.track.cues else ""
        if not self.track.cues:
            ok, why = can_read(self.view, plan)
            if ok:
                self.track.live = True
                how = (
                    "reading the film"
                    if plan["read"].get("index") is not None
                    else "listening"
                )
                self._read_from(current["position_ms"])
            else:
                self.track_note = why or "no subtitles"
        _log(
            self.c,
            {
                "event": "start",
                "title": _title(current),
                "server": current["server"],
                "dialogue": how,
                "why_not": self.track_note,
            },
        )

    def _read_from(self, position_ms):
        """(Re)start reading the film from where it is now."""
        self._stop_reader(keep_transcriber=True)
        read = (self.plan or {}).get("read")
        if not read:
            return
        try:
            if read.get("index") is None and self.transcriber is None:
                self.transcriber = Transcriber(listen_python(self.c))
        except (OSError, ValueError) as exc:
            self.track_note = f"the speech model could not start ({exc})"
            self.track.live = False
            return
        self.reader = Reader(
            self.view, self.plan, self.track, position_ms, self.transcriber
        )
        self.reader.start()

    def _stop_reader(self, keep_transcriber=False):
        if self.reader is not None:
            self.reader.stop()
            self.reader = None
        if not keep_transcriber and self.transcriber is not None:
            self.transcriber.close()
            self.transcriber = None

    def _mind_the_reader(self, at, current):
        """A long pause stops the reading; playing again starts it where the film is."""
        if not self.track.live:
            return
        if current["state"] != "playing":
            self.paused_since = self.paused_since or at
            if self.reader is not None and at - self.paused_since >= PAUSE_STOP_S:
                self._stop_reader(keep_transcriber=True)
            return
        self.paused_since = None
        if self.reader is None or not self.reader.is_alive():
            self._read_from(current["position_ms"])

    def _finish(self):
        self._stop_reader()
        if self.now is not None:
            _log(
                self.c,
                {
                    "event": "stop",
                    "title": _title(self.now),
                    "position_ms": self.now["position_ms"],
                    "said": len(self.said),
                },
            )
        self.now, self.item, self.track = None, None, Track([])
        self.head = Playhead()
        self._write_scene(self.clock(), gone=True)

    def _consider(self, fresh, at):
        mode, pace = self.pace()
        if not pace or not self._together_ok(self.now):
            return
        length = self.now.get("length_ms")
        best = max(
            ((score(cue, cue.end, length), cue) for cue in fresh),
            key=lambda row: row[0][0],
        )
        (points, _kind), cue = best
        if points > self.loudest[0]:
            self.loudest = (points, cue)
        since = (at - self.last_said_at) if self.last_said_at else None
        if since is not None and since < pace["gap_s"]:
            return
        hour_ago = [row for row in self.said if at - row["clock"] < 3600]
        if len(hour_ago) >= pace["per_hour"]:
            return
        # A long quiet stretch: the newest line is enough to ask about, if anything has been said worth a word.
        lull = (
            bool(pace["lull_s"])
            and (since is None or since >= pace["lull_s"])
            and cue.end > OPENING_MS
        )
        if points < pace["threshold"]:
            if not (lull and self.loudest[0] >= 1):
                return
            cue = fresh[-1]
        self.loudest = (0, None)
        chosen = targets(self.c, self.now)
        lines = self.track.window(cue.end)
        try:
            content, model = self.speak(
                self.c,
                prompt(
                    self.c, self.now, lines, cue, self.said, reach_text(self.c, chosen)
                ),
            )
        except (
            Exception
        ) as exc:  # noqa: BLE001 -- a failed call is a missed moment, never a stopped follower
            _log(
                self.c,
                {"event": "error", "title": _title(self.now), "error": str(exc)[:200]},
            )
            self.last_said_at = at  # do not hammer a failing provider at every line
            return
        reply = parse_reply(content)
        self.last_said_at = at
        if not reply:
            _log(
                self.c,
                {
                    "event": "silent",
                    "title": _title(self.now),
                    "position_ms": cue.end,
                    "line": cue.text[:200],
                },
            )
            return
        reached = self.send(self.view, self.now, reply) if chosen else []
        row = {
            "event": "said",
            "title": _title(self.now),
            "server": self.now["server"],
            "key": self.now["key"],
            "position_ms": cue.end,
            "line": cue.text[:200],
            "said": reply["say"],
            "buzz": reply["buzz"],
            "reached": reached,
            "model": model,
        }
        _log(self.c, row)
        self.said.append({**row, "clock": at})
        self._write_scene(at)

    def _write_scene(self, at, gone=False):
        self.scene_written = at
        path, md = scene_path(self.c), scene_md_path(self.c)
        if gone or self.now is None:
            for p in (path, md):
                try:
                    p.unlink()
                except OSError:
                    pass
            return
        lines = (
            self.track.window(self.now["position_ms"], WINDOW_MS) if self.track else []
        )
        data = {
            "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(
                timespec="seconds"
            ),
            "title": _title(self.now),
            "server": self.now["server"],
            "state": self.now["state"],
            "position_ms": self.now["position_ms"],
            "length_ms": self.now.get("length_ms"),
            "dialogue": (
                self.track.source
                if self.track.cues
                else ("listening" if self.track.live else "")
            ),
            "why_no_dialogue": self.track_note,
            "lines": [[cue.end, cue.text] for cue in lines[-12:]],
            "said": [
                {
                    "position_ms": r["position_ms"],
                    "said": r["said"],
                    "reached": r["reached"],
                }
                for r in self.said[-4:]
            ],
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            cp.atomic_write(path, json.dumps(data, ensure_ascii=False))
            cp.atomic_write(md, render_scene(self.c, data))
        except OSError:
            pass


def _log(c, row):
    row = {"at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), **row}
    try:
        path = log_path(c)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass


def render_scene(c, data, limit=900):
    """The scene, for her context: what is on, where, what was just said, what she said."""
    state = {"paused": "paused at", "buffering": "at"}.get(data.get("state"), "at")
    head = f"{data.get('title')}, {state} {_mmss(data.get('position_ms') or 0)}"
    if data.get("length_ms"):
        head += f" of {_mmss(data['length_ms'])}"
    out = [head + f" (on {c.human}'s {data.get('server', 'media')} server)."]
    if data.get("lines"):
        out.append("Just said, up to now (nothing after the playhead is known):")
        out.extend(f"[{_mmss(ms)}] {text}" for ms, text in data["lines"])
    elif data.get("why_no_dialogue"):
        out.append(
            f"You cannot hear the dialogue of this one ({data['why_no_dialogue']}); go by what {c.human} says."
        )
    if data.get("said"):
        out.append(
            "What you said during it: "
            + "; ".join(
                f'"{r["said"]}" at {_mmss(r["position_ms"])}' for r in data["said"]
            )
            + "."
        )
    text = "\n".join(out)
    if len(text) <= limit:
        return text
    keep = [out[0]] + out[-3:] if len(out) > 4 else out[:1]
    return "\n".join(keep)[:limit]


def scene_now(c, now=None):
    """The scene, when it is now (fresh), for the context builder; "" otherwise."""
    now = now or dt.datetime.now(dt.timezone.utc)
    try:
        data = json.loads(scene_path(c).read_text(encoding="utf-8"))
        checked = dt.datetime.fromisoformat(data["checked_at"])
    except (OSError, ValueError, KeyError, TypeError):
        return ""
    age = (now - checked).total_seconds()
    fresh = SCENE_PAUSED_FRESH_S if data.get("state") == "paused" else SCENE_FRESH_S
    if age < -60 or age > fresh:
        return ""
    return render_scene(c, data)


def recent(c, limit=6, hours=36, now=None):
    """What she said while watching lately, newest last: for memory of it later."""
    now = now or dt.datetime.now(dt.timezone.utc)
    rows = []
    try:
        with log_path(c).open(encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("event") != "said":
                    continue
                try:
                    at = dt.datetime.fromisoformat(row["at"])
                except (KeyError, ValueError):
                    continue
                if (now - at).total_seconds() <= hours * 3600:
                    rows.append(row)
    except OSError:
        return []
    return rows[-limit:]


# ---- running it --------------------------------------------------------------------------------------------------
class Runner(threading.Thread):
    """A follower per companion, in the app's process. Re-reads the companion's settings every few minutes."""

    def __init__(self, home, stop=None):
        super().__init__(name=f"watchalong:{home}", daemon=True)
        self.home = pathlib.Path(home)
        self.stop_event = stop or threading.Event()
        self.follower = None
        self.loaded_at = 0.0

    def run(self):
        while not self.stop_event.is_set():
            wait = READ_IDLE_S
            try:
                if self.follower is None or time.time() - self.loaded_at > 300:
                    c = cc.load(self.home)
                    self.loaded_at = time.time()
                    if enabled(c):
                        if self.follower is None:
                            self.follower = Follower(c)
                        else:
                            import companion_viewing as viewing

                            self.follower.c = c
                            self.follower.view = viewing.server_for(
                                c, self.follower.now or {}
                            )
                    else:
                        self.follower = None
                if self.follower is not None:
                    wait = self.follower.tick()
            except (
                Exception
            ):  # noqa: BLE001 -- the follower must survive anything a server or a file does
                wait = READ_IDLE_S
            self.stop_event.wait(max(0.5, min(wait, READ_IDLE_S)))


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--home", type=pathlib.Path)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser(
        "status",
        help="what is playing, whether its dialogue can be followed, and the scene",
    )
    sub.add_parser("run", help="follow in the foreground (the app runs this itself)")
    test = sub.add_parser(
        "lines", help="parse a subtitle file and show the lines that would land"
    )
    test.add_argument("file", type=pathlib.Path)
    args = parser.parse_args()
    if args.cmd == "lines":
        cues = parse_subtitles(args.file.read_text(encoding="utf-8", errors="replace"))
        for cue in cues:
            points, kind = score(cue, cue.end, None)
            if points >= 2:
                print(f"{_mmss(cue.end)}  {points}  {kind:24}  {cue.text[:90]}")
        return
    c = cc.load(args.home)
    if args.cmd == "status":
        print(
            json.dumps(
                {
                    "enabled": enabled(c),
                    "mode": mode_of(c),
                    "reach": getattr(c, "watchalong_reach", None),
                }
            )
        )
        try:
            rows = playing(c)
        except ValueError as exc:
            print("server:", exc)
            return
        for row in rows:
            raw, why = subtitles(c, row)
            print(
                f"{_title(row)} at {_mmss(row['position_ms'])} ({row['state']}): "
                + (
                    f"{len(parse_subtitles(raw))} lines to follow"
                    if raw
                    else f"no dialogue ({why})"
                )
            )
        print(scene_now(c) or "(no scene now)")
        return
    if not enabled(c):
        sys.exit(
            "Watching together is off, or no media server is set up with the viewing sense on."
        )
    follower = Follower(c)
    while True:
        time.sleep(follower.tick())


if __name__ == "__main__":
    main()
