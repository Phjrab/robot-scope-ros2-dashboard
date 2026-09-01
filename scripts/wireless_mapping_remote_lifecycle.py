#!/usr/bin/env python3
"""Start/stop only fixed robot-side wireless observation services."""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Sequence

from check_wireless_mapping_preflight import _service_active, remote_command


SERVICES = ("relay", "imu", "odom")


def ensure_started(service: str, environment: dict[str, str]) -> str:
    status = remote_command(f"{service}-status", environment=environment)
    if status.returncode == 0 and _service_active(status.stdout):
        return "existing"
    started = remote_command(f"{service}-start", environment=environment)
    if started.returncode != 0:
        raise RuntimeError("fixed remote service start failed")
    for _ in range(20):
        time.sleep(0.25)
        status = remote_command(f"{service}-status", environment=environment)
        if status.returncode == 0 and _service_active(status.stdout):
            return "started"
    remote_command(f"{service}-stop", environment=environment)
    raise RuntimeError("fixed remote service did not become active")


def stop(service: str, environment: dict[str, str]) -> None:
    stopped = remote_command(f"{service}-stop", environment=environment)
    if stopped.returncode != 0:
        raise RuntimeError("fixed remote service stop failed")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", required=True, choices=SERVICES)
    parser.add_argument("--action", required=True, choices=("ensure-started", "stop"))
    options = parser.parse_args(argv)
    try:
        if options.action == "ensure-started":
            print(ensure_started(options.service, dict(os.environ)))
        else:
            stop(options.service, dict(os.environ))
    except (OSError, RuntimeError):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
