Tamanitomo 3.6.1: connected accounts you can actually see, and put to work in one step.

- **Connected accounts & routing.** A new settings panel shows every provider this
  companion can reach — API key, OAuth sign-in, or reachable endpoint — next to the
  primary model, tier status, and how many jobs follow it versus have their own
  override. "Use everywhere" points the primary model, both tiers, and every shipped
  job at one account in a single operation.
- **OAuth sign-ins are visible immediately.** Hermes's own record of a Grok or ChatGPT
  sign-in now shows up in the provider list right away, marked active, instead of
  waiting on the model cache to notice. "Connect Grok" / "Connect ChatGPT" buttons use
  the existing device-code flow as an alternative to the raw Hermes console.
- **Connecting an account now offers to use it.** Right after signing in, choose
  whether that account should generate this companion's images (with a style picker,
  offered only when Hermes reports an image-capable provider for it) and then whether
  it should provide voice (with a voice picker) — no more separate, undiscoverable
  steps to actually put a freshly connected account to work.
- **A steadier Vault.** Adds the Living Archive presentation and fixes date/datetime
  properties not serializing correctly in the link index.
- **More portable hosts.** Further process, file, and locking fixes for Windows and
  macOS surfaced by the platform test matrix.

### Install or update

Download **tamanitomo-release.zip** and its SHA-256 checksum below. Extract the ZIP into its own application folder and run the Tamanitomo launcher, or use the in-app updater. Keep your Hermes home and vault outside the application folder. Use the attached release ZIP for updates; GitHub's generated source archives are for development.

Existing Hermes profiles, transcripts, memories and vault files need no migration. Android/Termux's precompiled wheel download remains available on the `wheelhouse-aarch64` branch.
