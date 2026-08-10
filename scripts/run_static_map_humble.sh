#!/usr/bin/env bash
set -eo pipefail

WORKSPACE_ROOT="${ROBOT_SCOPE_WORKSPACE_ROOT:-$HOME}"
MAP_YAML="${ROBOT_SCOPE_STATIC_MAP:-$WORKSPACE_ROOT/ws/go2_3d/maps/go2_room_2d.yaml}"
if [[ "$WORKSPACE_ROOT" != /* || "$WORKSPACE_ROOT" == "/" || "$MAP_YAML" != /* ]]; then
  echo "[Robot Scope] workspace and static map paths must be absolute and safe" >&2
  exit 2
fi
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"

source "$PROJECT_DIR/scripts/setup_go2_ros2_humble.sh"

exec ros2 run nav2_map_server map_server \
  --ros-args -p yaml_filename:="$MAP_YAML"
