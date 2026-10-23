"""Stdlib-only pre-import admission for an owned native observer scope.

This module must run before the pinned worker imports NumPy/Open3D. It never
changes cgroups; it verifies the scope already established by systemd-run.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import socket
import stat
import time
import uuid


UNIT = re.compile(r"robot-scope-(?:sensor|global)-[a-f0-9]{32}\.scope\Z")
NONCE = re.compile(r"[a-f0-9]{32}\Z")
LIMITS = {"memory.max": "2147483648", "memory.swap.max": "0", "pids.max": "64"}
WORKERS = {"sensor": "sensor_tracking_worker.py", "global": "global_observation_worker.py"}


def read_boundary(unit: str, *, proc_cgroup: Path = Path("/proc/self/cgroup"),
                  cgroup_root: Path = Path("/sys/fs/cgroup")) -> dict:
    if not UNIT.fullmatch(unit):
        raise ValueError("SCOPE_UNIT_INVALID")
    rows = proc_cgroup.read_text().splitlines()
    if len(rows) != 1 or not rows[0].startswith("0::/"):
        raise ValueError("SCOPE_UNIFIED_CGROUP_REQUIRED")
    relative = PurePosixPath(rows[0][3:])
    if ".." in relative.parts or relative.name != unit:
        raise ValueError("SCOPE_PROCESS_NOT_IN_EXACT_UNIT")
    folder = cgroup_root.joinpath(*relative.parts[1:])
    actual = {name: (folder / name).read_text().strip() for name in LIMITS}
    if actual != LIMITS:
        raise ValueError("SCOPE_MEMORY_PIDS_BOUNDARY_MISMATCH")
    oom_group = (folder / "memory.oom.group").read_text().strip()
    if oom_group not in {"0", "1"}:
        raise ValueError("SCOPE_OOM_GROUP_READBACK_INVALID")
    cpu = folder / "cpu.max"
    cpu_max = cpu.read_text().strip() if cpu.exists() else None
    if cpu_max is not None and cpu_max.split()[0] != "max":
        raise ValueError("SCOPE_EXTRA_CPU_QUOTA_FORBIDDEN")
    ancestors = {}
    parent = folder.parent
    while parent == cgroup_root or cgroup_root in parent.parents:
        path = parent / "cpu.max"
        ancestors[str(parent.relative_to(cgroup_root))] = path.read_text().strip() if path.exists() else None
        if parent == cgroup_root:
            break
        parent = parent.parent
    return {"control_group": str(relative), "limits": actual, "cpu_max": cpu_max,
            "memory_oom_group": oom_group, "oom_atomic_group_kill": oom_group == "1",
            "cpu_controller_delegated": cpu_max is not None,
            "ancestor_cpu_max": ancestors,
            "cpu_ancestor_quota_observed": True}


def private_json(path: Path, value: dict) -> None:
    temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex)
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "w") as output:
            json.dump(value, output, allow_nan=False, separators=(",", ":"))
            output.flush()
            os.fsync(output.fileno())
        # Atomic publication with no replacement: peer never reads partial JSON.
        os.link(temporary, path, follow_symlinks=False)
    finally:
        temporary.unlink(missing_ok=True)


def read_private_json(path: Path) -> dict:
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.getuid() or info.st_size > 8192):
        raise ValueError("SCOPE_PRIVATE_CONTROL_FILE_INVALID")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("SCOPE_CONTROL_OBJECT_REQUIRED")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--unit", required=True)
    parser.add_argument("--nonce", required=True)
    parser.add_argument("--kind", required=True, choices=tuple(WORKERS))
    parser.add_argument("--worker", type=Path, required=True)
    parser.add_argument("--worker-sha256", required=True)
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--socket-fd", type=int)
    args = parser.parse_args()
    if not NONCE.fullmatch(args.nonce) or os.getuid() != 1000 or os.geteuid() != 1000:
        raise ValueError("SCOPE_NONCE_OR_UID_INVALID")
    folder = args.workdir
    info = folder.lstat()
    if (not folder.is_absolute() or folder.resolve() != folder or not stat.S_ISDIR(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o700 or info.st_uid != 1000):
        raise ValueError("SCOPE_PRIVATE_WORKDIR_REQUIRED")
    worker = args.worker
    if (not worker.is_absolute() or worker.resolve() != worker or worker.name != WORKERS[args.kind]
            or hashlib.sha256(worker.read_bytes()).hexdigest() != args.worker_sha256):
        raise ValueError("SCOPE_FIXED_WORKER_HASH_MISMATCH")
    if args.kind == "sensor":
        if args.socket_fd is None or args.socket_fd < 3:
            raise ValueError("SCOPE_SENSOR_SOCKET_FD_REQUIRED")
        with socket.fromfd(args.socket_fd, socket.AF_UNIX, socket.SOCK_STREAM) as channel:
            if channel.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_STREAM:
                raise ValueError("SCOPE_SENSOR_SOCKET_INVALID")
    elif args.socket_fd is not None:
        raise ValueError("SCOPE_GLOBAL_HAS_NO_SENSOR_SOCKET")
    boundary = read_boundary(args.unit)
    proof = {"schema": "robot-scope.native-scope-admission.v1", "nonce": args.nonce,
             "unit": args.unit, "kind": args.kind, "uid": os.getuid(),
             "pid": os.getpid(), "pgid": os.getpgrp(), "sid": os.getsid(0),
             "worker_sha256": args.worker_sha256, "socket_fd": args.socket_fd,
             "observed_utc": datetime.now(timezone.utc).isoformat(),
             "native_thread_caps": {name: os.environ.get(name) for name in
                                    ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")},
             "extra_cgroup_cpu_quota": False,
             "native_import_performed": False, **boundary}
    private_json(folder / ("resource-proof-" + args.nonce + ".json"), proof)
    ack_path = folder / ("resource-ack-" + args.nonce + ".json")
    deadline = time.monotonic() + 5.
    while not ack_path.exists():
        if time.monotonic() >= deadline:
            raise ValueError("SCOPE_PARENT_ACK_TIMEOUT_NO_NATIVE_IMPORT")
        time.sleep(.01)
    ack = read_private_json(ack_path)
    if ack != {"schema": "robot-scope.native-scope-ack.v1", "unit": args.unit,
               "nonce": args.nonce, "pid": proof["pid"], "pgid": proof["pgid"]}:
        raise ValueError("SCOPE_PARENT_ACK_IDENTITY_MISMATCH")
    # Re-read the kernel boundary immediately before the unchanged worker exec.
    if read_boundary(args.unit) != boundary:
        raise ValueError("SCOPE_BOUNDARY_CHANGED_BEFORE_EXEC")
    if (worker.resolve() != worker
            or hashlib.sha256(worker.read_bytes()).hexdigest() != args.worker_sha256):
        raise ValueError("SCOPE_WORKER_CHANGED_BEFORE_EXEC")
    if args.socket_fd is not None:
        os.set_inheritable(args.socket_fd, True)
    argv = [os.sys.executable, "-I", str(worker), str(folder)]
    if args.socket_fd is not None:
        argv.append(str(args.socket_fd))
    os.execv(os.sys.executable, argv)
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
