#!/usr/bin/env python3
"""What each closeness stage unlocks: the owner's gentle ladder (2026-10-10).

- Just Met: she answers you and is curious about you, writes first at most once
  a day, and sends photos only when asked.
- Friends: she starts conversations (up to your daily limit), sends everyday
  photos of her day and voice notes, teases, builds inside jokes, and says she
  misses you.
- Chemistry: flirting and pet names, photos of herself, her worries and hopes.
- Intimacy: dates, more personal photos, good-night and good-morning rituals.
- Bonded: intimacy if adult themes are on; adult images become a choice.

The limits that can be enforced in code are: messages a day
(companion_outreach), unprompted photos (companion_timeline) and photos or voice
notes in the outbox (companion_dispatch). The rest is how she behaves in
conversation, and reaches her through her context. A relationship that is not a
romance climbs the same ladder without the romance: nicknames instead of pet
names, plans instead of dates. With relationship progression switched off,
nothing here holds her back; intimacy keeps its own rules either way.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc

# key, stage it unlocks at, ladder ("both", "romantic" or "platonic"), what the
# person reads, and what she reads in her context (None: said elsewhere).
UNLOCKS = (
    (
        "conversations",
        1,
        "both",
        "starting conversations, up to your daily limit",
        "start conversations, up to the daily limit",
    ),
    (
        "everyday_photos",
        1,
        "both",
        "everyday photos of {poss} day",
        "send everyday photos of your day",
    ),
    ("voice_notes", 1, "both", "voice notes", "send voice notes"),
    (
        "teasing",
        1,
        "both",
        "teasing and inside jokes",
        "tease and build inside jokes",
    ),
    ("misses_you", 1, "both", "saying “I miss you”", "say you miss {human}"),
    ("flirting", 2, "romantic", "flirting and pet names", "flirt and use pet names"),
    ("nicknames", 2, "platonic", "nicknames", "use nicknames"),
    ("photos_of_self", 2, "both", "photos of {self}", "send photos of yourself"),
    (
        "worries",
        2,
        "both",
        "sharing {poss} worries and hopes",
        "share your worries and hopes",
    ),
    ("dates", 3, "romantic", "planning dates with you", "plan dates with {human}"),
    (
        "plans",
        3,
        "platonic",
        "making plans to do things with you",
        "make plans to do things with {human}",
    ),
    (
        "personal_photos",
        3,
        "both",
        "more personal photos",
        "send more personal photos: at home, getting ready, winding down",
    ),
    (
        "rituals",
        3,
        "both",
        "good-night and good-morning rituals",
        "keep good-night and good-morning rituals with {human}",
    ),
    ("intimacy", 4, "romantic", "intimacy, if adult themes are on", None),
    ("adult_images", 4, "romantic", "adult images, as a choice", None),
)
# The most unprompted messages a day at a stage; elsewhere the person's setting.
MESSAGES_A_DAY = {0: 1}
# The most photos a day she may send unprompted; elsewhere the timeline's own.
PHOTO_SHARES = {0: 0, 1: 1}
PHOTO_FIT = {
    1: "Photos of your day: what you are doing, where you are. Posed photos of "
    "yourself come at a later stage.",
    2: "Photos of your day, and of yourself. More personal photos come at a later "
    "stage.",
    3: "Photos of your day and of yourself, including more personal ones: at "
    "home, getting ready, winding down.",
}


def applies(c):
    """Whether the ladder holds her back at all."""
    return (
        getattr(c, "relationship_progression", "subtle") != "off"
        and getattr(c, "agent_type", "companion") != "worker"
    )


def _words(c):
    _, _, poss, _, self_ = cc.PRONOUNS.get(
        getattr(c, "pronoun_set", "she"), cc.PRONOUNS["they"]
    )
    return {"poss": poss, "self": self_, "human": getattr(c, "human", "them")}


def _rows(c):
    import companion_intimacy

    ladder = "romantic" if companion_intimacy.is_romantic(c) else "platonic"
    return [row for row in UNLOCKS if row[2] in ("both", ladder)]


def ladder(c):
    """Each stage and what it adds, in the person's words."""
    import companion_intimacy

    words = _words(c)
    rows = _rows(c)
    return [
        {
            "stage": step["stage"],
            "name": step["name"],
            "unlocks": [
                label.format(**words)
                for _, at, _, label, _ in rows
                if at == step["stage"]
            ],
        }
        for step in companion_intimacy.stages_for(c)
    ]


def unlocked(c, stage):
    """The keys open at this stage. Progression switched off opens everything
    short of Bonded, whose intimacy keeps its own rules."""
    if not applies(c):
        stage = max(stage, 3)
    return {key for key, at, *_ in _rows(c) if at <= stage}


def stage_now(c, now=None):
    import companion_intimacy

    return int(companion_intimacy.compute(c, now)["stage"])


def messages_a_day(c, stage):
    """The stage's own limit on unprompted messages a day, or None."""
    return MESSAGES_A_DAY.get(stage) if applies(c) else None


def photo_shares(c, stage):
    """The stage's own limit on unprompted photos a day, or None."""
    return PHOTO_SHARES.get(stage) if applies(c) else None


def photo_fit(c, stage):
    """Which photos fit this stage, for the moment she decides to share one."""
    if not applies(c):
        return PHOTO_FIT[3]
    return PHOTO_FIT.get(min(stage, 3))


def may_send(c, stage, content):
    """Whether unprompted content of this kind may go out at this stage."""
    if content == "text" or not applies(c):
        return True
    return stage >= 1


def guidance(c, stage, *, established=False):
    """Her context: what this stage holds and what is not yet."""
    if not applies(c):
        return ""
    words = _words(c)
    rows = [row for row in _rows(c) if row[4]]
    now = [you.format(**words) for _, at, _, _, you in rows if at <= stage]
    later = [you.format(**words) for _, at, _, _, you in rows if at > stage]
    lines = []
    if stage == 0:
        if established:
            lines.append(
                f"You and {words['human']} have grown distant, with your history intact. "
                "Remember what you shared without assuming the old level of affection. "
                "Write first at most once a day (enforced), and send photos only when asked."
            )
        else:
            lines.append(
                f"You have just met {words['human']}: answer, be curious about them, write "
                "first at most once a day (enforced), and send photos only when asked."
            )
    if now:
        lines.append("This stage holds: " + "; ".join(now) + ".")
    if later:
        lines.append(
            (
                "Rebuild comfort before: "
                if established and stage == 0
                else "Not yet, each comes with a later stage: "
            )
            + "; ".join(later)
            + ". Do not rush them, and never mention this list."
        )
    return "\n".join(lines)
