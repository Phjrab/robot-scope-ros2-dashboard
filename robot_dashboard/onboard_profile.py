"""Keep the explicit onboard profile consistent across local child processes."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import MutableMapping


ONBOARD_PROFILE = "go2-onboard"
ROBOT_PROFILE_PATH_ENV = "ROBOT_SCOPE_ROBOT_PROFILE_PATH"
ONBOARD_ENVIRONMENT_DEFAULTS = {
    "ROBOT_SCOPE_GO2_INTERFACE": "eth0",
    "ROBOT_SCOPE_GO2_INTERFACE_CIDR": "192.168.123.18/24",
    "ROBOT_SCOPE_CONTROL_TRANSPORT": "ros",
    "ROBOT_SCOPE_CONTROL_BRIDGE_LIFECYCLE_TRANSPORT": "local",
    "ROBOT_SCOPE_REALSENSE_PROFILE_LIFECYCLE_MODE": "local",
    "ROBOT_SCOPE_FASTLIO_DDS_MODE": "direct",
}
ONBOARD_REQUIRED_ENVIRONMENT = {
    "ROS_DISTRO": "humble",
    "RMW_IMPLEMENTATION": "rmw_cyclonedds_cpp",
    "ROS_LOCALHOST_ONLY": "0",
    "ROBOT_SCOPE_CONTROL_TRANSPORT": "ros",
    "ROBOT_SCOPE_CONTROL_BRIDGE_LIFECYCLE_TRANSPORT": "local",
    "ROBOT_SCOPE_REALSENSE_PROFILE_LIFECYCLE_MODE": "local",
    "ROBOT_SCOPE_FASTLIO_DDS_MODE": "direct",
}


def configure_onboard_profile(
    mapping_profile: str,
    profile_path: str,
    *,
    project_dir: Path,
    environment: MutableMapping[str, str],
) -> str:
    """Select one trusted Go2 profile without weakening any motion interlock.

    An explicit CLI/environment disagreement is an error. Export the chosen
    mapping profile so its existing direct sensor/map/navigation launchers
    cannot accidentally fall back to the historical wired default.
    """

    configured = environment.get("ROBOT_SCOPE_MAPPING_PROFILE", "").strip()
    if ONBOARD_PROFILE not in {mapping_profile, configured}:
        return profile_path
    if mapping_profile != ONBOARD_PROFILE or configured not in {"", ONBOARD_PROFILE}:
        raise ValueError("go2-onboard mapping profile conflicts with the startup environment")
    for key, expected in ONBOARD_REQUIRED_ENVIRONMENT.items():
        if environment.get(key, expected).strip() != expected:
            raise ValueError(f"go2-onboard requires {key}={expected}")

    supplied_path = environment.get(ROBOT_PROFILE_PATH_ENV, "").strip()
    if profile_path and supplied_path and Path(profile_path) != Path(supplied_path):
        raise ValueError("go2-onboard robot profile conflicts with the startup environment")
    path = Path(profile_path or supplied_path or project_dir / "config" / "go2-onboard.json")
    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise ValueError("go2-onboard robot profile must be an absolute regular non-symlink file")
    profile = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(profile, dict) or profile.get("robot_type") != "go2":
        raise ValueError("go2-onboard robot profile must describe Go2")

    environment["ROBOT_SCOPE_MAPPING_PROFILE"] = ONBOARD_PROFILE
    environment[ROBOT_PROFILE_PATH_ENV] = str(path)
    for key, default in ONBOARD_ENVIRONMENT_DEFAULTS.items():
        if not environment.get(key, "").strip():
            environment[key] = default
    if not environment.get("ROBOT_SCOPE_CAMERA_INTERFACE", "").strip():
        environment["ROBOT_SCOPE_CAMERA_INTERFACE"] = environment["ROBOT_SCOPE_GO2_INTERFACE"]
    return str(path)


def configure_onboard_arguments(arguments: object) -> None:
    """Apply the selected startup contract to parsed dashboard arguments."""

    arguments.profile = configure_onboard_profile(
        arguments.mapping_profile,
        arguments.profile,
        project_dir=Path(__file__).resolve().parents[1],
        environment=os.environ,
    )
