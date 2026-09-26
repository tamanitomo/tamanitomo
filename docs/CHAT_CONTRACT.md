# Companion chat

The floating chat dock is the workspace's chat surface on every page. On desktop it
opens as a card in the lower-right corner; on phones it opens from a circular
button into a bottom sheet. Closing or minimizing the dock does not cancel a turn.

`POST /api/chat` runs `Runtime.chat` against the selected Hermes home. The runtime
launches `hermes_stream.py` with Hermes's own interpreter, preserving its hooks,
identity, tools and session storage. If that interpreter is unavailable for a
custom command, the normal quiet CLI supplies the final reply.

Browsers request `Accept: text/event-stream` to receive operation, delta, session,
final and error events. Other clients can keep using the JSON operation response
and `/api/operations/{id}` polling. A disconnected browser must inspect the
operation or reload history before retrying; it must never resubmit automatically.

Hermes remains the transcript authority. Read-only history excludes other
profiles, groups, unknown platform participants, background jobs and tool output.
A resumed turn must belong to an eligible local conversation in the selected
profile. App authentication and profile selection apply to history and streaming
requests alike.

No user transcript or existing data file is migrated or removed by this reset.
