#!/usr/bin/env bash
set -eo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
XT16_BRIDGE="$PROJECT_DIR/workspaces/ws/xt16_bridge_ws/install/lib/robot_scope_xt16_bridge/robot_scope_xt16_bridge_node"
[[ -x "$XT16_BRIDGE" ]] || {
  echo "[Robot Scope] built C++ XT16 bridge is missing; run scripts/build_xt16_bridge_humble.sh" >&2
  exit 1
}

source "$PROJECT_DIR/scripts/setup_go2_ros2_humble.sh"

exec "$XT16_BRIDGE"
