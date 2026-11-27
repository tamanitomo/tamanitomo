#!/usr/bin/env python3
"""On this day: what the two of them had on today's date a month, a season, a year or years ago.

People who share a life remember by the calendar: "a year ago today we...". Her memory is long (every conversation is
kept, and so are what they watched and the moments she wrote down), but a memory nobody brings up might as well be
gone. Once a day this looks back at the same date one, three and six months ago and each year before, and picks a few
true things: something the human said, a film they watched together, a moment she kept, a time they felt close.

No model is called; records are only read. She is told she may bring one up, once and lightly, and never to recite
them. The senses job keeps it fresh (`ambient/onthisday.md`), and her context gives it a short section of its own.
"""

from __future__ import annotations
import argparse
import calendar
import datetime as dt
import json
import pathlib
import re
from zoneinfo import ZoneInfo

import companion_config as cc

MONTHS_BACK = (1, 3, 6)
YEARS_BACK = range(1, 31)
MAX_ITEMS = 4
QUOTE_CHARS = 150
# What makes a day's message worth remembering, and what makes it machinery. A guess, and a cheap one: the best line
# of a day still has to be one a person would recall, so a day of nothing but setup work offers nothing.
WARM = re.compile(
    r"\b(love\w*|miss\w*|proud|happy|happiest|excited|nervous|scared|sad|sorry|thank\w*|remember\w*|first|"
    r"birthday|anniversary|dinner|date|trip|vacation|holiday|movie|film|watched|game|played|cooked|ate|went|saw|"
    r"met|dream\w*|tired|family|mom|dad|mum|friend\w*|beautiful|laugh\w*|cried|hug\w*|kiss\w*|together|home)\b",
    re.I,
)
MACHINERY = re.compile(
    r"\b(ssh|sudo|error|config\w*|install\w*|restart\w*|cron|model|token|https?|api|server|docker|plugin|python|"
    r"script|repo|commit|logs?|gateway|deploy\w*|update|debug\w*|terminal|prompt|json|yaml|bug|fix\w*)\b",
    re.I,
)
PATHS = re.compile(r"(?:/[\w.-]+){2,}|https?://|\w:\\\\")
LABELS = {1: "A month ago", 3: "Three months ago", 6: "Six months ago"}
YEARS = {
    1: "A year ago",
    2: "Two years ago",
    3: "Three years ago",
    4: "Four years ago",
    5: "Five years ago",
}


def _tz(c):
    try:
        return ZoneInfo(c.timezone or "UTC")
    except Exception:  # noqa: BLE001
        return ZoneInfo("UTC")


def _months_before(day, months):
    """The same day of the month, `months` earlier; the month's last day when it is shorter."""
    year, month = day.year, day.month - months
    while month <= 0:
        month += 12
        year -= 1
    last = calendar.monthrange(year, month)[1]
    return dt.date(year, month, min(day.day, last))


def past_days(today):
    """[(label, date)], nearest first: one, three, six months back, then each year back."""
    out = [(LABELS[m], _months_before(today, m)) for m in MONTHS_BACK]
    for years in YEARS_BACK:
        try:
            then = today.replace(year=today.year - years)
        except ValueError:  # the 29th of February
            then = today.replace(year=today.year - years, day=28)
        out.append((YEARS.get(years, f"{years} years ago"), then))
    return out


def _quote(text, limit=QUOTE_CHARS):
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def score(text):
    """How much a line from that day is a thing a person would remember. Below 1, it is not offered."""
    text = text or ""
    if len(text) < 15 or text.lstrip().startswith(("/", "[", "{")):
        return 0
    points = 2 * len(WARM.findall(text)) - 3 * len(MACHINERY.findall(text))
    if PATHS.search(text):
        points -= 3  # a file path or a link: work, not a memory
    if 30 <= len(text) <= 300:
        points += 1
    return points


def _day_bounds(c, day):
    tz = _tz(c)
    start = dt.datetime.combine(day, dt.time(0, 0), tz)
    return start.timestamp(), (start + dt.timedelta(days=1)).timestamp()


def said(c, days):
    """{date: (line, channel)}: the human's most memorable message of each of those days, from every conversation
    with them (companion_transcript decides which those are)."""
    import companion_transcript as transcript

    def read(view):
        if view is None:
            return {}
        found = {}
        for day in days:
            start, end = _day_bounds(c, day)
            best = (0, None)
            for record in view.forward(start, 0, end, end_inclusive=False):
                if record.speaker != "owner":
                    continue
                points = score(record.content)
                if points > best[0]:
                    best = (points, record)
            if best[1] is not None:
                record = best[1]
                channel = record.channel or {"telegram": "Telegram", "workspace": "the app", "terminal": "a terminal",
                                             "api": "another app"}.get(record.source_kind, "")  # fmt: skip
                found[day] = (_quote(record.content), channel)
        return found

    try:
        return transcript.owner_evidence(c, read)
    except (transcript.SourceUnavailable, ValueError, OSError):
        return {}


def _rows(path):
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    yield json.loads(line)
                except ValueError:
                    continue
    except OSError:
        return


def _date_of(value, tz):
    try:
        when = dt.datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        try:
            return dt.date.fromisoformat(str(value)[:10])
        except ValueError:
            return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=tz)
    return when.astimezone(tz).date()


def watched(c, days):
    """{date: [titles]} of what was finished that day, what they watched together first."""
    import companion_viewing as viewing

    tz, wanted, out = _tz(c), set(days), {}
    for row in _rows(viewing.path_for(c)):
        if row.get("kind") != "seen":
            continue
        day = _date_of(row.get("at"), tz)
        if day not in wanted:
            continue
        title = viewing.label(row)
        rows = out.setdefault(day, [])
        if title not in [t for t, _ in rows]:
            rows.append((title, bool(row.get("together"))))
    return {
        day: [t for t, _ in sorted(rows, key=lambda r: not r[1])]
        for day, rows in out.items()
    }


def kept(c, days):
    """{date: text} of a relationship moment she wrote down for that day."""
    try:
        import companion_notes as notes

        rows = notes.moments(c)
    except Exception:  # noqa: BLE001
        return {}
    tz, wanted, out = _tz(c), set(days), {}
    for row in rows:
        day = _date_of(row.get("happened_on") or row.get("at"), tz)
        if day in wanted and day not in out and row.get("text"):
            out[day] = _quote(row["text"])
    return out


def close(c, days):
    """{date: text} of a time she felt close to them that day (a connection, never a hurt)."""
    try:
        import companion_feelings as feelings

        rows = feelings.experiences(c)
    except Exception:  # noqa: BLE001
        return {}
    tz, wanted, out = _tz(c), set(days), {}
    for row in rows:
        if row.get("kind") != "connection" or not row.get("text"):
            continue
        day = _date_of(row.get("at"), tz)
        if day in wanted and day not in out:
            out[day] = _quote(row["text"])
    return out


def reactions(c, days):
    """{date: (what she said, title)} from watching together, live."""
    import companion_watchalong as watchalong

    tz, wanted, out = _tz(c), set(days), {}
    for row in _rows(watchalong.log_path(c)):
        if row.get("event") != "said":
            continue
        day = _date_of(row.get("at"), tz)
        if day in wanted and day not in out:
            out[day] = (_quote(row.get("said"), 80), row.get("title") or "")
    return out


def items(c, now=None):
    """The day's memories: [{"label", "date", "lines": [...]}], at most MAX_ITEMS lines in all, years first."""
    now = now or dt.datetime.now(_tz(c))
    today = now.astimezone(_tz(c)).date()
    days = past_days(today)
    dates = [d for _, d in days]
    sources = {
        "kept": kept(c, dates),
        "close": close(c, dates),
        "watched": watched(c, dates),
        "reactions": reactions(c, dates),
        "said": said(c, dates),
    }
    out, total = [], 0
    # The furthest back first: a year ago is rarer than a month ago, and worth more.
    for label, day in sorted(days, key=lambda row: row[1]):
        lines = []
        if day in sources["kept"]:
            lines.append(f'you wrote down: "{sources["kept"][day]}"')
        if day in sources["close"]:
            lines.append(f'you felt close: "{sources["close"][day]}"')
        if day in sources["watched"]:
            titles = sources["watched"][day][:2]
            lines.append("you two watched " + " and ".join(titles))
        if day in sources["reactions"]:
            words, title = sources["reactions"][day]
            lines.append(f'you said "{words}" while watching {title}'.rstrip())
        if day in sources["said"] and not (
            day in sources["kept"] or day in sources["close"]
        ):
            # What she kept of a day already says it; his words are for days she wrote nothing down.
            line, channel = sources["said"][day]
            lines.append(
                f'{c.human} said{(" on " + channel) if channel else ""}: "{line}"'
            )
        if not lines:
            continue
        lines = lines[: max(1, MAX_ITEMS - total)]
        out.append({"label": label, "date": day.isoformat(), "lines": lines})
        total += len(lines)
        if total >= MAX_ITEMS:
            break
    return out


def render(c, now=None):
    """(text, data) for the senses job: nothing at all when there is nothing true to say."""
    found = items(c, now)
    if not found:
        return "", {"items": []}
    tz = _tz(c)
    rows = []
    for row in found:
        day = dt.date.fromisoformat(row["date"])
        when = (
            f"{day.day} {day:%B %Y}"
            if day.year != dt.datetime.now(tz).year
            else f"{day.day} {day:%B}"
        )
        rows.append(
            f"- {row['label']} today ({when}): " + "; ".join(row["lines"]) + "."
        )
    text = (
        "On this day:\n"
        + "\n".join(rows)
        + "\nBring one up only if it fits the moment, the way people remember: once, lightly, as your own memory. "
        "Never recite them, and never as a test of whether they remember."
    )
    return text, {"items": found}


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--home", type=pathlib.Path)
    parser.add_argument("--date", help="pretend today is this YYYY-MM-DD")
    args = parser.parse_args()
    c = cc.load(args.home)
    now = None
    if args.date:
        now = dt.datetime.combine(dt.date.fromisoformat(args.date), dt.time(12), _tz(c))
    text, _data = render(c, now)
    print(text or "(nothing on this day)")


if __name__ == "__main__":
    main()
