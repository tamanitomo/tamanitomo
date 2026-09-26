"""The catalog browser."""

from __future__ import annotations
import companion_platform as cp
import companion_render as cr
import sys
import companion_wizard as wiz
from .common import print
from .questions import ask


def cmd_catalog(args):
    """Browse character options without creating or editing a profile."""
    from companion_catalog import load as load_catalog, options, BOUNDARIES

    cat = load_catalog()["categories"]
    gender = args.gender
    key = args.category
    if key is None and cp.is_terminal(sys.stdin):
        key = ask(
            "Explore a category",
            1,
            [(k, v["label"]) for k, v in cat.items() if gender in v]
            + [
                ("personas", "Personas"),
                ("images", "Image styles"),
                ("boundaries", "Relationship boundaries"),
            ],
        )
    if key == "personas":
        rows = [(v["label"], v["blurb"]) for v in cr.load_personas().values()]
    elif key == "images":
        rows = [(v["label"], v["blurb"]) for v in cr.load_styles().values()]
    elif key == "boundaries":
        rows = [(v[0], v[2]) for v in BOUNDARIES.values()]
    elif key:
        rows = options(key, gender)
    else:
        rows = [
            (v["label"], f"{len(v[gender])} {gender} choices")
            for v in cat.values()
            if gender in v
        ]
        rows.extend(
            [
                ("Personas", str(len(cr.load_personas()))),
                (
                    "Image styles",
                    str(len(cr.load_styles()) - 2) + " plus text-only and undecided",
                ),
                ("Boundaries", str(len(BOUNDARIES))),
            ]
        )
    wiz.banner(
        "Character catalog", f"{gender.capitalize()} · " + (key or "all categories")
    )
    from companion_catalog import fill
    import textwrap

    # Browsing has no companion to name yet, so the two names stay visible as
    # placeholders. Labels are filled too — some of them carry pronouns.
    pron = "he" if gender == "male" else "she"
    for i, (label, detail) in enumerate(rows, 1):
        print(
            wiz.C.cyan(f"  {i:2}. ")
            + wiz.C.bold(fill(label, "<<agent>>", "<<user>>", pron, pron))
        )
        detail = fill(detail, "<<agent>>", "<<user>>", pron, pron)
        for line in textwrap.wrap(detail, wiz.width() - 6):
            print("      " + wiz.C.dim(line))
        print()
    return 0
