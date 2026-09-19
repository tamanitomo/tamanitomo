# Official releases and updates

All installations use the stable releases at https://github.com/tamanitomo/tamanitomo/releases/latest. For a new installation, download the attached **tamanitomo-release.zip**, extract it into a dedicated application folder and run `tamanitomo` (or `tamanitomo.cmd` on Windows). GitHub's automatically generated source archives do not contain the installed release checksum manifest and cannot use the ZIP updater.

Keep Hermes profiles, credentials, memories, models and vaults outside the application folder. The update archive contains application files from `release-files.json`; it never contains your running instance or Python environment.

## Update from a phone or desktop browser

Open **Settings → App & access → Updates**, select **Check for updates**, then **Update to v… Now**. The host downloads the official asset, verifies its file manifest and available GitHub asset digest, installs changed Python requirements, backs up the old application files, applies the update and restarts the workspace. Leave the browser open while it reconnects. Hermes itself is not updated or restarted.

Git installations fetch the published release tag and require a clean checkout that can fast-forward. They do not stash changes or reset local work. ZIP installations refuse modified managed files or collisions with unmanaged files. Network errors are shown as errors rather than “up to date.” A failed dependency installation leaves the application code unchanged, although pip may already have changed some packages; rerun the update after resolving the error.

## Source copies and existing installations

An extracted official release includes `SHA256SUMS.json`. A manually copied source folder does not. Do not fabricate a manifest for unverified code: extract an official ZIP into a new application folder and point the existing launcher/service at it, retaining the same external Hermes home and workspace state. Development checkouts can use the release-tag update path when clean.

## Recovery

Previous application files are stored under `.update-backups/<id>`. Stop the workspace before restoring a backup, including its `SHA256SUMS.json`, and remove application files introduced by the failed update. Alternatively, extract the previous official ZIP into a fresh application folder and configure the same external Hermes home and workspace state. A rollback of code is not a restore of companion data. Python dependencies may require reinstalling from the previous requirements file.

## Publish a release

1. Update `VERSION`, `CHANGELOG.md` and `docs/RELEASE_NOTES.md`.
2. Run the Python suite and JavaScript UI checks. Build with `python tools/build_release.py --output build/tamanitomo-release.zip` and verify an upgrade in a disposable installation.
3. Commit the source, push it, then push the matching `vX.Y.Z` tag.
4. The Release workflow reruns tests, builds the allowlisted ZIP plus its checksum, and publishes them together. The app checks only published stable releases with the expected asset.

A package's internal checksums prove consistency, not publisher identity. Download from the official release page.
