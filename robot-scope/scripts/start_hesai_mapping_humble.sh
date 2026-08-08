#!/usr/bin/env bash
set -eo pipefail

PROJECT_DIR="${ROBOT_SCOPE_DIR:-$HOME/robot-scope}"
LOG_DIR="${ROBOT_SCOPE_MAPPING_LOG_DIR:-$HOME/ws/go2_3d}"
mkdir -p "$LOG_DIR"

# Fail before leaving detached ROS children behind when the robot/LiDAR cable
# is not ready.  This helper only selects the already-configured interface; it
# never adds addresses or invokes sudo from the dashboard.
source /opt/ros/humble/setup.bash
source "$HOME/setup_go2_ros2_humble.sh"

has_live_match() {
  local pattern="$1"
  local pid
  while read -r pid; do
    [[ -z "$pid" ]] && continue
    if [[ "$(awk '{print $3}' "/proc/$pid/stat" 2>/dev/null || true)" != "Z" ]]; then
      return 0
    fi
  done < <(pgrep -u "$(id -u)" -f -- "$pattern" || true)
  return 1
}

stop_existing() {
  local pattern="$1"
  local label="$2"
  local pids=()
  mapfile -t pids < <(pgrep -u "$(id -u)" -f -- "$pattern" || true)
  if [[ "${#pids[@]}" -eq 0 ]]; then
    return
  fi
  echo "[Robot Scope] stopping previous $label session (${pids[*]})"
  kill -INT "${pids[@]}" 2>/dev/null || true
  local deadline=$((SECONDS + 5))
  while (( SECONDS < deadline )); do
    local alive=0
    for pid in "${pids[@]}"; do
      if kill -0 "$pid" 2>/dev/null && [[ "$(awk '{print $3}' "/proc/$pid/stat" 2>/dev/null || true)" != "Z" ]]; then alive=1; fi
    done
    [[ "$alive" -eq 0 ]] && return
    sleep 0.25
  done
  kill -TERM "${pids[@]}" 2>/dev/null || true
  sleep 1
  for pid in "${pids[@]}"; do
    local state="$(awk '{print $3}' "/proc/$pid/stat" 2>/dev/null || true)"
    if ! kill -0 "$pid" 2>/dev/null || [[ "$state" == "Z" ]]; then continue; fi
    # "새 맵 시작" explicitly resets the fixed mapping stack.  Revalidate the
    # exact same-user process and command pattern before the final escalation,
    # so a reused PID or unrelated process can never be killed.
    local owner="$(stat -c '%u' "/proc/$pid" 2>/dev/null || true)"
    local command="$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)"
    if [[ "$owner" == "$(id -u)" && "$command" =~ $pattern ]]; then
      echo "[Robot Scope] force stopping verified previous $label process (pid $pid)"
      kill -KILL "$pid" 2>/dev/null || true
    else
      echo "[Robot Scope] refused to force stop unverified pid $pid" >&2
      exit 1
    fi
  done
  sleep 0.5
  for pid in "${pids[@]}"; do
    local state="$(awk '{print $3}' "/proc/$pid/stat" 2>/dev/null || true)"
    if kill -0 "$pid" 2>/dev/null && [[ "$state" != "Z" ]]; then
      echo "[Robot Scope] previous $label process did not stop (pid $pid, state $state)" >&2
      exit 1
    fi
  done
}

start_once() {
  local pattern="$1"
  local label="$2"
  local log_file="$3"
  local command="$4"
  if has_live_match "$pattern"; then
    echo "[Robot Scope] $label already running"
    return
  fi
  nohup "$command" > "$log_file" 2>&1 < /dev/null &
  echo "[Robot Scope] started $label"
}

# "새 맵 시작" is an explicit reset operation.  Stop only the fixed mapping
# components owned by this Unix user, then build a fresh FAST-LIO accumulator.
stop_existing "fastlio_mapping|ros2 launch fast_lio" "FAST-LIO"
stop_existing "xt16_fastlio_bridge.py" "XT16 bridge"
stop_existing "hesai_ros_driver_node" "Hesai driver"

start_once "hesai_ros_driver_node" "Hesai driver" "$LOG_DIR/hesai_dashboard.log" "$PROJECT_DIR/scripts/run_hesai_driver_humble.sh"
sleep 2
start_once "xt16_fastlio_bridge.py" "XT16 bridge" "$LOG_DIR/xt16_bridge_dashboard.log" "$PROJECT_DIR/scripts/run_xt16_bridge_humble.sh"
sleep 2
start_once "fastlio_mapping" "FAST-LIO" "$LOG_DIR/fastlio_dashboard.log" "$PROJECT_DIR/scripts/run_hesai_fastlio_humble.sh"

sleep 3
if [[ "${ROBOT_SCOPE_START_STATIC_MAP:-0}" == "1" ]]; then
  start_once "nav2_map_server map_server" "static map server" "$LOG_DIR/map_server_dashboard.log" "$PROJECT_DIR/scripts/run_static_map_humble.sh"
  MAP_STATE="$(ros2 lifecycle get /map_server 2>/dev/null || true)"
  if [[ "$MAP_STATE" != *"active"* ]]; then
    [[ "$MAP_STATE" == *"unconfigured"* ]] && ros2 lifecycle set /map_server configure >/dev/null
    ros2 lifecycle set /map_server activate >/dev/null
  fi
fi

echo "[Robot Scope] Hesai + XT16 bridge + FAST-LIO processes started"
