# Core cohesion reset

All implementation and verification use the repository and synthetic temporary
profiles. Existing Hermes homes, vaults and transcript databases require no
migration.

## Phase 1 — one chat surface

- Replaced the full-screen chat with a floating dock on every workspace page.
- Removed the obsolete send supervisor, projection/cache and keyed browser client.
- Kept Hermes as the transcript authority and streaming runtime, with an SSE
  transport and the existing operation API for connection recovery.
- Kept owner/profile filtering in a small read-only transcript adapter for both
  chat history and evidence-backed memory.
- Checked existing application, reflection, context and runtime tests (165 pass),
  plus presence/configuration/outbox/journal/bridge tests (59 pass).
- Browser smoke: Chromium at 1440px and 390px, no page errors; successful chat
  sends; desktop card and 65vh phone sheet.

The final phase will record the consolidated suite timing, startup measurement,
release integrity check and final responsive browser results here.
