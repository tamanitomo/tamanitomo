#!/usr/bin/env python3
"""The queue every outbound message passes through, and nothing bypasses.

Deciding to say something and saying it are two different acts, and the second
one is where a limit can actually be enforced. The lesson is on the record: a
companion whose restraint lived only in a prompt sent the same pulse-tick
report four to six times a day for a week, held a backlog through quiet hours,
and then flushed the whole thing at ten past midnight.

So: a job may only ever *queue*. A dispatcher that runs without a model decides
whether anything leaves, one message at a time. Queue entries carry a priority,
an earliest time, and an expiry — and an expired message is dropped, never sent
late. Something worth saying at 9pm is not worth saying at 2am, and a backlog
delivered at once is the single most alarming thing a companion can do.

Append-only, like every ledger here: queueing appends an entry, every decision
about it appends another, and the current state is the fold.
"""

from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
from companion_platform import file_lock
import companion_self as slf

KINDS = ("text", "image", "voice")
PRIORITIES = ("normal", "high")
STATUSES = ("queued", "sent", "expired", "failed", "withheld")  # what mark() may write
# Delivery states: an attempt in progress, and what can end one.
# An entry in a PHASE is owned by exactly one attempt; only that attempt's guarded
# transition() moves it on, and a dispatcher that died mid-attempt is resolved by the
# next run under the run lock (companion_dispatch.recover).
PHASES = ("dispatching", "reserving_slot", "slot_reserved", "sending")
OUTCOMES = (
    "sent",
    "failed",
    "unknown",
    "withheld",
    "expired",
    "reservation_unresolved",
)
ALL_STATUSES = ("queued",) + PHASES + OUTCOMES
DEFAULT_TTL_HOURS = 8
# Hermes delivery platforms. A target is where a message goes, never who it is for:
# a model that wrote "target": "<the human's name>" queued messages Hermes could only
# refuse ("Unknown or unregistered plugin platform"), and they failed at send time.
PLATFORMS = (
    "telegram",
    "discord",
    "slack",
    "signal",
    "whatsapp",
    "matrix",
    "weixin",
    "feishu",
    "dingtalk",
    "ntfy",
    "simplex",
    "qqbot",
    "yuanbao",
    "email",
    "sms",
)


def check_target(value, human="the human"):
    """'telegram' when absent; a platform or platform:chat_id when given; else refused."""
    target = str(value or "").strip() or "telegram"
    platform = target.split(":", 1)[0].lower()
    if platform not in PLATFORMS or len(target) > 80:
        raise ValueError(
            f'target must be a delivery platform such as "telegram", not a person. '
            f"Leave target out and it reaches {human} on the usual channel."
        )
    return target


MAX_QUEUED = 20
# Saying the same thing again. Her messages are compared with what she sent (or
# still has on its way) in the last two weeks: by the weighted share of their
# content words, as facts are, and by how they open. Calibrated on two live
# outboxes (2026-10-11): the same message re-sent scored 0.34-0.51, everything
# else 0.30 or less. Short messages are not compared -- a good-night is a ritual,
# not a repeat.
REPEAT_DAYS = 14
SAME_MESSAGE = 0.33
MIN_WORDS = 6
OPENER_WORDS = 3
OPENER_REPEATS = 3
OPENER_WINDOW = 10
EARLIER_SHOWN = 8


def _tz(c):
    try:
        return ZoneInfo(c.timezone)
    except Exception:
        return ZoneInfo("UTC")


def path_for(c):
    return c.life / "outbox.jsonl"


def _iso(value, tz, label):
    if not value:
        return ""
    try:
        when = dt.datetime.fromisoformat(str(value))
        return (when if when.tzinfo else when.replace(tzinfo=tz)).isoformat()
    except ValueError:
        raise ValueError(f"{label} must be an ISO timestamp")


def queue(c, entry, now=None):
    """Put one message in the queue. Nothing is sent here."""
    now = now or dt.datetime.now(_tz(c))
    tz = _tz(c)
    kind = entry.get("kind", "text")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    body = (entry.get("body") or "").strip()
    if not body:
        raise ValueError("body required")
    if len(body) > 4000:
        raise ValueError("body must be at most 4000 characters")
    priority = entry.get("priority", "normal")
    if priority not in PRIORITIES:
        raise ValueError(f"priority must be one of {PRIORITIES}")
    media = (entry.get("media_path") or "").strip()
    if kind in ("image", "voice") and not media:
        raise ValueError(f"a {kind} needs media_path pointing at the file to send")
    if media and not pathlib.Path(media).is_absolute():
        raise ValueError("media_path must be absolute")
    ttl = entry.get("ttl_hours", DEFAULT_TTL_HOURS)
    if not isinstance(ttl, (int, float)) or not 0 < ttl <= 168:
        raise ValueError("ttl_hours must be a positive number of hours, at most a week")
    with file_lock(path_for(c).with_suffix(".jsonl.lock")):
        history = fold(c)
        waiting = [e for e in history if e["status"] == "queued"]
        if len(waiting) >= MAX_QUEUED:
            raise ValueError(
                f"{len(waiting)} messages are already waiting; the queue is full, "
                f"which means nothing is going out and something is wrong"
            )
        for prior in waiting:
            if (
                prior.get("content") == kind
                and prior.get("body", "").strip() == body.strip()
            ):
                return {"written": False, "entry": prior}
        again = repeats(c, body, now, history)
        if again:
            raise ValueError(again)
        row = {
            "id": entry.get("id")
            or "msg-"
            + hashlib.sha256(
                (body + kind + now.date().isoformat()).encode()
            ).hexdigest()[:16],
            "kind": "outbox",
            "content": kind,
            "body": body,
            "media_path": media,
            "priority": priority,
            "reason": (entry.get("reason") or "")[:200],
            "not_before": _iso(entry.get("not_before"), tz, "not_before"),
            "expires_at": (now + dt.timedelta(hours=ttl)).isoformat(),
            "target": check_target(
                entry.get("target"), getattr(c, "human", "the human")
            ),
            "status": "queued",
            "queued_at": now.isoformat(),
        }
        return slf._append(path_for(c), row)


def _opener(body):
    words = re.findall(r"[\w'’]+", str(body or "").casefold())
    return " ".join(words[:OPENER_WORDS]) if len(words) >= OPENER_WORDS else ""


def _said(history, now, tz):
    """(when, entry) for what she sent, or still has on its way, in the window."""
    out = []
    for entry in history:
        status = entry.get("status")
        if status not in ("sent", "queued") + PHASES:
            continue
        stamp = entry.get("decided_at") if status == "sent" else entry.get("queued_at")
        try:
            at = dt.datetime.fromisoformat(stamp or "")
        except ValueError:
            continue
        at = at if at.tzinfo else at.replace(tzinfo=tz)
        if dt.timedelta(0) <= now - at <= dt.timedelta(days=REPEAT_DAYS):
            out.append((at, entry))
    return sorted(out, key=lambda row: row[0])


def repeats(c, body, now=None, history=None):
    """Why this message would be her saying the same thing again, or None."""
    tz = _tz(c)
    now = now or dt.datetime.now(tz)
    said = _said(fold(c) if history is None else history, now, tz)
    if not said:
        return None
    names = {
        str(n).casefold()
        for n in [getattr(c, "human", ""), getattr(c, "agent", "")]
        + list(getattr(c, "names", []) or [])
        if n
    }
    words = slf._content(body, names)
    if len(words) >= MIN_WORDS:
        sets = [slf._content(e.get("body"), names) for _, e in said]
        weight = slf._weigher(sets + [words])
        for (at, entry), other in zip(said, sets):
            if len(other) < MIN_WORDS:
                continue
            overlap, _ = slf._similarity(words, other, weight)
            if overlap >= SAME_MESSAGE:
                return (
                    f"you already said nearly this on {at.astimezone(tz):%a %d %b}: "
                    f'"{entry.get("body", "")[:120]}". Say something new, or nothing.'
                )
    opener = _opener(body)
    if opener and len(body.split()) >= 8:
        sent = [e for _, e in said if e.get("status") == "sent"][-OPENER_WINDOW:]
        same = [e for e in sent if _opener(e.get("body")) == opener]
        if len(same) >= OPENER_REPEATS:
            return (
                f'{len(same)} of your last {len(sent)} messages open with "{opener}"; '
                "open this one another way."
            )
    return None


def mark(c, ident, status, detail="", now=None):
    """Decide a QUEUED entry by hand (or from older code). Guarded like every write here:
    an entry an attempt currently owns, or one already decided, is refused and unchanged.
    """
    now = now or dt.datetime.now(_tz(c))
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")

    def guard():
        entry = current(c, ident)
        if entry is not None and entry["status"] != "queued":
            return {
                "written": False,
                "refused": f"the message is {entry['status']}; only a queued message can be marked",
            }
        return None

    return slf._append(
        path_for(c),
        {
            "id": ident,
            "kind": "outbox_update",
            "status": status,
            "detail": str(detail)[:300],
            "at": now.isoformat(),
        },
        dedupe_id=False,
        guard=guard,
    )


def current(c, ident):
    """The folded entry, or None."""
    return next((e for e in fold(c) if e.get("id") == ident), None)


def transition(c, ident, status, attempt, run_id, expect, now=None, detail="", **extra):
    """Append a guarded delivery attempt. Under the outbox lock, re-read the fold and
    write only if the entry's status is exactly `expect` and, from any phase, its current
    attempt is `attempt`. Otherwise nothing is written: {'written': False, 'refused': why}.
    A stale snapshot, a second dispatcher, or a late update for another attempt changes nothing.
    """
    if status not in ALL_STATUSES:
        raise ValueError(f"status must be one of {ALL_STATUSES}")
    if not attempt:
        raise ValueError("an attempt id is required")
    now = now or dt.datetime.now(_tz(c))

    def guard():
        entry = current(c, ident)
        if entry is None:
            return {"written": False, "refused": "no such message"}
        if entry["status"] != expect:
            return {
                "written": False,
                "refused": f"status is {entry['status']}, not {expect}",
            }
        if expect != "queued" and entry.get("attempt") != attempt:
            return {
                "written": False,
                "refused": "the message belongs to a different attempt",
            }
        return None

    row = {
        "id": ident,
        "kind": "outbox_update",
        "status": status,
        "attempt": attempt,
        "run_id": run_id,
        "detail": str(detail)[:300],
        "at": now.isoformat(),
        **extra,
    }
    return slf._append(path_for(c), row, dedupe_id=False, guard=guard)


def resolve_unknown(
    c, ident, attempt, outcome, delivery, run_id="reconciler", now=None, detail=""
):
    """An `unknown` outcome may be replaced only by the SAME attempt with
    positive evidence (a message_id or an explicit platform result). Nothing is ever resent.
    """
    if outcome not in ("sent", "failed"):
        raise ValueError("a late outcome is sent or failed")
    delivery = dict(delivery or {})
    if not (delivery.get("message_id") or delivery.get("platform_result")):
        return {
            "written": False,
            "refused": "a late outcome needs evidence: a message_id or a platform result",
        }
    return transition(
        c,
        ident,
        outcome,
        attempt,
        run_id,
        "unknown",
        now,
        detail,
        delivery=delivery,
        late=True,
    )


def fold(c):
    """Current state of every message ever queued, oldest first."""
    latest = {}
    for row in slf._read(path_for(c)):
        ident = row.get("id")
        if row.get("kind") == "outbox":
            latest.setdefault(ident, dict(row))
        elif row.get("kind") == "outbox_update" and ident in latest:
            item = latest[ident]
            item["status"] = row.get("status", item["status"])
            item["decided_at"] = row.get("at", "")
            if row.get("detail"):
                item["detail"] = row["detail"]
            # Attempt ownership follows the latest row (absent on pre-1B rows).
            item["attempt"] = row.get("attempt")
            item["run_id"] = row.get("run_id")
            for key in ("delivery", "not_dispatched", "release_reason", "error_code"):
                item.pop(key, None)  # never carried over from an earlier attempt
                if key in row:
                    item[key] = row[key]
    return sorted(latest.values(), key=lambda e: e["queued_at"])


def waiting(c, now=None):
    """Queued messages in the order a dispatcher should consider them."""
    now = now or dt.datetime.now(_tz(c))
    rows = [e for e in fold(c) if e["status"] == "queued"]
    order = {"high": 0, "normal": 1}
    return sorted(rows, key=lambda e: (order.get(e["priority"], 1), e["queued_at"]))


def expired(entry, now):
    try:
        return dt.datetime.fromisoformat(entry["expires_at"]) < now
    except (ValueError, KeyError):
        return False


def held_until(entry, now):
    if not entry.get("not_before"):
        return False
    try:
        return dt.datetime.fromisoformat(entry["not_before"]) > now
    except ValueError:
        return False


def render(c, now=None):
    rows = waiting(c, now)
    if not rows:
        return ""
    return "\n".join(
        f"- {e['content']}: {e['body'][:120]}"
        + (f" (not before {e['not_before'][11:16]})" if e.get("not_before") else "")
        for e in rows
    )


UNCONFIRMED = (
    " (sent; delivery not confirmed, it most likely arrived: do not send it again)"
)


def sent_recently(c, now=None, hours=24, limit=6):
    """What she actually sent in the last day, oldest first, as (sent_at, entry).

    A sent message is meant to be copied into her conversation too, and that copy can
    fail; when it did, she had no record of a photo she had just sent and was surprised
    by the reply to it. The ledger is the record that does not depend on the copy."""
    tz = _tz(c)
    now = now or dt.datetime.now(tz)
    rows = []
    for entry in fold(c):
        # An unconfirmed send went out as far as anyone can tell. Left off this list,
        # a photo whose upload timed out -- and that arrived anyway -- read to her as
        # never sent, so she waited for it in a towel and queued it twice more.
        if entry.get("status") not in ("sent", "unknown"):
            continue
        try:
            at = dt.datetime.fromisoformat(entry.get("decided_at") or "")
        except ValueError:
            continue
        at = at if at.tzinfo else at.replace(tzinfo=tz)
        if dt.timedelta(0) <= now - at <= dt.timedelta(hours=hours):
            rows.append((at, entry))
    rows.sort(key=lambda row: row[0])
    return rows[-limit:]


def render_sent(c, now=None):
    """The last day in full, and the rest of the fortnight in a line each, so
    she can see what she has been saying and not say it again."""
    tz = _tz(c)
    recent = sent_recently(c, now)
    lines = [
        f"- {at.astimezone(tz):%a %H:%M} {e['content']}: {e['body'][:120]}"
        + (UNCONFIRMED if e.get("status") == "unknown" else "")
        for at, e in recent
    ]
    shown = {e.get("id") for _, e in recent}
    earlier = [
        (at, e)
        for at, e in sent_recently(c, now, hours=24 * REPEAT_DAYS, limit=200)
        if e.get("id") not in shown
    ][-EARLIER_SHOWN:]
    if earlier:
        lines.append("Earlier these two weeks (say something new, not these again):")
        lines += [
            f"- {at.astimezone(tz):%a %d %b} {e['content']}: {e['body'][:70]}"
            for at, e in earlier
        ]
    return "\n".join(lines)


def batch(c, path, now=None):
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "entries" in data:
        data = data["entries"]
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not data:
        raise ValueError("file must hold one message or a list of them")
    if len(data) > 5:
        raise ValueError("queue at most five messages at once")
    out = []
    for i, entry in enumerate(data):
        try:
            out.append(
                {"index": i, "ok": True, "id": queue(c, entry, now)["entry"]["id"]}
            )
        except (ValueError, OSError) as exc:
            out.append({"index": i, "ok": False, "error": str(exc)})
            return {
                "queued": sum(1 for r in out if r["ok"]),
                "failed_at": i,
                "results": out,
            }
    return {"queued": len(out), "failed_at": None, "results": out}


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--home", type=pathlib.Path)
    s = p.add_subparsers(dest="cmd", required=True)
    q = s.add_parser("queue", help="queue one or more messages from a JSON file")
    q.add_argument("--file", type=pathlib.Path, required=True)
    l = s.add_parser("list")
    l.add_argument("--status", choices=list(ALL_STATUSES) + ["all"], default="queued")
    d = s.add_parser("drop", help="withdraw a queued message")
    d.add_argument("--id", required=True)
    a = p.parse_args()
    c = cc.load(a.home)
    if a.cmd == "queue":
        out = batch(c, a.file)
    elif a.cmd == "drop":
        out = mark(c, a.id, "withheld", "withdrawn by hand")
    else:
        rows = fold(c)
        out = {
            "messages": (
                rows
                if a.status == "all"
                else [r for r in rows if r["status"] == a.status]
            )
        }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, json.JSONDecodeError) as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
