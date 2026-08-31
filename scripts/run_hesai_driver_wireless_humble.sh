#!/usr/bin/env bash
set -eo pipefail

if [[ "$#" -ne 0 ]]; then
  echo "[Robot Scope] wireless Hesai driver accepts no arguments" >&2
  exit 2
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
WORKSPACE_ROOT="${ROBOT_SCOPE_WORKSPACE_ROOT:-$HOME}"
HESAI_CONFIG="$PROJECT_DIR/config/hesai_xt16_wireless.yaml"

[[ "$WORKSPACE_ROOT" == /* && "$WORKSPACE_ROOT" != "/" ]] || {
  echo "[Robot Scope] wireless Hesai workspace path is unsafe" >&2
  exit 2
}
[[ -f "$HESAI_CONFIG" ]] || {
  echo "[Robot Scope] repository wireless Hesai config is missing" >&2
  exit 1
}

python3 "$PROJECT_DIR/scripts/hesai_calibration_manifest.py" validate

source "$PROJECT_DIR/scripts/setup_wireless_mapping_ros2_humble.sh"
source "$WORKSPACE_ROOT/ws/hesai_ws/install/setup.bash"

exec ros2 run hesai_ros_driver hesai_ros_driver_node \
  --ros-args -p config_path:="$HESAI_CONFIG"
