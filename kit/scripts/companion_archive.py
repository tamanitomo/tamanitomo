#!/usr/bin/env python3
"""The conversation archive: every conversation with the human, month by month, as plain files in the vault.

The conversations themselves live in Hermes's session database, which a companion meant to last decades should not
have to outlive. Here every message between the two of them (every channel her thread counts: messaging, the app,
a wearable, a game; never a scheduled job or a tool) is copied once into `<vault>/conversations/<year>/<year>-<month>`:
a `.jsonl` with the exact record, and a `.md` a person (or she, with her file tools) can read. The vault is committed
to git every fifteen minutes and backed up with it, so the archive survives a database that is lost, migrated or
pruned. Append-only: what was said stays said.

It runs with the vault commit job, so it costs nothing new: a cursor remembers the last message copied, and a run
with nothing new reads only the newest rows. No model is called.
"""

from __future__ import annotations
import argparse
import datetime as dt
import json
import pathlib
from zoneinfo import ZoneInfo

import companion_config as cc
from companion_platform import atomic_write, file_lock

CHANNELS = {
    "telegram": "Telegram",
    "workspace": "the app",
    "terminal": "a terminal",
    "api": "another app",
}


def folder(c):
    return pathlib.Path(c.data) / "conversations"


def cursor_path(c):
    return pathlib.Path(c.home) / "state" / "conversation-archive.json"


def _tz(c):
    try:
        return ZoneInfo(c.timezone or "UTC")
    except Exception:  # noqa: BLE001
        return ZoneInfo("UTC")


def _cursor(c):
    try:
        data = json.loads(cursor_path(c).read_text(encoding="utf-8"))
        return (
            float(data.get("after_stamp", 0)),
            int(data.get("after_id", 0)),
            dict(data.get("days") or {}),
        )
    except (OSError, ValueError, TypeError):
        return 0.0, 0, {}


def update(c, now=None, limit=20000):
    """Copy every message since the last run. Returns {"copied": n, "months": [...]}."""
    import companion_transcript as transcript

    now = now or dt.datetime.now(dt.timezone.utc)
    tz = _tz(c)
    base = folder(c)
    with file_lock(cursor_path(c).with_suffix(".lock")):
        after_stamp, after_id, days = _cursor(c)

        def read(view):
            if view is None:
                return []
            rows = []
            for record in view.forward(after_stamp, after_id, now.timestamp()):
                rows.append(record)
                if len(rows) >= limit:
                    break
            return rows

        try:
            records = transcript.owner_evidence(c, read)
        except (transcript.SourceUnavailable, ValueError, OSError) as exc:
            return {"copied": 0, "months": [], "reason": str(exc)[:200]}
        if not records:
            return {"copied": 0, "months": []}
        by_month = {}
        for record in records:
            at = dt.datetime.fromtimestamp(record.occurred_at, tz)
            by_month.setdefault(at.strftime("%Y-%m"), []).append((at, record))
        for month, rows in sorted(by_month.items()):
            year = month[:4]
            target = base / year
            target.mkdir(parents=True, exist_ok=True)
            jsonl, md = target / f"{month}.jsonl", target / f"{month}.md"
            lines, text = [], []
            if not md.exists():
                first = rows[0][0]
                text.append(f"# Conversations, {first.strftime('%B %Y')}\n")
            last_day = days.get(month, "")
            for at, record in rows:
                speaker = c.human if record.speaker == "owner" else c.agent
                channel = record.channel or CHANNELS.get(
                    record.source_kind, record.source_kind
                )
                lines.append(
                    json.dumps(
                        {
                            "id": record.source_message,
                            "session": record.source_session,
                            "at": at.isoformat(timespec="seconds"),
                            "channel": channel,
                            "speaker": speaker,
                            "who": record.speaker,
                            "text": record.content,
                        },
                        ensure_ascii=False,
                    )
                )
                day = at.date().isoformat()
                if day != last_day:
                    text.append(
                        f"\n## {at.strftime('%A')} {at.day} {at.strftime('%B')}\n"
                    )
                    last_day = day
                body = (record.content or "").replace("\n", "\n  ")
                text.append(
                    f"**{at.strftime('%H:%M')} · {channel} · {speaker}:** {body}\n"
                )
            with jsonl.open("a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            with md.open("a", encoding="utf-8") as f:
                f.write("".join(text))
            days[month] = last_day
        last = records[-1]
        state = {
            "after_stamp": last.occurred_at,
            "after_id": int(last.source_message),
            "days": dict(sorted(days.items())[-3:]),
            "updated_at": now.isoformat(timespec="seconds"),
        }
        cursor_path(c).parent.mkdir(parents=True, exist_ok=True)
        atomic_write(cursor_path(c), json.dumps(state))
        return {"copied": len(records), "months": sorted(by_month)}


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--home", type=pathlib.Path)
    args = parser.parse_args()
    print(json.dumps(update(cc.load(args.home))))


if __name__ == "__main__":
    main()
