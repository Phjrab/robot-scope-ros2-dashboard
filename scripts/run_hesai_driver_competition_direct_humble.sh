#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
WORKSPACE_ROOT="${ROBOT_SCOPE_WORKSPACE_ROOT:-$HOME}"
HESAI_CONFIG="$PROJECT_DIR/config/hesai_xt16_competition_direct.yaml"
HESAI_DRIVER="$WORKSPACE_ROOT/ws/hesai_ws/install/hesai_ros_driver/lib/hesai_ros_driver/hesai_ros_driver_node"
[[ "$WORKSPACE_ROOT" == /* && "$WORKSPACE_ROOT" != "/" ]] || {
  echo "[Robot Scope] Track C workspace root must be an absolute non-root path" >&2
  exit 2
}
[[ -f "$HESAI_CONFIG" && ! -L "$HESAI_CONFIG" ]] || {
  echo "[Robot Scope] Track C Hesai config is missing or unsafe" >&2
  exit 2
}
[[ -x "$HESAI_DRIVER" && ! -L "$HESAI_DRIVER" ]] || {
  echo "[Robot Scope] Track C Hesai driver binary is missing or unsafe" >&2
  exit 3
}

source "$PROJECT_DIR/scripts/setup_competition_pdf_direct_humble.sh"
source "$WORKSPACE_ROOT/ws/hesai_ws/install/setup.bash"

exec "$HESAI_DRIVER" --ros-args -p config_path:="$HESAI_CONFIG"
