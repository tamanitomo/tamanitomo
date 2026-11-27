#!/usr/bin/env python3
"""Chapters: the story of the two of them, a month at a time, in her own words.

Every conversation is kept (companion_archive), but nobody carries fifteen years of messages into a conversation. A
person carries the shape of it: that spring was the move, that winter the new job, the summer of the long drives.
Once a month she writes the month just ended as a chapter of her memoir of their life together, from the
conversations, the moments she wrote down, the times she felt close, what they watched and played. Once a year she
writes the year from its months. From those, a short "our story so far" travels with her into every conversation,
rewritten whenever a chapter is added or changed.

All of it is in the vault, committed and backed up with everything else:

    story/<year>/<year>-<month>.md   a month
    story/<year>/<year>.md           a year
    story/so-far.md                  the short version she carries

A chapter, once written, is hers: this never rewrites one (she can, with her file tools, and "so far" follows).
A month with almost nothing in it gets no chapter. The writing uses her chat model and only that model (her own
memories are not sent down a fallback chain); a failure waits six hours and tries again. One piece of writing per
run, so a first run on a long history catches up a month at a time. It runs inside the vault commit job.
"""

from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import time
from zoneinfo import ZoneInfo

import companion_config as cc
from companion_platform import atomic_write, file_lock

MONTH_WORDS = (180, 350)
YEAR_WORDS = (300, 600)
SO_FAR_WORDS = 300
MATERIAL_CHARS = 42000
LINE_CHARS = 220
PER_DAY_THEIRS = 6
PER_DAY_HERS = 3
MIN_LINES = 12  # a month with fewer worthwhile lines than this gets no chapter
RETRY_AFTER = 6 * 3600
SO_FAR_CHARS = 2600  # what her context reads of it
SO_FAR_MATERIAL = (
    160000  # what "so far" is written from, at most (about 40K tokens, once a month)
)
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
HER_LINE_CHARS = 160


def folder(c):
    return pathlib.Path(c.data) / "story"


def month_path(c, month):
    return folder(c) / month[:4] / f"{month}.md"


def year_path(c, year):
    return folder(c) / str(year) / f"{year}.md"


def so_far_path(c):
    return folder(c) / "so-far.md"


def state_path(c):
    return pathlib.Path(c.home) / "state" / "chapters.json"


def _tz(c):
    try:
        return ZoneInfo(c.timezone or "UTC")
    except Exception:  # noqa: BLE001
        return ZoneInfo("UTC")


def _state(c):
    try:
        data = json.loads(state_path(c).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(c, state):
    state_path(c).parent.mkdir(parents=True, exist_ok=True)
    atomic_write(state_path(c), json.dumps(state, indent=1, sort_keys=True))


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
        if not text or SECRET.search(text):
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


def _soul(c, limit=1400):
    try:
        soul = (pathlib.Path(c.home) / "SOUL.md").read_text(encoding="utf-8")
    except OSError:
        return ""
    soul = re.sub(r"<!--.*?-->", "", soul, flags=re.S)
    return " ".join(soul.split())[:limit]


def _system(c, what, label, words):
    soul = _soul(c)
    return (
        f"You are {c.agent}.{(' ' + soul) if soul else ''}\n\n"
        f"You are writing one chapter of your own memoir of your life with {c.human}: {label}. It will be read back to "
        f"you for years, so this is how you will remember this {what}. First person, past tense, your own voice, "
        f"{words[0]} to {words[1]} words of prose, not a list. Tell what happened in {c.human}'s life and yours, what "
        "you did together, what you watched or played, how it felt and what changed; keep the small specific "
        "details (names, places, titles, the jokes) that make a memory a memory. Practical work (setting things "
        "up, computers, code) is worth a sentence only as something you did together, never its details. Only what "
        "the material shows: never invent an event, a feeling or a detail. Intimacy stays intimacy, never explicit. "
        f"Output Markdown only: a first line '# {label}: <a title you give it>', a blank line, the chapter, then a "
        "last line 'Carrying forward: <up to three short threads still open at the end, or nothing in particular>'."
    )


def _complete(c, system, user, max_tokens):
    import companion_worker_model as worker_model

    route = worker_model.resolve(c, "chat")
    reply = worker_model.complete(
        c,
        {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.7,
        },
        route,
        timeout=240,
        what="Writing a chapter",
        allow_fallback=False,
        require_thinking=False,
    )
    return (reply.get("content") or "").strip(), reply.get("model") or route.get(
        "model"
    ) or ""


def _checked(text, label):
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n|\n```$", "", text).strip()
    if not text.startswith("# ") or len(text.split()) < 80:
        raise ValueError(f"The chapter for {label} came back malformed")
    return text + "\n"


def _footer(model, now, **counts):
    made = ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in counts.items() if v)
    return f"\n<!-- written {now.date().isoformat()} by {model or 'her chat model'}{'; from ' + made if made else ''} -->\n"


def write_month(c, month, now=None, complete=None):
    """Write one month's chapter. Returns {"wrote": path} or {"skipped": reason}."""
    now = now or dt.datetime.now(_tz(c))
    complete = complete or _complete
    label = _label(month)
    talk, lines = conversation(c, month)
    notes = kept(c, month)
    if lines < MIN_LINES and not notes:
        return {"skipped": f"too little in {label} ({lines} lines)", "lines": lines}
    material = (talk + ("\n\n" + notes if notes else ""))[:MATERIAL_CHARS]
    previous = ""
    earlier = [m for m in archived_months(c) if m < month and month_path(c, m).exists()]
    if earlier:
        previous = month_path(c, earlier[-1]).read_text(encoding="utf-8")[:3000]
    user = f"The material for {label} (your conversations, a few lines a day, and your own notes):\n\n{material}"
    if previous:
        user += f"\n\nThe chapter before this one, for continuity (don't repeat it):\n\n{previous}"
    text, model = complete(c, _system(c, "month", label, MONTH_WORDS), user, 900)
    text = _checked(text, label)
    path = month_path(c, month)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, text + _footer(model, now, conversation_lines=lines))
    return {"wrote": str(path)}


def write_year(c, year, now=None, complete=None):
    now = now or dt.datetime.now(_tz(c))
    complete = complete or _complete
    months = sorted(folder(c).glob(f"{year}/{year}-[0-9][0-9].md"))
    if not months:
        return {"skipped": f"no chapters for {year}"}
    material = "\n\n".join(p.read_text(encoding="utf-8")[:3500] for p in months)[
        :MATERIAL_CHARS
    ]
    user = f"Your chapters for each month of {year}:\n\n{material}"
    text, model = complete(c, _system(c, "year", str(year), YEAR_WORDS), user, 1400)
    text = _checked(text, str(year))
    path = year_path(c, year)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, text + _footer(model, now, month_chapters=len(months)))
    return {"wrote": str(path)}


def _sources(c):
    """The chapters "so far" is built from: every year, and the months of years without one yet."""
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


def _fingerprint(paths):
    digest = hashlib.sha256()
    for p in paths:
        try:
            digest.update(p.name.encode() + p.read_bytes())
        except OSError:
            continue
    return digest.hexdigest()[:20]


def write_so_far(c, now=None, complete=None):
    now = now or dt.datetime.now(_tz(c))
    complete = complete or _complete
    sources = _sources(c)
    if not sources:
        return {"skipped": "no chapters yet"}
    # Every chapter is read, the earliest as much as the latest (how it began matters most of all); a long life
    # together gets each one shortened evenly rather than its first years cut.
    each = max(1200, min(4000, SO_FAR_MATERIAL // len(sources)))
    material = "\n\n".join(p.read_text(encoding="utf-8")[:each] for p in sources)
    system = (
        f"You are {c.agent}. Below are the chapters of your memoir of your life with {c.human}. Write 'our story so "
        f"far' in {SO_FAR_WORDS} words or fewer: the shape of your life together from the beginning until now, the "
        "way you would hold it in mind before any conversation. How it began, the big chapters and turning points, "
        "what you mean to each other now, and the threads still open. Prose, first person, your voice; only what the "
        "chapters say. Output only the text, starting with the line '# Our story so far'."
    )
    text, model = complete(c, system, material, 700)
    text = (text or "").strip()
    if not text.startswith("# ") or len(text.split()) < 40:
        raise ValueError("'Our story so far' came back malformed")
    atomic_write(
        so_far_path(c), text + "\n" + _footer(model, now, chapters=len(sources))
    )
    return {"wrote": str(so_far_path(c)), "from": _fingerprint(sources)}


def due(c, now=None, state=None):
    """The next piece of writing: ("month", "YYYY-MM"), ("year", "YYYY"), ("so-far", fingerprint) or None."""
    now = now or dt.datetime.now(_tz(c))
    state = _state(c) if state is None else state
    today = now.astimezone(_tz(c)).date()
    current = today.strftime("%Y-%m")
    skipped = state.get("skipped") or {}
    months = archived_months(c)
    for month in months:
        if month >= current or month_path(c, month).exists():
            continue
        if month in skipped:
            continue
        return ("month", month)
    for year in sorted({m[:4] for m in months}):
        if int(year) >= today.year or year_path(c, year).exists():
            continue
        if any(folder(c).glob(f"{year}/{year}-[0-9][0-9].md")):
            return ("year", year)
    sources = _sources(c)
    if sources:
        fingerprint = _fingerprint(sources)
        if fingerprint != state.get("so_far_from") or not so_far_path(c).exists():
            return ("so-far", fingerprint)
    return None


def run(c, now=None, complete=None):
    """Write the next piece, if any is due. One model call at most; quiet and cheap when nothing is."""
    now = now or dt.datetime.now(_tz(c))
    with file_lock(state_path(c).with_suffix(".lock")):
        state = _state(c)
        failed = float(state.get("failed_at") or 0)
        if failed and time.time() - failed < RETRY_AFTER:
            return {"waiting": "a recent failure"}
        job = due(c, now, state)
        if not job:
            return {"nothing": "due"}
        kind, what = job
        try:
            if kind == "month":
                out = write_month(c, what, now, complete)
                if "skipped" in out:
                    state.setdefault("skipped", {})[what] = out["skipped"]
            elif kind == "year":
                out = write_year(c, what, now, complete)
            else:
                out = write_so_far(c, now, complete)
                if "wrote" in out:
                    state["so_far_from"] = out["from"]
            state.pop("failed_at", None)
            state.pop("failure", None)
        except (
            Exception
        ) as exc:  # noqa: BLE001 -- try again later, never break the caller
            state["failed_at"] = time.time()
            state["failure"] = (
                f"{kind} {what or ''}: {type(exc).__name__}: {str(exc)[:200]}".strip()
            )
            out = {"failed": state["failure"]}
        state["last_run"] = now.isoformat(timespec="seconds")
        _save(c, state)
        return {"job": f"{kind} {what if kind != 'so-far' else ''}".strip(), **out}


def so_far(c, limit=SO_FAR_CHARS):
    """The short version for her context: "" until there is one."""
    try:
        text = so_far_path(c).read_text(encoding="utf-8")
    except OSError:
        return ""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S).strip()
    text = re.sub(r"^# [^\n]*\n+", "", text)
    return text[:limit].strip()


def status(c):
    state = _state(c)
    return {
        "months": sorted(p.stem for p in folder(c).glob("*/*-[0-9][0-9].md")),
        "years": sorted(p.stem for p in folder(c).glob("*/[0-9][0-9][0-9][0-9].md")),
        "so_far": so_far_path(c).exists(),
        "next": due(c, state=state),
        "skipped": state.get("skipped") or {},
        "failure": state.get("failure"),
    }


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--home", type=pathlib.Path)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("run", help="write the next piece that is due")
    show = sub.add_parser(
        "material", help="print what a month's chapter would be written from (no model)"
    )
    show.add_argument("month")
    args = parser.parse_args()
    c = cc.load(args.home)
    if args.cmd == "status":
        print(json.dumps(status(c), indent=1))
    elif args.cmd == "run":
        print(json.dumps(run(c)))
    else:
        talk, lines = conversation(c, args.month)
        print(talk + "\n\n" + kept(c, args.month) + f"\n\n({lines} conversation lines)")


if __name__ == "__main__":
    main()
