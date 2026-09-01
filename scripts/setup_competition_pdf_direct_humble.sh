#!/usr/bin/env bash
# Source this file for the isolated Track C direct-wired competition profile.

robot_scope_competition_setup_error() {
  echo "[Robot Scope] $*" >&2
}

if [[ "${ROS_DISTRO:-}" != "" && "${ROS_DISTRO:-}" != "humble" ]]; then
  robot_scope_competition_setup_error \
    "competition-pdf-direct refuses a mixed ROS environment: ${ROS_DISTRO}"
  return 1 2>/dev/null || exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
DIRECT_SETUP="$PROJECT_DIR/scripts/setup_go2_ros2_humble.sh"
if [[ ! -f "$DIRECT_SETUP" ]]; then
  robot_scope_competition_setup_error "direct Humble setup is missing"
  return 1 2>/dev/null || exit 1
fi

export ROBOT_SCOPE_MAPPING_PROFILE="competition-pdf-direct"
# shellcheck disable=SC1090
source "$DIRECT_SETUP" || return 1 2>/dev/null || exit 1

if [[ "${ROS_DISTRO:-}" != "humble" ]]; then
  robot_scope_competition_setup_error "competition-pdf-direct requires ROS 2 Humble"
  return 1 2>/dev/null || exit 1
fi
if [[ "${RMW_IMPLEMENTATION:-}" != "rmw_cyclonedds_cpp" ]]; then
  robot_scope_competition_setup_error "competition-pdf-direct requires CycloneDDS"
  return 1 2>/dev/null || exit 1
fi

echo "[Robot Scope] Track C direct competition environment ready"
unset DIRECT_SETUP PROJECT_DIR SCRIPT_DIR
unset -f robot_scope_competition_setup_error
