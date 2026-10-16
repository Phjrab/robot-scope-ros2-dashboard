"""Fixed operator-managed scope and live, parent-held reservation evidence.

Scope configuration records policy and sensor identity, never current freedom.
Only a probe performed while holding the matching lock creates live evidence.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import socket
import struct
import time
from typing import Any


PROTOCOL = "robot-scope-camera-managed-v1"
OWNER_POLICY = "shared_flock_live_probe"
OWNERS = {"robot_scope_rgb_relay", "robot_scope_slam_broker"}
SCOPE_FIELDS = {"schema_version", "lock_protocol", "scope_id", "devices",
                "camera_lock_path", "domain_id", "operational_domain_id",
                "domain_lock_path", "owner_policy", "cooperative_owners",
                "relay_script_path", "relay_script_sha256", "lock_helper_sha256", "host_pid_namespace",
                "owner_probe_socket"}


class ManagedScopeError(RuntimeError):
    def __init__(self, resource: str, reason: str) -> None:
        self.code = "RESOURCE_CONFLICT"
        self.status = 409
        self.resources = [{"resource": resource, "reason": reason}]
        super().__init__(self.code)


def private_json(path: Path, limit: int = 16384) -> dict[str, Any]:
    """Read one private inode; do not follow a replaced file or parent symlink."""
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError("private canonical path required")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as source:
        info = os.fstat(source.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077 or info.st_size > limit):
            raise ValueError("private same-UID regular file required")
        data = source.read(limit + 1)
    if len(data) > limit:
        raise ValueError("private document exceeds limit")
    value = json.loads(data, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    if not isinstance(value, dict):
        raise ValueError("private document must be an object")
    return value


def _lock_path(value: Any) -> Path:
    if not isinstance(value, str):
        raise ValueError("lock path required")
    path = Path(value)
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError("canonical lock path required")
    parent = path.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.geteuid() or parent.st_mode & 0o077:
        raise ValueError("private same-UID lock parent required")
    return path


def load_managed_scope(path: Path, *, camera_lock_path: Path | None = None,
                       domain_id: int | None = None,
                       operational_domain_id: int | None = None) -> dict[str, Any]:
    try:
        scope = private_json(path)
        if (set(scope) != SCOPE_FIELDS or type(scope["schema_version"]) is not int
                or scope["schema_version"] != 1 or scope["lock_protocol"] != PROTOCOL
                or not isinstance(scope["scope_id"], str)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{7,79}", scope["scope_id"])
                or scope["owner_policy"] != OWNER_POLICY
                or not isinstance(scope["cooperative_owners"], list)
                or len(scope["cooperative_owners"]) != len(OWNERS)
                or not all(isinstance(item, str) for item in scope["cooperative_owners"])
                or set(scope["cooperative_owners"]) != OWNERS):
            raise ValueError("managed scope policy is invalid")
        devices = scope["devices"]
        if (not isinstance(devices, list) or not 1 <= len(devices) <= 16
                or not all(isinstance(item, str) and re.fullmatch(
                    r"/dev/(?:video[0-9]+|bus/usb/[0-9]{3}/[0-9]{3})", item) for item in devices)
                or len(set(devices)) != len(devices)):
            raise ValueError("exact camera device inventory required")
        camera_lock = _lock_path(scope["camera_lock_path"])
        domain_lock = _lock_path(scope["domain_lock_path"])
        if camera_lock == domain_lock:
            raise ValueError("independent resource locks required")
        probe_socket = Path(scope["owner_probe_socket"])
        if not probe_socket.is_absolute() or probe_socket.resolve() != probe_socket:
            raise ValueError("canonical fixed owner probe socket required")
        relay_path = Path(scope["relay_script_path"])
        if (not relay_path.is_absolute() or relay_path.resolve() != relay_path
                or relay_path.name != "realsense_mjpeg_relay.py"
                or any(not isinstance(scope[key], str) or not re.fullmatch(r"[a-f0-9]{64}", scope[key])
                       for key in ("relay_script_sha256", "lock_helper_sha256"))
                or not isinstance(scope["host_pid_namespace"], str)
                or not re.fullmatch(r"pid:\[[0-9]+\]", scope["host_pid_namespace"])):
            raise ValueError("observed relay source and host PID namespace required")
        domain, operational = scope["domain_id"], scope["operational_domain_id"]
        if (type(domain) is not int or not 1 <= domain <= 232
                or type(operational) is not int or not 0 <= operational <= 232
                or domain == operational):
            raise ValueError("distinct fixed ROS domains required")
        if (camera_lock_path is not None and camera_lock != camera_lock_path
                or domain_id is not None and domain != domain_id
                or operational_domain_id is not None and operational != operational_domain_id):
            raise ValueError("managed scope differs from runtime resources")
        encoded = json.dumps(scope, sort_keys=True, separators=(",", ":")).encode()
        return dict(scope, scope_sha256=hashlib.sha256(encoded).hexdigest())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ManagedScopeError("session", "managed_scope_invalid") from exc


def probe_managed_camera_owner(scope: dict[str, Any]) -> dict[str, Any]:
    """Query only the fixed read-only root helper; never fall back to partial /proc."""
    try:
        path = Path(scope["owner_probe_socket"])
        info = path.lstat()
        if (path.resolve() != path or not stat.S_ISSOCK(info.st_mode)
                or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600):
            raise ValueError("private fixed owner probe socket required")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(4.0)
            connection.connect(str(path))
            if hasattr(socket, "SO_PEERCRED"):
                uid = struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[1]
            elif hasattr(connection, "getpeereid"):
                uid = connection.getpeereid()[0]
            else:
                uid = None
            if uid != 0:
                raise ValueError("root owner probe peer required")
            requested_mono, requested_epoch = time.monotonic(), time.time()
            connection.sendall(b'{"operation":"camera_owner_state"}\n')
            raw = bytearray()
            while b"\n" not in raw:
                chunk = connection.recv(4097 - len(raw))
                if not chunk or len(raw) + len(chunk) > 4096:
                    raise ValueError("bounded owner probe response required")
                raw.extend(chunk)
            response = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        now_mono, now_epoch = time.monotonic(), time.time()
        required = {"schema_version", "devices", "state", "checked_at_epoch", "checked_at_monotonic", "host_pid_namespace"}
        if (not isinstance(response, dict) or set(response) != required
                or type(response["schema_version"]) is not int or response["schema_version"] != 1
                or response["devices"] != scope["devices"]
                or response["host_pid_namespace"] != scope["host_pid_namespace"]
                or response["state"] not in {"free", "occupied", "unavailable"}):
            raise ValueError("owner probe response differs from fixed scope")
        for key in ("checked_at_epoch", "checked_at_monotonic"):
            if type(response[key]) not in {int, float} or not math.isfinite(response[key]):
                raise ValueError("finite owner probe timestamps required")
        if (not requested_mono <= response["checked_at_monotonic"] <= now_mono
                or not 0 <= now_mono - response["checked_at_monotonic"] <= 5
                or not requested_epoch <= response["checked_at_epoch"] <= now_epoch
                or not 0 <= now_epoch - response["checked_at_epoch"] <= 5):
            raise ValueError("owner probe report must be from this request")
        return response
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ManagedScopeError("camera", "owner_state_unavailable") from exc


def cooperative_relay_ready(scope: dict[str, Any], proc: Path = Path("/proc")) -> bool:
    """A waiting RGB relay must use the same lock before opening the device."""
    if not proc.is_dir():
        return False
    try:
        if os.readlink(proc / "self/ns/pid") != scope["host_pid_namespace"]:
            return False  # An isolated container cannot inspect host owners.
        project = Path(__file__).resolve().parents[1]
        relay = Path(scope["relay_script_path"])
        helper = relay.parents[1] / "robot_dashboard/slam_camera.py"
        for installed, expected, key in (
            (relay, project / "scripts/realsense_mjpeg_relay.py", "relay_script_sha256"),
            (helper, Path(__file__).with_name("slam_camera.py"), "lock_helper_sha256"),
        ):
            if (installed.is_symlink() or hashlib.sha256(installed.read_bytes()).hexdigest() != scope[key]
                    or hashlib.sha256(expected.read_bytes()).hexdigest() != scope[key]):
                return False
        boot = next(float(line.split()[1]) for line in (proc / "stat").read_text().splitlines()
                    if line.startswith("btime "))
        for process in proc.glob("[0-9]*"):
            try:
                arguments = (process / "cmdline").read_bytes().split(b"\0")
                if not any(Path(os.fsdecode(item)).name == "realsense_mjpeg_relay.py" for item in arguments if item):
                    continue
                # A foreign or unreadable relay cannot be assumed cooperative.
                if process.stat().st_uid != os.geteuid():
                    return False
                scripts = [Path(os.fsdecode(item)) for item in arguments if item
                           and Path(os.fsdecode(item)).name == "realsense_mjpeg_relay.py"]
                if len(scripts) != 1 or scripts[0] != relay:
                    return False
                started = boot + float((process / "stat").read_text().rsplit(")", 1)[1].split()[19]) / os.sysconf("SC_CLK_TCK")
                if relay.stat().st_mtime > started:
                    return False  # Source changed after this process loaded it.
                environment = (process / "environ").read_bytes().split(b"\0")
                if os.fsencode("ROBOT_SCOPE_CAMERA_LOCK=" + scope["camera_lock_path"]) not in environment:
                    return False
            except FileNotFoundError:
                continue  # Process exited during the current observation.
        return True
    except (OSError, ValueError, KeyError, StopIteration, IndexError, TypeError):
        return False


def lock_evidence(descriptor: int, path: Path) -> dict[str, Any]:
    info = os.fstat(descriptor)
    current = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_mode & 0o077 or (info.st_dev, info.st_ino) != (current.st_dev, current.st_ino)):
        raise ManagedScopeError("session", "reservation_lock_changed")
    return {"path": str(path), "fd": descriptor, "device": info.st_dev, "inode": info.st_ino}


class DomainReservation:
    """Held through graph observation, child lifetime and confirmed cleanup."""
    def __init__(self, scope: dict[str, Any]) -> None:
        self.scope = scope
        self.path = Path(scope["domain_lock_path"])
        self.fd: int | None = None

    def acquire(self) -> None:
        if self.fd is not None:
            raise ManagedScopeError("ros_domain", "reservation_owned")
        try:
            _lock_path(str(self.path))
            descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            try:
                lock_evidence(descriptor, self.path)
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BaseException:
                os.close(descriptor)
                raise
            self.fd = descriptor
        except (OSError, ValueError) as exc:
            raise ManagedScopeError("ros_domain", "reservation_unavailable") from exc

    def evidence(self) -> dict[str, Any]:
        if self.fd is None:
            raise ManagedScopeError("ros_domain", "reservation_missing")
        return lock_evidence(self.fd, self.path)

    def release(self) -> None:
        if self.fd is not None:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)
            self.fd = None


def validate_reservation_proof(proof: dict[str, Any], scope: dict[str, Any], *,
                               monotonic: Any = time.monotonic, proc: Path = Path("/proc")) -> None:
    """Child-side proof check; historical camera observations are left intact."""
    try:
        if (proof["schema_version"] != 1 or proof["evidence_kind"] != "live_managed_reservation"
                or proof["scope_id"] != scope["scope_id"] or proof["scope_sha256"] != scope["scope_sha256"]
                or proof["domain_id"] != scope["domain_id"] or proof["devices"] != scope["devices"]
                or proof["owner_uid"] != os.geteuid() or type(proof["owner_pid"]) is not int
                or proof["owner_pid"] <= 0 or type(proof["checked_at_monotonic"]) not in {float, int}
                or not 0 <= monotonic() - proof["checked_at_monotonic"] <= 300):
            raise ValueError("fresh matching reservation required")
        if os.readlink(proc / "self/ns/pid") != scope["host_pid_namespace"]:
            raise ValueError("host PID visibility changed")
        process = proc / str(proof["owner_pid"])
        if process.stat().st_uid != os.geteuid():
            raise ValueError("reservation owner changed")
        for key, path_key in (("camera_lock", "camera_lock_path"), ("domain_lock", "domain_lock_path")):
            evidence = proof[key]
            if (evidence["path"] != scope[path_key] or type(evidence["fd"]) is not int
                    or evidence["fd"] < 0):
                raise ValueError("reservation path differs")
            current = Path(scope[path_key]).lstat()
            held = (process / "fd" / str(evidence["fd"])).stat()
            expected = (evidence["device"], evidence["inode"])
            if ((current.st_dev, current.st_ino) != expected or (held.st_dev, held.st_ino) != expected
                    or not stat.S_ISREG(current.st_mode) or current.st_uid != os.geteuid()
                    or current.st_mode & 0o077):
                raise ValueError("reservation inode changed")
            # Opening the same inode must still conflict with the parent's flock.
            descriptor = os.open(scope[path_key], os.O_RDWR | os.O_NOFOLLOW)
            try:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    pass
                else:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
                    raise ValueError("reservation lock is no longer held")
            finally:
                os.close(descriptor)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ManagedScopeError("session", "reservation_proof_invalid") from exc
