"""Finding the agents on a Hermes home and letting a person choose between them."""

from __future__ import annotations
import companion_config as cc
import json
import pathlib
import sys
import companion_wizard as wiz
from .common import input, print
from .questions import ask


def existing_vault(hermes_root, exclude=None):
    """The vault other agents here already use, so a new one joins them."""
    hermes_root = pathlib.Path(hermes_root)
    homes = [hermes_root]
    pdir = hermes_root / "profiles"
    if pdir.is_dir():
        homes += sorted(pdir.iterdir())
    for h in homes:
        try:
            if not h.is_dir() or h == exclude:
                continue
        except OSError:
            continue
        cfgp = h / cc.CONFIG_NAME
        if cfgp.exists():
            try:
                v = json.loads(cfgp.read_text(encoding="utf-8")).get("vault")
                if v:
                    return pathlib.Path(v)
            except (ValueError, OSError):
                pass
    return None


def discover(hermes_root):
    """Every agent under this Hermes root: the root profile plus each profile dir."""
    hermes_root = pathlib.Path(hermes_root)
    found = []
    if (hermes_root / "SOUL.md").exists() or (hermes_root / "config.yaml").exists():
        found.append(("", hermes_root))
    pdir = hermes_root / "profiles"
    if pdir.is_dir():
        for d in sorted(pdir.iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                found.append((d.name, d))
    return found


def describe(name, home):
    kitted = (home / cc.CONFIG_NAME).exists()
    soul = home / "SOUL.md"
    size = (
        f'{len(soul.read_text(encoding="utf-8")):,} char SOUL'
        if soul.exists()
        else "no SOUL.md"
    )
    label = name or "root agent"
    return f"{label} — {size}" + ("  [already set up]" if kitted else "")


def pick_agent(hermes_root, answers=None, purpose="upgrade"):
    agents = discover(hermes_root)
    if not agents:
        sys.exit(f"no Hermes agents found under {hermes_root}")
    if answers and "which" in answers:
        want = str(answers["which"])
        for n, h in agents:
            if n == want or (want in ("root", "") and not n):
                return h
        sys.exit(f"no agent named {want!r}")
    if len(agents) == 1:
        return agents[0][1]
    choice = ask(
        f"Which agent do you want to {purpose}?",
        1,
        [(str(h), describe(n, h)) for n, h in agents],
        None,
        None,
    )
    return pathlib.Path(choice)


def agent_rows(hermes_root):
    """Every agent here with the facts needed to choose between them."""
    rows = []
    for name, home in discover(hermes_root):
        cfgp = home / cc.CONFIG_NAME
        set_up = cfgp.exists()
        c = cc.load(home) if set_up else None
        soul = home / "SOUL.md"
        rows.append(
            {
                "name": name or "default",
                "home": home,
                "set_up": set_up,
                "agent": (c.agent if set_up else "—"),
                "window": (f"{c.context_tokens//1024}K" if set_up else "—"),
                "has_soul": soul.exists(),
                "is_root": not name,
            }
        )
    return rows


def print_roster(rows):
    wiz.rule("YOUR COMPANIONS")
    if not rows:
        print("  No Hermes profiles found here yet.")
        print(
            wiz.C.dim(
                "  Install and configure Hermes, or choose Create to add a profile."
            )
        )
        return
    import textwrap

    for row in rows:
        status = (
            wiz.C.green("KIT INSTALLED")
            if row["set_up"]
            else wiz.C.yellow("READY TO ADOPT")
        )
        label = f"{row['agent']} / {row['name']}" if row["set_up"] else row["name"]
        print("  " + wiz.C.bold(label))
        print("  " + status + "  " + wiz.C.dim(f"context {row['window']}"))
        if not row["has_soul"]:
            print("  " + wiz.C.yellow("Identity file missing"))
        for line in textwrap.wrap(str(row["home"]), wiz.width() - 4):
            print("  " + wiz.C.dim(line))
        print()


def menu_pick(rows, prompt, only_set_up=None):
    pool = [r for r in rows if only_set_up is None or r["set_up"] == only_set_up]
    if not pool:
        print(wiz.C.yellow("  nothing here matches that."))
        return None
    picked = wiz.choose(
        prompt,
        [(f"{r['name']} — {r['agent']}", str(i)) for i, r in enumerate(pool)]
        + [("Back", "back")],
        allow_write=False,
        allow_skip=False,
    )
    return None if picked == "back" else pool[int(picked)]


def confirm_removal(row):
    """Deleting an agent takes its SOUL, memories, sessions and ledgers with it.
    Typing the name is the confirmation — a bare y/n is too easy to fat-finger."""
    print()
    print(
        "  " + wiz.C.yellow(wiz.C.bold(f"This removes {row['agent']} ({row['name']})."))
    )
    print("  " + wiz.C.dim(f"  {row['home']}"))
    print(
        "  "
        + wiz.C.dim(
            "  Its Hermes home is archived. Files in the shared vault stay in place."
        )
    )
    print(
        "  "
        + wiz.C.dim(
            "  The profile is ARCHIVED, not deleted — you can still get it back."
        )
    )
    typed = input(
        "\n  "
        + wiz.C.bold(f"Type {row['name']} to confirm, or anything else to cancel: ")
    ).strip()
    return typed == row["name"]
