#!/usr/bin/env bash
# Source before launching any component of the fixed onboard profile.
# This selects existing paths; it never changes network or control state.

robot_scope_onboard_error() {
  echo "[Robot Scope] go2-onboard: $*" >&2
}

if [[ "${ROBOT_SCOPE_MAPPING_PROFILE:-}" == "go2-onboard" ]]; then
  if [[ "${ROS_DISTRO:-humble}" != "humble" ||
    "${RMW_IMPLEMENTATION:-rmw_cyclonedds_cpp}" != "rmw_cyclonedds_cpp" ||
    "${ROS_LOCALHOST_ONLY:-0}" != "0" ||
    "${ROBOT_SCOPE_CONTROL_TRANSPORT:-ros}" != "ros" ||
    "${ROBOT_SCOPE_CONTROL_BRIDGE_LIFECYCLE_TRANSPORT:-local}" != "local" ||
    "${ROBOT_SCOPE_REALSENSE_PROFILE_LIFECYCLE_MODE:-local}" != "local" ||
    "${ROBOT_SCOPE_FASTLIO_DDS_MODE:-direct}" != "direct" ]]; then
    robot_scope_onboard_error "requires Humble, CycloneDDS, ROS control, local lifecycle and direct sensor DDS"
    unset -f robot_scope_onboard_error
    return 2 2>/dev/null || exit 2
  fi
  export ROBOT_SCOPE_GO2_INTERFACE="${ROBOT_SCOPE_GO2_INTERFACE:-eth0}"
  export ROBOT_SCOPE_GO2_INTERFACE_CIDR="${ROBOT_SCOPE_GO2_INTERFACE_CIDR:-192.168.123.18/24}"
  export ROBOT_SCOPE_CAMERA_INTERFACE="${ROBOT_SCOPE_CAMERA_INTERFACE:-$ROBOT_SCOPE_GO2_INTERFACE}"
  export ROBOT_SCOPE_CONTROL_TRANSPORT=ros
  export ROBOT_SCOPE_CONTROL_BRIDGE_LIFECYCLE_TRANSPORT=local
  export ROBOT_SCOPE_REALSENSE_PROFILE_LIFECYCLE_MODE=local
  export ROBOT_SCOPE_FASTLIO_DDS_MODE=direct
fi
unset -f robot_scope_onboard_error
