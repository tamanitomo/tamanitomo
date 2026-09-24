"""Read-only sources for the owner's private conversation (Phase 1A).

A source adapter turns rows some other program owns into SourceRecords. It
never writes to that program's store. What belongs in the owner's private
conversation is decided here, from structural provenance only:

  workspace  a cli/desktop/tui session this app started (its session registry),
             when the binding trusts the workspace
  terminal   a local cli/desktop/tui session with no gateway chat attached and
             not started by this app, when the binding trusts the terminal
  telegram   a direct-message session whose Telegram user ID is bound to the
             owner; a user turn counts as the owner only when Hermes recorded
             the platform message id it was received as. That id is part of
             the row's identity: another known id in the same chat is another
             message (see platform_conflict)

Everything else -- another participant, a group or channel, a platform this
phase has not verified, a scheduled run, a sub-agent, an internal notification
-- is excluded and counted by reason. Nothing is matched by display name or
message text. See docs/CHAT_CONTRACT.md for the capability table.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import sqlite3
from pathlib import Path

from . import runtime as hr

# Local Hermes front ends. A session from one of these was typed on this host.
LOCAL_SOURCES = ('cli', 'desktop', 'tui')
# Adapters whose identity and DM semantics this phase has checked against the
# installed Hermes schema. Anything else is excluded as unverified.
VERIFIED_CHANNELS = ('telegram',)
# Gateway sources whose inbound user turns Hermes records with the platform's
# own message id (gateway/run_turn.py _hmwa_user_transcript_entry). For a user
# row in such a session WITHOUT one, the sender is not established: Hermes's
# delivery mirror (gateway/mirror.py) writes cron briefs as role="user" rows with
# no id, and genuine owner messages from releases before the column existed have
# none either. Missing metadata does not prove the owner never sent it; it only
# means this adapter cannot say so, so the row stays out of the private feed.
PLATFORM_ID_SOURCES = ('telegram',)


class SourceUnavailable(Exception):
    """The source cannot be read right now or has a schema this code does not
    understand. Recoverable: nothing was changed, try again later."""


@dataclasses.dataclass(frozen=True)
class OwnerBinding:
    """Who the owner is on each channel, by stable adapter identifiers.

    `telegram` holds Telegram user IDs. `origin` says where the binding came
    from, because a binding read from an allow-list is weaker evidence than
    one the owner wrote down."""
    workspace: bool = True
    terminal: bool = True
    telegram: tuple[str, ...] = ()
    origin: str = 'none'

    def digest(self):
        body = json.dumps({'workspace': self.workspace, 'terminal': self.terminal,
                           'telegram': sorted(self.telegram)}, sort_keys=True)
        return hashlib.sha256(body.encode()).hexdigest()[:16]


BINDING_FILE = '.tamanitomo-chat-owner.json'


def owner_binding(c):
    """The owner's channel identities for this profile.

    1. `<profile home>/.tamanitomo-chat-owner.json`, written by the owner:
       {"workspace": true, "terminal": true, "telegram": ["123456"]}
    2. Otherwise TELEGRAM_ALLOWED_USERS when it names exactly ONE user: the
       only account the owner authorised to talk to this companion.
    3. Otherwise no Telegram identity: several allowed users do not say which
       of them is the owner, and a guess would put someone else's messages
       in a private feed."""
    path = Path(c.home) / BINDING_FILE
    if path.is_file() and not path.is_symlink():
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            ids = tuple(sorted({str(v).strip() for v in data.get('telegram', []) if str(v).strip().lstrip('-').isdigit()}))
            return OwnerBinding(bool(data.get('workspace', True)), bool(data.get('terminal', True)), ids, 'owner-file')
        except (OSError, ValueError, TypeError, AttributeError):
            raise SourceUnavailable('The chat owner binding file cannot be read; fix or remove it.')
    try:
        from companion_gateway import _env_values
        users = _env_values(c.home).get('TELEGRAM_ALLOWED_USERS') or _env_values(c.hermes_root).get('TELEGRAM_ALLOWED_USERS') or ''
    except Exception:
        users = ''
    ids = [u.strip() for u in str(users).replace('"', '').replace("'", '').strip('[]').split(',') if u.strip()]
    if len(ids) == 1 and ids[0].lstrip('-').isdigit():
        return OwnerBinding(telegram=(ids[0],), origin='telegram-allowlist-single')
    return OwnerBinding(origin='none' if not ids else 'telegram-allowlist-ambiguous')


@dataclasses.dataclass
class SourceRecord:
    source_key: str            # stable within one source generation
    source_kind: str           # workspace / terminal / telegram
    source_account: str | None
    source_channel: str | None
    source_session: str
    source_message: str
    platform_message_id: str | None
    speaker: str               # owner / companion / unverified
    occurred_at: float | None
    content: str
    visible: bool              # False: the source says it is no longer public
    note: str = ''
    # A source's own ordering of versions of this message (e.g. an edit time),
    # when it has one. Hermes has none: its current row is authoritative.
    source_revision: float | None = None
    # Identity of the source row (see fingerprint()); None for push records.
    fingerprint: str | None = None


# ---------------------------------------------------------------- Hermes store
class HermesSource:
    """Hermes state.db, read-only (`mode=ro`, `query_only`), profile-scoped by
    runtime.session_db. Message identity is messages.id, which Hermes declares
    INTEGER PRIMARY KEY AUTOINCREMENT: never reused within one database file.
    A replaced or restored file is a different generation (see generation())."""

    name = 'hermes'
    REQUIRED_MESSAGE_COLUMNS = {'id', 'session_id', 'role', 'content', 'timestamp'}

    def __init__(self, c, binding, workspace_sessions=None):
        self.c = c
        self.binding = binding
        self.workspace = set(workspace_sessions if workspace_sessions is not None else hr.read_workspace_sessions(c))

    # -- opening -------------------------------------------------------------
    def _open(self):
        try:
            return hr.session_db(self.c)
        except ValueError as exc:
            raise SourceUnavailable(str(exc)) from exc

    def read(self, fn):
        """Run fn(reader) inside one read-only connection. Every failure to
        read the source is SourceUnavailable; nothing is ever written."""
        try:
            with self._open() as state:
                if state is None:
                    return fn(None)
                con, columns, scope, params = state
                cols = {r[1] for r in con.execute('PRAGMA table_info(messages)')}
                if not self.REQUIRED_MESSAGE_COLUMNS <= cols:
                    raise SourceUnavailable('This Hermes messages table has no stable message id; history is unavailable.')
                return fn(_HermesReader(self, con, columns, cols, scope, params))
        except SourceUnavailable:
            raise
        except (ValueError, sqlite3.Error, OSError) as exc:
            raise SourceUnavailable('Hermes session history is temporarily unavailable: ' + str(exc)[:200]) from exc


class _HermesReader:
    def __init__(self, source, con, session_cols, message_cols, scope, params):
        self.source, self.con = source, con
        self.session_cols, self.message_cols = session_cols, message_cols
        self.scope = scope.replace('profile_name', 's.profile_name')
        self.params = params
        # Every query is bounded by the caller; this guards one slow disk.
        import time
        deadline = time.monotonic() + 10
        con.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)

    def generation(self):
        """What identifies this database file's ID space, for detecting a
        replaced or restored store: the AUTOINCREMENT high-water mark and the
        first surviving message. Stored and compared by the projection."""
        seq = None
        try:
            row = self.con.execute("SELECT seq FROM sqlite_sequence WHERE name='messages'").fetchone()
            seq = int(row[0]) if row else None
        except sqlite3.Error:
            pass
        high = self.con.execute('SELECT max(id) FROM messages').fetchone()[0]
        return {'sequence': seq, 'max_id': high}

    def anchor(self, ident):
        """[fingerprint, platform id] of one row, to tell "the same row" from
        "a row that happens to have the same id in a different file"."""
        found = self.identities([ident]).get(ident)
        return list(found) if found else None

    def identities(self, ids):
        """{id: (fingerprint, platform_message_id)} for those of `ids` that
        still exist (<= 500)."""
        ids = [int(i) for i in ids][:500]
        if not ids:
            return {}
        pid = 'platform_message_id' if 'platform_message_id' in self.message_cols else 'NULL'
        rows = self.con.execute(f"SELECT id,session_id,role,timestamp,{pid} FROM messages "
                                f"WHERE id IN ({','.join('?' * len(ids))})", ids)
        return {r[0]: (fingerprint(*r[:4]), str(r[4]) if r[4] else None) for r in rows}

    def _select(self):
        sc, mc = self.session_cols, self.message_cols
        pick = lambda col, table, cols: f'{table}.{col}' if col in cols else 'NULL'
        return (f"SELECT m.id AS id, m.session_id AS session_id, m.role AS role, m.content AS content, m.timestamp AS timestamp, "
                f"{pick('platform_message_id','m',mc)} AS platform_message_id, {pick('display_kind','m',mc)} AS display_kind, "
                f"{pick('_compressed_summary','m',mc)} AS compressed, {pick('active','m',mc)} AS active, "
                f"{pick('compacted','m',mc)} AS compacted, s.source AS source, "
                f"{pick('user_id','s',sc)} AS user_id, {pick('chat_id','s',sc)} AS chat_id, "
                f"{pick('chat_type','s',sc)} AS chat_type "
                f"FROM messages m JOIN sessions s ON s.id=m.session_id WHERE {self.scope}")

    def after(self, last_id, limit):
        """Rows with id > last_id, in id order, at most `limit`. Returns
        (records, excluded_counts, highest_id_read)."""
        rows = self.con.execute(self._select() + ' AND m.id>? ORDER BY m.id LIMIT ?',
                                (*self.params, int(last_id), int(limit))).fetchall()
        return self._classify(rows)

    def between(self, low, high):
        """Current state of every row with low <= id <= high, for reconciling
        edits and deletions."""
        rows = self.con.execute(self._select() + ' AND m.id>=? AND m.id<=? ORDER BY m.id',
                                (*self.params, int(low), int(high))).fetchall()
        return self._classify(rows)

    def _classify(self, rows):
        out, excluded, highest = [], {}, 0
        for row in rows:
            highest = max(highest, row['id'])
            record, reason = classify(dict(row), self.source.binding, self.source.workspace)
            if record is None:
                excluded[reason] = excluded.get(reason, 0) + 1
            else:
                out.append(record)
        return out, excluded, highest


def session_kind(row, binding, workspace):
    """(source_kind, account, channel) for a session in the owner's private
    conversation, or (None, reason, None). Structural fields only."""
    source = str(row.get('source') or '').lower()
    chat_id = str(row.get('chat_id') or '')
    if source in LOCAL_SOURCES:
        if row.get('session_id') in workspace:
            # A session this app started is the workspace's, whatever else is
            # trusted: with workspace trust withdrawn it is excluded, never
            # relabelled as a terminal session.
            return ('workspace', None, None) if binding.workspace else (None, 'workspace_not_trusted', None)
        if chat_id:
            return None, 'local_source_with_gateway_chat', None
        if binding.terminal:
            return 'terminal', None, None
        return None, 'terminal_not_trusted', None
    if source == 'telegram':
        user = str(row.get('user_id') or '')
        chat_type = str(row.get('chat_type') or '').lower()
        # A Telegram private chat's id is the user's id; a group's is not.
        direct = chat_type == 'dm' or (not chat_type and chat_id and chat_id == user)
        if not direct:
            return None, 'group_or_channel', None
        if not user or user not in binding.telegram:
            return None, 'unknown_participant', None
        return 'telegram', user, chat_id or None
    if source in ('cron', 'subagent', 'tool') or source.startswith('local-') or source == 'config-audit':
        return None, 'internal_session', None
    return None, 'unverified_source:' + (source or 'none'), None


def classify(row, binding, workspace):
    """A SourceRecord for one row, or (None, reason). Visibility follows
    Hermes's own structural markers: role, display_kind, the compression
    summary flag and active/compacted. A row that fails them after it was
    public becomes `visible=False` (the projection records a deletion)."""
    kind, account, channel = session_kind(row, binding, workspace)
    if kind is None:
        return None, account
    role = row.get('role')
    if role not in ('user', 'assistant'):
        return None, 'non_public_role'
    content = row.get('content')
    if not isinstance(content, str):
        content = '' if content is None else json.dumps(content, ensure_ascii=False)
    public = (not (row.get('display_kind') or '') and not row.get('compressed')
              and (row.get('active') in (None, 1) or row.get('compacted') == 1)
              and bool(content.strip()))
    if role == 'user' and kind in PLATFORM_ID_SOURCES and not row.get('platform_message_id'):
        return None, 'unverified_sender'
    speaker, note = ('owner' if role == 'user' else 'companion'), ''
    stamp = row.get('timestamp')
    return SourceRecord(
        source_key=f"hermes:{row['id']}", source_kind=kind, source_account=account, source_channel=channel,
        source_session=str(row['session_id']), source_message=str(row['id']),
        platform_message_id=str(row['platform_message_id']) if row.get('platform_message_id') else None,
        speaker=speaker, occurred_at=float(stamp) if isinstance(stamp, (int, float)) else None,
        content=content if public else '', visible=public, note=note,
        fingerprint=fingerprint(row['id'], row['session_id'], role, stamp)), None


def fingerprint(ident, session, role, timestamp):
    """What must not change for a source row to still be the same message:
    its id, session, role and authored time. Content may change (an edit)."""
    return hashlib.sha256(json.dumps([ident, session, role, timestamp]).encode()).hexdigest()[:24]


def platform_conflict(stored, current):
    """True when two KNOWN platform message ids differ. Telegram numbers
    messages within one chat, so for the same source row (same session, hence
    the same account/chat) two different ids are two different messages. A
    missing id on either side is not evidence either way: missing -> known is
    enrichment, known -> missing keeps the known id (see the projection)."""
    return bool(stored) and bool(current) and str(stored) != str(current)


def capabilities():
    """What each source can and cannot establish in this phase. Shown by
    /api/chat/sources and docs/CHAT_CONTRACT.md."""
    common = {'schema': 'Hermes state.db sessions/messages (hermes_state_common.SCHEMA_SQL, schema_version 30)',
              'message_id': 'messages.id (AUTOINCREMENT) within one store generation',
              'edits': 'no revision column; a changed content hash is projected as an edit',
              'deletions': 'row removed, deactivated or hidden -> projected deletion',
              'reply_to': 'not stored by Hermes', 'deltas': 'completed messages only (stream deltas are not persisted)'}
    return {
        'workspace': {**common, 'status': 'supported', 'identity': 'session registry written by this app when it sends',
                      'tested': 'fixture'},
        'terminal': {**common, 'status': 'supported', 'identity': 'local cli/desktop/tui session with no gateway chat',
                     'tested': 'fixture'},
        'telegram': {**common, 'status': 'supported', 'identity': 'sessions.user_id bound to the owner; DM by chat_type=dm or chat_id=user_id',
                     'platform_message_id': 'required on user turns: without one the sender is not established (a '
                                            'cron-brief delivery mirror, or a genuine message older than the column), '
                                            'so the row is excluded as unverified_sender. Part of identity: a different '
                                            'known id in the same chat is a different message, never an edit',
                     'edits': 'Hermes does not record Telegram edits of past messages', 'tested': 'fixture'},
        'discord': {'status': 'unsupported', 'reason': 'identity/DM semantics not verified in this phase'},
        'signal': {'status': 'unsupported', 'reason': 'identity/DM semantics not verified in this phase'},
        'other gateways': {'status': 'unsupported', 'reason': 'excluded as unverified_source:<name>'},
        'proactive delivery provenance': {
            'status': 'unsupported',
            'reason': ('No source record proves that a proactive message was delivered: the outbox marks an entry '
                       'sent without the platform message id, and the Hermes delivery mirror row carries no outbox '
                       'id, no platform id and no marker distinguishing it from a model reply. Companion rows in a '
                       'trusted session are shown as that session recorded them, with delivery unverified; no row is '
                       'presented as a verified delivered outreach, and nothing is joined by text.'),
            'tested': 'fixture'},
    }
