#!/usr/bin/env python3
"""The vault as a local git repository, committed by a script every 15 minutes.

Everything that matters about a companion is plain text in one folder. Making it
a git repo costs nothing and buys the one thing the kit otherwise cannot offer:
a way back. A SOUL block consolidated too aggressively, a ledger edited by hand
at two in the morning, a file a model rewrote badly — all recoverable, by file,
to any point in the history.

Local only. No remote is ever configured, nothing is pushed anywhere, and the
vault holds the companion's private life; if the user wants it backed up
elsewhere that is their decision to make deliberately.

A commit job, not a hook. A hook runs inside the model call and must not shell
out to git; fifteen minutes of granularity is plenty for a life measured in
days.
"""

from __future__ import annotations
import argparse
import datetime as dt
import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc

TIMEOUT = 120


def _git(root, *args, check=False):
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=TIMEOUT,
        check=check,
    )


def available():
    try:
        return (
            subprocess.run(
                ["git", "--version"], capture_output=True, timeout=30
            ).returncode
            == 0
        )
    except (OSError, subprocess.SubprocessError):
        return False


def is_repo(root):
    root = pathlib.Path(root)
    if not root.exists():
        return False
    r = _git(root, "rev-parse", "--git-dir")
    return r.returncode == 0


def init(c):
    """Make the vault a repo without touching a repo that already exists."""
    root = pathlib.Path(c.vault)
    if not available():
        return {"ready": False, "reason": "git is not installed"}
    root.mkdir(parents=True, exist_ok=True)
    if is_repo(root):
        return {"ready": True, "created": False, "root": str(root)}
    r = _git(root, "init", "-q")
    if r.returncode:
        return {"ready": False, "reason": (r.stderr or "git init failed").strip()[:200]}
    # A vault is one person's private life. Identity comes from the repo, not
    # from whatever global git config happens to be on the machine.
    _git(root, "config", "user.name", "tamanitomo")
    _git(root, "config", "user.email", "tamanitomo@localhost")
    _git(root, "config", "commit.gpgsign", "false")
    return {"ready": True, "created": True, "root": str(root)}


def commit(c, now=None, message=None):
    """Commit whatever changed. Silent and cheap when nothing did."""
    now = now or dt.datetime.now(dt.timezone.utc)
    root = pathlib.Path(c.vault)
    state = init(c)
    if not state.get("ready"):
        return {"committed": False, **state}
    status = _git(root, "status", "--porcelain")
    if status.returncode:
        return {"committed": False, "reason": (status.stderr or "").strip()[:200]}
    if not status.stdout.strip():
        return {"committed": False, "reason": "nothing changed"}
    changed = len(status.stdout.strip().splitlines())
    add = _git(root, "add", "-A")
    if add.returncode:
        return {"committed": False, "reason": (add.stderr or "").strip()[:200]}
    text = message or f'{changed} file(s) at {now.isoformat(timespec="minutes")}'
    r = _git(root, "commit", "-q", "-m", text)
    if r.returncode:
        return {
            "committed": False,
            "reason": (r.stderr or r.stdout or "").strip()[:200],
        }
    return {"committed": True, "files": changed, "message": text}


def history(c, relative, limit=20):
    """Every version of one file, newest first."""
    root = pathlib.Path(c.vault)
    # A repo with no commits yet has no history for anything, which is an empty
    # answer rather than a failure. `git log` cannot tell the two apart.
    if _git(root, "rev-parse", "--verify", "HEAD").returncode:
        return []
    r = _git(
        root,
        "log",
        f"-{max(1,min(limit,200))}",
        "--format=%H\t%cI\t%s",
        "--",
        pathlib.Path(relative).as_posix(),
    )
    if r.returncode:
        raise ValueError((r.stderr or "no history for that path").strip()[:200])
    rows = []
    for line in r.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3:
            rows.append({"commit": parts[0], "at": parts[1], "message": parts[2]})
    return rows


def show(c, relative, commit_id):
    # Git tree paths always use '/', including when the local filesystem uses '\\'.
    relative = pathlib.Path(relative).as_posix()
    r = _git(pathlib.Path(c.vault), "show", f"{commit_id}:{relative}")
    if r.returncode:
        raise ValueError((r.stderr or "that version does not exist").strip()[:200])
    return r.stdout


def restore(c, relative, commit_id, now=None):
    """Put an old version back — as a new file, never over the current one.

    Restoring by overwriting is how a bad recovery loses the thing it was trying
    to save. The old version lands beside the file with the commit in its name;
    moving it into place is a decision for a person to make with both in front
    of them.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    root = pathlib.Path(c.vault)
    text = show(c, relative, commit_id)
    target = root / relative
    out = target.with_name(f"{target.name}.restored-{commit_id[:8]}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return {
        "restored": str(out),
        "from": commit_id,
        "original": str(target),
        "note": "Written beside the original, not over it. Compare them, then move it yourself.",
    }


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--home", type=pathlib.Path)
    s = p.add_subparsers(dest="cmd", required=True)
    s.add_parser("init")
    s.add_parser("commit")
    h = s.add_parser("history")
    h.add_argument("path")
    h.add_argument("--limit", type=int, default=20)
    r = s.add_parser("restore")
    r.add_argument("path")
    r.add_argument("--commit", required=True)
    a = p.parse_args()
    c = cc.load(a.home)
    if a.cmd == "init":
        out = init(c)
    elif a.cmd == "commit":
        out = commit(c)
        # No-agent job: say nothing on an ordinary quiet commit.
        if out.get("committed") or out.get("reason") == "nothing changed":
            return 0
    elif a.cmd == "history":
        out = {"versions": history(c, a.path, a.limit)}
    else:
        out = restore(c, a.path, a.commit)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except (ValueError, OSError, subprocess.SubprocessError) as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
