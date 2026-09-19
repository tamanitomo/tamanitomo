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

# Detect Termux or Test Mode
IS_TERMUX=0
if [[ -n "${PREFIX:-}" && "$PREFIX" == *"com.termux"* ]] || [[ -d "/data/data/com.termux" ]]; then
  IS_TERMUX=1
fi

if [[ "$IS_TERMUX" -eq 0 && "$TEST_MODE" -eq 0 && "$DRY_RUN" -eq 0 ]]; then
  echo -e "${YELLOW}Warning: Not running inside Android Termux.${RESET}"
  echo -e "If you are testing this installer on a standard Linux PC, use ${BOLD}--test-mode${RESET}."
  read -r -p "Continue anyway in test mode? [y/N]: " proceed
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
  mkdir -p "$PREFIX_DIR"
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

echo -e "${DIM}Destination home: ${HOME_DIR}${RESET}"
echo -e "${DIM}Hermes directory: ${HERMES_HOME}${RESET}"
echo -e "${DIM}Tamanitomo:       ${KIT_DIR}${RESET}"
echo ""

if [[ "$UPGRADE_MODE" -eq 1 ]]; then
  echo -e "${CYAN}→ Upgrading existing installation in $KIT_DIR...${RESET}"
  if [[ ! -d "$KIT_DIR" ]]; then
    echo -e "${RED}Error: Cannot find existing installation at $KIT_DIR${RESET}" >&2
    exit 1
  fi
  if [[ -d "$KIT_DIR/.git" ]]; then
    echo -e "  Pulling latest commits from git..."
    git -C "$KIT_DIR" fetch origin main 2>/dev/null || true
    git -C "$KIT_DIR" pull --ff-only origin main 2>/dev/null || true
  fi
  VENV_DIR="$KIT_DIR/.venv"
  if [[ -f "$KIT_DIR/requirements.txt" && -x "$VENV_DIR/bin/pip" ]]; then
    echo -e "  Updating Python dependencies..."
    "$VENV_DIR/bin/pip" install -r "$KIT_DIR/requirements.txt" >/dev/null 2>&1 || true
  fi
  echo -e "  Refreshing companion templates and cron shims..."
  "$VENV_DIR/bin/python" "$KIT_DIR/bin/tamanitomo" --home "$HERMES_HOME" upgrade --answers "$HOME_DIR/.companion-init-answers.json" >/dev/null 2>&1 || \
  "$VENV_DIR/bin/python" "$KIT_DIR/bin/tamanitomo" --home "$HERMES_HOME" upgrade >/dev/null 2>&1 || true
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
if [[ "$IS_TERMUX" -eq 1 ]]; then
  echo -e "${CYAN}→ Acquiring Termux wake-lock (prevents sleep while serving)...${RESET}"
  if command -v termux-wake-lock >/dev/null 2>&1; then
    termux-wake-lock || true
  fi
fi

# ------------------------------------------------------------------------------
# Interactive prompts for credentials if not supplied via flags
# ------------------------------------------------------------------------------
if [[ "$NON_INTERACTIVE" -eq 0 && "$DRY_RUN" -eq 0 ]]; then
  if [[ -t 0 ]]; then
    echo -e "${BOLD}1. Companion Identity${RESET}"
    read -r -p "   Companion Name [${COMPANION_NAME}]: " input_name
    COMPANION_NAME="${input_name:-$COMPANION_NAME}"

    read -r -p "   Your Name [${HUMAN_NAME}]: " input_human
    HUMAN_NAME="${input_human:-$HUMAN_NAME}"
    echo ""

    echo -e "${BOLD}2. Telegram Configuration (24/7 companion messaging)${RESET}"
    echo -e "${DIM}   Create a bot with @BotFather on Telegram to get your token.${RESET}"
    if [[ -z "$TELEGRAM_TOKEN" ]]; then
      read -r -p "   Telegram Bot Token: " TELEGRAM_TOKEN
    else
      echo -e "   Telegram Bot Token: ${GREEN}[Provided via flag]${RESET}"
    fi

    if [[ -z "$TELEGRAM_USER_ID" ]]; then
      echo -e "${DIM}   Find your numeric User ID by messaging @userinfobot on Telegram.${RESET}"
      read -r -p "   Telegram User ID (numeric chat owner): " TELEGRAM_USER_ID
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
      read -r -p "   Choose primary provider [1-4, default: 1]: " provider_num
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
          read -r -p "   OpenRouter API Key: " OPENROUTER_KEY
        else
          echo -e "   OpenRouter API Key:  ${GREEN}[Provided via flag]${RESET}"
        fi
        [[ -z "$MODEL_CHOICE" ]] && MODEL_CHOICE="openrouter/auto"
        ;;
      openai)
        if [[ -z "$OPENAI_KEY" ]]; then
          read -r -p "   OpenAI API Key: " OPENAI_KEY
        else
          echo -e "   OpenAI API Key:      ${GREEN}[Provided via flag]${RESET}"
        fi
        [[ -z "$MODEL_CHOICE" ]] && MODEL_CHOICE="gpt-4o"
        ;;
      xai)
        if [[ -z "$XAI_KEY" ]]; then
          read -r -p "   xAI (Grok) API Key: " XAI_KEY
        else
          echo -e "   xAI (Grok) API Key:  ${GREEN}[Provided via flag]${RESET}"
        fi
        [[ -z "$MODEL_CHOICE" ]] && MODEL_CHOICE="grok-2"
        ;;
      deepseek)
        if [[ -z "$DEEPSEEK_KEY" ]]; then
          read -r -p "   DeepSeek API Key: " DEEPSEEK_KEY
        else
          echo -e "   DeepSeek API Key:    ${GREEN}[Provided via flag]${RESET}"
        fi
        [[ -z "$MODEL_CHOICE" ]] && MODEL_CHOICE="deepseek-chat"
        ;;
    esac
    echo ""

    echo -e "${DIM}   (Optional) Secondary / Fallback API Keys (press Enter to skip):${RESET}"
    if [[ "$PRIMARY_PROVIDER" != "openrouter" && -z "$OPENROUTER_KEY" ]]; then
      read -r -p "   OpenRouter API Key (press Enter to skip): " OPENROUTER_KEY
    fi
    if [[ "$PRIMARY_PROVIDER" != "openai" && -z "$OPENAI_KEY" ]]; then
      read -r -p "   OpenAI API Key (press Enter to skip): " OPENAI_KEY
    fi
    if [[ "$PRIMARY_PROVIDER" != "deepseek" && -z "$DEEPSEEK_KEY" ]]; then
      read -r -p "   DeepSeek API Key (press Enter to skip): " DEEPSEEK_KEY
    fi
    if [[ "$PRIMARY_PROVIDER" != "xai" && -z "$XAI_KEY" ]]; then
      read -r -p "   xAI (Grok) API Key (press Enter to skip): " XAI_KEY
    fi
    echo ""

    echo -e "${BOLD}4. Remote Security PIN (Optional 4-digit PIN for Wi-Fi access)${RESET}"
    echo -e "${DIM}   Protect access when visiting from another device on your Wi-Fi (e.g. laptop).${RESET}"
    if [[ -z "$REMOTE_PIN" ]]; then
      read -r -p "   4-Digit PIN (press Enter to skip): " REMOTE_PIN
    else
      echo -e "   4-Digit PIN:         ${GREEN}[Provided via flag]${RESET}"
    fi
    echo ""

    if [[ ! -f "$KIT_DIR/kit/cli/main.py" ]]; then
      echo -e "${BOLD}5. GitHub Access (For Private Repository)${RESET}"
      echo -e "${DIM}   If tamanitomo/tamanitomo is private, supply a GitHub Personal Access Token (PAT).${RESET}"
      if [[ -z "$GITHUB_TOKEN" ]]; then
        read -r -p "   GitHub Token (press Enter to skip): " GITHUB_TOKEN
      else
        echo -e "   GitHub Token:        ${GREEN}[Provided via flag]${RESET}"
      fi
      echo ""
    fi
  fi
fi

# Validate Remote PIN if provided
if [[ -n "$REMOTE_PIN" ]]; then
  if [[ ! "$REMOTE_PIN" =~ ^[0-9]{4}$ ]]; then
    echo -e "${YELLOW}! Warning: Remote PIN must be exactly 4 numeric digits. Disabling PIN protection.${RESET}"
    REMOTE_PIN=""
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
if [[ -n "$TELEGRAM_TOKEN" ]]; then
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
  dpkg --configure -a --force-confdef --force-confold 2>/dev/null || true
  pkg update -y -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" || true
  pkg install -y -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" tur-repo || true
  pkg install -y -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" python3.11 git clang rust make pkg-config libffi openssl nodejs ripgrep tmux curl termux-services termux-api jq termux-tools libjpeg-turbo libpng libheif || true
  if command -v python3.11 >/dev/null 2>&1; then
    ln -sf "$(command -v python3.11)" "$PREFIX_DIR/bin/python" 2>/dev/null || true
    ln -sf "$(command -v python3.11)" "$PREFIX_DIR/bin/python3" 2>/dev/null || true
  fi
fi

# ------------------------------------------------------------------------------
# Step 1.5: Acquire Pre-compiled Wheelhouse (aarch64)
# ------------------------------------------------------------------------------
WHEELS_DIR="$HERMES_HOME/wheels"
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
      git clone --depth 1 https://github.com/NousResearch/hermes-agent.git "$HERMES_REPO" || true
    fi
    if [[ ! -d "$HERMES_VENV" ]]; then
      echo -e "  Setting up Hermes virtual environment..."
      if command -v python3.11 >/dev/null 2>&1; then
        python3.11 -m venv "$HERMES_VENV" 2>/dev/null || python3 -m venv "$HERMES_VENV"
      else
        python3 -m venv "$HERMES_VENV"
      fi
      if [[ -d "$WHEELS_DIR" && $(find "$WHEELS_DIR" -maxdepth 1 -name "*.whl" 2>/dev/null | wc -l) -ge 10 ]]; then
        echo -e "  Installing pre-compiled wheels into Hermes venv..."
        "$HERMES_VENV/bin/pip" install "$WHEELS_DIR"/*.whl >/dev/null 2>&1 || true
      fi
      if [[ -f "$HERMES_REPO/pyproject.toml" ]]; then
        echo -e "  Installing Hermes Agent..."
        "$HERMES_VENV/bin/pip" install -e "$HERMES_REPO" >/dev/null 2>&1 || true
      fi
    fi
  else
    curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash -s -- --skip-setup || curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash -s -- --skip-setup || true
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
  local k="$1"
  local v="$2"
  [[ -z "$v" ]] && return 0
  if grep -q "^${k}=" "$ENV_FILE" 2>/dev/null; then
    sed -i "s|^${k}=.*|${k}=${v}|" "$ENV_FILE"
  else
    echo "${k}=${v}" >> "$ENV_FILE"
  fi
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

chmod 0600 "$CONFIG_YAML"

# ------------------------------------------------------------------------------
# Step 5: Setup Companion Kit & Python Virtual Environment
# ------------------------------------------------------------------------------
echo -e "${CYAN}→ Setting up Companion Kit in $KIT_DIR...${RESET}"
mkdir -p "$VAULT_DIR"

if [[ ! -f "$KIT_DIR/kit/cli/main.py" ]]; then
  echo -e "  Cloning Companion Kit repository..."
  mkdir -p "$(dirname "$KIT_DIR")"
  REPO_URL="https://github.com/tamanitomo/tamanitomo.git"
  if [[ -n "$GITHUB_TOKEN" ]]; then
    REPO_URL="https://${GITHUB_TOKEN}@github.com/tamanitomo/tamanitomo.git"
  fi
  if ! git clone "$REPO_URL" "$KIT_DIR"; then
    echo -e "${RED}Error: Failed to clone tamanitomo repository.${RESET}" >&2
    if [[ -z "$GITHUB_TOKEN" ]]; then
      echo -e "${YELLOW}If tamanitomo/tamanitomo is private, pass your GitHub token:${RESET}" >&2
      echo -e "  bash setup-termux.sh --github-token <YOUR_GITHUB_TOKEN> ...${RESET}" >&2
    fi
    exit 1
  fi
fi

VENV_DIR="$KIT_DIR/.venv"
if [[ ! -d "$VENV_DIR" ]]; then
  echo -e "  Creating Python virtual environment..."
  if command -v python3.11 >/dev/null 2>&1; then
    python3.11 -m venv "$VENV_DIR" || python3 -m venv "$VENV_DIR"
  else
    python3 -m venv "$VENV_DIR"
  fi
fi

echo -e "  Installing Companion Kit Python dependencies..."
"$VENV_DIR/bin/pip" install --upgrade pip >/dev/null 2>&1 || true
if [[ -d "$WHEELS_DIR" && $(find "$WHEELS_DIR" -maxdepth 1 -name "*.whl" 2>/dev/null | wc -l) -ge 10 ]]; then
  "$VENV_DIR/bin/pip" install "$WHEELS_DIR"/*.whl >/dev/null 2>&1 || true
fi
if [[ -f "$KIT_DIR/requirements.txt" ]]; then
  "$VENV_DIR/bin/pip" install -r "$KIT_DIR/requirements.txt" >/dev/null 2>&1 || true
else
  "$VENV_DIR/bin/pip" install fastapi uvicorn pyyaml pydantic httpx requests >/dev/null 2>&1 || true
fi

# ------------------------------------------------------------------------------
# Step 6: Environment Ready for Web Onboarding
# ------------------------------------------------------------------------------
echo -e "${CYAN}→ Environment provisioned. Leaving profiles at 0 for interactive web onboarding...${RESET}"

# Save model configuration to Hermes config.yaml if provider and model were supplied
if [[ -n "$MODEL_CHOICE" ]]; then
  "$VENV_DIR/bin/python" -c "
import yaml, os
cfg_path = '$HERMES_HOME/config.yaml'
cfg = {}
if os.path.exists(cfg_path):
    try:
        with open(cfg_path, 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
    except Exception:
        pass
cfg.setdefault('model', {})
if isinstance(cfg['model'], str):
    cfg['model'] = {'default': cfg['model']}
cfg['model']['default'] = '$MODEL_CHOICE'
if '$PRIMARY_PROVIDER':
    cfg['model']['provider'] = '$PRIMARY_PROVIDER'
with open(cfg_path, 'w', encoding='utf-8') as f:
    yaml.safe_dump(cfg, f)
" || true
fi

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
  echo -e "  ${BOLD}Remote Access PIN:${RESET}   ${GREEN}Active (${REMOTE_PIN})${RESET}"
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
