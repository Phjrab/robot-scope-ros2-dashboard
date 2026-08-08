#!/usr/bin/env bash
set -eo pipefail

PROJECT_DIR="${ROBOT_SCOPE_DIR:-$HOME/robot-scope}"
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
if [[ -f "$HOME/setup_go2_ros2_humble.sh" ]]; then
  source "$HOME/setup_go2_ros2_humble.sh"
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
