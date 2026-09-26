#!/usr/bin/env python3
"""Deliver queued outreach through deterministic checks without an LLM.

A model may write a proposed message, but this maintenance job decides whether
it may leave the outbox. It checks expiry, not-before time, recipient, content
permissions, quiet hours and the durable daily allowance. High priority or
recent recorded human activity can permit delivery during quiet hours; neither
exception raises the daily cap. At most one message is dispatched per run so a
backlog cannot arrive as a burst.

A nonblocking run lock permits only one dispatcher per life directory. Durable
attempt records distinguish claiming an entry, reserving a daily slot and
starting transport. If a process disappears after transport may have started,
recovery records an unknown outcome and never automatically sends it again.
Failed or uncertain delivery retains its slot: an unconfirmed send must not
become a duplicate message through a retry.

This is local outbox bookkeeping, separate from interactive companion chat.
It calls no language model and can continue applying the same boundaries while
inference providers are unavailable. All dispatcher processes sharing one life
directory must follow the same locking and attempt protocol.
"""

from __future__ import annotations
import argparse
import contextlib
import datetime as dt
import json
import os
import pathlib
import secrets
import subprocess
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
import companion_outbox as outbox
import companion_outreach as outreach
from companion_platform import file_lock, hermes_command

RUN_LOCK = ".dispatch.run.lock"
# Hermes `error` strings verified to be returned BEFORE any platform adapter is called
# (observation O-7). Empty until a Hermes source reference is recorded for an entry:
# until then every reported error is `unknown`, never a definite failure.
PRE_PLATFORM_ERRORS = ()


def _hook(name):
    """Test seam at each crash boundary (delivery recovery). A no-op in production; a
    test replaces it to kill the process there. No environment variable is read (U6)."""


def run_lock_path(c):
    return pathlib.Path(c.life) / RUN_LOCK


def _tz(c):
    try:
        return ZoneInfo(c.timezone)
    except Exception:
        return ZoneInfo("UTC")


def recently_active(c, now, minutes=None):
    """Did the human write in the last few minutes?

    Read from the relationship-thread sensor when one is installed. Absent, the
    honest answer is "we do not know", which means the sleep window stands.
    """
    minutes = c.sleep_grace_minutes if minutes is None else minutes
    if not minutes:
        return False
    path = c.soul_dir / "ambient/relationship-thread.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    last = data.get("last_from_human")
    if not last:
        return False
    try:
        when = dt.datetime.fromisoformat(str(last))
    except ValueError:
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=_tz(c))
    return (now - when).total_seconds() <= minutes * 60


def verdict(c, entry, now):
    """Whether this message goes now, and if not, what becomes of it."""
    if outbox.expired(entry, now):
        return {
            "action": "expire",
            "reason": "past its expiry; a stale message is never sent late",
        }
    if outbox.held_until(entry, now):
        return {"action": "hold", "reason": f"not before {entry['not_before'][11:16]}"}
    try:
        outbox.check_target(entry.get("target"), c.human)
    except ValueError as exc:
        return {"action": "withhold", "reason": str(exc)}
    permission = c.may_send(entry.get("content", "text"))
    if permission == "no":
        return {
            "action": "withhold",
            "reason": f"unprompted {entry.get('content')} is switched off for this companion",
        }
    if permission == "ask" and entry.get("content") != "text":
        return {
            "action": "withhold",
            "reason": f"{entry.get('content')} is set to ask: offer it in words, do not attach it unasked",
        }
    asleep = outreach.in_quiet_hours(c, now)
    awake = asleep and recently_active(c, now)
    if asleep and entry.get("priority") != "high" and not awake:
        return {"action": "hold", "reason": f"quiet hours until {c.quiet_end}"}
    # The quiet-hours bypass is exactly that. The daily cap still applies, because
    # a cap the user set is not a bedtime and being awake does not raise it.
    urgent = entry.get("priority") == "high" or awake
    decision = outreach.decide(c, now, urgent=urgent)
    if not decision["allowed"]:
        # A cap reached today is a hold, not a drop: it may still be in time
        # tomorrow, and the expiry decides that rather than this code.
        return {"action": "hold", "reason": decision["reason"], "urgent": urgent}
    return {"action": "send", "reason": decision["reason"], "urgent": urgent}


def review_hold(c, entry):
    """Why an image may not go, or '' when it may. Never claims a slot."""
    if not pathlib.Path(entry["media_path"]).exists():
        return ""  # deliver() reports this
    from companion_media_review import ensure_delivery

    try:
        ensure_delivery(c, entry["media_path"], entry.get("body", ""))
    except Exception as exc:
        return "image held by pre-delivery review: " + str(exc)[:200]
    return ""


def deliver(c, entry):
    """Hand it to Hermes exactly once. Returns the outcome record (see classify()).
    A local check that stops it BEFORE Hermes is called is a definite `failed`."""
    body = entry["body"]
    if entry.get("media_path"):
        if not pathlib.Path(entry["media_path"]).exists():
            return {
                "outcome": "failed",
                "detail": "the file to send is gone",
                "not_dispatched": True,
            }
        if entry.get("content") == "image":
            from companion_media_review import ensure_delivery

            try:
                ensure_delivery(c, entry["media_path"], body)
            except Exception:
                return {
                    "outcome": "failed",
                    "not_dispatched": True,
                    "detail": "image held: pre-delivery review did not pass; inspect it in Photos",
                }
        body = f"MEDIA:{entry['media_path']}\n{body}"
    return hermes_send_result(c, body, entry.get("target") or "telegram")


def _env(c):
    env = {**os.environ, "HERMES_HOME": str(c.home), "PYTHONUTF8": "1"}
    if c.profile:
        prefixes = (
            "TELEGRAM_",
            "DISCORD_",
            "SLACK_",
            "SIGNAL_",
            "WHATSAPP_",
            "MATRIX_",
            "WEIXIN_",
            "FEISHU_",
            "DINGTALK_",
            "NTFY_",
            "SIMPLEX_",
            "QQBOT_",
            "YUANBAO_",
        )
        env = {k: v for k, v in env.items() if not k.startswith(prefixes)}
    return env


def classify(target, returncode=None, stdout="", stderr="", error=None):
    """Delivery outcome recording. Only a confirmed success is `sent`;
    `skipped` is `withheld`; an error on the verified pre-platform list is `failed`; every
    other error, a timeout, an OS error, a kill, non-JSON output or a non-zero exit is
    `unknown`. Nothing here ever leads to a resend."""
    record = {
        "platform": str(target).split(":", 1)[0],
        "requested_target": target,
        "recipient_resolved": None,
        "message_id": None,
        "id_scope": "last_chunk",
        "mirrored": None,
    }
    if error is not None:
        code = "timeout" if isinstance(error, subprocess.TimeoutExpired) else "os_error"
        return {
            "outcome": "unknown",
            "error_code": code,
            "delivery": record,
            "detail": f"delivery not confirmed ({code}: {str(error)[:160]}); the slot is kept and it is not retried",
        }
    try:
        payload = json.loads(stdout or "")
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        for key in ("chat_id", "recipient"):
            if isinstance(payload.get(key), (str, int)) and not isinstance(
                payload.get(key), bool
            ):
                record["recipient_resolved"] = payload[key]
                break
        if isinstance(payload.get("message_id"), (str, int)) and not isinstance(
            payload.get("message_id"), bool
        ):
            record["message_id"] = payload["message_id"]
        if isinstance(payload.get("mirrored"), bool):
            record["mirrored"] = payload["mirrored"]
    if not isinstance(payload, dict):
        return {
            "outcome": "unknown",
            "error_code": "no_json",
            "delivery": record,
            "detail": f"delivery not confirmed (exit {returncode}, no result from Hermes: "
            f'{(stderr or "").strip()[-160:]}); the slot is kept and it is not retried',
        }
    error_text = payload.get("error")
    if payload.get("success") is True and payload.get("skipped") and not error_text:
        return {
            "outcome": "withheld",
            "delivery": record,
            "detail": f"Hermes skipped it: {str(payload.get('reason') or payload.get('skipped'))[:200]}",
        }
    if returncode == 0 and payload.get("success") is True and not error_text:
        record["id_missing"] = record["message_id"] is None
        return {"outcome": "sent", "delivery": record, "detail": "sent"}
    if error_text and str(error_text) in PRE_PLATFORM_ERRORS:
        return {
            "outcome": "failed",
            "error_code": "pre_platform",
            "delivery": record,
            "not_dispatched": True,
            "detail": f"delivery failed before any platform call ({str(error_text)[:200]})",
        }
    # Keep Hermes's own reason: "failed or unconfirmed" alone sent the last
    # investigation into the logs to find a target Hermes had named plainly.
    why = error_text or (stderr or "").strip()[-200:] or f"exit {returncode}"
    return {
        "outcome": "unknown",
        "error_code": "hermes_error" if error_text else "unconfirmed",
        "delivery": record,
        "detail": f"delivery failed or unconfirmed ({str(why)[:200]}); the slot is kept and it is not retried",
    }


def _invoke(c, body, target):
    """The one call that can reach a platform. Tests replace this with a delivery double."""
    return subprocess.run(
        hermes_command("send", "--to", target, "--json"),
        input=body,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        env=_env(c),
    )


def hermes_send_result(c, body, target="telegram"):
    """One native Hermes send with this profile's own credentials, classified."""
    try:
        proc = _invoke(c, body, target)
    except (OSError, subprocess.SubprocessError) as exc:
        return classify(target, error=exc)
    return classify(target, proc.returncode, proc.stdout, proc.stderr)


def hermes_send(c, body, target="telegram"):
    """(ok, detail): the older shape, kept for callers outside the outbox (the watch notifier)."""
    result = hermes_send_result(c, body, target)
    return result["outcome"] == "sent", result["detail"]


def _outcome(result):
    """A deliver() result as an outcome record. A (ok, detail) pair from an older caller or
    a test double is read conservatively: not confirmed means `unknown`, never `failed`.
    """
    if isinstance(result, dict) and result.get("outcome") in (
        "sent",
        "failed",
        "unknown",
        "withheld",
    ):
        return result
    if isinstance(result, tuple) and len(result) == 2:
        ok, detail = result
        if ok:
            return {
                "outcome": "sent",
                "detail": str(detail),
                "delivery": {
                    "message_id": None,
                    "id_missing": True,
                    "id_scope": "last_chunk",
                    "recipient_resolved": None,
                    "mirrored": None,
                },
            }
        return {
            "outcome": "unknown",
            "detail": str(detail),
            "error_code": "unconfirmed",
        }
    return {
        "outcome": "unknown",
        "detail": "the delivery result could not be read",
        "error_code": "unreadable_result",
    }


def recover(c, run_id, now):
    """Resolve attempts a dispatcher that no longer holds the run lock left mid-way (table
    7.3). Only called while THIS run holds the run lock, which is what proves the earlier
    run is gone; a timeout is never the evidence. Returns [(id, resolution)]."""
    out = []
    for entry in outbox.fold(c):
        status, attempt = entry["status"], entry.get("attempt")
        if status not in outbox.PHASES or not attempt or entry.get("run_id") == run_id:
            continue
        ident = entry["id"]

        def move(to, **extra):
            r = outbox.transition(c, ident, to, attempt, run_id, status, now, **extra)
            if r.get("written", True) is not False:
                out.append((ident, to if to != "failed" else "failed_not_dispatched"))

        if status == "dispatching":
            move(
                "queued",
                release_reason="abandoned",
                detail="a dispatcher stopped before reserving a slot; nothing was charged or sent",
            )
        elif status == "reserving_slot":
            try:
                n = outreach.charges_for(c, attempt)
            except (OSError, ValueError) as exc:
                move(
                    "reservation_unresolved",
                    detail="definitely not dispatched; whether a daily slot was used is unknown "
                    f"(the outreach ledger could not be read: {str(exc)[:120]}). Not requeued, not refunded.",
                )
                continue
            if n:
                move(
                    "failed",
                    not_dispatched=True,
                    detail="a dispatcher stopped after charging a slot and before sending; not sent, the slot stays used",
                )
            else:
                move(
                    "queued",
                    release_reason="abandoned",
                    detail="a dispatcher stopped before charging a slot; nothing was charged or sent",
                )
        elif status == "slot_reserved":
            move(
                "failed",
                not_dispatched=True,
                detail="a dispatcher stopped after reserving a slot and before sending; not sent, the slot stays used",
            )
        elif status == "sending":
            move(
                "unknown",
                error_code="dispatcher_stopped",
                detail="the dispatcher stopped mid-send; delivery is not known. It is never sent again.",
            )
    return out


def run(c, now=None, send=True):
    """One dispatcher run: at most one message leaves. Holds the run lock throughout."""
    now = (now or dt.datetime.now(_tz(c))).astimezone(_tz(c))
    with contextlib.ExitStack() as stack:
        try:
            stack.enter_context(file_lock(run_lock_path(c), timeout=0))
        except TimeoutError:
            return {
                "at": now.isoformat(timespec="minutes"),
                "handled": [],
                "busy": True,
                "reason": "another dispatcher is running",
                "still_waiting": len(outbox.waiting(c, now)),
            }
        return _run_locked(c, now, send)


def _run_locked(c, now, send):
    run_id = secrets.token_hex(8)
    recovered = recover(c, run_id, now)
    handled = []

    def step(ident, status, attempt, expect, **extra):
        r = outbox.transition(c, ident, status, attempt, run_id, expect, now, **extra)
        return r.get("written", True) is not False, r.get("refused", "")

    for n, entry in enumerate(outbox.waiting(c, now)):
        ident, attempt = entry["id"], f"{run_id}:{n}"
        call = verdict(c, entry, now)
        if call["action"] == "hold":
            handled.append({"id": ident, **call})
            continue
        if call["action"] in ("expire", "withhold"):
            ok, why = step(
                ident,
                "expired" if call["action"] == "expire" else "withheld",
                attempt,
                "queued",
                detail=call["reason"],
            )
            handled.append(
                {"id": ident, **call}
                if ok
                else {"id": ident, "action": "skipped", "reason": why}
            )
            continue
        # A dry run decides and stops: claiming first used up a real daily slot for a
        # message it never sent.
        if not send:
            handled.append(
                {"id": ident, "action": "would-send", "reason": call["reason"]}
            )
            break
        ok, why = step(ident, "dispatching", attempt, "queued")  # 7.2 step 1: the claim
        if not ok:
            handled.append(
                {"id": ident, "action": "skipped", "reason": f"not claimed: {why}"}
            )
            continue
        _hook("after_claim")
        # A picture is reviewed BEFORE a slot is claimed. A review that holds it is a
        # verdict about the picture, not a delivery that failed, so it withholds the
        # message and leaves today's allowance alone.
        if entry.get("content") == "image" and entry.get("media_path"):
            held = review_hold(c, entry)
            if held:
                step(ident, "withheld", attempt, "dispatching", detail=held)
                handled.append({"id": ident, "action": "withhold", "reason": held})
                continue
        ok, why = step(
            ident, "reserving_slot", attempt, "dispatching"
        )  # 3a: intent BEFORE any charge
        if not ok:
            handled.append({"id": ident, "action": "stopped", "reason": why})
            break
        _hook("after_reservation_intent")
        # 3b: one charge per run, carrying the attempt, before delivery, so a crash
        # mid-send cannot hand back a free slot and a crash after it is found by lookup.
        slot = outreach.claim(
            c,
            entry.get("reason") or "outbox",
            now=now,
            urgent=call.get("urgent", False),
            attempt=attempt,
        )
        if not slot["allowed"]:
            step(
                ident,
                "queued",
                attempt,
                "reserving_slot",
                detail=slot["reason"],
                release_reason=(
                    "ledger_unreadable" if slot.get("storage_error") else "cap"
                ),
            )
            handled.append({"id": ident, "action": "hold", "reason": slot["reason"]})
            break
        _hook("after_charge")
        ok, why = step(ident, "slot_reserved", attempt, "reserving_slot")
        if not ok:
            handled.append({"id": ident, "action": "stopped", "reason": why})
            break
        _hook("after_slot_marker")
        ok, why = step(
            ident, "sending", attempt, "slot_reserved"
        )  # 4: marker right before the send
        if not ok:
            handled.append({"id": ident, "action": "stopped", "reason": why})
            break
        _hook("after_sending_marker")
        try:
            result = _outcome(deliver(c, entry))
        except Exception as exc:
            result = {
                "outcome": "unknown",
                "error_code": "dispatcher_error",
                "detail": f"the delivery step raised {type(exc).__name__}; delivery is not known and it is not retried",
            }
        _hook("after_delivery")
        extra = {
            k: result[k]
            for k in ("delivery", "not_dispatched", "error_code")
            if k in result
        }
        step(
            ident,
            result["outcome"],
            attempt,
            "sending",
            detail=result.get("detail", ""),
            **extra,
        )  # 5
        handled.append(
            {
                "id": ident,
                "action": result["outcome"],
                "reason": result.get("detail", ""),
            }
        )
        break
    return {
        "at": now.isoformat(timespec="minutes"),
        "run_id": run_id,
        "recovered": recovered,
        "handled": handled,
        "still_waiting": len(outbox.waiting(c, now)),
    }


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--home", type=pathlib.Path)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="decide, expire and withhold, but send nothing",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="print the whole decision, not just problems",
    )
    a = p.parse_args()
    c = cc.load(a.home)
    result = run(c, send=not a.dry_run)
    if a.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result.get("busy"):
        pass  # another run is going: a normal, silent tick
    else:
        # As a no-agent job, stdout is delivered. Stay silent unless something
        # went wrong: a dispatcher narrating every quiet tick is the noise this
        # whole design exists to stop.
        bad = [
            h
            for h in result["handled"]
            if h["action"] in ("failed", "unknown", "expire")
        ]
        for item in bad:
            print(f"{item['action']}: {item['reason']}")
        for ident, resolution in result.get("recovered", []):
            if resolution in (
                "unknown",
                "reservation_unresolved",
                "failed_not_dispatched",
            ):
                print(
                    f"{resolution}: {ident} (left by a dispatcher that stopped mid-way)"
                )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except (ValueError, OSError) as e:
        print(f"{e}", file=sys.stderr)
        sys.exit(1)
