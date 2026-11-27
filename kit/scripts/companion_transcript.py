"""Read-only owner transcripts for quote-backed memory and cross-channel context.

Only explicitly trusted local sessions, the owner's Telegram direct messages and
the Hermes API conversations the owner names (companion.json
`owner_api_conversations`) may become evidence. Roles, platform message IDs,
profile boundaries, and Hermes compression markers are checked in code; message
wording never establishes who said it. This reader creates no cache, journal,
lock, or additional message store.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

LOCAL_SOURCES = ("cli", "desktop", "tui", "oneshot")
# Hermes 0.3x files `hermes chat --oneshot` (the workspace's /api/chat and other local
# clients) as source "oneshot", with chat_id set to the session's own id and user_id
# "uid:<local uid>". Those are local conversations with the owner; scheduled runs stay
# "cron" and are never accepted.
# Every source session_kind can accept. Rows from anything else are always dropped,
# so they are not read at all: scheduled runs are nineteen sessions in twenty, and
# paging through them 200 rows at a time to find the conversation made the chat
# feed take most of a second on every load.
OWNER_SOURCES = LOCAL_SOURCES + ("telegram",)
# Hermes's API server. Any client holding the API key can open a conversation there (a
# script, a shared front end), so none is the owner's by default. A conversation the
# owner names in companion.json (`owner_api_conversations`, name -> what to call the
# place: a game add-on, a voice front end) is read like Telegram and the app.
API_SOURCE = "api_server"
# Beside state.db, Hermes's API server keeps the names clients give `conversation` on
# /v1/responses: conversations(name -> latest response id) and responses(response id ->
# a JSON record whose "session_id" is the transcript that turn ran in).
RESPONSE_STORE = "response_store.db"
BINDING_FILE = ".tamanitomo-chat-owner.json"
# Hermes 0.23 freezes a local conversation's launch policy (its model among it) when the
# conversation starts and keeps it in state_meta under this key plus the session id.
# `--resume` runs that policy, so a model plan applied later never reaches it.
LOCAL_POLICY_PREFIX = "gateway.local_policy.v1:"


class SourceUnavailable(ValueError):
    """The transcript is unreadable; callers must not advance memory watermarks."""


@dataclass(frozen=True)
class OwnerBinding:
    workspace: bool = True
    terminal: bool = True
    telegram: tuple[str, ...] = ()
    origin: str = "none"
    # (conversation name, what to call it) for each owner API conversation.
    api: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Record:
    source_message: str
    source_session: str
    source_kind: str
    speaker: str
    occurred_at: float
    content: str
    # What to call the place for an "api" record ("the game"); "" for every other kind.
    channel: str = ""


def api_conversations(c):
    """(name, label) for each Hermes API conversation companion.json names as the
    owner's, sorted; () when none is named."""
    named = getattr(c, "owner_api_conversations", None)
    if not isinstance(named, dict):
        return ()
    return tuple(
        sorted(
            (str(name).strip(), str(label or "").strip() or str(name).strip())
            for name, label in named.items()
            if str(name).strip()
        )
    )


def api_sessions(c, binding):
    """{session id: label} for the transcript each named API conversation is on now.

    Read-only from Hermes's response store (RESPONSE_STORE). A store that is missing,
    locked or shaped differently trusts nothing rather than guessing; the names stay
    trusted only through a session key a client declared (X-Hermes-Session-Key)."""
    if not binding.api:
        return {}
    path = Path(c.home) / RESPONSE_STORE
    if not path.is_file():
        return {}
    found = {}
    try:
        con = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)
    except sqlite3.Error:
        return {}
    try:
        con.execute("PRAGMA query_only=ON")
        for name, label in binding.api:
            join = (
                "FROM conversations c JOIN responses r ON r.response_id=c.response_id "
                "WHERE c.name=?"
            )
            try:
                # Only the session id: the record also holds the whole history.
                row = con.execute(
                    f"SELECT json_extract(r.data,'$.session_id') {join}", (name,)
                ).fetchone()
            except sqlite3.OperationalError:
                # No JSON functions in this SQLite, or a record that is not JSON.
                row = con.execute(f"SELECT r.data {join}", (name,)).fetchone()
                try:
                    row = (json.loads(row[0]).get("session_id"),) if row else None
                except (TypeError, ValueError, AttributeError):
                    row = None
            session = row[0] if row else None
            if isinstance(session, str) and session.strip():
                found[session.strip()] = label
    except sqlite3.Error:
        return {}
    finally:
        con.close()
    return found


def owner_binding(c):
    binding = _channel_binding(c)
    named = api_conversations(c)
    return replace(binding, api=named) if named else binding


def _channel_binding(c):
    path = Path(c.home) / BINDING_FILE
    if path.is_file() and not path.is_symlink():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            ids = tuple(
                sorted(
                    {
                        str(value).strip()
                        for value in data.get("telegram", [])
                        if str(value).strip().lstrip("-").isdigit()
                    }
                )
            )
            return OwnerBinding(
                bool(data.get("workspace", True)),
                bool(data.get("terminal", True)),
                ids,
                "owner-file",
            )
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            raise SourceUnavailable(
                "The chat owner binding file cannot be read."
            ) from exc
    from companion_gateway import _env_values

    users = (
        _env_values(c.home).get("TELEGRAM_ALLOWED_USERS")
        or _env_values(c.hermes_root).get("TELEGRAM_ALLOWED_USERS")
        or ""
    )
    ids = [
        value.strip()
        for value in str(users).replace('"', "").replace("'", "").strip("[]").split(",")
        if value.strip()
    ]
    if len(ids) == 1 and ids[0].lstrip("-").isdigit():
        return OwnerBinding(telegram=(ids[0],), origin="telegram-allowlist-single")
    return OwnerBinding(origin="none" if not ids else "telegram-allowlist-ambiguous")


def session_kind(row, binding, workspace, api=None):
    """(kind, "") for an owner conversation, else (None, why not). `api` maps the
    session ids of the owner's named API conversations to their labels (api_sessions).
    """
    source = str(row.get("source") or "").lower()
    chat_id = str(row.get("chat_id") or "")
    if source == API_SOURCE:
        known = str(row.get("session_id") or "") in (api or {})
        declared = str(row.get("session_key") or "").strip()
        if not (known or (declared and declared in dict(binding.api))):
            return None, "unverified_source:" + source
        if str(row.get("chat_type") or "dm").lower() != "dm":
            return None, "group_or_channel"
        return "api", ""
    if source in LOCAL_SOURCES:
        if row.get("session_id") in workspace:
            return (
                ("workspace", "")
                if binding.workspace
                else (None, "workspace_not_trusted")
            )
        if source == "oneshot":
            # Its own session id as chat_id, and this machine's user: anything else
            # did not come from a conversation on this host.
            user = str(row.get("user_id") or "")
            uid = getattr(os, "getuid", None)  # Windows has no uid to compare
            local_user = not user or uid is None or user == f"uid:{uid()}"
            if (
                chat_id and chat_id != str(row.get("session_id") or "")
            ) or not local_user:
                return None, "oneshot_not_local"
        elif chat_id:
            return None, "local_source_with_gateway_chat"
        return ("terminal", "") if binding.terminal else (None, "terminal_not_trusted")
    if source == "telegram":
        user = str(row.get("user_id") or "")
        chat_type = str(row.get("chat_type") or "").lower()
        if not (chat_type == "dm" or (not chat_type and chat_id and chat_id == user)):
            return None, "group_or_channel"
        if user not in binding.telegram:
            return None, "unknown_participant"
        return "telegram", ""
    return None, "unverified_source:" + (source or "none")


def shared_store(c):
    """A redirected or hard-linked store cannot own unlabelled profile rows."""
    path = Path(c.home) / "state.db"
    try:
        if path.resolve().parent != Path(c.home).resolve() or path.stat().st_nlink > 1:
            return True
        candidates = [Path(c.hermes_root) / "state.db"]
        directory = Path(c.hermes_root) / "profiles"
        if directory.exists():
            candidates.extend(p / "state.db" for p in directory.iterdir() if p.is_dir())
        return any(
            other.exists()
            and other.resolve() != path.resolve()
            and path.samefile(other)
            for other in candidates
        )
    except OSError:
        return True


def owner_evidence(c, callback, binding=None):
    """Read one profile in one read-only connection, without copying its history."""
    root = str(Path(__file__).resolve().parents[2])
    if root not in sys.path:
        sys.path.append(root)
    from kit.app import runtime

    binding = binding or owner_binding(c)
    try:
        with runtime.session_db(c) as state:
            if state is None:
                return callback(None)
            connection, session_columns, scope, params = state
            if shared_store(c):
                if "profile_name" not in session_columns:
                    raise SourceUnavailable(
                        "Cannot safely scope this shared session store"
                    )
                if c.profile:
                    scope = "lower(coalesce(profile_name,''))=?"
                    params = (c.profile.lower(),)
            message_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(messages)")
            }
            if (
                not {"id", "session_id", "role", "content", "timestamp"}
                <= message_columns
            ):
                raise SourceUnavailable("The Hermes transcript schema is unsupported.")
            return callback(
                Transcript(
                    connection,
                    session_columns,
                    message_columns,
                    scope,
                    params,
                    binding,
                    runtime.read_workspace_sessions(c),
                    api_sessions(c, binding),
                )
            )
    except (ValueError, sqlite3.Error, OSError) as exc:
        raise SourceUnavailable(
            "Hermes conversation history is unavailable: " + str(exc)[:200]
        ) from exc


class Transcript:
    def __init__(
        self,
        connection,
        session_columns,
        message_columns,
        scope,
        params,
        binding,
        workspace,
        api=None,
    ):
        self.con = connection
        self.session_columns = session_columns
        self.message_columns = message_columns
        self.scope = scope.replace("profile_name", "s.profile_name")
        self.params = params
        self.binding = binding
        self.workspace = workspace
        self.excluded = {}
        self._sessions = {}
        self._lineage = {
            "parent_session_id",
            "end_reason",
            "started_at",
        } <= session_columns
        self.limits = [
            "A compression handoff without its original time cannot be distinguished from a new message."
        ]
        if not self._lineage:
            self.limits.append("This Hermes store does not record compression lineage.")
        deadline = time.monotonic() + 10
        self.con.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
        # A named API conversation's earlier transcripts, before Hermes compressed it
        # into the current one, are the same conversation.
        self.api = {}
        for session, label in (api or {}).items():
            for ident in self.lineage(session):
                self.api.setdefault(ident, label)

    def session(self, ident):
        ident = str(ident)
        if ident not in self._sessions:
            fields = ["id AS session_id", "source"]
            for name, alias in [
                ("user_id", "user_id"),
                ("chat_id", "chat_id"),
                ("chat_type", "chat_type"),
                ("parent_session_id", "parent"),
                ("end_reason", "end_reason"),
                ("started_at", "started_at"),
                ("session_key", "session_key"),
            ]:
                fields.append(
                    f"{name if name in self.session_columns else 'NULL'} AS {alias}"
                )
            row = self.con.execute(
                f"SELECT {','.join(fields)} FROM sessions s WHERE id=? AND {self.scope}",
                (ident, *self.params),
            ).fetchone()
            self._sessions[ident] = dict(row) if row else None
        return self._sessions[ident]

    def owner_session(self, ident):
        row = self.session(ident)
        return (
            session_kind(row, self.binding, self.workspace, self.api)[0]
            if row
            else None
        )

    def channel_label(self, ident):
        """What to call the place an owner API conversation happens, or ""."""
        ident = str(ident)
        if ident in self.api:
            return self.api[ident]
        row = self.session(ident) or {}
        declared = str(row.get("session_key") or "").strip()
        return dict(self.binding.api).get(declared, "") if declared else ""

    def locked_route(self, ident):
        """The model this profile's local conversation is locked to, or None.

        {"model", "provider"} from the policy Hermes froze when the conversation began
        (`/model` and `/model reset` rewrite it). None when Hermes keeps no such
        record (older versions run the profile's current model) or it is unreadable."""
        if self.session(ident) is None:
            return None
        try:
            row = self.con.execute(
                "SELECT value FROM state_meta WHERE key=?",
                (LOCAL_POLICY_PREFIX + str(ident),),
            ).fetchone()
        except sqlite3.Error:
            return None
        if row is None:
            return None
        try:
            policy = json.loads(row[0])["policy"]
            frozen = json.loads(policy.get("config_json") or "{}").get("model")
        except (KeyError, TypeError, ValueError, AttributeError):
            return None
        if isinstance(frozen, str):
            frozen = {"default": frozen}
        if not isinstance(frozen, dict):
            frozen = {}
        model = policy.get("model") or frozen.get("default")
        provider = frozen.get("provider")
        if not isinstance(model, str) or not model.strip():
            return None
        return {
            "model": model.strip(),
            "provider": provider.strip() if isinstance(provider, str) else None,
        }

    def lineage(self, ident):
        result, current = [], str(ident)
        while current and current not in result and len(result) < 20:
            result.append(current)
            row = self.session(current)
            current = str(row["parent"]) if row and row.get("parent") else None
            if current:
                parent = self.session(current)
                if not parent or parent.get("end_reason") != "compression":
                    break
        return result

    def _select(self):
        fields = ["m.id", "m.session_id", "m.role", "m.content", "m.timestamp"]
        for name in (
            "platform_message_id",
            "display_kind",
            "_compressed_summary",
            "active",
            "compacted",
        ):
            fields.append(
                f"{('m.' + name) if name in self.message_columns else 'NULL'} AS {name}"
            )
        accepted = OWNER_SOURCES + ((API_SOURCE,) if self.binding.api else ())
        sources = ",".join(f"'{name}'" for name in accepted)
        return (
            f"SELECT {','.join(fields)} FROM messages m JOIN sessions s ON s.id=m.session_id "
            f"WHERE {self.scope} AND s.source IN ({sources})"
        )

    def _record(self, row):
        session = self.session(row["session_id"])
        if session is None:
            return None
        kind, reason = session_kind(session, self.binding, self.workspace, self.api)
        if kind:
            if row["role"] not in ("user", "assistant"):
                reason = "non_public_role"
            elif (
                row["role"] == "user"
                and kind == "telegram"
                and not row["platform_message_id"]
            ):
                reason = "unverified_sender"
            elif (
                row["display_kind"]
                or row["_compressed_summary"]
                or (row["active"] not in (None, 1) and row["compacted"] != 1)
                or not str(row["content"] or "").strip()
            ):
                reason = "not_public"
            elif (
                self._lineage
                and session.get("parent")
                and session.get("started_at") is not None
            ):
                parent = self.session(session["parent"])
                if (
                    parent
                    and parent.get("end_reason") == "compression"
                    and row["timestamp"] <= float(session["started_at"])
                ):
                    reason = "compression_carryover"
        if reason:
            self.excluded[reason] = self.excluded.get(reason, 0) + 1
            return None
        content = row["content"]
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        return Record(
            str(row["id"]),
            str(row["session_id"]),
            kind,
            "owner" if row["role"] == "user" else "companion",
            float(row["timestamp"]),
            content,
            self.channel_label(row["session_id"]) if kind == "api" else "",
        )

    def forward(self, after_stamp, after_id, end_stamp, end_inclusive=True):
        stamp, ident = float(after_stamp), int(after_id)
        operator = "<=" if end_inclusive else "<"
        while True:
            rows = self.con.execute(
                self._select()
                + f" AND (m.timestamp>? OR (m.timestamp=? AND m.id>?)) AND m.timestamp{operator}? "
                "ORDER BY m.timestamp,m.id LIMIT 200",
                (*self.params, stamp, stamp, ident, float(end_stamp)),
            ).fetchall()
            for row in rows:
                record = self._record(row)
                if record is not None:
                    yield record
            if len(rows) < 200:
                return
            stamp, ident = float(rows[-1]["timestamp"]), int(rows[-1]["id"])

    def page(self, limit, before=None):
        """A page of visible owner messages, newest first, with an older cursor."""
        cursor = before
        records = []
        while len(records) <= limit:
            condition = " AND (coalesce(m.timestamp,0),m.id)<(?,?)" if cursor else ""
            values = (*self.params, *cursor) if cursor else self.params
            rows = self.con.execute(
                self._select()
                + condition
                + " ORDER BY coalesce(m.timestamp,0) DESC,m.id DESC LIMIT 200",
                values,
            ).fetchall()
            for row in rows:
                record = self._record(row)
                if record is not None:
                    records.append(record)
                    if len(records) > limit:
                        return records[:limit], True
            if len(rows) < 200:
                return records, False
            cursor = (rows[-1]["timestamp"] or 0, rows[-1]["id"])
        return records, False

    def recent(self, since_stamp, skip_sessions, limit):
        skip = {str(session) for session in skip_sessions}
        rows = self.con.execute(
            self._select()
            + " AND m.timestamp>=? ORDER BY m.timestamp DESC,m.id DESC LIMIT 400",
            (*self.params, float(since_stamp)),
        ).fetchall()
        records = []
        for row in rows:
            if str(row["session_id"]) in skip:
                continue
            record = self._record(row)
            if record is not None:
                records.append(record)
                if len(records) >= limit:
                    return records, True
        return records, len(rows) < 400

    def search(self, words, deadline, limit=40, since=None, until=None):
        """Bounded lexical candidates, with the same ownership checks as chat.

        The FTS index narrows candidates only. Session and message identity,
        visibility, compression and source eligibility still pass through _record.
        Newest matches win ties, so a busy archive does not hide later corrections.
        """
        if not words or time.monotonic() >= deadline:
            return [], False
        self.con.execute(
            f"PRAGMA busy_timeout={max(1, int((deadline-time.monotonic())*1000))}"
        )
        self.con.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
        match = " OR ".join('"' + word.replace('"', '""') + '"' for word in words)
        condition = " AND m.role='user' AND m.id IN (SELECT rowid FROM messages_fts WHERE messages_fts MATCH ?)"
        values = [*self.params, match]
        if since is not None:
            condition += " AND m.timestamp>=?"
            values.append(float(since))
        if until is not None:
            condition += " AND m.timestamp<=?"
            values.append(float(until))
        rows = self.con.execute(
            self._select()
            + condition
            + " ORDER BY m.timestamp DESC,m.id DESC LIMIT 200",
            values,
        ).fetchall()
        records = []
        for row in rows:
            if time.monotonic() >= deadline:
                return records, False
            record = self._record(row)
            if record and len(record.content) <= 30000:
                records.append(record)
                if len(records) >= limit:
                    return records, False
        return records, len(rows) < 200
