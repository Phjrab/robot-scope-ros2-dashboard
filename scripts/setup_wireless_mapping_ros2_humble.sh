#!/usr/bin/env bash
# Source this file to keep the wireless mapping ROS graph local to the external
# Jetson.  eno1/.50.10 remains a required fixed transport interface for the
# bounded XT16, IMU and odometry UDP receivers, but it is not a DDS discovery
# bus.  This prevents an unrelated ROS workstation on the shared competition
# LAN from contributing same-name publishers to the safety-cardinality gates.

WIRELESS_MAPPING_INTERFACE="eno1"
WIRELESS_MAPPING_CIDR="192.168.50.10/24"

if [[ ! -f /opt/ros/humble/setup.bash ]]; then
  echo "[Robot Scope] ROS 2 Humble setup is missing" >&2
  return 1 2>/dev/null || exit 1
fi
if [[ ! -d "/sys/class/net/$WIRELESS_MAPPING_INTERFACE" ]]; then
  echo "[Robot Scope] wireless mapping interface is missing" >&2
  return 1 2>/dev/null || exit 1
fi
if ! ip -o -4 address show dev "$WIRELESS_MAPPING_INTERFACE" 2>/dev/null |
  awk -v cidr="$WIRELESS_MAPPING_CIDR" '$4 == cidr {found=1} END {exit !found}'; then
  echo "[Robot Scope] wireless mapping interface address is unavailable" >&2
  return 1 2>/dev/null || exit 1
fi

source /opt/ros/humble/setup.bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_LOCALHOST_ONLY=1
# A service EnvironmentFile may contain the direct-wired CycloneDDS binding.
# Replace it with a loopback-safe override for this explicit wireless profile.
# CycloneDDS 0.10 defaults to only ten auto participant indices when loopback
# cannot multicast.  The fixed sensor, FAST-LIO and Nav2 processes exceed that
# limit; expanding only the local participant search prevents domain creation
# failure without opening DDS discovery on the competition LAN.
export CYCLONEDDS_URI="<CycloneDDS><Domain><Discovery><MaxAutoParticipantIndex>32</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>"

unset WIRELESS_MAPPING_INTERFACE WIRELESS_MAPPING_CIDR
