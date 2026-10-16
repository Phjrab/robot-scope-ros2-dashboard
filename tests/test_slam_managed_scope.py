"""SYNTHETIC managed policy/probe fixtures; no camera, ROS or device calls."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from robot_dashboard.slam_camera import CameraBusy, CameraOwnerCoordinator, acquire_producer_lock, release_producer_lock
from robot_dashboard.slam_managed_scope import (
    DomainReservation, ManagedScopeError, cooperative_relay_ready, load_managed_scope,
    probe_managed_camera_owner, validate_reservation_proof,
)
from robot_dashboard.slam_ros_runtime import IsaacRuntimeError, IsaacStereoAdapter
from test_isaac_vslam_launch_contract import camera_contract, input_contract


PROJECT = Path(__file__).resolve().parents[1]
SESSION = {"session_id": "synthetic-managed", "generation": 2}


class ManagedScopeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="rs-scope-", dir="/tmp")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.path = self.root / "managed-scope.json"
        self.camera_lock, self.domain_lock = self.root / "camera.lock", self.root / "domain.lock"
        relay = PROJECT / "scripts/realsense_mjpeg_relay.py"
        self.record = dict(schema_version=1, lock_protocol="robot-scope-camera-managed-v1",
            scope_id="synthetic-fixed-scope", devices=["/dev/video99"],
            camera_lock_path=str(self.camera_lock), domain_lock_path=str(self.domain_lock),
            domain_id=71, operational_domain_id=0, owner_policy="shared_flock_live_probe",
            cooperative_owners=["robot_scope_rgb_relay", "robot_scope_slam_broker"],
            relay_script_path=str(relay), relay_script_sha256=hashlib.sha256(relay.read_bytes()).hexdigest(),
            lock_helper_sha256=hashlib.sha256((PROJECT / "robot_dashboard/slam_camera.py").read_bytes()).hexdigest(),
            host_pid_namespace="pid:[123456789]")
        self.record["owner_probe_socket"] = str(self.root / "root-owner-probe.sock")
        self.write_scope()

    def write_scope(self, record=None):
        self.path.write_text(json.dumps(self.record if record is None else record))
        self.path.chmod(0o600)

    def camera(self, probe=lambda _: True, relay=lambda _: True):
        return CameraOwnerCoordinator(self.camera_lock, self.path, owner_probe=probe,
            relay_probe=relay, wall_clock=lambda: 1234.)

    def proc_fixture(self):
        proc = self.root / "proc"
        for directory in (proc / "self/ns", proc / "1/ns", proc / str(os.getpid()) / "fd"):
            directory.mkdir(parents=True, exist_ok=True)
        for namespace in (proc / "self/ns/pid", proc / "1/ns/pid"):
            namespace.symlink_to(self.record["host_pid_namespace"])
        return proc

    def test_fixed_policy_needs_no_timestamp_but_is_not_ownership_proof(self):
        scope = load_managed_scope(self.path, camera_lock_path=self.camera_lock, domain_id=71, operational_domain_id=0)
        self.assertNotIn("checked_at_epoch", scope)
        calls = []
        def probe(devices):
            calls.append(devices)
            with self.assertRaises(CameraBusy):
                acquire_producer_lock(self.camera_lock)
            return True
        camera = self.camera(probe)
        with patch("robot_dashboard.slam_camera.time.monotonic", return_value=42.):
            camera.acquire(SESSION)
        try:
            first = camera.reservation_proof(SESSION)
            with patch("robot_dashboard.slam_camera.time.monotonic", return_value=99999.):
                self.assertEqual(camera.reservation_proof(SESSION), first)
            self.assertEqual(first["checked_at_monotonic"], 42.)
            self.assertEqual(calls, [["/dev/video99"]])
        finally:
            camera.release(SESSION)
        camera.acquire(SESSION)
        camera.release(SESSION)
        self.assertEqual(len(calls), 2)

    def test_fixed_scope_mismatch_unknown_fields_and_unsafe_policy_fail_closed(self):
        for change in (dict(domain_id=0), dict(operational_domain_id=71), dict(schema_version=True),
                       dict(camera_lock_path=str(self.domain_lock)), dict(owner_policy="always_free"),
                       dict(cooperative_owners=["robot_scope_rgb_relay"]), dict(devices=["/tmp/not-device"]),
                       dict(devices=["/dev/video99"] * 2), dict(extra="command"),
                       dict(host_pid_namespace="unobserved"), dict(relay_script_sha256="unobserved")):
            with self.subTest(change=change):
                self.write_scope(self.record | change)
                with self.assertRaises(ManagedScopeError):
                    load_managed_scope(self.path)
        self.write_scope()
        with self.assertRaises(ManagedScopeError):
            load_managed_scope(self.path, domain_id=72)
        self.path.chmod(0o644)
        with self.assertRaises(ManagedScopeError):
            load_managed_scope(self.path)

    def test_each_start_rejects_uncooperative_relay_or_busy_device_without_retaining_lock(self):
        for manager, reason in ((self.camera(relay=lambda _: False), "relay_not_cooperative"),
                                (self.camera(probe=lambda _: False), "device_busy")):
            with self.subTest(reason=reason):
                with self.assertRaises(CameraBusy) as caught:
                    manager.acquire(SESSION)
                self.assertEqual(caught.exception.code, "RESOURCE_CONFLICT")
                self.assertEqual(caught.exception.resources, [{"resource": "camera", "reason": reason}])
                self.assertFalse(manager.snapshot()["reserved"])
                descriptor = acquire_producer_lock(self.camera_lock)
                release_producer_lock(descriptor)

    def test_incomplete_os_visibility_never_becomes_a_free_camera(self):
        camera = CameraOwnerCoordinator(self.camera_lock, self.path, relay_probe=lambda _: True)
        with patch("robot_dashboard.slam_managed_scope.probe_managed_camera_owner", return_value={"state": "unavailable"}):
            with self.assertRaises(CameraBusy) as caught:
                camera.acquire(SESSION)
        self.assertEqual(caught.exception.resources[0]["reason"], "owner_state_unavailable")

    def test_domain_reservation_is_exclusive_and_explicitly_released(self):
        scope = load_managed_scope(self.path)
        first, second = DomainReservation(scope), DomainReservation(scope)
        first.acquire()
        try:
            with self.assertRaises(ManagedScopeError) as caught:
                second.acquire()
            self.assertEqual(caught.exception.resources[0]["resource"], "ros_domain")
            self.assertIsNotNone(first.evidence())
        finally:
            first.release()
        second.acquire()
        second.release()

    def test_domain_conflict_prevents_native_start_and_preserves_foreign_lock(self):
        scope = load_managed_scope(self.path)
        camera, foreign = self.camera(), DomainReservation(scope)
        camera.acquire(SESSION)
        foreign.acquire()
        self.addCleanup(foreign.release)
        self.addCleanup(camera.release, SESSION)
        adapter = IsaacStereoAdapter(PROJECT, self.root / "sessions")
        adapter.bind_camera_coordinator(camera)
        config = {"_managed_scope": scope, "input_content": b"{}", "camera_content": b"{}",
                  "input_hash": "a" * 64, "managed_scope": str(self.path)}
        with patch.object(adapter, "preflight"), patch.object(adapter, "_configuration", return_value=config), \
                patch.object(adapter, "_attach_ros") as attach, patch("subprocess.Popen") as process:
            with self.assertRaises(ManagedScopeError):
                adapter.start(SESSION | dict(task="mapping"), threading.Event())
        attach.assert_not_called()
        process.assert_not_called()
        self.assertIsNone(adapter._job)
        self.assertTrue(camera.snapshot()["reserved"])
        with self.assertRaises(ManagedScopeError):
            DomainReservation(scope).acquire()

    def test_failed_observer_cleanup_does_not_release_domain_reservation(self):
        scope = load_managed_scope(self.path)
        domain = DomainReservation(scope)
        domain.acquire()
        self.addCleanup(domain.release)
        adapter = IsaacStereoAdapter(PROJECT, self.root / "sessions")
        def fail():
            raise RuntimeError("synthetic cleanup not confirmed")
        job = {"identity": (SESSION["session_id"], SESSION["generation"]),
               "node": SimpleNamespace(destroy_node=fail), "domain_reservation": domain}
        adapter._job = job
        with self.assertRaisesRegex(RuntimeError, "not confirmed"):
            adapter.stop(SESSION)
        self.assertIs(adapter._job, job)
        with self.assertRaises(ManagedScopeError):
            DomainReservation(scope).acquire()

    def test_live_proof_checks_scope_age_parent_fds_and_actual_held_locks(self):
        scope = load_managed_scope(self.path)
        camera, domain = self.camera(), DomainReservation(scope)
        camera.acquire(SESSION)
        domain.acquire()
        self.addCleanup(domain.release)
        self.addCleanup(camera.release, SESSION)
        proof = dict(camera.reservation_proof(SESSION), schema_version=1,
            evidence_kind="live_managed_reservation", domain_id=71, domain_lock=domain.evidence())
        proc = self.proc_fixture()
        for key in ("camera_lock", "domain_lock"):
            evidence = proof[key]
            (proc / str(os.getpid()) / "fd" / str(evidence["fd"])).symlink_to(evidence["path"])
        checked = proof["checked_at_monotonic"]
        validate_reservation_proof(proof, scope, monotonic=lambda: checked + 1, proc=proc)
        for change in (dict(scope_id="foreign-scope"), dict(domain_id=72),
                       dict(checked_at_monotonic=checked - 301), dict(owner_pid=-1)):
            with self.subTest(change=change), self.assertRaises(ManagedScopeError):
                validate_reservation_proof(proof | change, scope, monotonic=lambda: checked, proc=proc)
        domain.release()
        with self.assertRaises(ManagedScopeError):
            validate_reservation_proof(proof, scope, monotonic=lambda: checked, proc=proc)

    def test_host_visibility_and_exact_relay_source_are_required_even_when_no_relay_runs(self):
        scope = load_managed_scope(self.path)
        proc = self.proc_fixture()
        (proc / "stat").write_text("btime 1000\n")
        for process in proc.glob("[0-9]*"):
            (process / "cmdline").write_bytes(b"synthetic-unrelated-process\0")
        self.assertTrue(cooperative_relay_ready(scope, proc))
        self.assertFalse(cooperative_relay_ready(scope | dict(host_pid_namespace="pid:[1]"), proc))
        self.assertFalse(cooperative_relay_ready(scope | dict(relay_script_sha256="a" * 64), proc))

    def owner_probe(self, response, uid=0):
        scope = load_managed_scope(self.path)
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.getsockopt.return_value = struct.pack("3i", 123, uid, 0)
        connection.recv.return_value = json.dumps(response).encode() + b"\n"
        with patch("robot_dashboard.slam_managed_scope.socket.socket", return_value=connection), \
                patch("robot_dashboard.slam_managed_scope.socket.SO_PEERCRED", 17, create=True), \
                patch("robot_dashboard.slam_managed_scope.Path.lstat", return_value=SimpleNamespace(
                    st_mode=stat.S_IFSOCK | 0o600, st_uid=os.geteuid())), \
                patch("robot_dashboard.slam_managed_scope.time.monotonic", side_effect=[10., 12.]), \
                patch("robot_dashboard.slam_managed_scope.time.time", side_effect=[100., 102.]):
            result = probe_managed_camera_owner(scope)
        connection.sendall.assert_called_once_with(b'{"operation":"camera_owner_state"}\n')
        return result

    def test_root_owner_probe_requires_this_request_and_keeps_original_times(self):
        scope = load_managed_scope(self.path)
        response = dict(schema_version=1, devices=scope["devices"], state="free",
            checked_at_epoch=101., checked_at_monotonic=11., host_pid_namespace=scope["host_pid_namespace"])
        self.assertEqual(self.owner_probe(response), response)
        for change in (dict(checked_at_monotonic=9.), dict(checked_at_monotonic=13.),
                       dict(checked_at_epoch=99.), dict(checked_at_epoch=float("nan")),
                       dict(devices=["/dev/video1"]), dict(host_pid_namespace="pid:[1]"),
                       dict(state="always_free"), dict(extra="stderr"), dict(schema_version=True)):
            with self.subTest(change=change), self.assertRaises(ManagedScopeError):
                self.owner_probe(response | change)
        with self.assertRaises(ManagedScopeError):
            self.owner_probe(response, uid=1000)

    def test_managed_configuration_preserves_historical_sensor_timestamps_and_legacy_gate(self):
        inputs = input_contract()
        inputs["source"]["kind"], inputs["clock_domain"] = "live", "host_ros"
        camera = camera_contract()
        camera["checked_at_utc"] = "2000-01-01T00:00:00+00:00"
        for name, value in (("input", inputs), ("camera", camera)):
            path = self.root / (name + ".json")
            path.write_text(json.dumps(value))
            path.chmod(0o600)
        config = dict(managed_scope=str(self.path), domain_id=71, operational_domain_id=0,
            domain_available=False, domain_checked_at_utc="2000-01-01T00:00:00+00:00",
            input_contract=str(self.root / "input.json"), camera_contract=str(self.root / "camera.json"),
            stereo_profile="640x480x30")
        config_path = self.root / "runtime.json"
        config_path.write_text(json.dumps(config))
        config_path.chmod(0o600)
        adapter = IsaacStereoAdapter(PROJECT, self.root / "sessions", enabled=True, config_path=config_path)
        with patch.object(adapter, "capability", return_value={"available_now": True}):
            result = adapter._configuration()
            self.assertEqual(json.loads(result["camera_content"])["checked_at_utc"], camera["checked_at_utc"])
            self.assertEqual(result["domain_checked_at_utc"], config["domain_checked_at_utc"])
            unmanaged = deepcopy(config)
            unmanaged.pop("managed_scope")
            config_path.write_text(json.dumps(unmanaged))
            with self.assertRaises(IsaacRuntimeError):
                adapter._configuration()


if __name__ == "__main__":
    unittest.main()
