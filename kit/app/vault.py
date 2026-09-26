"""Constrained vault browsing and optimistic writes to user-owned notes."""

from __future__ import annotations
import hashlib
import json
import datetime as dt
import uuid
import os
from pathlib import Path
import companion_platform as cp
import companion_peer as peer

MAX_TEXT = 2_000_000
TEXT = {".md", ".txt", ".json", ".jsonl", ".yaml", ".yml", ".csv"}


def resolve(c, relative=""):
    if not isinstance(relative, str) or "\\" in relative or "\x00" in relative:
        raise ValueError("Use a relative vault path")
    rel = Path(relative)
    if rel.is_absolute() or any(
        p in ("..", ".") or p.startswith(".") for p in rel.parts
    ):
        raise ValueError("Path must stay inside the vault; hidden files are excluded")
    if peer.is_secret(rel):
        raise ValueError("Credential files are not served by the vault browser")
    root = c.vault.resolve()
    path = (root / rel).resolve()
    if path != root and root not in path.parents:
        raise ValueError("Path leaves the vault")
    if any(p.startswith(".") for p in path.relative_to(root).parts):
        raise ValueError("Hidden files are excluded")
    return path


def editable(c, relative):
    rel = Path(relative)
    return rel.suffix.lower() == ".md" and not protected(c, relative)


def protected(c, relative):
    """Protect runtime state and identity for every companion in a shared vault."""
    path = resolve(c, relative)
    parts = {p.lower() for p in path.relative_to(c.vault.resolve()).parts}
    critical = {
        "soul.md",
        "agents.md",
        "user.md",
        "memory.md",
        "config.yaml",
        "config.yml",
        "companion.json",
        "profile.yaml",
        "requirements.txt",
        "pyproject.toml",
        "package.json",
        "package-lock.json",
        "uv.lock",
    }
    return (
        path.name.lower() in critical
        or bool(parts & {"companion-life", "soul", "hooks", "scripts", "hermes-agent"})
        or path.suffix.lower()
        in {
            ".db",
            ".db-wal",
            ".db-shm",
            ".sqlite",
            ".sqlite3",
            ".py",
            ".sh",
            ".ps1",
            ".cmd",
        }
        or path == c.soul.resolve()
        or path == c.canonical_soul.resolve()
        or path == c.home.resolve()
        or c.home.resolve() in path.parents
    )


def metadata(c, relative):
    locked = protected(c, relative)
    return {
        "protected": locked,
        "editable": editable(c, relative),
        "deletable": not locked and resolve(c, relative).is_file(),
        "protection_reason": (
            "Installation or companion state. Read-only in Vault; use its dedicated settings editor."
            if locked
            else ""
        ),
    }


def listing(c, relative=""):
    path = resolve(c, relative)
    if not path.is_dir():
        raise ValueError("Vault folder does not exist")
    rows = []
    for p in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        rel = p.relative_to(c.vault.resolve()).as_posix()
        try:
            target = resolve(c, rel)
            if p.is_symlink():
                continue
            stat = target.stat()
        except (ValueError, OSError):
            continue
        rows.append(
            {
                "name": p.name,
                "path": rel,
                "directory": target.is_dir(),
                "bytes": stat.st_size,
                "modified": stat.st_mtime,
                **metadata(c, rel),
            }
        )
        if len(rows) >= 2000:
            break
    return {"path": relative, "entries": rows, "root": str(c.vault), "limit": 2000}


def read(c, relative):
    path = resolve(c, relative)
    if not path.is_file() or path.suffix.lower() not in TEXT:
        raise ValueError("Select a text or Markdown file")
    if path.stat().st_size > MAX_TEXT:
        raise ValueError("This file is too large for the editor (2 MB limit)")
    data = path.read_bytes()
    return {
        "path": relative,
        "text": data.decode("utf-8"),
        "revision": hashlib.sha256(data).hexdigest(),
        **metadata(c, relative),
    }


def trash(c, relative, revision=None):
    path = resolve(c, relative)
    if not path.is_file() or protected(c, relative):
        raise ValueError("This file is protected or is not a regular file")
    with cp.file_lock(c.vault / ".companion-editor.lock"):
        if (
            revision is not None
            and hashlib.sha256(path.read_bytes()).hexdigest() != revision
        ):
            raise FileExistsError(
                "This file changed since you opened it. Reload before moving it to trash."
            )
        ident = uuid.uuid4().hex
        folder = c.vault / ".trash" / "tamanitomo" / ident
        if (c.vault / ".trash").is_symlink() or (
            c.vault / ".trash" / "tamanitomo"
        ).is_symlink():
            raise ValueError("Trash must not be a symbolic link")
        folder.mkdir(parents=True)
        cp.atomic_write(
            folder / "metadata.json",
            json.dumps(
                {
                    "id": ident,
                    "path": relative,
                    "deleted_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                }
            ),
        )
        os.replace(path, folder / "file")
    return {"trashed": relative, "id": ident}


def trash_list(c):
    rows = []
    for sub in ("tamanitomo", "companion-kit"):
        root = c.vault / ".trash" / sub
        if root.exists():
            if root.is_symlink() or root.parent.is_symlink():
                raise ValueError("Trash must not be a symbolic link")
            if root.is_dir():
                for folder in root.iterdir():
                    if folder.is_symlink() or not (folder / "file").is_file():
                        continue
                    try:
                        rows.append(json.loads((folder / "metadata.json").read_text()))
                    except (OSError, ValueError):
                        continue
    return {"files": sorted(rows, key=lambda r: r["deleted_at"], reverse=True)}


def restore(c, ident):
    if not isinstance(ident, str) or not __import__("re").fullmatch(
        "[a-f0-9]{32}", ident
    ):
        raise ValueError("Invalid trash entry")
    folder = c.vault / ".trash" / "tamanitomo" / ident
    if not folder.exists():
        folder = c.vault / ".trash" / "companion-kit" / ident
    if any(
        p.is_symlink()
        for p in (
            folder,
            folder.parent,
            folder.parent.parent,
            folder / "file",
            folder / "metadata.json",
        )
    ):
        raise ValueError("Invalid trash entry")
    with cp.file_lock(c.vault / ".companion-editor.lock"):
        row = json.loads((folder / "metadata.json").read_text())
        dest = resolve(c, row["path"])
        if protected(c, row["path"]):
            raise ValueError("The restore destination is protected")
        if dest.exists():
            raise FileExistsError(
                "A file already exists at the original path. Rename it before restoring."
            )
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(folder / "file", dest)
        (folder / "metadata.json").unlink()
        folder.rmdir()
    return {"restored": row["path"]}


BACKUPS = ".companion-editor-backups"
BACKUP_WINDOW = 600  # seconds: saves closer together than this share one backup
BACKUP_KEEP = 20  # per note, newest kept


def backup_folder(c, relative):
    """This note's editor-backup folder inside the vault, never through a link."""
    base = c.vault / BACKUPS
    folder = base / hashlib.sha256(relative.encode("utf-8")).hexdigest()[:24]
    if any(p.is_symlink() for p in (base, folder)):
        raise ValueError("Editor backups must not be a symbolic link")
    folder.mkdir(parents=True, exist_ok=True)
    if not folder.resolve().is_relative_to(c.vault.resolve()):
        raise ValueError("Editor backups must stay inside the vault")
    return folder


def backup(c, relative, data, now=None):
    """Keep the bytes a save is about to replace, exactly (BOM, CRLF and all).

    The editor saves every few seconds while someone types, so one backup per save
    would grow without bound. Backups are grouped per note and coalesced: when the
    bytes being replaced are exactly what this editor itself last wrote AND the
    newest backup is younger than BACKUP_WINDOW, a save adds none, so the version
    from before an editing session survives it. Bytes written by anything else (an
    external editor, sync, the companion) are always backed up before they are
    replaced. At most BACKUP_KEEP are kept per note. Returns the new backup path,
    or None when coalesced."""
    import time

    now = time.time() if now is None else now
    folder = backup_folder(c, relative)
    kept = sorted(p for p in folder.glob("*.bak") if p.is_file() and not p.is_symlink())
    last = folder / "last-write"
    ours = (
        last.is_file()
        and not last.is_symlink()
        and last.read_text().strip() == hashlib.sha256(data).hexdigest()
    )
    if ours and kept and now - kept[-1].stat().st_mtime < BACKUP_WINDOW:
        return None
    stamp = dt.datetime.fromtimestamp(now, dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = folder / f"{stamp}-{hashlib.sha256(data).hexdigest()[:12]}.bak"
    handle = folder / (".tmp-" + uuid.uuid4().hex)
    with open(handle, "wb") as out:
        out.write(data)
        out.flush()
        os.fsync(out.fileno())
    os.replace(handle, target)
    os.utime(target, (now, now))
    source = folder / "source.json"
    if not source.exists():
        cp.atomic_write(source, json.dumps({"path": relative}))
    for old in (kept + [target])[:-BACKUP_KEEP]:
        old.unlink(missing_ok=True)
    return target


def write(c, relative, text, revision):
    path = resolve(c, relative)
    if not editable(c, relative):
        raise ValueError("The document editor writes Markdown files only.")
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_TEXT:
        raise ValueError("Note exceeds 2 MB")
    with cp.file_lock(c.vault / ".companion-editor.lock"):
        data = path.read_bytes() if path.exists() else None
        current = hashlib.sha256(data).hexdigest() if data is not None else ""
        if current != revision:
            raise FileExistsError(
                "This file changed since you opened it. Reload before saving."
            )
        folder = backup_folder(
            c, relative
        )  # refuses a linked folder before anything is written
        if data is not None:
            backup(c, relative, data)
        cp.atomic_write(path, text)
        # What this editor wrote, so the next save can tell its own bytes from an external edit.
        cp.atomic_write(
            folder / "last-write", hashlib.sha256(text.encode("utf-8")).hexdigest()
        )
    return read(c, relative)


# --- File actions (LINK-05): new folder, duplicate, rename/move ------------------------
#
# One service, one policy, reused by every caller (keyboard, context menu, drag/drop):
# the same resolve()/protected()/editable() boundary as read/write/trash/restore, and the
# same collision/reserved-name/symlink checks regardless of how the action was triggered.
#
# Link-aware rewriting (LINK-06) is layered on top of that: move() rewrites the links
# that point at a renamed/moved NOTE (.md to .md) wherever it can do so unambiguously,
# both directions -- other notes' links to it, and its own relative links to others.
# Scope, stated plainly: this covers note-to-note renames/moves only. A folder move (many
# notes relocating as a unit) and renaming a non-.md asset (an image an embed points at)
# still move exactly as "dumb" about links as the filesystem's own rename is -- extending
# link-awareness to those is real further work, not done here.

RESERVED_STEMS = cp.WINDOWS_RESERVED
FORBIDDEN_CHARS = frozenset('<>:"|?*')


def _validate_name(name):
    """One name (a path component), for every supported platform, not just the one this
    process happens to run on -- a note created on Linux must not become unrenameable
    once synced to a Windows or Termux host."""
    if not name or name in (".", ".."):
        raise ValueError("Invalid name")
    if len(name) > 200:
        raise ValueError("Name is too long")
    if name[-1] in (".", " ") or name[0] == " ":
        raise ValueError(
            "Names cannot start or end with a space, or end with a period (unsafe on Windows)"
        )
    if any(ord(ch) < 32 for ch in name) or FORBIDDEN_CHARS & set(name):
        raise ValueError(r'Names cannot contain control characters or < > : " | ? *')
    stem = name.rsplit(".", 1)[0] if "." in name else name
    if stem.lower() in RESERVED_STEMS:
        raise ValueError(f'"{stem}" is a reserved name on some platforms')


def _validate_path(relative):
    if not isinstance(relative, str):
        raise ValueError("Use a relative vault path")
    rel = Path(relative)
    if rel.is_absolute() or any(p in ("..", ".") for p in rel.parts):
        raise ValueError("Use a relative vault path")
    for part in rel.parts:
        _validate_name(part)


def _no_symlink_on_path(c, path):
    """Every component from `path` up to the vault root, inclusive: a symlink anywhere
    on that chain (including `path` itself, if it already exists) is refused. Walks the
    given path directly -- never `.resolve()` first, which would silently follow a
    symlink and check the WRONG chain."""
    root = c.vault.resolve()
    node = path
    for _ in range(
        200
    ):  # the vault cannot be 200 directories deep; a safety bound, not a real limit
        if node.is_symlink():
            raise ValueError("That path passes through a symbolic link.")
        if node == root or node.parent == node:
            return
        node = node.parent
    raise ValueError("Path is too deep to validate safely.")


def _atomic_write_bytes(path, data):
    """Binary-safe counterpart to companion_platform.atomic_write, which is text-mode
    only (it would raise on bytes, and forcing text mode risks a newline translation
    an exact-byte copy must not have). Same durability shape as vault.backup()'s own
    write: temp file in the destination directory, fsync, then an atomic rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.parent / ("." + path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with open(handle, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(handle, path)
    finally:
        handle.unlink(missing_ok=True)


def mkdir(c, relative):
    _validate_path(relative)
    path = resolve(c, relative)
    if path.exists():
        raise FileExistsError("A file or folder already exists at that path.")
    _no_symlink_on_path(c, c.vault / relative)
    path.mkdir(parents=True)
    return {"created": relative}


def duplicate(c, relative, revision):
    src = resolve(c, relative)
    if not src.is_file():
        raise ValueError("Only an existing file can be duplicated.")
    if protected(c, relative):
        raise ValueError("This file is protected.")
    _no_symlink_on_path(c, c.vault / relative)
    data = src.read_bytes()
    if hashlib.sha256(data).hexdigest() != revision:
        raise FileExistsError(
            "This file changed since you opened it. Reload before duplicating."
        )
    stem, suffix = src.stem, src.suffix
    folder_rel = str(Path(relative).parent) if "/" in relative else ""
    is_text = suffix.lower() in TEXT
    for n in range(1, 10000):
        candidate = f"{stem} copy {n}{suffix}" if n > 1 else f"{stem} copy{suffix}"
        candidate_rel = (
            (folder_rel + "/" + candidate)
            if folder_rel and folder_rel != "."
            else candidate
        )
        _validate_name(candidate)
        dest = resolve(c, candidate_rel)
        if dest.exists():
            continue
        with cp.file_lock(c.vault / ".companion-editor.lock"):
            if dest.exists():
                continue  # lost a race with another duplicate/create
            if is_text:
                cp.atomic_write(dest, data.decode("utf-8"))
            else:
                _atomic_write_bytes(dest, data)
        return {"duplicated": candidate_rel}
    raise ValueError("Too many copies already exist with that name.")


def move(c, relative, dest_relative, revision=None):
    """Rename or move one file or folder. `revision` is REQUIRED and checked for a file
    (the same optimistic-concurrency contract as write/trash/duplicate); a folder has no
    revision concept and moves as a unit regardless. Restore-safety: this never
    overwrites an existing destination, including a case-only rename target on a
    case-INsensitive filesystem, which is handled as a safe two-step through a private
    temporary name rather than risking the OS treating "File.md" -> "file.md" as a
    same-file no-op that could drop the original if anything failed mid-way."""
    _validate_path(dest_relative)
    src = resolve(c, relative)
    if not src.exists():
        raise ValueError("Source does not exist.")
    if protected(c, relative):
        raise ValueError("This file is protected.")
    is_file = src.is_file()
    if is_file:
        if not isinstance(revision, str):
            raise ValueError("A revision is required to rename or move a file.")
        if hashlib.sha256(src.read_bytes()).hexdigest() != revision:
            raise FileExistsError(
                "This file changed since you opened it. Reload before renaming or moving it."
            )
    dest = resolve(c, dest_relative)
    if protected(c, dest_relative):
        raise ValueError("That destination is protected.")
    _no_symlink_on_path(c, c.vault / relative)
    _no_symlink_on_path(c, c.vault / dest_relative)
    # Keep the requested spelling after validation; resolve() may canonicalize
    # an existing destination's case on a case-insensitive filesystem.
    src = c.vault.resolve() / relative
    dest = c.vault.resolve() / dest_relative
    is_note_rename = (
        is_file
        and Path(relative).suffix.lower() == ".md"
        and Path(dest_relative).suffix.lower() == ".md"
    )
    link_lookup = None
    inbound_plan = None
    if is_note_rename:
        # Snapshotted BEFORE the physical move: resolving old_rel against the index
        # requires the index to still contain it.
        from . import vault_link_index as vli

        entries, _ = vli.build(c)
        link_lookup = vli.build_lookup(entries)
        inbound_plan = vli.backlinks(entries, relative)
    case_only = str(src).casefold() == str(dest).casefold() and str(src) != str(dest)
    with cp.file_lock(c.vault / ".companion-editor.lock"):
        if dest.exists() and (not case_only or not src.samefile(dest)):
            raise FileExistsError("A file or folder already exists at the destination.")
        dest.parent.mkdir(parents=True, exist_ok=True)
        if case_only:
            tmp = dest.parent / (".vault-move-" + uuid.uuid4().hex)
            os.replace(src, tmp)
            try:
                os.replace(tmp, dest)
            except OSError:
                if not src.exists():
                    os.replace(tmp, src)
                raise
        else:
            os.replace(src, dest)
        if is_file:
            # Backup history follows the file (its folder is keyed by path hash, so a
            # rename orphans the old one unless it physically moves too): carried only
            # when the destination has no backups of its own yet, never merged/overwritten.
            old_backups = (
                c.vault
                / BACKUPS
                / hashlib.sha256(relative.encode("utf-8")).hexdigest()[:24]
            )
            new_backups = (
                c.vault
                / BACKUPS
                / hashlib.sha256(dest_relative.encode("utf-8")).hexdigest()[:24]
            )
            if (
                old_backups.is_dir()
                and not old_backups.is_symlink()
                and not new_backups.exists()
            ):
                os.replace(old_backups, new_backups)
                cp.atomic_write(
                    new_backups / "source.json", json.dumps({"path": dest_relative})
                )
    result = {"moved": dest_relative}
    if is_note_rename:
        result["links"] = _rewrite_links_after_move(
            c, relative, dest_relative, link_lookup, inbound_plan
        )
    return result


def _rewrite_links_after_move(c, old_relative, new_relative, lookup, inbound_plan):
    """Runs AFTER the physical move above has already committed. Each note gets its own
    ordinary write() -- the same revision check, backup and atomic write as any other
    edit, just computed here instead of typed by a person -- so a note that changed
    concurrently is refused (reported, not silently skipped) rather than clobbered, and
    every rewrite is recoverable exactly the way a manual edit already is."""
    from . import vault_link_index as vli

    updated, skipped = [], []
    for row in inbound_plan["linked"]:
        path = row["path"]
        try:
            current = read(c, path)
        except ValueError:
            skipped.append({"path": path, "reason": "unreadable"})
            continue
        new_text, count = vli.rewrite_inbound_links(
            current["text"], old_relative, new_relative, path, lookup
        )
        if not count:
            continue
        try:
            write(c, path, new_text, current["revision"])
            updated.append({"path": path, "links": count})
        except (FileExistsError, ValueError):
            skipped.append({"path": path, "reason": "changed since it was indexed"})
    own_updated = 0
    try:
        own = read(c, new_relative)
        own_text, own_count = vli.rewrite_own_relative_links(
            own["text"], old_relative, new_relative, lookup
        )
        if own_count:
            write(c, new_relative, own_text, own["revision"])
            own_updated = own_count
    except (FileExistsError, ValueError):
        skipped.append({"path": new_relative, "reason": "changed since the move"})
    return {
        "updated": updated,
        "own_links_updated": own_updated,
        "ambiguous": [
            {"path": r["path"], "candidates": r["candidates"]}
            for r in inbound_plan["ambiguous"]
        ],
        "skipped": skipped,
    }


def files(c, limit=20000):
    import os

    count = 0
    for directory, dirs, names in os.walk(c.vault, followlinks=False):
        dirs[:] = [
            name
            for name in dirs
            if not name.startswith(".") and not (Path(directory) / name).is_symlink()
        ]
        for name in names:
            candidate = Path(directory) / name
            if candidate.is_symlink():
                continue
            rel = candidate.relative_to(c.vault).as_posix()
            try:
                path = resolve(c, rel)
            except ValueError:
                continue
            if not path.is_file():
                continue
            count += 1
            if count > limit:
                raise ValueError(
                    f"The vault has more than {limit:,} files; use the vault folder directly for a full export."
                )
            yield path, rel


def search(c, query):
    if not isinstance(query, str) or not 2 <= len(query) <= 200:
        raise ValueError("Search for 2–200 characters")
    matches = []
    scanned = 0
    needle = query.casefold()
    for path, rel in files(c):
        if path.suffix.lower() not in TEXT or path.stat().st_size > MAX_TEXT:
            continue
        scanned += 1
        try:
            body = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        index = body.casefold().find(needle)
        if index >= 0 or needle in rel.casefold():
            matches.append(
                {"path": rel, "excerpt": body[max(0, index - 80) : max(0, index) + 200]}
            )
        if len(matches) >= 50 or scanned >= 2000:
            break
    return {
        "matches": matches,
        "scanned": scanned,
        "limited": len(matches) >= 50 or scanned >= 2000,
    }
