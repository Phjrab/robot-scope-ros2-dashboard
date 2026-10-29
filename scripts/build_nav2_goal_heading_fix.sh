#!/usr/bin/env bash
# Build/test only. Never select the overlay, restart a service, or send a goal.
set -euo pipefail
if [[ "$#" -ne 2 || "$1" != /* || "$2" != /* || -e "$2" ]]; then
  echo "usage: build_nav2_goal_heading_fix.sh ABSOLUTE_VERIFIED_SOURCE_CACHE NEW_ABSOLUTE_OUTPUT" >&2
  exit 2
fi
HEADING_CACHE="$1"
HEADING_OUTPUT="$2"
HEADING_PROJECT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
HEADING_SOURCE="$HEADING_PROJECT/ros2/nav2_goal_heading_fix"
mkdir -m 700 -p "$HEADING_OUTPUT"
python3 "$HEADING_SOURCE/prepare.py" --cache "$HEADING_CACHE" --destination "$HEADING_OUTPUT/fixed"
python3 "$HEADING_SOURCE/prepare.py" --cache "$HEADING_CACHE" --destination "$HEADING_OUTPUT/tf-only" --tf-only
# Do not mix an experimental controller overlay into this build.
unset AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH PYTHONPATH
unset RMW_IMPLEMENTATION CYCLONEDDS_URI FASTRTPS_DEFAULT_PROFILES_FILE
set +u
source /opt/ros/humble/setup.bash
set -u
export ROS_DOMAIN_ID=187 ROS_LOCALHOST_ONLY=1 ROS_LOG_DIR="$HEADING_OUTPUT/ros-logs"
cmake -S "$HEADING_OUTPUT/fixed/nav2_rotation_shim_controller" -B "$HEADING_OUTPUT/build" \
  -DCMAKE_INSTALL_PREFIX="$HEADING_OUTPUT/install" -DBUILD_TESTING=OFF -DPYTHON_EXECUTABLE=/usr/bin/python3
cmake --build "$HEADING_OUTPUT/build" -j2
cmake --install "$HEADING_OUTPUT/build"
cmake -S "$HEADING_SOURCE" -B "$HEADING_OUTPUT/tests" \
  -DUPSTREAM_DIR="$HEADING_CACHE" -DPATCHED_DIR="$HEADING_OUTPUT/fixed" \
  -DTF_ONLY_DIR="$HEADING_OUTPUT/tf-only" -DPYTHON_EXECUTABLE=/usr/bin/python3 \
  -DCANDIDATE_LIBRARY="$HEADING_OUTPUT/install/lib/libnav2_rotation_shim_controller.so"
cmake --build "$HEADING_OUTPUT/tests" -j2
ctest --test-dir "$HEADING_OUTPUT/tests" --output-on-failure
python3 - "$HEADING_PROJECT" "$HEADING_OUTPUT/install" <<'PY'
import hashlib,json,sys
from pathlib import Path
project,prefix=map(Path,sys.argv[1:])
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
patches=project/'ros2/nav2_goal_heading_fix'
receipt={'schema':'robot-scope.nav2-heading-overlay.v1','nav2_version':'1.1.20',
 'patch_files':{n:sha(patches/n) for n in ['same-time-goal.patch','final-rotation-collision.patch','common_time.hpp']},
 'base_library_sha256':sha(Path('/opt/ros/humble/lib/libnav2_rotation_shim_controller.so')),
 'installed_files':{n:sha(prefix/n) for n in ['lib/libnav2_rotation_shim_controller.so','share/nav2_rotation_shim_controller/nav2_rotation_shim_controller.xml','share/nav2_rotation_shim_controller/package.xml']},
 'native_tests_passed':True}
(prefix/'robot-scope-heading-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
PY
python3 "$HEADING_PROJECT/scripts/check_nav2_heading_overlay.py" --overlay "$HEADING_OUTPUT/install"
