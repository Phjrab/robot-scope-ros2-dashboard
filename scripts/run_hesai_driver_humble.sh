#!/usr/bin/env bash
set -eo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
source "$SCRIPT_DIR/apply_go2_onboard_contract.sh"
HESAI_CONFIG="$PROJECT_DIR/config/hesai_xt16.yaml"
if [[ "${ROBOT_SCOPE_MAPPING_PROFILE:-}" == "go2-onboard" ]]; then
  HESAI_CONFIG="$PROJECT_DIR/config/hesai_xt16_onboard.yaml"
fi
HESAI_CONFIG="${ROBOT_SCOPE_HESAI_CONFIG_PATH:-$HESAI_CONFIG}"
[[ "$HESAI_CONFIG" == /* && -f "$HESAI_CONFIG" && ! -L "$HESAI_CONFIG" ]] || {
  echo "[Robot Scope] Hesai config must be an absolute regular non-symlink file" >&2
  exit 1
}
if [[ "${ROBOT_SCOPE_MAPPING_PROFILE:-}" == "go2-onboard" ]]; then
  python3 "$PROJECT_DIR/scripts/hesai_calibration_manifest.py" validate
fi

source "$PROJECT_DIR/scripts/setup_go2_ros2_humble.sh"
source "$ROBOT_SCOPE_WORKSPACE_ROOT/ws/hesai_ws/install/setup.bash"

if [[ "${ROBOT_SCOPE_MAPPING_PROFILE:-}" == "go2-onboard" ]]; then
  # Keep sensor-NIC discovery multicast, but send the large raw cloud payload
  # by unicast. Keep this setting local to the driver participant.
  CYCLONEDDS_URI="$(python3 - <<'PY'
import os
import xml.etree.ElementTree as ET

root = ET.fromstring(os.environ["CYCLONEDDS_URI"])
general = root.find("Domain/General")
if general is None:
    raise SystemExit("onboard Hesai requires the selected CycloneDDS General configuration")
multicast = general.find("AllowMulticast")
if multicast is None:
    multicast = ET.SubElement(general, "AllowMulticast")
multicast.text = "spdp"
print(ET.tostring(root, encoding="unicode"))
PY
)"
  export CYCLONEDDS_URI
fi

exec ros2 run hesai_ros_driver hesai_ros_driver_node \
  --ros-args -p config_path:="$HESAI_CONFIG"
