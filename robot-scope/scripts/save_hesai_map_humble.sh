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
PROJECT_DIR="${ROBOT_SCOPE_DIR:-$HOME/robot-scope}"
MAPS_DIR="$(realpath -m -- "${ROBOT_SCOPE_MAPS_DIR:-$HOME/ws/go2_3d/maps}")"
JOBS_DIR="$MAPS_DIR/.robot_scope_jobs"
SAVE_SCRIPT="$HOME/ws/go2_3d/save_map.py"

case "$OUTPUT_PREFIX" in
  "$JOBS_DIR"/*) ;;
  *) echo "refusing map output outside the private job directory" >&2; exit 2 ;;
esac
[[ -f "$SAVE_SCRIPT" ]] || { echo "FAST-LIO map saver is not installed" >&2; exit 2; }

source /opt/ros/humble/setup.bash
source "$HOME/unitree_ros2/cyclonedds_ws/install/setup.bash"
source "$HOME/setup_go2_ros2_humble.sh"

echo "[Robot Scope] capturing the fresh /Laser_map snapshot"
/usr/bin/python3 "$SAVE_SCRIPT" "$OUTPUT_PREFIX.pcd"

if [[ "$SAVE_MODE" == "pcd" ]]; then
  exit 0
fi

RESOLUTION="0.05"
Z_MIN="-0.2"
Z_MAX="0.8"
"$PROJECT_DIR/scripts/check_pcd_bounds.py" "$OUTPUT_PREFIX.pcd" \
  --resolution "$RESOLUTION" --z-min "$Z_MIN" --z-max "$Z_MAX" --max-cells 16000000

# The conversion is intentionally local-only and uses a job-specific topic so
# it cannot collide with the archived /map server or another ROS machine.
unset AMENT_PREFIX_PATH COLCON_PREFIX_PATH CMAKE_PREFIX_PATH PYTHONPATH
unset CYCLONEDDS_URI
source /opt/ros/humble/setup.bash
source "$HOME/ws/install/setup.bash"
export ROS_LOCALHOST_ONLY=1

JOB_TOKEN="$(basename "$(dirname "$OUTPUT_PREFIX")" | tr '-' '_')"
MAP_TOPIC="/robot_scope/conversion/${JOB_TOKEN}/map"
NODE_NAME="robot_scope_pcd2pgm_${JOB_TOKEN}"
CONVERTER_PID=""
cleanup() {
  if [[ -n "$CONVERTER_PID" ]] && kill -0 "$CONVERTER_PID" 2>/dev/null; then
    kill -INT "$CONVERTER_PID" 2>/dev/null || true
    wait "$CONVERTER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

ros2 run pcd2pgm pcd2pgm_node --ros-args \
  -r "__node:=$NODE_NAME" \
  -p "pcd_file:=$OUTPUT_PREFIX.pcd" \
  -p "map_topic_name:=$MAP_TOPIC" \
  -p flag_pass_through:=false \
  -p "thre_z_min:=$Z_MIN" \
  -p "thre_z_max:=$Z_MAX" \
  -p "map_resolution:=$RESOLUTION" \
  -p thre_radius:=0.1 \
  -p thres_point_count:=10 &
CONVERTER_PID="$!"

echo "[Robot Scope] converting PCD to a 0.05 m/cell occupancy map"
/usr/bin/timeout --signal=INT 35s ros2 run nav2_map_server map_saver_cli \
  -t "$MAP_TOPIC" -f "$OUTPUT_PREFIX" --fmt pgm --mode trinary --occ 0.65 --free 0.25
cleanup
trap - EXIT INT TERM
echo "[Robot Scope] 3D PCD and 2D map saved"
