# Backup and recovery

Open **Settings → System → Diagnostics → Complete companion recovery** to download
a recovery ZIP. The app verifies every archived file and records the time of the
last verified export. Keep another copy on a separate device.

The bundle contains the selected companion's profile, identity, configuration,
conversation database, saved state, schedules and the entire shared vault,
including its Git history. A vault shared by several companions therefore contains
their vault content too; other companions' Hermes profiles are not exported.
SQLite is snapshotted through its backup API, including committed WAL data. A
shared transcript database is scoped to the selected profile, or refused if its
ownership cannot be established safely.

Runtime caches, locks, processes and the Hermes application installation are
excluded. Model weights and other services are not installed by recovery. The
manifest lists excluded paths. File symlinks are recreated when the host supports
them; linked directories are materialized. Supported external linked files are
copied so the bundle does not depend on their old host. Unsupported links fail
explicitly.

Saved account credential files and recognized configuration secrets are excluded
by default. **Include saved account credentials** opts them in. The archive is not
encrypted, and even a bundle without saved credentials can contain secrets you
typed into a conversation, document or historical vault revision. Store and move
it as private personal data.

## Restore or move a companion

1. Choose the ZIP under **Restore or move a companion**. The preview checks its
   format, paths, sizes and SHA-256 hashes before showing the companion and date.
2. Enter two **new** folders on the machine running Tamanitomo: a Hermes root and
   a vault. Existing folders and overlapping destinations are refused.
3. Restore, then choose **Open restored companion**. The original remains intact.
4. Reconnect accounts if credentials were excluded. Install or select a working
   Hermes runtime and inspect the restored identity, history and vault.
5. Check the model plan and gateway, then enable only the schedules and outreach
   you want. Restored model jobs and outreach start paused; merely restoring a
   backup does not send a message.

Do not run two active gateways for the same restored account. For a move, stop the
old host's gateway before enabling the replacement. Paths referring to the old
Hermes home or vault in configuration and scheduled jobs are rebased; external
services and paths still need review. Original prose and history retain their
recorded paths as provenance.

## Command line

```sh
./tamanitomo --home /path/to/hermes/profile backup --output /private/companion.zip
./tamanitomo recover /private/companion.zip
./tamanitomo recover /private/companion.zip --root /new/hermes --vault /new/vault
```

Add `--include-credentials` to `backup` only when you want saved account secrets in
the unencrypted archive. Running `recover` without destination arguments verifies
and describes the bundle without writing a restored companion.

The older **Export vault** button still exports vault contents only. The
`restore <path> --commit <id>` command still recovers an older individual vault
file beside its current version; use `recover` for a whole companion bundle.

## What verification establishes

Hashes detect missing or altered archive members, and restore rejects unsafe paths,
unexpected files and unsupported formats. Hashes are not a signature identifying
the author. Open only backups you trust. An export is a collection of file
snapshots, not a single transaction across every running service; export during a
quiet period when possible. Recovery preserves data and pauses automation, but
provider sign-ins, device services and reboot behavior need checking on the new host.
