#!/usr/bin/env bash
# Spectroo v3 — boot detection wrapper.
# Called by the systemd service as ExecStart.
# Activates the venv and delegates to main.py.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")/spectroo_v3"
VENV="$PROJECT_DIR/.venv"
MAIN="$PROJECT_DIR/main.py"

if [[ ! -f "$VENV/bin/activate" ]]; then
    echo "ERROR: venv not found at $VENV" >&2
    exit 1
fi

source "$VENV/bin/activate"
exec python "$MAIN" "$@"
