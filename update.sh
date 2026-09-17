#!/usr/bin/env bash
# ==============================================================================
# Tamanitomo (魂の友) — Safe Turnkey Updater
# Updates Tamanitomo from GitHub, synchronizes Python dependencies,
# optionally updates Hermes agent, and safely restarts the background service.
# ==============================================================================
set -euo pipefail

BOLD="\033[1m"
GREEN="\033[32m"
YELLOW="\033[33m"
CYAN="\033[36m"
RED="\033[31m"
DIM="\033[2m"
RESET="\033[0m"

UPDATE_HERMES=0
RESTART_SERVICE=1
BRANCH="main"

usage() {
  echo -e "${BOLD}Tamanitomo — Turnkey Updater${RESET}"
  echo ""
  echo "Usage:"
  echo "  ./update.sh [OPTIONS]"
  echo ""
  echo "Options:"
  echo "  --hermes          Also update the upstream Hermes agent runtime (~/.hermes/hermes-agent)"
  echo "  --branch <name>   Git branch to pull from (default: main)"
  echo "  --no-restart      Do not restart background services after updating"
  echo "  -h, --help        Show this help message"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --hermes) UPDATE_HERMES=1; shift ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --no-restart) RESTART_SERVICE=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo -e "${RED}Unknown option: $1${RESET}" >&2; usage; exit 1 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${BOLD}${CYAN}"
echo "  ╔═══════════════════════════════════════════════════════════════╗"
echo "  ║           Tamanitomo (魂の友) — Safe Turnkey Updater           ║"
echo "  ╚═══════════════════════════════════════════════════════════════╝"
echo -e "${RESET}"

# 1. Check Git Status
echo -e "${CYAN}→ Checking local repository status...${RESET}"
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo -e "${RED}Error: Not inside a git repository.${RESET}" >&2
  exit 1
fi

STASHED=0
if ! git diff-index --quiet HEAD -- 2>/dev/null; then
  echo -e "${YELLOW}! Local modifications detected. Stashing changes before update...${RESET}"
  git stash push -m "Auto-stash before Tamanitomo update $(date +%s)"
  STASHED=1
fi

# 2. Fetch and Pull
echo -e "${CYAN}→ Fetching updates from origin/${BRANCH}...${RESET}"
git fetch origin "$BRANCH"

CURRENT_COMMIT="$(git rev-parse --short HEAD)"
TARGET_COMMIT="$(git rev-parse --short "origin/${BRANCH}")"

if [[ "$CURRENT_COMMIT" == "$TARGET_COMMIT" ]]; then
  echo -e "${GREEN}✓ Tamanitomo is already up to date on commit ${CURRENT_COMMIT}.${RESET}"
else
  echo -e "  Updating from ${DIM}${CURRENT_COMMIT}${RESET} to ${GREEN}${TARGET_COMMIT}${RESET}..."
  git checkout "$BRANCH"
  git merge --ff-only "origin/${BRANCH}" || {
    echo -e "${RED}! Fast-forward merge failed. Resetting safely to origin/${BRANCH}...${RESET}"
    git reset --hard "origin/${BRANCH}"
  }
  echo -e "${GREEN}✓ Tamanitomo code successfully updated.${RESET}"
fi

# Re-apply stash if any
if [[ "$STASHED" -eq 1 ]]; then
  echo -e "${CYAN}→ Restoring your local modifications...${RESET}"
  git stash pop || echo -e "${YELLOW}! Note: Check 'git status' to inspect any stash merge adjustments.${RESET}"
fi

# 3. Synchronize Dependencies
echo -e "${CYAN}→ Verifying Python virtual environment & dependencies...${RESET}"
VENV_DIR="$SCRIPT_DIR/.venv"
if [[ -f "$SCRIPT_DIR/requirements.txt" && -d "$VENV_DIR" ]]; then
  if command -v uv >/dev/null 2>&1; then
    uv pip install -q -r "$SCRIPT_DIR/requirements.txt" --python "$VENV_DIR/bin/python" || true
  elif [[ -x "$VENV_DIR/bin/pip" ]]; then
    "$VENV_DIR/bin/pip" install -q --upgrade -r "$SCRIPT_DIR/requirements.txt" || true
  fi
  echo -e "${GREEN}✓ Dependencies synchronized.${RESET}"
fi

# 4. Optional: Update Hermes
if [[ "$UPDATE_HERMES" -eq 1 ]]; then
  HERMES_DIR="${HERMES_HOME:-$HOME/.hermes}/hermes-agent"
  if [[ -d "$HERMES_DIR/.git" ]]; then
    echo -e "${CYAN}→ Updating Hermes agent repository in ${HERMES_DIR}...${RESET}"
    (
      cd "$HERMES_DIR"
      git fetch origin main 2>/dev/null || true
      git merge --ff-only origin/main 2>/dev/null || true
      if [[ -d "$HERMES_DIR/venv" && -x "$HERMES_DIR/venv/bin/pip" ]]; then
        "$HERMES_DIR/venv/bin/pip" install -q -e . 2>/dev/null || true
      fi
    )
    echo -e "${GREEN}✓ Hermes agent updated.${RESET}"
  else
    echo -e "${DIM}Hermes agent directory ($HERMES_DIR) is not a git repo; skipping.${RESET}"
  fi
fi

# 5. Restart Services
if [[ "$RESTART_SERVICE" -eq 1 ]]; then
  echo -e "${CYAN}→ Checking background services...${RESET}"
  RESTARTED=0

  # Systemd User Unit
  if command -v systemctl >/dev/null 2>&1; then
    if systemctl --user is-active companion-workspace >/dev/null 2>&1; then
      echo -e "  Restarting systemd service: ${BOLD}companion-workspace${RESET}..."
      systemctl --user restart companion-workspace
      RESTARTED=1
    fi
  fi

  # Termux Services
  if command -v sv >/dev/null 2>&1; then
    for svc in tamanitomo-workspace companion-workspace; do
      if sv status "$svc" >/dev/null 2>&1; then
        echo -e "  Restarting Termux service: ${BOLD}${svc}${RESET}..."
        sv restart "$svc" 2>/dev/null || true
        RESTARTED=1
      fi
    done
    for svc in tamanitomo-gateway companion-gateway; do
      if sv status "$svc" >/dev/null 2>&1; then
        echo -e "  Restarting Termux service: ${BOLD}${svc}${RESET}..."
        sv restart "$svc" 2>/dev/null || true
        RESTARTED=1
      fi
    done
  fi

  if [[ "$RESTARTED" -eq 1 ]]; then
    echo -e "${GREEN}✓ Services restarted with new code.${RESET}"
  else
    echo -e "${DIM}No running background services found to restart.${RESET}"
  fi
fi

VERSION="2.1.0"
[[ -f "$SCRIPT_DIR/VERSION" ]] && VERSION="$(cat "$SCRIPT_DIR/VERSION" | tr -d '[:space:]')"

echo ""
echo -e "${BOLD}${GREEN}================================================================${RESET}"
echo -e "${BOLD}${GREEN}  ✓ Tamanitomo is updated! (v${VERSION} · ${TARGET_COMMIT})${RESET}"
echo -e "${BOLD}${GREEN}================================================================${RESET}"
echo ""
