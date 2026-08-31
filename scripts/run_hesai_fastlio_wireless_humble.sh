#!/usr/bin/env bash
set -eo pipefail

if [[ "$#" -ne 0 ]]; then
  echo "[Robot Scope] wireless FAST-LIO accepts no arguments" >&2
  exit 2
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
export ROBOT_SCOPE_GO2_INTERFACE="eno1"
export ROBOT_SCOPE_GO2_INTERFACE_CIDR="192.168.50.10/24"
exec "$PROJECT_DIR/scripts/run_hesai_fastlio_humble.sh"
