#!/usr/bin/env bash
# lobot-tui launcher
# Usage: lobot-tui [--dev]
#   --dev  Run with mock data (no kubectl required); useful for local testing

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${1:-}" == "--dev" ]]; then
    export LOBOT_TUI_DEV=1
fi

# Run as a module so relative imports work
cd "$SCRIPT_DIR"
exec python3 -m lobot_tui
