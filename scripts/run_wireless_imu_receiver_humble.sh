#!/usr/bin/env bash
set -eo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"

source "$PROJECT_DIR/scripts/setup_wireless_mapping_ros2_humble.sh"
cd "$PROJECT_DIR"
exec /usr/bin/python3 "$PROJECT_DIR/scripts/wireless_imu_receiver_humble.py"
