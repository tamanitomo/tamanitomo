"""Versioned companion recovery bundles. Never overwrite an existing installation."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import sqlite3
import stat
import tempfile
import time
import zipfile
from contextlib import closing, nullcontext

import yaml

import companion_config as cc
from companion_platform import atomic_write, file_lock

FORMAT = "tamanitomo-companion"
VERSION = 1
MAX_BYTES = 2_000_000_000
MAX_FILES = 100_000
SKIP_DIRS = {
    "__pycache__",
    ".venv",
    "node_modules",
    "hermes-agent",
    ".cache",
    "profiles",
    "profiles-removed",
    ".tamanitomo-app",
    ".companion-app",
}
CREDENTIAL_FILES = {
    ".env",
    "auth.json",
    "credentials.json",
    "credentials.yaml",
    "credentials.yml",
    "token.json",
    "tokens.json",
    "access.json",
    "id_rsa",
    "id_ed25519",
    "cookies.txt",
    "cookies.json",
    ".tamanitomo-access.json",
}
SECRET_KEY = re.compile(
    r"(?:^|_)(?:api_key|access_token|refresh_token|token|password|secret|remote_pin|private_key|client_secret|authorization|credential|credentials)(?:$|_)",
    re.I,
)
ROOT_FILES = {"config.yaml", ".env", "auth.json"}


def _credential(path):
    return (
        path.name.lower() in CREDENTIAL_FILES
        or path.name.startswith(".env.")
        or any(
            p.lower() in {"credentials", "auth", "secrets", ".ssh", ".aws"}
            for p in path.parts
        )
    )


def _redact(value):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            normalized = (
                re.sub(r"(?<=[a-z])(?=[A-Z])", "_", str(key)).lower().replace("-", "_")
            )
            secret = SECRET_KEY.search(normalized) or normalized == "key"
            out[key] = (
                ""
                if secret and not normalized.endswith(("_env", "_env_var"))
                else _redact(item)
            )
        return out
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _json(data):
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _name(name):
    if not isinstance(name, str) or "\x00" in name:
        raise ValueError("Unsafe path in recovery bundle")
    path = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or ":" in name
        or path.is_absolute()
        or any(p in (".", "..", "") for p in name.split("/"))
    ):
        raise ValueError("Unsafe path in recovery bundle")
    if path.parts[0] not in {"home", "vault", "root"} or len(path.parts) < 2:
        raise ValueError("Unknown location in recovery bundle")
    if path.parts[0] == "root" and "/".join(path.parts[1:]) not in ROOT_FILES:
        raise ValueError("Unknown inherited root file in recovery bundle")
    if any(
        part.endswith((".", " "))
        or part.split(".")[0].upper()
        in {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }
        for part in path.parts
    ):
        raise ValueError("Recovery path is not portable across supported hosts")
    return path


def _control(name):
    path = PurePosixPath(name)
    return (
        path.name in {cc.CONFIG_NAME, "config.yaml", "config.yml", ".env", "auth.json"}
        or "cron" in path.parts
    )


def _snapshot(source, target):
    """SQLite's backup API includes committed WAL data without copying live locks."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as stream:
        header = stream.read(16)
    if header == b"SQLite format 3\x00":
        with closing(
            sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True, timeout=3)
        ) as original:
            with closing(sqlite3.connect(target)) as saved:
                deadline = time.monotonic() + 30

                def progress(status, remaining, total):
                    if time.monotonic() > deadline:
                        raise ValueError(
                            "Database is busy; retry the backup when it is idle"
                        )

                original.backup(saved, pages=256, progress=progress)
    else:
        before = source.stat()
        shutil.copyfile(source, target)
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError(f"A file changed during backup; retry: {source.name}")


def _scope_transcript(c, target, shared):
    """Prune only the copied database, retaining this profile's IDs and lineage."""
    with closing(sqlite3.connect(target)) as db:
        db.execute("PRAGMA journal_mode=DELETE")
        columns = {r[1] for r in db.execute("PRAGMA table_info(sessions)")}
        message_columns = {r[1] for r in db.execute("PRAGMA table_info(messages)")}
        if (
            not {"id", "source"} <= columns
            or not {"id", "session_id"} <= message_columns
        ):
            raise ValueError(
                "Unsupported transcript database; cannot verify profile ownership"
            )
        if shared and "profile_name" not in columns:
            raise ValueError(
                "Shared transcript database lacks profile labels; preserve the full installation before migrating"
            )
        if "profile_name" not in columns:
            scope, values = "1=1", ()
        elif c.is_root:
            scope, values = "lower(coalesce(profile_name,'')) IN ('','default')", ()
        elif shared:
            scope, values = "lower(coalesce(profile_name,''))=?", (c.profile.lower(),)
        else:
            scope, values = "lower(coalesce(profile_name,'')) IN ('','default',?)", (
                c.profile.lower(),
            )
        db.execute(
            "CREATE TEMP TABLE retained_sessions AS SELECT id FROM sessions WHERE "
            + scope,
            values,
        )
        if (
            "parent_session_id" in columns
            and db.execute(
                "SELECT 1 FROM sessions WHERE id IN (SELECT id FROM retained_sessions) AND parent_session_id IS NOT NULL AND parent_session_id<>'' AND parent_session_id NOT IN (SELECT id FROM retained_sessions) LIMIT 1"
            ).fetchone()
        ):
            raise ValueError(
                "Transcript history crosses profile ownership boundaries; preserve the full installation before migrating"
            )
        before = db.execute("SELECT count(*) FROM sessions").fetchone()[0]
        tables = [
            (row[0], row[1] or "")
            for row in db.execute(
                "SELECT name,sql FROM sqlite_master WHERE type='table'"
            )
        ]
        fts_sql = next((sql for name, sql in tables if name == "messages_fts"), None)
        fts_columns = (
            [row[1] for row in db.execute("PRAGMA table_info(messages_fts)")]
            if fts_sql
            else []
        )
        if fts_sql and (
            not fts_columns or any(name not in message_columns for name in fts_columns)
        ):
            raise ValueError(
                "Unsupported transcript search index; cannot preserve a scoped backup"
            )
        # Keep native triggers in place while deleting rows, then rebuild FTS so
        # even an index without delete triggers cannot retain another profile's text.
        for name, sql in tables:
            if (
                name in {"sessions", "messages"}
                or name.startswith(("sqlite_", "messages_fts"))
                or "VIRTUAL TABLE" in sql.upper()
            ):
                continue
            quoted = '"' + name.replace('"', '""') + '"'
            fields = {row[1] for row in db.execute("PRAGMA table_info(" + quoted + ")")}
            if "session_id" in fields:
                db.execute(
                    "DELETE FROM "
                    + quoted
                    + " WHERE session_id IS NOT NULL AND session_id NOT IN (SELECT id FROM retained_sessions)"
                )
            elif "message_id" in fields:
                db.execute(
                    "DELETE FROM "
                    + quoted
                    + " WHERE message_id NOT IN (SELECT id FROM messages WHERE session_id IN (SELECT id FROM retained_sessions))"
                )
        db.execute(
            "DELETE FROM messages WHERE session_id IS NULL OR session_id NOT IN (SELECT id FROM retained_sessions)"
        )
        db.execute(
            "DELETE FROM sessions WHERE id NOT IN (SELECT id FROM retained_sessions)"
        )
        if fts_sql:
            db.execute("DROP TABLE messages_fts")
            db.execute(fts_sql)
            names = ",".join(
                '"' + name.replace('"', '""') + '"' for name in fts_columns
            )
            db.execute(
                f"INSERT INTO messages_fts(rowid,{names}) SELECT id,{names} FROM messages"
            )
        kept = db.execute("SELECT count(*) FROM sessions").fetchone()[0]
        db.commit()
        db.execute("VACUUM")
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Transcript snapshot failed its integrity check")
        return {
            "sessions_retained": kept,
            "other_sessions_excluded": before - kept,
            "shared_source": shared,
        }


def _transcript_source(c, source):
    """Find the live WAL name when a database inode has several path aliases."""
    resolved = source.resolve()
    if resolved.stat().st_nlink <= 1:
        return resolved
    candidates = [resolved, c.hermes_root / "state.db"]
    directory = c.hermes_root / "profiles"
    if directory.is_dir():
        candidates.extend(
            path / "state.db" for path in directory.iterdir() if path.is_dir()
        )
    aliases = {
        path.resolve()
        for path in candidates
        if path.exists() and path.samefile(resolved)
    }
    if len(aliases) < resolved.stat().st_nlink:
        raise ValueError(
            "Cannot locate all hard-linked transcript files and their journals; preserve the full installation before migrating"
        )
    journals = [
        path
        for path in aliases
        if path.with_name(path.name + "-wal").is_file()
        and path.with_name(path.name + "-wal").stat().st_size > 0
    ]
    if len(journals) > 1:
        raise ValueError(
            "Several hard-linked transcript files have live journals; close Hermes and checkpoint before backing up"
        )
    return journals[0] if journals else resolved


def export(c, destination, *, include_credentials=False):
    """Snapshot the selected profile and its whole vault, including local history."""
    destination = Path(destination).expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Choose a new backup filename")
    if not (c.home / cc.CONFIG_NAME).is_file():
        raise ValueError("Create or adopt a companion before backing it up")
    if c.home.is_symlink() or c.vault.is_symlink():
        raise ValueError("Use the real profile and vault paths for a recovery backup")
    sources = {"home": c.home.resolve(), "vault": c.vault.resolve()}
    manifest = {
        "format": FORMAT,
        "version": VERSION,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "agent": c.agent,
        "profile": c.profile,
        "credentials_included": bool(include_credentials),
        "original": {
            "home": str(c.home),
            "root": str(c.hermes_root),
            "vault": str(c.vault),
            "kit": str(Path(__file__).resolve().parents[2]),
        },
        "files": {},
        "links": {},
        "excluded": [],
        "materialized_links": [],
        "note": "Includes the entire shared vault. Credentials omitted by default; notes and conversation history can still contain sensitive information.",
    }
    total = 0
    with tempfile.TemporaryDirectory(prefix="tamanitomo-backup-") as temporary:
        stage = Path(temporary)

        def add(source, name, ancestors=()):
            nonlocal total
            _name(name)
            if not include_credentials and (
                _credential(Path(name)) or _credential(source.resolve())
            ):
                manifest["excluded"].append(name)
                return
            if len(manifest["files"]) + len(manifest["links"]) >= MAX_FILES:
                raise ValueError("Recovery bundle contains too many files or links")
            if source.is_symlink():
                resolved = source.resolve()
                if not resolved.exists():
                    raise ValueError(
                        f"Broken link cannot be preserved in recovery: {name}"
                    )
                if (
                    resolved.is_file()
                    and not _control(name)
                    and name != "home/state.db"
                ):
                    for label, root in sources.items():
                        if resolved.is_relative_to(root):
                            manifest["links"][name] = (
                                label + "/" + resolved.relative_to(root).as_posix()
                            )
                            return
                manifest["materialized_links"].append(name)
            if source.is_dir():
                resolved = source.resolve()
                if resolved in ancestors:
                    raise ValueError(
                        f"Directory link cycle cannot be preserved: {name}"
                    )
                for child in sorted(source.iterdir()):
                    if name.startswith("home/") and child.name in SKIP_DIRS:
                        manifest["excluded"].append(name + "/" + child.name + "/")
                        continue
                    if child.name.endswith(
                        (".lock", ".pid", "-wal", "-shm", "-journal")
                    ):
                        continue
                    add(child, name + "/" + child.name, (*ancestors, resolved))
                return
            if not source.is_file():
                raise ValueError(f"Unsupported special file in recovery source: {name}")
            size = source.stat().st_size
            if total + size > MAX_BYTES or len(manifest["files"]) >= MAX_FILES:
                raise ValueError(
                    "Recovery bundles are limited to 2 GB and 100,000 files"
                )
            target = stage / name
            _snapshot(
                _transcript_source(c, source) if name == "home/state.db" else source,
                target,
            )
            if name == "home/state.db":
                import companion_transcript

                if c.is_root and source.resolve().is_relative_to(
                    (c.hermes_root / "profiles").resolve()
                ):
                    raise ValueError(
                        "Root transcript store points into a named profile"
                    )
                manifest["transcript"] = _scope_transcript(
                    c, target, bool(c.profile and companion_transcript.shared_store(c))
                )
            if not include_credentials and source.name in (
                "config.yaml",
                "config.yml",
                cc.CONFIG_NAME,
            ):
                data = yaml.safe_load(target.read_text(encoding="utf-8"))
                redacted = _redact(data)
                target.write_text(
                    (
                        _json(redacted)
                        if source.suffix == ".json"
                        else yaml.safe_dump(redacted, sort_keys=False)
                    ),
                    encoding="utf-8",
                )
            raw = target.read_bytes()
            total += len(raw)
            if total > MAX_BYTES:
                raise ValueError("Recovery bundle exceeds 2 GB")
            manifest["files"][name] = {
                "size": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }

        for label, root in sources.items():
            if not root.is_dir():
                raise ValueError(f"Missing {label} directory")

            def failed_walk(error):
                raise ValueError(
                    f"Cannot read recovery source directory: {error.filename}"
                ) from error

            for directory, dirs, files in os.walk(
                root, followlinks=False, onerror=failed_walk
            ):
                directory = Path(directory)
                for name in list(dirs):
                    path = directory / name
                    relative = label + "/" + path.relative_to(root).as_posix()
                    if path.is_symlink():
                        add(path, relative)
                        dirs.remove(name)
                    elif (label == "home" and name in SKIP_DIRS) or (
                        label == "home" and path.resolve() == sources["vault"]
                    ):
                        manifest["excluded"].append(relative + "/")
                        dirs.remove(name)
                for name in sorted(files):
                    source = directory / name
                    relative = label + "/" + source.relative_to(root).as_posix()
                    if source.absolute() == destination or name.endswith(
                        (".lock", ".pid", "-wal", "-shm", "-journal")
                    ):
                        continue
                    add(source, relative)
        if not c.is_root:
            for name in ("config.yaml", ".env", "auth.json"):
                source = c.hermes_root / name
                if source.is_file():
                    add(source, "root/" + name)
        # A skipped external link must never turn into an invented empty identity.
        if (
            "home/SOUL.md" not in manifest["files"]
            and "home/SOUL.md" not in manifest["links"]
        ):
            if c.canonical_soul.is_file():
                add(c.canonical_soul, "home/SOUL.md")
        manifest["bytes"] = total
        manifest["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        destination.parent.mkdir(parents=True, exist_ok=True)
        created = False
        try:
            descriptor = os.open(
                destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
            )
            created = True
            with os.fdopen(descriptor, "wb") as stream:
                with zipfile.ZipFile(
                    stream, "w", compression=zipfile.ZIP_DEFLATED
                ) as archive:
                    archive.writestr("manifest.json", _json(manifest))
                    for name in manifest["files"]:
                        archive.write(stage / name, name)
            os.chmod(destination, 0o600)
            inspect(destination)
        except Exception:
            if created:
                destination.unlink(missing_ok=True)
            raise
    return manifest


def inspect(bundle, *, extract_to=None):
    try:
        return _inspect(bundle, extract_to=extract_to)
    except (
        zipfile.BadZipFile,
        json.JSONDecodeError,
        UnicodeError,
        KeyError,
        TypeError,
        RuntimeError,
        NotImplementedError,
    ) as exc:
        raise ValueError("Malformed recovery bundle") from exc


def _inspect(bundle, *, extract_to=None):
    """Validate every member and hash before any restored installation is published."""
    with zipfile.ZipFile(bundle) as archive:
        entries = archive.infolist()
        if (
            len(entries) > MAX_FILES + 1
            or sum(row.file_size for row in entries) > MAX_BYTES + 20_000_000
        ):
            raise ValueError("Recovery bundle is too large")
        names = [row.filename for row in entries]
        if len(set(name.casefold() for name in names)) != len(names):
            raise ValueError("Duplicate paths in recovery bundle")
        if (
            "manifest.json" not in names
            or archive.getinfo("manifest.json").file_size > 20_000_000
        ):
            raise ValueError("Missing or oversized recovery manifest")
        manifest = json.loads(archive.read("manifest.json"))
        if (
            not isinstance(manifest, dict)
            or manifest.get("format") != FORMAT
            or manifest.get("version") != VERSION
        ):
            raise ValueError("Unsupported recovery bundle version")
        files = manifest.get("files")
        links = manifest.get("links", {})
        if (
            not isinstance(files, dict)
            or not isinstance(links, dict)
            or set(names) != {"manifest.json", *files}
        ):
            raise ValueError("Recovery manifest does not match its files")
        if (
            not isinstance(manifest.get("profile"), str)
            or not isinstance(manifest.get("agent"), str)
            or not isinstance(manifest.get("original"), dict)
            or not isinstance(manifest.get("created_at"), str)
            or type(manifest.get("credentials_included")) is not bool
        ):
            raise ValueError("Missing recovery metadata")
        if any(not isinstance(value, str) for value in manifest["original"].values()):
            raise ValueError("Invalid original recovery paths")
        all_paths = set(files) | set(links)
        if (
            len(all_paths) != len(files) + len(links)
            or len({name.casefold() for name in all_paths}) != len(all_paths)
            or len(all_paths) > MAX_FILES
        ):
            raise ValueError("Conflicting recovery paths")
        folded = {name.casefold() for name in all_paths}
        for name in all_paths:
            path = _name(name)
            if any(parent.as_posix().casefold() in folded for parent in path.parents):
                raise ValueError("A recovery file conflicts with a directory")
        if any(
            not isinstance(expected, dict)
            or type(expected.get("size")) is not int
            or expected["size"] < 0
            or not isinstance(expected.get("sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected["sha256"])
            for expected in files.values()
        ):
            raise ValueError("Invalid file metadata in recovery bundle")
        actual_bytes = sum(expected["size"] for expected in files.values())
        if manifest.get("bytes") != actual_bytes or actual_bytes > MAX_BYTES:
            raise ValueError("Recovery byte total does not match its files")
        if not manifest["profile"] and any(
            name.startswith("root/") for name in all_paths
        ):
            raise ValueError("Default profile cannot overlay inherited root files")
        if "home/companion.json" not in files:
            raise ValueError("Recovery bundle has no companion configuration")
        if manifest.get("profile"):
            from companion_platform import profile_name

            profile_name(manifest["profile"])
        for name, target in links.items():
            _name(name)
            _name(target)
            if _control(name) or name == "home/state.db" or target not in files:
                raise ValueError("Recovery link must refer to a bundled regular file")
        if (
            actual_bytes + sum(files[target]["size"] for target in links.values())
            > MAX_BYTES
        ):
            raise ValueError("Expanded recovery links exceed the size limit")
        for name, expected in files.items():
            _name(name)
            entry = archive.getinfo(name)
            if (
                stat.S_IFMT(entry.external_attr >> 16) not in (0, stat.S_IFREG)
                or entry.is_dir()
                or entry.file_size != expected.get("size")
            ):
                raise ValueError("Invalid file metadata in recovery bundle")
            digest = hashlib.sha256()
            target = Path(extract_to) / name if extract_to else None
            if target:
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.parent.resolve().is_relative_to(
                    Path(extract_to).resolve()
                ):
                    raise ValueError(
                        "Recovery extraction cannot cross a directory link"
                    )
            with archive.open(name) as source:
                with target.open("xb") if target else nullcontext() as output:
                    while chunk := source.read(1024 * 1024):
                        digest.update(chunk)
                        if output:
                            output.write(chunk)
            if digest.hexdigest() != expected.get("sha256"):
                raise ValueError("Recovery file failed its integrity check")
        manifest["links"] = links
        if not isinstance(manifest.get("excluded", []), list) or any(
            not isinstance(name, str) for name in manifest.get("excluded", [])
        ):
            raise ValueError("Invalid recovery exclusions")
        manifest.setdefault("excluded", [])
        manifest.setdefault(
            "note",
            "Restore creates a separate installation with scheduled jobs paused.",
        )
        return manifest


def _replace(value, mappings):
    if isinstance(value, str):
        replacements = {before: after for before, after in reversed(mappings) if before}
        if not replacements:
            return value
        pattern = "|".join(
            re.escape(key) for key in sorted(replacements, key=len, reverse=True)
        )
        return re.sub(pattern, lambda match: replacements[match.group()], value)
    if isinstance(value, list):
        return [_replace(item, mappings) for item in value]
    if isinstance(value, dict):
        return {key: _replace(item, mappings) for key, item in value.items()}
    return value


def restore(bundle, root, vault):
    """Restore to two new directories; all jobs paused, outbound queue held for review."""
    root, vault = (
        Path(root).expanduser().absolute(),
        Path(vault).expanduser().absolute(),
    )
    if root.exists() or vault.exists() or root.is_symlink() or vault.is_symlink():
        raise FileExistsError("Restore needs new, unused Hermes and vault directories")
    if root.resolve().is_relative_to(vault.resolve()) or vault.resolve().is_relative_to(
        root.resolve()
    ):
        raise ValueError("Choose separate Hermes and vault directories")
    root.parent.mkdir(parents=True, exist_ok=True)
    vault.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(root.parent / ".tamanitomo-restore.lock"):
        if root.exists() or vault.exists():
            raise FileExistsError("A restore destination is already in use")
        with tempfile.TemporaryDirectory(
            prefix=".tamanitomo-restore-", dir=root.parent
        ) as temporary:
            stage = Path(temporary)
            manifest = inspect(bundle, extract_to=stage / "unpacked")
            data = stage / "unpacked"
            profile = manifest["profile"]
            home = root / "profiles" / profile if profile else root
            staged_root, staged_vault = stage / "root", stage / "vault"
            staged_home = staged_root / "profiles" / profile if profile else staged_root
            staged_home.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(data / "home"), str(staged_home))
            if (data / "root").exists():
                shutil.copytree(data / "root", staged_root, dirs_exist_ok=True)
            (
                shutil.move(str(data / "vault"), str(staged_vault))
                if (data / "vault").exists()
                else staged_vault.mkdir()
            )
            original = manifest.get("original", {})
            mappings = sorted(
                [
                    (str(original.get("home", "")), str(home)),
                    (str(original.get("vault", "")), str(vault)),
                    (str(original.get("root", "")), str(root)),
                    (
                        str(original.get("kit", "")),
                        str(Path(__file__).resolve().parents[2]),
                    ),
                ],
                key=lambda pair: -len(pair[0]),
            )
            roots = {"home": staged_home, "root": staged_root, "vault": staged_vault}
            for name, target in manifest["links"].items():
                left, right = _name(name), _name(target)
                dest = roots[left.parts[0]].joinpath(*left.parts[1:])
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(roots[right.parts[0]].joinpath(*right.parts[1:]), dest)
            config = _replace(
                json.loads((staged_home / cc.CONFIG_NAME).read_text(encoding="utf-8")),
                mappings,
            )
            if not isinstance(config, dict):
                raise ValueError("Invalid companion configuration in recovery bundle")
            previous_outreach = config.get("outreach", "updates_only")
            config.update(
                hermes_root=str(root),
                vault=str(vault),
                profile=profile,
                cron_active=False,
                remote_pin="",
                outreach="never",
            )
            (staged_home / cc.CONFIG_NAME).write_text(_json(config), encoding="utf-8")
            for folder in {staged_root, staged_home}:
                access = folder / ".tamanitomo-access.json"
                if access.exists():
                    access.write_text(_json({"remote_pin": ""}), encoding="utf-8")
                for config_name in ("config.yaml", "config.yml"):
                    path = folder / config_name
                    if path.exists():
                        settings = _replace(
                            yaml.safe_load(path.read_text(encoding="utf-8")) or {},
                            mappings,
                        )
                        if not isinstance(settings, dict):
                            raise ValueError(
                                "Invalid Hermes configuration in recovery bundle"
                            )
                        # Starting a restored gateway is a deliberate setup step.
                        settings.pop("platforms", None)
                        path.write_text(
                            yaml.safe_dump(settings, sort_keys=False), encoding="utf-8"
                        )
                for path in (folder / "cron").glob("*.py"):
                    path.write_text(
                        _replace(path.read_text(encoding="utf-8"), mappings),
                        encoding="utf-8",
                    )
                path = folder / "cron/jobs.json"
                if path.exists():
                    jobs = _replace(
                        json.loads(path.read_text(encoding="utf-8")), mappings
                    )
                    rows = jobs.get("jobs", []) if isinstance(jobs, dict) else jobs
                    if not isinstance(rows, list) or any(
                        not isinstance(job, dict) for job in rows
                    ):
                        raise ValueError("Invalid scheduled jobs in recovery bundle")
                    for job in rows:
                        job.update(enabled=False, paused=True, next_run_at=None)
                    path.write_text(_json(jobs), encoding="utf-8")
            note = {
                "restored_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "source_created_at": manifest["created_at"],
                "credentials_included": manifest["credentials_included"],
                "previous_outreach": previous_outreach,
                "review_required": True,
                "note": "Jobs paused and outreach set to never. Review provider credentials, hooks, channel destinations and pending outbox before enabling routines.",
            }
            atomic_write(staged_home / "recovery.json", _json(note))
            created = []
            try:
                for source, destination in ((staged_vault, vault), (staged_root, root)):
                    destination.mkdir(mode=0o700)
                    created.append(destination)
                    shutil.copytree(source, destination, dirs_exist_ok=True)
                restored_roots = {"home": home, "root": root, "vault": vault}
                materialized = []
                for name, target in manifest["links"].items():
                    left, right = _name(name), _name(target)
                    dest = restored_roots[left.parts[0]].joinpath(*left.parts[1:])
                    origin = restored_roots[right.parts[0]].joinpath(*right.parts[1:])
                    link = dest.with_name(
                        dest.name + ".restore-" + secrets.token_hex(8)
                    )
                    linked = False
                    try:
                        link.symlink_to(os.path.relpath(origin, dest.parent))
                        linked = True
                        os.replace(link, dest)
                    except OSError:
                        if linked:
                            link.unlink(missing_ok=True)
                        shutil.copyfile(origin, dest)
                        materialized.append(name)
                note["links_restored_as_copies"] = materialized
                if materialized:
                    note[
                        "note"
                    ] += " This host could not recreate some file links; their contents were preserved as copies. Review recovery.json before editing linked identity files."
                atomic_write(home / "recovery.json", _json(note))
                for directory in (root, vault):
                    for path in directory.rglob("*"):
                        if not path.is_symlink():
                            os.chmod(path, 0o700 if path.is_dir() else 0o600)
            except Exception:
                for destination in reversed(created):
                    shutil.rmtree(destination)
                raise
            return {
                "root": str(root),
                "vault": str(vault),
                "home": str(home),
                "profile": profile or "default",
                "agent": manifest["agent"],
                "note": note["note"],
            }
