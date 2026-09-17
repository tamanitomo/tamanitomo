#!/usr/bin/env bash
# ==============================================================================
# Tamanitomo (魂の友) — 1-Command Linux Turnkey Setup
#
# Sets up Tamanitomo + Hermes Agent on Linux (Debian/Ubuntu, Fedora/RHEL, Arch).
# Configures local environment, dependencies, companion profile, and systemd
# background user service (tamanitomo.service).
# ==============================================================================
set -euo pipefail

# ANSI color formatting
BOLD=$'\033[1m'
DIM=$'\033[2m'
GREEN=$'\033[0;32m'
CYAN=$'\033[0;36m'
YELLOW=$'\033[0;33m'
RED=$'\033[0;31m'
RESET=$'\033[0m'

# Default values
COMPANION_NAME="Aura"
HUMAN_NAME="Friend"
PRIMARY_PROVIDER="openrouter"
OPENROUTER_KEY=""
OPENAI_KEY=""
XAI_KEY=""
DEEPSEEK_KEY=""
MODEL_CHOICE=""
PORT="8770"
REMOTE_PIN=""
INSTALL_DIR=""
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
DRY_RUN=0
NON_INTERACTIVE=0
SERVICE_ONLY=0
NO_SERVICE=0
UPGRADE_MODE=0

usage() {
  cat <<EOF
${BOLD}Tamanitomo — 1-Command Linux Setup${RESET}

Usage:
  bash setup-linux.sh [OPTIONS]

Options:
  --name <name>             Companion display name (default: Aura)
  --human <name>            Your name / what companion calls you (default: Friend)
  --provider <provider>     Primary AI provider: openrouter, openai, xai, deepseek (default: openrouter)
  --openrouter-key <key>    OpenRouter API Key
  --openai-key <key>        OpenAI API Key
  --xai-key <key>           xAI (Grok) API Key
  --deepseek-key <key>      DeepSeek API Key
  --model <model>           Primary model (e.g. openrouter/auto, gpt-4o, grok-2, deepseek-chat)
  --port <port>             Web workspace port (default: 8770)
  --remote-pin <pin>        4-digit PIN for remote network access
  --install-dir <dir>       Custom installation directory (default: ~/projects/tamanitomo)
  --hermes-home <dir>       Hermes Agent state directory (default: ~/.hermes)
  --service-only            Only install / update systemd user service and exit
  --no-service              Skip systemd user service setup
  --upgrade                 Upgrade existing installation dependencies and templates
  --non-interactive         Do not prompt for missing values (use defaults/flags)
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
    --model) MODEL_CHOICE="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --remote-pin) REMOTE_PIN="$2"; shift 2 ;;
    --install-dir) INSTALL_DIR="$2"; shift 2 ;;
    --hermes-home) HERMES_HOME="$2"; shift 2 ;;
    --service-only) SERVICE_ONLY=1; shift ;;
    --no-service) NO_SERVICE=1; shift ;;
    --upgrade) UPGRADE_MODE=1; shift ;;
    --non-interactive) NON_INTERACTIVE=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo -e "${RED}Unknown option: $1${RESET}" >&2; usage; exit 1 ;;
  esac
done

echo -e "${BOLD}${CYAN}"
echo "  ╔═══════════════════════════════════════════════════════════════╗"
echo "  ║             Tamanitomo — Linux Turnkey Setup                  ║"
echo "  ╚═══════════════════════════════════════════════════════════════╝"
echo -e "${RESET}"

CURRENT_DIR="$(pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

# Resolve kit directory
if [[ -n "$INSTALL_DIR" ]]; then
  KIT_DIR="$INSTALL_DIR"
elif [[ -f "$SCRIPT_DIR/launch.py" && -d "$SCRIPT_DIR/kit" ]]; then
  KIT_DIR="$SCRIPT_DIR"
elif [[ -f "$CURRENT_DIR/launch.py" && -d "$CURRENT_DIR/kit" ]]; then
  KIT_DIR="$CURRENT_DIR"
else
  KIT_DIR="$HOME/projects/tamanitomo"
fi

echo -e "${DIM}• Target kit directory: ${KIT_DIR}${RESET}"
echo -e "${DIM}• Hermes home directory: ${HERMES_HOME}${RESET}"

# ------------------------------------------------------------------------------
# Service-only mode fast path
# ------------------------------------------------------------------------------
setup_systemd_service() {
  local target_kit="$1"
  local target_hermes="$2"
  local target_port="$3"
  local sv_user_dir="$HOME/.config/systemd/user"

  echo -e "${CYAN}→ Configuring systemd user service...${RESET}"
  mkdir -p "$sv_user_dir"

  cat > "$sv_user_dir/tamanitomo.service" <<EOF
[Unit]
Description=Tamanitomo web backend
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${target_kit}
ExecStart=${target_kit}/.venv/bin/python -m kit.app.hosted
Environment=HERMES_HOME=${target_hermes}
Environment=TAMANITOMO_BIND=0.0.0.0
Environment=TAMANITOMO_PORT=${target_port}
Environment=COMPANION_BIND=0.0.0.0
Environment=COMPANION_PORT=${target_port}
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
UMask=0077

[Install]
WantedBy=default.target
EOF

  # Legacy symlink for compatibility
  ln -sfn "$sv_user_dir/tamanitomo.service" "$sv_user_dir/companion-workspace.service"

  if command -v systemctl >/dev/null 2>&1; then
    if systemctl --user status >/dev/null 2>&1; then
      systemctl --user daemon-reload || true
      systemctl --user enable tamanitomo.service || true
      systemctl --user restart tamanitomo.service || true
      echo -e "${GREEN}✓ tamanitomo.service enabled and started via systemctl --user${RESET}"
    else
      echo -e "${YELLOW}! systemd user session not active (headless/container); service file created at ~/.config/systemd/user/tamanitomo.service${RESET}"
    fi
  fi

  if command -v loginctl >/dev/null 2>&1; then
    loginctl enable-linger "$USER" 2>/dev/null || true
  fi
}

if [[ "$SERVICE_ONLY" -eq 1 ]]; then
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo -e "${YELLOW}[DRY RUN] Would configure ~/.config/systemd/user/tamanitomo.service for ${KIT_DIR}${RESET}"
    exit 0
  fi
  setup_systemd_service "$KIT_DIR" "$HERMES_HOME" "$PORT"
  echo -e "${GREEN}✓ Service configuration complete.${RESET}"
  exit 0
fi

# ------------------------------------------------------------------------------
# Step 1: Check Prerequisites
# ------------------------------------------------------------------------------
echo -e "${CYAN}→ Checking prerequisites...${RESET}"

MISSING_PKGS=()
for bin in git curl; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    MISSING_PKGS+=("$bin")
  fi
done

PYTHON_BIN=""
for candidate in python3.14 python3.13 python3.12 python3.11 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PY_VER=$("$candidate" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0.0")
    MAJOR=$(echo "$PY_VER" | cut -d. -f1)
    MINOR=$(echo "$PY_VER" | cut -d. -f2)
    if [[ "$MAJOR" -eq 3 && "$MINOR" -ge 11 ]]; then
      PYTHON_BIN="$candidate"
      break
    fi
  fi
done

if [[ -z "$PYTHON_BIN" ]]; then
  echo -e "${YELLOW}! Python 3.11+ was not detected in PATH.${RESET}"
  MISSING_PKGS+=("python3-venv" "python3")
fi

if [[ ${#MISSING_PKGS[@]} -gt 0 ]]; then
  echo -e "${YELLOW}Missing packages: ${MISSING_PKGS[*]}${RESET}"
  if [[ "$NON_INTERACTIVE" -eq 0 && "$EUID" -ne 0 ]]; then
    echo -e "Attempting package installation (sudo may prompt for password)..."
    if command -v apt-get >/dev/null 2>&1; then
      sudo apt-get update -y && sudo apt-get install -y "${MISSING_PKGS[@]}" || true
    elif command -v dnf >/dev/null 2>&1; then
      sudo dnf install -y "${MISSING_PKGS[@]}" || true
    elif command -v pacman >/dev/null 2>&1; then
      sudo pacman -Sy --noconfirm "${MISSING_PKGS[@]}" || true
    fi
  fi
fi

# Re-check python
if [[ -z "$PYTHON_BIN" ]]; then
  for candidate in python3.14 python3.13 python3.12 python3.11 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PY_VER=$("$candidate" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0.0")
      MAJOR=$(echo "$PY_VER" | cut -d. -f1)
      MINOR=$(echo "$PY_VER" | cut -d. -f2)
      if [[ "$MAJOR" -eq 3 && "$MINOR" -ge 11 ]]; then
        PYTHON_BIN="$candidate"
        break
      fi
    fi
  done
fi

if [[ -z "$PYTHON_BIN" ]]; then
  echo -e "${RED}Error: Python 3.11 or newer is required to run Tamanitomo.${RESET}"
  echo -e "Please install Python 3.11+ using your package manager or uv (https://docs.astral.sh/uv/)."
  exit 1
fi

echo -e "${GREEN}✓ Prerequisites satisfied (Python: $("$PYTHON_BIN" --version))${RESET}"

# ------------------------------------------------------------------------------
# Step 2: Interactive Prompts (if not non-interactive)
# ------------------------------------------------------------------------------
if [[ "$NON_INTERACTIVE" -eq 0 && "$UPGRADE_MODE" -eq 0 ]]; then
  echo ""
  echo -e "${BOLD}1. Companion Persona Details${RESET}"
  read -r -p "   Companion display name [${COMPANION_NAME}]: " input_name
  COMPANION_NAME="${input_name:-$COMPANION_NAME}"

  read -r -p "   What should your companion call you? [${HUMAN_NAME}]: " input_human
  HUMAN_NAME="${input_human:-$HUMAN_NAME}"

  echo ""
  echo -e "${BOLD}2. Cloud AI Provider${RESET}"
  echo -e "${DIM}   Select provider to power your companion's thoughts and dialogue.${RESET}"
  echo "   [1] OpenRouter (Recommended: access to Claude, Gemini, Llama 3, DeepSeek)"
  echo "   [2] OpenAI (GPT-4o, GPT-4o-mini)"
  echo "   [3] xAI (Grok-2)"
  echo "   [4] DeepSeek (DeepSeek V3 / R1)"
  read -r -p "   Select choice [1-4, default: 1]: " provider_choice
  provider_choice="${provider_choice:-1}"

  case "$provider_choice" in
    1)
      PRIMARY_PROVIDER="openrouter"
      MODEL_CHOICE="${MODEL_CHOICE:-openrouter/auto}"
      if [[ -z "$OPENROUTER_KEY" ]]; then
        read -r -s -p "   Enter OpenRouter API Key (sk-or-...): " OPENROUTER_KEY
        echo ""
      fi
      ;;
    2)
      PRIMARY_PROVIDER="openai"
      MODEL_CHOICE="${MODEL_CHOICE:-gpt-4o}"
      if [[ -z "$OPENAI_KEY" ]]; then
        read -r -s -p "   Enter OpenAI API Key (sk-...): " OPENAI_KEY
        echo ""
      fi
      ;;
    3)
      PRIMARY_PROVIDER="xai"
      MODEL_CHOICE="${MODEL_CHOICE:-xai/grok-2-latest}"
      if [[ -z "$XAI_KEY" ]]; then
        read -r -s -p "   Enter xAI API Key (xai-...): " XAI_KEY
        echo ""
      fi
      ;;
    4)
      PRIMARY_PROVIDER="deepseek"
      MODEL_CHOICE="${MODEL_CHOICE:-deepseek/deepseek-chat}"
      if [[ -z "$DEEPSEEK_KEY" ]]; then
        read -r -s -p "   Enter DeepSeek API Key: " DEEPSEEK_KEY
        echo ""
      fi
      ;;
  esac

  echo ""
  echo -e "${BOLD}3. Workspace Web Security${RESET}"
  read -r -p "   Create a 4-digit PIN for remote/LAN access (leave empty for none): " REMOTE_PIN
fi

# Set default model choice if unset
if [[ -z "$MODEL_CHOICE" ]]; then
  case "$PRIMARY_PROVIDER" in
    openrouter) MODEL_CHOICE="openrouter/auto" ;;
    openai)     MODEL_CHOICE="gpt-4o" ;;
    xai)        MODEL_CHOICE="xai/grok-2-latest" ;;
    deepseek)   MODEL_CHOICE="deepseek/deepseek-chat" ;;
    *)          MODEL_CHOICE="openrouter/auto" ;;
  esac
fi

# ------------------------------------------------------------------------------
# Step 3: Clone or Verify Repository
# ------------------------------------------------------------------------------
if [[ "$DRY_RUN" -eq 1 ]]; then
  echo -e "${YELLOW}[DRY RUN] Would set up repository in ${KIT_DIR}${RESET}"
else
  if [[ ! -d "$KIT_DIR" ]]; then
    echo -e "${CYAN}→ Cloning repository to ${KIT_DIR}...${RESET}"
    mkdir -p "$(dirname "$KIT_DIR")"
    git clone https://github.com/tamanitomo/tamanitomo.git "$KIT_DIR"
  elif [[ ! -f "$KIT_DIR/launch.py" ]]; then
    echo -e "${RED}Error: ${KIT_DIR} exists but is not a Tamanitomo repository.${RESET}"
    exit 1
  fi
fi

# ------------------------------------------------------------------------------
# Step 4: Bootstrap Environment (launch.py)
# ------------------------------------------------------------------------------
echo -e "${CYAN}→ Bootstrapping Python virtual environment...${RESET}"
if [[ "$DRY_RUN" -eq 1 ]]; then
  echo -e "${YELLOW}[DRY RUN] Would run launch.py in ${KIT_DIR}${RESET}"
else
  (cd "$KIT_DIR" && "$PYTHON_BIN" launch.py --dry-run >/dev/null 2>&1 || true)
  if [[ ! -d "$KIT_DIR/.venv" ]]; then
    echo -e "Creating virtual environment via $PYTHON_BIN -m venv .venv..."
    "$PYTHON_BIN" -m venv "$KIT_DIR/.venv"
  fi
  echo -e "Installing / verifying requirements..."
  "$KIT_DIR/.venv/bin/python" -m pip install --quiet --upgrade pip setuptools wheel
  "$KIT_DIR/.venv/bin/python" -m pip install --quiet -r "$KIT_DIR/requirements.txt"
fi

# ------------------------------------------------------------------------------
# Step 5: Detect or Configure Hermes Agent
# ------------------------------------------------------------------------------
echo -e "${CYAN}→ Checking Hermes Agent...${RESET}"
mkdir -p "$HERMES_HOME"

HERMES_BIN=""
if command -v hermes >/dev/null 2>&1; then
  HERMES_BIN="$(command -v hermes)"
elif [[ -f "$HERMES_HOME/hermes-agent/venv/bin/hermes" ]]; then
  HERMES_BIN="$HERMES_HOME/hermes-agent/venv/bin/hermes"
elif [[ -f "$HOME/.local/bin/hermes" ]]; then
  HERMES_BIN="$HOME/.local/bin/hermes"
fi

if [[ -n "$HERMES_BIN" ]]; then
  echo -e "${GREEN}✓ Found Hermes Agent: ${HERMES_BIN}${RESET}"
else
  echo -e "${YELLOW}! Hermes Agent CLI not found in PATH.${RESET}"
  echo -e "  Tamanitomo can run standalone or alongside Hermes."
  echo -e "  To install Hermes Agent later: curl -fsSL https://raw.githubusercontent.com/nousresearch/hermes-agent/main/install.sh | bash"
fi

# Configure provider keys in Hermes .env if keys were provided
HERMES_ENV="$HERMES_HOME/.env"
touch "$HERMES_ENV"
chmod 600 "$HERMES_ENV" 2>/dev/null || true

update_env_key() {
  local key="$1"
  local val="$2"
  if [[ -n "$val" ]]; then
    if grep -q "^${key}=" "$HERMES_ENV" 2>/dev/null; then
      sed -i "s|^${key}=.*|${key}=${val}|" "$HERMES_ENV"
    else
      echo "${key}=${val}" >> "$HERMES_ENV"
    fi
  fi
}

if [[ "$DRY_RUN" -eq 0 ]]; then
  update_env_key "OPENROUTER_API_KEY" "$OPENROUTER_KEY"
  update_env_key "OPENAI_API_KEY" "$OPENAI_KEY"
  update_env_key "XAI_API_KEY" "$XAI_KEY"
  update_env_key "DEEPSEEK_API_KEY" "$DEEPSEEK_KEY"
fi

# ------------------------------------------------------------------------------
# Step 6: Initialize / Configure Companion Profile
# ------------------------------------------------------------------------------
COMPANION_JSON="$HERMES_HOME/companion.json"
ANSWERS_JSON="$HOME/.companion-init-answers.json"

if [[ "$DRY_RUN" -eq 0 ]]; then
  cat > "$ANSWERS_JSON" <<EOF
{
  "agent_type": "companion",
  "name": "${COMPANION_NAME}",
  "human_name": "${HUMAN_NAME}",
  "relationship_framing": "companion",
  "contact_cadence": "balanced",
  "quiet_hours": "23:00-08:00"
}
EOF

  echo -e "${CYAN}→ Initializing companion profile for ${COMPANION_NAME}...${RESET}"
  "$KIT_DIR/.venv/bin/python" "$KIT_DIR/bin/tamanitomo" --home "$HERMES_HOME" upgrade --answers "$ANSWERS_JSON" >/dev/null 2>&1 || \
  "$KIT_DIR/.venv/bin/python" "$KIT_DIR/bin/tamanitomo" --home "$HERMES_HOME" init --answers "$ANSWERS_JSON" >/dev/null 2>&1 || true

  # Ensure companion.json models block is set
  "$KIT_DIR/.venv/bin/python" -c "
import json, os
path = '$COMPANION_JSON'
d = {}
if os.path.exists(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            d = json.load(f)
    except Exception:
        pass
d.setdefault('models', {})
d['models']['chat'] = {'provider': '$PRIMARY_PROVIDER', 'model': '$MODEL_CHOICE', 'reasoning_effort': 'medium'}
d['models']['loops'] = {'provider': '$PRIMARY_PROVIDER', 'model': '$MODEL_CHOICE', 'reasoning_effort': 'medium'}
d['models']['reflection'] = {'provider': '$PRIMARY_PROVIDER', 'model': '$MODEL_CHOICE', 'reasoning_effort': 'medium'}
if '$REMOTE_PIN':
    d['remote_pin'] = '$REMOTE_PIN'
with open(path, 'w', encoding='utf-8') as f:
    json.dump(d, f, indent=2)
" || true
fi

# ------------------------------------------------------------------------------
# Step 7: Configure Systemd User Service
# ------------------------------------------------------------------------------
if [[ "$NO_SERVICE" -eq 0 ]]; then
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo -e "${YELLOW}[DRY RUN] Would configure ~/.config/systemd/user/tamanitomo.service${RESET}"
  else
    setup_systemd_service "$KIT_DIR" "$HERMES_HOME" "$PORT"
  fi
fi

# Get Local IP Address
LOCAL_IP="127.0.0.1"
if command -v ip >/dev/null 2>&1; then
  LOCAL_IP=$(ip -4 addr show scope global | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -n 1 || echo "127.0.0.1")
fi

# ------------------------------------------------------------------------------
# Final Summary & Success Banner
# ------------------------------------------------------------------------------
echo ""
echo -e "${BOLD}${GREEN}================================================================${RESET}"
echo -e "${BOLD}${GREEN}  ✓ Tamanitomo Linux Setup Complete! ${RESET}"
echo -e "${BOLD}${GREEN}================================================================${RESET}"
echo ""
echo -e "  ${BOLD}Companion Name:${RESET}    ${COMPANION_NAME}"
echo -e "  ${BOLD}Primary Model:${RESET}     ${MODEL_CHOICE} (${PRIMARY_PROVIDER})"
echo -e "  ${BOLD}Local Workspace:${RESET}   ${CYAN}http://localhost:${PORT}${RESET}"
if [[ "$LOCAL_IP" != "127.0.0.1" ]]; then
  echo -e "  ${BOLD}LAN / Wi-Fi URL:${RESET}   ${CYAN}http://${LOCAL_IP}:${PORT}${RESET}"
fi
if [[ -n "$REMOTE_PIN" ]]; then
  echo -e "  ${BOLD}Remote Access PIN:${RESET} ${GREEN}Active (${REMOTE_PIN})${RESET}"
fi
echo ""
if [[ "$NO_SERVICE" -eq 0 ]]; then
  echo -e "${BOLD}Service Management Commands:${RESET}"
  echo -e "  • Check status:  ${DIM}systemctl --user status tamanitomo${RESET}"
  echo -e "  • View logs:     ${DIM}journalctl --user -u tamanitomo -f${RESET}"
  echo -e "  • Restart:       ${DIM}systemctl --user restart tamanitomo${RESET}"
  echo -e "  • Stop:          ${DIM}systemctl --user stop tamanitomo${RESET}"
fi
echo -e "  • CLI Menu:      ${DIM}${KIT_DIR}/bin/tamanitomo${RESET}"
echo -e "  • Run Doctor:    ${DIM}${KIT_DIR}/bin/tamanitomo doctor${RESET}"
echo ""
echo -e "${BOLD}Enjoy chatting with ${COMPANION_NAME}!${RESET}"
