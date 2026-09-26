"""Read-only owner transcripts for quote-backed memory and cross-channel context.

Only explicitly trusted local sessions and the owner's Telegram direct messages
may become evidence. Roles, platform message IDs, profile boundaries, and Hermes
compression markers are checked in code; message wording never establishes who
said it. This reader creates no cache, journal, lock, or additional message store.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
import sys
import time

LOCAL_SOURCES = ('cli', 'desktop', 'tui')
BINDING_FILE = '.tamanitomo-chat-owner.json'


class SourceUnavailable(ValueError):
    """The transcript is unreadable; callers must not advance memory watermarks."""


@dataclass(frozen=True)
class OwnerBinding:
    workspace: bool = True
    terminal: bool = True
    telegram: tuple[str, ...] = ()
    origin: str = 'none'


@dataclass(frozen=True)
class Record:
    source_message: str
    source_session: str
    source_kind: str
    speaker: str
    occurred_at: float
    content: str


def owner_binding(c):
    path = Path(c.home) / BINDING_FILE
    if path.is_file() and not path.is_symlink():
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            ids = tuple(sorted({str(value).strip() for value in data.get('telegram', [])
                                if str(value).strip().lstrip('-').isdigit()}))
            return OwnerBinding(bool(data.get('workspace', True)),
                                bool(data.get('terminal', True)), ids, 'owner-file')
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            raise SourceUnavailable('The chat owner binding file cannot be read.') from exc
    from companion_gateway import _env_values
    users = (_env_values(c.home).get('TELEGRAM_ALLOWED_USERS')
             or _env_values(c.hermes_root).get('TELEGRAM_ALLOWED_USERS') or '')
    ids = [value.strip() for value in str(users).replace('"', '').replace("'", '').strip('[]').split(',')
           if value.strip()]
    if len(ids) == 1 and ids[0].lstrip('-').isdigit():
        return OwnerBinding(telegram=(ids[0],), origin='telegram-allowlist-single')
    return OwnerBinding(origin='none' if not ids else 'telegram-allowlist-ambiguous')


def session_kind(row, binding, workspace):
    source = str(row.get('source') or '').lower()
    chat_id = str(row.get('chat_id') or '')
    if source in LOCAL_SOURCES:
        if row.get('session_id') in workspace:
            return ('workspace', '') if binding.workspace else (None, 'workspace_not_trusted')
        if chat_id:
            return None, 'local_source_with_gateway_chat'
        return ('terminal', '') if binding.terminal else (None, 'terminal_not_trusted')
    if source == 'telegram':
        user = str(row.get('user_id') or '')
        chat_type = str(row.get('chat_type') or '').lower()
        if not (chat_type == 'dm' or (not chat_type and chat_id and chat_id == user)):
            return None, 'group_or_channel'
        if user not in binding.telegram:
            return None, 'unknown_participant'
        return 'telegram', ''
    return None, 'unverified_source:' + (source or 'none')


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
            message_columns = {row[1] for row in connection.execute('PRAGMA table_info(messages)')}
            if not {'id', 'session_id', 'role', 'content', 'timestamp'} <= message_columns:
                raise SourceUnavailable('The Hermes transcript schema is unsupported.')
            return callback(Transcript(connection, session_columns, message_columns, scope,
                                       params, binding, runtime.read_workspace_sessions(c)))
    except (ValueError, sqlite3.Error, OSError) as exc:
        raise SourceUnavailable('Hermes conversation history is unavailable: ' + str(exc)[:200]) from exc


class Transcript:
    def __init__(self, connection, session_columns, message_columns, scope, params, binding, workspace):
        self.con = connection
        self.session_columns = session_columns
        self.message_columns = message_columns
        self.scope = scope.replace('profile_name', 's.profile_name')
        self.params = params
        self.binding = binding
        self.workspace = workspace
        self.excluded = {}
        self._sessions = {}
        self._lineage = {'parent_session_id', 'end_reason', 'started_at'} <= session_columns
        self.limits = ['A compression handoff without its original time cannot be distinguished from a new message.']
        if not self._lineage:
            self.limits.append('This Hermes store does not record compression lineage.')
        deadline = time.monotonic() + 10
        self.con.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)

    def session(self, ident):
        ident = str(ident)
        if ident not in self._sessions:
            fields = ['id AS session_id', 'source']
            for name, alias in [('user_id', 'user_id'), ('chat_id', 'chat_id'), ('chat_type', 'chat_type'),
                                ('parent_session_id', 'parent'), ('end_reason', 'end_reason'),
                                ('started_at', 'started_at')]:
                fields.append(f"{name if name in self.session_columns else 'NULL'} AS {alias}")
            row = self.con.execute(f"SELECT {','.join(fields)} FROM sessions s WHERE id=? AND {self.scope}",
                                   (ident, *self.params)).fetchone()
            self._sessions[ident] = dict(row) if row else None
        return self._sessions[ident]

    def owner_session(self, ident):
        row = self.session(ident)
        return session_kind(row, self.binding, self.workspace)[0] if row else None

    def lineage(self, ident):
        result, current = [], str(ident)
        while current and current not in result and len(result) < 20:
            result.append(current)
            row = self.session(current)
            current = str(row['parent']) if row and row.get('parent') else None
            if current:
                parent = self.session(current)
                if not parent or parent.get('end_reason') != 'compression':
                    break
        return result

    def _select(self):
        fields = ['m.id', 'm.session_id', 'm.role', 'm.content', 'm.timestamp']
        for name in ('platform_message_id', 'display_kind', '_compressed_summary', 'active', 'compacted'):
            fields.append(f"{('m.' + name) if name in self.message_columns else 'NULL'} AS {name}")
        return (f"SELECT {','.join(fields)} FROM messages m JOIN sessions s ON s.id=m.session_id "
                f"WHERE {self.scope}")

    def _record(self, row):
        session = self.session(row['session_id'])
        if session is None:
            return None
        kind, reason = session_kind(session, self.binding, self.workspace)
        if kind:
            if row['role'] not in ('user', 'assistant'):
                reason = 'non_public_role'
            elif row['role'] == 'user' and kind == 'telegram' and not row['platform_message_id']:
                reason = 'unverified_sender'
            elif (row['display_kind'] or row['_compressed_summary']
                  or (row['active'] not in (None, 1) and row['compacted'] != 1)
                  or not str(row['content'] or '').strip()):
                reason = 'not_public'
            elif self._lineage and session.get('parent') and session.get('started_at') is not None:
                parent = self.session(session['parent'])
                if (parent and parent.get('end_reason') == 'compression'
                        and row['timestamp'] <= float(session['started_at'])):
                    reason = 'compression_carryover'
        if reason:
            self.excluded[reason] = self.excluded.get(reason, 0) + 1
            return None
        content = row['content']
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        return Record(str(row['id']), str(row['session_id']), kind,
                      'owner' if row['role'] == 'user' else 'companion', float(row['timestamp']), content)

    def forward(self, after_stamp, after_id, end_stamp, end_inclusive=True):
        stamp, ident = float(after_stamp), int(after_id)
        operator = '<=' if end_inclusive else '<'
        while True:
            rows = self.con.execute(
                self._select() + f' AND (m.timestamp>? OR (m.timestamp=? AND m.id>?)) AND m.timestamp{operator}? '
                'ORDER BY m.timestamp,m.id LIMIT 200',
                (*self.params, stamp, stamp, ident, float(end_stamp))).fetchall()
            for row in rows:
                record = self._record(row)
                if record is not None:
                    yield record
            if len(rows) < 200:
                return
            stamp, ident = float(rows[-1]['timestamp']), int(rows[-1]['id'])

    def page(self, limit, before=None):
        """A page of visible owner messages, newest first, with an older cursor."""
        cursor = before
        records = []
        while len(records) <= limit:
            condition = ' AND (coalesce(m.timestamp,0),m.id)<(?,?)' if cursor else ''
            values = (*self.params, *cursor) if cursor else self.params
            rows = self.con.execute(self._select() + condition
                                    + ' ORDER BY coalesce(m.timestamp,0) DESC,m.id DESC LIMIT 200', values).fetchall()
            for row in rows:
                record = self._record(row)
                if record is not None:
                    records.append(record)
                    if len(records) > limit:
                        return records[:limit], True
            if len(rows) < 200:
                return records, False
            cursor = (rows[-1]['timestamp'] or 0, rows[-1]['id'])
        return records, False

    def recent(self, since_stamp, skip_sessions, limit):
        skip = {str(session) for session in skip_sessions}
        rows = self.con.execute(self._select() + ' AND m.timestamp>=? ORDER BY m.timestamp DESC,m.id DESC LIMIT 400',
                                (*self.params, float(since_stamp))).fetchall()
        records = []
        for row in rows:
            if str(row['session_id']) in skip:
                continue
            record = self._record(row)
            if record is not None:
                records.append(record)
                if len(records) >= limit:
                    return records, True
        return records, len(rows) < 400
