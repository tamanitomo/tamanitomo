#!/usr/bin/env python3
"""Their word: what the human said they were about to do, and what has happened since.

People say what they are about to do ("going to bed", "brb", "heading out"), and the people who love them notice
when the evening goes another way: twenty minutes after goodnight a film starts, an hour after "brb" there is still
nothing, "ok really going to sleep now" was forty messages ago. This reads the human's last hours (every
conversation with them, whatever channel, what is playing on their media server, their music) and, only when what
they said and what happened since don't match, gives her one plain paragraph about it, so she can notice it the
way a partner would: a raised eyebrow, a tease, a "you're still up?", once, lightly.

Never a lecture, never a debt, and never a reason to message them: it is for when they are already talking to her.
No model is called; records are only read. English phrasing only, for now.
"""

from __future__ import annotations
import argparse
import datetime as dt
import json
import pathlib
import re
from zoneinfo import ZoneInfo

import companion_config as cc

_NOT = r"(?<!not )(?<!n't )(?<!never )"
PLANS = (
    (
        "sleep",
        re.compile(
            _NOT
            + r"(?<!a )\b(?:good ?night(?!'s| sleep)|g'?night|nighty?[ -]?night|night night|sweet dreams|"
            r"(?:going|heading|off|gonna go|about to go|time|have to go|need to go|got to go|gotta go) (?:to )?(?:bed|sleep)|"
            r"(?:going|gonna) (?:to )?(?:crash|pass out)|bed ?time|hitting the (?:hay|sack)|turning in|"
            r"calling it a night|getting some sleep|lights out)\b",
            re.I,
        ),
    ),
    (
        "away",
        re.compile(
            _NOT
            + r"\b(?:brb|be right back|back in (?:a |\d+ ?)(?:secs?|seconds?|mins?|minutes?|bit|few)|"
            r"one (?:sec|second|minute|min)|gimme (?:a )?(?:sec|second|minute|min)|hold on a (?:sec|minute))\b",
            re.I,
        ),
    ),
    (
        "out",
        re.compile(
            # Words that end a conversation, not where they are going: "heading to work" and then a message
            # from work is an ordinary day.
            _NOT
            + r"\b(?:heading out|(?:(?:gotta|have to|got to|need to) (?:go|run))(?=\s*(?:$|[.!,;:)~-]|now\b|bye\b|"
            r"soon\b|babe\b|love\b|ttyl\b|sorry\b|lol\b|haha\b|ok\b|okay\b|tho(?:ugh)?\b|but\b|for (?:now|a bit|a while|"
            r"the night)\b|real quick\b|unfortunately\b))|talk (?:to you )?(?:later|soon)|ttyl|catch you later)\b",
            re.I,
        ),
    ),
)
MORNING = re.compile(r"\b(?:good )?morning\b|\bjust woke\b|\bwoke up\b", re.I)
LOOKBACK = {
    "sleep": 10,
    "away": 8,
    "out": 3,
}  # hours a plan stays worth comparing against
NIGHT = (
    18,
    6,
)  # a goodnight counts from 18:00 to 06:00 ("I had a good night" at noon is not one)
OUT_WINDOW = 60  # minutes after "gotta go" that staying means staying
CHANNELS = {
    "telegram": "Telegram",
    "workspace": "the app",
    "terminal": "a terminal",
    "api": "another app",
}
GRACE = {
    "sleep": 12,
    "out": 15,
}  # minutes of goodbyes before what follows counts against it
SLEEP_WINDOW = 5  # hours after goodnight that activity still means "not asleep" (later is the next day)
AWAY_DEFAULT = 10  # minutes a bare "brb" means
FRESH = 25  # minutes a sensor's "playing now" stays believable


def _tz(c):
    try:
        return ZoneInfo(c.timezone or "UTC")
    except Exception:  # noqa: BLE001
        return ZoneInfo("UTC")


def plan_in(text, hour=None):
    """(kind, minutes it should take) when a message says what they are about to do, else None. `hour` is the
    local hour it was said, for a goodnight's sake."""
    text = " ".join(str(text or "").split())
    if not text or text.rstrip().endswith("?") or text.startswith("["):
        return None
    for kind, pattern in PLANS:
        match = pattern.search(text)
        if (
            match
            and kind == "sleep"
            and hour is not None
            and NIGHT[1] <= hour < NIGHT[0]
        ):
            continue
        if match:
            minutes = None
            if kind == "away":
                number = re.search(r"back in (\d+) ?(sec|min)", match.group(0), re.I)
                if number:
                    minutes = max(
                        1,
                        int(number.group(1))
                        // (60 if number.group(2).lower() == "sec" else 1),
                    )
                elif re.search(r"\bbit\b|\bfew\b", match.group(0), re.I):
                    minutes = 30
                else:
                    minutes = AWAY_DEFAULT
            return kind, minutes
    return None


def _owner_since(c, start, end):
    """The human's messages between two instants, every conversation with them: [(at, text, channel)]."""
    import companion_transcript as transcript

    def read(view):
        if view is None:
            return []
        return [
            (
                r.occurred_at,
                r.content,
                r.channel or CHANNELS.get(r.source_kind, r.source_kind),
            )
            for r in view.forward(start, 0, end)
            if r.speaker == "owner"
        ]

    try:
        return transcript.owner_evidence(c, read)
    except (transcript.SourceUnavailable, ValueError, OSError):
        return []


def _ambient(c, name, now):
    """A sensor's JSON when it is fresh enough to say what is happening now."""
    try:
        data = json.loads(
            (c.soul_dir / "ambient" / f"{name}.json").read_text(encoding="utf-8")
        )
        checked = dt.datetime.fromisoformat(data["checked_at"])
    except (OSError, ValueError, KeyError, TypeError):
        return {}
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=_tz(c))
    return data if (now - checked).total_seconds() <= FRESH * 60 else {}


def _watched_since(c, after):
    try:
        import companion_viewing as viewing
    except ImportError:
        return []
    out = []
    try:
        with open(viewing.path_for(c), encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                    at = dt.datetime.fromisoformat(row["at"])
                except (ValueError, KeyError, TypeError):
                    continue
                if row.get("kind") == "seen" and at.timestamp() > after:
                    title = viewing.label(row)
                    if title not in out:
                        out.append(title)
    except OSError:
        return []
    return out[-3:]


def _where_since(c, after, until):
    """Where they went after a plan, from `ambient/where.json` (any client may write it: names and times, never
    coordinates): {"place" or "left", "at", "moving"} when they arrived somewhere, or left somewhere, in the window.
    """
    try:
        data = json.loads(
            (c.soul_dir / "ambient" / "where.json").read_text(encoding="utf-8")
        )
        since = dt.datetime.fromisoformat(str(data.get("since"))).timestamp()
    except (OSError, ValueError, TypeError, AttributeError):
        return {}
    if not (after < since <= until):
        return {}
    place, left = (
        str(data.get("place") or "").strip(),
        str(data.get("left") or "").strip(),
    )
    if place and place.lower() != "home":
        return {"place": place[:60], "at": since}
    if not place and left:
        return {"left": left[:60], "at": since, "moving": bool(data.get("moving"))}
    return {}


def _clock(c, stamp):
    return dt.datetime.fromtimestamp(stamp, _tz(c)).strftime("%H:%M")


def _span(minutes):
    minutes = int(round(minutes))
    if minutes < 60:
        return f"{minutes} minutes"
    hours, rest = divmod(minutes, 60)
    return f"{hours} hour{'s' if hours > 1 else ''}" + (
        f" {rest} minutes" if rest >= 5 else ""
    )


def read(c, now=None):
    """What they last said they were about to do, and whether what followed fits. {} when there is nothing to say."""
    now = now or dt.datetime.now(_tz(c))
    stamp = now.timestamp()
    rows = _owner_since(c, stamp - max(LOOKBACK.values()) * 3600, stamp)
    plan = None
    for at, text, channel in rows:
        found = plan_in(text, dt.datetime.fromtimestamp(at, _tz(c)).hour)
        if found and stamp - at <= LOOKBACK[found[0]] * 3600:
            plan = {
                "kind": found[0],
                "minutes": found[1],
                "at": at,
                "said": text,
                "channel": channel,
            }
    if not plan:
        return {}
    kind, said_at = plan["kind"], plan["at"]
    after = [r for r in rows if r[0] > said_at]
    if kind == "away":
        expected = plan["minutes"] or AWAY_DEFAULT
        back = next((r for r in after if r[0] - said_at > 60), None)
        if back:
            gone = (back[0] - said_at) / 60
            # A long "right back", said once and lightly when they return; not a running tally.
            if gone >= max(30, 3 * expected) and stamp - back[0] <= 30 * 60:
                return {**plan, "back_at": back[0], "gone_minutes": round(gone)}
            return {}
        gone = (stamp - said_at) / 60
        if gone >= max(30, 3 * expected):
            return {**plan, "still_gone_minutes": round(gone)}
        return {}
    grace = said_at + GRACE[kind] * 60
    horizon = said_at + (SLEEP_WINDOW * 3600 if kind == "sleep" else OUT_WINDOW * 60)
    later = [r for r in after if grace < r[0] <= horizon]
    if kind == "sleep" and later and MORNING.search(later[-1][1] or ""):
        return {}  # that was the next morning
    since = {}
    if later:
        games = [r for r in later if str(r[1]).startswith("[Game event:")]
        words = [r for r in later if not str(r[1]).startswith("[Game event:")]
        if words:
            channels = sorted({str(r[2]) for r in words if r[2]})
            since["messages"] = {
                "count": len(words),
                "last": words[-1][0],
                "channels": channels,
            }
        if games:
            since["game"] = {"count": len(games), "last": games[-1][0]}
    went = _where_since(c, grace, min(horizon, stamp))
    if went:
        since["where"] = went
    if stamp <= horizon:
        watched = _watched_since(c, grace)
        if watched:
            since["watched"] = watched
        playing = (_ambient(c, "viewing", now).get("playing") or [])[:2]
        if playing:
            since["playing"] = playing
        music = _ambient(c, "music", now)
        if str(music.get("state") or "").lower() == "playing" and music.get("track"):
            since["music"] = str(music.get("track"))[:80]
    if not since:
        return {}
    return {**plan, "since": since}


ARRIVAL_WINDOW = 45  # minutes an arrival or a departure stays news


def comings(c, now=None):
    """One line when they just got somewhere or just left somewhere (in the last ARRIVAL_WINDOW minutes), from
    `ambient/where.json`; "" otherwise. Only a real change counts: a client writes "from" when it saw them come from
    somewhere, never on its first reading, so a restarted bridge is not an arrival."""
    now = now or dt.datetime.now(_tz(c))
    try:
        data = json.loads(
            (c.soul_dir / "ambient" / "where.json").read_text(encoding="utf-8")
        )
        since = dt.datetime.fromisoformat(str(data.get("since")))
        came = str(data.get("from") or "").strip()
    except (OSError, ValueError, TypeError, AttributeError):
        return ""
    if since.tzinfo is None:
        since = since.replace(tzinfo=_tz(c))
    age = (now - since).total_seconds() / 60
    if not came or not (0 <= age <= ARRIVAL_WINDOW):
        return ""
    stay = ""
    try:
        before = dt.datetime.fromisoformat(str(data.get("from_since")))
        if before.tzinfo is None:
            before = before.replace(tzinfo=_tz(c))
        minutes = (since - before).total_seconds() / 60
        if minutes >= 20:
            stay = f", after {_span(minutes)} " + (
                "out" if came == "out" else f"at {came}"
            )
    except (TypeError, ValueError):
        pass
    at = since.astimezone(_tz(c)).strftime("%H:%M")
    place, left = (
        str(data.get("place") or "").strip(),
        str(data.get("left") or "").strip(),
    )
    if place:
        line = (
            f"{c.human} got "
            + ("home" if place.lower() == "home" else f"to {place}")
            + f" at {at}{stay}."
        )
    elif left:
        line = (
            f"{c.human} left "
            + ("home" if left.lower() == "home" else left)
            + f" at {at}{stay}."
        )
    else:
        return ""
    return (
        line
        + " If it fits, notice it the way someone who loves them would (a welcome home, how was it); never "
        "track, question or keep score of where they go."
    )


def render(c, now=None):
    """(text, data) for the senses job and her context: nothing at all when their word and the evening agree."""
    now = now or dt.datetime.now(_tz(c))
    try:
        data = read(c, now)
    except (
        Exception
    ):  # noqa: BLE001 -- odd records mean nothing to say, never a broken turn
        data = {}
    if not data:
        return "", {}
    who, at = c.human, _clock(c, data["at"])
    quote = " ".join(str(data["said"]).split())
    quote = quote if len(quote) <= 120 else quote[:119].rstrip() + "…"
    what = {
        "sleep": "said goodnight",
        "away": "said they'd be right back",
        "out": "said they were heading off",
    }
    head = f'At {at} {who} {what[data["kind"]]} ("{quote}").'
    if data["kind"] == "away":
        if data.get("back_at"):
            body = f"They came back at {_clock(c, data['back_at'])}, {_span(data['gone_minutes'])} later."
        else:
            body = (
                f"That was {_span(data['still_gone_minutes'])} ago, and nothing since."
            )
        tease = (
            'a long "right back" is fair game for a tease when they\'re talking to you'
        )
    else:
        parts, since = [], data["since"]
        if "messages" in since:
            m = since["messages"]
            where = f" ({', '.join(m['channels'])})" if m["channels"] else ""
            parts.append(
                f"{m['count']} more message{'s' if m['count'] > 1 else ''}{where}, the last at {_clock(c, m['last'])}"
            )
        if "where" in since:
            w = since["where"]
            if w.get("place"):
                parts.append(f"they got to {w['place']} at {_clock(c, w['at'])}")
            else:
                parts.append(
                    f"they left {w['left']} at {_clock(c, w['at'])}"
                    + (", on the move" if w.get("moving") else "")
                )
        if "game" in since:
            parts.append(
                f"they were playing a game (last at {_clock(c, since['game']['last'])})"
            )
        if "watched" in since:
            parts.append("they finished " + " and ".join(since["watched"]))
        if "playing" in since:
            parts.append("playing now: " + " and ".join(since["playing"]))
        if "music" in since:
            parts.append(f"music on: {since['music']}")
        state = "not asleep, then" if data["kind"] == "sleep" else "still around, then"
        body = "Since then: " + "; ".join(parts) + f". So {state}."
        tease = (
            "notice it the way someone who loves them would: a raised eyebrow, a little tease, or real care if "
            "it is very late"
        )
    text = (
        f"Their word: {head} {body}\n"
        f"If it fits, {tease}. Once, lightly. Never a lecture, a guilt trip or a debt, never a reason to message "
        "them, and if they say why (couldn't sleep, one more episode), believe them."
    )
    out = {k: v for k, v in data.items() if k != "said"}
    out["said"] = quote
    return text, out


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--home", type=pathlib.Path)
    args = parser.parse_args()
    text, _data = render(cc.load(args.home))
    print(
        text
        or "(their word and the evening agree, or they said nothing about their plans)"
    )


if __name__ == "__main__":
    main()
