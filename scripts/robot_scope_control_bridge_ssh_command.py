#!/usr/bin/env python3
"""Restricted SSH command for the robot-side Control Bridge service."""

from __future__ import annotations

import os
import subprocess
import sys


SERVICE_NAME = "robot-scope-control-bridge.service"
SYSTEMCTL = "/usr/bin/systemctl"
SUDO = "/usr/bin/sudo"
STATUS_COMMAND = (
    SYSTEMCTL,
    "show",
    "--property=ActiveState",
    "--property=SubState",
    "--property=InvocationID",
    "--property=LoadState",
    "--property=UnitFileState",
    SERVICE_NAME,
)
MUTATION_COMMANDS = {
    "start": (SUDO, "-n", SYSTEMCTL, "--no-block", "start", SERVICE_NAME),
    "stop": (SUDO, "-n", SYSTEMCTL, "--no-block", "stop", SERVICE_NAME),
}
FIXED_ENVIRONMENT = {
    "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
    "LANG": "C",
    "LC_ALL": "C",
}


def main() -> int:
    action = os.environ.get("SSH_ORIGINAL_COMMAND", "").strip()
    if action == "status":
        command = STATUS_COMMAND
        stdout = None
    elif action in MUTATION_COMMANDS:
        command = MUTATION_COMMANDS[action]
        stdout = subprocess.DEVNULL
    else:
        return 2
    try:
        completed = subprocess.run(
            command,
            shell=False,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=subprocess.DEVNULL,
            timeout=5.0,
            env=FIXED_ENVIRONMENT,
        )
    except (OSError, subprocess.SubprocessError):
        return 1
    return int(completed.returncode)


if __name__ == "__main__":
    sys.exit(main())
