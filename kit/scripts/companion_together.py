#!/usr/bin/env python3
"""The dates two people keep, counted instead of written down.

`dates.md` asks the human to maintain a file. Most of what a couple marks is
arithmetic on things that already happened: the first conversation, every month
since, a hundred days, a year. This works those out from the session history,
adds the human's birthday once they have said it, and counts how many times a
tradition has come round.

Nothing here is invented. The start is the first message actually written (or a
date the human entered, which wins), the birthday is stored with the words it came
from, and a tradition counts only from the date it was recorded as beginning.
No model is called.
"""

from __future__ import annotations
import argparse
import calendar
import datetime as dt
import json
import pathlib
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
from companion_platform import atomic_write, file_lock

RECURS = ("weekly", "monthly", "yearly")
# Counts of days worth marking. Beyond the list, every five hundred.
DAY_MILESTONES = (50, 100, 150, 200, 250, 300, 400, 500, 600, 700, 800, 900, 1000)


def _tz(c):
    try:
        return ZoneInfo(c.timezone)
    except Exception:
        return ZoneInfo("UTC")


def path_for(c):
    return c.life / "together.json"


def read(c):
    try:
        data = json.loads(path_for(c).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _date(value, label):
    try:
        return dt.date.fromisoformat(str(value).strip())
    except ValueError:
        raise ValueError(f"{label} must be a date like 2026-03-14")


def _month_day(value):
    """'MM-DD' or 'YYYY-MM-DD' -> (month, day, year or None)."""
    text = str(value).strip()
    parts = text.split("-")
    try:
        if len(parts) == 3:
            year, month, day = (int(x) for x in parts)
        elif len(parts) == 2:
            year, (month, day) = None, (int(x) for x in parts)
        else:
            raise ValueError
        dt.date(year or 2000, month, day)
    except ValueError:
        raise ValueError("a birthday must look like 03-14 or 1990-03-14")
    return month, day, year


def write(c, since=None, human_birthday=None, evidence=""):
    """Record what the human entered or told her. Only what is passed is changed."""
    with file_lock(c.life / ".together.lock"):
        data = read(c)
        if since:
            data["since"] = _date(since, "since").isoformat()
        if human_birthday:
            month, day, year = _month_day(human_birthday)
            evidence = (evidence or "").strip()
            if not evidence:
                raise ValueError(
                    "a birthday needs the words it came from (--evidence), so it can be checked"
                )
            data["human_birthday"] = (
                f"{year:04d}-{month:02d}-{day:02d}"
                if year
                else f"{month:02d}-{day:02d}"
            )
            data["human_birthday_evidence"] = evidence[:300]
        c.life.mkdir(parents=True, exist_ok=True)
        atomic_write(path_for(c), json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return data


def start(c, now=None):
    """(date, 'entered' | 'first message') or (None, why not)."""
    entered = read(c).get("since")
    if entered:
        try:
            return dt.date.fromisoformat(entered), "entered"
        except ValueError:
            pass
    import companion_thread

    first = companion_thread.first_contact(c, now)
    if first:
        return first.astimezone(_tz(c)).date(), "first message"
    return None, "no conversation history yet, and no start date entered"


def add_months(day, months):
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return dt.date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _is_day_milestone(n):
    return n in DAY_MILESTONES or (n > 1000 and n % 500 == 0)


def milestones(begin, today, horizon=7):
    """Upcoming (date, label), today included, soonest first."""
    out = []
    end = today + dt.timedelta(days=horizon)
    total = (today - begin).days
    for n in range(max(1, total - 1), total + horizon + 2):
        when = begin + dt.timedelta(days=n)
        if today <= when <= end and _is_day_milestone(n):
            out.append((when, f"{n} days together"))
    months = 1
    while True:
        when = add_months(begin, months)
        if when > end:
            break
        if when >= today:
            label = (
                f"{months // 12}-year anniversary"
                if months % 12 == 0
                else f"{months}-month anniversary"
            )
            out.append((when, label))
        months += 1
    return sorted(out)


def occurrence(first_on, recurs, today):
    """(next date on or after today, which time it will be) for a tradition."""
    if recurs == "yearly":
        for year in (today.year, today.year + 1):
            day = min(first_on.day, calendar.monthrange(year, first_on.month)[1])
            when = dt.date(year, first_on.month, day)
            if when >= today:
                return when, year - first_on.year + 1
    elif recurs == "monthly":
        n = max(0, (today.year - first_on.year) * 12 + today.month - first_on.month)
        while True:
            when = add_months(first_on, n)
            if when >= today:
                return when, n + 1
            n += 1
    elif recurs == "weekly":
        n = max(0, -(-(today - first_on).days // 7))
        return first_on + dt.timedelta(days=7 * n), n + 1
    return None


def traditions(c, today, horizon=14):
    """Recorded rituals that come round within `horizon` days: (date, text, nth)."""
    import companion_notes

    out = []
    for row in companion_notes.moments(c, "active", "ritual"):
        recurs, first = row.get("recurs"), row.get("first_on")
        if recurs not in ("monthly", "yearly") or not first:
            continue
        try:
            begun = dt.date.fromisoformat(first)
        except ValueError:
            continue
        found = occurrence(begun, recurs, today)
        if found and (found[0] - today).days <= horizon:
            out.append((found[0], row["text"], found[1]))
    return sorted(out)


def birthday(c, today, horizon=7):
    """(date, label) when the human's birthday is within `horizon` days."""
    value = read(c).get("human_birthday")
    if not value:
        return None
    try:
        month, day, year = _month_day(value)
    except ValueError:
        return None
    for y in (today.year, today.year + 1):
        when = dt.date(y, month, min(day, calendar.monthrange(y, month)[1]))
        if when >= today:
            if (when - today).days > horizon:
                return None
            turning = f" (turning {y - year})" if year else ""
            return when, f"{c.human}'s birthday{turning}"
    return None


def _when(delta):
    return "today" if delta == 0 else "tomorrow" if delta == 1 else f"in {delta} days"


def _span(begin, today):
    days = (today - begin).days
    months = (today.year - begin.year) * 12 + today.month - begin.month
    if today.day < begin.day:
        months -= 1
    if months >= 12:
        years, rest = divmod(months, 12)
        return f"{years} year{'s' if years != 1 else ''}" + (
            f" and {rest} month{'s' if rest != 1 else ''}" if rest else ""
        )
    if months >= 1:
        return f"{months} month{'s' if months != 1 else ''}"
    return f"{days} day{'s' if days != 1 else ''}"


def render(c, now=None):
    """(text, facts), or (None, why not). Used by the `together` sense."""
    now = (now or dt.datetime.now(_tz(c))).astimezone(_tz(c))
    today = now.date()
    begin, source = start(c, now)
    lines = []
    facts = {}
    if begin:
        days = (today - begin).days
        lines.append(
            f"You and {c.human} first talked on {begin.isoformat()} ({source}): "
            f"{days} day{'s' if days != 1 else ''} ago, about {_span(begin, today)}."
        )
        facts = {"since": begin.isoformat(), "days": days, "source": source}
        coming = [(d, label) for d, label in milestones(begin, today)]
    else:
        coming = []
    if bday := birthday(c, today):
        coming.append(bday)
    for when, text, nth in traditions(c, today):
        coming.append((when, f"{text} (the {_ordinal(nth)} time)"))
    for when, label in sorted(coming):
        lines.append(f"- {label} — {_when((when - today).days)} ({when.isoformat()})")
    if not lines:
        return None, source
    return "\n".join(lines), {**facts, "coming": len(coming)}


def _ordinal(n):
    suffix = (
        "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    )
    return f"{n}{suffix}"


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--home", type=pathlib.Path)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show", help="the dates as she sees them")
    s = sub.add_parser("set", help="record a start date or the human's birthday")
    s.add_argument("--since", help="the day you first talked, if the history is wrong")
    s.add_argument("--human-birthday", help="MM-DD or YYYY-MM-DD")
    s.add_argument(
        "--evidence", default="", help="what was said that gave the birthday"
    )
    a = p.parse_args()
    c = cc.load(a.home)
    if a.cmd == "set":
        out = write(c, a.since, a.human_birthday, a.evidence)
    else:
        text, facts = render(c)
        out = {
            "text": text,
            **(facts if isinstance(facts, dict) else {"reason": facts}),
        }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
