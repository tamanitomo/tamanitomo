Tamanitomo 2.2.2 makes the official GitHub release the shared update source.

### Install

Download **tamanitomo-release.zip** below, extract it into its own application folder, and run the Tamanitomo launcher. Keep your Hermes home and vault outside that folder. The automatically generated GitHub source archives are for development; use the attached release ZIP for in-app updates.

### Update

Open **Settings → App & access → Updates** in your desktop or mobile browser, check for updates, then select **Update to v2.2.2 Now**. The host downloads and installs the application and restarts the workspace. Your Hermes profiles, credentials, memories, journals and vault remain in their existing external locations.

Updates now check the published release and asset, show connection failures honestly, verify available download digests, stop on dependency failures, and retain a backup of the previous application files. Locally modified application code requires manual attention. Reconnection waits for the updated server.

This release also includes the onboarding and Termux lifecycle fixes from main. See CHANGELOG.md for details. The adjacent `.sha256` file verifies the complete ZIP.

### Validation scope

The release workflow runs the full test suite on Linux and update-specific tests on Linux, macOS and Windows. The broader existing macOS/Windows test matrix has known failures and is not claimed to pass in this release.
