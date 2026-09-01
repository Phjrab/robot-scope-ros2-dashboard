#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
source "$PROJECT_DIR/scripts/setup_competition_pdf_direct_humble.sh"
/usr/bin/python3 "$PROJECT_DIR/scripts/check_competition_direct_preflight.py" \
  --stage base
export ROBOT_SCOPE_HESAI_DRIVER_RUNNER="$PROJECT_DIR/scripts/run_hesai_driver_competition_direct_humble.sh"
exec "$PROJECT_DIR/scripts/start_xt16_preview_humble.sh"
