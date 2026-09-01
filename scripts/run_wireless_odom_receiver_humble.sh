#!/usr/bin/env bash
set -eo pipefail

[[ "$#" -eq 0 ]] || { echo "[Robot Scope] wireless odometry receiver accepts no arguments" >&2; exit 2; }
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
source "$PROJECT_DIR/scripts/setup_wireless_mapping_ros2_humble.sh"
cd "$PROJECT_DIR"
exec /usr/bin/python3 "$PROJECT_DIR/scripts/wireless_odom_receiver_humble.py"
