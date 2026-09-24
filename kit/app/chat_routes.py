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
from .chat_sources import HermesSource, SourceUnavailable, capabilities, owner_binding


def register(app, state_dir, current_selection, load, attach):
    from fastapi.responses import JSONResponse

    def capture():
        """Scope and authorisation, captured once before any read. Nothing
        later in the request looks at the selected profile again."""
        c = load()
        installation, profile = current_selection()
        binding = owner_binding(c)
        scope = ChatScope(installation, profile or 'default', str(Path(c.home).resolve()), binding.digest())
        return c, scope, binding, Projection(state_dir, scope)

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
            sync = projection.sync(HermesSource(c, binding))
            page = projection.snapshot(limit)
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
            return page
        return guarded(run)

    @app.get('/api/chat/changes')
    def chat_changes(after: str, limit: int | None = None):
        def run():
            c, scope, binding, projection = capture()
            projection.sync(HermesSource(c, binding))
            page = projection.changes(after, limit)
            with_media(c, [ch['message'] for ch in page['changes']])
            return page
        return guarded(run)

    @app.get('/api/chat/sources')
    def chat_sources():
        def run():
            c, scope, binding, projection = capture()
            return {'capabilities': capabilities(),
                    'owner_binding': {'origin': binding.origin, 'workspace': binding.workspace,
                                      'terminal': binding.terminal, 'telegram_accounts': len(binding.telegram)},
                    'conversation_id': scope.conversation_id}
        return guarded(run)
