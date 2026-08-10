#!/usr/bin/env bash
set -eo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="${ROBOT_SCOPE_DIR:-$(dirname -- "$SCRIPT_DIR")}"
LOG_DIR="${ROBOT_SCOPE_MAPPING_LOG_DIR:-$HOME/ws/go2_3d}"
mkdir -p "$LOG_DIR"

# Fail before leaving detached ROS children behind when the robot/LiDAR cable
# is not ready.  This helper only selects the already-configured interface; it
# never adds addresses or invokes sudo from the dashboard.
source /opt/ros/humble/setup.bash
source "$HOME/setup_go2_ros2_humble.sh"

STARTED_PIDS=()
STARTED_IDENTITIES=()
STARTED_LABELS=()
PIPELINE_COMMITTED=0

process_identity() {
  local pid="$1"
  awk '{print $22}' "/proc/$pid/stat" 2>/dev/null || true
}

is_started_process_alive() {
  local index="$1"
  local pid="${STARTED_PIDS[$index]}"
  local expected_identity="${STARTED_IDENTITIES[$index]}"
  local current_identity
  local state
  current_identity="$(process_identity "$pid")"
  state="$(awk '{print $3}' "/proc/$pid/stat" 2>/dev/null || true)"
  [[ -n "$expected_identity" && "$current_identity" == "$expected_identity" && "$state" != "Z" ]]
}

signal_started_processes() {
  local signal="$1"
  local index
  for ((index=${#STARTED_PIDS[@]} - 1; index >= 0; index--)); do
    if is_started_process_alive "$index"; then
      kill "-$signal" "${STARTED_PIDS[$index]}" 2>/dev/null || true
    fi
  done
}

wait_for_started_processes() {
  local timeout_seconds="$1"
  local deadline=$((SECONDS + timeout_seconds))
  local index
  local alive
  while (( SECONDS < deadline )); do
    alive=0
    for ((index=0; index < ${#STARTED_PIDS[@]}; index++)); do
      if is_started_process_alive "$index"; then alive=1; fi
    done
    [[ "$alive" -eq 0 ]] && return 0
    sleep 0.2
  done
  return 1
}

cleanup_started_processes() {
  if [[ "${#STARTED_PIDS[@]}" -eq 0 ]]; then
    return
  fi
  echo "[Robot Scope] mapping startup failed; stopping only this launch's processes" >&2
  signal_started_processes INT
  if ! wait_for_started_processes 5; then
    signal_started_processes TERM
    wait_for_started_processes 2 || true
  fi
  if ! wait_for_started_processes 1; then
    signal_started_processes KILL
    wait_for_started_processes 1 || true
  fi
  local pid
  for pid in "${STARTED_PIDS[@]}"; do
    wait "$pid" 2>/dev/null || true
  done
}

on_exit() {
  local status="$?"
  trap - EXIT INT TERM
  if [[ "$PIPELINE_COMMITTED" -ne 1 ]]; then
    cleanup_started_processes
    [[ "$status" -eq 0 ]] && status=1
  fi
  exit "$status"
}

trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

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
  local pid="$!"
  local identity
  identity="$(process_identity "$pid")"
  if [[ -z "$identity" ]]; then
    wait "$pid" 2>/dev/null || true
    echo "[Robot Scope] $label failed before its process could be tracked" >&2
    return 1
  fi
  STARTED_PIDS+=("$pid")
  STARTED_IDENTITIES+=("$identity")
  STARTED_LABELS+=("$label")
  echo "[Robot Scope] started $label (pid $pid)"
}

# "새 맵 시작" is an explicit reset operation.  Stop only the fixed mapping
# components owned by this Unix user, then build a fresh FAST-LIO accumulator.
stop_existing "fastlio_mapping|ros2 launch fast_lio" "FAST-LIO"
stop_existing "xt16_fastlio_bridge.py" "XT16 bridge"
stop_existing "hesai_ros_driver_node" "Hesai driver"

start_once "hesai_ros_driver_node" "Hesai driver" "$LOG_DIR/hesai_dashboard.log" "$PROJECT_DIR/scripts/run_hesai_driver_humble.sh"
python3 "$PROJECT_DIR/scripts/check_xt16_lidar_ready.py" \
  --stage raw \
  --timeout "${ROBOT_SCOPE_XT16_RAW_READY_TIMEOUT_SECONDS:-15}"
start_once "xt16_fastlio_bridge.py" "XT16 bridge" "$LOG_DIR/xt16_bridge_dashboard.log" "$PROJECT_DIR/scripts/run_xt16_bridge_humble.sh"
python3 "$PROJECT_DIR/scripts/check_xt16_lidar_ready.py" \
  --stage bridge \
  --timeout "${ROBOT_SCOPE_XT16_BRIDGE_READY_TIMEOUT_SECONDS:-15}"
start_once "fastlio_mapping" "FAST-LIO" "$LOG_DIR/fastlio_dashboard.log" "$PROJECT_DIR/scripts/run_hesai_fastlio_humble.sh"
python3 "$PROJECT_DIR/scripts/check_xt16_lidar_ready.py" \
  --stage fastlio \
  --timeout "${ROBOT_SCOPE_FASTLIO_READY_TIMEOUT_SECONDS:-45}"
if [[ "${ROBOT_SCOPE_START_STATIC_MAP:-0}" == "1" ]]; then
  start_once "nav2_map_server map_server" "static map server" "$LOG_DIR/map_server_dashboard.log" "$PROJECT_DIR/scripts/run_static_map_humble.sh"
  MAP_STATE="$(ros2 lifecycle get /map_server 2>/dev/null || true)"
  if [[ "$MAP_STATE" != *"active"* ]]; then
    [[ "$MAP_STATE" == *"unconfigured"* ]] && ros2 lifecycle set /map_server configure >/dev/null
    ros2 lifecycle set /map_server activate >/dev/null
  fi
fi

PIPELINE_COMMITTED=1
echo "[Robot Scope] Hesai + XT16 bridge + FAST-LIO processes started"
