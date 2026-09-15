# Private distribution and updates

Use a private GitHub repository with individually authorized access and tagged releases. An organization-owned repository can give friends read-only repository access; personal-repository collaborator permissions are less granular. Share the **built Companion Kit release ZIP**, not GitHub's automatically generated source archive and not a copy of your live working directory. Keep companions, model weights, voices, vaults, environment files, credentials and private workflows out of the repository/release.

For this beta, a recipient downloads your trusted release asset while signed into GitHub, then opens **Hermes settings → Companion Kit updates → Install update package**. Select the ZIP. Kit verifies its complete SHA-256 file manifest and stages it. Stop the Kit host using Ctrl-C in the launcher/terminal (closing a browser tab does not stop the host), then double-click `companion.cmd` again. The launcher applies the staged code update before checking dependencies. Hermes gateway and companion data are separate.

The updater refuses development checkouts and locally modified release files. It preserves unmanaged files, backs up previous release code under `.update-backups`, and restores that code if file installation fails. It does not migrate or overwrite the Hermes home or vault. Keep those directories outside the Kit code folder. Backups of your data are still recommended before any major application upgrade.

A package's internal checksum proves consistency, not publisher identity: install ZIPs only from the trusted private release page. For a later automatic **Check for updates** feature, use GitHub Releases metadata and a separate read-only credential belonging to each recipient (fine-grained token scoped to that repository with Contents: read where GitHub supports that access relationship; otherwise use a GitHub App or retain signed-in manual downloads). GitHub currently documents limitations for fine-grained tokens used by outside/repository collaborators, so test access before promising token-based updates. Keep credentials on the Hermes host, never in browser JavaScript or an APK. Download assets through GitHub's authenticated release-asset API and strip authorization when following redirects to a different host. Verify the published asset digest, then use the same staging/apply mechanism. Do not share your publisher token or run arbitrary `git pull` over a modified installation.

No repository or automatic update feed is configured by this package. The manual package button works without a repository integration. If you host everybody on one server instead, updating that server updates the UI for everyone, but you then own their availability, account isolation and backups. Separate friend-owned installations are the simpler privacy boundary for this beta.

## Publisher procedure

1. Set a new `VERSION`; update CHANGELOG and user documentation.
2. Run the test suite and browser checks. Build with `python tools/build_release.py --output build/companion-kit-VERSION.zip`.
3. Test extraction, first launch, one conversation, and an upgrade from the previous release in a disposable installation.
4. Create a private tagged release; upload the built ZIP and a SHA-256 of the complete ZIP. Explain changes and any manual migration steps.
5. Give the recipient repository access. They download the asset and use Install update package.

## Recovery

If staging fails, no installed code is changed. If launch says installed code changed, preserve those edits and install into a fresh folder rather than forcing replacement. If a completed update has a runtime regression, close the host, copy the contents of the desired `.update-backups/<id>` over the code folder (including SHA256SUMS.json), remove files introduced by the newer release if applicable, and relaunch. Alternatively extract the previous full release into a new code folder and select the same existing Hermes installation and vault. Never restore an old vault over newer companion memories merely to roll back code.

Sources: [GitHub Releases API](https://docs.github.com/en/rest/releases/releases), [fine-grained token permissions](https://docs.github.com/en/rest/authentication/permissions-required-for-fine-grained-personal-access-tokens).

Additional authentication reference: [GitHub token limitations](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens).
