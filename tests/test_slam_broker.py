"""SYNTHETIC broker tests over real private AF_UNIX sockets; no ROS runtime.

Peer UID is an explicit injected fixture for portable macOS/Linux testing. The
separate unsupported/foreign-credential cases verify authentication fails closed.
"""

from copy import deepcopy
import json
import os
from pathlib import Path
import socket
import socketserver
import tempfile
import threading
import unittest
from unittest.mock import patch

from robot_dashboard.slam_broker import (
    MAX_REQUEST, MAX_RESPONSE, BrokerDispatcher, BrokerIsaacAdapter, BrokerServer,
)
from robot_dashboard.slam_camera import (
    CameraBusy, CameraOwnerCoordinator, acquire_producer_lock, release_producer_lock,
)
from robot_dashboard.slam_sessions import SlamError


SESSION = dict(session_id="a"*32, generation=3, map_epoch="b"*32,
               engine_id="visual_stereo", task="mapping")
HINT = dict(frame_id="map", position=[1., 2., 3.],
            quaternion_xyzw=[0., 0., 0., 1.], operator_verified=True)


class SyntheticBrokerEngine:
    def __init__(self):
        self.calls = []
        self.stop_error = None
        self.start_error = None
        self.save_error = None
        self.block_start = False
        self.start_entered = threading.Event()
        self.frame_value = dict(session_id=SESSION["session_id"], generation=3,
            map_epoch=SESSION["map_epoch"], source_timestamp_ns="1792026000123456789",
            provenance="synthetic_fixture", global_map={"points": [[1, 2, 3]], "coverage": "unknown"})

    def capability(self):
        return dict(available_now=True, installed=True, tasks=["tracking", "mapping"],
                    provenance="synthetic_fixture")

    def preflight(self, task):
        self.calls.append(("preflight", task))

    def start(self, session, cancel):
        self.calls.append(("start", session["session_id"]))
        self.start_entered.set()
        if self.start_error:
            raise self.start_error
        if self.block_start and not cancel.wait(3):
            raise RuntimeError("synthetic start gate timed out")
        if cancel.is_set():
            raise SlamError("START_CANCELLED")
        return {"ready": True, "effective_mode": "synthetic-slam"}

    def stop(self, session):
        self.calls.append(("stop", session["session_id"]))
        if self.stop_error:
            raise self.stop_error

    def status(self, session):
        return dict(ready=True, alive=True, provenance="synthetic_fixture")

    def frame(self, session):
        return deepcopy(self.frame_value)

    def save(self, session, native_path):
        self.calls.append(("save", native_path))
        if self.save_error:
            raise self.save_error
        (native_path / "fixture.native").write_bytes(b"SYNTHETIC official save output")
        return dict(official_save_completed=True, required_native_files=["fixture.native"],
                    data_provenance="synthetic_fixture")

    def localize(self, session, native_path, hint):
        self.calls.append(("localize", native_path))
        return dict(native_load="SUCCEEDED", localize_success=True,
                    provenance="synthetic_fixture")


class SlamBrokerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="rs-broker-", dir="/private/tmp")
        self.root = Path(self.temporary.name)
        self.package_root = self.root / "packages"
        self.package_root.mkdir(mode=0o700)
        self.handoff = self.root / "handoff.json"
        self.handoff.write_text(json.dumps(dict(checked_at_epoch=1000, relay_released=True,
            lock_protocol="robot-scope-camera-v1", devices=["/dev/video99"])))
        self.handoff.chmod(0o600)
        self.camera_lock = self.root / "camera.lock"
        self.camera = CameraOwnerCoordinator(self.camera_lock, self.handoff,
            owner_probe=lambda _: True, wall_clock=lambda: 1100)
        self.engine = SyntheticBrokerEngine()
        self.dispatcher = BrokerDispatcher(self.engine, self.camera, self.package_root)
        self.socket_path = self.root / "observer.sock"
        self.peer = patch("robot_dashboard.slam_broker.peer_uid", return_value=os.geteuid(), create=True)
        self.peer_mock = self.peer.start()
        self.server = BrokerServer(self.socket_path, self.dispatcher)
        self.worker = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": 0.01}, daemon=True)
        self.worker.start()
        self.proxy = BrokerIsaacAdapter(self.socket_path)

    def tearDown(self):
        self.dispatcher._cancel.set()
        self.engine.stop_error = None
        owned = self.dispatcher._owned
        if owned:
            self.dispatcher.dispatch({"operation": "release_camera", "session": dict(owned)})
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(2)
        self.peer.stop()
        self.temporary.cleanup()

    def reserve(self):
        self.proxy.camera_coordinator.acquire(SESSION)

    def native_dir(self, group="staging", token="c"*32):
        parent = self.package_root / group
        parent.mkdir(mode=0o700, exist_ok=True)
        current = parent / token
        current.mkdir(mode=0o700, exist_ok=True)
        native = current / "native"
        native.mkdir(mode=0o700, exist_ok=True)
        return native

    def raw(self, payload):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(2)
            connection.connect(str(self.socket_path))
            connection.sendall(payload)
            result = bytearray()
            while b"\n" not in result:
                chunk = connection.recv(65536)
                if not chunk:
                    break
                result.extend(chunk)
            return bytes(result)

    def assert_code(self, code, callback):
        with self.assertRaises(SlamError) as raised:
            callback()
        self.assertEqual(raised.exception.code, code)
        self.assertNotIn(str(self.root), str(raised.exception))

    def test_capability_and_preflight_never_acquire_camera_or_start_engine(self):
        self.assertTrue(self.proxy.capability()["available_now"])
        self.proxy.preflight("mapping")
        self.assertEqual(self.engine.calls, [("preflight", "mapping")])
        self.assertFalse(self.camera.snapshot()["reserved"])
        self.assertIsNone(self.dispatcher._owned)

    def test_operation_allowlist_and_operation_specific_extra_fields(self):
        self.assert_code("INVALID_BROKER_REQUEST", lambda: self.dispatcher.dispatch({"operation": "exec"}))
        for request in ({"operation": "capability", "argv": ["shell"]},
                        {"operation": "capability", "native_path": "/tmp"},
                        {"operation": "preflight", "task": "mapping", "hint": HINT}):
            with self.subTest(request=request):
                self.assert_code("INVALID_BROKER_REQUEST", lambda: self.dispatcher.dispatch(request))
        self.assertEqual(self.engine.calls, [])

    def test_session_validation_and_old_generation_cannot_steal_ownership(self):
        for change in (dict(generation=True), dict(generation=0), dict(generation=2**31),
                       dict(engine_id="lidar_fastlio"), dict(task="shell"),
                       dict(session_id="../../escape"), dict(map_epoch="unknown")):
            with self.subTest(change=change):
                self.assert_code("INVALID_SESSION", lambda: self.dispatcher.dispatch(
                    {"operation": "reserve_camera", "session": SESSION | change}))
        self.reserve()
        for session in (SESSION | dict(generation=2), SESSION | dict(session_id="f"*32),
                        SESSION | dict(map_epoch="f"*32)):
            with self.subTest(session=session):
                self.assert_code("SESSION_GENERATION_CONFLICT", lambda: self.proxy.status(session))
        self.assertTrue(self.camera.snapshot()["reserved"])

    def test_reservation_is_idempotent_and_survives_proxy_client_disconnect(self):
        self.reserve()
        # Every proxy request opens/closes a real socket. Its physical lock is
        # owned by the broker and survives clients and adapter object lifetimes.
        replacement_proxy = BrokerIsaacAdapter(self.socket_path)
        replacement_proxy.camera_coordinator.acquire(SESSION)
        self.assertEqual(self.dispatcher._owned, SESSION)
        with self.assertRaises(CameraBusy):
            acquire_producer_lock(self.camera_lock)
        self.assert_code("CAMERA_BUSY", lambda: replacement_proxy.camera_coordinator.acquire(
            SESSION | dict(session_id="d"*32)))
        self.assertTrue(replacement_proxy.capability()["camera"]["reserved"])

    def test_start_stop_and_release_confirm_child_cleanup_before_unlocking(self):
        self.reserve()
        result = self.proxy.start(SESSION, threading.Event())
        self.assertEqual(result["effective_mode"], "synthetic-slam")
        self.proxy.stop(SESSION)
        self.assertTrue(self.camera.snapshot()["reserved"])
        self.proxy.camera_coordinator.release(SESSION)
        self.assertFalse(self.camera.snapshot()["reserved"])
        self.assertIsNone(self.dispatcher._owned)
        self.assertEqual(len([c for c in self.engine.calls if c[0] == "stop"]), 2)

    def test_lost_reserve_ack_is_reconciled_against_real_broker_owner(self):
        original = self.proxy._request
        def lose_reserve_response(operation, **values):
            result = original(operation, **values)
            if operation == "reserve_camera":
                raise SlamError("BROKER_TIMEOUT", 503)
            return result
        with patch.object(self.proxy, "_request", side_effect=lose_reserve_response):
            self.assert_code("BROKER_TIMEOUT", self.reserve)
            snapshot = self.proxy.camera_coordinator.snapshot()
            self.assertTrue(snapshot["reserved"])
            self.assertTrue(snapshot["reservation_unknown"])
            self.assertEqual(self.dispatcher._owned, SESSION)
            with self.assertRaises(CameraBusy):
                acquire_producer_lock(self.camera_lock)
            self.proxy.camera_coordinator.release_if_owned(SESSION)
        self.assertIsNone(self.dispatcher._owned)
        self.assertFalse(self.camera.snapshot()["reserved"])
        self.assertFalse(self.proxy.camera_coordinator.snapshot()["reservation_unknown"])
        fd = acquire_producer_lock(self.camera_lock)
        release_producer_lock(fd)

    def test_lost_release_ack_can_retry_without_releasing_another_owner(self):
        self.reserve()
        original = self.proxy._request
        lost = False
        def lose_first_release_response(operation, **values):
            nonlocal lost
            result = original(operation, **values)
            if operation == "release_camera" and not lost:
                lost = True
                raise SlamError("BROKER_TIMEOUT", 503)
            return result
        with patch.object(self.proxy, "_request", side_effect=lose_first_release_response):
            self.assert_code("BROKER_TIMEOUT", lambda: self.proxy.camera_coordinator.release(SESSION))
            self.assertIsNone(self.dispatcher._owned)
            self.assertFalse(self.camera.snapshot()["reserved"])
            self.assertTrue(self.proxy.camera_coordinator.snapshot()["reserved"])
            self.assertTrue(self.proxy.camera_coordinator.snapshot()["reservation_unknown"])
            self.proxy.camera_coordinator.release(SESSION)
        self.assertFalse(self.proxy.camera_coordinator.snapshot()["reserved"])
        self.assertEqual(len([c for c in self.engine.calls if c[0] == "stop"]), 1)

    def test_uncertain_cleanup_confirmed_foreign_owner_is_left_untouched(self):
        self.reserve()
        replacement = BrokerIsaacAdapter(self.socket_path)
        foreign = SESSION | dict(session_id="d"*32)
        self.assert_code("CAMERA_BUSY", lambda: replacement.camera_coordinator.acquire(foreign))
        self.assertTrue(replacement.camera_coordinator.snapshot()["reservation_unknown"])
        replacement.camera_coordinator.release_if_owned(foreign)
        self.assertFalse(replacement.camera_coordinator.snapshot()["reserved"])
        self.assertFalse(replacement.camera_coordinator.snapshot()["reservation_unknown"])
        self.assertEqual(self.dispatcher._owned, SESSION)
        self.assertTrue(self.camera.snapshot()["reserved"])
        self.assertEqual(self.engine.calls, [])
        with self.assertRaises(CameraBusy):
            acquire_producer_lock(self.camera_lock)

    def test_unreachable_cleanup_retains_uncertain_reservation(self):
        with patch.object(self.proxy, "_request", side_effect=SlamError("BROKER_TIMEOUT", 503)):
            self.assert_code("BROKER_TIMEOUT", self.reserve)
            self.assert_code("BROKER_TIMEOUT", lambda: self.proxy.camera_coordinator.release_if_owned(SESSION))
        snapshot = self.proxy.camera_coordinator.snapshot()
        self.assertTrue(snapshot["reserved"])
        self.assertTrue(snapshot["reservation_unknown"])
        self.assertFalse(snapshot["rgb_available"])
        self.assertEqual(snapshot["session_id"], SESSION["session_id"])

    def test_cleanup_child_failure_keeps_physical_camera_reserved(self):
        self.reserve()
        self.engine.stop_error = RuntimeError("/private/native/process still alive")
        self.assert_code("ENGINE_OPERATION_FAILED", lambda: self.proxy.camera_coordinator.release(SESSION))
        self.assertTrue(self.camera.snapshot()["reserved"])
        self.assertTrue(self.proxy.camera_coordinator.snapshot()["reserved"])
        self.assertEqual(self.dispatcher._owned, SESSION)
        with self.assertRaises(CameraBusy):
            acquire_producer_lock(self.camera_lock)

    def test_start_failure_does_not_implicitly_release_camera_under_a_child(self):
        self.reserve()
        self.engine.start_error = RuntimeError("/private/native/start failed")
        self.assert_code("ENGINE_OPERATION_FAILED", lambda: self.proxy.start(SESSION, threading.Event()))
        self.assertTrue(self.camera.snapshot()["reserved"])
        self.assertEqual(self.dispatcher._owned, SESSION)

    def test_busy_operation_rejects_save_stop_release_and_cancel_remains_available(self):
        self.reserve()
        self.engine.block_start = True
        errors = []
        def start():
            try:
                self.proxy.start(SESSION, threading.Event())
            except Exception as exc:
                errors.append(exc)
        worker = threading.Thread(target=start, daemon=True)
        worker.start()
        self.assertTrue(self.engine.start_entered.wait(2))
        try:
            for operation in ("stop", "release_camera", "save"):
                with self.subTest(operation=operation):
                    self.assert_code("OPERATION_IN_PROGRESS", lambda: self.proxy._request(
                        operation, session=SESSION, **({"native_path": str(self.native_dir())} if operation == "save" else {})))
            self.proxy._request("cancel", session=SESSION)
        finally:
            self.dispatcher._cancel.set()
            worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].code, "START_CANCELLED")
        self.assertTrue(self.camera.snapshot()["reserved"])

    def test_proxy_cancellation_reaches_running_broker_operation(self):
        self.reserve()
        self.engine.block_start = True
        cancel = threading.Event()
        errors = []
        def start():
            try:
                self.proxy.start(SESSION, cancel)
            except Exception as exc:
                errors.append(exc)
        worker = threading.Thread(target=start, daemon=True)
        worker.start()
        self.assertTrue(self.engine.start_entered.wait(2))
        cancel.set()
        worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].code, "START_CANCELLED")
        self.assertTrue(self.camera.snapshot()["reserved"])

    def test_native_paths_are_private_server_staging_and_scratch_only(self):
        self.reserve()
        staging, scratch = self.native_dir(), self.native_dir("scratch")
        result = self.proxy.save(SESSION, staging)
        self.assertTrue(result["official_save_completed"])
        self.assertEqual((staging / "fixture.native").read_bytes(), b"SYNTHETIC official save output")
        result = self.proxy.localize(SESSION, scratch, HINT)
        self.assertTrue(result["localize_success"])
        for path in (self.root, self.package_root / "packages" / ("c"*32) / "native", scratch,
                     Path("/tmp/unapproved"), staging / ".."):
            with self.subTest(path=path):
                self.assert_code("INVALID_NATIVE_PATH", lambda: self.proxy.save(SESSION, path))
        self.assert_code("INVALID_NATIVE_PATH", lambda: self.proxy.localize(SESSION, staging, HINT))

    def test_native_path_symlink_unsafe_directory_and_root_are_rejected(self):
        self.reserve()
        native = self.native_dir()
        native.chmod(0o755)
        self.assert_code("INVALID_NATIVE_PATH", lambda: self.proxy.save(SESSION, native))
        native.chmod(0o700)
        self.package_root.chmod(0o777)
        try:
            self.assert_code("INVALID_NATIVE_PATH", lambda: self.proxy.save(SESSION, native))
        finally:
            self.package_root.chmod(0o700)
        native.rmdir()
        target = self.root / "external-native"
        target.mkdir(mode=0o700)
        native.symlink_to(target)
        self.assert_code("INVALID_NATIVE_PATH", lambda: self.proxy.save(SESSION, native))
        self.assertFalse(any(c[0] == "save" for c in self.engine.calls))

    def test_native_errors_are_sanitized_and_invalid_hints_never_reach_engine(self):
        self.reserve()
        self.engine.save_error = RuntimeError(str(self.root / "secret.env"))
        self.assert_code("ENGINE_OPERATION_FAILED", lambda: self.proxy.save(SESSION, self.native_dir()))
        self.assert_code("POSE_HINT_REQUIRED", lambda: self.proxy.localize(SESSION, self.native_dir("scratch"), {}))
        self.assertFalse(any(c[0] == "localize" for c in self.engine.calls))

    def test_foreign_or_unavailable_peer_uid_is_denied_before_dispatch(self):
        for uid in (os.geteuid()+1, None):
            with self.subTest(uid=uid):
                self.peer_mock.return_value = uid
                try:
                    response = self.raw(b'{"operation":"capability"}\n')
                except (BrokenPipeError, ConnectionResetError):
                    response = b""  # Peer may close before the client writes.
                self.assertEqual(response, b"")
        self.assertEqual(self.engine.calls, [])

    def test_private_socket_permissions_parent_and_existing_socket_are_enforced(self):
        with self.assertRaisesRegex(SlamError, "BROKER_SOCKET_EXISTS"):
            BrokerServer(self.socket_path, self.dispatcher)
        self.socket_path.chmod(0o666)
        try:
            self.assert_code("UNSAFE_BROKER_SOCKET", lambda: self.proxy.preflight("mapping"))
            self.assertFalse(self.proxy.capability()["available_now"])
        finally:
            self.socket_path.chmod(0o600)
        unsafe = self.root / "unsafe"
        unsafe.mkdir(mode=0o755)
        self.assert_code("UNSAFE_BROKER_SOCKET", lambda: BrokerServer(unsafe / "socket", self.dispatcher))

    def test_protocol_rejects_oversize_malformed_and_nonfinite_requests(self):
        response = json.loads(self.raw(b"x"*(MAX_REQUEST+1)+b"\n"))
        self.assertEqual(response["code"], "INVALID_BROKER_REQUEST")
        for payload in (b"not-json\n", b'{"operation":NaN}\n'):
            response = json.loads(self.raw(payload))
            self.assertFalse(response["ok"])
            self.assertNotIn(str(self.root), json.dumps(response))
        self.assert_code("INVALID_BROKER_REQUEST", lambda: self.proxy._request("preflight", task="x"*MAX_REQUEST))

    def test_response_limit_and_exact_nanosecond_stamp_are_preserved(self):
        self.reserve()
        frame = self.proxy.frame(SESSION)
        self.assertEqual(frame["source_timestamp_ns"], "1792026000123456789")
        self.engine.frame_value = {"payload": "x"*MAX_RESPONSE}
        self.assert_code("VISUALIZATION_LIMIT", lambda: self.proxy.frame(SESSION))

    def test_localize_epoch_rotation_rejects_old_epoch_status(self):
        self.reserve()
        rotated = SESSION | dict(map_epoch="e"*32)
        result = self.proxy.localize(rotated, self.native_dir("scratch"), HINT)
        self.assertTrue(result["localize_success"])
        self.assertEqual(self.dispatcher._owned["map_epoch"], "e"*32)
        self.assert_code("SESSION_GENERATION_CONFLICT", lambda: self.proxy.status(SESSION))
        self.assertTrue(self.proxy.status(rotated)["alive"])

    def test_proxy_rejects_malformed_response_envelope_without_leaking_parser_exceptions(self):
        class MalformedResponse(socketserver.BaseRequestHandler):
            def handle(self):
                self.request.recv(MAX_REQUEST)
                self.request.sendall(self.server.synthetic_response)
        self.server.RequestHandlerClass = MalformedResponse
        for response in (b"[]\n", b'{"ok":true}\n', b'{"ok":true,"result":NaN}\n',
                         b'{"ok":true,"result":[]}\n',
                         b'{"ok":true,"result":{}}\n{"second":true}\n'):
            with self.subTest(response=response):
                self.server.synthetic_response = response
                self.assert_code("INVALID_BROKER_RESPONSE", lambda: self.proxy.preflight("mapping"))


if __name__ == "__main__":
    unittest.main()
