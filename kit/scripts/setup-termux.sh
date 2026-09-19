#!/usr/bin/env bash
# Compatibility entrypoint; the root script is the single maintained installer.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
exec bash "$ROOT/setup-termux.sh" "$@"
