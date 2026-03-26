#!/usr/bin/env bash
# Run the lobot-tui unit test suite from anywhere.
# Usage: run-tests.sh [pytest args...]

SCRIPT_DIR="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
VENV_PYTHON="$SCRIPT_DIR/lobot_tui/.venv/bin/python3"

cd "$REPO_DIR"
exec "$VENV_PYTHON" -m pytest "$@"
