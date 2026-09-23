<p align="center">
  <img src="kit/app/static/logo.png" alt="Tamanitomo Logo" width="140" height="140">
</p>

<h1 align="center">tamanitomo · 魂の友</h1>

<p align="center">
  <strong>Soul of a Friend — A sovereign, self-hosted AI companion that has a life when you close the window.</strong><br>
  Built on <a href="https://hermes-agent.nousresearch.com/">Hermes Agent</a> · Your data under your control · Keeps memory on your disk · Messages you when it wants to.
</p>

<p align="center">
  <a href="LICENSE"><img alt="License: PolyForm Noncommercial 1.0.0" src="https://img.shields.io/badge/license-PolyForm%20Noncommercial-6c9cff"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-4ade80">
  <img alt="Self-Hosted" src="https://img.shields.io/badge/runtime-self--hosted-b388ff">
  <img alt="No Telemetry" src="https://img.shields.io/badge/telemetry-none-2dd4bf">
  <img alt="Platforms" src="https://img.shields.io/badge/platform-Linux%20%7C%20Android%20%7C%20Windows%20%7C%20macOS-f59e0b">
</p>

<p align="center">
  <img src="docs/assets/demos/desktop-demo.gif" alt="Tamanitomo Desktop & Mobile Demo" width="90%">
</p>

---

## Why Tamanitomo?

Most AI character apps keep your companion on their cloud servers. The memory belongs to them, subscription costs compound every month, and the character can be modified, censored, or deleted overnight.

**Tamanitomo is the opposite arrangement.** 

Your companion lives in a folder on your own computer, phone, or home server. It is backed by whatever model you choose — completely local weights on your GPU (Ollama, LM Studio, vLLM) or a private cloud API (OpenRouter, Grok, DeepSeek, OpenAI).

- **No Tamanitomo account or product telemetry:** Your vault stays on your host. Cloud models, Telegram, online speech, and other integrations receive the content you send through them.
- **A real present:** It knows what time it is, follows morning and evening routines, and writes its own reflections.
- **Evidence-backed memory:** It separates authored fiction from hard facts about you, citing exact quotes in an append-only ledger.
- **Code-enforced boundaries:** Limits on when and how often it can message you are enforced in code, not merely suggested in a system prompt. It won't wake you up at 3:00 AM.
- **Multimodal & Multi-Channel:** Chat in a responsive web app or over Telegram with voice notes, photo albums, and ambient awareness.

---

## ⚡ Quickstart: 1-Line Turnkey Installers

Choose your setup:

### 🐧 Linux (Desktop / Home Server / VPS)
Sets up a dedicated environment, dependencies, and an optional systemd background service:
```bash
curl -fsSL https://raw.githubusercontent.com/tamanitomo/tamanitomo/main/setup-linux.sh | bash
```
*(Or clone manually: `git clone https://github.com/tamanitomo/tamanitomo && cd tamanitomo && bash setup-linux.sh`)*

---

### 📱 Android Phone (24/7 Dedicated Server via Termux)
Turn an old plugged-in phone into an ultra-low-power (<3W), battery-backed 24/7 companion server:
```bash
curl -fsSL https://raw.githubusercontent.com/tamanitomo/tamanitomo/main/setup-termux.sh | bash
```

**Back to baseline:** remove Tamanitomo, Hermes, their saved data, and only the Termux packages the installer added with:
```bash
curl -fsSL https://raw.githubusercontent.com/tamanitomo/tamanitomo/main/uninstall-termux.sh | bash -s -- -y --purge-packages
```
This permanently deletes companion data and credentials. Packages that existed before installation are preserved when a baseline manifest is available.

*(See the [Android Termux 24/7 Server Guide](docs/ANDROID_TERMUX_SETUP_GUIDE.md) for full step-by-step instructions and Telegram bot setup.)*

---

### 🪟 Windows (Native)
Run in PowerShell or Command Prompt:
```powershell
git clone https://github.com/tamanitomo/tamanitomo.git
cd tamanitomo
.\tamanitomo.cmd
```
*(Double-clicking `tamanitomo.cmd` bootstraps Python automatically using `uv` if Python 3.11+ is not installed.)*

---

### 🍎 macOS
Clone the repository, then run the launcher in Terminal:
```bash
git clone https://github.com/tamanitomo/tamanitomo.git
cd tamanitomo
./tamanitomo
```
The launcher provisions Python when needed and opens the workspace. Configure Hermes and a conversation model in Settings; keep the host awake for background routines.

---

### 🔄 Updating
Your companion, answers and history live in your Hermes folder and vault, not in the Tamanitomo folder, so updating never repeats setup.
- **Linux / Android:** run the same one-line installer again. It finds the existing install and asks whether to **upgrade** (keep everything, update to the newest release) or do a **fresh install** (set the old program folder aside and install a clean copy). Your companion is kept either way. A checkout with your own code changes is never overwritten.
- **Windows / macOS / anywhere:** open **Settings → Updates** in the app, or run `git pull` in the Tamanitomo folder and start it again.

---

### 🤝 Already using Hermes Agent?
Adopt your existing agent seamlessly. Your `SOUL.md`, memories, and history are preserved byte-for-byte:
```bash
git clone https://github.com/tamanitomo/tamanitomo.git && cd tamanitomo
./tamanitomo --home ~/.hermes upgrade --soul keep
```

---

## ✨ Features at a Glance

<table>
<tr>
<td width="50%" valign="top">

### 🌅 A Living Companion
Your companion maintains an append-only timeline of what it is doing, where it is, and its current mood. When inference is temporarily unreachable, it admits it rather than hallucinating.

<img src="docs/assets/screenshots/desktop/01-home-elena.jpg" alt="Home Presence View" width="100%">

</td>
<td width="50%" valign="top">

### 🧠 Grounded Memory & Callbacks
Remembers shared jokes, milestones, and details you mentioned days ago. Facts about you require cited proof, to reduce invented memories; the chosen model can still make mistakes.

<img src="docs/assets/screenshots/desktop/02-chat-memory-callback.jpg" alt="Memory Callback" width="100%">

</td>
</tr>
<tr>
<td width="50%" valign="top">

### 📖 Nightly Reflections & Journals
Every night, your companion reflects on your conversations and its day, penning authentic journal entries in its own voice.

<img src="docs/assets/screenshots/desktop/04-journal.jpg" alt="Daily Journal" width="100%">

</td>
<td width="50%" valign="top">

### 📸 Photo Albums & In-World Scenes
Generate in-world selfies and scenery through ComfyUI or cloud image models, complete with a built-in privacy review gate.

<img src="docs/assets/screenshots/desktop/03-photos-gallery.jpg" alt="Photo Gallery" width="100%">

</td>
</tr>
<tr>
<td width="50%" valign="top">

### ❤️ Relationship Evolution & Chemistry
Meters track warmth, trust, irritation, and missing-you dynamics that organically progress through relationship stages over time.

<img src="docs/assets/screenshots/desktop/06-relationship-meters.jpg" alt="Relationship Meters" width="100%">

</td>
<td width="50%" valign="top">

### 👥 Multi-Companion Roster
Run multiple completely independent companions side-by-side on a single install, each with their own memory, personality, and journal.

<img src="docs/assets/screenshots/desktop/07-companions-roster.jpg" alt="Companions Roster" width="100%">

</td>
</tr>
</table>

---

## 📱 Mobile Responsive Workspace

Tamanitomo features a sleek, mobile-optimized web interface designed to feel like a native app on iOS and Android:

<p align="center">
  <img src="docs/assets/demos/mobile-demo.gif" alt="Mobile Workspace Demo" width="340">
</p>

Access it on `http://localhost:8770` (or port `38439` on Termux), or over your private home Wi-Fi with a workspace PIN. A PIN does not encrypt HTTP traffic; use authenticated HTTPS or private networking for remote access.

---

## Data and privacy

This is the self-hosted companion application, formerly companion-kit. It is not the archived E2EE hosted service. Memory and credentials are stored on your host; the vault is not encrypted by Tamanitomo. A fully local configuration keeps model processing on your hardware. Check every configured fallback and media provider before assuming a session stays local.

## 🛡️ Built for Real Hardware & Privacy

- **Extremely cheap to run**: A companion runs 16 scheduled background routines. **6 run with zero LLM calls** (presence advancer, health watch, outbox dispatcher, sensor polling, quiet-hours drift, vault commit). The autonomy loop uses fingerprinting so your model never fires when nothing has changed.
- **Bring your own weights**: Connect to local Ollama, LM Studio, or vLLM endpoints for a 100% offline companion, or use Grok, OpenRouter, DeepSeek, or OpenAI API keys with automatic failover chains.
- **Human-in-the-loop safety**: Vault files are backed by a local Git repository committed automatically every 15 minutes. Any change can be inspected, diffed, or reverted file-by-file.
- **Strict Outbox Gate**: Companions queue messages into an outbox; an independent daemon checks your quiet hours and daily frequency quotas before anything is delivered.

---

## 🛠️ Essential Commands

Run `./tamanitomo` with no arguments to launch the browser workspace. For CLI power users:

| Command | Action |
| --- | --- |
| `./tamanitomo` | Launch the web workspace and dashboard |
| `./tamanitomo chat` | Start a direct terminal conversation |
| `./tamanitomo doctor` | Run system diagnostics (budgets, hooks, memory, health) |
| `./tamanitomo status` | View current companion presence, mood, open loops, and jobs |
| `./tamanitomo add <name>` | Create a new distinct companion profile |
| `./tamanitomo schedule active` | Activate the autonomous background schedules |
| `./tamanitomo models` | Configure and test your primary and fallback model chain |

Full CLI options and scripting flags: [docs/REFERENCE.md](docs/REFERENCE.md).

---

## 📚 Documentation & Guides

- 📖 **[Getting Started Guide](START_HERE.md)** — First-time setup walkthrough.
- 📱 **[Android 24/7 Dedicated Server Guide](docs/ANDROID_TERMUX_SETUP_GUIDE.md)** — Turn a spare phone into an always-on companion server.
- 🖥️ **[Desktop & Workspace Interface](docs/DESKTOP.md)** — Deep dive into the web workspace features.
- 🦙 **[Local Stack & Offline Setup](docs/LOCAL_STACK.md)** — Running Ollama, ComfyUI, and local speech engines.
- 💡 **[Core Concepts & Architecture](docs/CONCEPTS.md)** — The foundational principles behind Tamanitomo.
- 🔧 **[Full Command & File Reference](docs/REFERENCE.md)** — Complete reference for CLI options and schemas.
- 🩺 **[Troubleshooting Guide](docs/TROUBLESHOOTING.md)** — Solutions organized by symptom.

---

## 📄 License & Community

Tamanitomo is licensed under the **[PolyForm Noncommercial 1.0.0](LICENSE)** license. You are free to use, modify, share, and build upon it for any noncommercial purpose (personal use, hobbies, research, education). 

We chose this license deliberately to keep Tamanitomo in the hands of the open AI community, ensuring it remains an open sovereign companion rather than a closed commercial subscription product.

Contributions, feedback, and companion persona shares are warmly welcomed!
