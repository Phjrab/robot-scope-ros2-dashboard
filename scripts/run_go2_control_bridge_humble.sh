#!/usr/bin/env bash
set -eo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="${ROBOT_SCOPE_DIR:-$(dirname -- "$SCRIPT_DIR")}"

if [[ "${ROBOT_SCOPE_CONTROL_ENABLED:-0}" != "1" ]]; then
  echo "[Robot Scope] control bridge is disabled; set ROBOT_SCOPE_CONTROL_ENABLED=1" >&2
  exit 2
fi
if [[ "${#ROBOT_SCOPE_CONTROL_BRIDGE_KEY}" -lt 32 ]]; then
  echo "[Robot Scope] ROBOT_SCOPE_CONTROL_BRIDGE_KEY must contain at least 32 characters" >&2
  exit 2
fi

source "$PROJECT_DIR/scripts/setup_go2_ros2_humble.sh"

PYTHON_BIN="python3"
if [[ -x "$PROJECT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
fi

cd "$PROJECT_DIR"
exec "$PYTHON_BIN" -m robot_dashboard.go2_control_bridge \
  --profile "$PROJECT_DIR/config/go2.json"
