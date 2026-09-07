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
case "${ROBOT_SCOPE_D2_STATIONARY_RELOCALIZATION:-0}" in
  1)
    # D2 retains the fixed 0.15 m query voxel and 500-point acceptance gate.
    # Request the dense registered scan only for the explicit D2 runtime so
    # the query is not pre-thinned by FAST-LIO's normal visualization output.
    export ROBOT_SCOPE_FASTLIO_CONFIG_FILE="fastlio_xt16_d2_relocalization.yaml"
    ;;
  0|"")
    unset ROBOT_SCOPE_FASTLIO_CONFIG_FILE
    ;;
  *)
    echo "[Robot Scope] invalid D2 relocalization opt-in" >&2
    exit 2
    ;;
esac
exec "$PROJECT_DIR/scripts/run_hesai_fastlio_humble.sh"
