#!/usr/bin/env bash
set -eo pipefail

XT16_BRIDGE="${XT16_BRIDGE:-$HOME/ws/go2_3d/xt16_fastlio_bridge.py}"

source /opt/ros/humble/setup.bash
source "$HOME/unitree_ros2/cyclonedds_ws/install/setup.bash"
source "$HOME/setup_go2_ros2_humble.sh"

exec python3 "$XT16_BRIDGE"
