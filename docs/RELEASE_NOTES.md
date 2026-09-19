Tamanitomo 2.2.3 puts the patch notes directly in the app before installation.

### Install

Download **tamanitomo-release.zip** below, extract it into its own application folder, and run the Tamanitomo launcher. Keep your Hermes home and vault outside that folder. The automatically generated GitHub source archives are for development; use the attached release ZIP for in-app updates.

### Update

Open **Settings → App & access → Updates** in your desktop or mobile browser. When a release is available, the app shows its patch notes first and places **Update to v2.2.3 Now** beneath them. The home-screen update notice opens this review screen instead of installing immediately. The host downloads and installs the application and restarts the workspace. Your Hermes profiles, credentials, memories, journals and vault remain in their existing external locations.

Release notes are safely displayed as text, retain their line breaks, and scroll within a mobile-friendly panel when long. Updates continue to verify the published release asset, stop on dependency failures, retain rollback files, and wait for the updated server before reconnecting.

This release also includes the onboarding and Termux lifecycle fixes from main. See CHANGELOG.md for details. The adjacent `.sha256` file verifies the complete ZIP.

### Validation scope

The release workflow runs the full test suite on Linux and update-specific tests on Linux, macOS and Windows. The broader existing macOS/Windows test matrix has known failures and is not claimed to pass in this release.
