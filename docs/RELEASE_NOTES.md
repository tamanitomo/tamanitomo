Tamanitomo 3.6.3: one place to choose models, routines that stop failing, and a companion who keeps the thread.

- **Pick up where you left off.** A conversation still starts fresh each morning so replies
  stay quick, but your companion now sees the last few messages from before the reset and
  from your other channels (Telegram, the app), so the thread carries over. It sits in a
  space of its own and pushes nothing else out. On by default; Settings → Awareness.
- **Web pages read on your machine.** Pages your companion opens are fetched straight from
  their own site and turned into text locally. No reading service sees them, and a failed
  read is never quietly handed to a free online one. Pages that need a browser to appear
  point at the browser tool, which also runs locally. Settings → Awareness.
- **One model plan.** Settings → AI models → Models replaces four separate screens: choose
  what answers conversations, runs everyday routines and reflections, and what to fall back
  to, then apply it to any of your companions. Every routine, Hermes's helper tasks and the
  scheduled-job default follow, and each companion says what is still off the plan. Changes
  land on the next message.
- **Leaner conversations.** Hermes re-sent every earlier copy of the continuity snapshot
  with each message, so most of a long evening's request was old copies. Now only the
  newest goes, so replies start sooner and more real conversation fits before it is
  summarised.
- **Routines that stop failing.** Scheduled prompts run commands directly (a scheduled run
  cannot approve the wrapped kind, and that cost one companion most of its updates in a
  day); a second update in the same quarter hour lands; errors name exactly what to fix;
  and facts or moments with an unfamiliar category are kept instead of refused.
- **Quicker pages.** The chat feed no longer pages through scheduled runs, and the Models
  page no longer waits for OpenRouter's model list.
- **Also in this release:** a signed-in ChatGPT workload preset, independent projects and
  friendships that carry on while you are away, trusted messages counted for daily contact
  and quiet-hours learning, support for store-managed Hermes at the morning reset, and
  Windows fixes.

**After updating,** open Settings → Scheduled jobs and choose **Install / repair** (or apply
your model plan), then restart the gateway once, so Hermes loads the new plugins.

### Install or update

Download **tamanitomo-release.zip** and its SHA-256 checksum below. Extract the ZIP into its own application folder and run the Tamanitomo launcher, or use the in-app updater. Keep your Hermes home and vault outside the application folder. Use the attached release ZIP for updates; GitHub's generated source archives are for development.

Existing Hermes profiles, transcripts, memories and vault files need no migration. Android/Termux's precompiled wheel download remains available on the `wheelhouse-aarch64` branch.
