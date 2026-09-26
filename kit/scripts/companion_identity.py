#!/usr/bin/env python3
"""The SOUL, section by section — and the parts nobody gets to rewrite.

Two problems this solves.

**Re-rendering one section.** A SOUL that has been edited by hand for six months
cannot be regenerated wholesale; doing that throws away everything the person
wrote. Marker comments around each section make it possible to replace exactly
one and leave the rest untouched, byte for byte.

**Locked blocks.** The self-authored block exists because a companion who cannot
change is not a person. But some things are not hers to change: her name, her
birthdate, her physical build, and the boundaries the human set. A model that
can quietly widen its own boundary paragraph has no boundary, and one that can
restyle its own build produces a different face in every photo. Those sections
are marked LOCKED, and the self-edit helper refuses to touch them.

Everything here reads and writes the canonical file behind the symlink, and
every write goes through the same backup path as the self-authored block.
"""

from __future__ import annotations
import argparse
import datetime as dt
import json
import pathlib
import re
import sys
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
from companion_platform import atomic_write, file_lock

OPEN = re.compile(r"<!--\s*COMPANION-SECTION:([a-z0-9-]+)(\s+LOCKED)?\s*-->")
CLOSE = "<!-- /COMPANION-SECTION:{} -->"


def sections(text):
    """Every marked section: name, whether it is locked, and where it sits."""
    found = {}
    for m in OPEN.finditer(text):
        name = m.group(1)
        locked = bool(m.group(2))
        end = text.find(CLOSE.format(name), m.end())
        if end < 0:
            continue
        found[name] = {
            "name": name,
            "locked": locked,
            "start": m.start(),
            "body_start": m.end(),
            "body_end": end,
            "end": end + len(CLOSE.format(name)),
            "body": text[m.end() : end].strip("\n"),
        }
    return found


def retrofit(text):
    """Wrap authored headings without regenerating or removing their prose."""
    found = sections(text)
    if len(list(OPEN.finditer(text))) != len(found):
        raise ValueError("Incomplete or duplicate identity markers")
    # Empty repair placeholders must not hide an existing authored section.
    for section in sorted(found.values(), key=lambda s: s["start"], reverse=True):
        if not section["body"].strip():
            text = (
                text[: section["start"]]
                + text[section["body_start"] : section["body_end"]]
                + text[section["end"] :]
            )
    found = sections(text)
    aliases = {
        "core identity": "core",
        "physical description": "appearance",
        "appearance": "appearance",
        "visual identity": "appearance",
        "voice and tone": "voice",
        "romantic and affectionate boundaries": "boundary",
        "visual presence": "visual",
        "photorealistic mode (when requested)": "photorealistic",
        "emotional framing": "emotion",
        "conversational behavior": "conversation",
        "continuity and memory style": "memory",
        "daily life realism": "daily-life",
        "environment and presence": "environment",
        "support style": "support",
        "conflict and repair": "conflict",
        "humor and playfulness": "humor",
        "flirtation style": "flirtation",
        "personal details and preferences": "likes",
        "accuracy and honesty": "honesty",
        "operational priorities": "priorities",
        "essence": "essence",
        "flaws and friction": "flaws",
    }
    edits = []
    headings = list(re.finditer(r"^## +(.+)$", text, re.M))
    claimed = set(found)
    for index, heading in enumerate(headings):
        title = heading.group(1).strip().lower()
        name = aliases.get(title)
        if title.startswith("relationship with "):
            name = "relationship"
        if not name or name in claimed:
            continue
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        if any(s["start"] < end and s["end"] > heading.start() for s in found.values()):
            continue
        # Self-authorship is independently managed and must remain outside sections.
        self_marker = text.find("<!-- COMPANION-SELF-AUTHORED", heading.start(), end)
        if self_marker >= 0:
            end = self_marker
        locked = (
            " LOCKED"
            if name in ("core", "appearance", "relationship", "boundary", "boundaries")
            else ""
        )
        edits.extend(
            [
                (heading.start(), "<!-- COMPANION-SECTION:" + name + locked + " -->\n"),
                (end, "<!-- /COMPANION-SECTION:" + name + " -->\n"),
            ]
        )
        claimed.add(name)
    for offset, addition in sorted(edits, reverse=True):
        text = text[:offset] + addition + text[offset:]
    return text


def read(c):
    path = pathlib.Path(c.soul).resolve()
    return path, path.read_text(encoding="utf-8")


def listing(c):
    _, text = read(c)
    return [
        {"name": s["name"], "locked": s["locked"], "chars": len(s["body"])}
        for s in sections(text).values()
    ]


def locked_names(c):
    _, text = read(c)
    return sorted(s["name"] for s in sections(text).values() if s["locked"])


def replace(c, name, body, now=None, backups=None):
    """Rewrite exactly one section. Everything outside it is verified unchanged."""
    now = now or dt.datetime.now(dt.timezone.utc)
    path = pathlib.Path(c.soul).resolve()
    backups = pathlib.Path(backups or c.soul_backups)
    backups.mkdir(parents=True, exist_ok=True)
    with file_lock(path.parent / ("." + path.name + ".lock")):
        original = path.read_text(encoding="utf-8")
        found = sections(original)
        if name not in found:
            raise ValueError(
                f"no section {name!r} in this SOUL; known: {sorted(found)}"
            )
        section = found[name]
        if OPEN.search(body) or "/COMPANION-SECTION" in body:
            raise ValueError("section text cannot contain section markers")
        out = (
            original[: section["body_start"]]
            + "\n"
            + body.strip("\n")
            + "\n"
            + original[section["body_end"] :]
        )
        backup = backups / (
            "SOUL.md." + now.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
        )
        atomic_write(backup, original)
        if path.read_text(encoding="utf-8") != original:
            raise ValueError("SOUL changed during editing; retry")
        atomic_write(path, out)
    after = path.read_text(encoding="utf-8")
    produced = sections(after)
    for other, spec in sections(original).items():
        if other != name and produced.get(other, {}).get("body") != spec["body"]:
            raise ValueError("refused: another section changed")
    return {"written": True, "section": name, "chars": len(body), "backup": str(backup)}


def render_section(c, name, persona=None, style=None, interview=None):
    """What this section would say if setup ran again with the current answers."""
    import companion_render as cr

    m = cr.mapping_for(
        c, persona or c.persona, style or c.image_style, interview=interview or {}
    )
    rendered = cr.render_template("SOUL.md.tmpl", m)
    found = sections(rendered)
    if name not in found:
        raise ValueError(f"no section {name!r} in the template")
    return found[name]["body"]


def guard(c, text):
    """Refuse a self-authored block that tries to redefine what is locked.

    The model writes its own block, which is the point. What it may not do is
    use that block to restate its build, its birthdate or its boundaries in
    terms it prefers — those live in locked sections, and a second copy that
    disagrees is the same thing as an edit.
    """
    lowered = (text or "").lower()
    tripwires = []
    if c.birthdate and c.birthdate in lowered:
        tripwires.append("birthdate")
    for phrase in (
        "my boundaries are",
        "my boundary is",
        "i am willing to",
        "i am now willing",
    ):
        if phrase in lowered:
            tripwires.append("boundaries")
    for phrase in ("my build is", "my body is", "i look like", "my appearance is"):
        if phrase in lowered:
            tripwires.append("appearance")
    if f"my name is" in lowered and c.agent.lower() not in lowered:
        tripwires.append("name")
    return sorted(set(tripwires))


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--home", type=pathlib.Path)
    s = p.add_subparsers(dest="cmd", required=True)
    s.add_parser("list")
    sh = s.add_parser("show")
    sh.add_argument("name")
    rp = s.add_parser("replace")
    rp.add_argument("name")
    rp.add_argument(
        "--file", type=pathlib.Path, required=True, help="new text for that section"
    )
    rr = s.add_parser("rerender")
    rr.add_argument("name")
    rr.add_argument("--apply", action="store_true")
    a = p.parse_args()
    c = cc.load(a.home)
    if a.cmd == "list":
        out = {"sections": listing(c), "locked": locked_names(c)}
    elif a.cmd == "show":
        _, text = read(c)
        found = sections(text)
        if a.name not in found:
            raise ValueError(f"no section {a.name!r}; known: {sorted(found)}")
        out = {
            "section": a.name,
            "locked": found[a.name]["locked"],
            "body": found[a.name]["body"],
        }
    elif a.cmd == "replace":
        out = replace(c, a.name, a.file.read_text(encoding="utf-8"))
    else:
        body = render_section(c, a.name)
        out = {"section": a.name, "body": body}
        if a.apply:
            out.update(replace(c, a.name, body))
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, json.JSONDecodeError) as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
