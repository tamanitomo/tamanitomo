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

## Phase 2 — portable hosts

- Shared standard-library network, memory and process probes across entry points.
- Native Windows process checks never use `os.kill(pid, 0)`; Unix-only locks and
  process groups remain guarded. Linux start-time identity checks are optional:
  unavailable process metadata is reported as unknown, not as a dead process.
- Native RAM measurements use sysconf, macOS tools or Windows APIs. Missing
  measurements are marked unknown instead of inventing host capacity.
- Bootstrap/update locks no longer grow on every launch. Hosted bindings support
  IPv6; launchers preserve paths with spaces and Unicode. Git records platform
  line-ending rules.
- Verification: 71 platform, launcher, gateway, installer and chat checks pass;
  POSIX launcher `--help` succeeds in 0.354s with a temporary home.
- Native Windows/macOS execution remains a CI responsibility; local tests exercise
  their branches with controlled adapters.
