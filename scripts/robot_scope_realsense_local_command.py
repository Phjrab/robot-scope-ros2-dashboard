#!/usr/bin/env python3
"""Local entry point for the existing fixed RealSense profile/rollback helper.

Only status and the three approved resolutions are accepted. The executing
service user's private config is used; no host, path, or shell argument crosses
this interface. The existing helper retains its exact service and sudo policy.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


HELPER_PATH = Path(__file__).resolve().with_name("robot_scope_wireless_mapping_ssh_command.py")
ALLOWED_ACTIONS = frozenset({
    "realsense-profile-status", "realsense-profile-320x240",
    "realsense-profile-640x480", "realsense-profile-1280x720",
})


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1 or arguments[0] not in ALLOWED_ACTIONS:
        return 2
    spec = importlib.util.spec_from_file_location("_robot_scope_camera_profile", HELPER_PATH)
    if spec is None or spec.loader is None:
        return 1
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    helper.REALSENSE_ENV_FILE = Path.home() / ".config" / "robot-scope" / "realsense-camera.env"
    try:
        action = arguments[0]
        if action == "realsense-profile-status":
            result = helper._realsense_status()
        else:
            result = helper._apply_realsense_profile(action.removeprefix("realsense-profile-"))
        print(json.dumps(result, separators=(",", ":")))
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
