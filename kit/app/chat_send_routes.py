"""Keyed workspace sends over HTTP: the Phase 1B C1 integration (PHASE1B_DESIGN.md 5).

NOT ACTIVATED. `register()` runs only when the app is built with an explicit
`chat_sends=Options(...)` (server.build); no shipped entry point passes it, so no
ordinary or live profile has these routes, no UI calls them, and nothing is in
release-files.json. The current `POST /api/chat` path is unchanged and there is no
fallback between the two: an accepted keyed send is never retried on the unkeyed path.

  GET  /api/chat/sends/bootstrap          {conversation_id, generation}; creates the ledger
  POST /api/chat/sends                    keyed acceptance: 202 new, 200 replay, 409/422/503
  GET  /api/chat/sends/{send_id}          receipt (recovery first)
  GET  /api/chat/sends?key=K | ?open=1    receipt by client key | open receipts
  POST /api/chat/sends/{send_id}/stop     receipt; never `interrupted` because a stop was asked
  POST /api/chat/sends/ledger/reset       explicit, confirmed ledger reset (4.1)
  GET  /api/operations/{id}               for a send's reserved id: a view built from the ledger;
                                          while running, an authorised public stream snapshot;
                                          a keyed send the ledger cannot resolve: status unknown

Every route captures its scope (installation, profile, resolved home, owner binding) ONCE,
before any read or side effect, and never looks at the selected profile again. A send_id,
key or operation id from another scope is 404. Source links, message ids and any content
are returned only while the CURRENT binding still authorises the send's source kind, and
only for rows whose identity fingerprint still matches the receipt (4.10.3).
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import os
import re
import threading
from pathlib import Path
from typing import Callable

from . import chat_sends as cs
from . import runtime as hr
from .chat_projection import ChatScope, Projection
from .chat_sources import HermesSource, SourceUnavailable, owner_binding, session_kind

NOTE = 'Hermes owns this conversation. All channels share this profile’s identity, memory, and lived state.'
RESET_CONFIRMATION = 'reset send ledger'
STATUS = {'accepted': 'running', 'launching': 'running', 'generating': 'running', 'stopping': 'running',
          'complete': 'complete', 'failed': 'failed', 'interrupted': 'interrupted',
          'not_started': 'failed', 'unknown': 'interrupted'}
PROGRESS = {'accepted': 'Starting', 'launching': 'Starting', 'generating': 'Replying', 'stopping': 'Replying',
            'complete': 'Complete'}
# The only fields a chat operation file may hold (5.7). Text never reaches the file:
# `progress` is from a fixed set, `error` is the fixed sentence for `error_code`.
PERSISTED = ('id', 'scope', 'profile', 'kind', 'label', 'status', 'progress', 'percent', 'started_at',
             'finished_at', 'send_id', 'error_code', 'error', 'format')
FIXED_PROGRESS = ('Starting', 'Waiting for Hermes', 'Replying', 'Complete', 'Needs attention')
# A keyed operation whose ledger cannot resolve it (F1): never a legacy row, never content.
UNRESOLVED = {
    'send_ledger_unavailable': 'The send ledger for this conversation cannot be read, so how this reply '
                               'went is unknown here.',
    'send_record_unavailable': 'The send ledger no longer holds this send (reset or retention), so how '
                               'this reply went is not shown.',
}
# The public stream snapshot (F2): bounded, reasoning markup removed server side.
STREAM_LIMIT = 100_000
_REASONING = re.compile(r'<(think|thinking|reasoning)>[\s\S]*?(</\1>|$)', re.I)
_TAGS = ('<think>', '<thinking>', '<reasoning>')
_CLOSE = {t: '</' + t[1:] for t in _TAGS}
_LONGEST = max(map(len, _TAGS))
# Only ASCII tag names are case-insensitive. Preserve offsets into the original Unicode
# string: full str.lower() can expand characters (for example U+0130) and shift indices.
_ASCII_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
REFUSALS = {
    'installation_busy': 'Another action is running for this Hermes installation; try again when it finishes.',
    'chat_reply_running': 'A chat reply is still running; wait for it to finish first.',
}


@dataclasses.dataclass
class Options:
    """How keyed sends run when explicitly enabled. `executor(runtime, home)` returns the
    ExecutorSpec (default: the installation's own Hermes interpreter, Runtime.executor_spec)."""
    executor: Callable | None = None
    turn_timeout: float = 600.0
    stop_grace: float = 15.0
    watchdog_interval: float = 1.0
    platform_check: Callable | None = None


def _iso(stamp):
    return dt.datetime.fromtimestamp(stamp, dt.timezone.utc).isoformat() if stamp else None


@dataclasses.dataclass
class Context:
    """Everything one request is authorised for, captured once."""
    c: object
    rt: object
    scope: ChatScope
    binding: object
    svc: cs.SendService
    model: cs.ReadModel

    @property
    def kinds(self):
        return {k for k, on in (('workspace', self.binding.workspace), ('terminal', self.binding.terminal)) if on}


class Hidden(LookupError):
    """A keyed operation outside the captured scope: 404, never the legacy branch."""


def public_stream(text):
    """The reply text streamed so far with reasoning blocks removed, including one still
    open and a trailing fragment that may be the start of an opening tag. (text, truncated)."""
    text = _REASONING.sub('', text or '')
    cut = text.rfind('<')
    if cut >= 0 and '>' not in text[cut:] and any(t.startswith(text[cut:].lower()) for t in _TAGS):
        text = text[:cut]
    if len(text) > STREAM_LIMIT:
        return text[-STREAM_LIMIT:], True
    return text, False


class PublicFilter:
    """The public-output boundary for one attempt's delta stream (R1/R2), applied BEFORE any
    buffering or truncation. Incremental and bounded: across fragments it keeps only whether
    the stream is inside a withheld block and a partial tag of at most a few characters. A
    withheld body is never stored, so dropping old text can never forget that a block is open.
    Tags as `public_stream`: <think>, <thinking>, <reasoning>, case-insensitive. One instance
    per attempt, fed from one thread; a provider retry inside the attempt is the same stream."""

    def __init__(self):
        self.close = None           # the closing tag while inside a withheld block
        self.pending = ''           # a possible partial tag (bounded by _LONGEST)
        self.withheld = False       # a block was withheld at some point

    def feed(self, text):
        s = self.pending + str(text or '')
        low, n, i, out = s.translate(_ASCII_LOWER), len(s), 0, []
        self.pending = ''
        while i < n:
            if self.close:
                j = low.find(self.close, i)
                if j < 0:
                    start = max(i, n - len(self.close) + 1)
                    k = next((k for k in range(start, n) if self.close.startswith(low[k:])), n)
                    self.pending = s[k:]
                    break
                i, self.close = j + len(self.close), None
                continue
            j = low.find('<', i)
            if j < 0:
                out.append(s[i:])
                break
            out.append(s[i:j])
            head = low[j:j + _LONGEST]
            tag = next((t for t in _TAGS if head.startswith(t)), None)
            if tag:
                self.close, self.withheld, i = _CLOSE[tag], True, j + len(tag)
            elif n - j < _LONGEST and any(t.startswith(low[j:]) for t in _TAGS):
                self.pending = s[j:]            # maybe an opening tag split across fragments
                break
            else:
                out.append('<')
                i = j + 1
        return ''.join(out)

    def finish(self):
        """End of the attempt's stream: a partial that never became a tag was ordinary text;
        an unclosed block stays withheld."""
        tail = '' if self.close else self.pending
        self.pending = ''
        return tail


def public_text(text):
    """A whole string through the same boundary (terminal responses)."""
    f = PublicFilter()
    return f.feed(text) + f.finish()


class Integration:
    """One app process's keyed-send integration: one SendService (one controller) per
    physical profile home, shared by every request that reaches that home."""

    def __init__(self, state_dir, options, operations, runtimes):
        self.state_dir = Path(state_dir)
        self.options = options
        self.operations = operations
        self.runtimes = runtimes            # the app's live {id: Runtime} mapping
        self._services = {}
        self._lock = threading.Lock()

    # ----- services -----

    def service(self, rt, home):
        key = os.path.realpath(home)
        make = self.options.executor or (lambda runtime, h: runtime.executor_spec(h))
        spec = make(rt, home)       # per request, like Runtime.chat: a changed .env applies to the next turn
        with self._lock:
            svc = self._services.get(key)
            if svc is None:
                svc = cs.SendService(home, self.state_dir, spec, installation_root=rt.root,
                                     turn_timeout=self.options.turn_timeout, stop_grace=self.options.stop_grace,
                                     watchdog_interval=self.options.watchdog_interval,
                                     platform_check=self.options.platform_check)
                self._services[key] = svc
            else:
                svc.executor = spec
            return svc

    def close(self):
        with self._lock:
            for svc in self._services.values():
                svc.close()

    def homes(self, rt):
        root = Path(rt.root)
        extra = sorted(p for p in (root / 'profiles').glob('*') if p.is_dir()) if (root / 'profiles').is_dir() else []
        return [root, *extra]

    def recover_all(self):
        """Eager recovery at app start (4.6) for every profile home that has a ledger."""
        for rt in list(self.runtimes.values()):
            for home in self.homes(rt):
                if not cs.sp.ledger_dir(home).is_dir():
                    continue
                svc = self.service(rt, home)
                try:
                    if svc.status() == 'ok':
                        svc.recover_open()
                        svc.prune()
                except (cs.Refused, OSError, cs.sqlite3.Error):
                    pass            # reported by the next request touching this home

    # ----- the installation guard (4.7) -----

    def guard(self, scope):
        """Operations.guard: the cross-process hold for a non-chat action on a Hermes
        installation. Other scopes (the application's own update) are not installations."""
        roots = {os.path.realpath(str(rt.root)) for rt in self.runtimes.values()}
        if os.path.realpath(str(scope)) not in roots:
            return None
        try:
            return cs.hold_installation(scope)
        except cs.Refused as exc:
            raise ValueError(REFUSALS.get(exc.code, exc.code)) from None

    # ----- scope -----

    def capture(self, select, load, current_selection):
        c = load()
        rt, _ = select()
        installation, profile = current_selection()
        binding = owner_binding(c)
        home = str(Path(c.home).resolve())
        scope = ChatScope(installation, profile or 'default', home, binding.digest())
        return Context(c, rt, scope, binding, self.service(rt, c.home), cs.read_model(c.home))

    def authorize_session(self, ctx):
        """A resumed session must be one the CURRENT binding would project as a workspace or
        terminal session of this profile (4.10.3); profile membership alone is not enough."""
        def check(scope, session):
            workspace = hr.read_workspace_sessions(ctx.c) | set(ctx.model.workspace_sessions)
            try:
                with hr.session_db(ctx.c) as state:
                    if state is None:
                        return None
                    con, columns, where, params = state
                    pick = lambda col: col if col in columns else 'NULL'
                    row = con.execute(f"SELECT id AS session_id, source, {pick('user_id')} AS user_id, "
                                      f"{pick('chat_id')} AS chat_id, {pick('chat_type')} AS chat_type "
                                      f'FROM sessions WHERE id=? AND {where}', (session, *params)).fetchone()
            except (ValueError, OSError, cs.sqlite3.Error):
                raise cs.Refused('source_unavailable', 503) from None
            if row is None:
                return None
            kind, _, _ = session_kind(dict(row), ctx.binding, workspace)
            return (kind, None) if kind in ('workspace', 'terminal') else None
        return check

    # ----- links, content -----

    def resolve(self, ctx, row, links):
        """Resolve receipted links to projected messages under the current authorisation.
        ('linked' | 'lost' | 'pending' | 'unavailable' | 'not_authorised', owner, replies)."""
        if row['source_kind'] not in ctx.kinds or row['capability'] != 'full':
            return 'not_authorised', None, []
        if not links:
            return 'pending', None, []
        projection = Projection(self.state_dir, ctx.scope)
        try:
            projection.sync(HermesSource(ctx.c, ctx.binding, provenance=ctx.model))
            found = projection.by_source([(l['session_id'], l['row_id']) for l in links])
        except SourceUnavailable:
            return 'unavailable', None, []
        owner, replies, lost = None, [], False
        for link in links:
            hit = found.get((str(link['session_id']), int(link['row_id'])))
            if hit is None or hit['status'] == 'deleted' or hit['fingerprint'] != link['fingerprint'] \
                    or hit['kind'] != row['source_kind'] or hit['account'] != row['source_namespace']:
                lost = True         # the new holder of a source id never gets this send
                continue
            if link['role'] == 'owner':
                owner = hit['message']
            else:
                replies.append(hit['message'])
        return ('lost' if lost else 'linked'), owner, replies

    def http_receipt(self, ctx, receipt, row):
        out = {k: receipt[k] for k in ('send_id', 'client_key', 'conversation_id', 'state', 'owner_turn', 'reply',
                                       'correlation', 'capability', 'liveness', 'coverage', 'settled', 'error',
                                       'created_at', 'updated_at')}
        out['operation'] = {'id': receipt['operation_id']}
        if 'source_links' not in receipt:
            return out              # not authorised now: state and codes only (4.10.3)
        links = ctx.svc.links(row['send_id'])
        status, owner, replies = self.resolve(ctx, row, links)
        sessions = receipt.get('hermes_sessions') or []
        out['session'] = sessions[-1]['session_id'] if sessions else None
        out['links'] = status
        out['owner_message_id'] = owner['message_id'] if owner else None
        out['reply_message_ids'] = [m['message_id'] for m in replies]
        return out

    def receipt(self, ctx, send_id, recover=True):
        receipt = ctx.svc.receipt(ctx.scope, send_id, authorized_kinds=ctx.kinds, recover=recover)
        return self.http_receipt(ctx, receipt, ctx.svc.row(ctx.scope, send_id))

    # ----- operations as views (5.6, 5.7) -----

    def persist(self, send_id):
        def allowlisted(row):
            out = {k: row[k] for k in PERSISTED if k in row}
            out['format'], out['send_id'] = 2, send_id
            if out.get('progress') not in FIXED_PROGRESS:
                out['progress'] = 'Needs attention' if row.get('status') == 'failed' else 'Starting'
            result = row.get('result') if isinstance(row.get('result'), dict) else {}
            state = result.get('state')
            if row.get('status') == 'complete' and state:
                out['status'], out['error_code'] = STATUS.get(state, 'interrupted'), result.get('error_code')
            elif row.get('status') == 'failed':
                out['error_code'] = 'launch_failed'
            out['error'] = cs.ERRORS.get(out.get('error_code')) if out.get('error_code') else None
            if out.get('status') in ('failed', 'interrupted') and not out['error']:
                out['error'] = 'Needs attention.'
            out['result'] = {k: result.get(k) for k in ('session', 'send_id', 'note')} if result else None
            return out
        return allowlisted

    def operation_view(self, ident, select, load, current_selection):
        """The operation for a send's reserved id, built from the ledger (authoritative).
        None ONLY when this app knows no keyed send by this id (the legacy branch may answer).
        A keyed send whose ledger is unreadable, reset or pruned gets an explicit `unknown`
        view with no content; one outside the captured scope raises Hidden (404). A missing
        or stale operation file never implies that a new send is needed, and nothing here
        ever launches, resets or recreates anything."""
        if not re.fullmatch('[a-f0-9]{32}', ident or ''):
            return None
        origin = self.operations.keyed(ident)
        ctx = self.capture(select, load, current_selection)
        try:
            ledger = ctx.svc.status()
            send_id = ctx.svc.by_operation(ctx.scope, ident) if ledger == 'ok' else None
        except (cs.Refused, OSError, cs.sqlite3.Error):
            ledger, send_id = 'lost', None
        if send_id is None:
            if origin is None:
                return None
            return self.unresolved_view(ctx, ident, origin, ledger)
        receipt = ctx.svc.receipt(ctx.scope, send_id, authorized_kinds=ctx.kinds)
        row = ctx.svc.row(ctx.scope, send_id)
        http = self.http_receipt(ctx, receipt, row)
        status = STATUS[row['state']]
        with self.operations.lock:
            memory = dict(self.operations.rows.get(ident) or {})
        view = {'id': ident, 'scope': str(ctx.rt.root), 'profile': ctx.scope.profile, 'kind': 'chat',
                'label': memory.get('label') or 'Chat', 'status': status,
                'progress': PROGRESS.get(row['state'], 'Needs attention'),
                'started_at': _iso(row['created_at']), 'finished_at': _iso(row['settled_at']),
                'send_id': send_id, 'error_code': row['error_code'],
                'error': cs.ERRORS.get(row['error_code']) if row['error_code'] else None,
                'format': 2, 'send': http}
        if status != 'running':
            view['result'] = self.legacy_result(ctx, row, http, memory)
        else:
            view['stream'] = self.stream(ctx, row, memory)
            if view['stream'].get('available'):
                view['stream_text'] = view['stream']['text']     # what the current poller renders
        return view

    def unresolved_view(self, ctx, ident, origin, ledger):
        """F1: a keyed send this app recorded, which the ledger cannot resolve now. Metadata
        only; `unknown`, never a claim that it ran, failed, or never existed."""
        if origin.get('scope') != str(ctx.rt.root) or (origin.get('profile') or 'default') != ctx.scope.profile:
            raise Hidden(ident)
        code = 'send_ledger_unavailable' if ledger != 'ok' else 'send_record_unavailable'
        return {'id': ident, 'scope': str(ctx.rt.root), 'profile': ctx.scope.profile, 'kind': 'chat',
                'label': origin.get('label') or 'Chat', 'status': 'unknown', 'progress': 'Needs attention',
                'started_at': origin.get('started_at'), 'finished_at': None, 'send_id': origin['send_id'],
                'error_code': code, 'error': UNRESOLVED[code], 'format': 2, 'result': None,
                'send': {'send_id': origin['send_id'], 'state': 'unknown', 'settled': None,
                         'ledger': 'unavailable' if ledger != 'ok' else 'no_record'}}

    def stream(self, ctx, row, memory):
        """F2: the public stream so far, as a snapshot (never an append log), rechecked on
        every read against the CURRENT binding. Only this process's in-memory buffer is a
        source: after a restart it is honestly unavailable, never regenerated."""
        if row['source_kind'] not in ctx.kinds:
            return {'available': False, 'reason': 'not_authorised'}
        if row['capability'] != 'full':
            return {'available': False, 'reason': 'sources_unverified'}
        if memory.get('send_id') != row['send_id'] or 'stream_text' not in memory:
            return {'available': False, 'reason': 'not_retained' if memory.get('send_id') != row['send_id']
                    else 'not_started'}
        text, truncated = public_stream(memory['stream_text'])
        return {'available': True, 'text': text, 'truncated': truncated}

    def legacy_result(self, ctx, row, http, memory):
        """The legacy `result` for old clients (5.7), under the CURRENT authorisation on both
        branches: the live process's in-memory response is withheld exactly like the
        reconstruction when the send's kind is no longer authorised or its linked sources no
        longer resolve. A reply is never regenerated because content is missing."""
        result = {'session': http.get('session'), 'send_id': row['send_id'], 'note': NOTE,
                  'response': None, 'messages': [], 'content_retained': False}
        if http.get('links') != 'linked':
            return result
        _, owner, replies = self.resolve(ctx, row, ctx.svc.links(row['send_id']))
        messages = [m for m in [owner, *replies] if m]
        # R2: the authorised linked final row first; the in-memory transcript (already filtered
        # when it was streamed) only when no reply row is linked. Either way through the same
        # public-output boundary, so a terminal state never reintroduces withheld text.
        remembered = (memory.get('result') or {}).get('response') if memory.get('status') != 'running' else None
        response = replies[-1]['content'] if replies else remembered
        response = public_text(response) if response else None
        result.update(messages=messages, response=response or None, content_retained=bool(response))
        return result

    def launch_action(self, ctx, send_id, message):
        svc, c = ctx.svc, ctx.c

        def action(report):
            report('Waiting for Hermes')
            public, started = [], []
            gate = PublicFilter()           # this attempt's public-output boundary (R1)

            def on_delta(text):
                if not started:
                    started.append(1)
                    report('Replying')
                visible = gate.feed(text)
                if visible:
                    public.append(visible)
                    report.stream(visible)  # only public text is ever buffered
            try:
                row = svc.launch(send_id, message, on_delta)
            except Exception:
                # Nothing about this attempt is guessed: fence it (not_started when it never
                # registered) and let the ledger say what happened.
                row = svc._resolve(send_id, fence=True, error_code='launch_failed')
                if row is None:
                    raise
            tail = gate.finish()
            if tail:
                public.append(tail)
                report.stream(tail)
            receipt = svc.receipt(ctx.scope, send_id, recover=False)
            created = [s['session_id'] for s in receipt['hermes_sessions'] if s['created_here']]
            if row['capability'] == 'full' and row['source_kind'] == 'workspace':
                for session in created:     # for older readers of the JSON registry only (4.10.2)
                    hr.note_workspace_session(c, session)
            sessions = receipt['hermes_sessions']
            return {'state': row['state'], 'error_code': row['error_code'], 'send_id': send_id, 'note': NOTE,
                    'session': sessions[-1]['session_id'] if sessions else None,
                    'response': ''.join(public) or None}
        return action


def register(app, state_dir, select, load, current_selection, operations, options):
    from fastapi import Body
    from fastapi.responses import JSONResponse

    sends = Integration(state_dir, options, operations, app.state.runtimes)
    app.state.chat_sends = sends
    operations.guard = sends.guard

    def refused(exc):
        extra = {k: v for k, v in exc.extra.items() if k in ('send_id', 'executors')}
        return JSONResponse({'error': exc.code, **extra}, status_code=exc.status)

    def guarded(fn):
        try:
            return fn()
        except cs.Refused as exc:
            return refused(exc)
        except cs.NotFound:
            return JSONResponse({'error': 'not_found'}, status_code=404)
        except SourceUnavailable as exc:
            return JSONResponse({'error': 'source_unavailable', 'retryable': True, 'detail': str(exc)},
                                status_code=503)

    def capture():
        return sends.capture(select, load, current_selection)

    @app.get('/api/chat/sends/bootstrap')
    def send_bootstrap():
        def run():
            ctx = capture()
            return ctx.svc.bootstrap(ctx.scope)
        return guarded(run)

    @app.post('/api/chat/sends')
    def send_accept(payload: dict = Body(...)):
        def run():
            ctx = capture()
            root = str(ctx.rt.root)
            claimed = operations.claim(root)
            try:
                status, body = ctx.svc.accept(ctx.scope, payload, sends.authorize_session(ctx), admit=claimed)
            except BaseException:
                if claimed:
                    operations.release(root)
                raise
            send_id = body['send']['send_id']
            if status == 202:
                row = ctx.svc.row(ctx.scope, send_id)
                try:
                    operations.submit(root, 'Chat with ' + str(getattr(ctx.c, 'agent', 'companion')),
                                      sends.launch_action(ctx, send_id, payload['message']),
                                      profile=ctx.scope.profile, kind='chat', ident=row['operation_id'],
                                      claimed=True, persist=sends.persist(send_id), send_id=send_id)
                except BaseException:
                    operations.release(root)
                    ctx.svc._resolve(send_id, fence=True, error_code='launch_failed')
                    raise
            elif claimed:
                operations.release(root)
            out = {'send': sends.receipt(ctx, send_id, recover=False),
                   'operation': {'id': body['send']['operation_id']}}
            for key in ('replay', 'rearm', 'rearmed'):
                if key in body:
                    out[key] = body[key]
            return JSONResponse(out, status_code=status)
        return guarded(run)

    @app.get('/api/chat/sends')
    def send_lookup(key: str | None = None, open: int | None = None):
        def run():
            ctx = capture()
            if key is not None:
                receipt = ctx.svc.lookup(ctx.scope, key, authorized_kinds=ctx.kinds)
                return sends.http_receipt(ctx, receipt, ctx.svc.row(ctx.scope, receipt['send_id']))
            if open:
                return {'sends': [sends.http_receipt(ctx, r, ctx.svc.row(ctx.scope, r['send_id']))
                                  for r in ctx.svc.open_receipts(ctx.scope, authorized_kinds=ctx.kinds)]}
            return JSONResponse({'error': 'invalid_request'}, status_code=400)
        return guarded(run)

    @app.get('/api/chat/sends/{send_id}')
    def send_receipt(send_id: str):
        def run():
            ctx = capture()
            ctx.svc._open_or_refuse()
            return sends.receipt(ctx, send_id)
        return guarded(run)

    @app.post('/api/chat/sends/ledger/reset')
    def send_reset(payload: dict = Body(default={})):
        def run():
            ctx = capture()
            if payload.get('confirm') != RESET_CONFIRMATION:
                return JSONResponse({'error': 'confirmation_required', 'confirm': RESET_CONFIRMATION,
                                     'reason': 'Resetting the send ledger forgets every earlier send: a retry of '
                                               'one is refused, and whether it was sent stays unknown.'},
                                    status_code=400)
            out = ctx.svc.reset()
            return {'conversation_id': ctx.scope.conversation_id, 'generation': out['generation']}
        return guarded(run)

    @app.post('/api/chat/sends/{send_id}/stop')
    def send_stop(send_id: str):
        def run():
            ctx = capture()
            ctx.svc.stop(ctx.scope, send_id)
            return sends.receipt(ctx, send_id, recover=False)
        return guarded(run)

    sends.recover_all()
    return sends
