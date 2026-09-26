"""Profile-owned content catalog for the companion desktop app."""

from __future__ import annotations
from fastapi import Request
import datetime as dt
import hashlib
from functools import lru_cache
import os
import json
import companion_media_review as review
from pathlib import Path
from zoneinfo import ZoneInfo
import re
from urllib.parse import quote
import companion_peer as peer

KINDS = {
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
    ".gif": "image",
    ".mp3": "audio",
    ".wav": "audio",
    ".ogg": "audio",
    ".m4a": "audio",
    ".flac": "audio",
    ".mp4": "video",
    ".webm": "video",
    ".mov": "video",
    ".md": "writing",
    ".txt": "writing",
    ".pdf": "document",
}
EXCLUDED = {
    "soul-backups",
    "memory-archive",
    "__pycache__",
    "captures",
    "node_modules",
    ".git",
}


def resolve(c, relative):
    if not isinstance(relative, str) or "\\" in relative or "\x00" in relative:
        raise ValueError("Invalid content path")
    rel = Path(relative)
    if (
        rel.is_absolute()
        or not rel.parts
        or any(
            p in ("..", ".") or p.startswith(".") or p in EXCLUDED for p in rel.parts
        )
        or peer.is_secret(rel)
        or re.search(
            r"(?i)(?:^|[._-])(credentials?|secrets?|passwords?|tokens?|api[_-]?keys?)(?:[._-]|$)",
            rel.name,
        )
    ):
        raise ValueError("Choose a visible companion content file")
    if c.is_root and rel.parts[0] == "agents":
        raise ValueError("Choose this companion’s own content")
    root = c.data.resolve()
    path = root / rel
    for parent in [path, *path.parents]:
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError("Linked content files are not served")
    path = path.resolve()
    if (
        not path.is_relative_to(root)
        or not path.is_file()
        or path.suffix.lower() not in KINDS
    ):
        raise ValueError("Content file not found")
    return path


def with_etags(c, variants, prefs=None):
    """Each variant, carrying the etag and the review state of its own file.

    Switching variants in the viewer repoints the item at a different picture, so
    without this the delete that follows sent the new path with the old picture's
    etag and was refused as "the file changed" -- every time, for every variant.

    The rating travels with it for the same reason. A variant arrived carrying no
    review at all, so the viewer read it as safe and took the blur off the moment
    you picked one -- the one action you might take precisely because you did not
    want to see it. An unreviewed variant is treated as unreviewed, not as safe.
    """
    if prefs is None:
        prefs = review.preferences(c)
    folder = c.data / "image-timeline/images"
    out = []
    for v in variants:
        if not isinstance(v, dict) or not v.get("filename"):
            continue
        row = dict(v)
        path = folder / v["filename"]
        try:
            stat = path.stat()
            row["etag"] = str(stat.st_mtime_ns) + ":" + str(stat.st_size)
        except OSError:
            row["etag"] = None
        row["path"] = "image-timeline/images/" + v["filename"]
        meta = review.metadata(path)
        row["rating"] = meta.get("rating", "unknown")
        row["review"] = meta.get("review", row.get("review"))
        row["blur"] = review.should_blur(prefs, meta)
        out.append(row)
    return out


def forget_timeline_image(c, relative):
    """Take a deleted timeline image out of the capture that still advertises it.

    The capture id is not the image's stem: a variant is `<id>_v2.png`, so deriving
    the record from the stem looked for `<id>_v2.json` and silently found nothing,
    leaving the picture gone from disk and still listed in the moment.
    """
    if not relative.startswith("image-timeline/images/"):
        return
    import companion_timeline as timeline

    timeline.forget_image(c, Path(relative).name)


def deletable(relative):
    return not relative.startswith(("soul/", "knowledge/", "environment/")) and (
        Path(relative).suffix.lower()
        in {k for k, v in KINDS.items() if v in ("image", "audio", "video")}
        or relative.startswith("creations/")
    )


@lru_cache(maxsize=4096)
def _image_digest(path, mtime_ns, ctime_ns, size, inode):
    # Stat identity invalidates cached hashes when an image is replaced in place.
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def unique_images(rows):
    """Group byte-identical saved copies, retaining every collection membership."""
    groups = {}
    result = []
    for row in rows:
        digest = row.pop("_digest", None)
        if row["kind"] != "image" or digest is None:
            result.append(row)
            continue
        groups.setdefault(digest, []).append(row)
    for digest, copies in groups.items():
        copies.sort(
            key=lambda r: (
                {"creation": 0, "photo session": 1, "album": 2}[r["source"]],
                r["at"],
                r["path"],
            )
        )
        row = dict(copies[0])
        row["content_id"] = digest
        row["at"] = min(r["at"] for r in copies)
        row["copies"] = [
            {k: r[k] for k in ("path", "source", "url", "etag", "deletable")}
            for r in copies
        ]
        row["blur"] = any(r.get("blur", False) for r in copies)
        # A saved copy with a stricter review must not become exposed by grouping.
        row["rating"] = next(
            (
                rating
                for rating in ("nsfw", "unknown", "safe")
                if any(r.get("rating", "unknown") == rating for r in copies)
            ),
            "unknown",
        )
        result.append(row)
    return result


def life_moments(events):
    """Collapse adjacent unchanged snapshots for display, leaving history intact."""
    previous = None
    for row in events:
        state = {k: v for k, v in row["state"].items() if k != "transition"}
        if state != previous:
            yield row
        previous = state


def catalog(
    c,
    limit=1500,
    before=None,
    kind="",
    q="",
    day="",
    collection="all",
    content_id=None,
    reference_paths=None,
):
    from .runtime import _page_cursor, _encode_cursor

    if type(limit) != int or not 1 <= limit <= 1500:
        raise ValueError("Content page size must be 1–1500")
    if kind and kind not in set(KINDS.values()):
        raise ValueError("Unknown content kind")
    if len(q) > 200 or len(collection) > 100:
        raise ValueError("Content filter is too long")
    if day:
        try:
            dt.date.fromisoformat(day)
        except ValueError:
            raise ValueError("Choose a valid photo day")
    cursor = _page_cursor(before)
    if cursor and not isinstance(cursor[1], str):
        raise ValueError("Invalid content cursor")
    prefs = review.preferences(c)
    rows = []
    scanned = 0
    limited = False
    for folder, dirs, names in os.walk(c.data, followlinks=False):
        dirs[:] = sorted(
            d
            for d in dirs
            if not d.startswith(".")
            and d not in EXCLUDED
            and not (Path(folder) / d).is_symlink()
        )
        if c.is_root and Path(folder) == c.data and "agents" in dirs:
            dirs.remove("agents")
        for name in sorted(names):
            scanned += 1
            if scanned > 10000:
                limited = True
                break
            p = Path(folder) / name
            if p.suffix.lower() not in KINDS:
                continue
            rel = p.relative_to(c.data).as_posix()
            try:
                p = resolve(c, rel)
                stat = p.stat()
            except (OSError, ValueError):
                continue
            media_kind = KINDS[p.suffix.lower()]
            if media_kind == "image":
                superseded = review.metadata(p).get("superseded_by")
                if superseded:
                    try:
                        replacement = resolve(c, superseded)
                        if review.metadata(replacement).get("rating") == "safe":
                            continue
                    except (OSError, ValueError):
                        pass
            # Protocol/configuration and rendered state belong in the Vault, not Creations.
            if media_kind == "writing" and (
                rel.startswith("soul/")
                or p.name in ("README.md", "PROTOCOL.md", "PRESENCE.md")
            ):
                continue
            try:
                digest = (
                    _image_digest(
                        str(p),
                        stat.st_mtime_ns,
                        stat.st_ctime_ns,
                        stat.st_size,
                        stat.st_ino,
                    )
                    if media_kind == "image"
                    else None
                )
            except OSError:
                continue
            rows.append(
                {
                    "path": rel,
                    "title": p.stem.replace("_", " ").replace("-", " "),
                    "kind": media_kind,
                    "at": dt.datetime.fromtimestamp(
                        stat.st_mtime, dt.timezone.utc
                    ).isoformat(),
                    "bytes": stat.st_size,
                    "etag": str(stat.st_mtime_ns) + ":" + str(stat.st_size),
                    "deletable": deletable(rel),
                    **({"_digest": digest} if media_kind == "image" else {}),
                    **(
                        {
                            **review.metadata(p),
                            "blur": review.should_blur(prefs, review.metadata(p)),
                        }
                        if media_kind == "image"
                        else {}
                    ),
                    "url": "/api/content/file?path=" + quote(rel, safe=""),
                    "source": (
                        "photo session"
                        if rel.startswith("image-timeline/")
                        else "album" if rel.startswith("albums/") else "creation"
                    ),
                }
            )
        if limited:
            break
    rows = unique_images(rows)
    if kind == "image":
        import companion_timeline as timeline

        captures = {}
        for _, r in timeline.records(c):
            if r.get("status") != "saved":
                continue
            if r.get("filename"):
                captures[r["filename"]] = r
            for v in r.get("variants", []):
                if isinstance(v, dict) and v.get("filename"):
                    captures[v["filename"]] = r
        for row in rows:
            copy = next(
                (x for x in row.get("copies", [row]) if x["source"] == "photo session"),
                None,
            )
            capture = captures.get(Path(copy["path"]).name) if copy else None
            if capture:
                scene = capture.get("scene", {})
                state = scene.get("state", {})
                row.update(
                    at=scene.get("recorded_at") or row["at"],
                    title=state.get("activity") or row["title"],
                    mood=state.get("mood", ""),
                    capture_id=capture.get("id"),
                    capture=capture.get("id"),
                    variants=with_etags(c, capture.get("variants", []), prefs),
                    primary_filename=capture.get(
                        "primary_filename", capture.get("filename")
                    ),
                    prompts=capture.get("prompts") or row.get("prompts"),
                    active_prompt_type=capture.get("active_prompt_type")
                    or row.get("active_prompt_type"),
                )
    if reference_paths is not None:
        rows = [
            row
            for row in rows
            if any(
                copy["path"] in reference_paths
                or str(c.data / copy["path"]) in reference_paths
                for copy in row.get("copies", [row])
            )
        ]
    if content_id:
        rows = [r for r in rows if r.get("content_id") == content_id]
    if kind:
        rows = [r for r in rows if r["kind"] == kind]
    if q:
        rows = [
            r
            for r in rows
            if q.casefold()
            in (r["title"] + " " + r["path"] + " " + str(r.get("mood", ""))).casefold()
        ]
    if day:
        rows = [
            r
            for r in rows
            if dt.datetime.fromisoformat(r["at"])
            .astimezone(ZoneInfo(c.timezone))
            .date()
            .isoformat()
            == day
        ]
    if collection != "all":
        rows = [
            r
            for r in rows
            if any(
                (
                    x["path"].startswith("albums/" + collection[6:] + "/")
                    if collection.startswith("album:")
                    else x["source"] == collection
                )
                for x in r.get("copies", [r])
            )
        ]
    key = lambda r: (dt.datetime.fromisoformat(r["at"]).timestamp(), r["path"])
    rows.sort(key=key, reverse=True)
    total = len(rows)
    if cursor:
        rows = [r for r in rows if key(r) < tuple(cursor)]
    # Chat resolves explicit references across the bounded scan, independent of gallery pages.
    page_limit = limit if reference_paths is None else len(rows)
    more = len(rows) > page_limit
    rows = rows[:page_limit]
    return {
        "timezone": c.timezone,
        "items": rows,
        "limited": limited or more,
        "scan_limited": limited,
        "scanned": scanned,
        "total": total,
        "next_cursor": _encode_cursor(*key(rows[-1])) if more else None,
    }


def journals(c, limit=1000, before=None, q="", month="", entry_id=None):
    if type(limit) != int or not 1 <= limit <= 1000:
        raise ValueError("Journal page size must be 1–1000")
    if len(q) > 200:
        raise ValueError("Journal search must be at most 200 characters")
    if month and not re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])", month):
        raise ValueError("Choose a valid journal month")
    if before and not re.fullmatch(r"\d{4}-\d{2}-\d{2}:[a-f0-9]{20}", before):
        raise ValueError("Invalid journal cursor")
    if entry_id and not re.fullmatch(r"[a-f0-9]{20}", entry_id):
        raise ValueError("Invalid journal entry")
    roots = list(
        dict.fromkeys(
            [
                c.soul_dir / "Lifelog.md",
                c.home / "Lifelog.md",
                *sorted((c.soul_dir / "continuity/archive").glob("Lifelog-*.md")),
                *sorted((c.home / "continuity/archive").glob("Lifelog-*.md")),
            ]
        )
    )
    result = []
    warnings = []
    remaining = 16_000_000
    if len(roots) > 500:
        warnings.append(
            "Only the first 500 journal files were scanned. Additional archives remain in the Vault."
        )
    for path in roots[:500]:
        if not path.exists():
            continue
        contained = False
        for base in (c.data, c.home):
            try:
                parts = path.relative_to(base).parts
            except ValueError:
                continue
            if not any(
                base.joinpath(*parts[:i]).is_symlink() for i in range(1, len(parts) + 1)
            ):
                contained = True
                break
        if not contained:
            warnings.append(
                "A linked journal archive was excluded. Open it from your local vault."
            )
            continue
        if path.is_symlink() or path.stat().st_size > 8_000_000:
            warnings.append(
                "A journal file is linked or too large to preview. Open it from your local vault."
            )
            continue
        size = path.stat().st_size
        if size > remaining:
            warnings.append(
                "Journal preview reached its 16 MB limit. Browse the Vault for additional archives."
            )
            break
        remaining -= size
        try:
            body = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            warnings.append("A journal file could not be read.")
            continue
        matches = list(re.finditer(r"^##\s+(\d{4}-\d{2}-\d{2})[^\n]*$", body, re.M))
        for i, m in enumerate(matches):
            text = body[
                m.end() : matches[i + 1].start() if i + 1 < len(matches) else len(body)
            ].strip()
            if not text:
                continue
            try:
                dt.date.fromisoformat(m.group(1))
            except ValueError:
                continue
            ident = hashlib.sha256((str(path) + str(m.start())).encode()).hexdigest()[
                :20
            ]
            row = {
                "id": ident,
                "day": m.group(1),
                "text": text if entry_id else text[:100000],
                "excerpt": re.sub(r"[#*_`>\[\]]", "", text)[:240],
                "words": len(text.split()),
                "source": path.name,
                "truncated": not entry_id and len(text) > 100000,
            }
            if entry_id:
                if ident == entry_id:
                    return {"timezone": c.timezone, "entry": row}
                continue
            if month and not row["day"].startswith(month):
                continue
            if q and q.casefold() not in (row["day"] + " " + text).casefold():
                continue
            result.append(row)
    if entry_id:
        raise ValueError(
            "This journal entry changed or is no longer available. Refresh the journal list."
        )
    result.sort(key=lambda r: (r["day"], r["id"]), reverse=True)
    total = len(result)
    if before:
        result = [r for r in result if r["day"] + ":" + r["id"] < before]
    more = len(result) > limit
    result = result[:limit]
    return {
        "timezone": c.timezone,
        "entries": result,
        "warnings": warnings,
        "total": total,
        "next_cursor": result[-1]["day"] + ":" + result[-1]["id"] if more else None,
    }


def register(app, load):
    from .scanner import register as register_scanner

    register_scanner(app, load)
    from fastapi import HTTPException
    from fastapi.responses import FileResponse, Response

    @app.get("/api/media/preferences")
    def media_preferences():
        return review.preferences(load())

    @app.post("/api/media/preferences")
    def save_media_preferences(payload: dict):
        c = load()
        result = review.save_preferences(c, payload)
        if (c.data / "image-timeline").is_dir():
            import companion_timeline as timeline

            timeline.render_gallery(c)
        return result

    @app.post("/api/content/rating")
    def rate_content(payload: dict):
        c = load()
        p = resolve(c, payload.get("path", ""))
        if KINDS[p.suffix.lower()] != "image" or payload.get("rating") not in (
            "safe",
            "nsfw",
            "unknown",
        ):
            raise ValueError("Choose an image rating")
        paths = [p]
        stat = p.stat()
        digest = _image_digest(
            str(p), stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, stat.st_ino
        )
        for item in catalog(c, content_id=digest)["items"]:
            copies = item.get("copies", [])
            if any(copy["path"] == payload["path"] for copy in copies):
                paths = [resolve(c, copy["path"]) for copy in copies]
                break
        for path in paths:
            review.write_metadata(
                path, {"rating": payload["rating"], "rating_source": "user"}
            )
        return {"saved": True}

    def _remove(c, relative, p):
        """Delete one file, its review sidecar, its studio record and its capture entry."""
        if p.is_file():
            p.unlink()
            review.sidecar(p).unlink(missing_ok=True)
            if relative.startswith("creations/image-studio/"):
                p.with_suffix(".json").unlink(missing_ok=True)
        forget_timeline_image(c, relative)

    def sibling_copies(c, relative, p):
        """The other saved copies of the same picture, outside the albums.

        Every generated picture is written twice -- once into the studio and once
        into the photo session -- and the two are byte-identical, so the library
        shows them as one photo. Deleting that photo removed whichever copy the
        grouping happened to name first and left the other on disk, whereupon the
        photo reappeared on the next refresh. It looked exactly like a delete
        button that did nothing, and reported success while doing it.

        Album copies are deliberately left alone; the confirmation says so.
        """
        if not p.is_file() or relative.startswith("albums/"):
            return []
        try:
            stat = p.stat()
            digest = _image_digest(
                str(p), stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, stat.st_ino
            )
        except (OSError, ValueError, KeyError):
            return []
        out = []
        for item in catalog(c, content_id=digest)["items"]:
            for copy in item.get("copies", []):
                other = copy["path"]
                if (
                    other == relative
                    or other.startswith("albums/")
                    or not deletable(other)
                ):
                    continue
                try:
                    out.append((other, resolve(c, other)))
                except (OSError, ValueError):
                    pass
        return out

    @app.post("/api/content/delete")
    def delete_content(payload: dict):
        c = load()
        relative = payload.get("path", "")
        p = resolve(c, relative)
        if not deletable(relative):
            raise ValueError("This document is protected; use its dedicated editor")
        # A record can outlive its file -- that is exactly the state a half-finished
        # delete leaves behind -- so a missing file is something to finish tidying
        # rather than an error to refuse.
        if p.is_file():
            stat = p.stat()
            if payload.get("etag") != str(stat.st_mtime_ns) + ":" + str(stat.st_size):
                raise ValueError("The file changed; refresh before deleting")
        others = sibling_copies(c, relative, p)
        _remove(c, relative, p)
        for other, path in others:
            _remove(c, other, path)
        return {
            "deleted": True,
            "path": relative,
            "also_deleted": [other for other, _ in others],
        }

    @app.get("/api/content")
    def list_content(
        limit: int = 1500,
        before: str | None = None,
        kind: str = "",
        q: str = "",
        day: str = "",
        collection: str = "all",
    ):
        return catalog(load(), limit, before, kind, q, day, collection)

    @app.get("/api/journals")
    def read_journals(
        limit: int = 1000, before: str | None = None, q: str = "", month: str = ""
    ):
        return journals(load(), limit, before, q, month)

    @app.get("/api/journals/{ident}")
    def read_journal_entry(ident: str):
        return journals(load(), entry_id=ident)

    @app.post("/api/content/album")
    def save_album(payload: dict):
        import companion_timeline as timeline

        c = load()
        source = resolve(c, payload.get("path", ""))
        album = payload.get("album", "Favorites")
        if KINDS[source.suffix.lower()] != "image":
            raise ValueError("Choose an image to keep")
        if not isinstance(album, str) or not timeline.ALBUM_NAME.fullmatch(album):
            raise ValueError(
                "Use letters, numbers, spaces, hyphens, or underscores for the album name"
            )
        folder = c.data / "albums" / album
        if (
            (c.data / "albums").is_symlink()
            or folder.is_symlink()
            or not folder.resolve().is_relative_to(c.data.resolve())
        ):
            raise ValueError("Album directories must stay inside the companion vault")
        result = timeline.add_to_album(c, str(source), album)
        review.write_metadata(Path(result["file"]), review.metadata(source))
        return {"saved": True, "album": result["album"]}

    @app.post("/api/content/batch-album")
    def batch_album(payload: dict):
        import companion_timeline as timeline

        c = load()
        paths = payload.get("paths", [])
        album = payload.get("album", "Favorites")
        if not isinstance(paths, list) or not paths:
            raise ValueError("Choose at least one image")
        if len(paths) > 200:
            raise ValueError("Too many items in one batch")
        if not isinstance(album, str) or not timeline.ALBUM_NAME.fullmatch(album):
            raise ValueError(
                "Use letters, numbers, spaces, hyphens, or underscores for the album name"
            )
        folder = c.data / "albums" / album
        if (
            (c.data / "albums").is_symlink()
            or folder.is_symlink()
            or not folder.resolve().is_relative_to(c.data.resolve())
        ):
            raise ValueError("Album directories must stay inside the companion vault")
        count = 0
        for rel in paths:
            source = resolve(c, rel)
            if KINDS[source.suffix.lower()] != "image":
                continue
            result = timeline.add_to_album(c, str(source), album)
            review.write_metadata(Path(result["file"]), review.metadata(source))
            count += 1
        return {"saved": True, "album": album, "count": count}

    @app.post("/api/content/batch-delete")
    def batch_delete(payload: dict):
        c = load()
        items = payload.get("items", [])
        if not isinstance(items, list) or not items:
            raise ValueError("Choose at least one file to delete")
        if len(items) > 200:
            raise ValueError("Too many items in one batch")
        # Validate every item before deleting anything.
        resolved = []
        for entry in items:
            relative = entry.get("path", "")
            p = resolve(c, relative)
            if not deletable(relative):
                raise ValueError(f"Protected file cannot be deleted: {relative}")
            # A file already gone is a record still to tidy, not a reason to refuse
            # the whole batch and leave the rest selected.
            if p.is_file():
                stat = p.stat()
                if entry.get("etag") != str(stat.st_mtime_ns) + ":" + str(stat.st_size):
                    raise ValueError(
                        f"A file changed since you selected it. Refresh before deleting."
                    )
            resolved.append((relative, p))
        count = 0
        done = set()
        for relative, p in resolved:
            # The same expansion as a single delete: a photo shown once is deleted
            # once, however many identical copies the pipeline wrote for it.
            others = sibling_copies(c, relative, p)
            if relative not in done:
                _remove(c, relative, p)
                done.add(relative)
                count += 1
            for other, path in others:
                if other in done:
                    continue
                _remove(c, other, path)
                done.add(other)
        return {"deleted": True, "count": count}

    @app.get("/api/content/text")
    def text_content(path: str):
        p = resolve(load(), path)
        if p.suffix.lower() not in (".md", ".txt"):
            raise ValueError("Choose a text document")
        if p.stat().st_size > 2_000_000:
            raise ValueError(
                "This document is too large to preview. Download it instead."
            )
        return {"text": p.read_text(encoding="utf-8"), "path": path}

    @app.get("/api/content/file")
    def content_file(request: Request, path: str, download: bool = False):
        p = resolve(load(), path)
        stat = p.stat()
        tag = f'"{int(stat.st_mtime)}-{stat.st_size}"'
        headers = {
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=604800",
            "ETag": tag,
        }
        if request.headers.get("if-none-match") == tag:
            return Response(status_code=304, headers=headers)
        return FileResponse(p, filename=p.name if download else None, headers=headers)
