#!/usr/bin/env bash
set -eo pipefail

usage() {
  echo "usage: run_go2_navigation_humble.sh --map-yaml ABSOLUTE_FILE --params-file ABSOLUTE_FILE" >&2
  exit 2
}

if [[ "$#" -ne 4 || "$1" != "--map-yaml" || "$3" != "--params-file" ]]; then
  usage
fi

MAP_INPUT="$2"
PARAMS_INPUT="$4"
if [[ "$MAP_INPUT" != /* || "$PARAMS_INPUT" != /* ]]; then
  echo "[Robot Scope] navigation snapshots must use absolute paths" >&2
  exit 2
fi
if [[ ! -f "$MAP_INPUT" || -L "$MAP_INPUT" || ! -f "$PARAMS_INPUT" || -L "$PARAMS_INPUT" ]]; then
  echo "[Robot Scope] navigation snapshots must be regular, non-symlink files" >&2
  exit 2
fi

MAP_YAML="$(realpath -e -- "$MAP_INPUT")"
PARAMS_FILE="$(realpath -e -- "$PARAMS_INPUT")"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
MAPPING_PROFILE="${ROBOT_SCOPE_MAPPING_PROFILE:-go2-xt16-wired}"

case "$MAPPING_PROFILE" in
  go2-xt16-wired)
    source "$PROJECT_DIR/scripts/setup_go2_ros2_humble.sh"
    ;;
  go2-xt16-wireless)
    source "$PROJECT_DIR/scripts/setup_wireless_mapping_ros2_humble.sh"
    ;;
  *)
    echo "[Robot Scope] navigation mapping profile is unsupported" >&2
    exit 2
    ;;
esac
cd "$PROJECT_DIR"

PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="/usr/bin/python3"
fi
if ! "$PYTHON_BIN" -c 'import numpy, rclpy, yaml' >/dev/null 2>&1; then
  PYTHON_BIN="/usr/bin/python3"
fi
if ! "$PYTHON_BIN" -c 'import numpy, rclpy, yaml' >/dev/null 2>&1; then
  echo "[Robot Scope] Python runtime requires numpy, rclpy and PyYAML" >&2
  exit 3
fi

MAP_SERVER="/opt/ros/humble/lib/nav2_map_server/map_server"
CONTROLLER_SERVER="/opt/ros/humble/lib/nav2_controller/controller_server"
PLANNER_SERVER="/opt/ros/humble/lib/nav2_planner/planner_server"
BEHAVIOR_SERVER="/opt/ros/humble/lib/nav2_behaviors/behavior_server"
BT_NAVIGATOR="/opt/ros/humble/lib/nav2_bt_navigator/bt_navigator"
LIFECYCLE_MANAGER="/opt/ros/humble/lib/nav2_lifecycle_manager/lifecycle_manager"
for executable in \
  "$MAP_SERVER" \
  "$CONTROLLER_SERVER" \
  "$PLANNER_SERVER" \
  "$BEHAVIOR_SERVER" \
  "$BT_NAVIGATOR" \
  "$LIFECYCLE_MANAGER"; do
  if [[ ! -x "$executable" ]]; then
    echo "[Robot Scope] required Humble executable is missing: $executable" >&2
    exit 3
  fi
done

PIDS=()
STOPPING=0
REMOTE_ODOM_STARTED=0

remote_lifecycle() {
  /usr/bin/python3 "$PROJECT_DIR/scripts/wireless_mapping_remote_lifecycle.py" "$@"
}

stop_children() {
  local requested_status="${1:-1}"
  if [[ "$STOPPING" -eq 1 ]]; then
    return
  fi
  STOPPING=1
  trap - INT TERM
  if [[ "${#PIDS[@]}" -gt 0 ]]; then
    kill -INT "${PIDS[@]}" 2>/dev/null || true
    local deadline=$((SECONDS + 4))
    while [[ "$SECONDS" -lt "$deadline" ]]; do
      local alive=0
      for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
          alive=1
          break
        fi
      done
      [[ "$alive" -eq 0 ]] && break
      sleep 0.1
    done
    kill -TERM "${PIDS[@]}" 2>/dev/null || true
    wait "${PIDS[@]}" 2>/dev/null || true
  fi
  if [[ "$REMOTE_ODOM_STARTED" -eq 1 ]]; then
    remote_lifecycle --service odom --action stop >/dev/null 2>&1 || true
    REMOTE_ODOM_STARTED=0
  fi
  exit "$requested_status"
}

trap 'stop_children 130' INT TERM

if [[ "$MAPPING_PROFILE" == "go2-xt16-wireless" ]]; then
  odom_state="$(remote_lifecycle --service odom --action ensure-started)" || {
    echo "[Robot Scope] WIRELESS CONTROLLER ODOMETRY OFFLINE" >&2
    stop_children 69
  }
  [[ "$odom_state" == "started" ]] && REMOTE_ODOM_STARTED=1
  "$PROJECT_DIR/scripts/run_wireless_odom_receiver_humble.sh" &
  PIDS+=("$!")
  if ! "$PYTHON_BIN" "$PROJECT_DIR/scripts/check_wireless_odom_ready.py" \
    --timeout "${ROBOT_SCOPE_WIRELESS_ODOM_READY_TIMEOUT_SECONDS:-15}"; then
    echo "[Robot Scope] WIRELESS CONTROLLER ODOMETRY STALE" >&2
    stop_children 69
  fi
fi

"$PYTHON_BIN" -m robot_dashboard.navigation_runtime \
  --runtime-params-file "$PARAMS_FILE" &
PIDS+=("$!")
"$MAP_SERVER" --ros-args \
  --params-file "$PARAMS_FILE" \
  -p yaml_filename:="$MAP_YAML" &
PIDS+=("$!")
"$CONTROLLER_SERVER" --ros-args \
  --params-file "$PARAMS_FILE" \
  -r cmd_vel:=/robot_scope/nav/cmd_vel_raw &
PIDS+=("$!")
"$PLANNER_SERVER" --ros-args --params-file "$PARAMS_FILE" &
PIDS+=("$!")
# Recovery motion is intentionally isolated.  Only controller_server may
# publish the raw navigation command topic consumed by the signed watchdog.
"$BEHAVIOR_SERVER" --ros-args \
  --params-file "$PARAMS_FILE" \
  -r cmd_vel:=/robot_scope/nav/recovery_cmd_vel_blocked &
PIDS+=("$!")
"$BT_NAVIGATOR" --ros-args --params-file "$PARAMS_FILE" &
PIDS+=("$!")
"$LIFECYCLE_MANAGER" --ros-args \
  -r __node:=lifecycle_manager_navigation \
  --params-file "$PARAMS_FILE" &
PIDS+=("$!")

echo "[Robot Scope] fixed Humble navigation stack started | profile=$MAPPING_PROFILE"
set +e
wait -n "${PIDS[@]}"
CHILD_STATUS="$?"
set -e
if [[ "$CHILD_STATUS" -eq 0 ]]; then
  CHILD_STATUS=1
fi
echo "[Robot Scope] navigation child exited unexpectedly (status $CHILD_STATUS)" >&2
stop_children "$CHILD_STATUS"
