#!/usr/bin/env bash
set -eo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="${ROBOT_SCOPE_DIR:-$(dirname -- "$SCRIPT_DIR")}"
PORT="${ROBOT_SCOPE_PORT:-8088}"
ROBOT_IP="${ROBOT_SCOPE_ROBOT_IP:-192.168.123.161}"
CLOUD_MAX_POINTS="${ROBOT_SCOPE_CLOUD_MAX_POINTS:-10000}"

# rclpy, DDS and JSON encoding use several native threads.  Limiting glibc
# arenas prevents large PointCloud messages from leaving hundreds of MiB in
# one arena per thread after a temporary allocation spike.
export MALLOC_ARENA_MAX="${ROBOT_SCOPE_MALLOC_ARENA_MAX:-2}"
export MALLOC_TRIM_THRESHOLD_="${ROBOT_SCOPE_MALLOC_TRIM_THRESHOLD:-131072}"

source /opt/ros/humble/setup.bash
if [[ -f "$HOME/unitree_ros2/cyclonedds_ws/install/setup.bash" ]]; then
  source "$HOME/unitree_ros2/cyclonedds_ws/install/setup.bash"
fi

# Publish the startup DDS decision to the health API.  ICMP reachability can
# recover after a cable is connected, but an rclpy participant created in the
# fallback mode cannot retarget itself to the dedicated Go2 interface.
export ROBOT_SCOPE_DDS_MODE="offline_viewer"
export ROBOT_SCOPE_DDS_INTERFACE_READY="0"
unset ROBOT_SCOPE_DDS_INTERFACE
if [[ -f "$HOME/setup_go2_ros2_humble.sh" ]]; then
  if ! source "$HOME/setup_go2_ros2_humble.sh"; then
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
    ROBOT_SCOPE_DDS_INTERFACE="$(ip -o -4 addr show 2>/dev/null | awk '$4 ~ /^192\.168\.123\./ {print $2; exit}')"
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
exec "$PYTHON_BIN" -m robot_dashboard.app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --robot-ip "$ROBOT_IP" \
  --cloud-max-points "$CLOUD_MAX_POINTS" \
  --profile "$PROJECT_DIR/config/go2.json"
