#!/usr/bin/env bash
set -eo pipefail

HESAI_CONFIG="${HESAI_CONFIG:-$HOME/ws/hesai_ws/src/HesaiLidar_ROS_2.0/config/config.yaml}"

source /opt/ros/humble/setup.bash
source "$HOME/unitree_ros2/cyclonedds_ws/install/setup.bash"
source "$HOME/ws/hesai_ws/install/setup.bash"
source "$HOME/setup_go2_ros2_humble.sh"

exec ros2 run hesai_ros_driver hesai_ros_driver_node \
  --ros-args -p config_path:="$HESAI_CONFIG"
