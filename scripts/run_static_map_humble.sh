#!/usr/bin/env bash
set -eo pipefail

MAP_YAML="${ROBOT_SCOPE_STATIC_MAP:-$HOME/ws/go2_3d/maps/go2_room_2d.yaml}"

source /opt/ros/humble/setup.bash
source "$HOME/setup_go2_ros2_humble.sh"

exec ros2 run nav2_map_server map_server \
  --ros-args -p yaml_filename:="$MAP_YAML"
