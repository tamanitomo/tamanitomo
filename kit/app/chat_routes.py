"""Read routes for the owner's private conversation (Phase 1A contract).

  GET /api/chat/snapshot?limit=60         newest page + change high-water mark
  GET /api/chat/history?before=C&limit=60 older retained history
  GET /api/chat/changes?after=C&limit=200 what changed after a mark
  GET /api/chat/sources                   capability table and exclusions

Sending is unchanged (POST /api/chat) and so is the legacy /api/feed. Errors:
  400 invalid_cursor        malformed, forged, or another conversation's cursor
  409 resync_required       load a new snapshot (reason says why)
  503 source_unavailable    retryable; nothing was changed
"""
from __future__ import annotations

from pathlib import Path

from .chat_projection import ChatScope, CursorError, Projection, ResyncRequired
from .chat_sources import HermesSource, SourceUnavailable, capabilities, owner_binding, platform_conflict


def send_overlay(scope, binding, model):
    """correlation.send_id for projected rows (Phase 1B 4.10.3), computed at read time.

    A row gets a send's id only when ALL hold for the captured scope: the send belongs to
    this conversation, its source kind equals the row's and is authorised by the CURRENT
    binding, the send's sources were verified (capability full), the receipt's identity
    fingerprint equals the row's, and no known platform id conflicts. One row linked by
    two sends is ambiguous and gets neither. The projection itself is unchanged."""
    kinds = {k for k, on in (('workspace', binding.workspace), ('terminal', binding.terminal)) if on}

    def overlay(rows):
        keys = [(r['source_session'], int(r['source_message'])) for r in rows
                if r['source_kind'] in kinds and str(r['source_key']).startswith('hermes:')
                and str(r['source_message']).isdigit() and r['status'] != 'deleted']
        found = model.links(keys) if keys else {}
        out = {}
        for r in rows:
            if r['source_kind'] not in kinds or not str(r['source_message']).isdigit():
                continue
            hits = [l for l in found.get((r['source_session'], int(r['source_message'])), [])
                    if l['conversation_id'] == scope.conversation_id and l['capability'] == 'full'
                    and l['source_kind'] == r['source_kind'] and l['source_namespace'] == r['source_account']
                    and l['fingerprint'] == r['source_fp'] and not platform_conflict(None, r['platform_message_id'])]
            if len(hits) == 1:
                h = hits[0]
                out[r['message_id']] = {'send_id': h['send_id'],
                                        'send_part': 'owner' if h['role'] == 'owner' else f"reply:{h['part']}"}
        return out
    return overlay


# The keyed-send ledger directory (Phase 1B). Named here only to disclose, in an app built
# WITHOUT keyed sends, that a profile holds send provenance these reads are not applying.
SEND_LEDGER_DIR = '.tamanitomo-sends'


class _NoProvenance:
    """Keyed sends not enabled in this app (every shipped build): nothing is applied."""
    workspace_sessions = frozenset()
    internal_map = {}

    def __init__(self, home):
        self.ledger = (Path(home) / SEND_LEDGER_DIR).exists()

    def links(self, keys):
        return {}

    def disclosure(self):
        if not self.ledger:
            return None
        return {'state': 'not_applied', 'notice': 'This profile has a keyed-send ledger, but keyed sends are not '
                'enabled in this app, so its provenance (continuation notes, created sessions) is not applied.'}


def register(app, state_dir, current_selection, load, attach, provenance=None):
    """`provenance(home)` -> chat_sends.ReadModel, passed only by an app built with keyed
    sends enabled (Phase 1B, not activated). Otherwise reads are exactly Phase 1A's."""
    from fastapi.responses import JSONResponse

    def capture():
        """Scope and authorisation, captured once before any read. Nothing
        later in the request looks at the selected profile again."""
        c = load()
        installation, profile = current_selection()
        binding = owner_binding(c)
        scope = ChatScope(installation, profile or 'default', str(Path(c.home).resolve()), binding.digest())
        if provenance is None:
            projection = Projection(state_dir, scope)
            projection.provenance = _NoProvenance(c.home)
        else:
            # Send provenance (Phase 1B): read-only; state 'none' when no ledger exists here.
            model = provenance(c.home)
            projection = Projection(state_dir, scope, overlay=send_overlay(scope, binding, model))
            projection.provenance = model
        return c, scope, binding, projection

    def source(c, binding, projection):
        if provenance is None:
            return HermesSource(c, binding)
        return HermesSource(c, binding, provenance=projection.provenance)

    def disclose(page, projection):
        note = projection.provenance.disclosure()
        if note is not None:
            page['provenance'] = note
        return page

    def guarded(fn):
        try:
            return fn()
        except SourceUnavailable as exc:
            return JSONResponse({'error': 'source_unavailable', 'retryable': True, 'detail': str(exc)}, status_code=503)
        except ResyncRequired as exc:
            return JSONResponse({'error': 'resync_required', 'reason': exc.reason}, status_code=409)
        except CursorError as exc:
            return JSONResponse({'error': 'invalid_cursor', 'detail': str(exc)}, status_code=400)

    def with_media(c, messages):
        visible = [m for m in messages if m.get('content') is not None]
        attach(c, visible)
        for m in messages:
            m.setdefault('attachments', [])
        return messages

    @app.get('/api/chat/snapshot')
    def chat_snapshot(limit: int | None = None):
        def run():
            c, scope, binding, projection = capture()
            sync = projection.sync(source(c, binding, projection))
            page = projection.snapshot(limit)
            disclose(page, projection)
            page['messages'] = with_media(c, page['messages'])
            page['scope'] = {'profile': scope.profile, 'installation': scope.installation,
                             'owner_binding': binding.origin}
            page['sync'] = {k: v for k, v in sync.items() if k != 'excluded'}
            return page
        return guarded(run)

    @app.get('/api/chat/history')
    def chat_history(before: str, limit: int | None = None):
        def run():
            c, scope, binding, projection = capture()
            page = projection.history(before, limit)
            page['messages'] = with_media(c, page['messages'])
            disclose(page, projection)
            return page
        return guarded(run)

    @app.get('/api/chat/changes')
    def chat_changes(after: str, limit: int | None = None):
        def run():
            c, scope, binding, projection = capture()
            projection.sync(source(c, binding, projection))
            page = projection.changes(after, limit)
            disclose(page, projection)
            with_media(c, [ch['message'] for ch in page['changes']])
            return page
        return guarded(run)

    @app.get('/api/chat/sources')
    def chat_sources():
        def run():
            c, scope, binding, projection = capture()
            return {'capabilities': capabilities(send_provenance=provenance is not None),
                    'owner_binding': {'origin': binding.origin, 'workspace': binding.workspace,
                                      'terminal': binding.terminal, 'telegram_accounts': len(binding.telegram)},
                    'conversation_id': scope.conversation_id}
        return guarded(run)
