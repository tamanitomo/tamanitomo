"""Context engine for a Tamanitomo companion.

Every message carries a fresh continuity snapshot: her present, what she knows
about you, her day. Hermes stores that snapshot with the message and replays it
on every later turn, so a conversation re-sends the same block again and again --
in one ten-turn evening, three quarters of each request was old snapshots. That
is time before every reply, and it fills the window that decides when the
conversation itself gets summarised away.

This engine is Hermes's own compressor with one seam: a request carries only the
newest snapshot. What is stored -- every message, every snapshot, every ledger --
is untouched. Installed and kept current by the kit (companion_routing.install).
"""

import json
import pathlib
import re

NAME = "tamanitomo-context"

# A photo is sent by a bare `MEDIA:/path` line. Written as a Markdown image,
# `![a stretch](MEDIA:/path)`, Hermes still sends the photo but strips only the tag,
# and `![a stretch]()` arrived in the chat as stray text beside every picture.
WRAPPED_MEDIA = re.compile(r"!?\[[^\]\n]*\]\(\s*<?(MEDIA:[^\s()<>]+)>?\s*\)")


def unwrap_media(response_text="", **_):
    """The reply with each Markdown-wrapped MEDIA tag left bare; None when there is none.

    Runs as Hermes's transform_llm_output, which also corrects a reply that was
    already streamed, so the stray text is edited away rather than left behind."""
    if "MEDIA:" not in (response_text or ""):
        return None
    fixed = WRAPPED_MEDIA.sub(r"\1", response_text)
    return fixed if fixed != response_text else None


def register(ctx):
    if hasattr(ctx, "register_hook"):
        ctx.register_hook("transform_llm_output", unwrap_media)
    here = pathlib.Path(__file__).resolve().parent
    try:
        agent = json.loads((here / "companion.json").read_text(encoding="utf-8"))[
            "agent"
        ]
    except (OSError, ValueError, KeyError, TypeError):
        # Not installed by the kit: leave Hermes on its built-in compressor.
        return
    from hermes_cli.config import load_config

    from .snapshot import make_engine

    ctx.register_context_engine(make_engine(load_config(), agent, name=NAME))
