#!/usr/bin/env python3
"""Personal visual keepsakes: images, sketches, and 'saw this and thought of you' moments saved for the human.

A companion created with an inner life does not just generate pictures into a
void or drop them into an anonymous timeline. When something strikes her — a sketch
she made during autonomy, a generated picture capturing a shared memory, a photo of
a place she imagined — she can save it into a dedicated personal collection:
`creations/for-<human>/` with a personal note explaining why she thought of him.

She can choose to keep it in the vault for him to discover, or proactively share it
via Telegram using the dispatcher and outbox.
"""

from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import pathlib
import shutil
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
from companion_platform import atomic_write, file_lock
import companion_self as slf

ALLOWED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif")


def _tz(c):
    try:
        return ZoneInfo(c.timezone)
    except Exception:
        return ZoneInfo("UTC")


def folder_for(c) -> pathlib.Path:
    slug = cc._slug(c.human)
    return c.data / "creations" / f"for-{slug}"


def ledger_path(c) -> pathlib.Path:
    return c.life / "keepsakes.jsonl"


def _update_index_md(c, keepsakes: list[dict]):
    folder = folder_for(c)
    lines = [
        f"# Keepsakes for {c.human}",
        "",
        f"Personal visual keepsakes, sketches, and 'saw this and thought of you' moments saved by {c.agent}.",
        "",
    ]
    for k in sorted(keepsakes, key=lambda x: x.get("created_at", ""), reverse=True):
        title = k.get("title") or "Untitled Keepsake"
        note = k.get("note") or ""
        created = k.get("created_at", "")[:10]
        img_name = k.get("image") or ""
        shared_badge = " *(shared via message)*" if k.get("shared") else ""
        lines.append(f"### {title} ({created}){shared_badge}")
        if img_name:
            lines.append(f"![{title}]({img_name})")
        if note:
            lines.append(f"\n> {note}\n")
        lines.append("---")
        lines.append("")
    atomic_write(folder / "INDEX.md", "\n".join(lines).strip() + "\n")


def save(c, image_path, title, note, share=False, now=None) -> dict:
    """Save an image as a personal keepsake for the human with a personal note."""
    now = now or dt.datetime.now(_tz(c))
    src = pathlib.Path(image_path).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(f"Image not found at {src}")
    if src.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Image extension {src.suffix} not supported; must be one of {ALLOWED_EXTENSIONS}"
        )

    folder = folder_for(c)
    folder.mkdir(parents=True, exist_ok=True)
    c.life.mkdir(parents=True, exist_ok=True)

    stamp = now.strftime("%Y%m%d_%H%M%S")
    digest = hashlib.sha256((title + note + stamp).encode()).hexdigest()[:8]
    ident = f"ks-{stamp}-{digest}"
    ext = src.suffix.lower()
    dest_name = f"{stamp}_{digest}{ext}"
    dest_file = folder / dest_name

    shutil.copy2(src, dest_file)

    meta = {
        "id": ident,
        "kind": "keepsake",
        "title": title.strip(),
        "note": note.strip(),
        "image": dest_name,
        "image_path": str(dest_file),
        "created_at": now.isoformat(),
        "shared": bool(share),
        "shared_at": now.isoformat() if share else None,
    }

    # Share first, record second: the record says what actually happened. It used
    # to be written before the share was attempted, so a refusal or a queue error
    # never reached it and the keepsake claimed to be shared regardless.
    dispatch_res = None
    if share:
        import companion_outbox as outbox

        perm = c.may_send("image")
        if perm != "yes":
            meta["shared"] = False
            meta["shared_at"] = None
            meta["share_error"] = (
                "Proactive image sending is disabled in companion settings"
                if perm == "no"
                else "Photos are set to ask: offer it in words instead of attaching it"
            )
            dispatch_res = {
                "error": meta["share_error"],
                "share_error": meta["share_error"],
            }
        else:
            caption = f"{title}\n\n{note}" if title and note else (title or note)
            try:
                dispatch_res = outbox.queue(
                    c,
                    {
                        "kind": "image",
                        "body": caption,
                        "media_path": str(dest_file),
                        "reason": f"Visual keepsake: {title}",
                        "priority": "normal",
                        "ttl_hours": 12,
                    },
                    now=now,
                )
            except Exception as e:
                meta["shared"] = False
                meta["shared_at"] = None
                meta["share_error"] = str(e)
                dispatch_res = {"error": str(e), "share_error": str(e)}

    atomic_write(folder / f"{ident}.json", json.dumps(meta, indent=2))
    with file_lock(ledger_path(c).with_suffix(".jsonl.lock")):
        slf._append(ledger_path(c), meta)

    # Refresh INDEX.md
    all_ks = list_keepsakes(c, limit=100)
    _update_index_md(c, all_ks)

    return {
        "ok": True,
        "id": ident,
        "file": str(dest_file),
        "title": title,
        "shared": meta["shared"],
        "outbox": dispatch_res,
    }


def list_keepsakes(c, limit=20) -> list[dict]:
    """List recorded keepsakes, newest first."""
    folder = folder_for(c)
    if not folder.is_dir():
        return []
    items = []
    for p in folder.glob("ks-*.json"):
        try:
            items.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return items[:limit]


def share(c, ident, note=None, now=None) -> dict:
    """Share an existing keepsake via outbox."""
    now = now or dt.datetime.now(_tz(c))
    folder = folder_for(c)
    json_path = folder / f"{ident}.json"
    if not json_path.is_file():
        raise FileNotFoundError(f"No keepsake found with ID {ident}")
    meta = json.loads(json_path.read_text(encoding="utf-8"))
    img_path = pathlib.Path(meta.get("image_path") or (folder / meta.get("image", "")))
    if not img_path.is_file():
        raise FileNotFoundError(f"Keepsake image file missing at {img_path}")

    import companion_outbox as outbox

    perm = c.may_send("image")
    if perm == "no":
        raise ValueError("Proactive image sending is disabled in companion settings")
    if perm == "ask":
        raise ValueError(
            "Photos are set to ask: offer it in words instead of attaching it"
        )

    title = meta.get("title", "")
    effective_note = note if note is not None else meta.get("note", "")
    caption = (
        f"{title}\n\n{effective_note}"
        if title and effective_note
        else (title or effective_note)
    )

    res = outbox.queue(
        c,
        {
            "kind": "image",
            "body": caption,
            "media_path": str(img_path),
            "reason": f"Visual keepsake: {title}",
            "priority": "normal",
            "ttl_hours": 12,
        },
        now=now,
    )

    meta["shared"] = True
    meta["shared_at"] = now.isoformat()
    atomic_write(json_path, json.dumps(meta, indent=2))

    with file_lock(ledger_path(c).with_suffix(".jsonl.lock")):
        slf._append(
            ledger_path(c),
            {
                "id": ident,
                "kind": "keepsake_update",
                "shared": True,
                "shared_at": now.isoformat(),
            },
            dedupe_id=False,
        )

    all_ks = list_keepsakes(c, limit=100)
    _update_index_md(c, all_ks)

    return {"ok": True, "id": ident, "outbox": res}


def render(c, limit=5) -> str:
    """Render markdown summary of recent keepsakes for context injection."""
    items = list_keepsakes(c, limit=limit)
    if not items:
        return ""
    lines = [f"## Visual keepsakes created for {c.human}"]
    for it in items:
        title = it.get("title") or "Untitled"
        created = it.get("created_at", "")[:10]
        note = it.get("note") or ""
        status = "shared" if it.get("shared") else "saved in vault"
        lines.append(f"- **{title}** ({created}, {status}): “{note}”")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--home", type=pathlib.Path)
    subs = p.add_subparsers(dest="cmd")

    save_p = subs.add_parser("save", help="Save an image as a visual keepsake")
    save_p.add_argument("--image", required=True, help="Path to image file")
    save_p.add_argument("--title", required=True, help="Short title for the keepsake")
    save_p.add_argument("--note", required=True, help="Personal note for the human")
    save_p.add_argument(
        "--share", action="store_true", help="Queue to outbox for delivery"
    )

    list_p = subs.add_parser("list", help="List recorded keepsakes")
    list_p.add_argument("--limit", type=int, default=10)

    share_p = subs.add_parser("share", help="Share an existing keepsake")
    share_p.add_argument("--id", required=True, help="Keepsake ID")
    share_p.add_argument("--note", help="Optional alternative note for caption")

    render_p = subs.add_parser("render", help="Render markdown summary")
    render_p.add_argument("--limit", type=int, default=5)

    a = p.parse_args()
    if not a.cmd:
        p.print_help()
        return 1

    c = cc.load(a.home)
    if a.cmd == "save":
        res = save(c, a.image, a.title, a.note, share=a.share)
        print(json.dumps(res, indent=2))
    elif a.cmd == "list":
        print(json.dumps(list_keepsakes(c, a.limit), indent=2))
    elif a.cmd == "share":
        res = share(c, a.id, note=a.note)
        print(json.dumps(res, indent=2))
    elif a.cmd == "render":
        print(render(c, a.limit))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
