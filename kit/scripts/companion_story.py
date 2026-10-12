#!/usr/bin/env python3
"""Her world and her history, as context: places, what she has said about her past, and how to keep both straight.

The ledgers live in `companion_places.py`, `companion_canon.py` and
`companion_notes.py`; this only assembles what a turn should carry and the one short
paragraph that tells her how to add to them. It calls no model.
"""

from __future__ import annotations
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import companion_canon as canon
import companion_places as places

HERE = pathlib.Path(__file__).resolve().parent


def _command(c, script):
    from companion_platform import terminal_python_command

    return terminal_python_command(HERE / script, "--home", c.home)


def instructions(c):
    home = places.home(c)
    lines = [
        f"[Keeping your story straight — your history and your world are yours to invent, and then they are fixed]",
        f"When you tell {c.human} something about your past that is not recorded above (family, childhood, "
        f"old relationships, jobs), record it so you never contradict it: "
        f'{_command(c, "companion_canon.py")} add --topic T --statement S --evidence "where you said it". '
        "A topic you have already covered is refused until you say whether it revises (--supersedes ID) "
        "or adds to (--also) what you said.",
        "Where you are is part of every presence update: when you move, say which place "
        '("place": "home" with "room", a place id from your places, or "out"), and the first '
        'time you go somewhere describe it with "new_place" (or '
        f'{_command(c, "companion_places.py")} add --name N --description D). '
        "Later visits must match it; add new detail with the detail command instead of rewriting it.",
    ]
    if not home:
        where = f" in {c.location}" if getattr(c, "location", "") else ""
        lines.append(
            f"You have not described your home yet. When it comes up naturally, or in a quiet moment, "
            f"decide what it is like{where} and record it once with floor plan rooms: "
            f'{_command(c, "companion_places.py")} set-home --description D --room "Kitchen=what it is like" '
            "--room ... Until you do, do not describe the inside of your home in detail."
        )
    viewing = _command(c, "companion_viewing.py")
    lines.append(
        f"When you both agree to watch together, record `{viewing} together --title TITLE "
        "--comments quiet|occasional --evidence QUOTE` (manual progress without a media server). "
        f"Use `{viewing} pause|resume|stop --session-id ID` when participation changes. "
        f"Keep an actual human checkpoint with `{viewing} report --text TEXT --evidence QUOTE`; "
        "never infer progress from elapsed time. A synopsis is not scene perception and may spoil later events. "
        f"When something personal actually happened, `{viewing} moment --text TEXT --evidence QUOTE "
        "--session-id ID` links it into shared memory. A new joke is a note until it really recurs. "
        "Keep your own opinions; later callbacks should fit the conversation, not repeat on every turn."
    )
    import companion_music

    if companion_music.enabled(c):
        lines.append(music_instructions(c))
    lines.append(
        f"When something between you becomes a running joke, a nickname, a ritual or a first: "
        f'{_command(c, "companion_notes.py")} moment --moment joke|nickname|ritual|first|milestone --text T '
        '--evidence "the words or the occasion" (for a tradition that comes round, add --recurs yearly '
        f"--first-on YYYY-MM-DD). If {c.human} tells you their birthday: "
        f'{_command(c, "companion_together.py")} set --human-birthday MM-DD --evidence "their words". '
        "Do not claim anything was recorded until the command succeeds."
    )
    return "\n".join(lines)


def music_instructions(c):
    command = _command(c, "companion_music.py")
    return (
        f"For an album that brings {c.human} or your relationship to mind, `{command} discover` "
        "reads Spotify top artists and albums (recent artists if top access is unavailable). "
        f"Use `{command} search ARTIST --kind artist`, then `albums ARTIST_ID`, for a favorite "
        "they actually named. Listening affinity is not proof of a favorite. If Spotify is unavailable, "
        "say so; do not invent a catalog result. Pick only when you have a personal reason "
        "(a recorded preference or a shared memory, not because another run came round), "
        "keep the Spotify link, and don't claim to have heard audio or lyrics from metadata. "
        f"Save with `{command} suggest --file PATH` using JSON {{album_id, note, moment_id}} "
        "linked to a recorded shared moment, or {album_id, note, evidence, source} quoting a real exchange. "
        f"`{command} share ID` queues the saved note and album link through the usual outreach controls. "
        "Queued is not delivered. Read `history` before suggesting the same album again."
    )


def chat_parts(c, relationship_budget, compact=False):
    """([(priority, text)], suppressed section names) for the chat context."""
    if not c.has_inner_life:
        return [], set()
    shown = (
        places.render(c, max(300, relationship_budget // 2))
        if relationship_budget
        else ""
    )
    told = (
        canon.render(c, max(300, relationship_budget // 2))
        if relationship_budget
        else ""
    )
    parts, suppressed = [], set()
    if shown:
        parts.append(
            (
                5,
                "[Your own world — places in your life as you first described them. Visits must match; "
                "add detail rather than contradict]\n" + shown,
            )
        )
    if told:
        parts.append(
            (5, "[What you have told about your own past — fixed once told]\n" + told)
        )
    try:
        import companion_arcs

        running = companion_arcs.render(c)
    except (OSError, ValueError):
        running = ""
    if running and (companion_arcs.active(c) or not compact):
        parts.append((5, running))
    if not relationship_budget and (places.places(c) or canon.canon(c)):
        suppressed.add("your places and history")
    if not compact:
        parts.append((3, instructions(c)))
    return parts, suppressed


HOME_MISSING = (
    "[Your home is not on record yet, so it can drift from one day to the next. Describe it "
    "once, in the next presence update you write: add "
    '"home": {"description": "what kind of home it is and where", "rooms": ["Kitchen=what it is '
    'like", "Bedroom=...", ...]} and "room" for the room you are in. Decide it from what you '
    "already know of your life; after that every room and every move is kept.]"
)


def scheduled(c, limit=1500, now=None):
    """Places only, for the scheduled runs that choose where she is and what she does."""
    if not c.has_inner_life:
        return ""
    shown = places.render(c, limit)
    block = (
        (
            "[Places in your life, as first described, with their ids. Where you go must match "
            'them; when you move, say which with "place" ("out" when you are out and about); add '
            "detail with companion_places.py detail rather than contradict]\n" + shown
        )
        if shown
        else ""
    )
    if not places.home(c):
        block = HOME_MISSING + ("\n" + block if block else "")
    try:
        import companion_arcs

        running = companion_arcs.render(c)
    except (OSError, ValueError):
        running = ""
    if running:
        block = (block + "\n" if block else "") + running
    import companion_viewing
    import companion_music

    shared = companion_viewing.session_context(c, now, limit=1600)
    if shared:
        block += "\n" + shared
    # Albums are the Music sensor's: the scheduled runs learn how to pick one, and
    # what they picked, only while the human has it switched on.
    if companion_music.enabled(c):
        block += "\n" + music_instructions(c)
        saved_music = companion_music.render(c)
        if saved_music:
            block += "\n" + saved_music
    return block
