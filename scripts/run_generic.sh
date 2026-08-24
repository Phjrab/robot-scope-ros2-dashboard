#!/usr/bin/env bash
set -eo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="${ROBOT_SCOPE_DIR:-$(dirname -- "$SCRIPT_DIR")}"
PORT="${ROBOT_SCOPE_PORT:-8088}"
ROBOT_IP="${ROBOT_SCOPE_ROBOT_IP:-}"
ROS_DISTRO_NAME="${ROS_DISTRO:-}"
if [[ -z "$ROS_DISTRO_NAME" ]]; then
  OS_VERSION="$(awk -F= '$1 == "VERSION_ID" {value=$2; gsub(/^["'"'"']|["'"'"']$/, "", value); print value; exit}' /etc/os-release 2>/dev/null || true)"
  case "$OS_VERSION" in
    22.04) ROS_DISTRO_NAME="humble" ;;
    24.04) ROS_DISTRO_NAME="jazzy" ;;
    *)
      echo "[Robot Scope] set ROS_DISTRO explicitly on unsupported Ubuntu releases" >&2
      exit 2
      ;;
  esac
fi
case "$ROS_DISTRO_NAME" in
  humble|jazzy) ;;
  *)
    echo "[Robot Scope] unsupported ROS_DISTRO: $ROS_DISTRO_NAME" >&2
    exit 64
    ;;
esac
ROS_SETUP="${ROBOT_SCOPE_ROS_SETUP:-/opt/ros/$ROS_DISTRO_NAME/setup.bash}"
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

if [[ ! -f "$ROS_SETUP" ]]; then
  echo "[Robot Scope] ROS 2 $ROS_DISTRO_NAME setup is missing: $ROS_SETUP" >&2
  exit 2
fi
source "$ROS_SETUP"
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
