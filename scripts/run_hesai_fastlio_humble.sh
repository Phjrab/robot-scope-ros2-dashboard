#!/usr/bin/env bash
set -eo pipefail

# FAST-LIO consumes the already-running XT16 bridge topics:
#   /velodyne_points + /imu/body
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
WORKSPACE_ROOT="${ROBOT_SCOPE_WORKSPACE_ROOT:-$HOME}"
LIVOX_SDK_PREFIX="${ROBOT_SCOPE_LIVOX_SDK_PREFIX:-$WORKSPACE_ROOT/ws/livox/sdk2_install}"
if [[ "$WORKSPACE_ROOT" != /* || "$WORKSPACE_ROOT" == "/" ||
  "$LIVOX_SDK_PREFIX" != /* || "$LIVOX_SDK_PREFIX" == "/" ]]; then
  echo "[Robot Scope] workspace and Livox-SDK2 paths must be absolute and safe" >&2
  exit 1
fi
FASTLIO_CONFIG_PATH="$PROJECT_DIR/config"
FASTLIO_CONFIG_FILE="fastlio_xt16.yaml"
FASTLIO_RVIZ="${FASTLIO_RVIZ:-false}"
[[ -f "$FASTLIO_CONFIG_PATH/$FASTLIO_CONFIG_FILE" ]] || {
  echo "[Robot Scope] repository FAST-LIO config is missing" >&2
  exit 1
}

# Keep unrelated overlays out of this process.  FAST-LIO's installed overlay
# brings in the message definitions it needs.
unset AMENT_PREFIX_PATH COLCON_PREFIX_PATH CMAKE_PREFIX_PATH PYTHONPATH
unset RMW_IMPLEMENTATION CYCLONEDDS_URI

source /opt/ros/humble/setup.bash
if [[ ! -f "$LIVOX_SDK_PREFIX/lib/liblivox_lidar_sdk_shared.so" ]]; then
  echo "[Robot Scope] private Livox-SDK2 runtime is missing" >&2
  exit 1
fi
export LD_LIBRARY_PATH="$LIVOX_SDK_PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
source "$WORKSPACE_ROOT/ws/livox/ws_livox/install/setup.bash"
source "$WORKSPACE_ROOT/ws/fastlio_ws/install/setup.bash"

export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
LIDAR_CIDR="${ROBOT_SCOPE_GO2_INTERFACE_CIDR:-192.168.123.99/24}"
LIDAR_IFACE="${ROBOT_SCOPE_GO2_INTERFACE:-}"
if [[ -z "$LIDAR_IFACE" ]]; then
  LIDAR_IFACE="$(
    ip -o -4 addr show 2>/dev/null |
      awk -v cidr="$LIDAR_CIDR" '$4 == cidr {print $2; exit}'
  )"
fi
if [[ ! "$LIDAR_IFACE" =~ ^[A-Za-z0-9_.:-]{1,32}$ ]] ||
  [[ ! -d "/sys/class/net/$LIDAR_IFACE" ]]; then
  echo "[Robot Scope] configured LiDAR interface is missing or invalid" >&2
  exit 1
fi
if ! ip -o -4 addr show dev "$LIDAR_IFACE" 2>/dev/null |
  awk -v cidr="$LIDAR_CIDR" '$4 == cidr {found=1} END {exit !found}'; then
  echo "[Robot Scope] $LIDAR_IFACE does not own required address $LIDAR_CIDR" >&2
  exit 1
fi
export CYCLONEDDS_URI="<CycloneDDS><Domain><General><Interfaces><NetworkInterface name=\"$LIDAR_IFACE\" priority=\"default\" multicast=\"default\" /></Interfaces></General></Domain></CycloneDDS>"

exec ros2 launch fast_lio mapping.launch.py \
  config_path:="$FASTLIO_CONFIG_PATH" \
  config_file:="$FASTLIO_CONFIG_FILE" \
  rviz:="$FASTLIO_RVIZ"
