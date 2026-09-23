## 3.0.12 — What she sends, when she wakes, what she keeps (2026-09-23)

- Deliver the health watch's alert. Kit jobs are created to keep their output local, which Hermes treats as "deliver nowhere", so the watch recorded an alert as sent and then kept quiet about it for six hours while nobody had seen it. It now sends through the companion's own channel, waits out quiet hours, and only counts an alert as given once it was delivered. Looking with `--json` no longer counts as having told anyone.
- Decide what a companion may send in one place. The settings say you are willing; closeness, trust and any step back in the relationship now decide too, for every picture she makes, every review verdict and every delivery. A verdict recorded earlier is checked again when the picture would actually leave, including when pre-delivery review is off.
- Record what each piece of clothing covers (`covers`: top, bottom, full or none). The starter closet states it, new pieces must, and older pieces fall back by category. Socks, shoes, a cardigan or a top on their own no longer count as being dressed, and the camera describes what is really worn.
- Keep a moment she marks private out of the camera, always. What she has on is now read from the outfit rather than stored as if she had asked for privacy, so the two can no longer be confused.
- Add a `setting` field (`private` or `public`) to presence updates. It carries forward while she stays put and must be given again after a move; the rules about what she may wear where read it instead of guessing from the location's words, which counted "Home Depot" as home. The words are used only to ask about a record that contradicts itself.
- Run the morning routine when her declared morning arrives. It looks every quarter hour around the end of quiet hours and a fingerprint lets it run once, at the time she declared at wind-down, or just after quiet hours with no declaration.
- Queue from `companion_outreach.py send` instead of delivering, and stop teaching a direct send in the prompts. A thought that was both queued and sent arrived twice.
- Stop opening the Closet from switching on the clothing-care routine, and start a newly enabled routine with only the last two days' clothes in the hamper.
- Clear only the conversations a check-in was started for, so one that ends while it runs is still reflected on.
- Record a keepsake as shared only when it was queued; photos set to ask are offered in words.
- Review a picture before claiming the day's message slot, and let a dry run of the dispatcher decide without claiming one.
- Count what is waiting in the outbox for the autonomy fingerprint, not every message ever queued.
- Leave the root companion's own folders off a profile's vault map.
- Teach file-based recording in the per-turn lookup hints, matching the scheduled jobs.

## 3.0.11 — Updates on the phone stay fixed (2026-09-23)

- Keep `hermes update` from trying to build nemo-relay on the phone. 3.0.10 left it out of the first install, but an update resolves Hermes's dependencies again and would have hit the same failure. The installer now writes an override that uv honours, exports it in the shell and in both background services, and installs uv so Hermes updates through it. An update may report one package as missing; that is this package, and the update still completes.
- Remember `ANDROID_API_LEVEL` in the shell profile, so a later update that has to build a Rust package from source does not fail asking for it.
- Apply both on upgrade as well, so a phone that is already installed picks them up by running the installer again.

## 3.0.10 — Phones Hermes does not recognise (2026-09-23)

- Install Hermes on Android without `nemo-relay`. Hermes asks for that package everywhere except Android and recognises Android by the word "android" in the kernel's release string, which older phone kernels do not carry. On those phones pip set out to compile nemo-relay from Rust source and the install ended in "Failed to build nemo-relay" before Tamanitomo was ever downloaded. Hermes runs without it, so the installer now installs Hermes's own dependency list without that one package and then Hermes itself, which is the workaround Hermes suggests for these devices.

## 3.0.9 — Installing again is how you update (2026-09-23)

- Ask what to do when the Linux or Android installer finds Tamanitomo already installed: upgrade, which keeps everything and moves the program to the newest release, or a fresh install, which sets the old program folder aside and installs a clean copy. Before, running the installer again quietly kept the old code, so someone who reinstalled to fix a problem was still running the version that had it. Your companion, your setup answers and your vault are kept either way, and an unattended run always upgrades.
- Install the newest published release rather than whatever is on the main branch, so a new install gets exactly what was released and tested.
- Leave a checkout with its own code changes, or one already past the newest release, exactly as it is, and say so.
- Make the Android `--upgrade` option move to the newest release as well, instead of pulling the main branch.

## 3.0.8 — A budget that counts what it budgets (2026-09-23)

- Stop the doctor reporting every full continuity block as over budget. It was counting the two markers around the block, about seventy-five characters the budget never covered, so a block written exactly to size always read as too large and left the check marked incomplete.

## 3.0.7 — A map of the vault (2026-09-22)

- Give the companion a map of the whole vault at the start of every session: every folder, how many notes it holds, and up to five of the files that say what it is, a folder's README first and then the newest. Before, she only knew the files something else happened to mention, and "is there a note about this" was a guess. `companion_vault_index.py show <folder>` lists any folder in full, with each note's sections.
- Send the map once per session, not once per turn. Hermes replays each turn's injected context with the history, so a map sent every turn would be carried over and over; sent once, it stays in the cached prefix. It is sent again only when compression has summarised it away.
- Size the map from the model's window, up to a tenth of it, set by `vault_index_tokens` (`0` switches it off). A two-thousand-note vault takes about ten thousand tokens. On a tight window the key files per folder shrink before any folder is dropped, and a very small window gets a tree of folder counts, saying so.
- Leave installed tool folders such as `node_modules` off the map, since nobody wrote what is in them.
- Leave other agents' private folders off the map, along with hidden folders and anything named in `vault_index_exclude`.
- Recognise the kit's own Hermes hooks whatever Python the command names. Repair run under a different interpreter used to register the continuity hook a second time, and Hermes then ran both copies, so every turn carried the whole continuity block twice. The doctor now reports a duplicate.
- Raise Hermes's hook output limit so the first turn of a session is not written to disk in place of being read, and have the doctor say when that limit is too low.

## 3.0.6 — One Python on the phone (2026-09-22)

- Require Python 3.11 for every virtualenv on Termux, since the prebuilt Android packages exist for no other version. The installer used to fall back to whatever `python3` was there, pip rejected all eighteen wheels in silence, and the install died compiling Rust with `error running maturin`.
- Install the Termux packages one at a time when installing them together fails. apt is all or nothing, so a single unavailable package had been quietly taking Python 3.11 and the Rust toolchain down with it.
- Rebuild a virtualenv an earlier run left on the wrong Python, rather than reusing it and failing the same way on every attempt; and install Hermes into its virtualenv whenever it is missing, not only when the virtualenv is new.
- Show why the prebuilt packages did not install instead of discarding the output, and when pip does fail, say which Python the virtualenv has, whether Rust is installed and whether `ANDROID_API_LEVEL` is set. That variable is now set from the phone, because maturin will not build for Android without it.
- Stop pip announcing a newer version of itself during install, which read as the error.

## 3.0.5 — Six pages that had stopped being read (2026-09-22)

- Fold Creations into the Vault, which held the same files behind a second door: a Recent view that lists them newest first with a type filter and thumbnails, and a Folders view that is the tree and the reader. The old page laid every file out flat with no hierarchy and grew to a hundred and twenty-four thousand pixels of identical document icons; Recent is five thousand. The old route still answers, so an existing link lands somewhere sensible.
- Give the Memories page the forty preferences she had written about herself, which the server had been sending and no screen had ever shown.
- Join the questions she wants to ask you and the threads she is carrying into one list, instead of asking the same thing twice under two names on two different pages, and leave Plans and calendar to be about time.
- Read a day on the Timeline as a day: her reflection leads it, the scenes follow in order, and the photographs sit inline at the hour they were taken rather than behind a button that says View photo.
- Collapse a scene that was rewritten every few minutes into the span it actually covered, so one morning's shower stops being six identical rows — thirty-eight rows became twenty-six for a single day.
- Page the long lists rather than printing all of them: facts, moments, files and days all arrive in batches now, with what remains offered rather than assumed.
- Photograph the outside of an outfit rather than every layer of it. A record of jeans over briefs handed both to the image model, which drew the briefs riding out of the jeans — in every picture, because she is wearing underwear in every picture. A layer nothing covers is still described.
- Let the picture viewer's top bar float over the photograph without a divider, and stop it crushing the back button on a narrow cover screen.
- Keep bookmark, regenerate and the safety rating on the bar itself and put the rest behind the dots, and let the back arrow be an arrow instead of a button in a circle.

## 3.0.4 — Forwarding, and whose photograph this is (2026-09-22)

- Forward whatever Hermes passes to the functions the streaming bridge wraps, so a chat turn no longer fails with `TypeError: run() got an unexpected keyword argument 'emitter'` on Hermes 0.21.3 while cron jobs carry on working. Reported, diagnosed and fixed by **erohtar** (#1).
- Stop assigning an HTML-escaped URL directly to an image property: the entities stayed literal, `profile` arrived named `amp;profile`, and the photo viewer silently showed nothing for every companion but the first. The access token was being dropped the same way.
- Make the viewer's navigation arrows a hint rather than furniture — no pill, no border, no blur, fading in only when a pointer is near — and remove them entirely where there is no pointer, since swiping is the interaction there.

## 3.0.3 — An empty day is allowed to be empty (2026-09-22)

- Check the session record before writing about the person: `companion_life.py contact --day` reports how many of a day's sessions came from someone actually present rather than from a scheduled job, with their times and titles.
- Require the daily journal to run that check before it attributes a single word, want or feeling to the human, and to say plainly that a day held no exchange when none is recorded.
- Treat a session title as what it is — a summary written afterwards — and never as something the person said.
- Report an unreadable or absent session record as unknown rather than as nobody having been there; the two are not the same and only one is safe to write from.
- Count a dialogue between two companions as what it is, rather than as company.
- Judge a presence record by the moment it describes instead of the moment it is validated, so the same pulse no longer passes before nine in the morning and fails at ten, and a job catching up is not measured against a day it was not writing about.
- Let a browser keep a photograph instead of forbidding it, and answer the revalidation here, so scrolling a gallery stops re-fetching the whole library.
- Track every pointer in the photo viewer, so two fingers pinch to zoom rather than reading as one violent swipe; add pan while zoomed and double tap to zoom where you tapped.
- Move the picture out the way it was pushed and bring the next in from the far side, instead of snapping back and then changing.
- Restore the picture without waiting for an animation frame, which never arrives in a tab that is not being drawn — a swipe before switching away used to leave it invisible.
- Start selecting photographs by holding one, rather than only through a chip among the collection filters.

## 3.0.2 — What was missing, said out loud (2026-09-22)

- Import a workflow from a picture made with custom nodes: read the weights and the sampler's numbers off the field names rather than a handful of stock class names, so a graph from a node pack is no longer called incomplete for being unfamiliar.
- Drop the non-finite numbers ComfyUI stamps on the nodes it saves, which parsed fine and then made the reply unencodable, with an error that named no file.
- Name the node classes and the model files the target ComfyUI does not have, instead of letting the render fail later with an error from deep inside it.
- Read the card's VRAM and say when a model will not fit on it, with what to do about it: the same weights exist quantised. Do not suggest that to someone who already has a quantisation.
- Fetch a civitai.red link from the mirror that answers, since that host refuses an ordinary client and the failure blamed the link.
- Stop a preference save reporting that background jobs could not be updated when the jobs were updated and something unrelated was merely flagged.
- Keep a worker alive when the retry meant to improve its answer is refused, and when a provider replies with no choices at all.
- Scale the token budget for a reasoning model, so a job that thought hard does not return its answer cut in half.
- Find Hermes in a checkout made by `uv`, which writes `.venv` where this looked only for `venv`.
- Retire plan items whose time has passed unrecorded, so a morning walk stops reading as still ahead at four in the afternoon, and carry the reasons a day changed into what she is thinking with.
- Keep the newest few update backups rather than one per update, forever.
- Rebuild an imported workflow out of what it used — its model, its LoRAs at their strengths, its sampler settings — into a lane of this kit's own shape, and offer that beside the graph as detected and a download of the publisher's original file.
- Read the architecture of an imported graph from its own wiring rather than from a filename, and say so plainly when a graph does not declare one instead of guessing.
- Check settings recovered from someone else's image exactly as strictly as typed ones.
- Mark an imported workflow incomplete when the target ComfyUI is missing the nodes it needs, rather than calling it renderable and failing later.
- Stop advising on VRAM for weights that are already installed.
- Carry LoRA activation keywords in a companion's own quality tags, so the trigger a character LoRA needs reaches the prompt on ComfyUI lanes without displacing her written appearance.
- Give `feeling` a prompt box in the workflow template, and read the sampler's conditioning from the end of the chain so a contract that grows cannot orphan its last box.

## 3.0.1 — Reasoning that is actually asked for (2026-09-21)

- Keep `reasoning_effort` when a schema is restated into the prompt; that path had been stripping it from every structured request, so the workers that most need to think were told not to.
- Drop the fields a provider may have objected to only on the retry after it actually objected, which is what that code was written for.
- Treat "the provider does not report reasoning" as its own answer rather than as "it did not reason", and warn only on a reported zero.
- Say on the jobs page when a provider cannot confirm reasoning, so an effort setting that is being sent does not look like one that is being ignored.

## 3.0.0 — One author for a day (2026-09-21)

- Hold each day in one plan with one ordered timeline; two items may not occupy the same hours, and a plan that overlaps itself is refused when written, not only when added to.
- Require anything taking an occupied slot to name what it displaces, and record the displacement and its reason in that day's history. Nothing is deleted; items are marked done, moved or dropped.
- Keep whether an item was promised or merely wanted, and give the promise the slot when a day will not hold both.
- Make presence commitments a channel into that plan rather than a second store of dated plans; leave two clashing promises for the companion to resolve rather than choosing one.
- Migrate `tomorrow.json` and presence commitments into the plan, idempotently, leaving any day already settled by hand alone.
- Read care follow-ups from the loops the companion already records, instead of a file that had never existed for anyone.
- Index each archived memory as it moves, with a backfill for everything archived before, and snapshot a memory file before trimming it.
- Group background jobs by origin — shipped, yours, or not companion work — and within that by what they send; show a 24-hour view of when things run, and disclose jobs that make a second model call.
- Retire nine jobs: eight duplicating shipped machinery, and the present advancer, whose rendering was already done by every presence write.
- Judge whether the present is stale by when a model last confirmed it, not by a file's modification time.
- Stop trusting a provider to enforce a JSON schema it accepts and ignores; state the schema in the prompt and check the shape that comes back.
- Validate a presence record where the model can still be told what was wrong, rather than after the correction loop has ended.
- Sync the directory after an atomic replace, so the rename survives an unclean shutdown.
- Separate your to-do list from things you have told her about, and keep both out of her plan.

## 2.9.1 — Uncapped windows, and the call you could not see (2026-09-21)

- Take the largest window a model is measured at rather than the smallest, so nothing caps the context but an explicit `context_length`.
- Ignore endpoints on the local network when sizing a model reached through a hosted provider; a same-named local model may be a different size entirely.
- Show the second model call a pre-read job makes, and which setting governs it, instead of showing only the job's own model.
- Stop describing an unrecognised job as sending nothing private, which was an assertion about a prompt the app had not read.

## 2.9.0 — People, and where her private life goes (2026-09-21)

- Add a recurring cast of eight fictional friends, each with a rhythm, and offer whoever has not been seen lately alongside the evening's ideas. The field has existed since the beginning and nothing ever filled it.
- Let a companion add people she meets and drop ones she does not want; record who she saw by id, so a gap is a fact rather than something read out of her wording.
- Group background jobs by what they send: never contacts a model, contacts one with nothing private, or sends the companion's inner life or the human's own words. Each group states the risk and the safest choice; each job states what it sends.
- Summarise how many scheduled jobs send private material and to which provider, and stop showing a provider on jobs that never contact one.
- Stop inheriting Hermes' 2,200 and 1,375 character memory limits when a profile's config is silent; a missing setting now means the full allowance.
- Resolve a model's context window by name when the provider has no endpoint address, which had sized a 272,000-token model as 32,000 and starved the memory tier chosen from it.

## 2.8.0 — Something to want, and the model you chose (2026-09-21)

- Add a palette of 84 activity ideas, tagged by season, setting, company, energy and length, as seeds for a day rather than scripts for one.
- Offer a handful each evening, weighted away from what was recently chosen and toward the season and whether the day has room, and deterministic per day so the offer does not reshuffle.
- Let the companion add ideas of her own, which join the palette and are favoured afterwards, and decline ones she never wants offered again.
- Record what she chose by id, so recency never involves reading back what she wrote about it.
- Show the ideas she chose for a day alongside its schedule.
- Resolve a background worker's model from the companion's own `models.<tier>` configuration instead of from whatever endpoint the job was written with.
- Reach providers Hermes holds the session for, through a text bridge, so a worker is no longer limited to endpoints with a URL and a bearer token.

## 2.7.0 — A companion plans her day (2026-09-21)

- Ask the companion at wind-down what she means to do tomorrow: one sentence, a day-shape chosen by name, and the clothes she sets out. Nothing had looked past the end of the day, so she had a rhythm and no intentions.
- Take the day-shape from a field she sets rather than from words found in her sentence. The guess read a refusal as an acceptance, "an interest" as a rest day because the word contains "rest", and a workshop as a shopping trip -- and a shape replaces the whole day, so a wrong one rewrote it.
- Refuse a day-shape the companion does not have, naming the ones she does, instead of storing it and silently ignoring it later.
- Read the stated intention as the object the schema has produced for some time; reading it as text raised as soon as there was anything to plan.
- Choose the clothes laid out for tomorrow by the wardrobe's own category rather than by searching their names for "pyjama" or "sleep".
- Add `companion_life.py themes` and validate `plan-tomorrow --theme` against it.

## 2.6.0 — Her day, and your chosen face (2026-09-21)

- Show the companion's expected day on the calendar: daily anchors, the weekly ones belonging to that weekday, and what she intends instead on a day she has planned. A full imagined week previously showed as an empty month.
- Add `GET /api/schedule`, which answers for any day asked for rather than only for right now.
- Fall back to the companion's chosen visual style for a render's quality, which had no fallback at all; a drawn style sent no style direction and came back photorealistic.
- Keep the two style entries that describe a companion rather than a picture out of image prompts.
- Show the chosen profile photo on the home screen, which had been showing the newest picture in the library instead, and redraw it as soon as one is chosen.
- Never use a blurred or sensitive picture as the home screen face; one was used and blurred in place.
- Work out today in the companion's timezone, so the calendar stops highlighting tomorrow through the evening.

## 2.5.0 — Creations and captures are different things (2026-09-21)

- Render an automatic capture out of sight and hand it straight to the timeline, instead of writing it into Creations and copying what the timeline needed; a moment from the companion's day was being filed as something she made.
- Leave one file per photo, which is what made deleting one work: the duplicate copy was why a deleted picture reappeared.
- Treat another version of an existing moment as part of that moment rather than a new creation.
- Keep a capture held for review in Creations, where it can still be found and decided about.
- Clear renders abandoned partway rather than keeping them in a folder built so that nobody sees them.
- Default a render to a creation, so nothing becomes a capture by omission.

## 2.4.1 — Deleting, and knowing a render is running (2026-09-21)

- Delete every saved copy of a photo rather than whichever one the grouping named first; the other copy survived, so the picture reappeared and delete looked broken while reporting success.
- Leave album copies alone, as the confirmation has always promised, and delete only the album copy when that is the one chosen.
- Apply the same expansion to a batch delete, so a photo shown once is deleted once.
- Queue a regeneration through the operation status toast instead of holding the request open for the length of the render, which is why pressing Generate appeared to do nothing.
- Show a progress wheel in that toast, filled from the render's own step count where the provider reports one and turning where it does not, and report queue position while a job waits its turn.
- Blur the versions in a photo's version strip; they were shown in the clear beneath a blurred picture.
- Send each version's own review with it, so choosing one no longer removes the blur, and treat an unreviewed or newly made version as unreviewed rather than safe.

## 2.4.0 — A day counts for what was in it (2026-09-21)

- Score each day of conversation on its own merits rather than counting any day the human spoke, so closeness reflects what was actually said.
- Weigh how much was said, how many times, and how much of the day it spanned, each capped so no one of them can stand in for a day on its own.
- Ignore a message repeating something already said that day, which is what made the old count farmable.
- Charge for thin contact as well as silence, measured over a fortnight against a par of a real conversation every other day, and never charge for both at once.
- Count days in the human's own timezone, so an evening conversation is one day rather than two half-days.
- Keep the stage timings as they were: friendship in about four days, the deepest stage at about two months of genuine daily conversation.

## 2.3.10 — Pictures stay with their companion (2026-09-21)

- Scope a moment's identifier to the companion, so two companions can no longer produce pictures with the same filename.
- Attach the companion to the variant thumbnail, which was the one media link built without it and could show another companion's picture.
- Honour a seed sent with a regeneration; asking for a new one previously had no effect.
- Store each compiled prompt under its own name, and translate pictures recorded under the previous names.
- Give the wardrobe, lighting and framing one place each instead of repeating them inside the scene.
- Record what is actually being done, and mark a moment as private rather than inferring it from wording.

## 2.3.9 — Prompt details (2026-09-21)

- Store each compiled prompt under its own name; the details pane had been showing the two forms with their titles swapped.
- Translate pictures recorded under the previous names instead of relabelling them, so older pictures read correctly too.
- Show the form that was actually sent, with the other folded away, rather than printing the same scene twice.

## 2.3.8 — Deleting one picture from a moment (2026-09-21)

- Carry a picture's version marker with it when switching between renders of the same moment, so deleting one is no longer refused as a conflict.
- Resolve a deleted picture back to the moment it belongs to, remove just that render, promote another if it was the one on display, and retire the moment only when nothing remains.
- Tidy a record whose file is already gone instead of refusing it.

## 2.3.7 — Wardrobe accuracy and relationship scales (2026-09-21)

- Read a companion's wardrobe state from the record rather than inferring it from activity or location wording, which could contradict what she was recorded wearing.
- Keep picture prompts and their constraints consistent, so a private routine is rendered in keeping with your settings or not captured at all.
- Give non-romantic companions their own closeness scale, and allow any companion to reach the final stage.
- Earn closeness from days that belong to the relationship instead of the whole message history.
- Add a finer control under Companion → Relationship for what a companion may send.
- Judge shower duration by the recorded bathing state rather than by any activity that mentions one.
- Stop the update notice and photo provider picker from crushing their own text, and let picture variants render without holding the page.

## 2.3.6 — Photo fixes, moment variations, and daily routine transitions (2026-09-21)

- Photo fixes: accurately honor wardrobe states and contextual prompt compilation for private routines and bathing, eliminating conflicting outerwear prompts.
- Multi-provider moment variations: retry any captured moment with another configured image provider while keeping the companion's scene, activity, wardrobe, and identity locked.
- Lightbox variant switcher: inspect multiple renders for a single moment and select "Use this photo for this moment" to update primary timeline and gallery cards without modifying profile portraits.
- Dual prompt inspection: view both prose narrative and structured prompts in the photo details viewer.
- Daily routine hygiene: cap shower durations to 40 minutes, track removed clothing items into laundry care, and enforce daytime attire before leaving home.

## 2.3.5 — Overnight sleep cadence and quiet hours separation (2026-09-20)

- Separate sleeping state from quiet-hours outreach rules so scheduled lifecycles remain consistent overnight.
- Gate photographic capture on scene changes rather than time intervals during rest.
- Group daily rhythm settings into companion preferences and reflect commitments on the calendar.

## 2.3.4 — Reliable pulse-to-image handoff (2026-09-19)

- Teach companion pulses the smallest valid recovery when clothing-care timing rules conflict with a full bedtime transition, preventing stale state from needlessly starving image timeline captures.
- Flatten mood and current wants into clean emotional-tone text instead of leaking Python list notation into hosted image prompts.

## 2.3.3 — Simpler companion settings (2026-09-19)

- Move Daily rhythm into the Companion settings group and remove the now-empty Schedule & usage menu.

## 2.3.2 — Hot-fix update completion (2026-09-19)

- Let the rollback installer complete when an installed bootstrap file already exactly matches the verified staged release, while continuing to reject unrelated local edits.

## 2.3.1 — Reliable in-app updates (2026-09-19)

- Keep application-wide update operations visible to the browser while preserving installation and profile isolation.
- Allow a trusted release to adopt files that already exactly match it, so an official update can replace an earlier hot-fix without weakening local-change protection.
- Give the primary update action comfortable line height, spacing and mobile wrapping.

## 2.3.0 — Companion continuity and structured image routing (2026-09-19)

- Add Companion Continuity Settings under Models & providers with live provider/model dropdowns, the full Hermes reasoning-effort range, per-job guidance, bulk routing, failure details, and editable schedules/prompts.
- Migrate recognizable legacy Tamanitomo workers that bypassed Hermes through provider-pinned scripts back to native Hermes agent jobs without changing job IDs, schedules, enabled state, or run history.
- Keep script-only maintenance explicitly model-free while making every model-backed Tamanitomo job configurable through the UI.
- Give hosted image providers a labelled identity, wardrobe, scene, feeling, lighting, camera, and quality brief. Preserve ComfyUI's mapped-node contract: separately mapped parts remain separate, while single-prompt workflows retain their combined diffusion prompt.
- Bundle direct Mistral model and FLUX image-provider plugins, add Mistral model discovery, image-studio setup, and Voxtral voice model selection.
- Add photo multi-select album/delete actions and allow an existing vault image to become the companion's reference portrait.
- Preserve the current provider/model settings when repairing jobs and expose the expanded Hermes reasoning levels from `none` through `ultra`.

## 2.2.3 — Patch notes before updating (2026-09-19)

- Show the latest stable release notes directly in the Updates panel, with the Update button beneath them.
- Send the home-screen update notice to that review screen instead of installing immediately.
- Preserve line breaks, safely escape release text, and keep long notes usable on mobile in a bounded scrolling panel.

## 2.2.2 — Official release updates (2026-09-19)

- Publish a source-only `tamanitomo-release.zip` with an explicit file manifest and SHA-256 checksums for every stable release.
- The in-app update feature uses the latest published stable release for both ZIP and Git installations. It reports unavailable checks, rejects downgrades and missing assets, and verifies the downloaded asset digest when GitHub provides one.
- Dependency failures stop code installation. ZIP installs retain rollback backups and preserve executable permissions; locally edited installations are refused.
- Restart only the current workspace, retain Hermes profiles and private data, and wait for the new server instance before reconnecting.
- Include the onboarding and Termux lifecycle fixes already present on main.

## 2.2.1 — Interactive Onboarding, Intimacy Recalibration & Mobile Hardening (2026-09-17)

- **Interactive First-Visit Onboarding:** Zero-profile detection triggers guided birth wizard (Telegram BotFather/userinfobot guide, Relational vs Worker choice, 8 PMD-style dilemma questions, Sam companion card reveal with in-drawer customizer, and cloud device-code OAuth for xAI Grok and OpenAI Codex).
- **Default Companion Name:** Default companion is now officially **Sam** (gender-neutral).
- **Intimacy Recalibration & Neglect Decay:** Starts at Level 0 (Just Met), Stage 1 Friends floor (25 pts), Stage 2 Chemistry flirting (50 pts, can be lost from >24h neglect), Stage 4 Bonded taking ~2 months of daily interaction.
- **Finish Customizing Banner:** Secondary workspace notification banner and 3-card modal for Spoken Voice (with preview), Photos/Images, and Location/Sensors.
- **Emergency CLI PIN Reset:** `tamanitomo pin [--set PIN | --clear]` to inspect, change, or remove remote access network PIN.
- **Vault Backup & Export:** One-click web download (`/api/vault/export`) and `tamanitomo backup` CLI command.
- **Android & Mobile Hardening:** Battery optimization guidance for Termux, and Wi-Fi to cellular rollover delay/finish hooks for gateway stability.
- **Local LLM Memory Guardrails & On-Device Verification:** Automatic host RAM probing (`get_host_memory`), mobile platform detection (`is_mobile`), 2.8 GB model weight safety limit to prevent Android Low Memory Killer (LMK) crashes, 4,096-token context cap, 4-thread concurrency limits for mobile SoC thermal stability, mobile model recommendations (SmolLM2 1.7B, Qwen 2.5 1.5B, Llama 3.2 1B/3B), and live verified 17.3 t/s on-device inference on Google Pixel 8 Pro (Tensor G3).
- **"Keep It Local" Guided Onboarding:** 100% private on-device brain setup in the first-visit wizard, featuring hardware detection, mobile limitations guidance (RAM limits, battery drain, thermal pacing), 1-click downloading/configuration for mobile and desktop models, and automated companion activation.
- **In-App 1-Click Updates:** Interactive "⚡ Update Now" buttons in Settings and the Home notification banner for zero-terminal upgrades. Automatically fetches and applies verified releases, syncs dependencies, and reboots the workspace service with an automated browser reconnection heartbeat, while explicitly isolating the Hermes engine and leaving companion memories, journals, and vault files untouched.

## 2.2.0 — Initial Release (2026-09-17)

**Name change.** The project is now published as **tamanitomo** (魂の友 — "Soul of a Friend").
All user-facing references to `companion-kit` have been updated: CLI help, version strings,
User-Agent headers, Windows launcher (`tamanitomo.cmd`), git vault identity, setup wizard banner,
CI artifacts, and documentation. Internal script filenames (`companion_*.py`), config files
(`companion.json`), and environment variables (`COMPANION_HOME`) are unchanged in this release to
avoid breaking existing installations. A future compatibility pass will rename them with a
migration script.

## Unreleased — interface overhaul

**Licence.** Relicensed from AGPL-3.0 to PolyForm Noncommercial 1.0.0. Any noncommercial
purpose is permitted; commercial use is not. Fill in the `Required Notice:` line in `LICENSE`
with your name before publishing.

**Theming actually works now.** The stylesheet carried 492 hardcoded colours and 95 hardcoded
`rgba()` values that ignored the seven theme variables entirely, so every theme except the
default rendered partly in the default palette. All of them, plus 113 in inline styles, are now
design tokens, and themes derive the rest with `color-mix()`. Twelve themes (nine dark, three
light), a live accent-colour picker, and a Match-system mode. Appearance is stored per companion
on the server and mirrored to `localStorage`, so a companion looks the same on every device and
the first paint never flashes.

**Navigation.** Phones get a bottom bar instead of a hamburger drawer: four destinations you
choose, with More permanently in the last slot opening a directory of everything, each entry
explained in a line and starrable straight onto the bar. The desktop rail keeps its groups.

**Creating a companion is an interview.** Seven situational questions, one per screen, propose a
personality, a relationship frame, a pace and contact limits, then show every value they chose in
plain language. From there: save, edit, start over, or start over without the questions and fill
the fields in directly. Keyboard-answerable, skippable throughout.

**Fixed while rebuilding it:**
- Creating a companion from the browser always failed. The form submitted `explicit` and
  `relationship_pace`, which `POST /api/profiles` rejects as unknown setup answers. The existing
  test only ever sent a five-key subset, so nothing caught it. `relationship_pace` is now a real
  setup answer and reaches the saved config; `explicit` is no longer sent at all.
- The wizard had two `<select name="boundary">` controls, so the relationship frame chosen on
  step 2 was silently discarded on submit.
- Step 4's frames (`partner`, `crush`, `platonic`) were not real catalog keys, and its
  `explicit = boundary !== 'platonic'` rule set adult themes on frames that forbid them.
- The Profile ID field's `pattern` never validated anything: browsers compile `pattern` with the
  regex `v` flag, where its unescaped `-` is a syntax error.
- `.section-subheading` was used in the markup but never defined in the stylesheet.
- Theme preview swatches were hardcoded and disagreed with the themes they previewed; they now
  read the live token values.
- Identity opened on a configuration warning above the page title. It now opens on a profile
  header — who they are, their personality, your frame, their age and timezone.

**Licensing audit.** Added `THIRD-PARTY-NOTICES.md`. The interface icons derive from Feather
(MIT) and Lucide (ISC) and were shipping without their required notices; both are now reproduced.
Nothing else third-party is redistributed — Hermes (MIT), ComfyUI (GPL-3.0) and Ollama (MIT) are
fetched from their publishers, and release archives stay source-only, which is what keeps the
LGPL-3.0 `pyte` dependency an ordinary library import rather than a redistribution. The Civitai
downloader already read each model's permission flags but never showed them; it now displays
commercial-use, derivative, credit and relicensing terms before a download, marked when restricted.

**Tests.** 760 passing. New coverage for the appearance API, per-profile isolation and validation;
the full creation payload a browser actually sends; unknown-answer rejection; navigation/pin
allowlist parity; and the interview's derivation, checked against the real persona and
relationship-frame catalogs so it can never propose something the backend would refuse.

## 0.9.0-beta.1 — friend deployment beta

- Opening photo details never reveals an NSFW image; reveal is explicit inside the viewer. Unreviewed photos are no longer blurred automatically.
- Add push-to-talk browser voice with profile-owned STT/TTS, visible recording state, cancel, playback controls and bounded temporary audio.
- Add trusted release ZIP staging, managed-file checks, launcher-time updates, runtime locking and rollback copies.
- Add Windows-first setup/feature guide, private distribution plan and source-checked Android WebToApp settings.
- Improve mobile photo details and group update controls outside advanced command-line setup.

## Unreleased — companion editors and media studios

### Contextual feelings

- Browse older relationship experiences and select them for repair or correction, even after they leave the latest 30 records.

- Derive warmth, trust, hurt, irritation and missing-you indicators from expected routines, temperament and evidence-backed relationship experiences, alongside the existing authored mood.
- Carry the same live state into chat and scheduled context; preserve a returning human's preceding gap even when the new message is already saved.
- Add Together controls for overnight/weekly routines, temperament, connection, rupture, repair and correction. Repeated ruptures have stronger effects; repair softens without deleting history; corrections exclude mistaken records.
- Keep experience ledgers companion-private, protect settings with revisions, and make experience retries idempotent. Add a feelings shortcut beneath the companion's name in chat.
- Find the last human contact independently of the recent assistant-message tail, so long runs of updates do not hide it.

### Daily browsing and conversation

- Keep the composer and Send visible in short phone viewports; constrain long moods and names so they do not displace chat controls.
- Fix journal horizontal page overflow and add a collapsible vertical entry picker for narrow screens.
- Stop microphone capture and playback before refreshing Conversation or starting a new chat.

- Keep successful chat notices from covering Send; remove the empty welcome card when sending the first message.
- Resolve older chat media and album-copy references before gallery paging, preserving concealment across duplicates. Skip gallery scans for text-only history.
- Fix the empty Gateway & routine tab and make Gateway settings open its controls directly; add a shortcut from Hermes settings.

- Page through photo archives beyond 1,500 images; search and filter across the scanned collection. Preserve duplicate privacy and album membership, and update ratings across copies even outside the first page.

- Page through journal archives beyond 1,000 entries, search across the scanned archive, and load long entries fully in the reader. Keep the journal paging button reachable alongside the sticky list and report archive scan limits explicitly.
- Page through older conversations and messages using stable cursors, retaining the selected conversation even when it falls outside the latest 100. Loading earlier messages preserves the current scroll position and marks the beginning of the conversation.
- Put Conversation first, retain direct Hermes settings and Jobs & health navigation, and gather secondary destinations under More. Page search recognizes provider and administration terminology.
- Give chat the available window height, format saved messages with the shared escaped Markdown renderer, add date separators, and stop streamed replies pulling readers away from older messages.
- Ignore out-of-order conversation-history responses after another conversation has been selected.
- Group photos by day in a compact grid, move capture diagnostics into a disclosure, and keep journal/photo filters while visiting other pages. Keep the journal's selected entry and provide a sticky reading list on larger screens.

### Reliability and predictable editing

- Make unlimited proactive contact an explicit choice; numeric daily caps start at one, and Replies only is clearly labeled.
- Keep NSFW/unreviewed chat and activity images concealed until revealed, and fix authenticated URLs used for spoken replies and choosing photo references.
- Preserve existing human records when changing sharing, reject conflicting destinations, and apply the same photo validation and background-job synchronization from both preference editors.
- Scope operation results to their originating companion, retain status recovery after connection failures, and avoid blindly resubmitting work with an unknown outcome.
- Protect unsaved notes, documents, profile settings, and preferences with a visible indicator and Stay/Discard controls; recover the composer after failed transcription.
- Version page asset URLs by content so refreshed workspaces do not combine new and cached older scripts.
- Match whole mood words and suppress local negation in the basic wellbeing scorer; remove stale Markdown and JSON indicator snapshots when disabled or empty.

### Day continuity and self-directed images

- Every companion can retain previously / now / next, estimated activity duration and timed commitments in the presence ledger. Chat and scheduled context flag preparation deadlines and plans that will not fit; passing time never completes a promise automatically.
- Model-authored pose, hands, gaze, framing, props, expression and lighting direct images of the saved current moment. Recorded wardrobe and visual identity remain authoritative.
- Skip consecutive unchanged timeline scenes after a successful capture; failed renders remain retryable and unconfirmed carried state cannot trigger a photo.
- Existing histories require no rewrite. Repair updates shared presence guidance and adds the continuity instruction to existing pulse prompts while preserving custom text.

### Media deletion, provenance and pre-delivery review

- Add profile-scoped file deletion with change checks and protection for identity/reference files; preserve independent album copies.
- Show recorded generation sources and keep labels/ratings on album copies.
- Blur NSFW and unreviewed images by default, with per-profile preferences and manual rating controls.
- Review actual image pixels against intent before generation succeeds or the Companion outbox sends; hold mismatches and unavailable reviews, while supporting explicitly requested adult images.

### Guided Comfy workflow creator

- Compose six-section prompt recipes with checkpoint/model, encoder, VAE and LoRA slots, strengths, enable switches and architecture compatibility checks.
- Inspect Civitai versions and download selected SafeTensors/GGUF weights to a local or SSH Comfy host with SHA-256 verification and private API-key storage.
- Derive separate reference-based image-to-image presets from compatible single-sampler workflows.
- Install a reusable prompt-structure skill without overwriting companion-authored guidance.
- Disable supported Comfy API-node/frontend networking and telemetry in managed launches by default.

### Local stack setup and studio provider routing

- Added a host-local Ollama installer with official release SHA-256 verification, safe extraction, startup, streamed model downloads, and per-profile assignment after a real load test.
- Added Qwen3 4B/8B/14B Q4_K_M recommendations with weight sizes and memory guidance. Local assignment removes cloud fallbacks and resets companion job overrides.
- Added timezone dropdowns to onboarding and companion editing; timezone edits also update Hermes configuration.
- Discover configured/available Hermes image providers as named preset drafts, including OAuth; route saved presets through Hermes's plugin-aware dispatcher with a per-request provider selection.
- Added Civitai/Hugging Face model guidance and fixed preset ID creation on HTTP LAN origins.
- Normal browser launcher now supports host and LAN access by default with its access token; explicit reverse-proxy binds remain unchanged.
- Added the local stack guide and boundary tests for downloads, provider dispatch, profile isolation, and timezone synchronization.

### Companion editors and media studios

- Repair adopted identity documents by wrapping existing prose; empty markers no longer hide an authored appearance. Preserve self-authored blocks.
- Pass canonical reference images through saved Hermes image presets.
- Correct Pocket TTS decode-step arguments and enable voice-note conversion for local speech adapters.
- Move workspace renaming into the full companion editor; load current configuration and authored SOUL sections with backups and conflict checks.
- Add Image Studio under Identity: named provider/workflow presets, PlantMilk-style prompt components, per-category defaults, workflow downloads, LoRA controls, and ComfyUI installation on the Hermes host.
- Add Chatterbox, Audio8, Pocket TTS, and Qwen3-TTS through Hermes command providers, with provider-specific controls and independent or inherited companion settings.
- Integrate the complete installed Hermes dashboard and its WebSocket/API surface into settings while retaining native CLI setup.
- Add vault breadcrumbs/back navigation, recoverable trash, and server-enforced read-only protection for critical files.

## 2.2.0-beta.5 — hosted companion workspace

- Add an optional native Hermes streaming bridge and inline vault media in chat.
- Add an activity feed combining latest job results and saved creations.
- Add a persistent backend entry point and documented Authelia/Tailscale deployment.
- Verify signed-out access, admin policy, authenticated browser reads/actions, and native streaming with a local model fixture. All 548 tests pass on Linux.

## 2.2.0-beta.4 — conversation and gateway clarity

- Add a conversation header, collapsible history, remembered thread, saved draft, keyboard sending, and reply status.
- Support workspace display names for all profiles, including the default Hermes home.
- Show gateway checks alongside service controls and explain background independence.
- Validation: all 21 workspace contract tests pass; JavaScript syntax checked.

## 2.2.0-beta.3 — relationship preferences

- Enable the two computed indicators by default, preserving explicit opt-outs.
- Show indicators on Home and Together; move relationship pace and related choices into Preferences only.
- Add a first-install handoff checklist and document Android hosting limits.
- Validation: 543 tests pass on Linux/Python 3.14.

## 2.2.0-beta.2 — companion product interface

- Redesign the local desktop app with grouped navigation, quick page search, responsive layouts, and a content-focused home.
- Add photo browsing by day and collection, full-size viewing, downloads, and album copies for companion-owned images.
- Add a searchable journal reader for dated Lifelog entries and archived journals, and a creations library for writing, images, audio, video, and documents.
- Combine recorded life, photographs, and journal entries in the Timeline. Explain disabled, paused, missing, and failed photo capture states.
- Organize Hermes management and companion preferences into focused panels. Replace duplicate job listings with search, filters, run results, and schedule editing.
- Enforce profile boundaries and secret/symlink exclusions for new content routes; retain raw documents without executing their HTML.

## 2.2.0-beta.1 — companion workspace

- Bootstrap launchers for Windows/Linux, including Python provisioning when needed.
- Existing and kit-managed Hermes environments; explicit per-request profile scope.
- Profile creation/adoption/archive/restore; native-session chat and history.
- Primary/fallback providers, write-only credentials, native setup consoles, advanced config,
  gateway controls, job history/actions, and application of pins to existing jobs.
- Lived-state timeline, relationship preferences/milestones, vault browsing/search/edit/export.
- Private media authentication, cross-origin write protection, optimistic note editing.
- Normalize Hermes's trimmed job prompts when checking fingerprints; keep meaningful user edits protected.
- Reserve memory-omission disclosures when relationship preferences consume context.

This is a private-test beta. Native Windows and live model/day-long acceptance are not implied by unit tests.
See docs/DESKTOP.md for the complete limits and setup steps.

# Changelog

Versions are `companion --version`. Dates are the day the work landed.

## 2.1.0 — 2026-09-10

The first install by someone other than the author, and what it found. Ash, a
cold install on another machine from the release archive against Hermes 0.21.1,
is recorded in `docs/REVIEW.md`.

### Fixed

- **The kit would not run on Python 3.11 at all.** A backslash escape inside a
  nested f-string expression in `companion_wizard.py` is 3.12+ syntax; on the
  3.11 the README promises and CI tests, twenty-four tests errored out on the
  `SyntaxError`. The suite now passes on 3.11 and 3.14, and 3.14 joins the CI matrix. The 3.11 lane
  that should have caught this has existed all along; no run of it has ever been observed.
- **`companion init --home X` was rejected.** `--home` is accepted on either
  side of the subcommand now, which is what everybody tries first.
- **A birthday was computed in the caller's timezone rather than the
  companion's.** A companion whose day had not turned over yet could be told it
  was her birthday, or not told on the day. Her own timezone decides.
- **A likeness stored as a JPEG or WebP was invisible.** `save_reference` wrote
  `reference-portrait.jpg`; everything that looked for it looked only for the
  `.png`. The reference existed and was never passed to a provider. Replacing a
  likeness now also removes the old one, so there is exactly one canonical face.

### Added

- **A photograph can become the appearance section.** Upload a likeness in the
  app, and `companion_vision.py` asks a model to read the face and propose the
  locked `appearance` block, rendered through the same interview fields and the
  same fixed order a typed description uses. It proposes; a person reads it and
  keeps it. Nothing reaches `SOUL.md` without that. This is the only part of the
  kit that calls a model, and the only thing in the app that costs money; it runs
  with `--ignore-rules`, so it is a model looking at a picture rather than the
  companion looking at a picture of herself.
- The app grows `GET/POST/DELETE /api/portrait`, `GET /media/portrait` and
  `POST /api/portrait/describe`; the write still goes through the section editor
  that already existed.
- `hermes -p <profile> chat -q 'hello' --oneshot --accept-hooks` is documented as
  the hook-consent path for an unattended install, in the README, the migration
  steps, doctor and setup's own next steps.
- The README says to probe a model chain rather than pick it from a catalog
  listing, and that a fresh install generates no image until a model-backed job
  has recorded a present.

### Also fixed, found by running that loop against a real model

- **The compiled image prompt carried instructions meant for her.** The
  appearance section ends by telling her how to maintain a wardrobe, with the
  command that does it, and the identity block was handing that to image
  providers as part of her face. The template marks that paragraph as excluded
  from prompts; a SOUL written before the marker is cut at the paragraph holding
  the first inline code span. This predates the vision work and affected every
  companion.
- The vision prompt asks for a complete sentence rather than a fragment, so a
  described face is shaped like a typed one, and it refuses to describe the
  absence of something — "no visible facial hair" is a phrase an image generator
  will draw around.

## 2.0.0 — 2026-09-10

The v2 line, built from the three review rounds recorded in
`notes/companion-kit-*-2026-09-10.md`. Its target: install Hermes,
configure a messaging platform, run one command, meet your companion — and have
that companion stay honest when the model is down.

### Phase 0 — stabilize (2026-09-10)

- Reflections are recorded from one JSON file (`companion_self.py ledger --file`)
  instead of quoted shell arguments. An apostrophe in a remembered sentence no
  longer breaks an unattended daily, weekly or monthly run. A rendered-prompt
  scan in the suite fails if any cron template goes back to quoting prose.
- `companion_prune.py` removes files older than seven days from the only two
  directories that hold disposable work: staged prose and Hermes's capture of
  each job's stdout. Both are resolved from the profile config, never from an
  argument. The weekly hygiene job runs it dry first.
- `companion doctor` reports staging sizes, the episode ledger size, and any job
  running on a model other than the profile default.
- Setup replaces the stock `SOUL.md` that `hermes profile create` writes, after
  backing it up, so a fresh profile no longer keeps Hermes's system prompt in
  place of the companion's identity. A SOUL someone else wrote is still left
  alone, and doctor now says so instead of staying quiet.
- `bin/companion` is a thin entry point; the command lives in `kit/cli/`.
- `companion repair` can re-render installed job prompts from the current
  templates, so a prompt fix reaches companions that already exist. The kit
  records a hash of each prompt it writes and never overwrites one you edited
  without `--prompts force`, which backs your version up first.
- `companion --version`, and this file.
- The questionnaire test no longer touches a real terminal.

### Phase 1 — present, loops, resilience (2026-09-10)

- The presence state gains `wants` and `private_stance`, and `Emotive.md` is
  rendered from it rather than written by hand. One state, one author.
- Open loops become a ledger, each entry carrying a `gentle_use` line saying how
  and when to raise the thing.
- `ActiveContext.md` is assembled by `companion_active.py` from the state, that
  ledger and whatever sensors exist. The model no longer writes it. An absent
  sensor produces no section rather than a claim.
- A no-agent present advancer carries the state forward when no model is
  available, marked `confirmed: false`; the hook says `UNCONFIRMED since HH:MM`.
- The pulse and autonomy loop get an assembled pre-read through `--script`;
  autonomy is gated by `--monitor-script` on a stable fingerprint; both use
  `--continuity`.
- `companion models` chooses per-tier models and reasoning effort and writes up
  to two `fallback_providers` entries into Hermes's config.
- A no-agent health watch, and `companion status`.
- The continuity hook waits at most two seconds on a contended lock.

### Phase 2 — outreach and senses (2026-09-10)

- Nothing sends directly any more. Jobs queue into `companion_outbox.py`; a
  no-agent dispatcher decides what leaves, one message per run, enforcing
  expiry, earliest-send time, the sleep window, per-content permission and the
  daily cap. Expired messages are dropped rather than delivered late.
- Being visibly awake — a message from the human in the last 45 minutes — steps
  past the sleep window without raising the cap.
- Five optional sensors write into `ambient/`: weather, daylight, dates, care
  follow-ups, and the relationship thread. A sensor with nothing to say writes
  nothing and removes its stale file.
- A morning job and a wind-down job on the edges of the sleep window, moving
  with it. Overnight is script-only.
- Adaptive quiet hours, opt-in: evidence only, a fortnight not a night, half an
  hour at a time, never below six hours, mentioned once when it moves.
- Setup asks for a location, which sensors to switch on, and whether unprompted
  photos and voice notes are allowed.

### Phase 3 — agents and memory (2026-09-10)

- Three agent types chosen first at setup — companion, colleague, quiet worker —
  deciding which jobs are installed and what the SOUL says the agent is.
- Memory caps sized at the end of setup from the context window and the rendered
  SOUL, written where Hermes reads them, instead of its 2,200/1,375 defaults.
- The vault becomes a local git repo with a commit job, and `companion restore`
  brings an old version back beside the current file rather than over it.
- Standing instructions and a relationship ledger, both injected every turn.
  Zero-budget sections are now named in the omissions line rather than being
  quietly absent.
- People-sharing setting: one record of the human across agents, or private.
- Missions with exclusive claims and self-releasing stale ones, worked in
  configurable autonomy windows.
- A check-in gated on Hermes's `on_session_end`, reflecting within minutes of a
  conversation rather than at 04:00, and silent otherwise.

### Phase 4 — identity (2026-09-10)

- A birthdate instead of a frozen age. The age is computed at render time and on
  every turn, the appearance paragraph moves with it, and the hook marks the day.
- SOUL.md gains section markers; `companion identity <section> --rerender`
  rebuilds exactly one and verifies every other byte is unchanged.
- The build and the human's boundaries are LOCKED against the companion; the
  self-edit helper refuses a block that restates them.
- Texting style, pet-name mode, a "won't do" list, and a paragraph the human
  writes that the companion cannot edit or argue with.
- Five more relationship frames that are not a romance with the romance removed.
- A durations sensor: "married 13 years", counted rather than remembered.

### Phase 5 — media and voice (2026-09-10)

- `companion_portrait.py` compiles the image prompt: locked appearance in a
  fixed order, then the recorded scene, then the style. It refuses when there is
  no state, because a scene invented for the camera is the thing to prevent.
- Timeline retention is a storage budget rather than thirty days. Albums keep
  copies that retention never touches, and take the human's own pictures too.
- Voice notes go through the outbox with the words beside the audio. Cloning
  writes Hermes's own neutts keys and requires saying the recording is yours.

### Phase 6 — the app (2026-09-10)

- `companion app`: one companion on localhost — now, timeline scrubber, loops
  and missions, what she knows, settings, identity, health and token usage.
- Two optional computed bars, written as signals rather than a nag schedule.

### Phase 7 — adoption (2026-09-10)

- `upgrade --soul keep` leaves an existing SOUL byte-for-byte alone.
- Verified on a simulated long-lived agent: memories, session database and vault
  all stay where they are while the machinery is installed around them.

### Phase 8 — docs (2026-09-10)

- `docs/CONCEPTS.md` (why it is shaped this way), `docs/REFERENCE.md` (the full
  command, file and scripting reference) and `docs/TROUBLESHOOTING.md` (organized
  by symptom). The README was rewritten as an explainer and installation guide;
  the reference material it had accreted moved into `docs/REFERENCE.md`, and the
  stale claims in it — six jobs, six relationship frames, thirty-day image
  retention, Hermes's default memory caps — were corrected or removed.
