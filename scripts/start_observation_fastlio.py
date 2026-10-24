#!/usr/bin/env python3
"""Entry point for the fixed systemd unit, with private FAST-LIO output mounts."""

from __future__ import annotations

import os
from pathlib import Path
import re
import sys


def existing_fastlio(proc: Path = Path("/proc")) -> bool:
    if not proc.is_dir():
        raise RuntimeError("Linux process inspection is unavailable")
    for candidate in proc.iterdir():
        if not candidate.name.isdigit():
            continue
        try:
            argv = (candidate / "cmdline").read_bytes().split(b"\0")
        except FileNotFoundError:
            continue
        except PermissionError as exc:
            raise RuntimeError("process ownership inspection is unavailable") from exc
        if any(arg.rsplit(b"/", 1)[-1] == b"fastlio_mapping" for arg in argv):
            return True
    return False


def prepare_outputs(state: Path, fastlio: Path, invocation: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", invocation):
        raise RuntimeError("systemd invocation identity is required")
    # Verify both bind mounts before touching any file. An ordinary/manual
    # invocation cannot write into FAST-LIO's original compiled-in Log/PCD.
    for source, target in (("log", "Log"), ("pcd", "PCD")):
        private, compiled = state / source, fastlio / target
        if (
            private.is_symlink()
            or compiled.is_symlink()
            or not private.is_dir()
            or not compiled.is_dir()
            or not os.path.samefile(private, compiled)
        ):
            raise RuntimeError("private FAST-LIO output mounts are required")
    session = state / "sessions" / invocation
    session.mkdir(parents=True, exist_ok=False)
    # Keep all previous observation output; never overwrite it on a new start.
    for name in ("log", "pcd"):
        archive = session / ("previous-" + name)
        archive.mkdir()
        for item in (state / name).iterdir():
            item.rename(archive / item.name)
    ros_log = session / "ros"
    ros_log.mkdir()
    return ros_log


def main() -> None:
    if len(sys.argv) != 1:
        raise RuntimeError("observation service accepts no arguments")
    if existing_fastlio():
        raise RuntimeError("existing FAST-LIO detected; refusing duplicate start")
    workspace = Path(os.environ["ROBOT_SCOPE_WORKSPACE_ROOT"])
    if not workspace.is_absolute() or workspace == Path("/"):
        raise RuntimeError("invalid workspace")
    logs = prepare_outputs(
        Path("/var/lib/robot-scope-observation"),
        workspace / "ws/fastlio_ws/src/FAST_LIO",
        os.environ.get("INVOCATION_ID", ""),
    )
    os.environ["ROS_LOG_DIR"] = str(logs)
    os.environ["ROBOT_SCOPE_FASTLIO_OBSERVATION_ONLY"] = "1"
    command = Path(__file__).resolve().parent / "run_hesai_fastlio_humble.sh"
    os.execv(str(command), [str(command)])


if __name__ == "__main__":
    main()
