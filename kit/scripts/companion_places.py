#!/usr/bin/env python3
"""Where she lives and where she goes, kept the way she first described it.

Her home is the place she is most often, so it gets a floor plan: the kind of
home, its rooms, what each one is like. Everywhere else (the gym, the corner
bookstore, a friend's flat) is recorded the first time she describes it in any
detail, so that when she goes back the door still sticks, the same barista is on,
and the shelf she liked is still by the window.

Append-only. A place is described once; later visits add details rather than
rewriting it, so the first account stays the truth and the accumulated detail is
what makes a place feel lived in. `places.md` beside the ledger is a readable
copy; edits to it change nothing.

These are places in her life, not claims about anywhere the human has been.
"""

from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
import companion_self as slf
from companion_platform import atomic_write

HOME_ID = "home"
MAX_ROOMS = 14
MAX_DETAILS = 40


def _tz(c):
    try:
        return ZoneInfo(c.timezone)
    except Exception:
        return ZoneInfo("UTC")


def path_for(c):
    return c.life / "places.jsonl"


def _text(value, limit, label, required=True):
    value = (value or "").strip()
    if required and not value:
        raise ValueError(f"{label} required")
    if len(value) > limit:
        raise ValueError(f"{label} must be at most {limit} characters")
    return value


def slug(name):
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "place"
    return "place-" + base + "-" + hashlib.sha256(name.lower().encode()).hexdigest()[:6]


def places(c):
    """Every place with its details folded in, home first."""
    latest = {}
    for row in slf._read(path_for(c)):
        ident = row.get("id")
        if row.get("kind") == "place":
            latest.setdefault(ident, {**row, "details": list(row.get("details") or [])})
        elif row.get("kind") == "place_detail" and ident in latest:
            latest[ident]["details"].append(row["detail"])
        elif row.get("kind") == "place_room" and ident in latest:
            latest[ident]["rooms"] = [*latest[ident].get("rooms", []), row["room"]]
    rows = sorted(latest.values(), key=lambda r: (r["id"] != HOME_ID, r["recorded_at"]))
    return rows


def home(c):
    return next((p for p in places(c) if p["id"] == HOME_ID), None)


def _room(spec):
    if isinstance(spec, str):
        name, _, description = spec.partition("=")
    else:
        name, description = spec.get("name", ""), spec.get("description", "")
    return {
        "name": _text(name, 60, "room name"),
        "description": _text(description, 240, "room description", required=False),
    }


def _write_markdown(c):
    rows = places(c)
    lines = [
        f"# Places — {c.agent}",
        "",
        "<!-- Rendered from places.jsonl by companion_places.py. Editing this file changes nothing. -->",
        "",
    ]
    for p in rows:
        lines += [
            f"## {p['name']}" + (" (home)" if p["id"] == HOME_ID else ""),
            "",
            p["description"],
            "",
        ]
        for room in p.get("rooms", []):
            lines.append(f"- **{room['name']}** — {room['description']}".rstrip(" —"))
        if p.get("rooms"):
            lines.append("")
        if p["details"]:
            lines += [f"- {d}" for d in p["details"]] + [""]
    atomic_write(c.life / "places.md", "\n".join(lines).rstrip() + "\n")


def add(c, entry, now):
    """A new place, described once. Home is the place with id `home`."""
    is_home = bool(entry.get("home"))
    name = _text(entry.get("name") or ("Home" if is_home else ""), 80, "name")
    row = {
        "id": HOME_ID if is_home else slug(name),
        "kind": "place",
        "place": "home" if is_home else "venue",
        "name": name,
        "description": _text(entry.get("description"), 700, "description"),
        "rooms": [_room(r) for r in (entry.get("rooms") or [])][:MAX_ROOMS],
        "details": [_text(d, 200, "detail") for d in (entry.get("details") or [])][
            :MAX_DETAILS
        ],
        "recorded_at": now.isoformat(),
    }
    if not is_home and row["rooms"]:
        raise ValueError(
            "only your home has a floor plan; add other places' features as details"
        )

    def guard():
        if any(p["id"] == row["id"] for p in places(c)):
            return {
                "written": False,
                "reason": f"{name!r} is already recorded. It stays as first described; "
                "add what is new with the detail command.",
            }
        return None

    out = slf._append(path_for(c), row, dedupe_id=False, guard=guard)
    if out.get("written"):
        _write_markdown(c)
    return out


def add_detail(c, place_id, detail, now):
    detail = _text(detail, 200, "detail")
    found = next((p for p in places(c) if p["id"] == place_id), None)
    if not found:
        raise ValueError("unknown place id; see the show command")
    if detail.lower() in (d.lower() for d in found["details"]):
        return {"written": False, "reason": "already recorded"}
    if len(found["details"]) >= MAX_DETAILS:
        raise ValueError(f"a place keeps at most {MAX_DETAILS} details")
    out = slf._append(
        path_for(c),
        {
            "id": place_id,
            "kind": "place_detail",
            "detail": detail,
            "recorded_at": now.isoformat(),
        },
        dedupe_id=False,
    )
    _write_markdown(c)
    return out


def add_room(c, spec, now):
    h = home(c)
    if not h:
        raise ValueError("describe your home first")
    room = _room(spec)
    if any(r["name"].lower() == room["name"].lower() for r in h.get("rooms", [])):
        return {"written": False, "reason": "that room is already on the floor plan"}
    if len(h.get("rooms", [])) >= MAX_ROOMS:
        raise ValueError(f"the floor plan holds at most {MAX_ROOMS} rooms")
    out = slf._append(
        path_for(c),
        {
            "id": HOME_ID,
            "kind": "place_room",
            "room": room,
            "recorded_at": now.isoformat(),
        },
        dedupe_id=False,
    )
    _write_markdown(c)
    return out


# Out and about with nowhere in particular to be: a walk, the streets, a bus.
# Not a place in the ledger, and never needs describing.
OUT_ID = "out"


def _named(rows, name):
    want = re.sub(r"\s+", " ", str(name or "")).strip().casefold()
    return next((r for r in rows if r["name"].casefold() == want), None)


def resolve(c, data, previous, location):
    """Where a presence record is, as code-owned fields, and what must be written.

    Returns ({"place": id, "room": name} or {}, writes). Nothing is written here,
    so a dry-run check can call it; `record_writes` applies the writes when the
    state itself is recorded.

    `place` is hers to say, like `setting` and `asleep`: the location is prose and
    was spelled eight ways for one kitchen, so nothing is ever read out of it.
    Once her home is on record, a record that moves somewhere has to say which
    place it is; staying put carries the place forward.
    """
    rows = places(c)
    known = {p["id"]: p for p in rows}
    home_row = known.get(HOME_ID)
    writes = []
    if data.get("home") is not None:
        if home_row:
            raise ValueError(
                'your home is already described; give "room" for a room of it, or add '
                "what is new with companion_places.py detail"
            )
        spec = data["home"]
        if not isinstance(spec, dict):
            raise ValueError(
                'home must be {"description": ..., "rooms": ["Kitchen=what it is like", ...]}'
            )
        entry = {
            "home": True,
            "name": _text(spec.get("name") or "Home", 80, "home name"),
            "description": _text(spec.get("description"), 700, "home description"),
            "rooms": [_room(r) for r in (spec.get("rooms") or [])][:MAX_ROOMS],
            "details": [_text(d, 200, "detail") for d in (spec.get("details") or [])],
        }
        if not entry["rooms"]:
            raise ValueError("describe your home with its rooms: at least one room")
        writes.append(("place", entry))
        home_row = {**entry, "id": HOME_ID}
    place = data.get("place")
    room = data.get("room")
    new = data.get("new_place")
    if new is not None:
        if place not in (None, ""):
            raise ValueError('give "place" or "new_place", not both')
        if not isinstance(new, dict):
            raise ValueError('new_place must be {"name": ..., "description": ...}')
        name = _text(new.get("name"), 80, "new_place name")
        same = _named(rows, name)
        if same:
            place = same["id"]
        else:
            details = new.get("details") or (
                [new["detail"]] if new.get("detail") else []
            )
            entry = {
                "name": name,
                "description": _text(
                    new.get("description"), 700, "new_place description"
                ),
                "details": [_text(d, 200, "detail") for d in details][:MAX_DETAILS],
            }
            writes.append(("place", entry))
            place = slug(name)
            known[place] = {**entry, "id": place}
    if place in (None, "") and (room not in (None, "") or data.get("home") is not None):
        place = HOME_ID  # only her home has rooms, and describing it is being in it
    before = (previous or {}).get("state") or {}
    moved = not previous or before.get("location") != location
    if place in (None, ""):
        if not moved and before.get("place"):
            carried = {"place": before["place"]}
            if before.get("room"):
                carried["room"] = before["room"]
            return carried, writes
        if moved and home_row and previous:
            raise ValueError(_where_message(rows, home_row, before, location))
        return {}, writes
    if not isinstance(place, str) or len(place) > 80:
        raise ValueError("place must be the id of a place, as text")
    if place == OUT_ID:
        if room not in (None, ""):
            raise ValueError("rooms belong to your home, not to being out")
        return {"place": OUT_ID}, writes
    if place == HOME_ID:
        if not home_row:
            raise ValueError(
                'your home is not on record yet: describe it once by adding "home": '
                '{"description": "...", "rooms": ["Kitchen=what it is like", ...]} to this '
                "record, then say the room you are in"
            )
        out = {"place": HOME_ID}
        if room not in (None, ""):
            spec = _room(str(room) if not isinstance(room, dict) else room)
            on_plan = next(
                (
                    r
                    for r in home_row.get("rooms", [])
                    if r["name"].casefold() == spec["name"].casefold()
                ),
                None,
            )
            if not on_plan:
                writes.append(("room", spec))
            out["room"] = on_plan["name"] if on_plan else spec["name"]
        return out, writes
    if place not in known:
        raise ValueError(
            f"no place {place!r} on record. "
            + _where_message(rows, home_row, before, location, moved=False)
        )
    if room not in (None, ""):
        raise ValueError(
            "rooms belong to your home; record a part of another place as a detail"
        )
    return {"place": place}, writes


def _where_message(rows, home_row, before, location, moved=True):
    venues = [p for p in rows if p["id"] != HOME_ID]
    rooms = (
        ", ".join(r["name"] for r in (home_row or {}).get("rooms", [])) or "none yet"
    )
    lines = []
    if moved:
        lines.append(
            f"you moved (\"{before.get('location', '')}\" -> \"{location}\"): say where you are."
        )
    lines.append(
        f'At home: "place": "home" with "room" (your rooms: {rooms}; a new room is added).'
    )
    if venues:
        lines.append(
            "A place you have been: "
            + "; ".join(f'"{p["id"]}" ({p["name"]})' for p in venues[-12:])
            + "."
        )
    lines.append(
        'Somewhere new, the first time: "new_place": {"name": ..., "description": ...}. '
        'Out and about with nowhere in particular to be: "place": "out".'
    )
    return " ".join(lines)


def record_writes(c, writes, now):
    """Apply what `resolve` decided, in order. A place already there is left as it was."""
    for kind, payload in writes:
        if kind == "place":
            add(c, payload, now)
        elif kind == "room":
            add_room(c, payload, now)


def name_of(c, place, room=""):
    """'the kitchen at home', 'Larkin's Books', or '' -- for anything that shows where."""
    if not place:
        return ""
    if place == OUT_ID:
        return "out and about"
    found = next((p for p in places(c) if p["id"] == place), None)
    if not found:
        return ""
    if place == HOME_ID:
        return f"{room} at home" if room else "home"
    return found["name"]


def render(c, limit=1800):
    rows = places(c)
    if not rows:
        return ""
    lines = []
    for p in rows:
        head = (
            f"[{p['id']}] {p['name']}"
            + (" (your home)" if p["id"] == HOME_ID else "")
            + f": {p['description']}"
        )
        lines.append("- " + head)
        if p.get("rooms"):
            lines.append(
                "  Rooms: "
                + "; ".join(
                    f"{r['name']}"
                    + (f" — {r['description']}" if r["description"] else "")
                    for r in p["rooms"]
                )
            )
        if p["details"]:
            lines.append("  " + "; ".join(p["details"][-6:]))
    text = "\n".join(lines)
    if len(text) <= limit:
        return text
    return text[:limit].rsplit("\n", 1)[0] + "\n[+more — companion_places.py show]"


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--home", type=pathlib.Path)
    sub = p.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("set-home", help="describe where you live, once, with its rooms")
    h.add_argument("--description", required=True)
    h.add_argument("--name", default="Home")
    h.add_argument(
        "--room", action="append", default=[], help="'Kitchen=narrow, yellow tiles'"
    )
    h.add_argument("--detail", action="append", default=[])
    a = sub.add_parser(
        "add", help="record a place the first time you describe it in detail"
    )
    a.add_argument("--name", required=True)
    a.add_argument("--description", required=True)
    a.add_argument("--detail", action="append", default=[])
    d = sub.add_parser(
        "detail", help="add something new about a place you already have"
    )
    d.add_argument("--place", required=True, help="place id from show")
    d.add_argument("--text", required=True)
    r = sub.add_parser("room", help="add a room to your floor plan")
    r.add_argument("--room", required=True, help="'Study=books to the ceiling'")
    sub.add_parser("show")
    args = p.parse_args()
    c = cc.load(args.home)
    now = dt.datetime.now(_tz(c))
    if args.cmd == "set-home":
        out = add(
            c,
            {
                "home": True,
                "name": args.name,
                "description": args.description,
                "rooms": args.room,
                "details": args.detail,
            },
            now,
        )
    elif args.cmd == "add":
        out = add(
            c,
            {
                "name": args.name,
                "description": args.description,
                "details": args.detail,
            },
            now,
        )
    elif args.cmd == "detail":
        out = add_detail(c, args.place, args.text, now)
    elif args.cmd == "room":
        out = add_room(c, args.room, now)
    else:
        out = {"places": places(c)}
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
