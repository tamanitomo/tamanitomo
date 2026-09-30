Tamanitomo 3.6.2: a companion that actually knows you, and a steadier pulse.

- **She knows all of it, not two facts.** What is known about you now has its own room in
  every turn's context, sized from the model's window, instead of a slice so small that
  two facts out of seventy-eight got through (and often none). Facts that matter most,
  such as health, lead the list and are the last to be cut. Fixed a bug that listed
  categories backwards and made `history` facts unreachable.
- **No more duplicate memories.** A fact is no longer stored if Hermes's own notes
  (USER.md or its archive) or the ledger already say it. The nightly reflection now
  reasons about each fact against everything known, judging by meaning: new, more proof of
  an existing fact, a correction, or already known. Repeats are kept as extra evidence
  under the fact instead of new rows. One-off events (what you ate, when you woke) stay in
  the journal; lasting patterns become facts. Passing or unclear things, such as an
  illness, become a follow-up rather than a fact.
- **Weekly tidy-up.** The hygiene job merges leftover duplicates, promotes the facts that
  would hurt to forget, and writes a readable facts index next to the ledger.
- **A calmer pulse.** The pulse and autonomy loops no longer wake on nearly every tick
  because ambient sensors and re-worded plans changed the fingerprint; they now run on
  real transitions.

### Install or update

Download **tamanitomo-release.zip** and its SHA-256 checksum below. Extract the ZIP into its own application folder and run the Tamanitomo launcher, or use the in-app updater. Keep your Hermes home and vault outside the application folder. Use the attached release ZIP for updates; GitHub's generated source archives are for development.

Existing Hermes profiles, transcripts, memories and vault files need no migration. Android/Termux's precompiled wheel download remains available on the `wheelhouse-aarch64` branch.
