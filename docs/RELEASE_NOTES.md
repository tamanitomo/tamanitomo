Tamanitomo 2.3.0 adds explicit model control for companion continuity and structured cross-provider image prompts.

### Install

Download **tamanitomo-release.zip** below, extract it into its own application folder, and run the Tamanitomo launcher. Keep your Hermes home and vault outside that folder. The automatically generated GitHub source archives are for development; use the attached release ZIP for in-app updates.

### Update

Open **Settings → App & access → Updates** in your desktop or mobile browser. When the release is available, review these notes and choose **Update to v2.3.0 Now**. The host downloads and installs the application and restarts the workspace. Your Hermes profiles, credentials, memories, journals and vault remain in their existing external locations.

### Companion continuity

Every model-backed Tamanitomo cron job can now be routed from **Settings → Models & providers → Companion continuity**. Each job shows its provider, model, reasoning effort, recommendation and last failure. Script-only maintenance remains model-free. Repair safely migrates older provider-pinned continuity scripts to native Hermes model routing while preserving their history.

### Images across GPT, Grok, Mistral and ComfyUI

Hosted image providers receive a labelled brief with separate identity, wardrobe, scene, feeling, lighting, camera and quality constraints. ComfyUI workflows retain their native mapping behavior: each named mapping is written to its own node input, and only single-prompt workflows receive a combined diffusion prompt. This release also bundles Mistral model and FLUX image-provider support.

### Photos and identity

Photos can be selected in batches for albums or deletion, and any eligible vault image can become the companion's reference portrait.

Updates continue to verify the published release asset, stop on dependency failures, retain rollback files, and wait for the updated server before reconnecting.

See CHANGELOG.md for details. The adjacent `.sha256` file verifies the complete ZIP.

### Validation scope

The release workflow runs the full test suite on Linux and update-specific tests on Linux, macOS and Windows. The broader existing macOS/Windows test matrix has known failures and is not claimed to pass in this release.
