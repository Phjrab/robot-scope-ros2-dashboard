#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 0 ]]; then
  echo "[Robot Scope] wireless XT16 cloud-only build accepts no arguments" >&2
  exit 2
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
WORKSPACE_ROOT="${ROBOT_SCOPE_WORKSPACE_ROOT:-$HOME}"
ROS_SETUP="${ROBOT_SCOPE_ROS_SETUP:-/opt/ros/humble/setup.bash}"
PACKAGE_DIR="$PROJECT_DIR/ros2/robot_scope_xt16_bridge"
BUILD_ROOT="$PROJECT_DIR/workspaces/ws/xt16_bridge_ws"

if [[ "$WORKSPACE_ROOT" != /* || "$WORKSPACE_ROOT" == "/" || "$BUILD_ROOT" == "/" ]]; then
  echo "[Robot Scope] XT16 cloud-only workspace paths must be absolute and safe" >&2
  exit 2
fi
[[ -f "$ROS_SETUP" ]] || { echo "[Robot Scope] ROS 2 Humble setup is missing" >&2; exit 1; }
[[ -f "$PACKAGE_DIR/package.xml" ]] || { echo "[Robot Scope] C++ XT16 bridge source is missing" >&2; exit 1; }
command -v colcon >/dev/null 2>&1 || { echo "[Robot Scope] colcon is required" >&2; exit 1; }

set +u
# shellcheck disable=SC1090
source "$ROS_SETUP"
set -u

mkdir -p "$BUILD_ROOT"
exec colcon \
  --log-base "$BUILD_ROOT/log" \
  build \
  --base-paths "$PACKAGE_DIR" \
  --build-base "$BUILD_ROOT/build" \
  --install-base "$BUILD_ROOT/install" \
  --merge-install \
  --cmake-args \
    -DCMAKE_BUILD_TYPE=Release \
    -DROBOT_SCOPE_XT16_BUILD_LEGACY=OFF
