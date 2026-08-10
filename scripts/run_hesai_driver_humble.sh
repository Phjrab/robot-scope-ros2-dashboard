#!/usr/bin/env bash
set -eo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
HESAI_CONFIG="$PROJECT_DIR/config/hesai_xt16.yaml"
[[ -f "$HESAI_CONFIG" ]] || { echo "[Robot Scope] repository Hesai config is missing" >&2; exit 1; }

source "$PROJECT_DIR/scripts/setup_go2_ros2_humble.sh"
source "$ROBOT_SCOPE_WORKSPACE_ROOT/ws/hesai_ws/install/setup.bash"

exec ros2 run hesai_ros_driver hesai_ros_driver_node \
  --ros-args -p config_path:="$HESAI_CONFIG"
