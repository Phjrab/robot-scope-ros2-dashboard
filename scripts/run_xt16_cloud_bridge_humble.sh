#!/usr/bin/env bash
set -eo pipefail

if [[ "$#" -ne 0 ]]; then
  echo "[Robot Scope] wireless XT16 cloud bridge accepts no arguments" >&2
  exit 2
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
CLOUD_BRIDGE="$PROJECT_DIR/workspaces/ws/xt16_bridge_ws/install/lib/robot_scope_xt16_bridge/robot_scope_xt16_cloud_bridge_node"
[[ -x "$CLOUD_BRIDGE" ]] || {
  echo "[Robot Scope] built C++ XT16 cloud bridge is missing; run scripts/build_xt16_bridge_humble.sh" >&2
  exit 1
}

source /opt/ros/humble/setup.bash
exec "$CLOUD_BRIDGE"
