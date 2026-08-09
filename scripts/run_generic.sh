#!/usr/bin/env bash
set -eo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="${ROBOT_SCOPE_DIR:-$(dirname -- "$SCRIPT_DIR")}"
PORT="${ROBOT_SCOPE_PORT:-8088}"
ROBOT_IP="${ROBOT_SCOPE_ROBOT_IP:-}"
ROS_DISTRO_NAME="${ROS_DISTRO:-humble}"
PROFILE_NAME="${ROBOT_SCOPE_PROFILE:-generic}"

case "$PROFILE_NAME" in
  generic)
    PROFILE_FILE="generic.json"
    ;;
  turtlebot)
    PROFILE_FILE="turtlebot.json"
    ;;
  so-101|so101)
    PROFILE_FILE="so101.json"
    ;;
  *)
    echo "[Robot Scope] unsupported ROBOT_SCOPE_PROFILE: $PROFILE_NAME" >&2
    exit 64
    ;;
esac

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
  --profile "$PROJECT_DIR/config/$PROFILE_FILE"
