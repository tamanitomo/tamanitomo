"""The app-owned, rebuildable index of the owner's private conversation.

Sources (chat_sources) are read-only and remain the authority for content.
This file holds only what the app derives from them, so it can always be
deleted and rebuilt:

  messages   one row per source message: a stable opaque message_id, where it
             came from, who said it, when, its revision and status
  changes    what the app learned, in the order it learned it (observed_seq)
  meta       scope, owner-binding digest, source generation, cursor secret

History order is (occurred_at, message_id): when things were said. Change
order is `changes.seq`: when the app noticed. A message imported today with
yesterday's timestamp sorts into yesterday's history AND appears in today's
changes. Cursors are opaque, signed, and scoped to one conversation and one
projection; a rebuild or an expired change window answers `resync_required`,
never "nothing new".

Location: <app state>/chat/<installation>/<profile-home digest>.sqlite3.
Writes are single SQLite transactions (BEGIN IMMEDIATE): an interrupted sync
rolls back to the previous consistent state. See docs/CHAT_CONTRACT.md.
"""
from __future__ import annotations

import base64
import contextlib
import dataclasses
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
import uuid
from pathlib import Path

from .chat_sources import SourceUnavailable

SCHEMA_VERSION = 1
PAGE_DEFAULT, PAGE_MAX = 60, 200
CHANGES_DEFAULT, CHANGES_MAX = 200, 1000
# Change rows kept for incremental readers; older cursors must resync.
RETAIN_CHANGES = 10000
# Rows read from a source per sync call, and reconciled per sync call. Bounds
# the work any one request can cause on a phone-class host.
SYNC_BATCH = 5000
SYNC_MAX_ROWS = 20000
RECONCILE_CHUNK = 10000
RECONCILE_INTERVAL = 30.0


class ResyncRequired(Exception):
    """The cursor cannot be continued: rebuild, source replacement, owner
    binding change, or changes older than the retained window. Load a new
    snapshot. This never means "no new messages"."""
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class CursorError(ValueError):
    """The cursor is malformed, forged, or belongs to another conversation."""


@dataclasses.dataclass(frozen=True)
class ChatScope:
    """Everything a read is authorised for, captured before it starts. A
    request never re-reads the selected profile later."""
    installation: str
    profile: str
    home: str
    binding_digest: str

    @property
    def conversation_id(self):
        return 'conv_' + hashlib.sha256(f'{self.installation}|{self.home}'.encode()).hexdigest()[:20]

    def path(self, state_dir):
        safe = ''.join(ch for ch in self.installation if ch.isalnum() or ch in '-_')[:40] or 'x'
        return Path(state_dir) / 'chat' / safe / (hashlib.sha256(self.home.encode()).hexdigest()[:24] + '.sqlite3')


SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE messages(
  pk INTEGER PRIMARY KEY,
  message_id TEXT NOT NULL UNIQUE,
  source_key TEXT NOT NULL UNIQUE,
  source_kind TEXT NOT NULL,
  source_account TEXT, source_channel TEXT,
  source_session TEXT NOT NULL, source_message TEXT NOT NULL,
  platform_message_id TEXT,
  speaker TEXT NOT NULL,
  occurred_at REAL, first_observed_at REAL NOT NULL, sort_at REAL NOT NULL,
  observed_seq INTEGER NOT NULL,
  revision INTEGER NOT NULL,
  source_revision REAL,
  status TEXT NOT NULL,
  content TEXT NOT NULL, content_hash TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  source_id INTEGER NOT NULL);
CREATE INDEX messages_history ON messages(sort_at DESC, message_id DESC) WHERE status<>'deleted';
CREATE INDEX messages_source_id ON messages(source_id);
CREATE TABLE changes(seq INTEGER PRIMARY KEY AUTOINCREMENT, message_id TEXT NOT NULL, revision INTEGER NOT NULL,
  kind TEXT NOT NULL, at REAL NOT NULL);
"""


def _hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


class Projection:
    def __init__(self, state_dir, scope, clock=time.time):
        self.scope = scope
        self.path = scope.path(state_dir)
        self.clock = clock
        self._counts = {}

    # ---------------------------------------------------------------- storage
    @contextlib.contextmanager
    def _db(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.is_symlink():
            raise SourceUnavailable('The chat projection path is a symlink; refusing to use it.')
        con = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        con.row_factory = sqlite3.Row
        if os.name != 'nt':
            os.chmod(self.path, 0o600)   # a copy of private conversation text
        try:
            con.execute('PRAGMA busy_timeout=15000')
            yield con
        finally:
            con.close()

    def _meta(self, con):
        try:
            return {r['key']: json.loads(r['value']) for r in con.execute('SELECT key,value FROM meta')}
        except sqlite3.OperationalError:
            return {}

    @staticmethod
    def _set(con, **values):
        con.executemany('INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                        [(k, json.dumps(v)) for k, v in values.items()])

    def _create(self, con, reason):
        """A new, empty projection with a new identity. Old cursors cannot
        continue into it."""
        for table in ('meta', 'messages', 'changes'):
            con.execute(f'DROP TABLE IF EXISTS {table}')
        con.execute("DELETE FROM sqlite_sequence WHERE name='changes'") if con.execute(
            "SELECT 1 FROM sqlite_master WHERE name='sqlite_sequence'").fetchone() else None
        # One statement at a time: executescript() would commit the open transaction.
        for statement in filter(str.strip, SCHEMA.split(';')):
            con.execute(statement)
        self._set(con, schema=SCHEMA_VERSION, projection_id='proj_' + uuid.uuid4().hex[:16],
                  generation_id='gen_' + uuid.uuid4().hex[:12], secret=secrets.token_hex(16),
                  scope={'installation': self.scope.installation, 'home': self.scope.home},
                  binding=self.scope.binding_digest, created_at=self.clock(), created_reason=reason,
                  last_id=0, reconcile_pos=0, reconcile_at=0, retained_from=1, source=None,
                  excluded={}, rows_seen=0)

    def _ensure(self, con):
        """Open the projection for this scope, rebuilding it when it was made
        for another schema, scope or owner binding. Runs inside a write
        transaction."""
        meta = self._meta(con)
        if not meta:
            self._create(con, 'new')
        elif meta.get('schema') != SCHEMA_VERSION:
            self._create(con, 'schema_changed')
        elif meta.get('scope') != {'installation': self.scope.installation, 'home': self.scope.home}:
            self._create(con, 'scope_changed')
        elif meta.get('binding') != self.scope.binding_digest:
            # Owner binding revoked or changed: nothing authorised under the old
            # binding may keep being served, so the projection starts over.
            self._create(con, 'owner_binding_changed')
        return self._meta(con)

    # ------------------------------------------------------------------- sync
    def sync(self, source, force_reconcile=False):
        """Bring the projection up to date with the source, within bounds.
        Returns stats. Raises SourceUnavailable without changing anything when
        the source cannot be read."""
        with self._db() as con:
            con.execute('BEGIN IMMEDIATE')
            try:
                meta = self._ensure(con)
                stats = source.read(lambda reader: self._sync(con, meta, reader, force_reconcile))
                con.execute('COMMIT')
                return stats
            except BaseException:
                con.execute('ROLLBACK')
                raise

    def _sync(self, con, meta, reader, force_reconcile):
        now = self.clock()
        stats = {'inserted': 0, 'edited': 0, 'deleted': 0, 'restored': 0, 'read': 0, 'rebuilt': None}
        if reader is None:
            # No store yet. If one existed before, it has gone: a replacement.
            if meta.get('source'):
                self._create(con, 'source_removed');stats['rebuilt'] = 'source_removed'
            return stats
        gen = reader.generation()
        known = meta.get('source')
        if known and self._replaced(known, gen, reader):
            self._create(con, 'source_replaced');stats['rebuilt'] = 'source_replaced'
            meta = self._meta(con)
        last = meta['last_id'];excluded = dict(meta.get('excluded') or {})
        self._counts = {}
        while stats['read'] < SYNC_MAX_ROWS:
            records, skipped, highest = reader.after(last, SYNC_BATCH)
            if not highest:
                break
            for record in records:
                self._apply(con, record, now)
            for reason, n in skipped.items():
                excluded[reason] = excluded.get(reason, 0) + n
            stats['read'] += len(records) + sum(skipped.values())
            last = highest
            if len(records) + sum(skipped.values()) < SYNC_BATCH:
                break
        stats.update(self._counts)
        stats['caught_up'] = stats['read'] < SYNC_MAX_ROWS
        anchor_id = (known or {}).get('anchor_id')
        if not anchor_id or reader.anchor(anchor_id) is None:
            anchor_id = last or None
        source_state = {'sequence': gen['sequence'], 'max_id': gen['max_id'], 'anchor_id': anchor_id,
                        'anchor': reader.anchor(anchor_id) if anchor_id else None}
        self._set(con, last_id=last, excluded=excluded, source=source_state)
        if force_reconcile or now - meta.get('reconcile_at', 0) >= RECONCILE_INTERVAL:
            stats.update({k: stats.get(k, 0) + v for k, v in self._reconcile(con, reader, now, last, force_reconcile).items()})
        self._prune(con)
        stats['excluded'] = excluded
        return stats

    @staticmethod
    def _replaced(known, gen, reader):
        """True when the source's ID space is not the one indexed: an AUTOINCREMENT
        sequence that went backwards (an older copy restored), or the anchor row
        now holding different content (a different file)."""
        if known.get('sequence') is not None and gen['sequence'] is not None and gen['sequence'] < known['sequence']:
            return True
        if known.get('max_id') and gen['max_id'] is None:
            return True
        if known.get('anchor_id') and known.get('anchor'):
            now = reader.anchor(known['anchor_id'])
            if now is not None and now != known['anchor']:
                return True
        return False

    def _message_id(self, con, source_key):
        meta = self._meta(con)
        return 'msg_' + hashlib.sha256(f"{self.scope.conversation_id}|{meta['generation_id']}|{source_key}".encode()).hexdigest()[:24]

    def _change(self, con, message_id, revision, kind, now):
        cur = con.execute('INSERT INTO changes(message_id,revision,kind,at) VALUES(?,?,?,?)', (message_id, revision, kind, now))
        return cur.lastrowid

    def _count(self, kind):
        self._counts[kind] = self._counts.get(kind, 0) + 1

    def _apply(self, con, record, now):
        """Fold one SourceRecord in. Idempotent: the same record twice is one
        message and no change. A record carrying a source_revision older than
        the one applied is ignored, so a replayed old event cannot resurrect
        content that was edited or deleted since."""
        row = con.execute('SELECT * FROM messages WHERE source_key=?', (record.source_key,)).fetchone()
        rev = getattr(record, 'source_revision', None)
        if row is not None and rev is not None and row['source_revision'] is not None and rev < row['source_revision']:
            return self._count('ignored_stale')
        source_id = int(record.source_message) if str(record.source_message).isdigit() else 0
        if row is None:
            if not record.visible:
                return self._count('ignored_never_public')
            message_id = self._message_id(con, record.source_key)
            seq = self._change(con, message_id, 1, 'insert', now)
            con.execute('INSERT INTO messages(message_id,source_key,source_kind,source_account,source_channel,source_session,'
                        'source_message,platform_message_id,speaker,occurred_at,first_observed_at,sort_at,observed_seq,revision,'
                        'source_revision,status,content,content_hash,note,source_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (message_id, record.source_key, record.source_kind, record.source_account, record.source_channel,
                         record.source_session, record.source_message, record.platform_message_id, record.speaker,
                         record.occurred_at, now, record.occurred_at if record.occurred_at is not None else now, seq, 1,
                         rev, 'public', record.content, _hash(record.content), record.note, source_id))
            return self._count('inserted')
        if not record.visible:
            if row['status'] == 'deleted':
                return self._count('unchanged')
            return self._mark_deleted(con, row, now, rev)
        if row['status'] == 'deleted':
            kind, status = 'restore', 'public'
        elif _hash(record.content) != row['content_hash']:
            kind, status = 'edit', 'edited'
        elif record.speaker != row['speaker']:
            kind, status = 'edit', row['status']
        else:
            if rev is not None and rev != row['source_revision']:
                con.execute('UPDATE messages SET source_revision=? WHERE pk=?', (rev, row['pk']))
            return self._count('unchanged')
        revision = row['revision'] + 1
        seq = self._change(con, row['message_id'], revision, kind, now)
        con.execute('UPDATE messages SET content=?,content_hash=?,speaker=?,note=?,status=?,revision=?,observed_seq=?,source_revision=? WHERE pk=?',
                    (record.content, _hash(record.content), record.speaker, record.note, status, revision, seq, rev, row['pk']))
        return self._count('restored' if kind == 'restore' else 'edited')

    def _mark_deleted(self, con, row, now, rev=None):
        revision = row['revision'] + 1
        seq = self._change(con, row['message_id'], revision, 'delete', now)
        # The projection keeps no copy of deleted content.
        con.execute("UPDATE messages SET status='deleted',content='',content_hash=?,revision=?,observed_seq=?,source_revision=coalesce(?,source_revision) WHERE pk=?",
                    (_hash(''), revision, seq, rev, row['pk']))
        return self._count('deleted')

    def _reconcile(self, con, reader, now, last, full):
        """Compare indexed rows with the source's current state, a bounded
        chunk of source ids per call (all of them when `full`), resuming where
        the last call stopped. Finds edits, deletions and restorations."""
        self._counts = {}
        pos = 0 if full else self._meta(con).get('reconcile_pos', 0)
        if pos >= last:
            pos = 0
        budget = last if full else RECONCILE_CHUNK
        done = 0
        while last and done < budget:
            low, high = pos + 1, min(last, pos + RECONCILE_CHUNK)
            records, _, _ = reader.between(low, high)
            current = {r.source_key: r for r in records}
            for row in con.execute("SELECT * FROM messages WHERE source_id BETWEEN ? AND ? AND source_key LIKE 'hermes:%'",
                                   (low, high)).fetchall():
                record = current.get(row['source_key'])
                if record is None:
                    if row['status'] != 'deleted':
                        self._mark_deleted(con, row, now)
                else:
                    self._apply(con, record, now)
            for record in records:
                if not con.execute('SELECT 1 FROM messages WHERE source_key=?', (record.source_key,)).fetchone():
                    self._apply(con, record, now)
            done += high - low + 1
            pos = high if high < last else 0
            if pos == 0:
                break
        self._set(con, reconcile_pos=pos, reconcile_at=now)
        out, self._counts = self._counts, {}
        return out

    def apply_records(self, records):
        """Fold records from a push-style adapter (or a replayed webhook) in one
        transaction. Used by adapters that are not pulled from a store."""
        with self._db() as con:
            con.execute('BEGIN IMMEDIATE')
            try:
                self._ensure(con)
                self._counts = {}
                for record in records:
                    self._apply(con, record, self.clock())
                out, self._counts = self._counts, {}
                self._prune(con)
                con.execute('COMMIT')
                return out
            except BaseException:
                con.execute('ROLLBACK')
                raise

    def _prune(self, con):
        high = con.execute('SELECT max(seq) FROM changes').fetchone()[0] or 0
        if high > RETAIN_CHANGES:
            con.execute('DELETE FROM changes WHERE seq<=?', (high - RETAIN_CHANGES,))
            self._set(con, retained_from=high - RETAIN_CHANGES + 1)

    # ------------------------------------------------------------------ reads
    def _sign(self, secret, payload):
        body = base64.urlsafe_b64encode(json.dumps(payload, separators=(',', ':')).encode()).decode().rstrip('=')
        mac = hmac.new(bytes.fromhex(secret), body.encode(), hashlib.sha256).hexdigest()[:24]
        return body + '.' + mac

    def _open_cursor(self, meta, cursor, kind):
        if not isinstance(cursor, str) or len(cursor) > 600 or cursor.count('.') != 1:
            raise CursorError('Invalid cursor')
        body, mac = cursor.split('.')
        try:
            payload = json.loads(base64.urlsafe_b64decode(body + '=' * (-len(body) % 4)))
        except (ValueError, TypeError):
            raise CursorError('Invalid cursor')
        if not isinstance(payload, dict) or payload.get('k') != kind:
            raise CursorError('Invalid cursor')
        if payload.get('c') != self.scope.conversation_id:
            raise CursorError('This cursor belongs to another conversation')
        if payload.get('p') != meta.get('projection_id'):
            raise ResyncRequired('projection_rebuilt')
        expected = hmac.new(bytes.fromhex(meta['secret']), body.encode(), hashlib.sha256).hexdigest()[:24]
        if not hmac.compare_digest(expected, mac):
            raise CursorError('Invalid cursor')
        return payload

    def _read_meta(self, con):
        meta = self._meta(con)
        if not meta or meta.get('schema') != SCHEMA_VERSION or meta.get('binding') != self.scope.binding_digest:
            raise ResyncRequired('projection_rebuilt')
        return meta

    @staticmethod
    def _message(row):
        deleted = row['status'] == 'deleted'
        return {'message_id': row['message_id'], 'revision': row['revision'], 'status': row['status'],
                'speaker': row['speaker'], 'role': {'owner': 'user', 'companion': 'assistant'}.get(row['speaker'], 'user'),
                'content': None if deleted else row['content'],
                'occurred_at': row['occurred_at'], 'occurred_at_known': row['occurred_at'] is not None,
                'observed_seq': row['observed_seq'],
                'source': {'kind': row['source_kind'], 'account': row['source_account'], 'channel': row['source_channel'],
                           'session': row['source_session'], 'message': row['source_message']},
                'reply_to': None,
                'correlation': {'platform_message_id': row['platform_message_id']} if row['platform_message_id'] else None,
                **({'note': row['note']} if row['note'] else {})}

    def _page(self, con, meta, limit, before=None):
        values = []
        where = "status<>'deleted'"
        if before is not None:
            where += ' AND (sort_at<? OR (sort_at=? AND message_id<?))'
            values = [before[0], before[0], before[1]]
        rows = con.execute(f'SELECT * FROM messages WHERE {where} ORDER BY sort_at DESC, message_id DESC LIMIT ?',
                           (*values, limit + 1)).fetchall()
        more = len(rows) > limit
        rows = rows[:limit]
        cursor = self._sign(meta['secret'], {'k': 'h', 'c': self.scope.conversation_id, 'p': meta['projection_id'],
                                             't': rows[-1]['sort_at'], 'i': rows[-1]['message_id']}) if more else None
        return [self._message(r) for r in reversed(rows)], cursor

    @staticmethod
    def _limit(limit, default, maximum):
        if limit is None:
            return default
        if type(limit) is not int or not 1 <= limit <= maximum:
            raise CursorError(f'limit must be 1-{maximum}')
        return limit

    def snapshot(self, limit=None):
        """The newest page of history and the change high-water mark, read in
        one transaction: every change after the mark is newer than this page."""
        limit = self._limit(limit, PAGE_DEFAULT, PAGE_MAX)
        with self._db() as con:
            con.execute('BEGIN')
            try:
                meta = self._read_meta(con)
                messages, before = self._page(con, meta, limit)
                high = con.execute('SELECT coalesce(max(seq),0) FROM changes').fetchone()[0]
                if not high:
                    high = meta.get('retained_from', 1) - 1
                return {'conversation_id': self.scope.conversation_id, 'projection_id': meta['projection_id'],
                        'messages': messages,
                        'history': {'before': before, 'start_reached': before is None,
                                    'start_note': 'The earliest message the sources still hold. '
                                                  'Messages a source deleted are not recoverable.'},
                        'changes': {'after': self._sign(meta['secret'], {'k': 'c', 'c': self.scope.conversation_id,
                                                                          'p': meta['projection_id'], 's': high}),
                                    'high_water': high},
                        'excluded': meta.get('excluded') or {}}
            finally:
                con.execute('COMMIT')

    def history(self, before, limit=None):
        limit = self._limit(limit, PAGE_DEFAULT, PAGE_MAX)
        with self._db() as con:
            con.execute('BEGIN')
            try:
                meta = self._read_meta(con)
                payload = self._open_cursor(meta, before, 'h')
                messages, cursor = self._page(con, meta, limit, (payload['t'], payload['i']))
                return {'conversation_id': self.scope.conversation_id, 'projection_id': meta['projection_id'],
                        'messages': messages, 'history': {'before': cursor, 'start_reached': cursor is None}}
            finally:
                con.execute('COMMIT')

    def changes(self, after, limit=None):
        """Changes after the cursor's mark, oldest first, each with the
        message's current state (a deleted message carries no content).
        Clients apply them by message_id, keeping the highest revision."""
        limit = self._limit(limit, CHANGES_DEFAULT, CHANGES_MAX)
        with self._db() as con:
            con.execute('BEGIN')
            try:
                meta = self._read_meta(con)
                payload = self._open_cursor(meta, after, 'c')
                mark = payload['s']
                if not isinstance(mark, int) or mark < 0:
                    raise CursorError('Invalid cursor')
                if mark + 1 < meta.get('retained_from', 1):
                    raise ResyncRequired('changes_expired')
                rows = con.execute('SELECT c.seq,c.kind,c.revision AS change_revision,m.* FROM changes c '
                                   'JOIN messages m ON m.message_id=c.message_id WHERE c.seq>? ORDER BY c.seq LIMIT ?',
                                   (mark, limit + 1)).fetchall()
                more = len(rows) > limit
                rows = rows[:limit]
                high = rows[-1]['seq'] if rows else mark
                return {'conversation_id': self.scope.conversation_id, 'projection_id': meta['projection_id'],
                        'changes': [{'seq': r['seq'], 'kind': r['kind'], 'revision': r['change_revision'],
                                     'message': self._message(r)} for r in rows],
                        'after': self._sign(meta['secret'], {'k': 'c', 'c': self.scope.conversation_id,
                                                             'p': meta['projection_id'], 's': high}),
                        'more': more}
            finally:
                con.execute('COMMIT')
