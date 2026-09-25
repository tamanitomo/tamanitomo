# Release status: Chat/Journal release candidate

This is the one maintained release and blocker register for the Chat/Journal candidate. Update rows in
place. Do not add parallel lists. Last pass: 2026-09-25, one bounded release-preparation pass. Nothing
was pushed, tagged, merged, version-bumped, published or installed. No live profile, model, platform
or dispatcher was exercised.

## 1. Candidate identity

| | SHA | Notes |
|---|---|---|
| Public base (`origin/main`, fetched read-only) | `e28197c` | Release 3.0.24. Local `main` is the same commit. It is an ancestor of the candidate, which is linear with 59 commits on top and no origin changes to integrate. |
| Installed application on the first host | 3.0.24 | Its `SHA256SUMS.json` equals a rebuild of `e28197c` (280 files, **0 modified**). The install also has 9 unmanaged leftover files that are not in any manifest (see PKG-03). |
| Accepted tested code | `dc14b0c` | Journal J1/J2 closed. |
| Accepted documentation/evidence head | `c9292cf` | Report-only relative to `dc14b0c`: 12 files, none in `release-files.json`. |
| **Integrated/tested candidate** | **`754d9d6`** | Branch `release/chat-journal-rc` = `c9292cf` + one packaging-test correction (PKG-05). |
| Report-only on top | the commit adding this file | Adds this register and `docs/release_rc_evidence/`, neither of which ships. |

The owner's `stash@{0}` (WIP on `main`: LAN model endpoints for the local pulse and reflection) and the
`test/*` branches are untouched. The stash is **not** in the candidate or the installed app.
`VERSION` is still `3.0.24`: the version bump is REL-01.

**Artifact:** `build/tamanitomo-release.zip` built by `tools/build_release.py` from `754d9d6`:
296 source files plus the integrity manifest, sha256
`b22ca2ebcbe999f48f3d66df5a91f210c984966b857be4626ba5e980d18b1fc8`. The build is deterministic: two
independent builds gave the same hash. **Rollback artifact:** `build/tamanitomo-3.0.24-rebuilt.zip`
(sha256 `1aedf44d…8a6a91`), whose manifest equals the installed one. The published v3.0.24 GitHub
asset is the other source.

## 2. First host and runtime (from environment metadata, not exercised)

- **OS:** the owner's primary Linux host (CachyOS, kernel 7.2), x86-64.
- **Launch:** a systemd **user** unit (`deploy/companion-workspace.service` shape) runs
  `<app>/.venv/bin/python -m kit.app.hosted` from an extracted release directory. The app venv is
  Python 3.14.7. The unit binds loopback plus a private tailnet address behind a reverse proxy, with
  `UMask=0077`.
- **Hermes:** Agent v0.21.1, git install. Its HEAD is exactly `0e9fc2cc15`, the Phase 1B pin, so the
  C1/C2 pinned-lane evidence applies to the Hermes actually installed.
- **Profiles:** the default Hermes home and one named profile. Each has an **outbox dispatcher cron
  (`*/5`) that runs `kit/scripts/companion_dispatch.py` directly from the installed app directory**.
- **Update path:** either the owner extracts a release ZIP over the app directory and restarts the
  unit, or the in-app updater stages the GitHub `latest` release (published only by `release.yml` on a
  `v*` tag) and applies it at the next launcher start. The updater refuses modified managed files and
  unmanaged files at incoming paths, and keeps 3 backups in `.update-backups/`.
- **Not claimed:** Windows, macOS, Android/Termux and any other host.

## 3. What the packaged candidate enables and executes

| Feature | In the ZIP | State after install | Evidence |
|---|---|---|---|
| Journal Day \| Reflection archive (`journal_archive.py`, `journal.js`, date routes) | yes | **on**; read-only GETs | packaged smoke: historical Day/Reflection, back/refresh, shared date link, Timeline link, pin and diary link, profile isolation |
| Existing Chat (`POST /api/chat` → `hermes chat --oneshot`) | yes | **on, unchanged**. The only edits are two `window.KeyedChat` guards and row-id attributes | packaged smoke: legacy send round-trip (fake Hermes), no `KeyedChat`, draft kept across Journal/Timeline/back/reload |
| Phase 1A read routes (`/api/chat/snapshot\|history\|changes\|sources`) | yes | **registered** (authenticated); the flag-off page never calls them. A call writes a projection SQLite under the app-state dir | gate; ACT-02 affects them |
| Persistent Chat UI, keyed sends (`chat_sends`, `chat_send_routes`, `send_*`, `chat-*.js`, `chat.css`) | **no** | absent. No shipped entry point passes `chat_sends=` | packaged smoke: the 5 assets return 404; no keyed signal in the page |
| Trusted reflection (`--trusted-sources`), cross-channel handoff (`TAMANITOMO_DEV_CROSS_CHANNEL_HANDOFF=1`) | code yes, dependency no | **off** (development options; not set on the first host) | PKG-02: in the package `owner_evidence` raises `ImportError` |
| **C2 dispatcher** (`companion_dispatch.py`, `companion_outbox.py`, `companion_outreach.py`) | yes | **runs** from the next cron tick after install. **Not gated by any keyed flag** | C2 tests in the gate; ACT-04 procedure below |
| Context hook, Phase 0 memory (`companion_self.py`), local reflection | yes | run by Hermes hooks and crons, as accepted in Phase 0/1C | gate |

## 4. Readiness decisions

| | Decision | Supported scope | Blocking IDs |
|---|---|---|---|
| **A.** Publish the accepted source branch without live activation | **READY** | Push `release/chat-journal-rc` (or the accepted `test/*` heads) to `origin` **without a tag, merge or release**. That runs `test.yml` (CI only, `contents: read`). `release.yml` runs only on `v*` tags. The updater reads only the `latest` release, so no install changes. The pre-push leak guard must pass. | none |
| **B.** Release Journal with the existing production Chat | **NOT READY until owner steps, no code blockers** | Linux first host, installed with the quiescent procedure (§6). Journal on, legacy Chat, keyed sends absent, **C2 dispatcher live**. | REL-01, REL-02, CI-01, OWN-01 |
| **C.** Release persistent Chat with its live keyed send path | **NOT READY** | Could at most be Linux-only (non-Linux sends refused in code). | ACT-01, ACT-02, ACT-04, PKG-01, PKG-02 (plus B's items) |

B is a fallback, not a silent downgrade of C. The combined product (C) remains blocked on the
activation items below.

## 5. Register

Status values: **OPEN** (blocks the listed decision), **PROCEDURE** (closed by an owner-executed step
defined here), **SCOPED** (an enforceable exclusion holds), **NON-BLOCKING**, **CLOSED**.

### Activation (C)

| ID | Status | Affects | Evidence / executor | Smallest closure condition | Next responsible action |
|---|---|---|---|---|---|
| ACT-01 | **OPEN** (C) | keyed sends, Linux | `Phase1B_C1_ActivationReadiness.md` §4: after an executor hard-kill during a tool, the send settles `quiescent`, lease 0, **tool still alive**. The pinned local terminal starts tools with `start_new_session=True`. Hermes `background: true` processes and `os.setsid()` children survive a `complete` send. Measured on the pinned Hermes (C1 executor). One containment problem: graceful cleanup does not solve it. | The lease is released only when **every** process started for the attempt, including new sessions and background children, is proven gone, **or** such sends are refused. The two pinned-lane cases (`test_executor_killed_during_a_tool_leaves_the_tool_running`, `test_tool_descendants_escape_the_managed_group`) must flip to "no survivor / lease held". | Owner assigns a containment task. **Proposal, not accepted:** a per-attempt transient systemd user scope (`systemd-run --user --scope`), with quiescence = its `cgroup.procs` empty and kill = `cgroup.kill`, and sends refused where cgroup v2 user delegation is unavailable. Needs design review first. |
| ACT-02 | **OPEN** (C); latent in B | Phase 1A reads, keyed sends | Same report §4: after real CLI compression, the owner row reads as deleted and the copies read as new public messages (including an owner-text copy read as uncorrelated owner speech). This affects any compressed session. Phase 1C filtering and R1 refusal do not establish canonical history. | Reads keep the original message identity after an in-place rewrite, using **recorded** copy→original provenance bound to fingerprints (the executor already classifies `rewrite_copy`). Sessions without that provenance are labelled "rewritten; history not canonical". No text matching. | Owner assigns a compression-lineage task, separate from ACT-01. In B no UI calls these routes, so this is not a B blocker. |
| ACT-03 | **SCOPED** (Linux-only C) | platform claim | Linux supervision is observed on this host with the pinned Hermes (C1/C2 lanes; failures are ACT-01's). `send_quiescence.platform_supported()` refuses non-Linux, no `fcntl`, unreadable `/proc` and `hidepid`. O-8 (Windows), O-9 (Termux) and O-11 (macOS) were not observed. **Termux runs Python 3.11 with `sys.platform == 'linux'`, so its refusal depends on `/proc` hidepid detection**, which was never observed on a device. | C claims Linux desktop hosts only. Other platforms need native evidence before any claim. | For a Termux claim, first observe the refusal on a device with a synthetic profile. Not needed for a Linux-only C. |
| ACT-04 | **PROCEDURE** (B) / **OPEN** (C) | dispatcher; keyed sends | C2 §4 item 5 / §5: an old and a new dispatcher on one life directory is unsupported. A pre-C2 dispatcher with a pre-claim snapshot **sends again** (pinned by `test_a_running_pre_1b_dispatcher_is_not_excluded`). Pre-1B outbox rows fold and dispatch correctly. For C, foreign writers (terminal, gateway, Telegram) on the same Hermes session have no lease guarantee (O-5 is not relied on). | **B:** follow the quiescent install in §6 (pause both dispatcher jobs, wait for no running dispatcher, install, then resume), and state it in the release notes (REL-02). **C:** a stated supported-writer boundary, plus a refusal or detection for a foreign write during a keyed attempt. | B: owner follows §6. C: include the boundary in the C activation design. |
| ACT-05 | **SCOPED** | Chat provenance | `chat_sources.capabilities()` reports "proactive delivery provenance: unsupported". No join by text or time; the Hermes mirror row carries no outbox id. | Keep the exclusion; claim no exact linkage. | Follow-up REL-05 (stale reason text), non-blocking. |

### Release integration, packaging and CI

| ID | Status | Affects | Evidence / executor | Smallest closure condition | Next responsible action |
|---|---|---|---|---|---|
| PKG-01 | **OPEN** (C only) | C packaging | `release-files.json` excludes `chat_sends.py`, `chat_send_routes.py`, `send_executor.py`, `send_protocol.py`, `send_quiescence.py`, `chat-{store,sends,view,controller}.js` and `chat.css`. `kit/app/hosted.py` never passes `chat_sends=`, so a package cannot turn persistent Chat on. This is intended for B and a gap for C. | An explicit, default-off enablement in the shipped entry point, those files in the manifest, and a packaged test that the flag-off page is unchanged. **Only after ACT-01/02.** | Part of the C activation task. |
| PKG-02 | **SCOPED** (B) / **OPEN** (C) | trusted reflection, handoff | `chat_sources.owner_evidence()` imports `chat_sends` when no provenance is passed. In the extracted package this raises `ImportError`. With the handoff env on, every turn would show "could not be checked (ImportError)", and `--trusted-sources` would fail. Both are development options, off on the first host. | **B:** these options are not claimed and stay off. **C:** ship the read model (`chat_sends`, `send_protocol`, `send_quiescence`) with PKG-01, and add a packaged-tree test that `owner_evidence` reads. | With PKG-01. |
| PKG-03 | **NON-BLOCKING** (pre-existing in 3.0.24) | shipped tests | Run inside the extracted ZIP, `tests/test_audit_2026_09_23.py::KeepsakeTruthTests` fails (`companion_keepsake` not shipped) and `test_installers.py::…termux_compatibility_entrypoint…` fails (`kit/scripts/setup-termux.sh` not shipped). Both fail the same way in the 3.0.24 package. `release.yml` tests the checkout, not the ZIP. | Stop shipping those two tests, or ship the modules. **Adding `companion_keepsake.py`/`icon_*.png`/`setup-termux.sh` to the manifest would make the updater refuse on hosts that carry them as unmanaged leftovers** (the first host has all 9). | A later release. Move the leftovers aside before shipping those paths. |
| PKG-04 | **NON-BLOCKING** | shipped tests | C2's `tests/test_dispatch_claim.py` and `tests/phase1b_c2/`, `tests/fixtures/phase1b_pre_c2/` are not in the manifest. The dispatcher ships without its tests. | Add them when convenient. They run in CI from the checkout either way. | A later release. |
| PKG-05 | **CLOSED** in `754d9d6` | shipped tests | `tests/test_preview_fixture.py` ships, but its persistent-Chat case imports unshipped keyed modules: 1 packaged failure introduced by the branch. It now skips in a package, stating why, and still runs in source/CI. | done | — |
| REL-01 | **OPEN** (B) | release | `VERSION` 3.0.24; `docs/RELEASE_NOTES.md`/`CHANGELOG.md` describe 3.0.24. `release.yml` requires tag = `v$(cat VERSION)`, and the updater compares versions. | A bump commit (e.g. 3.1.0) with rewritten release notes, on the candidate. | Owner authorizes; see §7 commands. |
| REL-02 | **OPEN** (B) | release notes | C2 requires "stop the old dispatcher first; to be stated in release notes". The in-app updater does not pause crons. | Release notes state the pause/resume of dispatcher jobs around an update. | Include in REL-01's notes. |
| CI-01 | **OPEN** (B), for the exact SHA | CI | **No CI has run on `754d9d6`** (nothing pushed). Local only: release gate as in `release.yml` (pytest with `hermes` off PATH, then `node tests/test_updates_ui.js`, then the build): **1833 passed, 52 skipped (all "pinned Hermes not configured"), 0 failed, 640 subtests**, Node OK, on Python 3.14.7/Node 26.7.0. `release.yml` uses Python 3.13; `test.yml` covers 3.11/3.13/3.14 plus Windows/macOS smoke. Earlier runners caught real failures. | A green `test.yml` run on the pushed candidate (or bump) SHA before tagging. A green `release.yml` on the tag. | After A's push. |
| ENV-01 | **NON-BLOCKING** (host) | local testing | The host's `/tmp` tmpfs is full. `test_workflows…download_checks_hash…` fails without `TMPDIR` elsewhere (it also fails on 3.0.24). The gate used a job-local `TMPDIR`. | — | Owner housekeeping. |
| OWN-01 | **OPEN** | all | Push, tag, merge, publish and install need explicit owner approval. | Owner decision on A/B/C scope. | Owner. |

### Observations (not findings)

- **OBS-01.** In the first packaged-smoke run, text typed right after `#chat-message` appeared (before the
  legacy feed load finished) was not retained after navigation. The legacy handler is attached after
  `await loadFeed()`, and then sets the box from `sessionStorage`. The rerun did not reproduce the loss,
  so this is unconfirmed and timing-dependent. The same code is in 3.0.24, so it is not a candidate
  regression. The persistent-Chat store is not affected (it is not in B).

### Accepted limitations (retained, not blockers)

- **N1**: the handoff cap counts quoted lines only. **N2**: an exhausted 400-row scan silently omits the handoff. Both only when handoff is on (it is off).
- Journal (`JournalDayArchiveResults.md`, "Known limitations"): catalog walk per Day request; malformed life lines are skipped silently; the Reflection photo strip is date-based; only `plans/<date>.json` is shown; "You two" needs ISO `happened_on`; tab switches replace history; full-page screenshots and the fixed bar; Timeline parity gaps in `docs/JOURNAL_ARCHIVE.md`. Timeline is not retired.
- C2: Windows run lock is unobserved; `PRE_PLATFORM_ERRORS` is empty (all errors `unknown`); `unknown`/`reservation_unresolved` need the owner; torn outbox lines are skipped.

### Closed and accepted (for reference)

J1, J2 (Journal); cache correction (`b7b57ec`); Phase 1C and R1 fail-closed provenance (`62c223b`);
projection; C1 F1–F3; C1 public-output R1–R4; C2 dispatcher safety with U1/T1; C3 and its recovery
closure; persistent Chat UI milestone; trusted Chat integration, including the earlier `latest_session`
→ gateway-session issue (the continuation endpoint now names the eligible session). O-12's continuation
note is handled by R1's fail-closed evidence.

### Historical follow-ups (recorded earlier; not re-verified in this pass, not claimed fixed)

- REL-05: the `proactive delivery provenance` reason text still says the outbox records no platform id (C2 §6).
- `companion_outreach.send()` remains a direct `hermes send` path with no in-repo caller, which bypasses the outbox (C2 §6).
- `companion_watch.py` alerts go through `hermes_send()` outside the outbox, by design (C2 §6).
- Updater: installs over hand-patched live files are refused by design; unmanaged leftovers block shipping those paths (PKG-03).

## 6. Install and rollback runbook (first host, B scope)

Exercised on a disposable fixture (`docs/release_rc_evidence/exercise.py`,
`install-rollback-exercise.json`). The fixture installed the rebuilt 3.0.24 with two unmanaged
leftovers. The **installed 3.0.24 updater code** staged the RC and `apply_pending` applied it: 296
files, 0 modified. Rollback restored `.update-backups/<id>`: 280 files, 0 modified, no RC-only files
left. The leftovers and a synthetic profile (including a ledger file) were byte-identical throughout.
Not run against live data.

**Install (quiescent):**

1. Record the previous artifact: `cat <app>/VERSION` and keep a copy of `<app>/SHA256SUMS.json`. The
   previous ZIP is the v3.0.24 GitHub asset or `build/tamanitomo-3.0.24-rebuilt.zip`.
2. Back up data, and do not modify it: the Hermes home(s) including `profiles/`, the vault, and the app
   state directory (`TAMANITOMO_APP_STATE`).
3. **Stop old writers.** Pause both outbox dispatcher jobs (`hermes cron pause <id>` for each profile)
   and any other job whose script lives in `<app>/kit/scripts`, if you want a fully quiet window. Wait
   until `pgrep -f companion_dispatch` is empty. Then stop the workspace:
   `systemctl --user stop companion-workspace.service`.
4. Install: extract the ZIP's `tamanitomo/` prefix over `<app>`, preserving modes. Or use the in-app
   updater and relaunch. Verify that every entry of the new `SHA256SUMS.json` matches, with 0 modified.
5. `systemctl --user start companion-workspace.service`, then open Journal and Chat once.
6. Resume the dispatcher jobs (`hermes cron resume <id>`).

**Rollback:** repeat step 3. Restore the previous code: either the updater's `.update-backups/<id>/`
(copy each file in its old `SHA256SUMS.json` plus the manifest back, then delete the files the RC
added: `kit/app/chat_projection.py`, `chat_routes.py`, `chat_sources.py`, `journal_archive.py`,
`static/journal.js`, `docs/TESTING.md` and the added tests), or extract the 3.0.24 ZIP over a
**fresh** directory and point the unit at it. Verify, then do steps 5–6.

**Ledger and reset implications (B):** B creates no send ledger (keyed sends are absent). The only new
state is the Phase 1A projection SQLite under `<app-state>/chat/`, and only if those routes are called.
3.0.24 ignores it, and deleting it is safe (it is a rebuildable cache). C2 adds attempt fields to outbox
lines. Pre-C2 `fold()`/`waiting()` read no C2 phase or outcome as `queued` (C2 M-20d), so 3.0.24 after a
rollback does not re-send recorded attempts. An entry C2 left `unknown` or mid-attempt is not retried by
3.0.24 and needs the owner's review. The duplicate-delivery risk is an old and a new dispatcher
**running at the same time** (ACT-04), so install and roll back only in the quiescent window from
step 3. For C (later), the send ledger lives in each profile home, and a ledger reset records lost
continuation-note provenance, after which trusted evidence reads fail closed (R1).

## 7. Proposed commands (NOT executed; owner approval required)

A, publish source (CI only, affects no install):

    git -C <repo> push origin release/chat-journal-rc
    # the pre-push leak guard runs; test.yml runs on the pushed SHA

B, release (after A is green and REL-01/02 are committed on top of the candidate):

    # on release/chat-journal-rc: bump VERSION, rewrite docs/RELEASE_NOTES.md (+ REL-02 text), CHANGELOG
    git commit -am "Release 3.1.0: Journal Day | Reflection archive; dispatcher safety"
    git push origin release/chat-journal-rc          # CI on the bump SHA
    git checkout main && git merge --ff-only release/chat-journal-rc && git push origin main
    git tag v3.1.0 && git push origin v3.1.0          # release.yml: tests, build, gh release --latest

Pushing the tag publishes GitHub **stable/latest**. Every install's in-app updater will then offer it,
on every platform the installers support, not only the first host. Install on the first host by §6.

C: no commands. It is blocked.

## 8. Smallest next implementation tasks for blocked paths

1. **ACT-01 containment** (separate branch; design review first): per-attempt containment that covers
   `setsid`/background descendants, lease release gated on proof that it is empty, refusal where the
   containment is unavailable. Flip the two pinned-lane cases.
2. **ACT-02 compression lineage**: recorded copy→original provenance and non-canonical labelling, with no
   text matching.
3. Then **PKG-01/02 + ACT-04 (C)**: default-off shipped enablement, manifest additions, packaged-tree
   tests, the foreign-writer boundary.

Vault editor/safe-save work proceeds on its own branch and stays out of this candidate.
