#!/usr/bin/env bash
# ==============================================================================
# Tamanitomo — 1-Command Android Termux Turnkey Setup
#
# Sets up Tamanitomo + Hermes Agent on an Android device running Termux.
# Configures 24/7 background gateway, Telegram bot, cloud inference (Grok,
# OpenRouter, OpenAI), autonomous companion routines, and web workspace.
# ==============================================================================
set -euo pipefail

# ANSI color formatting
BOLD='\033[1m'
DIM='\033[2m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
RESET='\033[0m'

# Default values
COMPANION_NAME="Sam"
HUMAN_NAME="Friend"
TELEGRAM_TOKEN=""
TELEGRAM_USER_ID=""
PRIMARY_PROVIDER=""
OPENROUTER_KEY=""
OPENAI_KEY=""
XAI_KEY=""
DEEPSEEK_KEY=""
GITHUB_TOKEN="${GITHUB_TOKEN:-}"
MODEL_CHOICE=""
PORT="38439"
REMOTE_PIN=""
WHEELHOUSE_SOURCE=""
DRY_RUN=0
TEST_MODE=0
NON_INTERACTIVE=0
UPGRADE_MODE=0

usage() {
  cat <<EOF
${BOLD}Tamanitomo — Android Termux Setup${RESET}

Usage:
  bash setup-termux.sh [OPTIONS]

Options:
  --name <name>             Companion display name (default: Sam)
  --human <name>            Your name / what companion calls you (default: Friend)
  --provider <provider>     Primary AI provider: openrouter, openai, xai, deepseek (default: openrouter)
  --openrouter-key <key>    OpenRouter API Key
  --openai-key <key>        OpenAI API Key
  --xai-key <key>           xAI (Grok) API Key
  --deepseek-key <key>      DeepSeek API Key
  --model <model>           Primary model (e.g. openrouter/auto, gpt-4o, grok-2, deepseek-chat)
  --telegram-token <token>  Telegram Bot Token from @BotFather
  --telegram-user-id <id>   Your numeric Telegram User ID (from @userinfobot)
  --github-token <token>    GitHub Personal Access Token (for private repo access)
  --port <port>             Web workspace port (default: 38439)
  --remote-pin <pin>        4-digit PIN for remote network access
  --wheelhouse <path|url>   Custom wheelhouse directory, tarball, or download URL
  --upgrade                 Upgrade an existing installation in-place
  --non-interactive         Do not prompt for missing values (use defaults/flags)
  --test-mode               Run on non-Android Linux simulating Termux environment
  --dry-run                 Validate inputs and show generated configuration only
  -h, --help                Show this help message
EOF
}

# Parse command-line flags
while [[ $# -gt 0 ]]; do
  case "$1" in
    --name) COMPANION_NAME="$2"; shift 2 ;;
    --human) HUMAN_NAME="$2"; shift 2 ;;
    --provider) PRIMARY_PROVIDER="$2"; shift 2 ;;
    --openrouter-key) OPENROUTER_KEY="$2"; shift 2 ;;
    --openai-key) OPENAI_KEY="$2"; shift 2 ;;
    --xai-key) XAI_KEY="$2"; shift 2 ;;
    --deepseek-key) DEEPSEEK_KEY="$2"; shift 2 ;;
    --telegram-token) TELEGRAM_TOKEN="$2"; shift 2 ;;
    --telegram-user-id) TELEGRAM_USER_ID="$2"; shift 2 ;;
    --github-token) GITHUB_TOKEN="$2"; shift 2 ;;
    --model) MODEL_CHOICE="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --remote-pin) REMOTE_PIN="$2"; shift 2 ;;
    --wheelhouse) WHEELHOUSE_SOURCE="$2"; shift 2 ;;
    --upgrade) UPGRADE_MODE=1; shift ;;
    --non-interactive) NON_INTERACTIVE=1; shift ;;
    --test-mode) TEST_MODE=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo -e "${RED}Unknown option: $1${RESET}" >&2; usage; exit 1 ;;
  esac
done

echo -e "${BOLD}${CYAN}"
echo "  ╔═══════════════════════════════════════════════════════════════╗"
echo "  ║          Tamanitomo — Android Termux Turnkey Setup            ║"
echo "  ╚═══════════════════════════════════════════════════════════════╝"
echo -e "${RESET}"

# curl | bash has script bytes on stdin. Prompts use the controlling terminal.
if [[ "$NON_INTERACTIVE" -eq 0 && "$DRY_RUN" -eq 0  ]]; then
  if ( : </dev/tty ) 2>/dev/null; then
    exec 3</dev/tty
  else
    echo 'No interactive terminal. Pass --non-interactive to use defaults.' >&2
    exit 1
  fi
fi

# Detect Termux or Test Mode
IS_TERMUX=0
if [[ -n "${PREFIX:-}" && "$PREFIX" == *"com.termux"* ]] || [[ -d "/data/data/com.termux" ]]; then
  IS_TERMUX=1
fi

if [[ "$IS_TERMUX" -eq 0 && "$TEST_MODE" -eq 0 && "$DRY_RUN" -eq 0 ]]; then
  echo -e "${YELLOW}Warning: Not running inside Android Termux.${RESET}"
  echo -e "If you are testing this installer on a standard Linux PC, use ${BOLD}--test-mode${RESET}."
  read -u 3 -r -p "Continue anyway in test mode? [y/N]: " proceed
  if [[ "$proceed" =~ ^[Yy]$ ]]; then
    TEST_MODE=1
  else
    exit 1
  fi
fi

# Define path targets
if [[ "$IS_TERMUX" -eq 1 ]]; then
  HOME_DIR="${HOME:-/data/data/com.termux/files/home}"
  PREFIX_DIR="${PREFIX:-/data/data/com.termux/files/usr}"
else
  HOME_DIR="${HOME}"
  PREFIX_DIR="/tmp/tamanitomo-termux-test/usr"
  if [[ "$DRY_RUN" -eq 0 ]]; then mkdir -p "$PREFIX_DIR"; fi
fi

# Auto-detect if running directly from an existing checkout
DETECTED_KIT_DIR=""
CURRENT_DIR="$(pwd)"
if [[ -f "$CURRENT_DIR/kit/cli/main.py" ]]; then
  DETECTED_KIT_DIR="$CURRENT_DIR"
elif [[ -n "${BASH_SOURCE[0]:-}" && -f "${BASH_SOURCE[0]}" ]]; then
  SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd || echo "")"
  if [[ -n "$SRC_DIR" && -f "$SRC_DIR/kit/cli/main.py" ]]; then
    DETECTED_KIT_DIR="$SRC_DIR"
  elif [[ -n "$SRC_DIR" && -f "$SRC_DIR/../kit/cli/main.py" ]]; then
    DETECTED_KIT_DIR="$(cd "$SRC_DIR/.." >/dev/null 2>&1 && pwd || echo "")"
  fi
fi

HERMES_HOME="${HERMES_HOME:-$HOME_DIR/.hermes}"
if [[ -z "${KIT_DIR:-}" ]]; then
  if [[ -n "${DETECTED_KIT_DIR:-}" ]]; then
    KIT_DIR="$DETECTED_KIT_DIR"
  elif [[ -d "$HOME_DIR/tamanitomo" ]]; then
    KIT_DIR="$HOME_DIR/tamanitomo"
  elif [[ -d "$HOME_DIR/companion-kit" ]]; then
    KIT_DIR="$HOME_DIR/companion-kit"
  else
    KIT_DIR="$HOME_DIR/tamanitomo"
  fi
fi
VAULT_DIR="${HOME_DIR}/vault"
WHEELS_DIR="$HERMES_HOME/wheels"

# The aarch64 wheelhouse is built for CPython 3.11 only.  A venv on any other
# Python rejects every wheel and pip falls back to compiling the Rust packages
# (pydantic-core, jiter, cryptography, rpds-py) with maturin, which is slow at
# best and usually fails on a phone.  So on Termux every venv must be 3.11.
WHEELHOUSE_PY="3.11"
export PIP_DISABLE_PIP_VERSION_CHECK=1
if [[ "$IS_TERMUX" -eq 1 ]]; then
  # Take an older prebuilt wheel over a newer source release.
  export PIP_PREFER_BINARY=1
  # maturin refuses to build for Android without this, even with Rust installed.
  if [[ -z "${ANDROID_API_LEVEL:-}" ]]; then
    ANDROID_API_LEVEL="$(getprop ro.build.version.sdk 2>/dev/null || true)"
    if [[ -n "$ANDROID_API_LEVEL" ]]; then export ANDROID_API_LEVEL; fi
  fi
fi

python_missing_error() {
  echo -e "${RED}Error: Python ${WHEELHOUSE_PY} is not installed.${RESET}" >&2
  echo "Tamanitomo's prebuilt Android packages only work with Python ${WHEELHOUSE_PY}. Without it pip" >&2
  echo "has to compile Rust packages from source, which is the 'error running maturin' failure." >&2
  echo "Install it, then run this script again:" >&2
  echo "  pkg install tur-repo && pkg install python${WHEELHOUSE_PY}" >&2
}

python_for_venv() {
  if command -v "python${WHEELHOUSE_PY}" >/dev/null 2>&1; then
    command -v "python${WHEELHOUSE_PY}"
  elif [[ "$IS_TERMUX" -eq 1 ]]; then
    return 1
  else
    command -v python3
  fi
}

venv_python_version() {
  "$1/bin/python" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo "unusable"
}

# Create the venv at $1.  One left on the wrong Python by an earlier run is
# rebuilt; otherwise every re-run would reuse it and fail the same way.
ensure_venv() {
  local dir="$1" py have
  if ! py="$(python_for_venv)"; then
    python_missing_error
    exit 1
  fi
  if [[ -d "$dir" && "$IS_TERMUX" -eq 1 ]]; then
    have="$(venv_python_version "$dir")"
    if [[ "$have" != "$WHEELHOUSE_PY" ]]; then
      echo -e "  ${YELLOW}! $dir uses Python $have, but the prebuilt packages need ${WHEELHOUSE_PY}. Rebuilding it.${RESET}"
      rm -rf "$dir"
    fi
  fi
  if [[ ! -d "$dir" ]]; then
    echo -e "  Creating Python virtual environment in $dir..."
    "$py" -m venv "$dir"
  fi
  "$dir/bin/python" -m pip install --upgrade pip >/dev/null 2>&1 || true
}

install_wheelhouse() {
  local venv="$1" log
  if [[ ! -d "$WHEELS_DIR" || $(find "$WHEELS_DIR" -maxdepth 1 -name "*.whl" 2>/dev/null | wc -l) -lt 10 ]]; then
    return 0
  fi
  echo -e "  Installing pre-compiled wheels into $venv..."
  log="$(mktemp)"
  if ! "$venv/bin/python" -m pip install "$WHEELS_DIR"/*.whl >"$log" 2>&1; then
    echo -e "  ${YELLOW}! The prebuilt packages did not install; pip may try to build them from source:${RESET}"
    tail -n 5 "$log" | sed 's/^/    /'
  fi
  rm -f "$log"
}

# pip_install <venv> <pip install arguments...>
pip_install() {
  local venv="$1"
  shift
  if ! "$venv/bin/python" -m pip install "$@"; then
    echo -e "${RED}Error: pip could not install Python packages into $venv.${RESET}" >&2
    if [[ "$IS_TERMUX" -eq 1 ]]; then
      echo "If the output above mentions maturin, Rust or cargo, a package had to be built from source." >&2
      echo "  venv Python:       $(venv_python_version "$venv") (prebuilt packages need ${WHEELHOUSE_PY})" >&2
      echo "  Rust compiler:     $(command -v rustc >/dev/null 2>&1 && rustc --version || echo 'missing - pkg install rust')" >&2
      echo "  ANDROID_API_LEVEL: ${ANDROID_API_LEVEL:-unset}" >&2
      echo "Fix whichever of those is wrong, then run this script again." >&2
    fi
    exit 1
  fi
}

echo -e "${DIM}Destination home: ${HOME_DIR}${RESET}"
echo -e "${DIM}Hermes directory: ${HERMES_HOME}${RESET}"
echo -e "${DIM}Tamanitomo:       ${KIT_DIR}${RESET}"
echo ""

# Bring a git checkout to the newest published release. Running the installer
# again is how people update, so a second run must not leave the first run's
# code in place. A checkout with local changes, or already past the newest
# release (someone working on Tamanitomo itself), is left exactly as it is.
sync_to_release() {
  local dir="$1" url="$2" fresh="${3:-0}" tag
  if [[ ! -d "$dir/.git" ]]; then
    if [[ -f "$dir/SHA256SUMS.json" ]]; then
      echo -e "  ${DIM}Installed from a release ZIP: update it from Settings > Updates in the app.${RESET}"
    fi
    return 0
  fi
  if ! git -C "$dir" fetch --quiet --tags "$url" 2>/dev/null; then
    echo -e "  ${YELLOW}Could not reach GitHub to check for a newer release; keeping the installed code.${RESET}"
    return 0
  fi
  tag="$(git -C "$dir" tag -l 'v[0-9]*' --sort=-v:refname | head -n 1)"
  [[ -n "$tag" ]] || return 0
  if [[ "$fresh" -eq 1 ]]; then
    git -C "$dir" reset --quiet --hard "$tag"
    echo -e "  Installed release ${tag}."
  elif [[ -n "$(git -C "$dir" status --porcelain)" ]]; then
    echo -e "  ${YELLOW}${dir} has local changes, so it was not updated. Commit or move them and run the installer again.${RESET}"
  elif git -C "$dir" merge-base --is-ancestor "$tag" HEAD; then
    echo -e "  Already on release ${tag} or newer."
  elif git -C "$dir" merge --quiet --ff-only "$tag" 2>/dev/null; then
    echo -e "  Updated to release ${tag}."
  else
    echo -e "  ${YELLOW}${dir} has diverged from the published releases, so it was not updated.${RESET}"
  fi
}

# An existing install was found: ask what the person wants instead of making
# them know about a flag. Upgrade keeps everything and moves the program to the
# newest release. A fresh install sets the old program folder aside (it is never
# deleted) and installs a clean copy with a new Python environment. The
# companion, the answers given at setup and the vault live in the Hermes folder
# and vault, so neither choice repeats setup or loses a companion.
choose_install_mode() {
  local dir="$1" answer=""
  INSTALL_MODE="upgrade"
  if [[ "$NON_INTERACTIVE" -eq 1 || "$DRY_RUN" -eq 1 ]]; then return 0; fi
  echo -e "${CYAN}Tamanitomo is already installed in ${dir}.${RESET}"
  echo "  1) Upgrade: keep everything and update to the newest release (recommended)"
  echo "  2) Fresh install: set this copy aside and install a clean one"
  echo "  Your companion, your setup answers and your vault are kept either way."
  read -u 3 -r -p "Choose 1 or 2 [1]: " answer || answer=""
  case "${answer:-1}" in
    2|f|F|fresh|Fresh) INSTALL_MODE="fresh" ;;
    *) INSTALL_MODE="upgrade" ;;
  esac
}

set_aside_install() {
  local dir="$1" dest
  dest="${dir%/}.old-$(date +%Y%m%d-%H%M%S)"
  mv "$dir" "$dest"
  echo -e "  Previous copy kept at ${dest} (delete it once the new install works)."
}

if [[ "$UPGRADE_MODE" -eq 0 && -f "$KIT_DIR/kit/cli/main.py" ]]; then
  choose_install_mode "$KIT_DIR"
  if [[ "$INSTALL_MODE" == "upgrade" ]]; then
    UPGRADE_MODE=1
  elif [[ "$DRY_RUN" -eq 0 ]]; then
    set_aside_install "$KIT_DIR"
  fi
fi

if [[ "$UPGRADE_MODE" -eq 1 && "$DRY_RUN" -eq 0 ]]; then
  echo -e "${CYAN}→ Upgrading existing installation in $KIT_DIR...${RESET}"
  if [[ ! -d "$KIT_DIR" ]]; then
    echo -e "${RED}Error: Cannot find existing installation at $KIT_DIR${RESET}" >&2
    exit 1
  fi
  UPGRADE_URL="https://github.com/tamanitomo/tamanitomo.git"
  if [[ -n "$GITHUB_TOKEN" ]]; then
    UPGRADE_URL="https://${GITHUB_TOKEN}@github.com/tamanitomo/tamanitomo.git"
  fi
  sync_to_release "$KIT_DIR" "$UPGRADE_URL"
  VENV_DIR="$KIT_DIR/.venv"
  if [[ -f "$KIT_DIR/requirements.txt" ]]; then
    echo -e "  Updating Python dependencies..."
    ensure_venv "$VENV_DIR"
    install_wheelhouse "$VENV_DIR"
    pip_install "$VENV_DIR" -r "$KIT_DIR/requirements.txt"
  fi
  echo -e "  Refreshing companion templates and cron shims..."
  "$VENV_DIR/bin/python" "$KIT_DIR/bin/tamanitomo" --home "$HERMES_HOME" upgrade --answers "$HOME_DIR/.companion-init-answers.json" >/dev/null 2>&1 || \
  "$VENV_DIR/bin/python" "$KIT_DIR/bin/tamanitomo" --home "$HERMES_HOME" upgrade
  if command -v sv >/dev/null 2>&1; then
    echo -e "  Restarting services..."
    for s in tamanitomo-workspace companion-workspace tamanitomo-gateway companion-gateway; do
      sv restart "$s" 2>/dev/null || true
    done
  fi
  echo -e "${BOLD}${GREEN}  ✓ Tamanitomo upgrade complete!${RESET}"
  exit 0
fi

# Request wake-lock on Termux so Android CPU doesn't sleep
if [[ "$IS_TERMUX" -eq 1 && "$DRY_RUN" -eq 0 ]]; then
  echo -e "${CYAN}→ Acquiring Termux wake-lock (prevents sleep while serving)...${RESET}"
  if command -v termux-wake-lock >/dev/null 2>&1; then
    termux-wake-lock || true
  fi
fi

# ------------------------------------------------------------------------------
# Interactive prompts for credentials if not supplied via flags
# ------------------------------------------------------------------------------
if [[ "$NON_INTERACTIVE" -eq 0 && "$DRY_RUN" -eq 0 ]]; then
  if [[ -t 3 ]]; then
    echo -e "${BOLD}1. Companion Identity${RESET}"
    read -u 3 -r -p "   Companion Name [${COMPANION_NAME}]: " input_name
    COMPANION_NAME="${input_name:-$COMPANION_NAME}"

    read -u 3 -r -p "   Your Name [${HUMAN_NAME}]: " input_human
    HUMAN_NAME="${input_human:-$HUMAN_NAME}"
    echo ""

    echo -e "${BOLD}2. Telegram Configuration (24/7 companion messaging)${RESET}"
    echo -e "${DIM}   Create a bot with @BotFather on Telegram to get your token.${RESET}"
    if [[ -z "$TELEGRAM_TOKEN" ]]; then
      read -u 3 -r -p "   Telegram Bot Token: " TELEGRAM_TOKEN
    else
      echo -e "   Telegram Bot Token: ${GREEN}[Provided via flag]${RESET}"
    fi

    if [[ -z "$TELEGRAM_USER_ID" ]]; then
      echo -e "${DIM}   Find your numeric User ID by messaging @userinfobot on Telegram.${RESET}"
      read -u 3 -r -p "   Telegram User ID (numeric chat owner): " TELEGRAM_USER_ID
    else
      echo -e "   Telegram User ID:    ${GREEN}[Provided via flag]${RESET}"
    fi
    echo ""

    echo -e "${BOLD}3. Primary AI Model Provider${RESET}"
    echo -e "${DIM}   Select which AI provider will power your companion's thoughts and dialogue.${RESET}"
    if [[ -z "$PRIMARY_PROVIDER" ]]; then
      echo "   1) OpenRouter (Recommended — Claude, Llama 3.3, DeepSeek, etc.)"
      echo "   2) OpenAI (GPT-4o, GPT-4o-mini)"
      echo "   3) xAI / Grok (grok-2, grok-beta)"
      echo "   4) DeepSeek (deepseek-chat, deepseek-reasoner)"
      echo ""
      read -u 3 -r -p "   Choose primary provider [1-4, default: 1]: " provider_num
      case "$provider_num" in
        2) PRIMARY_PROVIDER="openai" ;;
        3) PRIMARY_PROVIDER="xai" ;;
        4) PRIMARY_PROVIDER="deepseek" ;;
        *) PRIMARY_PROVIDER="openrouter" ;;
      esac
    else
      echo -e "   Primary Provider:    ${GREEN}${PRIMARY_PROVIDER} [Provided via flag]${RESET}"
    fi
    echo ""

    # Prompt for primary provider API key
    case "$PRIMARY_PROVIDER" in
      openrouter)
        if [[ -z "$OPENROUTER_KEY" ]]; then
          read -u 3 -r -p "   OpenRouter API Key: " OPENROUTER_KEY
        else
          echo -e "   OpenRouter API Key:  ${GREEN}[Provided via flag]${RESET}"
        fi
        [[ -z "$MODEL_CHOICE" ]] && MODEL_CHOICE="openrouter/auto"
        ;;
      openai)
        if [[ -z "$OPENAI_KEY" ]]; then
          read -u 3 -r -p "   OpenAI API Key: " OPENAI_KEY
        else
          echo -e "   OpenAI API Key:      ${GREEN}[Provided via flag]${RESET}"
        fi
        [[ -z "$MODEL_CHOICE" ]] && MODEL_CHOICE="gpt-4o"
        ;;
      xai)
        if [[ -z "$XAI_KEY" ]]; then
          read -u 3 -r -p "   xAI (Grok) API Key: " XAI_KEY
        else
          echo -e "   xAI (Grok) API Key:  ${GREEN}[Provided via flag]${RESET}"
        fi
        [[ -z "$MODEL_CHOICE" ]] && MODEL_CHOICE="grok-2"
        ;;
      deepseek)
        if [[ -z "$DEEPSEEK_KEY" ]]; then
          read -u 3 -r -p "   DeepSeek API Key: " DEEPSEEK_KEY
        else
          echo -e "   DeepSeek API Key:    ${GREEN}[Provided via flag]${RESET}"
        fi
        [[ -z "$MODEL_CHOICE" ]] && MODEL_CHOICE="deepseek-chat"
        ;;
    esac
    echo ""

    echo -e "${DIM}   (Optional) Secondary / Fallback API Keys (press Enter to skip):${RESET}"
    if [[ "$PRIMARY_PROVIDER" != "openrouter" && -z "$OPENROUTER_KEY" ]]; then
      read -u 3 -r -p "   OpenRouter API Key (press Enter to skip): " OPENROUTER_KEY
    fi
    if [[ "$PRIMARY_PROVIDER" != "openai" && -z "$OPENAI_KEY" ]]; then
      read -u 3 -r -p "   OpenAI API Key (press Enter to skip): " OPENAI_KEY
    fi
    if [[ "$PRIMARY_PROVIDER" != "deepseek" && -z "$DEEPSEEK_KEY" ]]; then
      read -u 3 -r -p "   DeepSeek API Key (press Enter to skip): " DEEPSEEK_KEY
    fi
    if [[ "$PRIMARY_PROVIDER" != "xai" && -z "$XAI_KEY" ]]; then
      read -u 3 -r -p "   xAI (Grok) API Key (press Enter to skip): " XAI_KEY
    fi
    echo ""

    echo -e "${BOLD}4. Remote Security PIN (Optional 4-digit PIN for Wi-Fi access)${RESET}"
    echo -e "${DIM}   Protect access when visiting from another device on your Wi-Fi (e.g. laptop).${RESET}"
    if [[ -z "$REMOTE_PIN" ]]; then
      read -u 3 -r -p "   4-Digit PIN (press Enter to skip): " REMOTE_PIN
    else
      echo -e "   4-Digit PIN:         ${GREEN}[Provided via flag]${RESET}"
    fi
    echo ""

    if [[ ! -f "$KIT_DIR/kit/cli/main.py" ]]; then
      echo -e "${BOLD}5. GitHub Access (For Private Repository)${RESET}"
      echo -e "${DIM}   If tamanitomo/tamanitomo is private, supply a GitHub Personal Access Token (PAT).${RESET}"
      if [[ -z "$GITHUB_TOKEN" ]]; then
        read -u 3 -r -p "   GitHub Token (press Enter to skip): " GITHUB_TOKEN
      else
        echo -e "   GitHub Token:        ${GREEN}[Provided via flag]${RESET}"
      fi
      echo ""
    fi
  fi
fi

if [[ ! "$PORT" =~ ^[0-9]+$ ]] || ((10#$PORT < 1 || 10#$PORT > 65535)); then
  echo 'Port must be between 1 and 65535.' >&2; exit 1
fi

# Validate Remote PIN if provided
if [[ -n "$REMOTE_PIN" ]]; then
  if [[ ! "$REMOTE_PIN" =~ ^[0-9]{4}$ ]]; then
    echo "Remote PIN must contain exactly four digits." >&2
    exit 1
  fi
fi

# Determine default model and provider if not interactively chosen
if [[ -z "$PRIMARY_PROVIDER" ]]; then
  if [[ -n "$OPENROUTER_KEY" ]]; then
    PRIMARY_PROVIDER="openrouter"
    [[ -z "$MODEL_CHOICE" ]] && MODEL_CHOICE="openrouter/auto"
  elif [[ -n "$OPENAI_KEY" ]]; then
    PRIMARY_PROVIDER="openai"
    [[ -z "$MODEL_CHOICE" ]] && MODEL_CHOICE="gpt-4o"
  elif [[ -n "$DEEPSEEK_KEY" ]]; then
    PRIMARY_PROVIDER="deepseek"
    [[ -z "$MODEL_CHOICE" ]] && MODEL_CHOICE="deepseek-chat"
  elif [[ -n "$XAI_KEY" ]]; then
    PRIMARY_PROVIDER="xai"
    [[ -z "$MODEL_CHOICE" ]] && MODEL_CHOICE="grok-2"
  else
    PRIMARY_PROVIDER="openrouter"
    [[ -z "$MODEL_CHOICE" ]] && MODEL_CHOICE="openrouter/auto"
  fi
else
  if [[ -z "$MODEL_CHOICE" ]]; then
    case "$PRIMARY_PROVIDER" in
      openrouter) MODEL_CHOICE="openrouter/auto" ;;
      openai) MODEL_CHOICE="gpt-4o" ;;
      xai) MODEL_CHOICE="grok-2" ;;
      deepseek) MODEL_CHOICE="deepseek-chat" ;;
      *) MODEL_CHOICE="openrouter/auto" ;;
    esac
  fi
fi

# Validate Telegram Token if provided
if [[ -n "$TELEGRAM_TOKEN" && "$DRY_RUN" -eq 0 ]]; then
  echo -e "${CYAN}→ Validating Telegram Bot Token with Telegram API...${RESET}"
  BOT_INFO=$(curl -sS --max-time 10 "https://api.telegram.org/bot${TELEGRAM_TOKEN}/getMe" 2>/dev/null || echo '{"ok":false}')
  if echo "$BOT_INFO" | grep -q '"ok":true'; then
    BOT_USERNAME=$(echo "$BOT_INFO" | sed -n 's/.*"username":"\([^"]*\)".*/\1/p')
    echo -e "  ${GREEN}✓ Telegram bot verified: @${BOT_USERNAME}${RESET}"
  else
    echo -e "  ${YELLOW}! Warning: Telegram token could not be verified online. Proceeding anyway.${RESET}"
  fi
fi

# In dry-run mode, print summary and exit
if [[ "$DRY_RUN" -eq 1 ]]; then
  echo -e "${BOLD}${GREEN}=== Dry Run Plan ===${RESET}"
  echo "Companion Name:       $COMPANION_NAME"
  echo "Human Name:           $HUMAN_NAME"
  echo "Primary Model:        $MODEL_CHOICE ($PRIMARY_PROVIDER)"
  echo "Telegram Bot Token:   $([ -n "$TELEGRAM_TOKEN" ] && echo "[configured (${#TELEGRAM_TOKEN} chars)]" || echo "[none]")"
  echo "Telegram User ID:     ${TELEGRAM_USER_ID:-[none]}"
  echo "OpenRouter Key:       $([ -n "$OPENROUTER_KEY" ] && echo "[configured (${#OPENROUTER_KEY} chars)]" || echo "[none]")"
  echo "OpenAI Key:           $([ -n "$OPENAI_KEY" ] && echo "[configured (${#OPENAI_KEY} chars)]" || echo "[none]")"
  echo "DeepSeek Key:         $([ -n "$DEEPSEEK_KEY" ] && echo "[configured (${#DEEPSEEK_KEY} chars)]" || echo "[none]")"
  echo "xAI (Grok) Key:       $([ -n "$XAI_KEY" ] && echo "[configured (${#XAI_KEY} chars)]" || echo "[none]")"
  echo "GitHub Token:         $([ -n "$GITHUB_TOKEN" ] && echo "[configured (${#GITHUB_TOKEN} chars)]" || echo "[none]")"
  echo "Remote PIN:           $([ -n "$REMOTE_PIN" ] && echo "[configured (4 digits)]" || echo "[none - open to LAN]")"
  echo "Web Port:             $PORT"
  echo "Target Directories:   $HOME_DIR, $HERMES_HOME, $KIT_DIR"
  echo -e "${GREEN}Dry run completed successfully.${RESET}"
  exit 0
fi

# ------------------------------------------------------------------------------
# Step 1: Install Termux packages
# ------------------------------------------------------------------------------
if [[ "$IS_TERMUX" -eq 1 ]]; then
  echo -e "${CYAN}→ Installing required Termux packages (python 3.11, git, curl, build tools)...${RESET}"
  export DEBIAN_FRONTEND=noninteractive
  # Remember the user's package set before the first install.  The uninstaller
  # uses this immutable manifest to remove only packages added by Tamanitomo.
  TERMUX_BASELINE="${HOME_DIR}/.tamanitomo-termux-baseline-packages"
  if [[ ! -f "$TERMUX_BASELINE" ]]; then
    dpkg-query -W -f='${db:Status-Abbrev} ${binary:Package}\n' 2>/dev/null | awk '$1 == "ii" { sub(/:.*/, "", $2); print $2 }' | sort -u > "$TERMUX_BASELINE"
    chmod 0600 "$TERMUX_BASELINE"
  fi
  dpkg --configure -a --force-confdef --force-confold 2>/dev/null || true
  pkg update -y -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" || true
  pkg install -y -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" tur-repo || true
  # apt installs all or nothing: one unavailable package here used to silently
  # skip python3.11 and rust too.  Retry one at a time so the rest still land.
  TERMUX_PACKAGES=(python3.11 git clang rust binutils make pkg-config libffi openssl nodejs ripgrep tmux curl termux-services termux-api jq termux-tools libjpeg-turbo libpng libheif)
  if ! pkg install -y -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" "${TERMUX_PACKAGES[@]}"; then
    echo -e "  ${YELLOW}! Installing the packages together failed; retrying one at a time...${RESET}"
    FAILED_PACKAGES=()
    for package in "${TERMUX_PACKAGES[@]}"; do
      pkg install -y -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" "$package" || FAILED_PACKAGES+=("$package")
    done
    if [[ ${#FAILED_PACKAGES[@]} -gt 0 ]]; then
      echo -e "  ${YELLOW}! Could not install: ${FAILED_PACKAGES[*]}${RESET}"
    fi
  fi
  if ! command -v python3.11 >/dev/null 2>&1; then
    python_missing_error
    exit 1
  fi
  ln -sf "$(command -v python3.11)" "$PREFIX_DIR/bin/python" 2>/dev/null || true
  ln -sf "$(command -v python3.11)" "$PREFIX_DIR/bin/python3" 2>/dev/null || true
fi

# ------------------------------------------------------------------------------
# Step 1.5: Acquire Pre-compiled Wheelhouse (aarch64)
# ------------------------------------------------------------------------------
mkdir -p "$WHEELS_DIR"
SYS_ARCH="$(uname -m 2>/dev/null || echo "unknown")"

if [[ "$SYS_ARCH" == "aarch64" || "$SYS_ARCH" == "arm64" ]]; then
  echo -e "${CYAN}→ Checking for pre-compiled aarch64 wheelhouse (fast binary install)...${RESET}"

  # 1. Custom source provided via flag
  if [[ -n "$WHEELHOUSE_SOURCE" ]]; then
    if [[ -d "$WHEELHOUSE_SOURCE" ]]; then
      cp "$WHEELHOUSE_SOURCE"/*.whl "$WHEELS_DIR/" 2>/dev/null || true
    elif [[ -f "$WHEELHOUSE_SOURCE" && "$WHEELHOUSE_SOURCE" == *.tar.gz ]]; then
      tar -xzf "$WHEELHOUSE_SOURCE" -C "$WHEELS_DIR" 2>/dev/null || true
    elif [[ "$WHEELHOUSE_SOURCE" =~ ^https?:// ]]; then
      TAR_TMP="$HERMES_HOME/.wheelhouse-custom.tar.gz"
      if curl -fsSL "$WHEELHOUSE_SOURCE" -o "$TAR_TMP" 2>/dev/null; then
        tar -xzf "$TAR_TMP" -C "$WHEELS_DIR" 2>/dev/null || true
        rm -f "$TAR_TMP"
      fi
    fi
  fi

  # 2. Local check: repository wheels or wheelhouse tarballs
  if [[ $(find "$WHEELS_DIR" -maxdepth 1 -name "*.whl" 2>/dev/null | wc -l) -lt 10 ]]; then
    for candidate_dir in "$CURRENT_DIR/wheels" "$KIT_DIR/wheels" "$HOME_DIR/tamanitomo/wheels" "$HOME_DIR/companion-kit/wheels"; do
      if [[ -d "$candidate_dir" && $(find "$candidate_dir" -maxdepth 1 -name "*.whl" 2>/dev/null | wc -l) -ge 10 ]]; then
        cp "$candidate_dir"/*.whl "$WHEELS_DIR/" 2>/dev/null || true
        break
      fi
    done
  fi

  if [[ $(find "$WHEELS_DIR" -maxdepth 1 -name "*.whl" 2>/dev/null | wc -l) -lt 10 ]]; then
    for candidate_tar in "$CURRENT_DIR/tamanitomo-wheels-aarch64.tar.gz" "$KIT_DIR/tamanitomo-wheels-aarch64.tar.gz" "$CURRENT_DIR/companion-wheels-aarch64.tar.gz" "$KIT_DIR/companion-wheels-aarch64.tar.gz" "$HOME_DIR/companion-kit/companion-wheels-aarch64.tar.gz"; do
      if [[ -f "$candidate_tar" ]]; then
        tar -xzf "$candidate_tar" -C "$WHEELS_DIR" 2>/dev/null || true
        break
      fi
    done
  fi

  # 3. Remote download from GitHub wheelhouse branch
  if [[ $(find "$WHEELS_DIR" -maxdepth 1 -name "*.whl" 2>/dev/null | wc -l) -lt 10 ]]; then
    WHEEL_URL="https://raw.githubusercontent.com/tamanitomo/tamanitomo/refs/heads/wheelhouse-aarch64/companion-wheels-aarch64.tar.gz"
    WHEEL_URL_ALT="https://github.com/tamanitomo/tamanitomo/raw/refs/heads/wheelhouse-aarch64/companion-wheels-aarch64.tar.gz"
    CURL_AUTH=()
    if [[ -n "$GITHUB_TOKEN" ]]; then
      CURL_AUTH=(-H "Authorization: token $GITHUB_TOKEN")
    fi
    TAR_TMP="$HERMES_HOME/.wheels-download.tar.gz"
    echo -e "  Attempting to fetch binary wheels from GitHub (~21 MB)..."
    if curl -fsSL "${CURL_AUTH[@]}" "$WHEEL_URL" -o "$TAR_TMP" 2>/dev/null || \
       curl -fsSL "${CURL_AUTH[@]}" "$WHEEL_URL_ALT" -o "$TAR_TMP" 2>/dev/null; then
      tar -xzf "$TAR_TMP" -C "$WHEELS_DIR" 2>/dev/null || true
      rm -f "$TAR_TMP"
    fi

    # 4. Git clone fallback for private/custom forks
    if [[ $(find "$WHEELS_DIR" -maxdepth 1 -name "*.whl" 2>/dev/null | wc -l) -lt 10 ]]; then
      GIT_URL="https://github.com/tamanitomo/tamanitomo.git"
      if [[ -n "$GITHUB_TOKEN" ]]; then
        GIT_URL="https://${GITHUB_TOKEN}@github.com/tamanitomo/tamanitomo.git"
      fi
      GIT_TMP="$HERMES_HOME/.wheelhouse-git-tmp"
      rm -rf "$GIT_TMP"
      if git clone --depth 1 --branch wheelhouse-aarch64 "$GIT_URL" "$GIT_TMP" 2>/dev/null; then
        if [[ -f "$GIT_TMP/companion-wheels-aarch64.tar.gz" ]]; then
          tar -xzf "$GIT_TMP/companion-wheels-aarch64.tar.gz" -C "$WHEELS_DIR" 2>/dev/null || true
        elif [[ -d "$GIT_TMP/wheels" ]]; then
          cp "$GIT_TMP/wheels/"*.whl "$WHEELS_DIR/" 2>/dev/null || true
        fi
        rm -rf "$GIT_TMP"
      fi
    fi
  fi

  WHEEL_COUNT=$(find "$WHEELS_DIR" -maxdepth 1 -name "*.whl" 2>/dev/null | wc -l || echo 0)
  if [[ "$WHEEL_COUNT" -ge 10 ]]; then
    echo -e "  ${GREEN}✓ Wheelhouse active: ${WHEEL_COUNT} pre-compiled binary packages ready (skips 25+ min Rust build).${RESET}"
    export PIP_FIND_LINKS="$WHEELS_DIR"
  else
    echo -e "  ${YELLOW}! Pre-compiled wheels not found; pip will build packages from source if needed.${RESET}"
  fi
fi

# Hermes requires nemo-relay everywhere except Android, and recognises Android by
# "android" in the kernel release string. Older (pre-GKI) phone kernels do not
# carry it, so pip sets out to compile nemo-relay's Rust from source and the
# install dies with "Failed to build nemo-relay". Hermes runs without it (the
# relay falls back to a no-op), so on the phone install Hermes's dependency list
# without it and then Hermes itself with --no-deps -- the workaround Hermes's own
# pyproject names for these devices.
hermes_requirements_without_relay() {
  "$1/bin/python" - "$2/pyproject.toml" <<'PY'
import re, sys, tomllib
with open(sys.argv[1], 'rb') as fh:
    dependencies = tomllib.load(fh)['project']['dependencies']
for dependency in dependencies:
    name = re.split(r'[\s;<>=!~\[(]', dependency.strip(), maxsplit=1)[0]
    if re.sub(r'[-_.]+', '-', name).lower() != 'nemo-relay':
        print(dependency)
PY
}

install_hermes_on_phone() {
  local venv="$1" repo="$2" requirements="$1/.hermes-requirements.txt"
  if ! hermes_requirements_without_relay "$venv" "$repo" > "$requirements"; then
    echo -e "${RED}Error: could not read Hermes's dependency list from $repo/pyproject.toml.${RESET}" >&2
    exit 1
  fi
  pip_install "$venv" -r "$requirements"
  pip_install "$venv" --no-deps -e "$repo"
}

# ------------------------------------------------------------------------------
# Step 2: Set up Hermes Agent
# ------------------------------------------------------------------------------
mkdir -p "$HERMES_HOME" "$HERMES_HOME/scripts" "$HERMES_HOME/cron" "$HERMES_HOME/memories" "$HERMES_HOME/skills"

if ! command -v hermes >/dev/null 2>&1; then
  echo -e "${CYAN}→ Installing Hermes Agent runtime...${RESET}"
  if [[ "$IS_TERMUX" -eq 1 ]]; then
    HERMES_REPO="$HERMES_HOME/hermes-agent"
    HERMES_VENV="$HERMES_REPO/venv"
    if [[ ! -d "$HERMES_REPO/.git" ]]; then
      echo -e "  Cloning Hermes Agent repository..."
      rm -rf "$HERMES_REPO"
      git clone --depth 1 https://github.com/NousResearch/hermes-agent.git "$HERMES_REPO"
    fi
    # Not gated on the venv existing: a run that failed half way left one
    # behind without hermes in it, and every later run skipped the install.
    echo -e "  Setting up Hermes virtual environment..."
    ensure_venv "$HERMES_VENV"
    install_wheelhouse "$HERMES_VENV"
    if [[ -f "$HERMES_REPO/pyproject.toml" ]]; then
      echo -e "  Installing Hermes Agent..."
      install_hermes_on_phone "$HERMES_VENV" "$HERMES_REPO"
    fi
  else
    curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash -s -- --skip-setup || curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash -s -- --skip-setup
  fi
fi

if [[ -f "$HERMES_HOME/hermes-agent/venv/bin/hermes" && ! -f "$PREFIX_DIR/bin/hermes" ]]; then
  ln -sf "$HERMES_HOME/hermes-agent/venv/bin/hermes" "$PREFIX_DIR/bin/hermes" 2>/dev/null || true
fi

# ------------------------------------------------------------------------------
# Step 3: Write Secure Credentials (.env)
# ------------------------------------------------------------------------------
echo -e "${CYAN}→ Writing credentials to $HERMES_HOME/.env...${RESET}"
ENV_FILE="$HERMES_HOME/.env"
touch "$ENV_FILE"
chmod 0600 "$ENV_FILE"

# Helper to upsert key-value in .env
upsert_env() {
  local key="$1" value="$2"
  [[ -z "$value" ]] && return 0
  python3 - "$ENV_FILE" "$key" "$value" <<'PYENV'
import json, re, sys
from pathlib import Path
path = Path(sys.argv[1])
key, value = sys.argv[2:]
lines = path.read_text().splitlines() if path.exists() else []
lines = [line for line in lines if not re.match(r'^\s*(?:export\s+)?' + re.escape(key) + r'\s*=', line)]
lines.append(key + '=' + json.dumps(value))
path.write_text('\n'.join(lines) + '\n')
path.chmod(0o600)
PYENV
}

upsert_env "TELEGRAM_BOT_TOKEN" "$TELEGRAM_TOKEN"
upsert_env "TELEGRAM_ALLOWED_USERS" "$TELEGRAM_USER_ID"
upsert_env "TELEGRAM_HOME_CHANNEL" "$TELEGRAM_USER_ID"
upsert_env "OPENROUTER_API_KEY" "$OPENROUTER_KEY"
upsert_env "OPENAI_API_KEY" "$OPENAI_KEY"
upsert_env "DEEPSEEK_API_KEY" "$DEEPSEEK_KEY"
upsert_env "XAI_API_KEY" "$XAI_KEY"
upsert_env "HERMES_ACCEPT_HOOKS" "1"

# ------------------------------------------------------------------------------
# Step 4: Write Hermes Configuration (config.yaml)
# ------------------------------------------------------------------------------
echo -e "${CYAN}→ Generating $HERMES_HOME/config.yaml...${RESET}"
CONFIG_YAML="$HERMES_HOME/config.yaml"

if [[ ! -f "$CONFIG_YAML" ]]; then
cat > "$CONFIG_YAML" <<EOF
model:
  default: ${MODEL_CHOICE}
  provider: ${PRIMARY_PROVIDER}

fallback_providers:
EOF

if [[ -n "$OPENROUTER_KEY" && "$PRIMARY_PROVIDER" != "openrouter" ]]; then
  cat >> "$CONFIG_YAML" <<EOF
- provider: openrouter
  model: openrouter/auto
EOF
fi

if [[ -n "$OPENAI_KEY" && "$PRIMARY_PROVIDER" != "openai" ]]; then
  cat >> "$CONFIG_YAML" <<EOF
- provider: openai
  model: gpt-4o
EOF
fi

if [[ -n "$DEEPSEEK_KEY" && "$PRIMARY_PROVIDER" != "deepseek" ]]; then
  cat >> "$CONFIG_YAML" <<EOF
- provider: deepseek
  model: deepseek-chat
EOF
fi

if [[ -n "$XAI_KEY" && "$PRIMARY_PROVIDER" != "xai" ]]; then
  cat >> "$CONFIG_YAML" <<EOF
- provider: xai
  model: grok-2
EOF
fi

cat >> "$CONFIG_YAML" <<EOF

telegram:
  reactions: false
  allowed_chats: '${TELEGRAM_USER_ID}'
  extra:
    rich_messages: false

agent:
  max_turns: 60
  gateway_timeout: 1800
  restart_drain_timeout: 180
  api_max_retries: 3
  reasoning_effort: medium

hooks_auto_accept: true

terminal:
  backend: local
  timeout: 180
  auto_source_bashrc: true
EOF

fi
chmod 0600 "$CONFIG_YAML"

# ------------------------------------------------------------------------------
# Step 5: Setup Companion Kit & Python Virtual Environment
# ------------------------------------------------------------------------------
echo -e "${CYAN}→ Setting up Companion Kit in $KIT_DIR...${RESET}"
mkdir -p "$VAULT_DIR"

REPO_URL="https://github.com/tamanitomo/tamanitomo.git"
if [[ -n "$GITHUB_TOKEN" ]]; then
  REPO_URL="https://${GITHUB_TOKEN}@github.com/tamanitomo/tamanitomo.git"
fi
if [[ ! -f "$KIT_DIR/kit/cli/main.py" ]]; then
  echo -e "  Cloning Companion Kit repository..."
  mkdir -p "$(dirname "$KIT_DIR")"
  if ! git clone "$REPO_URL" "$KIT_DIR"; then
    echo -e "${RED}Error: Failed to clone tamanitomo repository.${RESET}" >&2
    if [[ -z "$GITHUB_TOKEN" ]]; then
      echo -e "${YELLOW}If tamanitomo/tamanitomo is private, pass your GitHub token:${RESET}" >&2
      echo -e "  bash setup-termux.sh --github-token <YOUR_GITHUB_TOKEN> ...${RESET}" >&2
    fi
    exit 1
  fi
  sync_to_release "$KIT_DIR" "$REPO_URL" 1
else
  echo -e "  Updating the existing install..."
  sync_to_release "$KIT_DIR" "$REPO_URL"
fi

VENV_DIR="$KIT_DIR/.venv"
ensure_venv "$VENV_DIR"

echo -e "  Installing Companion Kit Python dependencies..."
install_wheelhouse "$VENV_DIR"
if [[ -f "$KIT_DIR/requirements.txt" ]]; then
  pip_install "$VENV_DIR" -r "$KIT_DIR/requirements.txt"
else
  echo 'Repository requirements.txt is missing; installation cannot continue.' >&2
  exit 1
fi

# ------------------------------------------------------------------------------
# Step 6: Environment Ready for Web Onboarding
# ------------------------------------------------------------------------------
echo -e "${CYAN}→ Environment provisioned. Leaving profiles at 0 for interactive web onboarding...${RESET}"

# Preserve existing provider choices and save host access before starting services.
"$VENV_DIR/bin/python" - "$HERMES_HOME" "$MODEL_CHOICE" "$PRIMARY_PROVIDER" "$REMOTE_PIN" <<'PYCONFIG'
import json, os, sys
from pathlib import Path
import yaml
root = Path(sys.argv[1])
path = root / 'config.yaml'
cfg = yaml.safe_load(path.read_text()) if path.exists() else {}
cfg = {} if cfg is None else cfg
if not isinstance(cfg, dict):
    raise SystemExit('Existing Hermes configuration must be a mapping; left unchanged.')
if 'model' not in cfg:
    cfg['model'] = {'default': sys.argv[2], 'provider': sys.argv[3]}
    with path.open('w') as stream:
        yaml.safe_dump(cfg, stream)
    path.chmod(0o600)
if sys.argv[4]:
    access = root / '.tamanitomo-access.json'
    fd = os.open(access, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump({'remote_pin': sys.argv[4]}, stream)
    access.chmod(0o600)
PYCONFIG

# ------------------------------------------------------------------------------
# Step 7: Configure 24/7 Background Supervision (termux-services / runit)
# ------------------------------------------------------------------------------
if [[ "$IS_TERMUX" -eq 1 ]]; then
  echo -e "${CYAN}→ Setting up 24/7 background services in Termux...${RESET}"
  SV_DIR="$PREFIX_DIR/var/service"
  mkdir -p "$SV_DIR/tamanitomo-gateway/log" "$SV_DIR/tamanitomo-workspace/log"

  # 1. Tamanitomo Gateway run script (Hermes Gateway)
  cat > "$SV_DIR/tamanitomo-gateway/run" <<EOF
#!/data/data/com.termux/files/usr/bin/sh
export HOME=${HOME_DIR}
export PREFIX=${PREFIX_DIR}
export HERMES_HOME=${HERMES_HOME}
export PATH="${HERMES_HOME}/hermes-agent/venv/bin:${KIT_DIR}/.venv/bin:${PREFIX_DIR}/bin:\$PATH"
export HERMES_ACCEPT_HOOKS=1
cd "${HOME_DIR}" || exit 1

# Network rollover guard: Allow sockets and routing to settle (e.g. during Wi-Fi to 5G handover)
sleep 2

exec hermes gateway run --replace
EOF
  chmod +x "$SV_DIR/tamanitomo-gateway/run"

  # Runit finish hook: backoff between restarts to prevent Telegram API 429 throttling on rollover
  cat > "$SV_DIR/tamanitomo-gateway/finish" <<EOF
#!/data/data/com.termux/files/usr/bin/sh
sleep 3
EOF
  chmod +x "$SV_DIR/tamanitomo-gateway/finish"

  # Gateway logger
  cat > "$SV_DIR/tamanitomo-gateway/log/run" <<EOF
#!/data/data/com.termux/files/usr/bin/sh
export LOGDIR=${PREFIX_DIR}/var/log
exec ${PREFIX_DIR}/share/termux-services/svlogger
EOF
  chmod +x "$SV_DIR/tamanitomo-gateway/log/run"

  # 2. Tamanitomo Workspace run script
  cat > "$SV_DIR/tamanitomo-workspace/run" <<EOF
#!/data/data/com.termux/files/usr/bin/sh
export HOME=${HOME_DIR}
export PREFIX=${PREFIX_DIR}
export HERMES_HOME=${HERMES_HOME}
export TAMANITOMO_BIND=0.0.0.0
export TAMANITOMO_PORT=${PORT}
export COMPANION_BIND=0.0.0.0
export COMPANION_PORT=${PORT}
export PATH="${KIT_DIR}/.venv/bin:${PREFIX_DIR}/bin:\$PATH"
export PYTHONPATH="${KIT_DIR}:${KIT_DIR}/kit/scripts"
cd "${KIT_DIR}" || exit 1
exec ${KIT_DIR}/.venv/bin/python -m kit.app.hosted
EOF
  chmod +x "$SV_DIR/tamanitomo-workspace/run"

  # Workspace logger
  cat > "$SV_DIR/tamanitomo-workspace/log/run" <<EOF
#!/data/data/com.termux/files/usr/bin/sh
export LOGDIR=${PREFIX_DIR}/var/log
exec ${PREFIX_DIR}/share/termux-services/svlogger
EOF
  chmod +x "$SV_DIR/tamanitomo-workspace/log/run"

  # Backward compatibility symlinks for legacy service names
  ln -sfn "$SV_DIR/tamanitomo-gateway" "$SV_DIR/companion-gateway"
  ln -sfn "$SV_DIR/tamanitomo-workspace" "$SV_DIR/companion-workspace"

  # Setup Termux:Boot autostart script
  BOOT_DIR="$HOME_DIR/.termux/boot"
  mkdir -p "$BOOT_DIR"
  cat > "$BOOT_DIR/start-tamanitomo-services" <<EOF
#!/data/data/com.termux/files/usr/bin/sh
/data/data/com.termux/files/usr/bin/termux-wake-lock >/dev/null 2>&1 || true
export PREFIX=${PREFIX_DIR}
export HOME=${HOME_DIR}
export SVDIR="${PREFIX_DIR}/var/service"
export LOGDIR="${PREFIX_DIR}/var/log"
export PATH="${PREFIX_DIR}/bin:${KIT_DIR}/.venv/bin:\$PATH"

/data/data/com.termux/files/usr/bin/service-daemon start >/dev/null 2>&1 &
EOF
  chmod +x "$BOOT_DIR/start-tamanitomo-services"
  ln -sfn "$BOOT_DIR/start-tamanitomo-services" "$BOOT_DIR/start-companion-services"

  # Enable and start services via termux-services
  export SVDIR="$SV_DIR"
  for rc in "$HOME_DIR/.bashrc" "$HOME_DIR/.profile"; do
    if ! grep -q "SVDIR=" "$rc" 2>/dev/null; then
      echo "export SVDIR=\"${PREFIX_DIR}/var/service\"" >> "$rc"
    fi
  done
  if [[ -f "${PREFIX_DIR}/etc/profile.d/start-services.sh" ]]; then
    # shellcheck disable=SC1090
    source "${PREFIX_DIR}/etc/profile.d/start-services.sh" 2>/dev/null || true
  fi
  if command -v sv-enable >/dev/null 2>&1; then
    sv-enable tamanitomo-gateway || true
    sv-enable tamanitomo-workspace || true
  fi
  if command -v service-daemon >/dev/null 2>&1; then
    service-daemon start >/dev/null 2>&1 || true
  fi

  # Wait for runsvdir to scan $SVDIR and attach service supervisors (up to 10 seconds)
  echo -e "  Waiting for background service supervisor to initialize..."
  for i in {1..10}; do
    if sv status tamanitomo-workspace >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done

  if command -v sv >/dev/null 2>&1; then
    sv up tamanitomo-gateway >/dev/null 2>&1 || true
    sv up tamanitomo-workspace >/dev/null 2>&1 || true
  fi

  # Check actual service status
  GATEWAY_RUNNING=0
  WORKSPACE_RUNNING=0
  if command -v sv >/dev/null 2>&1; then
    if sv status tamanitomo-gateway 2>/dev/null | grep -q "^run:"; then
      GATEWAY_RUNNING=1
    fi
    if sv status tamanitomo-workspace 2>/dev/null | grep -q "^run:"; then
      WORKSPACE_RUNNING=1
    fi
  fi
fi

# Send initial Telegram greeting if chat_id and token are set
if [[ -n "$TELEGRAM_TOKEN" && -n "$TELEGRAM_USER_ID" ]]; then
  echo -e "${CYAN}→ Sending connection handshake message to Telegram...${RESET}"
  curl -sS -X POST "https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage" \
    -d chat_id="${TELEGRAM_USER_ID}" \
    -d text="✨ Hello ${HUMAN_NAME}! Your companion server is now live on Android Termux. Send me a message anytime!" >/dev/null 2>&1 || true
fi

# Get Local IP Address
LOCAL_IP="127.0.0.1"
if command -v ip >/dev/null 2>&1; then
  LOCAL_IP=$(ip -4 addr show scope global | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -n 1 || echo "127.0.0.1")
elif command -v ifconfig >/dev/null 2>&1; then
  LOCAL_IP=$(ifconfig wlan0 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' || echo "127.0.0.1")
fi

# ------------------------------------------------------------------------------
# Final Summary & Success Banner
# ------------------------------------------------------------------------------
echo ""
echo -e "${BOLD}${GREEN}================================================================${RESET}"
echo -e "${BOLD}${GREEN}  ✓ Tamanitomo Setup Complete! ${RESET}"
echo -e "${BOLD}${GREEN}================================================================${RESET}"
echo ""
echo -e "  ${BOLD}Interactive Setup:${RESET}   Open ${CYAN}http://localhost:${PORT}${RESET} (or ${CYAN}http://${LOCAL_IP}:${PORT}${RESET}) in your browser"
echo -e "                         to begin your interactive onboarding and bring ${BOLD}${COMPANION_NAME}${RESET} to life!"
echo -e "  ${BOLD}Primary Model:${RESET}       ${MODEL_CHOICE:-'(Configure in Web Onboarding)'} (${PRIMARY_PROVIDER:-'Cloud'})"
if [[ "$IS_TERMUX" -eq 1 ]]; then
  if [[ "$WORKSPACE_RUNNING" -eq 1 ]]; then
    echo -e "  ${BOLD}Workspace Service:${RESET}   ${GREEN}Active & Serving${RESET}"
  else
    echo -e "  ${BOLD}Workspace Service:${RESET}   ${YELLOW}Pending shell restart${RESET}"
    echo -e "                         ${YELLOW}(If page does not load, run: ${CYAN}source \$PREFIX/etc/profile.d/start-services.sh && sv up tamanitomo-workspace${YELLOW})${RESET}"
  fi
  if [[ "$GATEWAY_RUNNING" -eq 1 ]]; then
    echo -e "  ${BOLD}Hermes Gateway:${RESET}      ${GREEN}Active${RESET}"
  elif [[ -n "$TELEGRAM_TOKEN" ]]; then
    echo -e "  ${BOLD}Hermes Gateway:${RESET}      ${YELLOW}Pending start${RESET} (${DIM}sv up tamanitomo-gateway${RESET})"
  fi
fi
if [[ -n "$REMOTE_PIN" ]]; then
  echo -e "  ${BOLD}Remote Access PIN:${RESET}   ${GREEN}Configured${RESET}"
else
  echo -e "  ${BOLD}Remote Access PIN:${RESET}   ${YELLOW}None (Open to local network)${RESET}"
fi
if [[ -n "$TELEGRAM_TOKEN" ]]; then
  echo -e "  ${BOLD}Telegram Bot:${RESET}        ${GREEN}Configured${RESET}"
fi
echo ""
echo -e "${BOLD}Important Android Termux Tips:${RESET}"
echo -e "  1. ${BOLD}Battery Optimization:${RESET} Go to Android Settings → Apps → Termux → Battery"
echo -e "     and set to ${YELLOW}Unrestricted / Don't optimize${RESET} so Android does not sleep."
echo -e "  2. ${BOLD}Autostart on Reboot:${RESET} Install ${CYAN}Termux:Boot${RESET} from F-Droid to automatically"
echo -e "     start your companion whenever the phone restarts."
echo -e "  3. ${BOLD}Service Controls:${RESET}"
echo -e "     • Check gateway:   ${DIM}sv status tamanitomo-gateway${RESET}"
echo -e "     • Check workspace: ${DIM}sv status tamanitomo-workspace${RESET}"
echo -e "     • Restart:         ${DIM}sv restart tamanitomo-gateway${RESET}"
echo -e "     • Manual start:    ${DIM}cd ~/tamanitomo && ./.venv/bin/python -m kit.app.hosted${RESET}"
echo ""
echo -e "${BOLD}Open ${CYAN}http://${LOCAL_IP}:${PORT}${RESET} to begin!${RESET}"
