# Fresh-eyes product and implementation audit

Reviewed September 12, 2026, against the current working tree, including its existing uncommitted changes.

Follow-up: the first reliability pass addressing F1–F8 has been implemented locally. See `docs/PRODUCT_DIRECTION.md` and the Unreleased reliability changelog for scope and verification. The findings below preserve the original audit evidence.

The product has a compelling center: a companion with continuity, an inspectable history, and boundaries enforced outside the model. The largest problem is consistency. The same person, preferences, files, and background actions are presented through several interfaces that do not always enforce the same rules. Make these behaviors dependable before adding more configuration surfaces.

## Scope and evidence

- Read the application entry point, API middleware, operation lifecycle, session retrieval, content catalog, vault, profile editor, image/voice boundaries, and the JavaScript layers actually loaded by the page.
- Ran `.venv/bin/python -m unittest discover -s tests`: **676 tests passed in 71.368 seconds**. There were resource/deprecation warnings, but no failures.
- Ran `node tests/test_content_ui.js`: passed.
- Opened an isolated local app using the existing test fixture and Hermes contract double. Inspected Home, navigation, Preferences, companion creation, Vault editing, and saved conversation presentation. Used synthetic profiles, notes, and an orange test image.
- Executed additional Python API probes and Node probes against the actual source functions. These exposed issues absent from the existing suite.
- Did not change application code or real companion data. Did not make provider calls, send messages, install engines, or alter a live gateway.

This is not Windows acceptance, a microphone/audio-device test, a production penetration test, or a full scheduled-day run. Existing tests prove many local contracts; they do not establish those other outcomes.

## What is good and should survive a redesign

1. **Continuity has a concrete implementation.** Append-only records, evidence-bearing facts, carried-forward scene labels, and model-independent contact gates give the product substance beyond a chat interface.
2. **The user owns inspectable files.** Plain Markdown/JSON, vault browsing, backups, stale-write rejection, and recoverable Vault trash are valuable. The API conflict tests are a particular strength.
3. **The visual language is coherent.** Typography, spacing, cards, and navigation groups create a calm workspace. The compact navigation uses an inert closed sidebar, labels, and an expanded state; keyboard focus is visible.
4. **Different views have useful purposes.** Timeline helps reconstruct a day; Photos supports collections; Journal supports reading; Memory exposes evidence. Keep these distinctions, while reducing competition in the main navigation.
5. **The application often admits uncertainty.** Missing scenes, unavailable history, and incomplete setup are represented explicitly. The implementation and documentation both recognize the limits of simulated integration tests.
6. **There are strong ingredients for safe configuration.** Profile addressing, token checks, secret masking, revisions, hook review, and operation progress are already present. The next work is to make them consistent across every entry point.

## Findings to fix first

P1 here means a trust, privacy, data-preservation, or core-flow issue worth fixing before expanding the beta. P2 means significant inconsistency or recoverable disruption. These priorities are product judgments, not CVSS ratings.

### F1 — P1: Zero daily messages silently means unlimited

**Evidence:** observed form and traced enforcement. Preferences labels the field “Messages a day,” accepts zero, and gives no explanation. Creation also accepts zero. `companion_outreach.decide()` converts zero to an absent cap and returns “No daily limit set.”

A person can reasonably enter zero intending silence and instead remove the daily limit. Quiet hours and the separate outreach policy still apply; zero does not bypass those gates.

**Fix:** offer explicit choices for Replies only, Limited proactive contact, and Unlimited. Show the resulting policy in plain language. Keep any legacy zero sentinel behind the UI, with an explicit migration rule.

**References:** `kit/app/static/index.html:226`, `kit/app/static/workspace.js:83`, `kit/scripts/companion_outreach.py:58`.

### F2 — P1: Chat and activity previews bypass image blurring

**Evidence:** API + actual JavaScript renderer probe; synthetic chat inspected in the browser. A marked image arrives in a session attachment with `blur: true`. `inlineMedia()` emits only `class="chat-media"`, ignoring that flag. The same helper is used by Gateway activity. Photos and Creations use a different helper that honors it.

**Fix:** one shared image presentation component that applies the review state, blur preference, and deliberate reveal behavior everywhere. Test both NSFW and unreviewed images, including activity previews and copied images.

**References:** `kit/app/static/workspace.js:148`, `kit/app/static/workspace.js:152`, `kit/app/static/product.js:104`, `kit/app/manage.py:554`.

### F3 — P1: Escaped media URLs break spoken-reply playback and reference selection

**Evidence:** executed the actual `mediaUrl()` function. It produces a URL containing `&amp;profile` and `&amp;token`. That is correct inside an HTML string, but incorrect for `fetch()` or assigning `audio.src`. Parsing the result produces parameters named `amp;profile` and `amp;token`; a request to the isolated authenticated server returned **401**.

Affected source paths include spoken chat reply playback and Identity → Choose reference from albums. Ordinary HTML image embeds do not have this problem because the HTML parser decodes the entities.

**Fix:** return a raw URL from the URL builder and HTML-escape only at the HTML insertion boundary. Audit every caller; add tests that parse the final requested URL, rather than comparing an HTML string alone.

**References:** `kit/app/static/index.html:48`, `kit/app/static/voice-chat.js:47`, `kit/app/static/product.js:138`.

### F4 — P1: Changing shared-fact preferences makes existing facts disappear

**Evidence:** created one fact in a disposable private human ledger. Changed `share_people` from false to true through `/api/settings`. The response was **200**, and `/api/ledgers` changed from **one fact to zero**. The original ledger remained on disk, but the newly selected location had no ledger.

This is not physical deletion. It is an unexplained change in the record the companion and Memory screen consult. The full profile editor already has migration/conflict handling for this situation, while Preferences does not.

**Fix:** use one migration-aware settings service. Explain what will be shared, preserve existing facts, handle conflicting destinations deliberately, and define what turning sharing off should copy or isolate.

**References:** `kit/app/server.py:223`, `kit/app/server.py:238`, `kit/app/profile_editor.py:55`.

### F5 — P1: Unsaved notes can be discarded without warning

**Evidence:** browser reproduction: open Vault → edit a disposable note → enter unsaved text → click the app's Refresh button. The editor immediately becomes “Choose a file to explore,” with no warning or recovery option.

The Vault's `leaveNote()` guard covers some file changes. The global refresh and page navigation paths do not use it. Returning to Vault reconstructs the view. Other long editors also lack a shared dirty-state mechanism.

**Fix:** a unified leave/refresh guard and draft preservation for notes, identity, profile, and workflow editors. Keep revision checks for saved-file conflicts; they solve a different problem.

**References:** `kit/app/static/product.js:11`, `kit/app/static/index.html:58`, `kit/app/static/studios.js:31`.

### F6 — P2: One failed operation poll can leave all subsequent actions blocked

**Evidence:** executed the actual `followOperation()` with a simulated rejected polling request. The promise rejected, but `activeOperation` remained set to the old operation ID. `action()` subsequently refuses new work with “Wait for the current action to finish.”

A temporary network problem can therefore leave the browser blocked even after the server finishes. Reload is a workaround, not a recovery flow.

**Fix:** distinguish server operation status from connection status. Preserve the operation ID for reconnecting, offer Retry status, and clear or reconcile the client lock safely. Never retry a potentially completed mutation automatically just because polling failed.

**References:** `kit/app/static/workspace.js:12`, `kit/app/static/workspace.js:31`.

### F7 — P2: Pending operations can be shown under the wrong companion

**Evidence:** submitted a synthetic Nova operation, then fetched its ID with `profile=rowan`. The API returned **200** and Nova's result. The endpoint checks the installation only. The browser also stores its pending operation under `operation-<installation>`, and streams any recovered chat text into the currently open chat.

Switching companions during work can therefore display a prior companion's progress or response in the new context. This is an isolation/attribution defect within one token-authorized workspace, not evidence of an unauthenticated cross-account breach.

**Fix:** keep installation-wide serialization where needed, but record a separate originating profile and operation kind. Only render a conversation result in its owning profile/session; show other-profile work as a labeled background task.

**References:** `kit/app/manage.py:116`, `kit/app/runtime.py:238`, `kit/app/static/workspace.js:12`, `kit/app/static/workspace.js:45`.

### F8 — P2: Different editors accept different settings and apply different side effects

**Evidence:** the complete profile editor accepted `image_timeline=true` with `image_style='none'` and saved it. The same values sent to Preferences were rejected with **400**, “Choose an image style before enabling the image timeline.”

Related source finding: Preferences can synchronize cadence changes to jobs, while the full editor returns an instruction to repair schedules manually. Its browser save handler discards that instruction and reports only that the companion was saved. Users can believe a schedule change is active when the installed jobs have not been updated.

**Fix:** both screens must call the same validation and apply pipeline. Return separate states for “configuration saved,” “background jobs updated,” and “restart or repair required,” and show them.

**References:** `kit/app/profile_editor.py:25`, `kit/app/profile_editor.py:94`, `kit/app/server.py:235`, `kit/app/static/studios.js:24`.

## Additional issues and investigations

- **Voice transcription failure recovery — code-traced, not audio-device tested.** A failed operation is returned by `followOperation()` rather than thrown. The transcription handler reenables the composer in the success callback or exception handler, but not for that failed result. It can leave Send/history/new-chat disabled and the composer read-only. Stop playback or navigation may recover it. Test failed/interrupted transcription as explicit terminal states (`voice-chat.js:31`).
- **Chat navigation during an in-flight turn — code-traced.** Reentering Chat constructs enabled controls regardless of an existing operation. The success callback can reconstruct Chat after the user has moved elsewhere. Test leave/return, refresh, and selected-session changes with delayed replies.
- **Browser Back is not application navigation.** `showTab()` uses `history.replaceState`, and there is no corresponding popstate navigation. Treat this as a deliberate decision to revisit: users generally expect Back to return to the prior page or document.
- **Long-history access is bounded without a browse-older flow.** Sessions return 100 entries and a conversation returns 200 messages. The UI has no pagination for retrieving older material. The interface should distinguish “not loaded” from “not recorded.”
- **Large-vault performance needs measurement.** Home refreshes every 30 seconds and requests the catalog and journal along with overview/timeline. Those scans are bounded and image digests are cached, but multiple tabs and large archives could still be expensive. Measure a representative large vault before deciding whether to index or cache more aggressively.

## What feels cumbersome

### The application asks users to understand its implementation too early

The creator puts profile ID, identity, relationship, timezone, visual configuration, contact policy, sharing, and a host filesystem path on one form before the user has had a conversation. Choosing Worker does not simplify the visible relationship-heavy form. The pronoun menus support only she/her and he/him, and visual catalog selection follows that choice.

Use a short staged setup: who this is, how to connect a model, then a first conversation. Present contact/routine activation as a clear later decision. Generate a profile ID by default. Explain optional choices at the moment they matter. Separate pronouns from visual presentation if broader character creation is intended.

### Too many places appear to own the same change

Identity, Edit companion, Preferences, Image studio, Voice studio, and the embedded Hermes dashboard overlap. A companion card says to choose someone to spend time with, but clicking it opens the full configuration editor. The header selector opens Home instead.

Make opening a companion consistent, and give editing its own named action. Establish one obvious home for each setting; other pages should link there or expose a clearly scoped shortcut using the same save logic.

### The daily experience has too much management furniture

There are 16 sidebar destinations, with more pages in the command finder. Hermes settings adds another row of dashboard destinations and an older native-setup interface underneath. On the tested compact viewport, introductory text and conversation history consume substantial vertical space above the messages, with a separately scrolling chat inside the page.

I would test five primary destinations: Home, Conversation, Life, Memory, and Settings. Life can contain Timeline, Photos, Journal, and Creations. Put specialist studios and runtime management under Settings/Advanced while preserving direct shortcuts.

This is a proposed structure to validate with your usage, not a reason to remove capabilities.

### Labels and save behavior sometimes overpromise

- “Find anything” only finds page names; even the hint “providers” does not match “Hermes settings.” Rename it “Go to page” until there is content search, and add aliases.
- Contact settings expose `updates_only`, `free`, and `never`, while creation uses readable descriptions.
- Media preferences have a separate Save button below the main Save preferences button, and appear under every preference category. Make that scope visually explicit.
- The same file is recoverably trashed in Vault but permanently deleted through the content viewer. Prefer a consistent Trash action, reserving permanent deletion for the trash interface.
- Chat prints Markdown syntax and attachment references literally, while Journal provides formatted reading. Render a safe common subset and avoid showing raw media markers beside the rendered attachment.
- Home's incomplete-fixture message says to set up a companion even when one is already installed. Distinguish missing identity, missing model, inactive routine, and simply no scene yet. Group setup issues by root cause rather than presenting many missing jobs as independent problems.
- Documentation has accumulated contradictions. `docs/DESKTOP.md` says streaming is not implemented, then later says compatible runtimes stream; its verification count is behind the current suite. Publish one current capability/verification table.

### Emotional indicators need an intentional product decision

“Feeling the gap” is a prominent percentage derived from elapsed time. Even with explanatory text, users may read it as pressure or as a measured emotional truth. Decide whether this is a desired game-like mechanic, optional simulation telemetry, or something that belongs only in diagnostics. Qualitative language and opt-in visibility may fit the product better.

## Questions for the product owner

1. Who must succeed first: you as a power user, a nontechnical friend receiving a Windows ZIP, or a mobile/LAN user?
2. What should someone accomplish in their first ten minutes, and which three actions matter most every day afterward?
3. Is the center of the product companionship and continuity, or an all-purpose Hermes management studio? How important are Worker and Colleague flows in this release?
4. What should shared memory mean when switching sharing on and off: carry existing facts, share future facts only, or choose what to share?
5. Should the companion's private reflections and connection indicators be prominent, optional, or hidden from the everyday experience?
6. Which platform and provider combinations are release requirements, and which can remain explicitly experimental?

## Proposed next work

### First: make the current promises reliable

Fix F1–F8 in small reviewable changes. Add targeted regression coverage at the layer where each issue occurs: API migration/validation tests, actual URL request tests, renderer privacy tests, and browser tests for dirty navigation and operation recovery. Test the same preference through every editor that exposes it.

### Second: simplify one complete journey

Choose the primary audience and walk through install → create/adopt → connect → first conversation → activate a routine → return tomorrow. Give every step a clear success condition and recovery path. Consolidate the overlapping settings during this work rather than attempting a wholesale visual rewrite.

### Third: establish real acceptance evidence

Run a disposable-profile test on each required platform: real model reply, streamed reply, image, voice, restart during an operation, changed provider credentials, unavailable gateway, quiet hours, and an overnight routine. Use deliberate test destinations for any delivery checks. Record failures and recoveries, not just successful setup.

### Engineering direction

Replace the chain of handler overrides with one explicit controller per page and shared services for configuration changes, operations, media URLs/rendering, and unsaved drafts. Format the source into reviewable functions. Preserve the existing backend contracts and visual design while doing so. A framework migration is not a prerequisite.

Success would mean the user can predict what Save does, trust that private images remain concealed, leave an editor without losing work, reconnect after a failure, and know which companion owns every visible result.
