#!/usr/bin/env bash
# lobot-tui launcher
# Usage: lobot-tui [--dev]
#   --dev  Run with mock data (no kubectl required); useful for local testing

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"

if [[ "${1:-}" == "--dev" ]]; then
    export LOBOT_TUI_DEV=1
fi

# Use venv if present (required on Ubuntu 24.04 / PEP 668 systems)
# Create it with: python3 -m venv lobot_tui/.venv && lobot_tui/.venv/bin/pip install textual aiofiles
PYTHON="$SCRIPT_DIR/lobot_tui/.venv/bin/python3"
if [[ ! -x "$PYTHON" ]]; then
    PYTHON="python3"
fi

# Run as a module so relative imports work
cd "$SCRIPT_DIR"
exec "$PYTHON" -m lobot_tui
