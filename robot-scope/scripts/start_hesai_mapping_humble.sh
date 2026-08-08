#!/usr/bin/env bash
set -eo pipefail

PROJECT_DIR="${ROBOT_SCOPE_DIR:-$HOME/robot-scope}"
LOG_DIR="${ROBOT_SCOPE_MAPPING_LOG_DIR:-$HOME/ws/go2_3d}"
mkdir -p "$LOG_DIR"

start_once() {
  local pattern="$1"
  local label="$2"
  local log_file="$3"
  local command="$4"
  if pgrep -f "$pattern" >/dev/null; then
    echo "[Robot Scope] $label already running"
    return
  fi
  nohup "$command" > "$log_file" 2>&1 < /dev/null &
  echo "[Robot Scope] started $label"
}

start_once "hesai_ros_driver_node" "Hesai driver" "$LOG_DIR/hesai_dashboard.log" "$PROJECT_DIR/scripts/run_hesai_driver_humble.sh"
start_once "xt16_fastlio_bridge.py" "XT16 bridge" "$LOG_DIR/xt16_bridge_dashboard.log" "$PROJECT_DIR/scripts/run_xt16_bridge_humble.sh"
start_once "fastlio_mapping" "FAST-LIO" "$LOG_DIR/fastlio_dashboard.log" "$PROJECT_DIR/scripts/run_hesai_fastlio_humble.sh"
start_once "nav2_map_server map_server" "static map server" "$LOG_DIR/map_server_dashboard.log" "$PROJECT_DIR/scripts/run_static_map_humble.sh"

sleep 3
source /opt/ros/humble/setup.bash
source "$HOME/setup_go2_ros2_humble.sh"
MAP_STATE="$(ros2 lifecycle get /map_server 2>/dev/null || true)"
if [[ "$MAP_STATE" != *"active"* ]]; then
  [[ "$MAP_STATE" == *"unconfigured"* ]] && ros2 lifecycle set /map_server configure >/dev/null
  ros2 lifecycle set /map_server activate >/dev/null
fi

echo "[Robot Scope] Hesai + FAST-LIO + /map stack ready"
