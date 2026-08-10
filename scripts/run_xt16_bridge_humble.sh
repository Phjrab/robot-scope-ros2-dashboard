#!/usr/bin/env bash
set -eo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
XT16_BRIDGE="$PROJECT_DIR/scripts/xt16_fastlio_bridge.py"
[[ -f "$XT16_BRIDGE" ]] || { echo "[Robot Scope] repository XT16 bridge is missing" >&2; exit 1; }

source "$PROJECT_DIR/scripts/setup_go2_ros2_humble.sh"

exec /usr/bin/python3 "$XT16_BRIDGE"
