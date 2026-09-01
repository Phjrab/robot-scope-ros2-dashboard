#!/usr/bin/env bash
set -eo pipefail

if [[ "$#" -ne 0 ]]; then
  echo "[Robot Scope] wireless mapping launcher accepts no arguments" >&2
  exit 2
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
WORKSPACE_ROOT="${ROBOT_SCOPE_WORKSPACE_ROOT:-$HOME}"
LOG_DIR="${ROBOT_SCOPE_MAPPING_LOG_DIR:-$WORKSPACE_ROOT/ws/go2_3d}"
[[ "$WORKSPACE_ROOT" == /* && "$WORKSPACE_ROOT" != "/" && "$LOG_DIR" == /* ]] || {
  echo "[Robot Scope] wireless mapping paths are unsafe" >&2
  exit 69
}
mkdir -p -- "$LOG_DIR"

LOCAL_PIDS=()
LOCAL_IDENTITIES=()
LOCAL_LABELS=()
REMOTE_RELAY_STARTED=0
REMOTE_IMU_STARTED=0
FINAL_STATUS=0

process_identity() {
  awk '{print $22}' "/proc/$1/stat" 2>/dev/null || true
}

local_alive() {
  local index="$1"
  local pid="${LOCAL_PIDS[$index]}"
  local identity="${LOCAL_IDENTITIES[$index]}"
  local state
  state="$(awk '{print $3}' "/proc/$pid/stat" 2>/dev/null || true)"
  [[ -n "$identity" && "$(process_identity "$pid")" == "$identity" && "$state" != "Z" ]]
}

stop_local_children() {
  local signal="$1"
  local index
  for ((index=${#LOCAL_PIDS[@]} - 1; index >= 0; index--)); do
    local_alive "$index" && \
      kill "-$signal" -- "-${LOCAL_PIDS[$index]}" 2>/dev/null || true
  done
}

wait_local_children() {
  local deadline=$((SECONDS + $1))
  local index alive
  while (( SECONDS < deadline )); do
    alive=0
    for ((index=0; index < ${#LOCAL_PIDS[@]}; index++)); do
      local_alive "$index" && alive=1
    done
    [[ "$alive" -eq 0 ]] && return 0
    sleep 0.2
  done
  return 1
}

remote_lifecycle() {
  /usr/bin/python3 "$PROJECT_DIR/scripts/wireless_mapping_remote_lifecycle.py" "$@"
}

cleanup() {
  local incoming_status="$?"
  trap - EXIT INT TERM
  if [[ "$FINAL_STATUS" -eq 0 && "$incoming_status" -ne 0 ]]; then
    FINAL_STATUS="$incoming_status"
  fi
  stop_local_children INT
  if ! wait_local_children 5; then
    stop_local_children TERM
    wait_local_children 2 || true
  fi
  if ! wait_local_children 1; then
    stop_local_children KILL
    wait_local_children 1 || true
  fi
  local pid
  for pid in "${LOCAL_PIDS[@]}"; do wait "$pid" 2>/dev/null || true; done
  if [[ "$REMOTE_IMU_STARTED" -eq 1 ]]; then
    remote_lifecycle --service imu --action stop >/dev/null 2>&1 || true
  fi
  if [[ "$REMOTE_RELAY_STARTED" -eq 1 ]]; then
    remote_lifecycle --service relay --action stop >/dev/null 2>&1 || true
  fi
  exit "$FINAL_STATUS"
}

trap cleanup EXIT
trap 'FINAL_STATUS=130; exit 130' INT
trap 'FINAL_STATUS=143; exit 143' TERM

fail() {
  FINAL_STATUS="$1"
  echo "[Robot Scope] $2" >&2
  exit "$FINAL_STATUS"
}

start_local() {
  local label="$1"
  local log_file="$2"
  local command="$3"
  /usr/bin/setsid -- "$command" >"$log_file" 2>&1 < /dev/null &
  local pid="$!"
  local identity
  identity="$(process_identity "$pid")"
  [[ -n "$identity" ]] || fail 69 "WIRELESS MAPPING PREFLIGHT BLOCKED"
  LOCAL_PIDS+=("$pid")
  LOCAL_IDENTITIES+=("$identity")
  LOCAL_LABELS+=("$label")
  echo "[Robot Scope] started wireless mapping $label"
}

/usr/bin/python3 "$PROJECT_DIR/scripts/check_wireless_mapping_preflight.py" --stage host || exit "$?"
source "$PROJECT_DIR/scripts/setup_wireless_mapping_ros2_humble.sh" || \
  fail 69 "WIRELESS MAPPING PREFLIGHT BLOCKED"

relay_state="$(remote_lifecycle --service relay --action ensure-started)" || \
  fail 61 "WIRELESS XT16 RELAY OFFLINE"
[[ "$relay_state" == "started" ]] && REMOTE_RELAY_STARTED=1

/usr/bin/python3 "$PROJECT_DIR/scripts/check_wireless_mapping_preflight.py" --stage relay-service || \
  fail 61 "WIRELESS XT16 RELAY OFFLINE"

imu_state="$(remote_lifecycle --service imu --action ensure-started)" || \
  fail 64 "WIRELESS IMU UNAUTHENTICATED"
[[ "$imu_state" == "started" ]] && REMOTE_IMU_STARTED=1
/usr/bin/python3 "$PROJECT_DIR/scripts/check_wireless_mapping_preflight.py" --stage imu-service || \
  fail 64 "WIRELESS IMU UNAUTHENTICATED"

start_local "IMU receiver" "$LOG_DIR/wireless_imu_receiver.log" \
  "$PROJECT_DIR/scripts/run_wireless_imu_receiver_humble.sh"
/usr/bin/python3 "$PROJECT_DIR/scripts/check_xt16_lidar_ready.py" --stage imu \
  --timeout "${ROBOT_SCOPE_WIRELESS_IMU_READY_TIMEOUT_SECONDS:-15}" || \
  fail 64 "WIRELESS IMU UNAUTHENTICATED"

start_local "Hesai driver" "$LOG_DIR/wireless_hesai_driver.log" \
  "$PROJECT_DIR/scripts/run_hesai_driver_wireless_humble.sh"
/usr/bin/python3 "$PROJECT_DIR/scripts/check_xt16_lidar_ready.py" --stage raw \
  --timeout "${ROBOT_SCOPE_WIRELESS_HESAI_READY_TIMEOUT_SECONDS:-20}" || \
  fail 63 "HESAI DRIVER WAITING"

# A connected relay socket can receive ICMP port-unreachable errors until the
# fixed Hesai consumer binds UDP 2368. Require two advancing, error-stable
# post-bind reports before any converted cloud is accepted.
relay_ready=0
for _ in {1..8}; do
  if /usr/bin/python3 "$PROJECT_DIR/scripts/check_wireless_mapping_preflight.py" --stage relay; then
    relay_ready=1
    break
  fi
  sleep 2
done
[[ "$relay_ready" -eq 1 ]] || fail 62 "XT16 PACKETS STALE"

start_local "cloud bridge" "$LOG_DIR/wireless_cloud_bridge.log" \
  "$PROJECT_DIR/scripts/run_xt16_cloud_bridge_humble.sh"
/usr/bin/python3 "$PROJECT_DIR/scripts/check_xt16_lidar_ready.py" --stage bridge \
  --timeout "${ROBOT_SCOPE_WIRELESS_CLOUD_READY_TIMEOUT_SECONDS:-20}" || \
  fail 67 "CLOUD BRIDGE STALE"

start_local "FAST-LIO" "$LOG_DIR/wireless_fastlio.log" \
  "$PROJECT_DIR/scripts/run_hesai_fastlio_wireless_humble.sh"
/usr/bin/python3 "$PROJECT_DIR/scripts/check_xt16_lidar_ready.py" --stage fastlio \
  --timeout "${ROBOT_SCOPE_WIRELESS_FASTLIO_READY_TIMEOUT_SECONDS:-45}" || \
  fail 68 "FAST-LIO NOT READY"

echo "[Robot Scope] wireless XT16 mapping readiness verified"

next_remote_check=$((SECONDS + 5))
while true; do
  for ((index=0; index < ${#LOCAL_PIDS[@]}; index++)); do
    if ! local_alive "$index"; then
      case "${LOCAL_LABELS[$index]}" in
        "IMU receiver") fail 65 "IMU STALE" ;;
        "Hesai driver") fail 63 "HESAI DRIVER WAITING" ;;
        "cloud bridge") fail 67 "CLOUD BRIDGE STALE" ;;
        "FAST-LIO") fail 68 "FAST-LIO NOT READY" ;;
      esac
    fi
  done
  if (( SECONDS >= next_remote_check )); then
    /usr/bin/python3 "$PROJECT_DIR/scripts/check_wireless_mapping_preflight.py" --stage relay >/dev/null || \
      fail 62 "XT16 PACKETS STALE"
    /usr/bin/python3 "$PROJECT_DIR/scripts/check_wireless_mapping_preflight.py" --stage imu-service >/dev/null || \
      fail 65 "IMU STALE"
    next_remote_check=$((SECONDS + 5))
  fi
  sleep 0.5
done
