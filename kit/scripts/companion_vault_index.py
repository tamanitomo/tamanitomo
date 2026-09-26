#!/usr/bin/env python3
"""A map of the vault: every folder, how many notes it holds, and a few of the
files that say what it is.

Without it an agent only knows the files something else happens to mention, and
"is there a note about X" becomes a guess. With it she can see the whole shape
of what she keeps and go straight to the right place; `show <folder>` then
lists that folder in full, with each note's sections.

It is sent once per session, not once per turn. Hermes replays each turn's
injected context with the history, so a map sent every turn would be carried N
times over; sent once it rides in the cached prefix like a context file. The
hook looks for its own marker in the history and sends the map again only when
it is missing: the first turn, and the first turn after compression summarised
it away.

Fitting is by budget, never by folder name. Every folder is listed; key files
per folder shrink from five toward none if the window is tight, and only a very
small window falls back to a tree of folder counts.
"""

from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
from companion_platform import atomic_write

BEGIN = "<!-- tamanitomo:vault-index:begin -->"
END = "<!-- tamanitomo:vault-index:end -->"
# Rebuilt at most this often; a session start reads the cache in between.
FRESH_SECONDS = 15 * 60
HEAD_BYTES = 64_000
MAX_HEADINGS = 6
HEADING_CHARS = 48
# Folders that hold installed tools rather than anything anyone wrote.
TOOL_DIRS = frozenset(
    {"node_modules", "__pycache__", "venv", "site-packages", "bower_components"}
)
# The root agent's own life, at the top of the vault (its `data` is the vault root).
ROOT_AGENT_DIRS = frozenset(
    {"soul", "companion-life", "creations", "image-timeline", "albums"}
)
# A folder's key files: the ones that say what the folder is, then the newest.
KEY_NAMES = ("readme", "index", "_index", "overview", "summary", "manifest", "soul")
MAX_KEYS = 5
HEADING = re.compile(r"^(#{1,2})\s+(.+?)\s*#*\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")


def budget_chars(c) -> int:
    """Chars the map may occupy; 0 means switched off."""
    return cc.vault_index_cap(c.context_tokens, c.vault_index_tokens)


def _excluded(c) -> set:
    return {
        str(p).strip("/") for p in (c.vault_index_exclude or []) if str(p).strip("/")
    }


def _prune(c, rel: str, name: str, excluded: set) -> bool:
    """True when a directory must not be walked."""
    if name.startswith(".") or name in TOOL_DIRS:
        return True
    path = f"{rel}/{name}" if rel else name
    if path in excluded:
        return True
    # Another agent's private life is not this one's to map. A profile sees its
    # own subtree; the root agent sees none of them.
    if rel == "agents" and name != (c.profile or ""):
        return True
    # ...and the root agent's own life lives at the top of the vault, not under
    # agents/, so a profile's map listed her soul, journal and pictures as if they
    # were its own. The shared knowledge around them stays on the map.
    if rel == "" and c.profile and name in ROOT_AGENT_DIRS:
        return True
    if (
        rel == ""
        and c.profile
        and name == "people"
        and not getattr(c, "share_people", False)
    ):
        return True
    return False


def headings(path: pathlib.Path) -> list:
    try:
        with open(path, "rb") as fh:
            text = fh.read(HEAD_BYTES).decode("utf-8", "replace")
    except OSError:
        return []
    out = []
    fenced = False
    for line in text.splitlines():
        if FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        m = HEADING.match(line)
        if not m:
            continue
        h = m.group(2).strip()
        if len(h) > HEADING_CHARS:
            h = h[: HEADING_CHARS - 1].rstrip() + "…"
        if h and h not in out:
            out.append(h)
        if len(out) >= MAX_HEADINGS:
            break
    return out


def scan(c) -> list:
    """Every note under the vault as {dir, name, mtime, headings}."""
    root = c.vault
    excluded = _excluded(c)
    notes = []
    if not root.is_dir():
        return notes
    for dirpath, dirs, files in os.walk(root):
        rel = pathlib.Path(dirpath).relative_to(root).as_posix()
        rel = "" if rel == "." else rel
        dirs[:] = sorted(d for d in dirs if not _prune(c, rel, d, excluded))
        for f in sorted(files):
            if not f.lower().endswith(".md") or f.startswith("."):
                continue
            p = pathlib.Path(dirpath) / f
            if f"{rel}/{f}".strip("/") in excluded:
                continue
            try:
                mtime = p.stat().st_mtime
            except OSError:
                continue
            stem = f[:-3]
            hs = headings(p)
            # A lone title that only restates the file name says nothing.
            if len(hs) == 1 and re.sub(r"[\W_]+", "", hs[0].lower()) == re.sub(
                r"[\W_]+", "", stem.lower()
            ):
                hs = []
            notes.append({"dir": rel, "name": stem, "mtime": mtime, "headings": hs})
    return notes


def _line(note, with_headings):
    if with_headings and note["headings"]:
        return "- " + note["name"] + ": " + " · ".join(note["headings"])
    return "- " + note["name"]


def _keys(ns: list) -> list:
    """A folder's notes, the ones that explain it first, then newest first."""

    def rank(n):
        name = n["name"].lower()
        return (
            KEY_NAMES.index(name) if name in KEY_NAMES else len(KEY_NAMES),
            -n["mtime"],
        )

    return sorted(ns, key=rank)


def render(c, notes: list, budget: int, built: str = "") -> str:
    """Every folder with its note count and a few key files, fitted to `budget`
    chars. The whole shape of the vault, not its contents: anything inside is
    one `show` away. Never silently partial."""
    dirs = {}
    for n in notes:
        dirs.setdefault(n["dir"], []).append(n)
    command = cc_command(c, "show")
    head = (
        f"[Vault map — {c.vault}: {len(notes)} notes in {len(dirs)} folders"
        + (f", built {built}" if built else "")
        + ". Each line is a folder, its note count, and a few of its "
        "key files (<folder>/<name>.md). Everything you have written or kept is in here: open any file "
        f"with your file tools, and list a folder in full, with each note's sections, with: {command} <folder>]"
    )

    def compose(keys):
        out = [head]
        for d in sorted(dirs):
            ns = dirs[d]
            line = f'{d or "(vault root)"}/ ({len(ns)})'
            if keys:
                shown = [n["name"] for n in _keys(ns)[:keys]]
                line += (
                    ": "
                    + ", ".join(shown)
                    + (f" +{len(ns)-len(shown)} more" if len(ns) > len(shown) else "")
                )
            out.append(line)
        return "\n".join(out)

    for keys in range(MAX_KEYS, -1, -1):
        text = compose(keys)
        if len(text) <= budget:
            return text

    # Too small a window for every folder: a tree of folder counts, as deep as
    # fits. Still a map, just a coarser one.
    def tree(depth):
        counts = {}
        for d, ns in dirs.items():
            key = "/".join(d.split("/")[:depth]) if d else ""
            counts[key] = counts.get(key, 0) + len(ns)
        return [f'{k or "(vault root)"}/ ({v})' for k, v in sorted(counts.items())]

    note = "[Folder counts only for space; the deepest folders shown include their subfolders.]"
    depth = max((d.count("/") + 1 for d in dirs if d), default=1)
    while depth > 1 and len("\n".join([head, note, *tree(depth)])) > budget:
        depth -= 1
    return "\n".join([head, note, *tree(depth)])[: max(budget, len(head))]


def cc_command(c, action: str) -> str:
    try:
        from companion_platform import terminal_python_command

        return terminal_python_command(pathlib.Path(__file__), "--home", c.home, action)
    except Exception:
        return f"companion_vault_index.py {action}"


def cache_path(c) -> pathlib.Path:
    return c.home / "cache" / "vault-index.json"


def build(c, force: bool = False) -> str:
    """The fitted map, from cache when fresh and built for the same budget."""
    budget = budget_chars(c)
    if budget <= 0:
        return ""
    path = cache_path(c)
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
        age = dt.datetime.now().timestamp() - float(cached["built_at"])
        if (
            not force
            and cached.get("budget") == budget
            and cached.get("vault") == str(c.vault)
            and 0 <= age < FRESH_SECONDS
        ):
            return cached["text"]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    now = dt.datetime.now().astimezone()
    text = render(c, scan(c), budget, now.strftime("%Y-%m-%d %H:%M"))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(
            path,
            json.dumps(
                {
                    "built_at": now.timestamp(),
                    "budget": budget,
                    "vault": str(c.vault),
                    "text": text,
                },
                ensure_ascii=False,
            ),
        )
    except OSError:
        pass
    return text


def in_history(history) -> bool:
    """Whether a turn this session already carried the map."""
    for row in history or []:
        if isinstance(row, dict) and row.get("role") == "user":
            for key in ("api_content", "content"):
                v = row.get(key)
                if isinstance(v, str) and BEGIN in v:
                    return True
    return False


def for_prompt(c, payload) -> str:
    """The fenced map when this turn should carry it, else ''."""
    if budget_chars(c) <= 0:
        return ""
    extra = (payload or {}).get("extra") if isinstance(payload, dict) else None
    history = extra.get("conversation_history") if isinstance(extra, dict) else None
    if in_history(history):
        return ""
    text = build(c)
    return BEGIN + "\n" + text + "\n" + END if text else ""


def show(c, folder: str = "") -> str:
    """Unbudgeted listing of one folder (recursive), with every note's sections."""
    folder = folder.strip().strip("/")
    if folder == ".":
        folder = ""
    notes = [
        n
        for n in scan(c)
        if not folder or n["dir"] == folder or n["dir"].startswith(folder + "/")
    ]
    if not notes:
        return f'No notes under {folder or "the vault root"}.'
    out = []
    last = None
    for n in notes:
        if n["dir"] != last:
            out.append(f'{n["dir"] or "(vault root)"}/')
            last = n["dir"]
        out.append(_line(n, True))
    return "\n".join(out)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--home", type=pathlib.Path)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build", help="rebuild the cached map and print it")
    s = sub.add_parser("show", help="list a folder with every note and its sections")
    s.add_argument("folder", nargs="?", default="")
    sub.add_parser("stats", help="size of the map against its budget")
    a = p.parse_args()
    c = cc.load(a.home)
    if a.cmd == "build":
        print(
            build(c, force=True)
            or "Vault index is switched off (vault_index_tokens is 0)."
        )
    elif a.cmd == "show":
        print(show(c, a.folder))
    else:
        notes = scan(c)
        text = build(c, force=True)
        print(
            json.dumps(
                {
                    "notes": len(notes),
                    "with_sections": sum(1 for n in notes if n["headings"]),
                    "budget_chars": budget_chars(c),
                    "map_chars": len(text),
                },
                indent=1,
            )
        )


if __name__ == "__main__":
    main()
