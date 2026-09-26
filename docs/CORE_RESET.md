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

## Phase 3 — inference recovery

- Added a shared ordered provider cascade for pulse/reflection workers, with
  transient HTTP and timeout handling, per-route credentials, and local fallbacks.
- Wired the same configured backups into Hermes's native chat recovery loop;
  local Ollama/LM Studio aliases use its custom endpoint adapter. No whole-turn
  retries or duplicated tool actions are introduced.
- Made the model probe test one route only, preserving saved files and credentials.
- Focused worker/configuration/reflection/model checks pass (114 cases in 2.58s);
  dedicated probe/fallback tests cover transient statuses, timeouts, permanent
  errors, empty chains, local-only consent and credential isolation.
- Also exercised the installed Hermes runtime against a synthetic local HTTP
  provider: a primary HTTP 500 switched to the fallback, returned exit code 0,
  streamed six deltas and produced the clean final reply. This used temporary
  homes and fixture tokens, with no live provider requests or user-data changes.

## Phase 4 — readable code and explicit rules

- Formatted all 109 Python modules in `kit/scripts`, `kit/cli` and `kit/app`, plus
  launch/update entry points. Expanded chained statements and split compound
  imports. Black and focused Ruff rules now have reproducible dev dependencies
  and a CI check.
- Verified the formatting pass has identical executable ASTs after normalizing
  import grouping and excluding docstrings. The representative 300-test domain
  run passed in 3.75s.
- Added module-level explanations and `ARCHITECTURE.md` for deterministic limits,
  evidence-backed memory and the six zero-inference maintenance routines.
- Follow-up review repaired three inference edge cases before consolidation:
  endpoint credential isolation, native Anthropic routing, and transient failure
  during schema correction. These behavior changes have separate regressions.
