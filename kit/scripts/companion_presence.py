#!/usr/bin/env python3
"""Wardrobe and lived state, with episode records as the state authority.

Deterministic boundaries belong here, not in model instructions. Every recorded
outfit must contain declared wardrobe IDs or explicit virtual tokens such as
``bathing`` and ``towel``. The writer rejects unknown IDs, duplicates, more than
20 entries, and inconsistent clothing or public/private declarations. A model
may propose a transition; it cannot make an invalid transition valid by wording
it differently. The previous episode ID is checked under the state lock so a
stale worker cannot replace a newer state.

``location``, ``activity``, ``outfit``, ``care`` and ``mood`` describe the present;
``wants`` and ``private_stance`` retain the companion's current intentions and
perspective. Emotive.md is rendered from these records rather than maintained
as a second, potentially contradictory source of truth.
"""

from __future__ import annotations
import re
import argparse
import datetime as dt
import hashlib
import json
import pathlib
import sys
from zoneinfo import ZoneInfo
import companion_config as cc
from companion_platform import atomic_write, file_lock
from companion_life import read_events, record

# Not-dressed is a state the record carries, not something a later reader infers.
# These ids stand in for wardrobe items so "she is in the shower" survives as data
# instead of having to be guessed from the sentence describing the scene.
VIRTUAL_TOKENS = {
    "nude": "undressed",
    "undressed": "undressed",
    "bathing": "in the bath/shower",
    "towel": "wrapped in a bath towel",
}
# The ones that mean nothing is being worn, as opposed to very little.
BARE_TOKENS = ("nude", "undressed", "bathing")


# Being in the water, as opposed to being near it or dressed for it. Deliberately
# narrow, and used for one thing only: refusing a record that says she is bathing
# while listing the clothes she is wearing. "sunbathing" has no word break before
# "bathing", and a bathing suit, a bathroom and a shower that is being cleaned are
# all excluded, because each of them is a thing done with clothes on.
BATHING_ACTIVITY = re.compile(
    r"\b(?:in|under|taking|having|getting|steps?|stepping|stood|standing)\b[^.,;]{0,24}"
    r"\b(?:shower|bath|tub)\b(?!\s*(?:suit|costume|room|mat|robe))"
    r"|\bshowering\b|\bbathing\b(?!\s*(?:suit|costume))|\bsoaking in\b",
    re.I,
)


# Where she is, as she declares it. A code-owned field like `asleep`: the rules about
# being undressed or in pyjamas somewhere she could be seen read THIS, never the
# words of the location. Substring-matching the location read "Home Depot" and a
# "public bathroom at the mall" as home, and "carpool" as a swim -- the fifth time
# prose decided something in this file. Absent, it carries forward while she stays
# where she is; once she moves it is unknown until she says, and unknown is never
# treated as private.
SETTINGS = ("private", "public")
# Words are kept for one job only: noticing a declaration that plainly disagrees
# with where she says she is, so she can be asked to correct it. Whole words only.
PUBLIC_PLACES = {
    "office",
    "library",
    "park",
    "street",
    "pavement",
    "sidewalk",
    "cafe",
    "restaurant",
    "mall",
    "shop",
    "store",
    "market",
    "supermarket",
    "grocery",
    "gym",
    "pool",
    "beach",
    "bus",
    "train",
    "station",
    "airport",
    "museum",
    "cinema",
    "theatre",
    "bar",
    "pub",
    "clinic",
    "hospital",
    "school",
    "campus",
    "workplace",
    "salon",
    "studio",
    "church",
    "stadium",
}
PRIVATE_PLACES = {
    "home",
    "house",
    "apartment",
    "flat",
    "bedroom",
    "bathroom",
    "ensuite",
    "room",
    "changing",
    "fitting",
    "cabin",
    "tent",
    "hotel",
}


def in_public(state):
    """Whether she is somewhere she could be seen: her own declaration, nothing else."""
    return (state or {}).get("setting") == "public"


def reads_public(location):
    """True only when the location's words name a public place and no private one."""
    words = set(re.findall(r"[a-z]+", (location or "").lower()))
    return bool(words & PUBLIC_PLACES) and not (words & PRIVATE_PLACES)


# What each piece of clothing covers. Kit-generated closet ids are code-owned, so
# their shape is known; anything else declares `covers` or falls back by category.
COVERS = ("top", "bottom", "full", "none")
STARTER_COVERS = (
    ("closet-pajamas-", "full"),
    ("closet-sports-bra-", "top"),
    ("closet-training-vest-", "top"),
    ("closet-training-bottoms-", "bottom"),
    ("closet-day-top-", "top"),
    ("closet-day-bottoms-", "bottom"),
    ("closet-underwear-", "none"),
    ("closet-socks-", "none"),
    ("closet-cardigan", "top"),
    ("closet-trainers", "none"),
    ("closet-jeans", "bottom"),
    ("closet-shorts", "bottom"),
    ("closet-occasion", "full"),
    ("closet-swimwear", "full"),
)
# A piece nobody described keeps the old reading -- it covers -- except where the
# category says plainly that it cannot.
CATEGORY_COVERS = {
    "underwear": "none",
    "footwear": "none",
    "outerwear": "top",
    "sleep": "full",
    "active": "full",
    "day": "full",
}


def covers_of(item, closet=None):
    """top, bottom, full or none, for a worn entry or a wardrobe item."""
    if isinstance(item, str):
        item = {"id": item}
    if not isinstance(item, dict):
        return "full"
    known = (closet or {}).get(item.get("id")) if isinstance(closet, dict) else None
    for source in (item, known or {}):
        if source.get("covers") in COVERS:
            return source["covers"]
    ident = str(item.get("id") or "")
    for prefix, value in STARTER_COVERS:
        if ident.startswith(prefix):
            return value
    category = item.get("category") or (known or {}).get("category")
    return CATEGORY_COVERS.get(category, "full")


def _closet_map(closet):
    if isinstance(closet, dict):
        return closet
    return {i.get("id"): i for i in (closet or ()) if isinstance(i, dict)}


def undress(state, closet=()):
    """What the record says she has on: ('undressed'|'bathing'|'towel'|'underwear'|None, text).

    Read from outfit ids and what each piece covers, never from prose. Sniffing
    `activity` and `location` for "bath" stripped the clothes off anyone brushing
    their teeth in the bathroom, sunbathing, or shopping for a bathing suit.

    'underwear' means nothing she has on covers her hips: underwear alone, or with
    socks, a cardigan or a top. Socks used to count as clothes, so underwear and
    socks was "dressed" and was photographed as "wearing socks".
    """
    # Both shapes reach this: a stored state holds {'id','description'} pairs, while a
    # validator sees the raw id list the update was written with.
    items = state.get("outfit") or []
    ids = {i.get("id", "") if isinstance(i, dict) else str(i) for i in items}
    text = ", ".join(
        i["description"] for i in items if isinstance(i, dict) and i.get("description")
    )
    if not items:
        return "undressed", ""
    for token in BARE_TOKENS:
        if token in ids:
            return ("bathing" if token == "bathing" else "undressed"), ""
    if "towel" in ids:
        return "towel", text
    known = _closet_map(closet)
    worn = [
        i
        for i in items
        if (i.get("id") if isinstance(i, dict) else i) not in VIRTUAL_TOKENS
    ]
    if not any(covers_of(i, known) in ("bottom", "full") for i in worn):
        return "underwear", text
    return None, text


# Moments the camera treats as private unless the adult gate is open. Her own
# `private: true` is a different thing and is never overridden.
UNDRESSED_KINDS = ("undressed", "bathing", "towel", "underwear")


def private_reason(state, closet=()):
    """'declared' when she marked the moment private, 'undressed' when her outfit
    makes it so, else None. Only the second can be unlocked by permissions."""
    if (state or {}).get("private"):
        return "declared"
    if undress(state or {}, closet)[0] in UNDRESSED_KINDS:
        return "undressed"
    return None


BASE_LAYERS = ("underwear",)
# Shoes do not cover anything, so a pair of trainers must not be the reason a
# base layer is treated as hidden.
COVERS_NOTHING = ("footwear",)


def visible_outfit(state, closet=()):
    """The clothes a camera would see, rather than every layer she has on.

    An outfit is a stack. Handing the whole stack to an image model describes
    it all at once and it obligingly draws all of it, so a record of jeans over
    briefs came back as briefs riding up out of the jeans -- in every picture,
    because she is wearing underwear in every picture.

    A base layer is left out only when something she has on actually covers her
    hips, which `undress` decides from what each piece covers. Socks, shoes, a
    cardigan or a top alone cover nothing there: that outfit is 'underwear' and is
    described in full, never as "wearing socks".
    """
    kind, text = undress(state, closet)
    if kind:
        return kind, text
    known = _closet_map(closet)

    def base(item):
        cat = item.get("category") or (known.get(item.get("id")) or {}).get("category")
        return cat in BASE_LAYERS or str(item.get("id", "")).startswith(
            "closet-underwear-"
        )

    items = [i for i in (state.get("outfit") or []) if isinstance(i, dict)]
    return kind, ", ".join(
        i["description"] for i in items if i.get("description") and not base(i)
    )


def wardrobe_clause(text):
    """`wearing X`, unless the description already reads as its own phrase.

    Without this the towel produced "wearing wrapped in a bath towel" in the
    prompt sent to the image model.
    """
    if not text:
        return ""
    return (
        text
        if text.split()[0] in ("wrapped", "in", "wearing", "dressed", "covered")
        else "wearing " + text
    )


def events(c):
    for path in sorted((c.life / "episodes").glob("????-??-??.jsonl"), reverse=True):
        for row in reversed(read_events(c.life, path.stem, limit=0)):
            if isinstance(row.get("state"), dict):
                yield row


def current(c):
    return next(events(c), None)


def wardrobe(c):
    path = c.life / "wardrobe.json"
    if not path.exists():
        return {
            "items": [],
            "guidance": "A developing closet, not a fixed costume. Add items as life requires.",
        }
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise ValueError("Invalid wardrobe")
    scene = current(c)
    acquired = scene["state"].get("lifestyle", {}).get("acquired", []) if scene else []
    owned = {item["id"]: item for item in acquired}
    owned.update({item["id"]: item for item in data["items"]})
    data["items"] = list(owned.values())
    return data


def text(value, name, limit=500):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} must be nonempty text, at most {limit} characters")
    return value.strip()


def update_wardrobe(c, items):
    if not isinstance(items, list) or not items:
        raise ValueError("Supply a JSON list of wardrobe items")
    with file_lock(c.life / ".presence.lock"):
        data = wardrobe(c)
        by_id = {item["id"]: item for item in data["items"]}
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Each wardrobe item must be an object")
            ident = text(item.get("id"), "item id", 80)
            if not all(ch.isalnum() or ch in "-_" for ch in ident):
                raise ValueError(
                    "Use letters, digits, hyphens or underscores in item IDs"
                )
            row = {
                "id": ident,
                "description": text(item.get("description"), "description"),
                "use": text(item.get("use"), "use", 160),
                "condition": text(item.get("condition", "clean"), "condition", 160),
            }
            covers = item.get("covers", by_id.get(ident, {}).get("covers"))
            if covers is not None:
                if covers not in COVERS:
                    raise ValueError("covers must be top, bottom, full or none")
                row["covers"] = covers
            category = item.get("category", by_id.get(ident, {}).get("category"))
            if category is not None:
                import companion_lifestyle

                if category not in companion_lifestyle.CATEGORIES:
                    raise ValueError("Invalid clothing category")
                row["category"] = category
            by_id[ident] = row
        data["items"] = list(by_id.values())
        atomic_write(
            c.life / "wardrobe.json",
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        )
    return data


def show(c):
    closet = wardrobe(c)
    needed = {item["id"] for item in closet["items"]}
    last = {}
    for row in events(c):
        for item in row["state"].get("outfit", []):
            if item["id"] in needed:
                last[item["id"]] = row["recorded_at"]
                needed.remove(item["id"])
        if not needed:
            break
    import companion_lifestyle

    result = {
        "current": current(c),
        "wardrobe": {
            **closet,
            "items": [
                {**item, "last_worn": last.get(item["id"])} for item in closet["items"]
            ],
        },
    }
    if companion_lifestyle.enabled(c):
        result["everyday_life"] = companion_lifestyle.render(
            c, dt.datetime.now(ZoneInfo(c.timezone))
        )
    return result


def check(c, data, now=None):
    """Would `update` accept this record? Raises the same ValueError if not.

    The pulse asks before it writes, so a model that got a field wrong is told
    what was wrong and asked again, rather than the job dying on a rule it was
    never shown. Validation-only: it writes nothing.

    `now` is the moment the record is about, and it matters: the rules being
    checked include which routine anchor is active, which is a question about
    that moment and not about when the check happens to run. Left to default,
    a record for eight in the morning was judged against whatever the clock
    said at validation time -- so the same pulse passed or failed depending on
    the hour it was run, and a job replaying or catching up was checked against
    a day it was not writing about.
    """
    return update(c, data, now, dry_run=True)


def update(c, data, now=None, dry_run=False):
    now = now or dt.datetime.now(ZoneInfo(c.timezone))
    if now.tzinfo is None:
        raise ValueError("Timezone required")
    if not isinstance(data, dict):
        raise ValueError("State must be an object")
    # Optimistic concurrency protects a chat transition from an older scheduled update.
    if "previous_id" not in data:
        raise ValueError(
            "Read current state first and supply previous_id (null initially)"
        )
    with file_lock(c.life / ".presence.lock"):
        previous = current(c)
        utc = now.astimezone(dt.timezone.utc)
        slot = utc.replace(minute=utc.minute // 15 * 15, second=0, microsecond=0)
        ident = (
            data.get("id")
            or "state-" + hashlib.sha256(slot.isoformat().encode()).hexdigest()[:20]
        )
        closet = {item["id"]: item for item in wardrobe(c)["items"]}
        import companion_lifestyle

        if companion_lifestyle.enabled(c):
            companion_day_schema = companion_lifestyle.schema_fields()[
                "wardrobe_additions"
            ]
            import companion_day

            companion_day._validate(
                data.get("wardrobe_additions", []),
                companion_day_schema,
                "wardrobe_additions",
            )
            closet.update(
                {item["id"]: item for item in data.get("wardrobe_additions", [])}
            )
        outfit = data.get("outfit")
        if not isinstance(outfit, list) or len(outfit) > 20:
            raise ValueError("outfit must list at most 20 wardrobe item IDs")
        # An item that is not a string reached `set()` and raised TypeError, which
        # the caller's correction loop does not catch -- so a model that answered
        # with objects instead of ids took the whole tick down with an error about
        # hashability rather than being told what was wrong and asked again.
        bad = [item for item in outfit if not isinstance(item, str)]
        if bad:
            raise ValueError(
                "outfit must be wardrobe item IDs as plain strings, "
                f"not {type(bad[0]).__name__} values"
            )
        if len(set(outfit)) != len(outfit):
            raise ValueError("Duplicate outfit item")
        for item in outfit:
            if item not in closet and item not in VIRTUAL_TOKENS:
                raise ValueError("Add new items to the wardrobe before wearing them")
        loc = text(data.get("location"), "location", 240)
        act = text(data.get("activity"), "activity", 120)
        # "Taking a hot morning shower" recorded while still wearing pyjamas is not a
        # scene, it is two records disagreeing -- and it photographed exactly as it
        # read. The words are only used to REFUSE and ask for a correction, never to
        # decide anything on their own; the outfit stays the thing that is believed.
        dressed = [
            i
            for i in outfit
            if i not in VIRTUAL_TOKENS
            and closet.get(i, {}).get("category") not in ("underwear",)
        ]
        if dressed and BATHING_ACTIVITY.search(act) and not data.get("private"):
            raise ValueError(
                "A bath or shower cannot be taken in clothes: record the outfit as "
                "bathing, towel or undressed, or say what you are really doing. "
                "If this is something else in a bathroom, set private explicitly."
            )
        # Where she is, as she says. Carried forward only while she stays put: once the
        # location moves, the old answer is about somewhere else.
        setting = data.get("setting")
        if setting is not None and setting not in SETTINGS:
            raise ValueError('setting must be "private" or "public"')
        if (
            setting is None
            and previous
            and previous["state"].get("setting") in SETTINGS
            and previous["state"].get("location") == loc
        ):
            setting = previous["state"]["setting"]
        kind = undress({"outfit": outfit}, closet)[0]
        exposed = kind in ("undressed", "bathing", "underwear")
        if exposed and setting != "private":
            if setting == "public":
                raise ValueError(
                    "Changing or undressed states require a private setting; dress in daytime "
                    "or active clothes before going out."
                )
            raise ValueError(
                "Undressed, bathing or underwear-only states need you to say where you are: "
                'add "setting": "private" if nobody can see you here (home, a changing room), '
                'or "public" if they can.'
            )
        # The words are used only to ask, never to decide: a declared private place whose
        # name is plainly a public one is a record that disagrees with itself.
        if exposed and setting == "private" and reads_public(loc):
            raise ValueError(
                f'"{loc}" reads as a public place but setting says private. Name the private '
                "part of it (a changing room, a hotel room), or dress before being there."
            )
        care = data.get("care", [])
        if not isinstance(care, list) or len(care) > 10:
            raise ValueError("care must be a short list of actual routine transitions")
        wants = data.get("wants", [])
        if not isinstance(wants, list) or len(wants) > 5:
            raise ValueError(
                "wants must be a list of at most 5 short things she is after right now"
            )
        outfit_entries = [
            (
                {"id": key, "description": closet[key]["description"]}
                if key in closet
                else {"id": key, "description": VIRTUAL_TOKENS[key]}
            )
            for key in outfit
        ]
        state = {
            "location": text(data.get("location"), "location", 240),
            "activity": text(data.get("activity"), "activity", 120),
            "outfit": outfit_entries,
            "mood": text(data.get("mood"), "mood", 240),
            "wants": [text(item, "want", 160) for item in wants],
            # Hers, not a line to say out loud. It exists so the same feeling
            # carries across a gap between conversations instead of resetting.
            "private_stance": str(data.get("private_stance") or "").strip()[:300],
            "care": [text(item, "care event", 160) for item in care],
            "transition": str(data.get("transition") or "").strip(),
            # A model looked at this and said it was so. The script advancer
            # below writes False, and the hook says so rather than presenting
            # an unwatched hour as a confirmed present.
            "confirmed": True,
        }
        if len(state["transition"]) > 500:
            raise ValueError("Keep transition under 500 characters")
        # Whether she is asleep is a fact the overnight gates act on, so it is a field she
        # sets rather than a word the next reader has to find in her prose. Absent from an
        # update it carries forward, so sleep persists across ticks without being
        # re-asserted -- and stays absent entirely on records written before it existed,
        # which is what lets a pre-upgrade replay still compare equal.
        if "asleep" in data:
            state["asleep"] = bool(data["asleep"])
        elif previous and "asleep" in previous["state"]:
            state["asleep"] = bool(previous["state"]["asleep"])
        # Whether this is a moment she would not want photographed. Like `asleep`, a
        # field she sets rather than something a later reader infers from the words.
        # It does NOT carry forward: privacy is about this moment, and a bath that
        # quietly persisted into breakfast would be worse than useless.
        # Only her own declaration is stored. Being undressed is read from the outfit by
        # private_reason() instead, so the camera can tell "she asked not to be
        # photographed" (never overridden) from "she is undressed" (the adult gate's call).
        if "private" in data:
            state["private"] = bool(data["private"])
        if setting in SETTINGS:
            state["setting"] = setting
        narrative = text(data.get("text"), "episode text", 1600)
        import companion_day

        parent = previous
        if previous and previous["id"] == ident:
            parent = next(
                (row for row in events(c) if row["id"] == data["previous_id"]), None
            )
        legacy_retry = (
            previous
            and previous["id"] == ident
            and "started_at" not in previous["state"]
            and not any(key in data for key in companion_day.schema_fields())
        )
        if not legacy_retry:
            import companion_sleep

            state.update(
                companion_day.evolve(
                    data,
                    state,
                    parent,
                    (
                        dt.datetime.fromisoformat(previous["recorded_at"])
                        if previous and previous["id"] == ident
                        else now
                    ),
                    asleep=companion_sleep.asleep(c, now),
                )
            )
        # Replay uses the original parent; care and acquisitions commit in the same
        # append as presence, so a rejected/racing write cannot wash or buy anything.
        if companion_lifestyle.enabled(c) and (
            not previous or previous["id"] != ident or "lifestyle" in previous["state"]
        ):
            base_closet = wardrobe(c)["items"]
            if previous and previous["id"] == ident:
                added = {i["id"] for i in data.get("wardrobe_additions", [])}
                base_closet = [i for i in base_closet if i["id"] not in added]
            state["lifestyle"] = companion_lifestyle.evolve(
                c,
                {**data, "setting": state.get("setting")},
                outfit,
                parent,
                base_closet,
                (
                    dt.datetime.fromisoformat(previous["recorded_at"])
                    if previous and previous["id"] == ident
                    else now
                ),
            )
            state["care_actions"] = data.get("care_actions", [])
            state["wardrobe_additions"] = data.get("wardrobe_additions", [])
        if previous and previous["id"] == ident:
            if "lifestyle" not in previous["state"] and (
                data.get("care_actions") or data.get("wardrobe_additions")
            ):
                raise ValueError(
                    "This tick is already recorded; use a distinct id for a real later transition"
                )
            if previous["state"] != state or previous["text"] != narrative:
                raise ValueError(
                    "This tick is already recorded; use a distinct id for a real later transition"
                )
            return {"written": False, "episode": previous}
        companion_day.validate_plan(data, state, now)
        if data["previous_id"] != (previous["id"] if previous else None):
            raise ValueError(
                "State changed since read; read current state and reconsider the transition"
            )
        if previous:
            before = previous["state"]
            if now < dt.datetime.fromisoformat(previous["recorded_at"]):
                raise ValueError("Cannot move state backward in time")
            changed = (
                before["outfit"] != state["outfit"]
                or before["location"] != state["location"]
                or before["activity"] != state["activity"]
            )
            if changed and not state["transition"]:
                raise ValueError(
                    "Explain the outfit, location or activity transition; do not teleport"
                )
        # Everything above is validation; this is the only line that writes.
        if dry_run:
            return {"written": False, "valid": True}
        result = record(
            c.life,
            narrative,
            state["activity"],
            "in_progress",
            now,
            ident,
            c.agent,
            c.human,
            state=state,
        )
    # Outside the lock: the view is derived, so a failure to write it must not
    # cost the state that was just recorded.
    try:
        write_emotive(c, now)
    except OSError:
        pass
    try:
        import companion_active

        companion_active.write(c, now)
    except (OSError, ValueError, ImportError):
        pass
    return result


# ---- keeping the present honest without a model --------------------------
def last_confirmed(c):
    """The newest state a model actually looked at."""
    for row in events(c):
        if row["state"].get("confirmed", True):
            return row
    return None


def advance(c, now=None, min_age_minutes=20):
    """Carry the present forward when no model is available to confirm it.

    This never invents. It repeats the last recorded state with `confirmed`
    false, which is the honest claim: nothing has changed on the record, and
    nobody has checked. The hook turns that into "state unconfirmed since
    HH:MM" so the next conversation opens on a truthful present instead of a
    Tuesday evening presented as now.
    """
    now = now or dt.datetime.now(ZoneInfo(c.timezone))
    # The assembled context is cheap and depends on sensors, not only on state,
    # so refresh it whether or not the state itself needs carrying forward.
    try:
        import companion_active

        companion_active.write(c, now)
    except (OSError, ValueError, ImportError):
        pass
    previous = current(c)
    if not previous:
        return {"written": False, "reason": "no state to carry forward"}
    age = (
        now - dt.datetime.fromisoformat(previous["recorded_at"])
    ).total_seconds() / 60
    if previous["state"].get("confirmed", True) and age < min_age_minutes:
        return {
            "written": False,
            "reason": f"a model confirmed the state {int(age)} minutes ago",
        }
    with file_lock(c.life / ".presence.lock"):
        previous = current(c)
        utc = now.astimezone(dt.timezone.utc)
        slot = utc.replace(minute=utc.minute // 15 * 15, second=0, microsecond=0)
        ident = "advance-" + hashlib.sha256(slot.isoformat().encode()).hexdigest()[:16]
        if previous["id"] == ident:
            return {"written": False, "episode": previous}
        if now < dt.datetime.fromisoformat(previous["recorded_at"]):
            return {
                "written": False,
                "reason": "clock moved backward; state left alone",
            }
        state = {**previous["state"], "transition": "", "confirmed": False}
        anchor = last_confirmed(c)
        since = dt.datetime.fromisoformat(anchor["recorded_at"]) if anchor else None
        note = (
            "No change recorded and no model confirmed it"
            + (
                f" since {since.astimezone(ZoneInfo(c.timezone)).strftime('%H:%M')}"
                if since
                else ""
            )
            + "."
        )
        result = record(
            c.life,
            note,
            state["activity"],
            "in_progress",
            now,
            ident,
            c.agent,
            c.human,
            state=state,
        )
    for step in (write_emotive,):
        try:
            step(c, now)
        except OSError:
            pass
    try:
        import companion_active

        companion_active.write(c, now)
    except (OSError, ValueError, ImportError):
        pass
    return result


# ---- Emotive.md, rendered ------------------------------------------------
EMOTIVE_NOTE = (
    "<!-- Rendered from the presence state by companion_presence.py. Editing this file\n"
    "     changes nothing: the next state update overwrites it. Change how you feel by\n"
    "     recording a state, which is the only place a mood is real. -->"
)


def mood_history(c, limit=12):
    """Recent moods, newest first, one per recorded state."""
    out = []
    for row in events(c):
        state = row["state"]
        out.append(
            {
                "at": row["recorded_at"],
                "mood": state.get("mood", ""),
                "activity": state.get("activity", ""),
                "location": state.get("location", ""),
            }
        )
        if len(out) >= limit:
            break
    return out


def render_emotive(c, now=None):
    now = now or dt.datetime.now(ZoneInfo(c.timezone))
    row = current(c)
    lines = [f"# Emotive — {c.agent}", "", EMOTIVE_NOTE, ""]
    if not row:
        lines += [
            "No state has been recorded yet, so there is nothing here to feel.",
            "",
        ]
        return "\n".join(lines)
    state = row["state"]
    when = dt.datetime.fromisoformat(row["recorded_at"]).astimezone(
        ZoneInfo(c.timezone)
    )
    lines += [
        "## Right now",
        f"_as of {when.strftime('%A %-d %B, %H:%M')}_",
        "",
        f"**Mood.** {state.get('mood') or 'unrecorded'}",
        "",
        f"**Where and what.** {state.get('activity','')} — {state.get('location','')}",
        "",
    ]
    if state.get("wants"):
        lines += ["**What I want.**", ""] + [f"- {w}" for w in state["wants"]] + [""]
    if state.get("private_stance"):
        lines += [
            "**Where I actually stand.** " + state["private_stance"],
            "",
            "_This one is mine. It shapes how I answer; it is not a line to deliver._",
            "",
        ]
    history = mood_history(c)[1:]
    if history:
        lines += ["## How it has been moving", ""]
        for h in history:
            at = dt.datetime.fromisoformat(h["at"]).astimezone(ZoneInfo(c.timezone))
            lines.append(f"- {at.strftime('%a %H:%M')} — {h['mood']}")
        lines.append("")
    return "\n".join(lines)


def write_emotive(c, now=None):
    path = c.soul_dir / "Emotive.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, render_emotive(c, now))
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=pathlib.Path)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("show")
    sub.add_parser("emotive")
    sub.add_parser("advance")
    for name in ("update", "wardrobe"):
        p = sub.add_parser(name)
        p.add_argument("--file", type=pathlib.Path, required=True)
    args = parser.parse_args()
    c = cc.load(args.home)
    if args.action == "show":
        out = show(c)
    elif args.action == "emotive":
        out = {"written": str(write_emotive(c))}
    elif args.action == "advance":
        out = advance(c)
    else:
        data = json.loads(args.file.read_text(encoding="utf-8"))
        out = update(c, data) if args.action == "update" else update_wardrobe(c, data)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        sys.exit(1)
