#!/usr/bin/env bash
# Source this file to bind ROS 2 Humble/CycloneDDS to the dedicated Go2 NIC.
# It is repository-owned and replaces the historical ~/setup_go2_ros2_humble.sh.

robot_scope_setup_error() {
  echo "[Robot Scope] $*" >&2
}

if [[ -n "${CONDA_PREFIX:-}" ]]; then
  robot_scope_setup_error "deactivate Conda before loading the ROS 2 environment"
  return 1 2>/dev/null || exit 1
fi

ROBOT_SCOPE_ROS_SETUP="${ROBOT_SCOPE_ROS_SETUP:-/opt/ros/humble/setup.bash}"
ROBOT_SCOPE_WORKSPACE_ROOT="${ROBOT_SCOPE_WORKSPACE_ROOT:-$HOME}"
ROBOT_SCOPE_UNITREE_SETUP="${ROBOT_SCOPE_UNITREE_SETUP:-$ROBOT_SCOPE_WORKSPACE_ROOT/unitree_ros2/cyclonedds_ws/install/setup.bash}"
ROBOT_SCOPE_GO2_INTERFACE="${ROBOT_SCOPE_GO2_INTERFACE:-}"
ROBOT_SCOPE_GO2_INTERFACE_CIDR="${ROBOT_SCOPE_GO2_INTERFACE_CIDR:-192.168.123.99/24}"

if [[ "$ROBOT_SCOPE_WORKSPACE_ROOT" != /* || "$ROBOT_SCOPE_WORKSPACE_ROOT" == "/" ]]; then
  robot_scope_setup_error "ROBOT_SCOPE_WORKSPACE_ROOT must be an absolute non-root path"
  return 1 2>/dev/null || exit 1
fi

if [[ ! -f "$ROBOT_SCOPE_ROS_SETUP" ]]; then
  robot_scope_setup_error "ROS 2 Humble setup is missing: $ROBOT_SCOPE_ROS_SETUP"
  return 1 2>/dev/null || exit 1
fi
if [[ ! -f "$ROBOT_SCOPE_UNITREE_SETUP" ]]; then
  robot_scope_setup_error "Unitree workspace setup is missing: $ROBOT_SCOPE_UNITREE_SETUP"
  return 1 2>/dev/null || exit 1
fi
if ! command -v ip >/dev/null 2>&1; then
  robot_scope_setup_error "iproute2 is not installed"
  return 1 2>/dev/null || exit 1
fi

# shellcheck disable=SC1090
source "$ROBOT_SCOPE_ROS_SETUP"
# shellcheck disable=SC1090
source "$ROBOT_SCOPE_UNITREE_SETUP"

if [[ -z "$ROBOT_SCOPE_GO2_INTERFACE" ]]; then
  ROBOT_SCOPE_GO2_INTERFACE="$(
    ip -o -4 address show 2>/dev/null |
      awk -v cidr="$ROBOT_SCOPE_GO2_INTERFACE_CIDR" '$4 == cidr {print $2; exit}'
  )"
fi

if [[ ! "$ROBOT_SCOPE_GO2_INTERFACE" =~ ^[A-Za-z0-9_.:-]{1,32}$ ]]; then
  robot_scope_setup_error "Go2 interface name is missing or invalid"
  return 1 2>/dev/null || exit 1
fi
if [[ ! -d "/sys/class/net/$ROBOT_SCOPE_GO2_INTERFACE" ]]; then
  robot_scope_setup_error "Go2 interface does not exist: $ROBOT_SCOPE_GO2_INTERFACE"
  return 1 2>/dev/null || exit 1
fi

if ! ip -o -4 address show dev "$ROBOT_SCOPE_GO2_INTERFACE" 2>/dev/null |
  awk -v cidr="$ROBOT_SCOPE_GO2_INTERFACE_CIDR" '$4 == cidr {found=1} END {exit !found}'; then
  robot_scope_setup_error \
    "$ROBOT_SCOPE_GO2_INTERFACE does not own required address $ROBOT_SCOPE_GO2_INTERFACE_CIDR"
  return 1 2>/dev/null || exit 1
fi

export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_LOCALHOST_ONLY=0
export ROBOT_SCOPE_GO2_INTERFACE
export ROBOT_SCOPE_GO2_INTERFACE_CIDR
export ROBOT_SCOPE_WORKSPACE_ROOT
export CYCLONEDDS_URI="<CycloneDDS><Domain><General><Interfaces><NetworkInterface name=\"$ROBOT_SCOPE_GO2_INTERFACE\" priority=\"default\" multicast=\"default\" /></Interfaces></General><Discovery><MaxAutoParticipantIndex>80</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>"

echo "[Robot Scope] ROS 2 Humble + CycloneDDS ready | iface=$ROBOT_SCOPE_GO2_INTERFACE | domain=${ROS_DOMAIN_ID:-0}"

unset ROBOT_SCOPE_ROS_SETUP ROBOT_SCOPE_UNITREE_SETUP
unset -f robot_scope_setup_error
