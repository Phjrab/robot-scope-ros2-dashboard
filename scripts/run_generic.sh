#!/usr/bin/env bash
set -eo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="${ROBOT_SCOPE_DIR:-$(dirname -- "$SCRIPT_DIR")}"
PORT="${ROBOT_SCOPE_PORT:-8088}"
ROBOT_IP="${ROBOT_SCOPE_ROBOT_IP:-}"
ROS_DISTRO_NAME="${ROS_DISTRO:-humble}"
PROFILE_NAME="${ROBOT_SCOPE_PROFILE:-generic}"
WORKSPACE_ROOT="${ROBOT_SCOPE_WORKSPACE_ROOT:-$PROJECT_DIR/workspaces}"
MAPS_DIR="${ROBOT_SCOPE_MAPS_DIR:-$WORKSPACE_ROOT/ws/go2_3d/maps}"
RUNTIME_DIR="${ROBOT_SCOPE_RUNTIME_DIR:-$PROJECT_DIR/runtime}"
DATASET_DIR="${ROBOT_SCOPE_DATASET_DIR:-$RUNTIME_DIR/datasets}"
STATE_DIR="${ROBOT_SCOPE_STATE_DIR:-$RUNTIME_DIR/state}"
SOURCE_SELECTION_STATE="${ROBOT_SCOPE_SOURCE_SELECTION_STATE:-$STATE_DIR/source-selection.json}"
NAVIGATION_RUNTIME_DIR="${ROBOT_SCOPE_NAVIGATION_RUNTIME_DIR:-$STATE_DIR/navigation}"
ROS_LOG_DIR="${ROS_LOG_DIR:-$RUNTIME_DIR/logs/ros}"

if [[ "$MAPS_DIR" != /* || "$RUNTIME_DIR" != /* || "$RUNTIME_DIR" == "/" ||
  "$DATASET_DIR" != /* || "$DATASET_DIR" == "/" ||
  "$STATE_DIR" != /* || "$STATE_DIR" == "/" ||
  "$SOURCE_SELECTION_STATE" != /* || "$NAVIGATION_RUNTIME_DIR" != /* ||
  "$ROS_LOG_DIR" != /* || "$ROS_LOG_DIR" == "/" ]]; then
  echo "[Robot Scope] maps, dataset, state and log paths must be absolute and safe" >&2
  exit 2
fi
mkdir -p -- "$ROS_LOG_DIR"
export ROS_LOG_DIR

case "$PROFILE_NAME" in
  generic)
    PROFILE_FILE="generic.json"
    ;;
  turtlebot)
    PROFILE_FILE="turtlebot.json"
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
  --mapping-output-dir "$MAPS_DIR" \
  --dataset-output-dir "$DATASET_DIR" \
  --source-selection-state "$SOURCE_SELECTION_STATE" \
  --navigation-runtime-dir "$NAVIGATION_RUNTIME_DIR" \
  --profile "$PROJECT_DIR/config/$PROFILE_FILE"
