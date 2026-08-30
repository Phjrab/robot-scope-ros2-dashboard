#!/usr/bin/env bash
set -eo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="${ROBOT_SCOPE_DIR:-$(dirname -- "$SCRIPT_DIR")}"
PORT="${ROBOT_SCOPE_PORT:-8088}"
ROBOT_IP="${ROBOT_SCOPE_ROBOT_IP:-192.168.123.161}"
CLOUD_MAX_POINTS="${ROBOT_SCOPE_CLOUD_MAX_POINTS:-10000}"
WORKSPACE_ROOT="${ROBOT_SCOPE_WORKSPACE_ROOT:-$HOME}"
MAPS_DIR="${ROBOT_SCOPE_MAPS_DIR:-$WORKSPACE_ROOT/ws/go2_3d/maps}"
RUNTIME_DIR="${ROBOT_SCOPE_RUNTIME_DIR:-$PROJECT_DIR/runtime}"
DATASET_DIR="${ROBOT_SCOPE_DATASET_DIR:-$RUNTIME_DIR/datasets}"
STATE_DIR="${ROBOT_SCOPE_STATE_DIR:-$RUNTIME_DIR/state}"
SOURCE_SELECTION_STATE="${ROBOT_SCOPE_SOURCE_SELECTION_STATE:-$STATE_DIR/source-selection.json}"
NAVIGATION_RUNTIME_DIR="${ROBOT_SCOPE_NAVIGATION_RUNTIME_DIR:-$STATE_DIR/navigation}"
MODEL_REGISTRY_DIR="${ROBOT_SCOPE_MODEL_REGISTRY_DIR:-$RUNTIME_DIR/model-registry}"
COMPETITION_STATE_DIR="${ROBOT_SCOPE_COMPETITION_STATE_DIR:-$RUNTIME_DIR/competition}"
ROS_LOG_DIR="${ROS_LOG_DIR:-$RUNTIME_DIR/logs/ros}"
if [[ "$WORKSPACE_ROOT" != /* || "$WORKSPACE_ROOT" == "/" ||
  "$MAPS_DIR" != /* || "$RUNTIME_DIR" != /* || "$RUNTIME_DIR" == "/" ||
  "$DATASET_DIR" != /* || "$DATASET_DIR" == "/" ||
  "$STATE_DIR" != /* || "$STATE_DIR" == "/" ||
  "$MODEL_REGISTRY_DIR" != /* || "$MODEL_REGISTRY_DIR" == "/" ||
  "$COMPETITION_STATE_DIR" != /* || "$COMPETITION_STATE_DIR" == "/" ||
  "$SOURCE_SELECTION_STATE" != /* || "$NAVIGATION_RUNTIME_DIR" != /* ||
  "$ROS_LOG_DIR" != /* || "$ROS_LOG_DIR" == "/" ]]; then
  echo "[Robot Scope] workspace, maps, dataset, state and log paths must be absolute and safe" >&2
  exit 2
fi
mkdir -p -- "$ROS_LOG_DIR"
export ROS_LOG_DIR

# rclpy, DDS and JSON encoding use several native threads.  Limiting glibc
# arenas prevents large PointCloud messages from leaving hundreds of MiB in
# one arena per thread after a temporary allocation spike.
export MALLOC_ARENA_MAX="${ROBOT_SCOPE_MALLOC_ARENA_MAX:-2}"
export MALLOC_TRIM_THRESHOLD_="${ROBOT_SCOPE_MALLOC_TRIM_THRESHOLD:-131072}"

# The offline viewer still needs the system ROS Python modules even when the
# Unitree overlay or dedicated cable is unavailable.
source "${ROBOT_SCOPE_ROS_SETUP:-/opt/ros/humble/setup.bash}"

# Publish the startup DDS decision to the health API.  ICMP reachability can
# recover after a cable is connected, but an rclpy participant created in the
# fallback mode cannot retarget itself to the dedicated Go2 interface.
export ROBOT_SCOPE_DDS_MODE="offline_viewer"
export ROBOT_SCOPE_DDS_INTERFACE_READY="0"
unset ROBOT_SCOPE_DDS_INTERFACE
GO2_SETUP="$PROJECT_DIR/scripts/setup_go2_ros2_humble.sh"
if [[ -f "$GO2_SETUP" ]]; then
  if ! source "$GO2_SETUP"; then
    # Keep the observability UI available while the dedicated Go2 cable is
    # disconnected. CycloneDDS auto-selects an active interface; reconnecting
    # the cable and restarting restores the dedicated-interface profile.
    export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
    export ROS_LOCALHOST_ONLY=0
    unset CYCLONEDDS_URI
    echo "[Robot Scope] Go2 interface unavailable; starting dashboard in offline viewer mode."
  else
    export ROBOT_SCOPE_DDS_MODE="go2_interface"
    export ROBOT_SCOPE_DDS_INTERFACE_READY="1"
    ROBOT_SCOPE_DDS_INTERFACE="$ROBOT_SCOPE_GO2_INTERFACE"
    export ROBOT_SCOPE_DDS_INTERFACE
  fi
else
  echo "[Robot Scope] Go2 environment helper unavailable; starting dashboard in offline viewer mode."
fi

PYTHON_BIN="python3"
if [[ -x "$PROJECT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
fi

cd "$PROJECT_DIR"
DASHBOARD_ARGS=(
  --host 0.0.0.0 \
  --port "$PORT" \
  --robot-ip "$ROBOT_IP" \
  --cloud-max-points "$CLOUD_MAX_POINTS" \
  --mapping-output-dir "$MAPS_DIR" \
  --dataset-output-dir "$DATASET_DIR" \
  --source-selection-state "$SOURCE_SELECTION_STATE" \
  --navigation-runtime-dir "$NAVIGATION_RUNTIME_DIR" \
  --model-registry-dir "$MODEL_REGISTRY_DIR" \
  --competition-state-dir "$COMPETITION_STATE_DIR" \
  --profile "$PROJECT_DIR/config/go2.json"
)
PERCEPTION_SOURCE_IP="${ROBOT_SCOPE_PERCEPTION_SOURCE_IP:-}"
PERCEPTION_POLICY="${ROBOT_SCOPE_PERCEPTION_POLICY:-}"
if [[ -n "$PERCEPTION_SOURCE_IP" || -n "$PERCEPTION_POLICY" ]]; then
  if [[ -z "$PERCEPTION_SOURCE_IP" || -z "$PERCEPTION_POLICY" || "$PERCEPTION_POLICY" != /* ]]; then
    echo "[Robot Scope] perception source IP and absolute policy path must be configured together" >&2
    exit 2
  fi
  DASHBOARD_ARGS+=(
    --perception-source-ip "$PERCEPTION_SOURCE_IP"
    --perception-result-port "${ROBOT_SCOPE_PERCEPTION_RESULT_PORT:-8092}"
    --perception-policy "$PERCEPTION_POLICY"
  )
fi
exec "$PYTHON_BIN" -m robot_dashboard.app "${DASHBOARD_ARGS[@]}"
