#!/usr/bin/env python3
"""Read-only, fixed-device ownership probe for the unprivileged SLAM broker.

Install a reviewed root-owned copy and root-owned configuration. This service
never opens the camera, starts/stops a producer, or accepts device paths from a
request. Run with host /proc visibility; an incomplete observation fails closed.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import errno
import json
import math
import os
from pathlib import Path
import re
import signal
import socket
import socketserver
import stat
import struct
import threading
import time


def _root_owned(info, *, directory: bool = False) -> None:
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if not kind(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise ValueError("protected root-owned path required")


def _root_directory(path: Path) -> int:
    """Walk protected directories without following any replaceable symlink."""
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("absolute protected path required")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    descriptor = os.open("/", flags)
    try:
        _root_owned(os.fstat(descriptor), directory=True)
        for name in path.parts[1:]:
            child = os.open(name, flags, dir_fd=descriptor)
            try:
                _root_owned(os.fstat(child), directory=True)
            except BaseException:
                os.close(child)
                raise
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _protected_bytes(path: Path, limit: int) -> bytes:
    parent = _root_directory(path.parent)
    try:
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                             dir_fd=parent)
        with os.fdopen(descriptor, "rb") as source:
            info = os.fstat(source.fileno())
            _root_owned(info)
            if info.st_size > limit:
                raise ValueError("protected file exceeds limit")
            content = source.read(limit + 1)
            if len(content) > limit:
                raise ValueError("protected file exceeds limit")
            return content
    finally:
        os.close(parent)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _json(content: bytes):
    return json.loads(content, object_pairs_hook=_unique_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("finite JSON required")))


def load_configuration(path: Path) -> dict:
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("canonical configuration required")
    config = _json(_protected_bytes(path, 8192))
    if (not isinstance(config, dict) or set(config) != {"schema_version", "uid", "devices", "socket"}
            or type(config["schema_version"]) is not int or config["schema_version"] != 1
            or type(config["uid"]) is not int or not 1 <= config["uid"] < 2**31
            or not isinstance(config["devices"], list) or not 1 <= len(config["devices"]) <= 16
            or any(not isinstance(item, str) or not re.fullmatch(
                r"/dev/(?:video[0-9]+|bus/usb/[0-9]{3}/[0-9]{3})", item)
                for item in config["devices"])
            or len(set(config["devices"])) != len(config["devices"])):
        raise ValueError("fixed device configuration required")
    if not isinstance(config["socket"], str):
        raise ValueError("fixed private socket required")
    endpoint = Path(config["socket"])
    if (not endpoint.is_absolute() or ".." in endpoint.parts
            or endpoint.parent != Path("/run/robot-scope-camera-owner")):
        raise ValueError("fixed private socket directory required")
    return config


def _proc_visible(proc: Path) -> bool:
    if proc != Path("/proc"):
        return True  # Injectable, local fixture only; requests never select /proc.
    if os.geteuid() != 0 or os.readlink(proc / "self/ns/pid") != os.readlink(proc / "1/ns/pid"):
        return False
    with (proc / "self/mountinfo").open("rb") as source:
        content = source.read(1024 * 1024 + 1)
    if len(content) > 1024 * 1024:
        return False
    mounts = []
    for line in content.decode().splitlines():
        before, after = line.split(" - ", 1)
        fields, filesystem = before.split(), after.split()
        if re.fullmatch(r"/proc/[0-9]+(?:/.*)?", fields[4]):
            return False
        if fields[4] == "/proc":
            if fields[3] != "/" or filesystem[0] != "proc":
                return False
            options = fields[5].split(",") + filesystem[2].split(",")
            if any(option.startswith("hidepid=") and option not in {"hidepid=0", "hidepid=off"}
                   for option in options):
                return False
            mounts.append(line)
    return len(mounts) == 1


@contextmanager
def _alarm(budget: float):
    # UnixStreamServer handles requests on the main thread. Never create an
    # unbounded background worker or signal any producer to enforce a timeout.
    if threading.current_thread() is not threading.main_thread() or signal.getitimer(signal.ITIMER_REAL)[0]:
        raise TimeoutError("exclusive main-thread observation deadline required")
    previous = signal.getsignal(signal.SIGALRM)
    def expired(_signum, _frame):
        raise TimeoutError("owner observation deadline")
    signal.signal(signal.SIGALRM, expired)
    try:
        signal.setitimer(signal.ITIMER_REAL, budget)
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _observe(devices: list[str], proc: Path, deadline: float) -> str:
    transient = {errno.ENOENT, errno.ESRCH}
    try:
        if not _proc_visible(proc):
            return "unavailable"
        identities = set()
        for device in devices:
            info = os.stat(device)
            if not stat.S_ISCHR(info.st_mode):
                return "unavailable"
            identities.add(info.st_rdev)
        if not identities:
            return "unavailable"
        seen, occupied = False, False
        for process in proc.iterdir():
            if not process.name.isdecimal():
                continue
            if time.monotonic() >= deadline:
                return "unavailable"
            try:
                with os.scandir(process / "fd") as descriptors:
                    seen = True
                    for descriptor in descriptors:
                        if time.monotonic() >= deadline:
                            return "unavailable"
                        try:
                            info = os.stat(descriptor.path)
                        except OSError as exc:
                            if exc.errno in transient:
                                continue
                            raise
                        if stat.S_ISCHR(info.st_mode) and info.st_rdev in identities:
                            occupied = True
            except OSError as exc:
                if exc.errno in transient:
                    # A missing fd directory is transient only if its process
                    # disappeared too. A still-live hidden process is partial.
                    try:
                        process.stat()
                    except OSError as process_error:
                        if process_error.errno in transient:
                            continue
                    return "unavailable"
                raise
        return ("occupied" if occupied else "free") if seen else "unavailable"
    except (OSError, ValueError, IndexError):
        return "unavailable"


def observe(devices: list[str], proc: Path = Path("/proc"), *, budget: float = 3.0) -> str:
    """Bound actual FD observation to three seconds, including blocking reads."""
    if type(budget) not in {int, float} or not math.isfinite(budget) or not 0 < budget <= 3.0:
        return "unavailable"
    try:
        with _alarm(budget):
            return _observe(devices, proc, time.monotonic() + budget)
    except (OSError, ValueError, TimeoutError):
        return "unavailable"


class Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        started = time.monotonic()
        self.connection.settimeout(1.0)
        try:
            with _alarm(3.0):
                self._request(started)
        except (OSError, ValueError, struct.error, TimeoutError):
            return

    def _request(self, started: float) -> None:
        try:
            peer = struct.unpack("3i", self.connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[1]
            if peer != self.server.config["uid"]:
                return
            raw = self.rfile.readline(257)
            if len(raw) > 256 or not raw.endswith(b"\n"):
                return
            if _json(raw) != {"operation": "camera_owner_state"}:
                return
            # Check once per request, including for occupied/unavailable states.
            state = _observe(self.server.config["devices"], Path("/proc"), started + 3.0)
            result = {"schema_version": 1, "devices": self.server.config["devices"],
                      "state": state, "checked_at_epoch": time.time(),
                      "checked_at_monotonic": time.monotonic(),
                      "host_pid_namespace": os.readlink("/proc/self/ns/pid")}
            self.connection.settimeout(max(0.001, 3.0 - (time.monotonic() - started)))
            self.wfile.write(json.dumps(result, allow_nan=False).encode() + b"\n")
        except (OSError, ValueError, struct.error, TimeoutError):
            return


class Server(socketserver.UnixStreamServer):
    def __init__(self, config: dict) -> None:
        self.config = config
        self._identity = None
        path = Path(config["socket"])
        parent = _root_directory(path.parent)
        try:
            try:
                os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise ValueError("existing probe socket requires owner investigation")
        finally:
            os.close(parent)
        super().__init__(str(path), Handler, bind_and_activate=False)
        try:
            self.server_bind()
            info = path.lstat()
            if not stat.S_ISSOCK(info.st_mode):
                raise ValueError("bound socket inode required")
            self._identity = (info.st_dev, info.st_ino)
            os.chmod(path, 0o600)
            os.chown(path, config["uid"], -1)
            self.server_activate()
        except BaseException:
            self.server_close()
            raise

    def server_close(self) -> None:
        super().server_close()
        path = Path(self.config["socket"])
        try:
            info = path.lstat()
            if self._identity is not None and (info.st_dev, info.st_ino) == self._identity and stat.S_ISSOCK(info.st_mode):
                path.unlink()
        except FileNotFoundError:
            pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    if os.geteuid() != 0 or os.readlink("/proc/self/ns/pid") != os.readlink("/proc/1/ns/pid"):
        raise SystemExit("root host ownership visibility required")
    _protected_bytes(Path(__file__), 65536)
    config = load_configuration(args.config)
    with Server(config) as server:
        def stop(_signum, _frame):
            threading.Thread(target=server.shutdown, daemon=True).start()
        for signum in (signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, stop)
        server.serve_forever(poll_interval=0.2)


if __name__ == "__main__":
    main()
