# Continuity and recovery acceptance — October 9, 2026

Development and verification took place on `beta`. All application testing used
invented companions, temporary homes and temporary vaults. No real companion
memory was exercised and no chat or outreach message was delivered.

## Browser checks

Using the synthetic preview in the Codex browser:

- Answered the first onboarding question, refreshed, resumed at the next question,
  completed the interview and created a companion with scheduled model work paused.
- Searched the trusted chat history for “Tea” and opened the surrounding exchange.
  Checked the new search controls at a 390-pixel phone width.
- Added a dated camping absence with an explanation and verified it appeared in Us.
- Confirmed unrecorded Home presence fields use unknown/empty labels.
- Downloaded a complete synthetic backup, uploaded it into the integrity preview,
  restored into separate new folders and opened the restored companion. Its trusted
  Telegram, app and terminal conversation history remained available.
- Added a synthetic incoming Telegram database row while the restored dock held an
  unsent draft. Bringing the workspace into view refreshed the new message and
  preserved the draft. No chat submission was made.

The recovery form initially triggered the general unsaved-settings guard. Recovery
inputs now remain outside that guard; the corrected restore-to-open flow passed.
Disposable browser tabs, downloads and preview data were removed afterward.
CLI backup, inspect and restore also passed with a disposable profile; the restored
configuration had `cron_active: false` and `outreach: never`.

## Actual Hermes compatibility

The isolated compatibility probe passed ten checks against Hermes commit
`bddd22be7c2e5f7630c3d90507e6e7280ff092e3`, using the installed managed Python 3.14.7:

- Actual plugin discovery and context engine registration.
- Native cron and gateway fallback paths, preserving ordering, endpoint credentials
  and individual overrides.
- Seven native no-agent maintenance jobs, without constructing an agent.
- Generated pre-LLM continuity and owner-only session-end reflection hooks.

The probe blocks network and writes outside its temporary profile. It made zero
model calls and sent zero messages. The pinned GitHub Actions workflow is included;
remote CI execution is separate from this local check.

## Six simulated days

The continuity harness advances a synthetic clock through a shared rain-gauge
project, an actual local calculation and saved output, a kept promise, rupture and
repair, an explained field-course absence, a simulated provider outage, restart,
independent fictional moth-sketchbook progress and a cross-channel return.

Ten deterministic assertions verify saved state and evidence, including exclusion
of an unrelated sender, no unexplained absence penalty during the course, no replay
of completed work, and separation of fictional life from facts about the human.
The optional frontier dialogue run and its limits are documented in
[TESTING.md](../TESTING.md). This is a simulated-clock acceptance test, not proof of
six days of unattended device uptime or autonomous tool choice.

## Frontier dialogue

Five tool-free replies through the installed Hermes runtime and
`openai-codex / gpt-5.6-sol` completed with one API call each. Provider-reported
usage totaled 18,412 input and 452 output tokens. Review against the saved rubrics
found the replies recognized the shared project, grounded saved calculation work
in its receipt, retained the recorded repair, accepted explained time away without
reply pressure, and resumed the app's next step from Telegram while keeping the
companion's fictional project separate. The initial reply computed the simple
arithmetic in prose but did not claim the later saved file existed yet.

The first runtime import exposed a test-harness isolation defect: Hermes bootstrap
treated the temporary home as a new installation. It rewrote two ignored
source-local launchers to a temporary Python path, refreshed generated web/TUI
bundles and the install stamp, and fetched upstream tags. Both launcher paths were
restored to the existing installed Python and verified with a guarded, offline
CLI version check. Hermes HEAD stayed at the reviewed commit and its tracked
worktree remained clean. No original hashes existed for the ignored generated
bundles/stamp, so exact restoration of those bytes is not claimed; fetched Git
objects/refs were retained. No real companion memories or message delivery were
used.

The harness now disables installation/bootstrap side effects and installs a write,
subprocess and credential-read guard before importing Hermes. Regression tests
exercise those boundaries. Earlier startup failures retain unknown usage rather
than reporting zero, and no alternate provider was tried. The successful live run
used the bootstrap suppression; the final enforced guard was checked afterward
without additional model calls.
