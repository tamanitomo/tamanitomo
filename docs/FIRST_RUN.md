# First install for a friend

Linux has been exercised; native Windows and Android still need device acceptance tests. If you are handing the kit to someone else, share a clean checkout or the release ZIP — never your own working directory, Hermes home, or vault.

## Windows first

1. Extract the ZIP into a permanent writable folder and double-click `tamanitomo.cmd`. First launch downloads dependencies and opens the local app.
2. Choose **Kit-managed Hermes** and complete installation, or choose **Existing Hermes** if already installed. See [desktop setup](DESKTOP.md) for platform prerequisites and installation details.
3. Create a new companion with its own identity and vault. Configure a primary model and fallback providers with the recipient's own credentials.
4. Run **Test saved model**, which checks only the selected provider with fallback disabled, then send a message from the floating **Chat** dock. These are real provider requests and can cost money. Verify the response appears in the dock’s history.
5. Review and approve the companion hooks, choose gateway ownership, configure Telegram if wanted, and install/start the gateway. Check installed schedules and errors in **Settings** before activating routines.
6. Check the same companion from the app and Telegram. Confirm a scheduled job completes, its journal/content appears in the app, and restarting the machine restores the gateway. These are acceptance checks, not already verified promises for Windows.
7. Photos remain optional. Configure an image provider, try one image, and choose a recurring schedule only when comfortable with the cost. Check **Photos**, the recorded day in **Journal**, and **Vault** after generation.
8. Set relationship pace in **Settings**. The two computed indicators start enabled and can be switched off there.

A fallback needs its own usable allowance. Hosting on a low-power device does not eliminate cloud inference or image charges. A consumer Grok subscription alone is not proof that the selected Hermes API credential has a usable allowance: check the actual xAI account, key, and usage/billing screen. Current [Grok plan documentation](https://docs.x.ai/grok/faq) describes shared usage, while [API billing documentation](https://docs.x.ai/developers/faq/billing) describes team credits and invoicing. Test the credential in Hermes before relying on it.

## Hosting on an Android phone

Hermes documents Termux as a best-effort platform. Its tested core includes CLI, cron, Telegram, and memory integrations. Android can suspend background work. Docker isolation and local faster-whisper are unavailable, and browser setup is experimental. See the official [Termux guide](https://hermes-agent.nousresearch.com/docs/getting-started/termux).

Tamanitomo's dependency bootstrap and gateway service controls have not been validated on Termux. This ZIP is not yet a verified one-click Android host installer. Do not assume the Linux service buttons work on Android.

Before using a phone as the permanent host, validate its Android version, Python/dependency installation, app startup, Hermes gateway supervision, screen-off job execution overnight, reboot recovery, and vault backups. Keep paid photo schedules off until those checks pass. A spare plugged-in phone is a candidate for a core-feature pilot; a full desktop-equivalent environment is not established by successful Hermes installation alone.

For remote Windows access, use the private access options in [DESKTOP.md](DESKTOP.md#private-remote-access-and-android). The Android APK is future work. Keep one authoritative companion home and vault; do not independently create the same companion on two hosts and expect shared history.
