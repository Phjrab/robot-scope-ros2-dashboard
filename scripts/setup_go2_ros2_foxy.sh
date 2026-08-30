#!/usr/bin/env bash
# Source this file to bind ROS 2 Foxy/CycloneDDS to the robot-side Go2 NIC.

robot_scope_setup_error() {
  echo "[Robot Scope] $*" >&2
}

if [[ -n "${CONDA_PREFIX:-}" ]]; then
  robot_scope_setup_error "deactivate Conda before loading the ROS 2 environment"
  return 1 2>/dev/null || exit 1
fi

ROBOT_SCOPE_ROS_SETUP="${ROBOT_SCOPE_ROS_SETUP:-/opt/ros/foxy/setup.bash}"
ROBOT_SCOPE_UNITREE_SETUP="${ROBOT_SCOPE_UNITREE_SETUP:-$HOME/autonomy_stack_go2/install/setup.bash}"
ROBOT_SCOPE_CYCLONEDDS_SETUP="${ROBOT_SCOPE_CYCLONEDDS_SETUP:-$HOME/unitree_ros2/cyclonedds_ws/install/setup.bash}"
ROBOT_SCOPE_GO2_INTERFACE="${ROBOT_SCOPE_GO2_INTERFACE:-eth0}"
ROBOT_SCOPE_GO2_INTERFACE_CIDR="${ROBOT_SCOPE_GO2_INTERFACE_CIDR:-192.168.123.18/24}"

for setup_file in \
  "$ROBOT_SCOPE_ROS_SETUP" \
  "$ROBOT_SCOPE_UNITREE_SETUP" \
  "$ROBOT_SCOPE_CYCLONEDDS_SETUP"; do
  if [[ ! -f "$setup_file" ]]; then
    robot_scope_setup_error "required ROS setup is missing: $setup_file"
    return 1 2>/dev/null || exit 1
  fi
done
if [[ ! "$ROBOT_SCOPE_GO2_INTERFACE" =~ ^[A-Za-z0-9_.:-]{1,32}$ ]]; then
  robot_scope_setup_error "Go2 interface name is invalid"
  return 1 2>/dev/null || exit 1
fi
if [[ ! "$ROBOT_SCOPE_GO2_INTERFACE_CIDR" =~ ^192\.168\.123\.[0-9]{1,3}/(24|25|26|27|28|29|30|31|32)$ ]]; then
  robot_scope_setup_error "Go2 interface CIDR is invalid"
  return 1 2>/dev/null || exit 1
fi
if ! ip -o -4 address show dev "$ROBOT_SCOPE_GO2_INTERFACE" 2>/dev/null |
  awk -v cidr="$ROBOT_SCOPE_GO2_INTERFACE_CIDR" '$4 == cidr {found=1} END {exit !found}'; then
  robot_scope_setup_error \
    "$ROBOT_SCOPE_GO2_INTERFACE does not own $ROBOT_SCOPE_GO2_INTERFACE_CIDR"
  return 1 2>/dev/null || exit 1
fi

# shellcheck disable=SC1090
source "$ROBOT_SCOPE_ROS_SETUP"
# shellcheck disable=SC1090
source "$ROBOT_SCOPE_UNITREE_SETUP"
# shellcheck disable=SC1090
source "$ROBOT_SCOPE_CYCLONEDDS_SETUP"

export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_LOCALHOST_ONLY=0
export CYCLONEDDS_URI="<CycloneDDS><Domain><General><Interfaces><NetworkInterface name=\"$ROBOT_SCOPE_GO2_INTERFACE\" priority=\"default\" multicast=\"default\" /></Interfaces></General><Discovery><MaxAutoParticipantIndex>80</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>"

echo "[Robot Scope] ROS 2 Foxy + CycloneDDS ready | iface=$ROBOT_SCOPE_GO2_INTERFACE | domain=${ROS_DOMAIN_ID:-0}"

unset ROBOT_SCOPE_ROS_SETUP ROBOT_SCOPE_UNITREE_SETUP ROBOT_SCOPE_CYCLONEDDS_SETUP
unset -f robot_scope_setup_error
