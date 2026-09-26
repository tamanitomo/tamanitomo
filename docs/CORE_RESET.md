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

## Phase 5 — seven focused suites

- Consolidated coverage into the seven requested domain files, retaining 291
  tests and 29 subtests for boundaries, persistence, concurrency, streaming,
  platform behavior and inference recovery. Shared fixtures contain no tests.
- Removed obsolete review snapshots, historical evidence bundles and tests for
  the retired chat architecture. Release manifests and CI use the current suites.
- Default test homes are isolated from real Hermes and user directories. The six
  maintenance wrappers have a regression check that rejects model invocation.
- Verification: the full suite passes in 4.21s; collection takes 0.19s. Python
  compilation, diff checks and the release archive build succeed. No tracked
  references to the deleted chat modules remain.

## Phase 6 — five destinations and responsive polish

- Home, Journal, Vault, Photos and Settings are the only primary destinations on
  desktop and mobile. Relationship, timeline and calendar views belong to Home;
  companions, identity and studios belong to Settings. Auxiliary routes retain
  direct links, parent navigation, back controls and keyboard focus.
- Unified dialog, photo viewer and dock surfaces with the theme tokens. The open
  mobile dock sits above navigation, and its header explicitly keeps a horizontal
  layout. Unknown hardware memory stays unknown in onboarding.
- Fixed expanded vault folders appearing empty before their contents were loaded.
  Only the visible expanded subtree is loaded, with a fixed bound and retry UI for
  failed reads. Browser checks covered note editing, saving, wikilinks and outline.
- Final review corrected IPv6 browser-launch URLs and included `pytest.ini` in the
  release archive, so shipped tests run with the same import configuration.
- Updated current onboarding, desktop, model and testing documentation to match
  the dock, five destinations and single-provider dry-run probe.

## Six-phase acceptance evidence

- **296 tests and 29 subtests pass in 4.24s**, across exactly seven domain suites.
  The same tests pass from an extracted release archive in 4.38s. Both runs emit
  one upstream Starlette/httpx deprecation warning and have zero failures.
- Fresh-process imports plus workspace construction: **0.282s**. Starting the
  hosted process and receiving the first authenticated feed response: **0.339s**.
  These are local measurements with synthetic homes, not a hardware-independent
  performance guarantee.
- Chromium at **1440 × 900** and **390 × 900**: five navigation destinations,
  eight auxiliary routes, legacy chat deep link, vault editing, draft persistence
  and profile isolation pass without page errors or primary-page overflow.
  Desktop dock measures 390 × 580; phone sheet measures 390 × 585 (65vh).
- Real preview chat requests survive navigation and a deliberately dropped SSE
  connection. Recovery, including a browser reload, uses the existing operation
  with exactly one POST per turn. Light/dark dock and dialog screenshots were
  visually inspected after theme transitions settled.
- Black checks all 111 production/launcher Python files; focused Ruff rules,
  Python compilation, browser-script parsing, shell syntax and diff checks pass.
  Release build contains 238 source files plus its integrity manifest. No tracked
  references to the removed chat modules or retired ledger remain.
- Native Windows/macOS runners were not available locally. Their platform
  branches have controlled tests, and CI is configured to run all seven suites on
  Linux, Windows and macOS. Actual provider failover was exercised only against
  synthetic local endpoints; no live provider calls or user-data migrations were
  needed.

Each phase is committed separately. All preview homes and vaults were temporary;
existing user Hermes profiles and vaults were left untouched.

## Version 3.6.0 release integration

The release also incorporates the published main branch and its subsequent Vault
work. It preserves CodeMirror note tabs, autosave, recovered drafts and exact-byte
backups, and includes the link index, backlinks, safe embeds, properties and
link-aware file actions. Root-folder refresh invalidates child caches so a rename
appears immediately. File-action checks reject symlinks and case collisions.

Updater integration uses the actual Hermes root, pauses only enabled dispatch
jobs, and aborts on a failed pause, an unreadable process list or a running-process
timeout while restoring already-paused jobs. Windows rollover preserves its host
environment and locates `python.exe`. CLI and application versions share `VERSION`.

Release validation: **313 tests and 29 subtests pass in 4.81s**, with the same seven
domain files and one upstream deprecation warning. Black checks 112 Python files;
Ruff and the reproducible editor-bundle build pass. The release manifest includes
242 source files plus its generated integrity manifest. A fresh synthetic browser
check at 1440px and 390px verifies the merged editor, autosave/reload, backlinks,
rename and inbound-link rewrites, navigation and one-POST chat during navigation,
with zero JavaScript errors. No existing profiles or vaults were used for testing.
