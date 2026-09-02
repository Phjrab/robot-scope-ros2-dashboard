#!/usr/bin/env bash
set -eo pipefail

if [[ "$#" -ne 0 ]]; then
  echo "[Robot Scope] wireless XT16 cloud bridge accepts no arguments" >&2
  exit 2
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
DEPENDENCY_WORKSPACE_ROOT="${ROBOT_SCOPE_DEPENDENCY_WORKSPACE_ROOT:-$PROJECT_DIR/workspaces}"
[[ "$DEPENDENCY_WORKSPACE_ROOT" == /* && "$DEPENDENCY_WORKSPACE_ROOT" != "/" ]] || {
  echo "[Robot Scope] dependency workspace root must be an absolute safe path" >&2
  exit 2
}
CLOUD_BRIDGE="$DEPENDENCY_WORKSPACE_ROOT/ws/xt16_bridge_ws/install/lib/robot_scope_xt16_bridge/robot_scope_xt16_cloud_bridge_node"
[[ -x "$CLOUD_BRIDGE" ]] || {
  echo "[Robot Scope] built C++ XT16 cloud bridge is missing; run scripts/build_xt16_bridge_humble.sh" >&2
  exit 1
}

source "$PROJECT_DIR/scripts/setup_wireless_mapping_ros2_humble.sh"
exec "$CLOUD_BRIDGE"
