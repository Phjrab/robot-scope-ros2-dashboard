#!/usr/bin/env bash
set -eo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="${ROBOT_SCOPE_DIR:-$(dirname -- "$SCRIPT_DIR")}"

if [[ "${ROBOT_SCOPE_CONTROL_ENABLED:-0}" != "1" ]]; then
  echo "[Robot Scope] signed transport is disabled" >&2
  exit 2
fi
if [[ "${ROBOT_SCOPE_C4C_OBSERVATION_ONLY:-0}" != "1" ]]; then
  echo "[Robot Scope] C4C observation-only mode requires explicit opt-in" >&2
  exit 2
fi
if [[ "${ROBOT_SCOPE_CONTROL_TRANSPORT:-}" != "udp" ]]; then
  echo "[Robot Scope] robot-side observer requires the fixed udp transport" >&2
  exit 2
fi
if [[ "${#ROBOT_SCOPE_CONTROL_BRIDGE_KEY}" -lt 32 ]]; then
  echo "[Robot Scope] signed transport key must contain at least 32 characters" >&2
  exit 2
fi

source "$PROJECT_DIR/scripts/setup_go2_ros2_foxy.sh"

cd "$PROJECT_DIR"
exec python3 -m robot_dashboard.go2_control_bridge \
  --profile "$PROJECT_DIR/config/go2.json" \
  --observation-only
