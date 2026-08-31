#!/usr/bin/env python3
"""Restricted robot-side lifecycle/status command for wireless mapping inputs."""

from __future__ import annotations

import os
import subprocess
import sys


SYSTEMCTL = "/usr/bin/systemctl"
JOURNALCTL = "/usr/bin/journalctl"
TIMEDATECTL = "/usr/bin/timedatectl"
SUDO = "/usr/bin/sudo"
RELAY_SERVICE = "robot-scope-xt16-wireless-relay.service"
IMU_SERVICE = "robot-scope-wireless-imu-sender.service"
SERVICES = {"relay": RELAY_SERVICE, "imu": IMU_SERVICE}
FIXED_ENVIRONMENT = {
    "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
    "LANG": "C",
    "LC_ALL": "C",
}


def command_for(action: str) -> tuple[tuple[str, ...], bool] | None:
    if action == "clock-status":
        return (
            (TIMEDATECTL, "show", "--property=NTPSynchronized", "--value"),
            True,
        )
    if action == "relay-health":
        return (
            (
                SUDO,
                "-n",
                JOURNALCTL,
                "--no-pager",
                "-o",
                "cat",
                "--since=-12s",
                "-n",
                "2",
                "-u",
                RELAY_SERVICE,
            ),
            True,
        )
    for label, service in SERVICES.items():
        if action == f"{label}-status":
            return (
                (
                    SYSTEMCTL,
                    "show",
                    "--property=ActiveState",
                    "--property=SubState",
                    "--property=LoadState",
                    service,
                ),
                True,
            )
        if action == f"{label}-start":
            return ((SUDO, "-n", SYSTEMCTL, "--no-block", "start", service), False)
        if action == f"{label}-stop":
            return ((SUDO, "-n", SYSTEMCTL, "--no-block", "stop", service), False)
    return None


def main() -> int:
    resolved = command_for(os.environ.get("SSH_ORIGINAL_COMMAND", "").strip())
    if resolved is None:
        return 2
    command, expose_stdout = resolved
    try:
        completed = subprocess.run(
            command,
            shell=False,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=None if expose_stdout else subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5.0,
            env=FIXED_ENVIRONMENT,
        )
    except (OSError, subprocess.SubprocessError):
        return 1
    return int(completed.returncode)


if __name__ == "__main__":
    sys.exit(main())
