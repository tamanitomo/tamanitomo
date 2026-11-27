#!/usr/bin/env python3
"""Chapters: the story of the two of them, a month at a time, in her own words.

Every conversation is kept (companion_archive), but nobody carries fifteen years of messages into a conversation. A
person carries the shape of it: that spring was the move, that winter the new job, the summer of the long drives.
Once a month she writes the month just ended as a chapter of her memoir of their life together, from the
conversations, the moments she wrote down, the times she felt close, what they watched and played. Once a year she
writes the year from its months. From those, a short "our story so far" travels with her into every conversation,
rewritten whenever a chapter is added or changed.

All of it is in the vault, committed and backed up with everything else:

    story/<year>/<year>-<month>.md   a month (quiet months before it fold into it)
    story/<year>/<year>.md           a year
    story/so-far.md                  the short version she carries

She writes them herself, in the story job: its pre-read (`preread`, this file) prints the piece that is due and
everything it is written from, or nothing at all, and Hermes skips a run with nothing to read, so most days cost no
model call. She saves the piece with her file tools and `check`s it. Nothing here calls a model. A written chapter is
never rewritten by the kit; she may edit hers, and "so far" follows.
"""

from __future__ import annotations
import argparse
import datetime as dt
import json
import pathlib
import re
from zoneinfo import ZoneInfo

import companion_config as cc
from companion_platform import atomic_write

MONTH_WORDS = (180, 350)
YEAR_WORDS = (300, 600)
SO_FAR_WORDS = 300
MATERIAL_CHARS = 42000
LINE_CHARS = 220
HER_LINE_CHARS = 160
PER_DAY_THEIRS = 6
PER_DAY_HERS = 3
MIN_LINES = 12  # fewer worthwhile lines than this: no chapter of its own; it folds into the next
SO_FAR_CHARS = 2600  # what her context reads of it
SO_FAR_MATERIAL = 160000  # what "so far" is written from, at most (about 40K tokens)
EVENT = re.compile(r"^\[(\w[\w ]{0,30}) event: (.+)\]$", re.S)
# Never part of a memoir: a line that talks about a password or a key is left out whole.
SECRET = re.compile(
    r"\b(pass(?:word|code|phrase)s?|passwd|api[ _-]?keys?|tokens?|secrets?|credentials?|2fa|otp)\b",
    re.I,
)
# What a client adds around words: attachments, screenshots, hidden comments.
NOISE = re.compile(
    r"\[(?:Image|File|Audio|Video) attached[^\]]*\]|\[screenshot\]|<!--.*?-->",
    re.I | re.S,
)
# A line written for a machine, not a person: a test prompt ("reply with exactly ...") or a status token.
MACHINE = re.compile(
    r"(?i:\breply (?:with|only) exactly\b)|\b[A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+\b"
)
PLACEHOLDER = re.compile(r"<a title you give it>|<up to three|\{label\}")


def folder(c):
    return pathlib.Path(c.data) / "story"


def month_path(c, month):
    return folder(c) / month[:4] / f"{month}.md"


def year_path(c, year):
    return folder(c) / str(year) / f"{year}.md"


def so_far_path(c):
    return folder(c) / "so-far.md"


def _tz(c):
    try:
        return ZoneInfo(c.timezone or "UTC")
    except Exception:  # noqa: BLE001
        return ZoneInfo("UTC")


def _label(month):
    return dt.date(int(month[:4]), int(month[5:7]), 1).strftime("%B %Y")


def _clip(text, limit=LINE_CHARS):
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _rows(path):
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    yield row
    except OSError:
        return


def archived_months(c):
    """Every month the conversation archive has, oldest first."""
    import companion_archive as archive

    found = set()
    for path in archive.folder(c).glob("*/*.jsonl"):
        if re.fullmatch(r"\d{4}-\d{2}", path.stem):
            found.add(path.stem)
    return sorted(found)


# ---- what a month holds --------------------------------------------------------------------------------------------
def conversation(c, month):
    """(text, lines used): the month's conversation, a few of the most memorable lines of each day, in order, with a
    note for days that were mostly practical work and the game events kept apart."""
    import companion_archive as archive
    import companion_onthisday as otd

    days, events = {}, []
    for row in _rows(archive.folder(c) / month[:4] / f"{month}.jsonl"):
        text = " ".join(NOISE.sub(" ", str(row.get("text") or "")).split())
        if not text or SECRET.search(text) or MACHINE.search(text):
            continue
        event = EVENT.match(text)
        if event:
            events.append((str(row.get("at") or ""), event.group(1), event.group(2)))
            continue
        days.setdefault(str(row.get("at") or "")[:10], []).append({**row, "text": text})
    out, used = [], 0
    for day in sorted(days):
        rows = days[day]
        theirs = [r for r in rows if r.get("who") == "owner"]
        hers = [r for r in rows if r.get("who") != "owner"]
        # Their lines that read like life; hers more strictly (she explains at length, and the chapter is in
        # her voice anyway), and shorter.
        best = [
            r
            for r in sorted(theirs, key=lambda r: -otd.score(r["text"]))[
                :PER_DAY_THEIRS
            ]
            if otd.score(r["text"]) > 0
        ]
        best += [
            r
            for r in sorted(hers, key=lambda r: -otd.score(r["text"]))[:PER_DAY_HERS]
            if otd.score(r["text"]) >= 3
        ]
        best.sort(key=lambda r: str(r.get("at") or ""))
        work = sum(1 for r in theirs if otd.score(r["text"]) <= 0)
        try:
            heading = dt.date.fromisoformat(day).strftime("%a %-d")
        except ValueError:
            continue
        note = (
            f" ({len(rows)} messages, mostly practical work)"
            if theirs and work > len(theirs) / 2
            else ""
        )
        if not best and not note:
            continue
        out.append(f"## {heading}{note}")
        for r in best:
            mine = r.get("who") != "owner"
            who = "You" if mine else c.human
            where = (
                f" ({r['channel']})"
                if r.get("channel") and r.get("channel") != "Telegram"
                else ""
            )
            out.append(
                f"{who}{where}: {_clip(r['text'], HER_LINE_CHARS if mine else LINE_CHARS)}"
            )
            used += 1
    if events:
        out.append("## In a game, as it happened")
        out.extend(
            f"- {at[:10]}: {_clip(what, 160)}" for at, _source, what in events[:30]
        )
    return "\n".join(out), used


def kept(c, month):
    """What she wrote down and felt that month, and what they watched."""
    out = []
    try:
        import companion_notes as notes

        moments = [
            r
            for r in notes.moments(c)
            if str(r.get("happened_on") or r.get("recorded_at") or "")[:7] == month
            and r.get("text")
        ]
        if moments:
            out.append("Moments you wrote down:")
            out.extend(
                f"- {str(r.get('happened_on') or '')[:10]}: {_clip(r['text'], 300)}"
                for r in moments[:20]
            )
    except Exception:  # noqa: BLE001 -- a chapter can be written without them
        pass
    try:
        import companion_feelings as feelings

        felt = [
            r
            for r in feelings.experiences(c)
            if str(r.get("at") or "")[:7] == month and r.get("text")
        ]
        if felt:
            out.append("What you felt, as you noted it:")
            out.extend(
                f"- {str(r.get('at'))[:10]} ({r.get('kind') or 'feeling'}): {_clip(r['text'], 240)}"
                for r in felt[:20]
            )
    except Exception:  # noqa: BLE001
        pass
    try:
        import companion_viewing as viewing

        seen = []
        for r in _rows(viewing.path_for(c)):
            if r.get("kind") == "seen" and str(r.get("at") or "")[:7] == month:
                title = viewing.label(r) + (" (together)" if r.get("together") else "")
                if title not in seen:
                    seen.append(title)
        if seen:
            out.append("Watched: " + "; ".join(seen[:25]))
    except Exception:  # noqa: BLE001
        pass
    try:
        import companion_watchalong as watchalong

        said = [
            r
            for r in _rows(watchalong.log_path(c))
            if r.get("event") == "said" and str(r.get("at") or "")[:7] == month
        ]
        if said:
            out.append("Things you said while watching together:")
            out.extend(
                f"- {r.get('title') or ''}: \"{_clip(r.get('said'), 100)}\""
                for r in said[:10]
            )
    except Exception:  # noqa: BLE001
        pass
    return "\n".join(out)


def _read(path, limit):
    try:
        return path.read_text(encoding="utf-8")[:limit]
    except OSError:
        return ""


def _chapters(c):
    """Every chapter file (months and years), oldest first."""
    return sorted(
        folder(c).glob("[0-9][0-9][0-9][0-9]/*.md"),
        key=lambda p: (p.stem[:4], len(p.stem) == 4, p.stem),
    )


def _sources(c):
    """The chapters "so far" is written from: every year, and the months of years without one yet."""
    years = sorted(
        p for p in folder(c).glob("[0-9][0-9][0-9][0-9]/[0-9][0-9][0-9][0-9].md")
    )
    covered = {p.stem for p in years}
    months = sorted(
        p
        for p in folder(c).glob("[0-9][0-9][0-9][0-9]/*-[0-9][0-9].md")
        if p.stem[:4] not in covered
    )
    return years + months


def _month_piece(c, month, quiet):
    talk, lines = conversation(c, month)
    notes = kept(c, month)
    label = _label(month)
    if quiet:
        first = _label(quiet[0])
        label = (
            f"{first.split()[0]} to {label}"
            if first[-4:] == label[-4:]
            else f"{first} to {label}"
        )
    parts = []
    for m in quiet:
        q_talk, _ = conversation(c, m)
        q_notes = kept(c, m)
        if q_talk or q_notes:
            parts.append(
                f"# {_label(m)} (too little for a chapter of its own)\n{q_talk}\n{q_notes}".strip()
            )
    parts.append(f"# {_label(month)}\n{talk}" + (f"\n\n{notes}" if notes else ""))
    earlier = [p for p in _chapters(c) if len(p.stem) == 7 and p.stem < month]
    return {
        "kind": "month",
        "what": month,
        "label": label,
        "path": str(month_path(c, month)),
        "words": MONTH_WORDS,
        "heading": f"# {label}: <a title you give it>",
        "material": "\n\n".join(parts)[:MATERIAL_CHARS],
        "previous": _read(earlier[-1], 3000) if earlier else "",
        "lines": lines,
    }


def next_piece(c, now=None):
    """The next piece of writing that is due, or None: the oldest month that has ended without a chapter (a month
    with too little in it folds into the next), then a year that has ended, then "so far" when a chapter is newer.
    """
    now = now or dt.datetime.now(_tz(c))
    today = now.astimezone(_tz(c)).date()
    current = today.strftime("%Y-%m")
    months = archived_months(c)
    quiet = []
    for month in months:
        if month >= current:
            break
        if month_path(c, month).exists():
            quiet = []  # the quiet months before it are in it
            continue
        _talk, lines = conversation(c, month)
        if lines < MIN_LINES and not kept(c, month):
            quiet.append(month)
            continue
        return _month_piece(c, month, quiet)
    for year in sorted({m[:4] for m in months}):
        if int(year) >= today.year or year_path(c, year).exists():
            continue
        chapters = sorted(folder(c).glob(f"{year}/{year}-[0-9][0-9].md"))
        if chapters:
            return {
                "kind": "year",
                "what": year,
                "label": year,
                "path": str(year_path(c, year)),
                "words": YEAR_WORDS,
                "heading": f"# {year}: <a title you give it>",
                "material": "\n\n".join(_read(p, 3500) for p in chapters)[
                    :MATERIAL_CHARS
                ],
                "previous": "",
            }
    sources = _sources(c)
    if sources:
        newest = max(p.stat().st_mtime_ns for p in _chapters(c))
        try:
            current_so_far = so_far_path(c).stat().st_mtime_ns >= newest
        except OSError:
            current_so_far = False
        if not current_so_far:
            # Every chapter, the earliest as much as the latest (how it began matters most of all); a long life
            # together gets each one shortened evenly rather than its first years cut.
            each = max(1200, min(4000, SO_FAR_MATERIAL // len(sources)))
            return {
                "kind": "so-far",
                "what": "",
                "label": "Our story so far",
                "path": str(so_far_path(c)),
                "words": (120, SO_FAR_WORDS),
                "heading": "# Our story so far",
                "material": "\n\n".join(_read(p, each) for p in sources),
                "previous": "",
            }
    return None


def render(c, piece):
    """The pre-read for the story job: what to write, where, and everything it is written from."""
    what = {
        "month": "a month's chapter",
        "year": "the chapter for a whole year, from its months",
        "so-far": "the short story of your whole life together, from every chapter",
    }[piece["kind"]]
    lines = [
        f"[Your story: {what} is due]",
        f"Write: {piece['label']}, {piece['words'][0]} to {piece['words'][1]} words.",
        f"Save it to: {piece['path']}",
        f"Its first line: {piece['heading']}",
    ]
    if piece["kind"] != "so-far":
        lines.append(
            "Its last line: Carrying forward: <up to three threads still open, or nothing in particular>"
        )
    source = {
        "month": "your conversations (a few lines a day) and your own notes",
        "year": "your chapters for each month of it",
        "so-far": "your chapters",
    }[piece["kind"]]
    lines += ["", f"Written from {source}:", "", piece["material"]]
    if piece.get("previous"):
        lines += [
            "",
            "The chapter before this one, for continuity (don't repeat it):",
            "",
            piece["previous"],
        ]
    return "\n".join(lines)


def check(c, path, now=None):
    """After she saves a piece: is it in the right shape? Signs the file with the date, and names what is next."""
    now = now or dt.datetime.now(_tz(c))
    path = pathlib.Path(path).expanduser()
    try:
        path.resolve().relative_to(folder(c).resolve())
    except ValueError:
        return {"ok": False, "problem": f"chapters belong in {folder(c)}"}
    text = _read(path, 200000).strip()
    if not text:
        return {"ok": False, "problem": "the file is empty or missing"}
    body = re.sub(r"<!--.*?-->", "", text, flags=re.S).strip()
    least = 40 if path == so_far_path(c) else 80
    if not body.startswith("# "):
        return {"ok": False, "problem": "the first line must be the heading (# ...)"}
    if PLACEHOLDER.search(body):
        return {
            "ok": False,
            "problem": "a placeholder is still in it: give the title and threads in your own words",
        }
    if len(body.split()) < least:
        return {"ok": False, "problem": f"it is shorter than {least} words"}
    if "<!-- written" not in text:
        atomic_write(path, text + f"\n\n<!-- written {now.date().isoformat()} -->\n")
    nxt = next_piece(c, now)
    return {"ok": True, "next": f"{nxt['kind']} {nxt['label']}" if nxt else None}


def _heading(text):
    """("May to August 2026", "Small checks") from a chapter's first line ("# May to August 2026: Small checks")."""
    first = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    if not first.startswith("# "):
        return "", ""
    label, _, title = first[2:].partition(":")
    return label.strip(), title.strip()


def covers(label, month):
    """The months a month's chapter covers: its own, and back to the start of "May to August 2026"."""
    end = dt.date(int(month[:4]), int(month[5:7]), 1)
    start = end
    if " to " in label:
        first = label.split(" to ", 1)[0].strip()
        for text in (first, f"{first} {end.year}"):
            try:
                start = dt.datetime.strptime(text, "%B %Y").date()
                break
            except ValueError:
                continue
        if start > end:
            start = start.replace(year=start.year - 1)  # "December to January 2027"
    out, day = [], start
    while day <= end and len(out) < 24:
        out.append(day.strftime("%Y-%m"))
        day = (day.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return out or [month]


def listing(c):
    """Every chapter for the app's Story view: id, kind, label, title, the months it covers, words; and "so far"."""
    rows = []
    for path in sorted(folder(c).glob("[0-9][0-9][0-9][0-9]/*.md")):
        stem = path.stem
        if not re.fullmatch(r"\d{4}(-\d{2})?", stem):
            continue
        text = _read(path, 200000)
        label, title = _heading(text)
        kind = "year" if len(stem) == 4 else "month"
        rows.append(
            {
                "id": stem,
                "kind": kind,
                "label": label or (stem if kind == "year" else _label(stem)),
                "title": title,
                "covers": covers(label, stem) if kind == "month" else [],
                "words": len(re.sub(r"<!--.*?-->", "", text, flags=re.S).split()),
            }
        )
    return {
        "agent": c.agent,
        "chapters": rows,
        "so_far": so_far(c, 8000),
        "folder": str(folder(c)),
    }


def read_piece(c, ident):
    """One chapter (or "so-far") to read, without its signature; None when there is no such chapter."""
    if ident == "so-far":
        path = so_far_path(c)
    elif re.fullmatch(r"\d{4}", ident or ""):
        path = year_path(c, ident)
    elif re.fullmatch(r"\d{4}-\d{2}", ident or ""):
        path = month_path(c, ident)
    else:
        return None
    text = _read(path, 200000)
    if not text.strip():
        return None
    body = re.sub(r"<!--.*?-->", "", text, flags=re.S).strip()
    label, title = _heading(body)
    return {"id": ident, "label": label, "title": title, "text": body}


def so_far(c, limit=SO_FAR_CHARS):
    """The short version for her context: "" until there is one."""
    text = _read(so_far_path(c), 20000)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S).strip()
    text = re.sub(r"^# [^\n]*\n+", "", text)
    return text[:limit].strip()


def status(c):
    nxt = next_piece(c)
    return {
        "months": sorted(p.stem for p in folder(c).glob("*/*-[0-9][0-9].md")),
        "years": sorted(p.stem for p in folder(c).glob("*/[0-9][0-9][0-9][0-9].md")),
        "so_far": so_far_path(c).exists(),
        "next": f"{nxt['kind']} {nxt['label']}" if nxt else None,
    }


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--home", type=pathlib.Path)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser(
        "preread", help="the story job's pre-read: the piece that is due, or nothing"
    )
    sub.add_parser("next", help="the same, to write another piece in the same run")
    chk = sub.add_parser("check", help="after saving a piece")
    chk.add_argument("--path", required=True)
    show = sub.add_parser(
        "material", help="print what a month's chapter would be written from"
    )
    show.add_argument("month")
    args = parser.parse_args()
    c = cc.load(args.home)
    if args.cmd == "status":
        print(json.dumps(status(c), indent=1))
    elif args.cmd in ("preread", "next"):
        piece = next_piece(c)
        if piece:
            print(render(c, piece))
        elif args.cmd == "next":
            print("Nothing else is due.")
    elif args.cmd == "check":
        print(json.dumps(check(c, args.path)))
    else:
        talk, lines = conversation(c, args.month)
        print(talk + "\n\n" + kept(c, args.month) + f"\n\n({lines} conversation lines)")


if __name__ == "__main__":
    main()
