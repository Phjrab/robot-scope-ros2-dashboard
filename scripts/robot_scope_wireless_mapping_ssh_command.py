#!/usr/bin/env python3
"""Restricted robot-side lifecycle/status command for wireless mapping inputs."""

from __future__ import annotations

import os
import re
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
_COUNT = r"[0-9]{1,20}"
_AGE = r"(?:none|[0-9]{1,6}\.[0-9]{3})"
_REJECTS = rf"(?:none|[a-z_]+:{_COUNT}(?:,[a-z_]+:{_COUNT})*)"
_RELAY_HEALTH_LINE = re.compile(
    rf"^\[Robot Scope wireless XT16 relay\] (?:periodic|final) "
    rf"captured={_COUNT} accepted={_COUNT} forwarded={_COUNT} "
    rf"bytes={_COUNT} send_errors={_COUNT} seq_lost={_COUNT} "
    rf"seq_duplicate={_COUNT} seq_reordered={_COUNT} "
    rf"last_accepted_age_s={_AGE} last_forwarded_age_s={_AGE} "
    rf"rejected={_COUNT}\({_REJECTS}\)$"
)


def _relay_health_lines(output: str) -> tuple[str, str] | None:
    lines = [
        line
        for line in output.splitlines()
        if len(line) <= 1024 and _RELAY_HEALTH_LINE.fullmatch(line)
    ]
    if len(lines) < 2:
        return None
    return lines[-2], lines[-1]


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
                "--since=-15s",
                "-n",
                "32",
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
    action = os.environ.get("SSH_ORIGINAL_COMMAND", "").strip()
    resolved = command_for(action)
    if resolved is None:
        return 2
    command, expose_stdout = resolved
    try:
        capture_health = action == "relay-health"
        completed = subprocess.run(
            command,
            shell=False,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=(
                subprocess.PIPE
                if capture_health
                else None if expose_stdout else subprocess.DEVNULL
            ),
            stderr=subprocess.DEVNULL,
            text=capture_health,
            timeout=5.0,
            env=FIXED_ENVIRONMENT,
        )
    except (OSError, subprocess.SubprocessError):
        return 1
    if capture_health:
        lines = _relay_health_lines(completed.stdout)
        if completed.returncode != 0 or lines is None:
            return 1
        print(*lines, sep="\n")
    return int(completed.returncode)


if __name__ == "__main__":
    sys.exit(main())
