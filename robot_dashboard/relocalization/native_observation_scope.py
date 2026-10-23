"""Owned resource scopes for the global and seeded observation children.

The parent must own the unique scope through verified all-member termination.
No command from this file is executed merely by importing it.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import threading
import tempfile
import time
import uuid

from .native_observation_scope_admission import LIMITS, UNIT, private_json, read_private_json, read_boundary

RESOURCE_MODE_ENV = "ROBOT_SCOPE_OBSERVATION_CHILD_RESOURCE_MODE"


class ScopeWorkDirectory:
    def __init__(self, *, prefix: str) -> None:
        # Explicit lifecycle: no GC finalizer may delete an unresolved child's files.
        self.name = tempfile.mkdtemp(prefix=prefix)
        self.retain = False

    def __enter__(self) -> str:
        return self.name

    def __exit__(self, *_ignored) -> None:
        if not self.retain:
            self.cleanup()

    def cleanup(self) -> None:
        shutil.rmtree(self.name, ignore_errors=False) if Path(self.name).exists() else None


def resource_mode_from_environment() -> bool:
    mode = os.environ.get(RESOURCE_MODE_ENV)
    if mode is None:
        return False
    if mode != "user_scope_v1":
        raise ValueError("unsupported native observation child resource mode")
    return True


def _user_bus_environment(environment: dict[str, str]) -> dict[str, str]:
    runtime, bus = Path("/run/user/1000"), Path("/run/user/1000/bus")
    if (os.getuid() != 1000 or os.geteuid() != 1000 or runtime.stat().st_uid != 1000
            or stat.S_IMODE(runtime.stat().st_mode) != 0o700
            or bus.stat().st_uid != 1000 or not stat.S_ISSOCK(bus.stat().st_mode)):
        raise ValueError("native scope requires the existing UID1000 private user bus")
    value = dict(environment)
    value.update(XDG_RUNTIME_DIR=str(runtime), DBUS_SESSION_BUS_ADDRESS="unix:path=" + str(bus))
    return value


def build_scope_command(*, python: Path, bootstrap: Path, worker: Path,
                        workdir: Path, kind: str, socket_fd: int | None = None,
                        runtime_s: int = 60, nonce: str | None = None) -> tuple[list[str], dict]:
    if kind not in {"sensor", "global"} or type(runtime_s) is not int or not 1 <= runtime_s <= 120:
        raise ValueError("SCOPE_KIND_OR_RUNTIME_INVALID")
    nonce = nonce if nonce is not None else uuid.uuid4().hex
    if not re.fullmatch(r"[a-f0-9]{32}", nonce):
        raise ValueError("SCOPE_NONCE_INVALID")
    if not all(path.is_absolute() and path.is_file() for path in (python, bootstrap, worker)):
        raise ValueError("SCOPE_ABSOLUTE_LAUNCH_PATHS_REQUIRED")
    if (kind == "sensor" and (type(socket_fd) is not int or socket_fd < 3)) or (kind == "global" and socket_fd is not None):
        raise ValueError("SCOPE_SOCKET_CONTRACT_INVALID")
    unit = f"robot-scope-{kind}-{nonce}.scope"
    worker_sha = hashlib.sha256(worker.read_bytes()).hexdigest()
    argv = ["/usr/bin/systemd-run", "--user", "--scope", "--quiet", "--collect",
            "--unit=" + unit, "--slice=app.slice", "--property=MemoryMax=2147483648",
            "--property=MemorySwapMax=0", "--property=TasksMax=64",
            "--property=RuntimeMaxSec=" + str(runtime_s) + "s", "--",
            str(python), "-I", str(bootstrap), "--unit", unit, "--nonce", nonce,
            "--kind", kind, "--worker", str(worker), "--worker-sha256", worker_sha,
            "--workdir", str(workdir)]
    if socket_fd is not None:
        argv += ["--socket-fd", str(socket_fd)]
    # OOMPolicy is a service property and is rejected for scopes on systemd249.
    # --wait is not required for synchronous scope mode. No CPUQuota is set.
    return argv, {"unit": unit, "nonce": nonce, "kind": kind,
                  "worker_sha256": worker_sha, "socket_fd": socket_fd,
                  "runtime_s": runtime_s, "workdir": str(workdir), "worker": str(worker)}


def wait_and_ack(process, specification: dict, *, cancel, deadline: float,
                 manager_readback=None) -> dict:
    """Admit the pre-import bootstrap only after checking its owned PGID/SID.

    On every exception the CALLER must close the exact owned scope and verify
    its cgroup empty; a bootstrap failure is never a reason to run uncontained.
    """
    if not UNIT.fullmatch(specification["unit"]):
        raise ValueError("SCOPE_UNIT_INVALID")
    folder = Path(specification["workdir"])
    proof_path = folder / ("resource-proof-" + specification["nonce"] + ".json")
    while not proof_path.exists():
        if (cancel is not None and cancel.is_set()) or time.monotonic() >= deadline:
            raise ValueError("SCOPE_ADMISSION_CANCELLED_OR_TIMED_OUT")
        if process.poll() is not None:
            raise ValueError("SCOPE_BOOTSTRAP_EXITED_NO_NATIVE_IMPORT")
        time.sleep(.01)
    proof = read_private_json(proof_path)
    if (proof.get("schema") != "robot-scope.native-scope-admission.v1"
            or any(proof.get(k) != specification[k] for k in
                   ("unit", "nonce", "kind", "worker_sha256", "socket_fd"))
            or proof.get("uid") != 1000 or proof.get("limits") != LIMITS
            or proof.get("pgid") != process.pid or proof.get("sid") != process.pid
            or proof.get("pid") != process.pid
            or proof.get("native_import_performed") is not False):
        raise ValueError("SCOPE_PARENT_ADMISSION_PROOF_MISMATCH")
    pid = proof["pid"]
    # Independently read the live kernel process identity, not just its receipt.
    rows = Path(f"/proc/{pid}/cgroup").read_text().splitlines()
    if (rows != ["0::" + proof["control_group"]]
            or Path(f"/proc/{pid}").stat().st_uid != 1000
            or os.getpgid(pid) != process.pid or os.getsid(pid) != process.pid):
        raise ValueError("SCOPE_LIVE_PROCESS_IDENTITY_CHANGED")
    boundary = read_boundary(specification["unit"], proc_cgroup=Path(f"/proc/{pid}/cgroup"))
    if any(proof.get(key) != value for key, value in boundary.items()):
        raise ValueError("SCOPE_LIVE_RESOURCE_BOUNDARY_CHANGED")
    if manager_readback is None:
        raise ValueError("SCOPE_MANAGER_READBACK_REQUIRED")
    manager_properties = manager_readback(proof)
    worker = Path(specification["worker"])
    if (worker.resolve() != worker
            or hashlib.sha256(worker.read_bytes()).hexdigest() != specification["worker_sha256"]):
        raise ValueError("SCOPE_WORKER_CHANGED_BEFORE_ACK")
    if (cancel is not None and cancel.is_set()) or process.poll() is not None or time.monotonic() >= deadline:
        raise ValueError("SCOPE_ADMISSION_CANCELLED_OR_TIMED_OUT")
    private_json(folder / ("resource-ack-" + specification["nonce"] + ".json"),
        {"schema": "robot-scope.native-scope-ack.v1", "unit": specification["unit"],
         "nonce": specification["nonce"], "pid": pid, "pgid": process.pid})
    return {**proof, "manager_properties": manager_properties}


class NativeObservationScope:
    """One unique owned scope; preserve this handle until close verifies empty."""

    def __init__(self, *, python: Path, worker: Path, folder: Path, kind: str,
                 environment: dict[str, str], runtime_s: int, socket_fd: int | None = None,
                 stdout=None, stderr=None) -> None:
        self._lock = threading.Lock()
        self._settled = False
        self._environment = _user_bus_environment(environment)
        self.proof: dict | None = None
        argv, self.specification = build_scope_command(
            python=python, bootstrap=Path(__file__).with_name("native_observation_scope_admission.py"),
            worker=worker, workdir=folder, kind=kind, socket_fd=socket_fd, runtime_s=runtime_s)
        self.process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
            cwd=folder, env=self._environment, pass_fds=(() if socket_fd is None else (socket_fd,)),
            close_fds=True, start_new_session=True)

    def admit(self, *, cancel, deadline: float) -> dict:
        self.proof = wait_and_ack(self.process, self.specification, cancel=cancel, deadline=deadline,
                                  manager_readback=self._read_manager_properties)
        return self.proof

    def _read_manager_properties(self, proof: dict) -> dict:
        shown = self._systemctl("show", "--property=RuntimeMaxUSec", "--property=Transient",
            "--property=ActiveState", "--property=ControlGroup", "--property=Delegate",
            "--", self.specification["unit"])
        value = dict(row.split("=", 1) for row in shown.stdout.splitlines() if "=" in row)
        runtime = value.get("RuntimeMaxUSec", "")
        tokens = runtime.split()
        multipliers = {"us": .000001, "ms": .001, "s": 1, "min": 60, "h": 3600, "d": 86400}
        seconds = 0.
        for token in tokens:
            match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)(us|ms|s|min|h|d)", token)
            if match is None:
                raise ValueError("SCOPE_FINITE_RUNTIME_READBACK_REQUIRED")
            seconds += float(match[1]) * multipliers[match[2]]
        if (shown.returncode != 0 or not tokens or seconds != self.specification["runtime_s"]
                or value.get("Transient") != "yes" or value.get("ActiveState") != "active"
                or value.get("Delegate") != "no" or value.get("ControlGroup") != proof["control_group"]):
            raise ValueError("SCOPE_APPLIED_MANAGER_POLICY_MISMATCH")
        return value

    def _systemctl(self, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run(["/usr/bin/systemctl", "--user", *arguments],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=self._environment, timeout=.5, check=False, text=True)

    def close(self) -> bool:
        with self._lock:
            if self._settled:
                return True
            try:
                return self._close_owned_scope()
            except (OSError, ValueError, subprocess.SubprocessError):
                # Readback uncertainty is unresolved cleanup, never permission
                # to delete inputs or forget this exact owned handle.
                return False

    def _close_owned_scope(self) -> bool:
        unit = self.specification["unit"]
        if not UNIT.fullmatch(unit):
            return False
        for name in ("SIGTERM", "SIGKILL"):
            try:
                self._systemctl("kill", "--kill-who=all", "--signal=" + name, "--", unit)
            except (OSError, subprocess.TimeoutExpired):
                pass
            # The scope owns all descendants. Signal only our unreaped
            # Popen leader as fallback; never target a recycled PGID.
            if self.process.poll() is None:
                try:
                    self.process.send_signal(getattr(signal, name))
                except (ProcessLookupError, PermissionError):
                    pass
            try:
                self.process.wait(timeout=.2)
            except subprocess.TimeoutExpired:
                pass
        try:
            self._systemctl("stop", "--", unit)
            shown = self._systemctl("show", "--property=LoadState", "--property=ActiveState",
                                   "--property=ControlGroup", "--", unit)
        except (OSError, subprocess.TimeoutExpired):
            return False
        properties = dict(row.split("=", 1) for row in shown.stdout.splitlines() if "=" in row)
        if (self.process.poll() is None or properties.get("ActiveState") not in {"inactive", "failed"}
                or properties.get("LoadState") not in {"loaded", "not-found"}):
            return False
        paths = {p for p in ((self.proof or {}).get("control_group"), properties.get("ControlGroup")) if p}
        for path in paths:
            if Path(path).name != unit or ".." in Path(path).parts:
                return False
            cgroup = Path("/sys/fs/cgroup") / path.lstrip("/")
            try:
                events = dict(row.split() for row in (cgroup / "cgroup.events").read_text().splitlines())
            except FileNotFoundError:
                continue
            if events.get("populated") != "0":
                return False
        self._settled = True
        return True
