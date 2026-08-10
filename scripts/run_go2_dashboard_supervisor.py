#!/usr/bin/env python3
"""Keep the offline dashboard available, then re-exec it on the Go2 LAN."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path


POLL_SECONDS = 0.05
CHILD_STOP_TIMEOUT_S = 20.0


def _executable(path: Path, label: str) -> str:
    if not path.is_file() or path.is_symlink() or not os.access(path, os.X_OK):
        raise RuntimeError(f"{label} is not a trusted executable file")
    return str(path)


def _stop_child(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=CHILD_STOP_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2.0)


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    runner = _executable(script_dir / "run_go2_humble.sh", "dashboard runner")
    waiter = _executable(
        script_dir / "wait_for_go2_interface.sh", "interface waiter"
    )

    check = subprocess.run([waiter, "--check"], check=False, timeout=5.0)
    if check.returncode == 0:
        os.execv(runner, [runner])
    if check.returncode != 1:
        return int(check.returncode or 2)

    print(
        "[Robot Scope] starting offline viewer while the Go2 interface is unavailable",
        flush=True,
    )
    stopping = threading.Event()

    def request_shutdown(_signum: int, _frame: object) -> None:
        stopping.set()

    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, request_shutdown)

    dashboard: subprocess.Popen[bytes] | None = None
    interface_waiter: subprocess.Popen[bytes] | None = None
    try:
        dashboard = subprocess.Popen([runner])
        interface_waiter = subprocess.Popen([waiter, "--wait"])
        while True:
            if stopping.is_set():
                _stop_child(interface_waiter)
                _stop_child(dashboard)
                return 0

            waiter_status = interface_waiter.poll()
            dashboard_status = dashboard.poll()
            if waiter_status is not None:
                if waiter_status != 0:
                    _stop_child(dashboard)
                    return int(waiter_status)
                print(
                    "[Robot Scope] Go2 interface became ready; "
                    "reinitializing the dashboard DDS participant",
                    flush=True,
                )
                _stop_child(dashboard)
                # systemd may request a stop/restart while the offline child is
                # draining.  A signal delivered to this supervisor must win
                # over the pending online transition; otherwise execv() would
                # start a fresh dashboard after the one service-stop signal.
                # Restore the default dispositions before the final Event
                # check.  Signals received before this point remain recorded;
                # signals received after it terminate this process (or its
                # exec() replacement) instead of being reduced to a stale flag.
                for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
                    signal.signal(signum, signal.SIG_DFL)
                if stopping.is_set():
                    _stop_child(interface_waiter)
                    return 0
                os.execv(runner, [runner])
            if dashboard_status is not None:
                _stop_child(interface_waiter)
                return int(dashboard_status)
            time.sleep(POLL_SECONDS)
    finally:
        # execv() never returns on a successful online transition.  Every
        # other exit path, including partial Popen failures and polling errors,
        # must reap both children so systemd never inherits an offline viewer
        # or waiter from a failed supervisor instance.
        for child in (interface_waiter, dashboard):
            if child is None:
                continue
            try:
                _stop_child(child)
            except (OSError, subprocess.SubprocessError) as exc:
                print(
                    f"Robot Scope child cleanup failed: {exc}",
                    file=sys.stderr,
                )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"Robot Scope dashboard supervisor failed: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
