#!/usr/bin/env bash
set -eo pipefail

# FAST-LIO consumes the already-running XT16 bridge topics:
#   /velodyne_points + /imu/body
FASTLIO_CONFIG_FILE="${FASTLIO_CONFIG_FILE:-xt16.yaml}"
FASTLIO_RVIZ="${FASTLIO_RVIZ:-false}"

# Keep unrelated overlays out of this process.  FAST-LIO's installed overlay
# brings in the message definitions it needs.
unset AMENT_PREFIX_PATH COLCON_PREFIX_PATH CMAKE_PREFIX_PATH PYTHONPATH
unset RMW_IMPLEMENTATION CYCLONEDDS_URI

source /opt/ros/humble/setup.bash
source "$HOME/ws/livox/ws_livox/install/setup.bash"
source "$HOME/ws/fastlio_ws/install/setup.bash"

export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
LIDAR_IFACE="$(ip -o -4 addr show 2>/dev/null | awk '$4 ~ /^192\.168\.123\./ {print $2; exit}')"
if [[ -z "$LIDAR_IFACE" ]]; then
  echo "[Robot Scope] 192.168.123.0/24 LiDAR interface not found" >&2
  exit 1
fi
export CYCLONEDDS_URI="<CycloneDDS><Domain><General><Interfaces><NetworkInterface name=\"$LIDAR_IFACE\" priority=\"default\" multicast=\"default\" /></Interfaces></General></Domain></CycloneDDS>"

exec ros2 launch fast_lio mapping.launch.py \
  config_file:="$FASTLIO_CONFIG_FILE" \
  rviz:="$FASTLIO_RVIZ"
