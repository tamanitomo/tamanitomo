Tamanitomo 3.6.0: one chat dock, five destinations, and resilient model routing.

- **One conversation, wherever you are.** The floating chat dock is the sole chat surface: a desktop card and a phone bubble that opens into a 65vh sheet. Replies stream through Hermes and recover after a dropped connection without resending the turn.
- **Five clear destinations.** Home, Journal, Vault, Photos and Settings lead the workspace. Relationship, calendar, identity and companion tools remain available as subviews.
- **Provider recovery.** Configured workers and chat can move from a primary provider to a secondary and then a local model on transient errors. The model probe tests one saved route without changing configuration.
- **A complete Vault.** The existing CodeMirror editor, tabs, autosave, exact-byte backups and conflict recovery are preserved. Notes gain a derived link index, backlinks, outline, properties, safe embeds and link-aware file actions.
- **More portable hosts.** Memory, process, locks, launchers and IPv6 browser URLs handle platform differences explicitly. Unknown hardware readings remain unknown.
- **A smaller, clearer core.** Python is formatted consistently, deterministic limits and evidence-backed memory are documented, and seven focused test suites cover the application.
- **Safer updates.** The updater pauses active dispatcher schedules and waits for dispatcher work to finish before changing application files, then restores the schedules it paused.

### Install or update

Download **tamanitomo-release.zip** and its SHA-256 checksum below. Extract the ZIP into its own application folder and run the Tamanitomo launcher, or use the in-app updater. Keep your Hermes home and vault outside the application folder. Use the attached release ZIP for updates; GitHub's generated source archives are for development.

Existing Hermes profiles, transcripts, memories and vault files need no migration. Android/Termux's precompiled wheel download remains available on the `wheelhouse-aarch64` branch.
