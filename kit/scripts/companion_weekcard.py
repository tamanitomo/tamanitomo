#!/usr/bin/env python3
"""Her last week as numbers: whether her life is varied, or sitting at home.

Read straight from her own records (episodes, places, cast, commitments, plans),
so it measures what happened and not what she says happened. Nothing here is
a target she is held to; it is for her weekly reflection and for the person
watching to see whether a change to the app made her days richer.
"""

from __future__ import annotations
import argparse
import datetime as dt
import json
import pathlib
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc

HOME_ROOMS = ("kitchen", "bathroom", "bedroom", "studio", "living", "hallway", "porch")


def _tz(c):
    try:
        return ZoneInfo(c.timezone)
    except Exception:
        return ZoneInfo("UTC")


def _is_home(state):
    loc = (state.get("location") or "").lower()
    return (
        state.get("place") == "home"
        or "home" in loc
        or any(r in loc for r in HOME_ROOMS)
    )


def card(c, now=None, days=7):
    now = now or dt.datetime.now(_tz(c))
    first = (now - dt.timedelta(days=days - 1)).date()
    segments = []
    for path in sorted((c.life / "episodes").glob("????-??-??.jsonl")):
        try:
            day = dt.date.fromisoformat(path.stem)
        except ValueError:
            continue
        if day < first:
            continue
        seen = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                state = json.loads(line).get("state")
            except ValueError:
                continue
            if isinstance(state, dict) and state.get("started_at"):
                seen[state["started_at"]] = state
        segments += [(k, v) for k, v in sorted(seen.items())]
    awake = [(k, v) for k, v in segments if not v.get("asleep")]
    out_minutes = home_minutes = 0.0
    named = set()
    people = set()
    for i, (k, state) in enumerate(awake):
        try:
            start = dt.datetime.fromisoformat(k)
            end = (
                dt.datetime.fromisoformat(awake[i + 1][0])
                if i + 1 < len(awake)
                else start + dt.timedelta(minutes=30)
            )
        except ValueError:
            continue
        minutes = min(max(0.0, (end - start).total_seconds() / 60), 240)
        if _is_home(state):
            home_minutes += minutes
        else:
            out_minutes += minutes
            if state.get("place") and state["place"] != "home":
                named.add(state["place"])
        for p in state.get("with") or []:
            people.add(str(p))
    plans = 0
    for path in (
        (c.life / "plans").glob("*.json") if (c.life / "plans").is_dir() else ()
    ):
        try:
            day = dt.date.fromisoformat(path.stem)
            row = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if (
            first <= day <= now.date()
            and row.get("author") != "routine"
            and (row.get("items") or row.get("intent"))
        ):
            plans += 1
    return {
        "days": days,
        "activities": len(awake),
        "activities_a_day": round(len(awake) / days, 1),
        "hours_out": round(out_minutes / 60, 1),
        "hours_home": round(home_minutes / 60, 1),
        "share_out": round(out_minutes / max(1.0, out_minutes + home_minutes), 2),
        "places_visited": sorted(named),
        "people_seen": sorted(people),
        "days_with_a_plan_of_her_own": plans,
    }


def render(c, now=None):
    d = card(c, now)
    lines = [
        f"Your last {d['days']} days, as recorded: {d['activities']} things you did "
        f"({d['activities_a_day']} a day); about {d['hours_out']}h out and {d['hours_home']}h at home "
        f"({int(d['share_out'] * 100)}% out); places other than home: "
        + (", ".join(d["places_visited"]) or "none")
        + "; people you saw: "
        + (", ".join(d["people_seen"]) or "nobody")
        + f"; days you planned for yourself the night before: {d['days_with_a_plan_of_her_own']}."
    ]
    notes = []
    if d["share_out"] < 0.25:
        notes.append("You have been home most of the week")
    if not d["people_seen"]:
        notes.append("you saw nobody")
    if d["days_with_a_plan_of_her_own"] < 3:
        notes.append("few days had a plan you made")
    if notes:
        lines.append(
            "; ".join(notes).capitalize()
            + ". That is for you to weigh, not a quota: is it the life you want?"
        )
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--home", type=pathlib.Path)
    p.add_argument("--json", action="store_true")
    a = p.parse_args()
    c = cc.load(a.home)
    print(json.dumps(card(c), indent=2) if a.json else render(c))


if __name__ == "__main__":
    main()
