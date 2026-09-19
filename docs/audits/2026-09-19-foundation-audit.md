# Tamanitomo foundation and product audit

Date: 2026-09-19. Scope: the current self-hosted application, formerly companion-kit, and the public tamanitomo/tamanitomo repository. This is not the archived E2EE hosted service.

## Assessment

The product has a substantial foundation: durable local records, separate companion profiles, evidence-aware memory, enforced contact limits, recoverable operations, and a shared backend for the browser and CLI. Its main weakness is the distance between those capabilities and a dependable, understandable first experience. There are more controls than a new owner can confidently configure, and some reassuring UI messages previously described successful intentions rather than successful operations.

The right near-term investment is completing the path from installation to a working conversation, a remembered detail, and one deliberate background interaction. Adding more companion subsystems before that path is reliably repeatable will increase the support burden.

The owner confirmed deployments on Android, Windows, Linux, and macOS. All four remain supported. This audit distinguishes those deployments from the checks reproduced here; it does not downgrade support because only Linux is available in this environment.

## Intent and implementation

| Intended experience | Evidence in the implementation | Assessment |
| --- | --- | --- |
| A companion whose continuity belongs to its owner | Local vault, identity documents, JSONL ledgers, profile-scoped state, backup and restoration paths | Strong architectural fit. Local storage is not application-level encryption. |
| A life that continues outside chat | Presence, day, lifestyle, journal and scheduled context; gateway and outbox integration | Substantial implementation. Depends on an awake host, installed runtime, enabled schedules and functioning inference. |
| A companion that can also help with practical work | Hermes runtime and tools, model routing, terminal and dashboard integration | Strong differentiation. Tool success must remain distinct from authored life and mood. |
| Meaningful relationship development | Contextual feelings, expected absences, experience records, corrections, intimacy progression | More than decorative UI. Numerical baselines and heuristic thresholds should be explained as modelled state, not measured human emotions. |
| A welcoming setup for ordinary users | Browser onboarding, installers, saved presets, local model setup | Previously undermined by broken frontend request contracts and setup ambiguity. Improved in this pass; operational readiness still needs a clearer product definition. |
| An imaginative personality discovery experience | Story choices and personality archetypes | Preserved and revised. Twelve short adventure scenes suggest personality; direct questions control pace, contact and relationship. |
| One understandable place for configuration | Settings plus studios and Hermes administration | Improved grouping and progressive disclosure. Voice now has one configuration editor. Specialist tools remain available. |

## Confirmed defects corrected

### Access and configuration

- **Workspace PIN bypass across profiles.** The request guard previously checked the default selection before request-specific selection was established. A PIN saved on another profile could therefore leave the default route open. Access policy now belongs to the workspace, with a shared `.tamanitomo-access.json`, legacy PIN discovery, consistent CLI management, and cross-profile regression coverage. Conflicting legacy PINs require a local reset rather than choosing an arbitrary unprotected profile.
- **Fail-open access handling.** An exception while reading PIN configuration previously fell through to the request. Remote requests now fail closed. Login and header-based PIN attempts share a bounded attempt limiter.
- **Installer PINs were not installed.** Both setup scripts accepted and reported a PIN without persisting it. They now write the workspace access configuration before normal service startup. Linux service-only setup also applies the PIN before selecting a network bind.
- **Network page could show the wrong port.** It now uses the requested/configured port instead of only a generic `PORT` fallback.
- **PIN disclosure in CLI output.** Setting a PIN no longer prints the PIN. The test now verifies the saved access state and absence of the value in output.

This remains a single-owner administrative application. A four-digit PIN does not encrypt traffic or make a raw public HTTP endpoint suitable for internet exposure. Existing authenticated reverse-proxy deployment remains a separate supported arrangement.

### Installation and release

- **Piped Linux setup was not safe for interactive input.** The advertised `curl | bash` path could lack `BASH_SOURCE[0]`, and prompts read script input. Installer prompts now use a separate controlling-terminal descriptor. Unattended execution requires the explicit noninteractive option.
- **Dry-run side effects.** Linux dry-run now exits before provisioning; Termux dry-run skips the upgrade path, wake lock, directory creation in its test prefix, and Telegram validation request.
- **Destructive Termux configuration rewrite.** Existing `config.yaml` is preserved instead of being replaced with a small installer-generated configuration. The later duplicate model rewrite was removed.
- **Unsafe interpolated Python and credential editing.** Paths/model values now reach Python as arguments; environment values are encoded rather than interpreted as `sed` replacements. A provision test uses a path containing both spaces and an apostrophe.
- **Hidden failures.** Required application dependency installation and selected Hermes/git upgrade steps now surface failures instead of printing completion after swallowing them. Best-effort Android integration steps still exist; see the acceptance matrix below.
- **Misleading no-service instructions.** Linux setup now prints the command needed to start the workspace when no background service was started. A missing Hermes runtime is described as a remaining requirement for conversation.
- **Broken source release.** The manifest named a missing `.github/workflows/test.yml`. The workflow has been restored with Linux, Windows and macOS jobs, Python 3.11/3.13/3.14, and Node for the JavaScript regressions. These new CI jobs have not been run on GitHub by this audit.

### Onboarding and settings

- **Credential/OAuth buttons sent the wrong HTTP method.** The frontend supplied three arguments to an API helper that accepts two. Telegram setup, inference setup and OAuth start now use the shared POST helper. A test drives their actual event handlers through the real fetch wrapper.
- **Romance inferred from unrelated answers.** Story answers no longer select a romantic frame or override explicit relationship/pace choices. Personality scores are averaged so merely answering more questions does not increase their magnitude.
- **Review did not expose all important choices.** Quiet hours, timezone, contact rate, photos and voice are editable before creation. Users can state what they hope to get from the connection and an explicit boundary. The hope is stored in the existing identity field, not an additional competing memory system.
- **Lost questionnaire state and keyboard interference.** Revisiting answers preserves selections and review inputs. Story keyboard shortcuts are cleared when leaving the question screen.
- **Creation failure could remain on “awakening.”** Creation now awaits its asynchronous action. The shared action helper now rejects failed operations, so callers cannot mark a failed job save as successful.
- **Telegram details appeared even for web-only setup.** The initial visibility now follows the selected channel. Failed credential saving no longer silently advances the user.
- **Settings density and discoverability.** Five task-oriented groups appear in a desktop sidebar, with related sections together on the right. Mobile opens a group as its own screen with a top-left back arrow. Paired times, removable time/list chips and shorter copy reduce scrolling. Each section saves independently.
- **Inaccessible visual toggles.** Settings checkboxes no longer use `display:none`; they remain keyboard and accessibility controls with visible focus.
- **Late panel responses and unsaved edits.** Panel renders use separate hosts and only the active render can clear dirty state. Settings shortcuts respect the leave guard. Job edits have individual dirty scopes and filtering checks before discarding them.
- **Duplicate voice editor.** Settings previously implemented a second engine/voice form with fewer engines than Voice Studio. Settings and Voice Studio now mount the same editor with a compact engine picker.
- **Overstated privacy/readiness copy.** README and onboarding distinguish local conversation inference from cloud fallbacks, voice, images and messaging. Profile creation is not described as proof that inference works.

## What was consolidated, and what was retained

The two full copies of the Android install/uninstall scripts under `kit/scripts/` are now compatibility entrypoints into the maintained root scripts, removing about 1,200 duplicated lines while preserving their paths. Voice configuration has one editor. Existing shared model/image helpers remain shared.

I did not flatten the CLI, runtime, ledger, image, voice and safety modules into a large file. Their boundaries separate different data ownership and failure modes. Meanwhile `product.js`, `studios.js` and `manage.py` are already large; reducing the file count indiscriminately would make those harder to maintain.

An AST comparison found no identical Python test bodies. Inspection found meaningful coverage of record preservation, profile isolation, contact enforcement, media review, recovery and packaging. Those tests were retained. The CLI test that required printing the PIN was corrected, and missing browser-request and installer contracts were added. Test cleanup should remove duplicated assertions or obsolete contracts, not protect an arbitrary target test count.

## Product strengths

1. **Ownership is real.** A user can inspect, back up and move the underlying records. This is a stronger promise than a chat interface with an export button.
2. **Continuity crosses surfaces.** Chat, scheduled life, journals and media share a companion rather than creating separate characters in each feature.
3. **Some important boundaries are implemented outside the model.** Outbox limits and record-handling rules do not depend exclusively on a prompt being obeyed.
4. **Practical agency differentiates it.** The same identity can participate in ordinary conversation and help investigate a real problem through Hermes.
5. **The testing investment is worth keeping.** The initial audit found 865 passing tests and a real release failure. The suite is useful evidence, although the broken onboarding buttons demonstrate why backend tests alone are insufficient.

## What still holds the product back

### 1. Define “ready” as an observed result

A saved provider name/key, a created profile, a running gateway and a successful model reply are different states. The onboarding environment currently derives `inference.configured` from model configuration and broad credential detection; that does not prove the selected provider works, and local no-key configurations need their own interpretation. Make readiness explicit: runtime installed, provider configured, model tested, first reply received. Keep the test voluntary when it makes a billable provider request.

Linux setup now invokes the official staged Hermes installer if absent; --skip-hermes explicitly defers it. Existing Hermes homes or configuration files can be linked from Settings. Windows/macOS launchers also bootstrap the workspace, not a preconfigured companion. This distinction should remain visible in the quickstart and success screen.

### 2. Make the first week demonstrate continuity

The best success criterion is a user returning and recognising a meaningful continuation: a remembered preference, an unfinished shared project, a relevant journal entry, or a welcome check-in they explicitly enabled. A new calendar, meter or studio does not by itself demonstrate that value.

Recommended first-week path: create → working conversation → inspect one remembered detail → choose contact preferences → inspect one background event → verify restart recovery. Offer these as gentle next steps; do not make every specialist setting a prerequisite.

### 3. Reduce maintenance decisions before adding capability

Model routing, installation, gateway ownership, schedules and media providers remain cognitively expensive. Presets need to state where requests go, which credentials they require, and whether fallbacks can cost money. Model IDs and performance claims need current provider/hardware evidence; this pass did not certify every advertised model, voice engine or GPU path.

Some old installer name/human flags now mainly affect installer presentation while browser onboarding owns identity. Retire or deliberately connect these inputs in a subsequent compatibility pass rather than presenting two independent questionnaires.

### 4. Explain the companion's state without pretending it is measurement

The feelings model starts from authored baselines (including warmth/trust) and updates them using experience records and heuristics. That is a coherent simulation, but a “70% trust” display can imply precision the implementation does not establish. Explain the evidence and recent changes alongside the numbers. Keep the existing distinction between authored mood and real operational failures.

### 5. Keep an acceptance record for every release

Android service supervision, wake locks, reboot recovery and native dependency wheels cannot be certified by shell syntax checks. Windows/macOS microphone, process startup and platform integration also need native checks. The owner's existing deployments are valuable; record OS/runtime versions, commands, outcomes and failures so that the next change can be compared against them.

## Verification and remaining acceptance

| Check | Result in this audit |
| --- | --- |
| Final Python/embedded JS suite | **881 passed, 46 subtests passed** on Linux/Python 3.14; one existing Starlette/httpx deprecation warning |
| Initial Python/embedded JS suite | 865 passed; 1 failed because the manifest referenced missing CI configuration |
| Installer contracts | Piped dry-run, invalid PIN rejection, configuration preservation, unusual path characters, saved access policy, compatibility entrypoint and upgrade dry-run exercised |
| Public installer dependencies | Both published setup scripts, Android wheel archive, official Hermes installer and both uv bootstrap URLs returned HTTP 200 on this date |
| Fresh Linux release bootstrap | New extraction, new virtual environment, actual dependency installation and CLI help succeeded |
| Fresh Linux hosted workspace | Served HTTP 200, identified itself as tamanitomo and reported its explicitly configured port |
| Browser settings | Saved a changed quiet hour, verified unsaved-navigation protection, navigated panels, checked search and accessible controls |
| Browser onboarding | Completed twelve story scenes and three preference choices, edited the proposed identity/contact settings, created a disposable profile, verified replies-only and the free-text intention in persisted state |
| Browser layout | Checked 390px phone and 1280px desktop viewports; no horizontal phone overflow; paired contact times, desktop sidebar, mobile group screens and back navigation verified |
| Release packaging | Source archive built successfully with its integrity manifest |
| Native Android/Windows/macOS reinstallation | Not run here; existing owner deployments acknowledged |
| Real provider, Telegram, voice and image delivery | Not exercised in this pass; no real credentials or live companion data used |
| Reboot, overnight schedules, battery management | Not exercised in this pass |

Before releasing these changes, run one fresh-install and one upgrade-preservation check on each supported platform. On each, confirm first chat, restart/resume and the intended network access. For Android also confirm runit startup and reboot/wake-lock behaviour. For enabled optional features, include one voice turn, one reviewed image and one permitted outbound message to a deliberate test destination.

Changes remain local and reviewable. No deployment, commit, push, real companion modification or external message was performed. The companion-life source changes and presence-template edits that already existed at the start were preserved.


## Layout revision awaiting owner approval

One owner may have multiple companions, each backed by a Hermes profile. The five settings groups are Companion, Models & providers, Images & voice, Schedule & usage, and App & access. The duplicate full profile settings form is reduced to identity and advanced context/storage. List-valued settings use chips where appropriate; complex advanced objects retain JSON editing.

Onboarding separates story-based personality suggestions from explicit permissions, includes the user's intention, and reviews schedules before creation. Worker setup omits inapplicable social questions. Friendship and collaboration no longer show romantic completion percentages. Personality suggestions are authored heuristics, not validated compatibility predictions.

Approved schedules require a successful model probe before enabling model jobs. Failed probes leave a created profile with paused jobs and an attention message. A running Hermes gateway remains a separate requirement; automatic gateway startup and overnight execution are not certified here.

New companions receive stable least-used minute offsets while explicit wake/sleep times remain intact. Offsets reduce simultaneous starts; they do not serialize requests. Photo cadence is editable and changes preserve custom job schedules. Usage shows recorded input/output tokens per last run, hour, day and week, with continuation sessions included and windows assigned by run start. Missing records remain unknown. These are not billing totals or image charges.

Image settings expose available Hermes connections and task routing separately from optional ComfyUI setup. Subscription image availability depends on the installed integration and account; no fixed-price entitlement is promised. Current official shell and PowerShell installer manifests were inspected without executing them.

A disposable browser preview completed creation using fake Hermes, correctly retained paused jobs after a failed probe, and entered the workspace. No real provider or live companion data was used. Android installation and device testing are explicitly deferred until the owner approves the layout. Native installers, media delivery and overnight scheduling remain acceptance work.


## Sidebar revision after layout feedback

The owner rejected the all-settings dropdown. It has been removed. Desktop keeps five groups in a left sidebar; the right side contains all related sections. Mobile shows the group index first, then a group screen with a back arrow. Each section has an independent dirty/save scope. Browser checks confirmed that saving photo preferences does not discard unsaved image-provider edits, and that grouped Hermes forms have no duplicate IDs or horizontal overflow at the checked mobile widths.

Image provider selection now reveals ComfyUI workflow lanes directly when ComfyUI is chosen. Existing workflow graphs, mappings and generation code are unchanged by this revision. A disposable fixture with two distinct workflows retained its custom lane assignments through cloud selection, save, reload and switching back to ComfyUI. The previous lane choices are retained as UI preferences when another provider is active. No real ComfyUI server or cloud generation was used; generation against the owner's server remains unverified.

Onboarding now explicitly asks which image style the owner wants. A regression drives the interview through creation and verifies that this choice is included in the saved answers. Completion offers a first-portrait request in chat when a visual style was chosen; this prepares an editable message, leaving the companion to choose the appearance. It does not automatically spend image credits or claim to have generated a portrait.

Verification: 881 tests and 46 subtests passed; additional focused browser and JavaScript checks cover the revised group navigation, independent saves, provider switching and onboarding style persistence. Android remains deferred pending layout approval.


## Provider-aware pickers and compact summaries

Primary, fallback and background tier editors now list the providers reported for the Hermes profile and use its per-provider model catalog. Switching provider clears incompatible model/endpoint selections. ChatGPT OAuth hides the base URL; local/custom connections expose it, while existing named-provider gateway overrides remain editable. Missing catalogs retain an explicit manual-model option. Cached lists are labelled as cached and are not proof of current account access.

Loops and Reflection have independent collapsible editors showing their assigned model in the summary. Saving models collapses them; saving an individual scheduled job collapses its editor too. Custom tier endpoints are validated and passed to cron creation/application only when Hermes supports the relevant flag. Unsupported Hermes versions receive an explicit error.

Statistics in jobs, memory and planning use compact label/value rows without redundant third-line captions. Shared fact lists are horizontal rows. Browser checks at 390px showed no horizontal overflow; job counters measured approximately 46px high. The disposable ChatGPT catalog fixture verified model options, hidden/cleared endpoints and collapsed saved tiers without making provider requests.

Final verification for this revision: **884 tests and 46 subtests passed**, with the existing Starlette/httpx deprecation warning. JavaScript syntax and regression checks passed. No phone installation or live provider calls were performed.
