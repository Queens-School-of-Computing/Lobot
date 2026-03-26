#!/usr/bin/env bash
# Run the lobot-tui unit test suite from anywhere.
# Usage: run-tests.sh [--log] [pytest args...]
#
# --log   Save output to tools/tests/last-run.log in addition to the terminal.
#         Without this flag output goes directly to the terminal with full formatting.

SCRIPT_DIR="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
VENV_PYTHON="$SCRIPT_DIR/lobot_tui/.venv/bin/python3"
LOG_FILE="$SCRIPT_DIR/tests/run-$(date '+%Y%m%d-%H%M%S').log"

SAVE_LOG=false
PYTEST_ARGS=()
for arg in "$@"; do
  case $arg in
    --log) SAVE_LOG=true ;;
    *) PYTEST_ARGS+=("$arg") ;;
  esac
done

cd "$REPO_DIR"
if [ "$SAVE_LOG" = true ]; then
  "$VENV_PYTHON" -m pytest "${PYTEST_ARGS[@]}" 2>&1 | tee "$LOG_FILE"
  exit "${PIPESTATUS[0]}"
else
  exec "$VENV_PYTHON" -m pytest "${PYTEST_ARGS[@]}"
fi
