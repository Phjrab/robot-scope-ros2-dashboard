#!/usr/bin/env bash
# Source this file to bind only the wireless mapping ROS graph to eno1/.50.10.

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
export ROS_LOCALHOST_ONLY=0
export CYCLONEDDS_URI="<CycloneDDS><Domain><General><Interfaces><NetworkInterface name=\"$WIRELESS_MAPPING_INTERFACE\" priority=\"default\" multicast=\"default\" /></Interfaces></General><Discovery><MaxAutoParticipantIndex>80</MaxAutoParticipantIndex></Discovery><Internal><SocketReceiveBufferSize max=\"8 MiB\" /></Internal></Domain></CycloneDDS>"

unset WIRELESS_MAPPING_INTERFACE WIRELESS_MAPPING_CIDR
