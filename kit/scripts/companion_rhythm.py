#!/usr/bin/env python3
"""When the human is usually quiet, learned from when they actually write.

A night's sleep must not read as distance, and nobody should have to type in a
sleep schedule for that to be true. This looks at the hours of the day at which
messages have really arrived, finds the longest stretch that is almost always
silent, and offers it to `companion_feelings` as an expected absence.

It is evidence, not a guess about what the human is doing. It uses timestamps
only, calls no model, says nothing until there is enough history to mean
something, and never claims the human is asleep: the window is "usually quiet".
Windows the human entered themselves are kept alongside it, and the whole thing
switches off with the `learn_rhythm` feelings setting.
"""

from __future__ import annotations
import datetime as dt
import sys
import pathlib
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

HISTORY_DAYS = 28
# Below these there is no pattern to find, only a few evenings.
MIN_ACTIVE_DAYS = 10
MIN_MESSAGES = 40
# An hour counts as quiet if messages land in it on no more than this share of the
# days the human wrote at all, so one 2 a.m. message does not erase a night.
QUIET_SHARE = 0.1
MIN_QUIET_HOURS = 5
MAX_QUIET_HOURS = 12
LABEL = "Usually quiet (learned from your messages)"


def _tz(c):
    try:
        return ZoneInfo(c.timezone)
    except Exception:
        return ZoneInfo("UTC")


def quiet_window(stamps, tz):
    """(start_hour, end_hour, active_days, messages) for the longest quiet stretch, or None."""
    local = [s.astimezone(tz) for s in stamps]
    days = {s.date() for s in local}
    if len(days) < MIN_ACTIVE_DAYS or len(local) < MIN_MESSAGES:
        return None
    busy_days = [set() for _ in range(24)]
    for stamp in local:
        busy_days[stamp.hour].add(stamp.date())
    quiet = [len(busy_days[h]) <= QUIET_SHARE * len(days) for h in range(24)]
    best_len, best_start = 0, None
    for start in range(24):
        # Only measure a run from its first hour, so a stretch is counted once.
        if not quiet[start] or quiet[(start - 1) % 24]:
            continue
        length = 0
        while length < 24 and quiet[(start + length) % 24]:
            length += 1
        if length > best_len:
            best_len, best_start = length, start
    if best_start is None or best_len >= 24 or best_len < MIN_QUIET_HOURS:
        return None
    length = min(best_len, MAX_QUIET_HOURS)
    return best_start, (best_start + length) % 24, len(days), len(local)


def learned(c, now=None):
    """The learned window as feelings settings would write it, plus its evidence.

    `{"windows": [...], "evidence": {...} | None}`; `windows` is empty when there is
    nothing to say.
    """
    import companion_thread

    now = now or dt.datetime.now(_tz(c))
    found = quiet_window(
        companion_thread.human_times(c, now, HISTORY_DAYS),
        _tz(c),
    )
    if not found:
        return {"windows": [], "evidence": None}
    start, end, days, messages = found
    return {
        "windows": [
            {
                "label": LABEL,
                "days": [0, 1, 2, 3, 4, 5, 6],
                "start": f"{start:02d}:00",
                "end": f"{end:02d}:00",
                "learned": True,
            }
        ],
        "evidence": {
            "start": f"{start:02d}:00",
            "end": f"{end:02d}:00",
            "active_days": days,
            "messages": messages,
            "window_days": HISTORY_DAYS,
        },
    }


# ---- things she could notice ---------------------------------------------
# Observations are counts from timestamps and message lengths. They say what
# happened, never why, and never how the human feels: "four nights this week" is
# something a person who has been paying attention would see; "you seem stressed"
# is a claim nobody has evidence for.
FALLBACK_LATE = (0, 5)
RECENT_DAYS = 7
BASELINE_DAYS = 28
MIN_TODAY_MESSAGES = 5
MIN_BASELINE_MESSAGES = 30
QUESTION_QUIET_MINUTES = 20


def _in_window(hour, start, end):
    return start <= hour < end if start < end else hour >= start or hour < end


def _night(stamp):
    """The evening a night began on, so 01:00 belongs to the day before it."""
    return (stamp - dt.timedelta(hours=12)).date()


def late_nights(stamps, window, now):
    """(nights this week in the window, typical per week over the three before or None)."""
    start, end = window
    since_recent = now - dt.timedelta(days=RECENT_DAYS)
    since_base = now - dt.timedelta(days=BASELINE_DAYS)
    recent, earlier = set(), set()
    for stamp in stamps:
        if not _in_window(stamp.hour, start, end):
            continue
        (recent if stamp >= since_recent else earlier).add(_night(stamp))
    earlier = {n for n in earlier if n >= _night(since_base)}
    known = len({s.date() for s in stamps if s < since_recent}) >= MIN_ACTIVE_DAYS
    typical = round(len(earlier) / 3, 1) if known else None
    return len(recent), typical


def writing_style(rows, now):
    """('shorter'|'longer', today's median, usual median) when today is clearly unlike usual."""
    today = now.date()
    since = today - dt.timedelta(days=BASELINE_DAYS)
    todays = sorted(n for role, s, n in rows if role == "user" and s.date() == today)
    usual = sorted(
        n for role, s, n in rows if role == "user" and since <= s.date() < today
    )
    if len(todays) < MIN_TODAY_MESSAGES or len(usual) < MIN_BASELINE_MESSAGES:
        return None
    median = lambda values: values[len(values) // 2]
    today_median, usual_median = median(todays), median(usual)
    if usual_median < 1:
        return None
    ratio = today_median / usual_median
    if ratio <= 0.5:
        return "shorter", today_median, usual_median
    if ratio >= 2:
        return "longer", today_median, usual_median
    return None


def unanswered(tail, now):
    """What she last asked, when the human has not answered it in the way a chat does.

    `tail` is `companion_thread.read(...)["tail"]`. Either nothing has come back
    since she asked, or the human's next message arrived long after it. Whether that
    message answers the question is not known and is not claimed.
    """
    rows = [r for r in tail or [] if r.get("at")]
    mine = [i for i, r in enumerate(rows) if r["who"] == "you"]
    if not mine:
        return None
    index = mine[-1]
    asked = rows[index]
    if not asked.get("asks"):
        return None
    try:
        asked_at = dt.datetime.fromisoformat(asked["at"])
    except ValueError:
        return None
    later = next((r for r in rows[index + 1 :] if r["who"] == "them"), None)
    until = now
    if later:
        try:
            until = dt.datetime.fromisoformat(later["at"])
        except ValueError:
            return None
    minutes = (until - asked_at).total_seconds() / 60
    if minutes < QUESTION_QUIET_MINUTES:
        return None
    return {
        "question": asked["asks"],
        "hours": round(minutes / 60, 1),
        "replied": bool(later),
    }


def _hours(value):
    return f"{value * 60:.0f} minutes" if value < 1.5 else f"{value:.0f} hours"


def observations(c, now=None, replying=False):
    """Plain statements about how the human has been writing. [] when there is nothing to say.

    `replying` is true when this is the answer to a message the human has just sent.
    Then "has not written back" is never said, whether or not that message has reached
    the database yet.
    """
    import companion_thread
    import companion_feelings

    now = (now or dt.datetime.now(_tz(c))).astimezone(_tz(c))
    human = c.human
    lines = []
    rows = companion_thread.activity(c, now, BASELINE_DAYS + 2)
    stamps = [s for role, s, _n in rows if role == "user"]
    window = FALLBACK_LATE
    learned_window = None
    try:
        if companion_feelings.settings(c)["settings"]["learn_rhythm"]:
            learned_window = learned(c, now)["evidence"]
    except (OSError, ValueError):
        pass
    if learned_window:
        window = (
            int(learned_window["start"][:2]),
            int(learned_window["end"][:2]),
        )
    nights, typical = late_nights(stamps, window, now)
    if nights >= 3 and (typical is None or nights > typical + 1):
        span = f"{window[0]:02d}:00–{window[1]:02d}:00"
        usual = (
            ""
            if typical is None
            else f"; over the three weeks before it was about {typical:g} a week"
        )
        lines.append(
            f"{human} has written between {span} on {nights} of the last {RECENT_DAYS} nights{usual}."
        )
    style = writing_style(rows, now)
    if style:
        word, today_median, usual_median = style
        lines.append(
            f"{human}'s messages today are much {word} than usual "
            f"(a typical message is {today_median} characters today, against {usual_median} on other days)."
        )
    try:
        tail = companion_thread.read(c, now, tail=6).get("tail")
    except (OSError, ValueError):
        tail = None
    left = unanswered(tail, now)
    if left and left["replied"]:
        lines.append(
            f"Your last message ended with a question — “{left['question']}” — and {human}'s "
            f"next message came {_hours(left['hours'])} later. Whether it answers that question is not known."
        )
    elif left and not replying:
        lines.append(
            f"Your last message ended with a question — “{left['question']}” — "
            f"{_hours(left['hours'])} ago, and {human} has not written back since."
        )
    return lines


def render(c, now=None, replying=False):
    lines = observations(c, now, replying)
    if not lines:
        return ""
    return (
        f"[Things you could notice about how {c.human} has been writing — counts from times and "
        "message lengths, not conclusions. You may remark on one the way someone who had noticed "
        "would. Do not say why it is happening, do not claim a mood from it, and do not read "
        "the numbers back like a report.]\n"
        + "\n".join("- " + line for line in lines)
        + "\n"
    )
