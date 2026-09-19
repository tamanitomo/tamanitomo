#!/usr/bin/env bash
# ==============================================================================
# Tamanitomo — Android Termux Clean Uninstaller & Reset to State 0
#
# Safely terminates all Tamanitomo and Hermes background services, removes
# daemon configurations, Termux:Boot autostart scripts, application checkouts,
# virtual environments, credentials, vaults, databases, and caches.
# Returns the Android Termux environment to State 0 so the turnkey installer
# (setup-termux.sh) can be run completely fresh.
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

AUTO_CONFIRM=0
KEEP_VAULT=0
PURGE_PACKAGES=0
FORCE_NON_TERMUX=0

usage() {
  cat <<EOF
${BOLD}Tamanitomo — Android Termux Uninstaller (Reset to State 0)${RESET}

Usage:
  bash uninstall-termux.sh [OPTIONS]

Options:
  -y, --yes             Non-interactive mode (automatically confirm uninstallation)
  --keep-vault          Preserve the ~/vault directory (keeps companion memories & journal)
  --purge-packages      Also remove Termux build packages (python3.11, clang, rust, nodejs, etc.)
  --force               Force execution even if not running inside Android Termux
  -h, --help            Show this help message

Examples:
  # Reset all Tamanitomo & Hermes assets back to State 0:
  bash uninstall-termux.sh

  # Completely unattended wipe back to State 0:
  bash uninstall-termux.sh -y

  # Full wipe including Termux compiler toolchain:
  bash uninstall-termux.sh -y --purge-packages
EOF
}

# Parse flags
while [[ $# -gt 0 ]]; do
  case "$1" in
    -y|--yes) AUTO_CONFIRM=1; shift ;;
    --keep-vault) KEEP_VAULT=1; shift ;;
    --purge-packages|--all) PURGE_PACKAGES=1; shift ;;
    --force) FORCE_NON_TERMUX=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo -e "${RED}Unknown option: $1${RESET}" >&2; usage; exit 1 ;;
  esac
done

echo -e "${BOLD}${CYAN}"
echo "  ╔═══════════════════════════════════════════════════════════════╗"
echo "  ║        Tamanitomo — Termux Reset & Uninstaller (State 0)      ║"
echo "  ╚═══════════════════════════════════════════════════════════════╝"
echo -e "${RESET}"

# Environment detection
IS_TERMUX=0
if [[ -n "${PREFIX:-}" && "$PREFIX" == *"com.termux"* ]] || [[ -d "/data/data/com.termux" ]]; then
  IS_TERMUX=1
fi

if [[ "$IS_TERMUX" -eq 0 && "$FORCE_NON_TERMUX" -eq 0 ]]; then
  echo -e "${RED}Error: This uninstaller is designed for Android Termux.${RESET}"
  echo -e "If you are testing this in a simulated environment, pass ${BOLD}--force${RESET}."
  exit 1
fi

# Define path targets
if [[ "$IS_TERMUX" -eq 1 ]]; then
  HOME_DIR="${HOME:-/data/data/com.termux/files/home}"
  PREFIX_DIR="${PREFIX:-/data/data/com.termux/files/usr}"
else
  HOME_DIR="${HOME}"
  PREFIX_DIR="${PREFIX:-/tmp/tamanitomo-termux-test/usr}"
fi

# Safety check: prevent catastrophic rm of root or empty paths
if [[ -z "$HOME_DIR" || "$HOME_DIR" == "/" || "$HOME_DIR" == "/root" ]]; then
  echo -e "${RED}Aborting: HOME directory resolves to unsafe location: '${HOME_DIR}'${RESET}" >&2
  exit 1
fi

echo -e "${BOLD}This script will reset your Android device to State 0 by removing:${RESET}"
echo -e "  • Background daemons (tamanitomo-gateway, tamanitomo-workspace)"
echo -e "  • Termux:Boot autostart scripts"
echo -e "  • Hermes Agent runtime and virtual environments (${HERMES_HOME:-$HOME_DIR/.hermes})"
echo -e "  • Tamanitomo repositories ($HOME_DIR/tamanitomo, $HOME_DIR/companion-kit)"
echo -e "  • Credentials & secrets ($HOME_DIR/.hermes/.env, API keys, tokens)"
echo -e "  • Application state & caches ($HOME_DIR/.local/share/tamanitomo, $HOME_DIR/.cache)"
if [[ "$KEEP_VAULT" -eq 0 ]]; then
  echo -e "  • Companion vault & memories (${RED}${BOLD}$HOME_DIR/vault${RESET})"
else
  echo -e "  • Companion vault & memories (${GREEN}${BOLD}PRESERVED at $HOME_DIR/vault${RESET})"
fi
if [[ "$PURGE_PACKAGES" -eq 1 ]]; then
  echo -e "  • Build packages & toolchain (${YELLOW}python3.11, clang, rust, nodejs, etc.${RESET})"
fi
echo ""

# Interactive confirmation
if [[ "$AUTO_CONFIRM" -eq 0 ]]; then
  read -r -p "Are you sure you want to reset everything back to State 0? [y/N]: " confirm
  if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Uninstallation cancelled. No changes made.${RESET}"
    exit 0
  fi
  echo ""

  if [[ "$PURGE_PACKAGES" -eq 0 && "$IS_TERMUX" -eq 1 ]]; then
    read -r -p "Do you also want to remove installed build tools (python3.11, rust, clang)? [y/N]: " purge_input
    if [[ "$purge_input" =~ ^[Yy]$ ]]; then
      PURGE_PACKAGES=1
    fi
    echo ""
  fi
fi

# ------------------------------------------------------------------------------
# 1. Stop Services and Terminate Processes
# ------------------------------------------------------------------------------
echo -e "${CYAN}→ [1/7] Stopping background services and companion processes...${RESET}"

# Release Termux wake-lock
if command -v termux-wake-unlock >/dev/null 2>&1; then
  termux-wake-unlock >/dev/null 2>&1 || true
fi

# Stop runit services if termux-services is installed
SV_DIR="${PREFIX_DIR}/var/service"
SERVICES=(
  "tamanitomo-gateway"
  "tamanitomo-workspace"
  "companion-gateway"
  "companion-workspace"
)

if command -v sv >/dev/null 2>&1; then
  export SVDIR="$SV_DIR"
  for s in "${SERVICES[@]}"; do
    sv down "$s" >/dev/null 2>&1 || true
    if command -v sv-disable >/dev/null 2>&1; then
      sv-disable "$s" >/dev/null 2>&1 || true
    fi
  done
fi

if command -v service-daemon >/dev/null 2>&1; then
  service-daemon stop >/dev/null 2>&1 || true
fi

# Terminate any remaining companion processes (carefully excluding this script)
PATTERNS=(
  "kit.app.hosted"
  "hermes gateway"
  "bin/tamanitomo"
  "bin/companion"
  "runsv.*tamanitomo"
  "runsv.*companion"
)

CURRENT_PID="$$"
PARENT_PID="$PPID"

for pat in "${PATTERNS[@]}"; do
  matched_pids=$(pgrep -f "$pat" 2>/dev/null || true)
  for p in $matched_pids; do
    if [[ "$p" != "$CURRENT_PID" && "$p" != "$PARENT_PID" ]]; then
      kill -9 "$p" 2>/dev/null || true
    fi
  done
done
echo -e "  ${GREEN}✓ All services and processes terminated.${RESET}"

# ------------------------------------------------------------------------------
# 2. Remove Service Descriptors & Runit State
# ------------------------------------------------------------------------------
echo -e "${CYAN}→ [2/7] Removing service definitions and log directories...${RESET}"
for s in "${SERVICES[@]}"; do
  rm -rf "${SV_DIR:?}/$s" 2>/dev/null || true
done

# Clear supervise runtime descriptors and logs
rm -rf "${PREFIX_DIR}/var/run/runit" 2>/dev/null || true
rm -rf "${PREFIX_DIR}/var/log/tamanitomo-"* 2>/dev/null || true
rm -rf "${PREFIX_DIR}/var/log/companion-"* 2>/dev/null || true
rm -rf "${PREFIX_DIR}/var/log/sv" 2>/dev/null || true
echo -e "  ${GREEN}✓ Service descriptors purged.${RESET}"

# ------------------------------------------------------------------------------
# 3. Clean Termux:Boot Autostart Scripts
# ------------------------------------------------------------------------------
echo -e "${CYAN}→ [3/7] Cleaning Termux:Boot autostart scripts...${RESET}"
BOOT_DIR="${HOME_DIR}/.termux/boot"
rm -f "${BOOT_DIR}/start-tamanitomo-services" 2>/dev/null || true
rm -f "${BOOT_DIR}/start-companion-services" 2>/dev/null || true

# Remove boot directory if now empty
if [[ -d "$BOOT_DIR" ]] && [[ -z "$(ls -A "$BOOT_DIR" 2>/dev/null)" ]]; then
  rmdir "$BOOT_DIR" 2>/dev/null || true
fi
echo -e "  ${GREEN}✓ Boot autostart scripts removed.${RESET}"

# ------------------------------------------------------------------------------
# 4. Remove Shell Environment Hooks
# ------------------------------------------------------------------------------
echo -e "${CYAN}→ [4/7] Cleaning shell RC files (.bashrc, .profile)...${RESET}"
for rc in "${HOME_DIR}/.bashrc" "${HOME_DIR}/.profile"; do
  if [[ -f "$rc" ]]; then
    sed -i '/export SVDIR=/d' "$rc" 2>/dev/null || true
    sed -i '/tamanitomo/d' "$rc" 2>/dev/null || true
  fi
done
echo -e "  ${GREEN}✓ Shell RC configurations restored.${RESET}"

# ------------------------------------------------------------------------------
# 5. Remove Command Symlinks
# ------------------------------------------------------------------------------
echo -e "${CYAN}→ [5/7] Removing command symlinks in ${PREFIX_DIR}/bin...${RESET}"
rm -f "${PREFIX_DIR}/bin/hermes" 2>/dev/null || true
rm -f "${PREFIX_DIR}/bin/tamanitomo" 2>/dev/null || true
rm -f "${PREFIX_DIR}/bin/companion" 2>/dev/null || true
echo -e "  ${GREEN}✓ Command links removed.${RESET}"

# ------------------------------------------------------------------------------
# 6. Wipe Application Directories, Configs, & Caches
# ------------------------------------------------------------------------------
echo -e "${CYAN}→ [6/7] Wiping application code, vaults, and state...${RESET}"

TARGET_DIRS=(
  "${HOME_DIR}/tamanitomo"
  "${HOME_DIR}/companion-kit"
  "${HOME_DIR}/.hermes"
  "${HOME_DIR}/.companion"
  "${HOME_DIR}/.tamanitomo"
  "${HOME_DIR}/.local/share/tamanitomo"
  "${HOME_DIR}/.local/share/companion-kit"
  "${HOME_DIR}/wheels"
)

if [[ "$KEEP_VAULT" -eq 0 ]]; then
  TARGET_DIRS+=("${HOME_DIR}/vault")
fi

for dir in "${TARGET_DIRS[@]}"; do
  if [[ -d "$dir" || -L "$dir" ]]; then
    rm -rf "$dir"
    echo -e "  ${DIM}Removed: ${dir}${RESET}"
  fi
done

# Remove config & temporary files
TARGET_FILES=(
  "${HOME_DIR}/.companion-init-answers.json"
  "${HOME_DIR}/.token.lock"
  "${HOME_DIR}/.runtime.lock"
  "${HOME_DIR}/.bootstrap.lock"
  "${HOME_DIR}/companion-wheels-aarch64.tar.gz"
  "${HOME_DIR}/tamanitomo-wheels-aarch64.tar.gz"
)

for file in "${TARGET_FILES[@]}"; do
  rm -f "$file" 2>/dev/null || true
done

# Clean caches
rm -rf "${HOME_DIR}/.cache" 2>/dev/null || true
rm -rf "${HOME_DIR}/.cargo" 2>/dev/null || true
rm -rf /tmp/tamanitomo-termux-test 2>/dev/null || true

echo -e "  ${GREEN}✓ All application assets and caches deleted.${RESET}"

# ------------------------------------------------------------------------------
# 7. (Optional) Purge Installed Packages
# ------------------------------------------------------------------------------
if [[ "$PURGE_PACKAGES" -eq 1 && "$IS_TERMUX" -eq 1 ]]; then
  echo -e "${CYAN}→ [7/7] Returning Termux packages to the pre-install baseline...${RESET}"
  BASELINE_FILE="${HOME_DIR}/.tamanitomo-termux-baseline-packages"
  PACKAGES_TO_PURGE=()
  if [[ -s "$BASELINE_FILE" ]]; then
    CURRENT_FILE="${PREFIX_DIR}/tmp/tamanitomo-current-packages.$$"
    dpkg-query -W -f='${db:Status-Abbrev} ${binary:Package}\n' 2>/dev/null | awk '$1 == "ii" { sub(/:.*/, "", $2); print $2 }' | sort -u > "$CURRENT_FILE"
    while IFS= read -r package; do
      [[ -n "$package" ]] && PACKAGES_TO_PURGE+=("$package")
    done < <(comm -13 "$BASELINE_FILE" "$CURRENT_FILE")
    rm -f "$CURRENT_FILE"
  else
    # Compatibility fallback for installations made before baseline manifests.
    # Do not list bootstrap packages such as curl, openssl, or termux-tools.
    PACKAGES_TO_PURGE=(python3.11 rust clang make pkg-config nodejs ripgrep git tmux termux-services termux-api jq libheif libjpeg-turbo libpng tur-repo)
  fi
  export DEBIAN_FRONTEND=noninteractive
  if [[ "${#PACKAGES_TO_PURGE[@]}" -gt 0 ]]; then
    pkg uninstall -y "${PACKAGES_TO_PURGE[@]}" >/dev/null 2>&1 || true
  fi
  apt autoremove -y --purge >/dev/null 2>&1 || true
  apt clean >/dev/null 2>&1 || true
  rm -f "$BASELINE_FILE"
  echo -e "  ${GREEN}✓ Installer-added packages purged; pre-existing packages preserved.${RESET}"
else
  echo -e "${CYAN}→ [7/7] Preserving package toolchain (Python, Git, etc. remain ready for fast reinstall).${RESET}"
fi

echo ""
echo -e "${BOLD}${GREEN}================================================================${RESET}"
echo -e "${BOLD}${GREEN}  ✓ Android Termux Reset to State 0 Complete!${RESET}"
echo -e "${BOLD}${GREEN}================================================================${RESET}"
echo ""
echo -e "Your Android Termux environment is now completely clean."
echo -e "To run the turnkey setup from scratch anytime, simply run:"
echo ""
echo -e "  ${BOLD}${CYAN}curl -fsSL https://raw.githubusercontent.com/tamanitomo/tamanitomo/main/setup-termux.sh | bash${RESET}"
echo ""
