# Turn an Old Android Phone into a 24/7 Dedicated Companion Server

This guide explains how to use an old Android phone to run your companion AI 24/7 using **Termux**, **Hermes Agent**, and **Tamanitomo**.

By using cloud inference (such as **xAI Grok**, **OpenRouter**, or **OpenAI OAuth**), the phone requires minimal CPU and RAM (~200MB RAM, <3W power), stays completely cool, and reliably serves your companion around the clock.

---

## Why An Old Phone Is The Ideal Companion Host

1. **Always On & Dedicated**: The phone sits plugged into a charger on your desk or bookshelf, connected to Wi-Fi.
2. **Built-in Battery Backup**: If power goes out or flickers, the phone's battery keeps your companion running without interruption.
3. **Chat on Your Everyday Device**: You chat with your companion directly on **Telegram** (voice notes, text, autonomous check-ins) from your daily iPhone, Android, or laptop.
4. **Access the Web Workspace from Your Laptop**: The Tamanitomo web UI is served over local Wi-Fi at `http://<phone-ip>:38439`, allowing you to inspect memories, journal, timeline, and identity from any browser on your network.

---

## Step 1: Install Termux on the Old Android Phone

> [!IMPORTANT]
> **Do NOT install Termux from the Google Play Store** — that version is abandoned and cannot update packages.
> Install from **F-Droid** or GitHub.

1. On the Android phone, download and install **F-Droid** from [f-droid.org](https://f-droid.org/).
2. Open F-Droid and install **Termux** (package: `com.termux`).
3. *(Recommended)* Also install **Termux:Boot** from F-Droid so your companion automatically boots when the phone restarts.

---

## Step 2: Configure Android Battery Settings

Android will aggressively kill background processes if battery optimization is enabled.
1. Go to Android **Settings** → **Apps** → **Termux**.
2. Tap **Battery** (or Battery Saver / Power Management).
3. Select **Unrestricted** (or **Don't optimize** / **No restrictions**).
4. If your phone has an app killer (Samsung, Xiaomi, Huawei), disable aggressive app freezing for Termux (see [dontkillmyapp.com](https://dontkillmyapp.com/)).

---

## Step 3: Get Your API & Telegram Keys

Before running the command, gather the keys you want to pre-fill:

| Key | Where to get it | Purpose |
|---|---|---|
| **Telegram Bot Token** | Message `@BotFather` on Telegram → `/newbot` → copy the HTTP API token | Connects your companion to Telegram |
| **Telegram User ID** | Message `@userinfobot` on Telegram → copy your numeric `Id: 123456789` | Authorizes you as the companion's owner |
| **xAI (Grok) API Key** | [console.x.ai](https://console.x.ai/) | Primary fast reasoning model (`grok-2` / `grok-beta`) |
| **OpenRouter Key** | [openrouter.ai/keys](https://openrouter.ai/keys) | Access to Claude, DeepSeek, Llama, and backup models |
| **OpenAI Key / OAuth** | [platform.openai.com](https://platform.openai.com/) or `hermes auth add openai-codex` | OpenAI fallback or ChatGPT subscription |

---

## Step 4: The 1-Command Setup

Open **Termux** on the phone.

> [!NOTE]
> **Repository Access**:
> The project is publicly available at `tamanitomo/tamanitomo`. Friends can clone directly without needing collaborator access.

### Option A: Clone & Run (Recommended for Friends)
Once invited as a collaborator and the invite is accepted on GitHub:

```bash
pkg update -y && pkg install -y git
git clone https://github.com/tamanitomo/tamanitomo.git
cd tamanitomo
bash setup-termux.sh
```
*(After cloning, the script runs the turnkey interactive wizard with zero hassle.)*

### Option B: Fully Pre-filled 1-Liner (Zero Typing on Phone)
If your friend generates a GitHub Personal Access Token (or you share a read-only repository token with them), they can paste this single command:

```bash
curl -fsSL https://raw.githubusercontent.com/tamanitomo/tamanitomo/main/setup-termux.sh | bash -s -- \
  --github-token "YOUR_GITHUB_PAT" \
  --name "Aura" \
  --human "YourName" \
  --telegram-token "YOUR_TELEGRAM_BOT_TOKEN" \
  --telegram-user-id "YOUR_TELEGRAM_USER_ID" \
  --xai-key "xai-YOUR_GROK_KEY" \
  --openrouter-key "sk-or-v1-YOUR_OPENROUTER_KEY"
```

### Option C: Interactive Wizard via Curl
```bash
curl -fsSL https://raw.githubusercontent.com/tamanitomo/tamanitomo/main/setup-termux.sh | bash -s --
```

The script will automatically:
1. Acquire a Termux wake-lock (`termux-wake-lock`) so Android doesn't suspend the CPU.
2. Install Python, Git, Curl, Clang, OpenSSH, and `termux-services`.
3. Fetch the pre-compiled `aarch64` wheelhouse to install heavy dependencies (`pydantic-core`, `firecrawl-anydoc`, `maturin`, `cryptography`, `uvloop`, etc.) in ~10 seconds, cutting install time from 35+ minutes down to ~2.5 minutes!
4. Clone Tamanitomo (if not already local) and install Hermes Agent in a dedicated virtualenv.
5. Validate your Telegram bot token live with the Telegram API.
6. Send a confirmation message directly to your Telegram chat.
7. Configure Grok (`grok-2`) as primary inference, with OpenRouter/OpenAI fallbacks.
8. Initialize the companion persona, memory vault, and autonomous cron routines.
9. Set up 24/7 background supervision (`runit`) and reboot autostart (`Termux:Boot`).

---

## Step 5: Accessing Your Companion & Web Dashboard

Your companion is now active in two places:

### 1. Telegram (Everyday Chat & Voice Notes)
- Open Telegram on your iPhone, Android, or laptop.
- Search for your bot username (the one you created with `@BotFather`).
- Send `/start`. Your companion will reply immediately!

### 2. Mobile Browser on the Server Phone (`localhost`)
- If using the phone directly, open Chrome or Firefox and navigate to:
  ```text
  http://localhost:38439
  ```
- Access from `localhost` is completely frictionless and bypasses the PIN requirement. The mobile-responsive interface includes a slide-out hamburger menu drawer, responsive emotional atmosphere badges, voice composer chips, and memory explorer.

### 3. Remote Browser over Wi-Fi (`LAN`)
- From any laptop, iPad, or desktop on the same Wi-Fi network:
  ```text
  http://<phone-ip-address>:38439
  ```
- If a 4-digit PIN was configured during setup (or set in Settings → Preferences → Server & Network Reachability), entering the PIN grants a 30-day session cookie. Localhost remains open without PIN.

---

## Termux Daily Cheat Sheet

You do not need to keep the Termux app open on your screen; it runs silently in the background. If you ever need to inspect or control it:

| Task | Command in Termux |
|---|---|
| **Check background service status** | `sv status companion-gateway` |
| **Check web UI status** | `sv status companion-workspace` |
| **Restart Telegram bot** | `sv restart companion-gateway` |
| **View live conversation logs** | `hermes logs -f` |
| **Chat in terminal** | `companion chat` |
| **Check scheduled cron jobs** | `companion schedule status` |
| **Run system doctor** | `companion doctor` |

---

## Using OAuth Instead of Paid API Keys (Subscriptions)

If you or your friend have an existing subscription (X Premium+ / SuperGrok or ChatGPT Plus/Pro), Hermes supports OAuth device-code login directly so you do not need to enter a credit card on an API developer console.

### 1. xAI Grok OAuth (SuperGrok / X Premium+)
If you subscribe to SuperGrok or X Premium+:
1. In Termux, run:
   ```bash
   hermes auth add xai-oauth
   ```
   *(or select **xAI Grok OAuth** in `hermes model`)*
2. Hermes will display a verification URL (e.g. `https://x.ai/device`) and a short code.
3. Open the link on your phone or laptop, approve the session, and Hermes will automatically store the refresh token in `~/.hermes/auth.json` and route all companion inference through your Grok subscription.

### 2. OpenAI OAuth (ChatGPT Plus/Pro)
If you subscribe to ChatGPT Plus or Pro:
1. In Termux, run:
   ```bash
   hermes auth add openai-codex
   ```
2. Open the URL in your browser, log in to ChatGPT, and authorize the session.
3. Hermes will automatically store the refresh token in `~/.hermes/auth.json` and use your ChatGPT subscription quota.
