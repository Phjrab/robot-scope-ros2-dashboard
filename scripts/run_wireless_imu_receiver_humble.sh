#!/usr/bin/env bash
set -eo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"

source /opt/ros/humble/setup.bash
cd "$PROJECT_DIR"
exec /usr/bin/python3 "$PROJECT_DIR/scripts/wireless_imu_receiver_humble.py"
