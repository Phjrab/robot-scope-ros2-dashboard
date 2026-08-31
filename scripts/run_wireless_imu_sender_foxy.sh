#!/usr/bin/env bash
set -eo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"

source "$PROJECT_DIR/scripts/setup_go2_ros2_foxy.sh"
cd "$PROJECT_DIR"
exec /usr/bin/python3 "$PROJECT_DIR/scripts/wireless_imu_sender_foxy.py"
