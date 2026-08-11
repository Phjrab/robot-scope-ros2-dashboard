#!/usr/bin/env bash
set -eo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
WORKSPACE_ROOT="${ROBOT_SCOPE_WORKSPACE_ROOT:-$HOME}"
LOG_DIR="${ROBOT_SCOPE_MAPPING_LOG_DIR:-$WORKSPACE_ROOT/ws/go2_3d}"
if [[ "$WORKSPACE_ROOT" != /* || "$WORKSPACE_ROOT" == "/" || "$LOG_DIR" != /* ]]; then
  echo "[Robot Scope] workspace and preview log paths must be absolute and safe" >&2
  exit 2
fi
mkdir -p "$LOG_DIR"

# This process is started only after the fixed Go2 interface is ready.  It
# owns the single local Hesai UDP receiver and the fixed-format conversion
# bridge for the complete dashboard lifetime; FAST-LIO is deliberately absent.
source "$PROJECT_DIR/scripts/setup_go2_ros2_humble.sh"

STARTED_PIDS=()
STARTED_IDENTITIES=()

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
  [[ "${#STARTED_PIDS[@]}" -eq 0 ]] && return
  signal_started_processes INT
  if ! wait_for_started_processes 4; then
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
  cleanup_started_processes
  exit "$status"
}

trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

refuse_existing_process() {
  local pattern="$1"
  local label="$2"
  local pids=()
  mapfile -t pids < <(pgrep -u "$(id -u)" -f -- "$pattern" || true)
  if [[ "${#pids[@]}" -gt 0 ]]; then
    echo "[Robot Scope] refused duplicate $label process: ${pids[*]}" >&2
    exit 1
  fi
}

start_owned_process() {
  local label="$1"
  local log_file="$2"
  local command="$3"
  "$command" > "$log_file" 2>&1 < /dev/null &
  local pid="$!"
  local identity
  identity="$(process_identity "$pid")"
  if [[ -z "$identity" ]]; then
    wait "$pid" 2>/dev/null || true
    echo "[Robot Scope] $label failed before it could be tracked" >&2
    exit 1
  fi
  STARTED_PIDS+=("$pid")
  STARTED_IDENTITIES+=("$identity")
  echo "[Robot Scope] started preview $label (pid $pid)"
}

refuse_existing_process "hesai_ros_driver_node" "Hesai driver"
refuse_existing_process "xt16_fastlio_bridge.py" "XT16 bridge"

start_owned_process \
  "Hesai driver" \
  "$LOG_DIR/hesai_preview.log" \
  "$PROJECT_DIR/scripts/run_hesai_driver_humble.sh"
sleep 1
if ! is_started_process_alive 0; then
  echo "[Robot Scope] Hesai preview driver exited during startup" >&2
  exit 1
fi

start_owned_process \
  "XT16 bridge" \
  "$LOG_DIR/xt16_preview_bridge.log" \
  "$PROJECT_DIR/scripts/run_xt16_bridge_humble.sh"
sleep 1
if ! is_started_process_alive 1; then
  echo "[Robot Scope] XT16 preview bridge exited during startup" >&2
  exit 1
fi

echo "[Robot Scope] XT16 preview running without FAST-LIO"
while true; do
  if ! is_started_process_alive 0 || ! is_started_process_alive 1; then
    echo "[Robot Scope] XT16 preview child exited unexpectedly" >&2
    exit 1
  fi
  sleep 0.5
done
