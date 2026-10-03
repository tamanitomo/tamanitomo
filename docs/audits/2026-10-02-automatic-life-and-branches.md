# Branch consolidation and automatic-life review — 2026-10-02

Work is staged on `beta`; `main` remains the released v3.6.2 and `gh-pages`
remains the live website. No installed personal profiles were changed. The owner
authorized consolidation, backup, commit, push and removal of redundant branches.

## Recovery

Before changes, all refs were saved in a verified `git bundle --all` at the sibling
folder `tamanitomo-backup-20261002-202520/repository.bundle`. The folder also contains
original refs, branch divergence inventory, worktree status, staged/unstaged binary
patches and untracked files. Retired worktree directories are moved whole into its
`retired-worktrees` folder so ignored files are retained too. The root `uv.lock`
was already untracked and is left untouched.

Recover without altering this checkout: `git clone /path/to/repository.bundle recovery`.
The bundle has all old refs; consult `refs.txt` for the exact original tips.
The wheelhouse has an additional remote immutable tag, so its binaries are not
reliant solely on the local backup. Old installers' `git clone --branch
wheelhouse-aarch64` fallback accepts this tag; updated installers use its tag URL
directly. Website history is not merged into the software tree.

## Branch-by-branch disposition

| Original ref | Disposition |
| --- | --- |
| `beta` | Keep as development/integration branch, based on main. |
| `checkpoint/vault-link06-complete` | Already an ancestor of main; remove redundant branch. |
| `design/living-archive-vault` | Already an ancestor of main; remove redundant branch. |
| `feat/lightweight-chat-dock` | Superseded: main has 6ed5ed7 streaming dock and the newer inference/probe implementation. Older branch would regress transcript handling. |
| `feat/provider-failover-benchmark` | Superseded: main has companion_inference.py and isolated no-fallback model probes. Preserve untracked benchmark scripts/results in the external backup. |
| `fix/issues-2-4-fingerprint-and-fact-order` | Already an ancestor of main; remove redundant branch. |
| `fix/stuck-sleep-gate` | Merged into beta. Preserve wake recovery and concise presence transitions; additionally fix private-scene continuation and stale visual direction. |
| `gh-pages` | Retain unchanged as website branch, including CNAME and deployment workflow. |
| `identity-document-view` | Already an ancestor of main; remove redundant branch. |
| `main` | Retain unchanged at released/tagged v3.6.2 (ac92901). |
| `release/chat-journal-rc` | Already an ancestor of main; remove redundant branch. |
| `scrub/depersonalise` | Pre-publication history superseded by main’s initial public snapshot 4da31c6 and subsequent privacy/packaging corrections. Compared trees; do not restore the earlier private-beta configuration. |
| `settings-unification` | Already an ancestor of main; remove redundant branch. |
| `sleep-and-photo-cadence` | Already an ancestor of main; remove redundant branch. |
| `test/chat-trusted-cache-correction` | Already an ancestor of main; remove redundant branch. |
| `test/chat-trusted-read-integration` | Already an ancestor of main; remove redundant branch. |
| `test/journal-archive-review-corrections` | Already an ancestor of main; remove redundant branch. |
| `test/journal-day-archive` | Already an ancestor of main; remove redundant branch. |
| `test/persistent-chat-ui` | Already an ancestor of main; remove redundant branch. |
| `test/phase0-memory-correctness` | Only unique change is a historical CI results annotation: 7fef922 / run 35955872873, claimed five jobs passed. Preserve in bundle and this audit; do not restore removed historical report files. |
| `test/phase1-conversation-contract` | Already an ancestor of main; remove redundant branch. |
| `test/phase1b-02f2285-corrections` | Already an ancestor of main; remove redundant branch. |
| `test/phase1b-c1-core` | Already an ancestor of main; remove redundant branch. |
| `test/phase1b-c1-integration-closure` | Already an ancestor of main; remove redundant branch. |
| `test/phase1b-c1-public-output-closure` | Already an ancestor of main; remove redundant branch. |
| `test/phase1b-c2-dispatcher-safety` | Already an ancestor of main; remove redundant branch. |
| `test/phase1b-c3-keyed-client` | Already an ancestor of main; remove redundant branch. |
| `test/phase1b-c3-recovery-closure` | Already an ancestor of main; remove redundant branch. |
| `test/phase1c-continuity` | Already an ancestor of main; remove redundant branch. |
| `test/phase1c-provenance-guard` | Already an ancestor of main; remove redundant branch. |
| `test/vault-editor-safe-save` | Already an ancestor of main; remove redundant branch. |
| `test/vault-v1-v3-corrections` | Already an ancestor of main; remove redundant branch. |
| `ui-overhaul` | Already an ancestor of main; remove redundant branch. |
| `wheelhouse-aarch64` | Retain the complete commit as immutable tag wheelhouse-aarch64, including archive, individual wheels and license notice. Remove development branch. |
| `origin/claude/beautiful-hamilton-0f8m4p` | Superseded: main has LINK-03/04 in 89fd28a, LINK-05 in df1c294 and LINK-06 in feb8a49. Retain newer corrections. |
| `origin/claude/hopeful-lamport-oyjt8h` | Already an ancestor of main; remove redundant branch. |
| `origin/design/living-archive-vault` | Already an ancestor of main; remove redundant branch. |
| `origin/gh-pages` | Retain unchanged as website branch, including CNAME and deployment workflow. |
| `origin/main` | Retain unchanged at released/tagged v3.6.2 (ac92901). |
| `origin/release/chat-journal-rc` | Already an ancestor of main; remove redundant branch. |
| `origin/test/phase0-memory-correctness` | Only unique change is a historical CI results annotation: 7fef922 / run 35955872873, claimed five jobs passed. Preserve in bundle and this audit; do not restore removed historical report files. |
| `origin/test/phase1-conversation-contract` | Already an ancestor of main; remove redundant branch. |
| `origin/test/phase1b-c1-core` | Already an ancestor of main; remove redundant branch. |
| `origin/wheelhouse-aarch64` | Retain the complete commit as immutable tag wheelhouse-aarch64, including archive, individual wheels and license notice. Remove development branch. |

## Automatic surfaces reviewed

| Surface | Result |
| --- | --- |
| Pulse / sleep / morning / wind-down | Recover stalled undeclared sleep; preserve private continuations; clear sleep on actual activity changes. Independent plans may continue when the human returns. |
| Autonomy / independent work window | Carry ongoing interest notes and fictional friendships; vary activity invitations; creating and practice are first-class options. Actual research still requires sources. |
| Daily / weekly / monthly reflection | Keep tiered reasoning, evidence rules and fiction separation. Daily contact checks actual trusted messages in the day, not session creation dates. |
| Check-in / memory / hygiene | Existing evidence-backed memory flow retained; model routing follows selected tiers and configured fallback order. |
| Chat and gateway | Configured primary/ordered fallbacks; ChatGPT preset also writes native chat reasoning. Native gateway free bundles refresh through the adapter. |
| Native cron model pins | Hermes currently suppresses inherited fallbacks on pinned jobs. Explicit companion enrollment restores the user's configured chain through a bundled plugin without replaying turns. |
| Legacy structured script workers | One-click model application migrates recognized provider-pinned script jobs to native agents and backs up their prompts. |
| Quiet-hours drift | Opt-in behavior retained; only trusted, profile-scoped owner messages influence it. Cron prompts no longer count as human activity. |
| Session rollover | Existing two-hour idle gate and history retention remain. Shared-store reads and eligible chain tips are now profile-scoped. |
| Outbox / dispatch / voice messages | Existing quiet hours, expiry, user cap, permissions and deduplication remain. No new scheduled greetings or pressure to return. |
| Timeline and media cleanup | Existing privacy, sleep gating and retention remain. No-agent maintenance stays model-free. Image synthesis and live audio retain their separate modality configuration. |
| Sensors / vault / health watch | Existing deterministic maintenance retained. Health failures remain visible. |
| Usage | Native audit field compatibility fixed. Input/output shown separately; missing usage remains unknown. No spending cap added. |

## Validation and limits

The full Python suite, JS syntax, Black/Ruff, installer syntax and source ZIP build
were run locally. The Hermes adapter was loaded through real native plugin
discovery in a temporary profile and checked for configured fallback behavior and
unrelated-job isolation. No paid model calls or live companion activity were used
for these checks. Account/model availability remains subject to the connected
provider; no end-to-end output-quality claim is made.

Free-model quality ordering is a transparent preference heuristic filtered by the
live free/tool-capable catalogue, not a benchmark-backed universal ranking. A
catalogue outage retains the last good choices. Explicit final fallback routes
keep their position. Per-job overrides remain possible after a bulk preset.

The plugin uses Hermes's internal `_job_fallback_chain` and gateway loader seams;
future Hermes updates must revalidate those seams. Applying settings to an existing
installation requires the normal gateway restart to load the plugin. Existing
custom prompts and routines are not silently rewritten.

Several files also received Black-only formatting needed by the existing CI gate.


The first CI pass also exposed Windows failures in existing tests: two source
reads used the Windows default encoding, SQLite test fixtures left connections
open, and the asset digest cache trusted same-size rapid-write timestamps that
are not sufficient on Windows. Fixtures now close connections explicitly and
read UTF-8; Windows asset versions hash their actual bytes. These corrections
were made before completing the beta handoff.
