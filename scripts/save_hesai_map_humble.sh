#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 2 ]]; then
  echo "usage: save_hesai_map_humble.sh OUTPUT_PREFIX {pcd|pcd-and-2d}" >&2
  exit 2
fi
if [[ "$2" != "pcd" && "$2" != "pcd-and-2d" ]]; then
  echo "usage: save_hesai_map_humble.sh OUTPUT_PREFIX {pcd|pcd-and-2d}" >&2
  exit 2
fi

OUTPUT_PREFIX="$(realpath -m -- "$1")"
SAVE_MODE="$2"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
WORKSPACE_ROOT="${ROBOT_SCOPE_WORKSPACE_ROOT:-$HOME}"
if [[ "$WORKSPACE_ROOT" != /* || "$WORKSPACE_ROOT" == "/" ]]; then
  echo "ROBOT_SCOPE_WORKSPACE_ROOT must be an absolute non-root path" >&2
  exit 2
fi
MAPS_DIR="$(realpath -m -- "${ROBOT_SCOPE_MAPS_DIR:-$WORKSPACE_ROOT/ws/go2_3d/maps}")"
JOBS_DIR="$MAPS_DIR/.robot_scope_jobs"
SAVE_SCRIPT="$PROJECT_DIR/scripts/save_map.py"
CONVERTER_SCRIPT="$PROJECT_DIR/scripts/convert_pcd_to_occupancy.py"

case "$OUTPUT_PREFIX" in
  "$JOBS_DIR"/*) ;;
  *) echo "refusing map output outside the private job directory" >&2; exit 2 ;;
esac
[[ -f "$SAVE_SCRIPT" ]] || { echo "repository FAST-LIO map saver is missing" >&2; exit 2; }
[[ -f "$CONVERTER_SCRIPT" ]] || { echo "repository PCD converter is missing" >&2; exit 2; }

# ROS 2 and colcon-generated setup files are not safe to source while Bash's
# nounset option is enabled (for example, they probe AMENT_TRACE_SETUP_FILES
# and COLCON_TRACE before those variables exist). Keep strict mode for this
# script, but suspend nounset only while importing trusted environment files.
set +u
source "$PROJECT_DIR/scripts/setup_go2_ros2_humble.sh"
set -u

echo "[Robot Scope] capturing the fresh /Laser_map snapshot"
/usr/bin/python3 "$SAVE_SCRIPT" "$OUTPUT_PREFIX.pcd"

if [[ "$SAVE_MODE" == "pcd" ]]; then
  exit 0
fi

RESOLUTION="0.05"
Z_MIN="-0.2"
Z_MAX="0.8"
PYTHON_BIN="/usr/bin/python3"
if [[ -x "$PROJECT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
fi
echo "[Robot Scope] converting PCD locally to a 0.05 m/cell occupancy map"
"$PYTHON_BIN" "$CONVERTER_SCRIPT" "$OUTPUT_PREFIX" \
  --resolution "$RESOLUTION" \
  --z-min "$Z_MIN" \
  --z-max "$Z_MAX" \
  --noise-radius 0.1 \
  --min-neighbors 10
echo "[Robot Scope] 3D PCD and 2D map saved"
