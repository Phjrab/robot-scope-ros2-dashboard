#!/usr/bin/env bash
set -eo pipefail

PROJECT_DIR="${ROBOT_SCOPE_DIR:-$HOME/robot-scope}"
PORT="${ROBOT_SCOPE_PORT:-8088}"
ROBOT_IP="${ROBOT_SCOPE_ROBOT_IP:-}"
ROS_DISTRO_NAME="${ROS_DISTRO:-humble}"

source "/opt/ros/$ROS_DISTRO_NAME/setup.bash"
if [[ -n "${ROBOT_SCOPE_OVERLAY:-}" ]]; then
  source "$ROBOT_SCOPE_OVERLAY"
fi

PYTHON_BIN="python3"
if [[ -x "$PROJECT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
fi

cd "$PROJECT_DIR"
exec "$PYTHON_BIN" -m robot_dashboard.app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --robot-ip "$ROBOT_IP" \
  --profile "$PROJECT_DIR/config/generic.json"
