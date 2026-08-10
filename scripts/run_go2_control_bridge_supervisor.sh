#!/usr/bin/env bash
set -eo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
RUNNER="$SCRIPT_DIR/run_go2_control_bridge_humble.sh"
INTERFACE_WAITER="$SCRIPT_DIR/wait_for_go2_interface.sh"

if [[ ! -x "$RUNNER" || ! -x "$INTERFACE_WAITER" ]]; then
  echo "[Robot Scope] control runner or interface waiter is not executable" >&2
  exit 2
fi

# This wrapper is the service's main process, not an ExecStartPre command.
# Type=simple therefore reaches active immediately while no ROS participant or
# sport publisher exists. Once the exact dedicated link is ready, replace this
# process with the fail-closed bridge runner.
"$INTERFACE_WAITER" --wait
exec "$RUNNER"
