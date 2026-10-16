"""Fixed local IPC for an observer in the preserved Isaac image.

The operator starts this service only in an approved resource window. It exposes
no command, Docker, sudo, topic, domain or general filesystem operation.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import socket
import socketserver
import signal
import stat
import struct
import threading
from typing import Any

from .slam_camera import CameraBusy, CameraOwnerCoordinator
from .slam_managed_scope import ManagedScopeError
from .slam_sessions import SlamError, _validate_hint

MAX_REQUEST = 64 * 1024
MAX_RESPONSE = 8 * 1024**2
RESOURCE_LABELS = {"navigation", "mission", "mission_route", "dataset_capture", "control",
                   "lidar", "lifecycle", "camera", "ros_domain", "broker", "session"}


def _resources(value: Any) -> list[dict[str, str]]:
    if (not isinstance(value, list) or not 1 <= len(value) <= 16
            or any(not isinstance(item, dict) or set(item) != {"resource", "reason"}
                   or not isinstance(item["resource"], str) or item["resource"] not in RESOURCE_LABELS
                   or not isinstance(item["reason"], str)
                   or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", item["reason"]) for item in value)):
        raise SlamError("INVALID_BROKER_RESPONSE", 503)
    return value


def peer_uid(connection: Any) -> int | None:
    if hasattr(socket, "SO_PEERCRED"):
        return struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[1]
    if hasattr(connection, "getpeereid"):
        return connection.getpeereid()[0]
    return None


def _wire(value: Any) -> bytes:
    return json.dumps(value, allow_nan=False, separators=(",", ":")).encode() + b"\n"


def _session(value: Any) -> dict[str, Any]:
    required = {"session_id", "generation", "map_epoch", "engine_id", "task"}
    if not isinstance(value, dict) or set(value) != required:
        raise SlamError("INVALID_SESSION", 422)
    if any(not isinstance(value[k], str) or not re.fullmatch(r"[a-f0-9]{32}", value[k]) for k in ("session_id", "map_epoch")):
        raise SlamError("INVALID_SESSION", 422)
    if type(value["generation"]) is not int or not 1 <= value["generation"] < 2**31:
        raise SlamError("INVALID_SESSION", 422)
    if value["engine_id"] != "visual_stereo" or value["task"] not in {"tracking", "mapping"}:
        raise SlamError("INVALID_SESSION", 422)
    return value


class BrokerDispatcher:
    def __init__(self, adapter: Any, camera: CameraOwnerCoordinator, package_root: Path) -> None:
        self.adapter = adapter
        self.camera = camera
        self.package_root = package_root.resolve()
        self._lock = threading.RLock()
        self._owned: dict[str, Any] | None = None
        self._cancel = threading.Event()
        self._running_operation = False
        bind_camera = getattr(adapter, "bind_camera_coordinator", None)
        if bind_camera is not None:
            bind_camera(camera)

    def _native_path(self, value: Any, group: str) -> Path:
        if not isinstance(value, str):
            raise SlamError("INVALID_NATIVE_PATH", 422)
        path = Path(value)
        root_info = self.package_root.lstat()
        if not stat.S_ISDIR(root_info.st_mode) or root_info.st_uid != os.geteuid() or root_info.st_mode & 0o077:
            raise SlamError("INVALID_NATIVE_PATH", 422)
        try:
            relative = path.relative_to(self.package_root)
        except ValueError as exc:
            raise SlamError("INVALID_NATIVE_PATH", 422) from exc
        if len(relative.parts) != 3 or relative.parts[0] != group or relative.parts[2] != "native" or not re.fullmatch(r"[0-9a-f]{32}", relative.parts[1]):
            raise SlamError("INVALID_NATIVE_PATH", 422)
        # Reject symlinks at every level before handing anything to native code.
        current = self.package_root
        for part in relative.parts:
            current = current / part
            info = current.lstat()
            if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077 or info.st_uid != os.geteuid():
                raise SlamError("INVALID_NATIVE_PATH", 422)
        if path.resolve() != path:
            raise SlamError("INVALID_NATIVE_PATH", 422)
        return path

    def dispatch(self, request: Any) -> Any:
        if not isinstance(request, dict) or set(request) - {"operation", "session", "task", "native_path", "hint"}:
            raise SlamError("INVALID_BROKER_REQUEST", 422)
        operation = request.get("operation")
        fields = {
            "capability": {"operation"}, "preflight": {"operation", "task"},
            **{op: {"operation", "session"} for op in ("reserve_camera", "release_camera", "start", "stop", "cancel", "status", "frame")},
            "save": {"operation", "session", "native_path"},
            "localize": {"operation", "session", "native_path", "hint"},
        }
        if operation not in fields or set(request) != fields[operation]:
            raise SlamError("INVALID_BROKER_REQUEST", 422)
        if operation == "capability":
            cap = self.adapter.capability()
            with self._lock:
                cap["camera"] = self.camera.snapshot()
                cap["broker_owned_session"] = self._owned["session_id"] if self._owned else None
            return cap
        if operation == "preflight":
            if request.get("task") not in {"tracking", "mapping"}:
                raise SlamError("MODE_UNSUPPORTED", 422)
            self.adapter.preflight(request["task"])
            return {"ok": True}
        session = _session(request.get("session"))
        with self._lock:
            if operation == "reserve_camera":
                if self._owned is not None:
                    if self._owned == session:
                        return {"ok": True}
                    raise SlamError("CAMERA_BUSY", resources=[{"resource": "camera", "reason": "reservation_owned"}])
                self.camera.acquire(session)
                self._owned = session
                self._cancel = threading.Event()
                return {"ok": True}
            if operation == "localize" and self._owned is not None and all(
                    self._owned[key] == session[key] for key in ("session_id", "generation", "engine_id", "task")):
                if self._running_operation:
                    raise SlamError("OPERATION_IN_PROGRESS")
                self._owned = session
            if self._owned != session:
                if operation in {"stop", "release_camera"} and self._owned is None:
                    return {"ok": True}
                raise SlamError("SESSION_GENERATION_CONFLICT")
            if operation == "cancel":
                self._cancel.set()
                return {"ok": True}
            if operation in {"start", "save", "localize", "stop", "release_camera"}:
                if self._running_operation:
                    raise SlamError("OPERATION_IN_PROGRESS")
                self._running_operation = True
        try:
            if operation == "start":
                return self.adapter.start(session, self._cancel)
            if operation == "stop":
                self._cancel.set()
                self.adapter.stop(session)
                return {"ok": True}
            if operation == "release_camera":
                # Reconfirm child cleanup before relinquishing the device lock.
                self.adapter.stop(session)
                self.camera.release(session)
                with self._lock:
                    self._owned = None
                return {"ok": True}
            if operation == "status":
                return self.adapter.status(session)
            if operation == "frame":
                return self.adapter.frame(session)
            if operation == "save":
                return self.adapter.save(session, self._native_path(request.get("native_path"), "staging"))
            if operation == "localize":
                _validate_hint(request.get("hint"))
                return self.adapter.localize(session, self._native_path(request.get("native_path"), "scratch"), request["hint"])
            raise SlamError("OPERATION_UNSUPPORTED", 422)
        finally:
            if operation in {"start", "save", "localize", "stop", "release_camera"}:
                with self._lock:
                    self._running_operation = False


class BrokerHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        self.connection.settimeout(55)
        # Linux service runs with the same uid on both sides of a private socket.
        if peer_uid(self.connection) != os.geteuid():
            return
        try:
            raw = self.rfile.readline(MAX_REQUEST + 1)
            if len(raw) > MAX_REQUEST or not raw.endswith(b"\n"):
                raise SlamError("INVALID_BROKER_REQUEST", 422)
            value = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            result = self.server.dispatcher.dispatch(value)
            response = _wire({"ok": True, "result": result})
            if len(response) > MAX_RESPONSE:
                raise SlamError("VISUALIZATION_LIMIT")
        except Exception as exc:
            code = exc.code if isinstance(exc, (SlamError, CameraBusy, ManagedScopeError)) else "ENGINE_OPERATION_FAILED"
            error = {"ok": False, "code": code}
            resources = getattr(exc, "resources", None)
            if resources:
                try:
                    error["resources"] = _resources(resources)
                except SlamError:
                    pass
            response = _wire(error)
        self.wfile.write(response)


class BrokerServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    block_on_close = False
    allow_reuse_address = False

    def __init__(self, path: Path, dispatcher: BrokerDispatcher) -> None:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = path.parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise SlamError("UNSAFE_BROKER_SOCKET")
        # Never unlink an existing socket: it may belong to an active runtime.
        if path.exists() or path.is_symlink():
            raise SlamError("BROKER_SOCKET_EXISTS")
        self.dispatcher = dispatcher
        super().__init__(str(path), BrokerHandler)
        os.chmod(path, 0o600)


class BrokerCameraCoordinator:
    def __init__(self, adapter: "BrokerIsaacAdapter") -> None:
        self.adapter = adapter
        self._owner: dict[str, Any] | None = None
        self._reservation_unknown = False

    def acquire(self, session: dict[str, Any]) -> None:
        self._owner = dict(session)
        self._reservation_unknown = True
        self.adapter._request("reserve_camera", session=session)
        self._reservation_unknown = False

    def release(self, session: dict[str, Any]) -> None:
        self._reservation_unknown = True
        self.adapter._request("release_camera", session=session)
        self._owner = None
        self._reservation_unknown = False

    def release_if_owned(self, session: dict[str, Any]) -> None:
        """Settle a lost reserve response using the broker's ownership ledger."""
        try:
            self.release(session)
        except SlamError as exc:
            if exc.code != "SESSION_GENERATION_CONFLICT":
                raise
            # A definitive foreign owner proves this session has no reservation.
            # The broker has neither stopped nor released that foreign producer.
            self._owner = None
            self._reservation_unknown = False

    def snapshot(self) -> dict[str, Any]:
        return {"reserved": self._owner is not None,
                "session_id": self._owner.get("session_id") if self._owner else None,
                "generation": self._owner.get("generation") if self._owner else None,
                "reservation_unknown": self._reservation_unknown,
                "rgb_available": self._owner is None, "owner_location": "isaac_broker"}


class BrokerIsaacAdapter:
    def __init__(self, socket_path: Path) -> None:
        self.socket_path = socket_path
        self.camera_coordinator = BrokerCameraCoordinator(self)

    def _request(self, operation: str, *, session: dict[str, Any] | None = None,
                 cancel: threading.Event | None = None, **values: Any) -> Any:
        info = self.socket_path.lstat()
        parent = self.socket_path.parent.lstat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077 or not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.geteuid() or parent.st_mode & 0o077:
            raise SlamError("UNSAFE_BROKER_SOCKET", 503)
        request = {"operation": operation, **values}
        if session is not None:
            request["session"] = {key: session[key] for key in ("session_id", "generation", "map_epoch", "engine_id", "task")}
        payload = _wire(request)
        if len(payload) > MAX_REQUEST:
            raise SlamError("INVALID_BROKER_REQUEST", 422)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(0.2)
            connection.connect(str(self.socket_path))
            connection.sendall(payload)
            import time
            deadline = time.monotonic() + (55 if operation in {"start", "save", "localize", "stop", "release_camera"} else 4)
            response = bytearray()
            cancel_sent = False
            while b"\n" not in response:
                if time.monotonic() > deadline:
                    raise SlamError("BROKER_TIMEOUT", 503)
                if cancel is not None and cancel.is_set() and not cancel_sent:
                    self._request("cancel", session=session)
                    cancel_sent = True
                try:
                    chunk = connection.recv(65536)
                except socket.timeout:
                    continue
                if not chunk or len(response) + len(chunk) > MAX_RESPONSE:
                    raise SlamError("INVALID_BROKER_RESPONSE", 503)
                response.extend(chunk)
        try:
            result = json.loads(response, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except (ValueError, UnicodeError) as exc:
            raise SlamError("INVALID_BROKER_RESPONSE", 503) from exc
        if not isinstance(result, dict) or type(result.get("ok")) is not bool:
            raise SlamError("INVALID_BROKER_RESPONSE", 503)
        if result["ok"] and set(result) != {"ok", "result"}:
            raise SlamError("INVALID_BROKER_RESPONSE", 503)
        if result["ok"] and not isinstance(result["result"], dict):
            raise SlamError("INVALID_BROKER_RESPONSE", 503)
        if not result["ok"] and set(result) not in ({"ok", "code"}, {"ok", "code", "resources"}):
            raise SlamError("INVALID_BROKER_RESPONSE", 503)
        if result.get("ok") is not True:
            code = result.get("code", "ENGINE_OPERATION_FAILED")
            resources = _resources(result["resources"]) if "resources" in result else None
            raise SlamError(code if isinstance(code, str) and re.fullmatch(r"[A-Z_]{1,80}", code) else "ENGINE_OPERATION_FAILED",
                            409 if code == "RESOURCE_CONFLICT" else 503, resources=resources)
        return result["result"]

    def capability(self) -> dict[str, Any]:
        try:
            return self._request("capability")
        except (OSError, ValueError, SlamError):
            return {"supported_in_source": True, "installed": None, "available_now": False,
                    "software_verified": False, "hardware_verified": False,
                    "blocked_reason": "BROKER_UNAVAILABLE", "tasks": ["tracking", "mapping"]}

    def preflight(self, task: str) -> None:
        self._request("preflight", task=task)

    def start(self, session: dict[str, Any], cancel: threading.Event) -> dict[str, Any]:
        return self._request("start", session=session, cancel=cancel)

    def stop(self, session: dict[str, Any]) -> None:
        self._request("stop", session=session)

    def status(self, session: dict[str, Any]) -> dict[str, Any]:
        return self._request("status", session=session)

    def frame(self, session: dict[str, Any]) -> dict[str, Any]:
        return self._request("frame", session=session)

    def save(self, session: dict[str, Any], native_path: Path) -> dict[str, Any]:
        return self._request("save", session=session, native_path=str(native_path))

    def localize(self, session: dict[str, Any], native_path: Path, hint: dict[str, Any]) -> dict[str, Any]:
        return self._request("localize", session=session, native_path=str(native_path), hint=hint)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", required=True, type=Path)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--package-root", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--camera-handoff", required=True, type=Path)
    parser.add_argument("--camera-lock", required=True, type=Path)
    args = parser.parse_args()
    # This is a separate service process, never the operational dashboard.
    for key in ("CYCLONEDDS_URI", "FASTDDS_DEFAULT_PROFILES_FILE", "FASTRTPS_DEFAULT_PROFILES_FILE"):
        os.environ.pop(key, None)
    os.environ.update(ROS_LOCALHOST_ONLY="1", RMW_IMPLEMENTATION="rmw_fastrtps_cpp")
    os.umask(0o077)
    from .slam_ros_runtime import IsaacStereoAdapter
    adapter = IsaacStereoAdapter(Path(__file__).resolve().parents[1], args.runtime_root,
                                  enabled=True, config_path=args.config)
    camera = CameraOwnerCoordinator(args.camera_lock, args.camera_handoff)
    dispatcher = BrokerDispatcher(adapter, camera, args.package_root)
    with BrokerServer(args.socket, dispatcher) as server:
        def request_shutdown(_signum: int, _frame: Any) -> None:
            def settle() -> None:
                import time
                dispatcher._cancel.set()
                deadline = time.monotonic() + 60
                while dispatcher._running_operation and time.monotonic() < deadline:
                    time.sleep(0.1)
                with dispatcher._lock:
                    owned = dict(dispatcher._owned) if dispatcher._owned else None
                try:
                    if owned:
                        dispatcher.dispatch({"operation": "stop", "session": owned})
                        dispatcher.dispatch({"operation": "release_camera", "session": owned})
                except Exception:
                    # Keep the service and its reservation alive for operator
                    # recovery instead of freeing the lock under a live child.
                    return
                server.shutdown()
            threading.Thread(target=settle, daemon=True).start()
        signal.signal(signal.SIGTERM, request_shutdown)
        signal.signal(signal.SIGINT, request_shutdown)
        server.serve_forever(poll_interval=0.5)
    if args.socket.is_socket():
        args.socket.unlink()


if __name__ == "__main__":
    main()
