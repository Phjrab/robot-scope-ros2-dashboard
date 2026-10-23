"""Resource contract fixtures; no systemd, sensor or native numerical worker."""
from __future__ import annotations

import gc
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock

from robot_dashboard.relocalization import native_observation_scope as scope
from robot_dashboard.relocalization import native_observation_scope_admission as admission
from robot_dashboard.relocalization import external_global_observation as global_subject
from robot_dashboard.relocalization import sensor_tracking_process as sensor_subject
import test_external_global_observation as global_fixtures
import test_sensor_tracking_process as sensor_fixtures


UNIT = "robot-scope-sensor-" + "a" * 32 + ".scope"


class ResourceBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cgroup = self.root / "user.slice/app.slice" / UNIT
        self.cgroup.mkdir(parents=True)
        for name, value in admission.LIMITS.items():
            (self.cgroup / name).write_text(value)
        (self.cgroup / "memory.oom.group").write_text("0")
        (self.root / "cpu.max").write_text("max 100000")
        self.proc = self.root / "proc-cgroup"
        self.proc.write_text("0::/user.slice/app.slice/" + UNIT + "\n")

    def read(self):
        return admission.read_boundary(UNIT, proc_cgroup=self.proc, cgroup_root=self.root)

    def test_missing_scope_cpu_controller_is_allowed_with_explicit_ancestor_readback(self):
        value = self.read()
        self.assertIsNone(value["cpu_max"])
        self.assertFalse(value["cpu_controller_delegated"])
        self.assertEqual(value["ancestor_cpu_max"]["."], "max 100000")
        self.assertFalse(value["oom_atomic_group_kill"])
        self.assertEqual(value["memory_oom_group"], "0")
        self.assertEqual(value["limits"], admission.LIMITS)

    def test_wrong_memory_swap_or_task_limit_fails_before_any_worker(self):
        for name in admission.LIMITS:
            with self.subTest(name=name):
                (self.cgroup / name).write_text("max")
                with self.assertRaisesRegex(ValueError, "BOUNDARY_MISMATCH"):
                    self.read()
                (self.cgroup / name).write_text(admission.LIMITS[name])

    def test_scope_cpu_quota_rejected_but_inherited_limit_is_reported(self):
        (self.cgroup / "cpu.max").write_text("100000 100000")
        with self.assertRaisesRegex(ValueError, "CPU_QUOTA_FORBIDDEN"):
            self.read()
        (self.cgroup / "cpu.max").write_text("max 100000")
        (self.root / "cpu.max").write_text("200000 100000")
        self.assertEqual(self.read()["ancestor_cpu_max"]["."], "200000 100000")

    def test_wrong_unit_traversal_or_hybrid_hierarchy_rejected(self):
        for text in ("0::/user.slice/wrong.scope\n", "0::/../" + UNIT + "\n", "1:memory:/x\n0::/" + UNIT):
            with self.subTest(text=text):
                self.proc.write_text(text)
                with self.assertRaises(ValueError):
                    self.read()

    def test_atomic_private_json_never_publishes_partial_target_or_overwrites(self):
        target = self.root / "control.json"
        link = os.link

        def inspect_link(source, destination, **kwargs):
            self.assertFalse(target.exists())
            self.assertEqual(json.loads(Path(source).read_text()), {"ready": True})
            return link(source, destination, **kwargs)

        with mock.patch.object(admission.os, "link", side_effect=inspect_link):
            admission.private_json(target, {"ready": True})
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            admission.private_json(target, {"different": True})
        self.assertEqual(json.loads(target.read_text()), {"ready": True})
        self.assertEqual(list(self.root.glob(".control.json.*")), [])


class ScopeLaunchTests(unittest.TestCase):
    def test_exact_scope_argv_has_no_extra_cpu_quota_or_unsupported_service_oom_property(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            worker = folder / "sensor_tracking_worker.py"
            worker.write_text("# fixture; never executed\n")
            argv, spec = scope.build_scope_command(python=Path(sys.executable), bootstrap=Path(admission.__file__),
                worker=worker, workdir=folder, kind="sensor", socket_fd=9, nonce="a" * 32)
        self.assertIn("--user", argv)
        self.assertIn("--scope", argv)
        self.assertIn("--property=MemoryMax=2147483648", argv)
        self.assertIn("--property=MemorySwapMax=0", argv)
        self.assertIn("--property=TasksMax=64", argv)
        self.assertIn("--property=RuntimeMaxSec=60s", argv)
        self.assertFalse(any("CPUQuota" in x or "OOMPolicy" in x or x == "--wait" for x in argv))
        self.assertEqual(spec["unit"], UNIT)
        self.assertEqual(spec["worker"], str(worker))
        self.assertEqual(argv[-2:], ["--socket-fd", "9"])

    def test_explicit_resource_mode_and_invalid_spellings(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(scope.resource_mode_from_environment())
        with mock.patch.dict(os.environ, {scope.RESOURCE_MODE_ENV: "user_scope_v1"}, clear=True):
            self.assertTrue(scope.resource_mode_from_environment())
        for value in ("true", "1", "disabled", ""):
            with mock.patch.dict(os.environ, {scope.RESOURCE_MODE_ENV: value}, clear=True):
                with self.assertRaises(ValueError):
                    scope.resource_mode_from_environment()

    def test_cancelled_or_exited_admission_never_writes_ack(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = {"unit": UNIT, "nonce": "a" * 32, "workdir": tmp}
            cancel = threading.Event()
            cancel.set()
            with self.assertRaisesRegex(ValueError, "CANCELLED"):
                scope.wait_and_ack(SimpleNamespace(poll=lambda: None), spec, cancel=cancel, deadline=float("inf"))
            with self.assertRaisesRegex(ValueError, "EXITED_NO_NATIVE_IMPORT"):
                scope.wait_and_ack(SimpleNamespace(poll=lambda: 1), spec, cancel=None, deadline=float("inf"))
            self.assertEqual(list(Path(tmp).glob("*ack*")), [])

    def test_successful_close_is_cached_and_never_signals_recycled_pid_or_pgid(self):
        owned = scope.NativeObservationScope.__new__(scope.NativeObservationScope)
        owned._lock = threading.Lock()
        owned._settled = False
        owned.specification = {"unit": UNIT}
        owned.proof = None
        owned.process = mock.Mock(pid=123)
        owned.process.poll.return_value = 0
        owned._systemctl = mock.Mock(return_value=SimpleNamespace(stdout="LoadState=not-found\nActiveState=inactive\nControlGroup=\n"))
        with mock.patch.object(scope.os, "killpg") as group_kill:
            self.assertTrue(owned.close())
            calls = list(owned._systemctl.call_args_list)
            self.assertTrue(owned.close())
            self.assertEqual(owned._systemctl.call_args_list, calls)
            owned.process.send_signal.assert_not_called()
            group_kill.assert_not_called()
        for call in calls:
            self.assertEqual(call.args[-1], UNIT)

    def test_nonempty_cgroup_is_not_settled_and_retry_can_confirm_empty(self):
        owned = scope.NativeObservationScope.__new__(scope.NativeObservationScope)
        owned._lock = threading.Lock()
        owned._settled = False
        owned.specification = {"unit": UNIT}
        owned.proof = {"control_group": "/user.slice/" + UNIT}
        owned.process = mock.Mock(pid=123)
        owned.process.poll.return_value = 0
        owned._systemctl = mock.Mock(return_value=SimpleNamespace(stdout="LoadState=loaded\nActiveState=inactive\nControlGroup=/user.slice/" + UNIT + "\n"))
        with mock.patch.object(Path, "read_text", return_value="populated 1\n"):
            self.assertFalse(owned.close())
        self.assertFalse(owned._settled)
        with mock.patch.object(Path, "read_text", return_value="populated 0\n"):
            self.assertTrue(owned.close())

    def test_retained_directory_survives_owner_gc_and_explicit_cleanup_removes_it(self):
        folder = scope.ScopeWorkDirectory(prefix="robot-scope-retain-fixture-")
        name = Path(folder.name)
        with folder:
            folder.retain = True
            (name / "owned-input").write_text("retained")
        del folder
        gc.collect()
        self.assertEqual((name / "owned-input").read_text(), "retained")
        recovered = scope.ScopeWorkDirectory.__new__(scope.ScopeWorkDirectory)
        recovered.name = str(name)
        recovered.cleanup()
        self.assertFalse(name.exists())

    def test_manager_requires_effective_finite_runtime_and_exact_active_scope(self):
        owned = scope.NativeObservationScope.__new__(scope.NativeObservationScope)
        owned.specification = {"unit": UNIT, "runtime_s": 60}
        proof = {"control_group": "/user.slice/app.slice/" + UNIT}
        def output(runtime="1min", **overrides):
            props = {"RuntimeMaxUSec": runtime, "Transient": "yes", "ActiveState": "active",
                     "ControlGroup": proof["control_group"], "Delegate": "no", **overrides}
            return SimpleNamespace(returncode=0, stdout="\n".join(k + "=" + v for k, v in props.items()))
        for runtime in ("1min", "60s", "60000ms", "0.5min 30s"):
            owned._systemctl = mock.Mock(return_value=output(runtime))
            self.assertEqual(owned._read_manager_properties(proof)["RuntimeMaxUSec"], runtime)
        for bad in (output("infinity"), output("0"), output(""), output("59s"),
                    output(Transient="no"), output(ActiveState="inactive"), output(Delegate="yes"),
                    output(ControlGroup="/other/" + UNIT)):
            with self.subTest(output=bad.stdout):
                owned._systemctl = mock.Mock(return_value=bad)
                with self.assertRaisesRegex(ValueError, "RUNTIME_READBACK|MANAGER_POLICY"):
                    owned._read_manager_properties(proof)

    def _admission_fixture(self, folder):
        worker = folder / "sensor_tracking_worker.py"
        worker.write_text("# no numerical worker is run by this fixture\n")
        _, spec = scope.build_scope_command(python=Path(sys.executable), bootstrap=Path(admission.__file__),
            worker=worker, workdir=folder, kind="sensor", socket_fd=9, nonce="a" * 32)
        boundary = {"control_group": "/user.slice/app.slice/" + UNIT, "limits": admission.LIMITS,
                    "cpu_max": None, "memory_oom_group": "0", "oom_atomic_group_kill": False,
                    "cpu_controller_delegated": False, "ancestor_cpu_max": {".": "max 100000"},
                    "cpu_ancestor_quota_observed": True}
        proof = {"schema": "robot-scope.native-scope-admission.v1", "unit": UNIT,
                 "nonce": spec["nonce"], "kind": "sensor", "worker_sha256": spec["worker_sha256"],
                 "socket_fd": 9, "uid": 1000, "pid": 123, "pgid": 123, "sid": 123,
                 "native_import_performed": False, **boundary}
        process = SimpleNamespace(pid=123, poll=lambda: None)
        return spec, boundary, proof, process

    def test_successful_parent_admission_none_cancel_checks_kernel_manager_then_acks(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp).resolve()
            spec, boundary, proof, process = self._admission_fixture(folder)
            admission.private_json(folder / ("resource-proof-" + spec["nonce"] + ".json"), proof)
            original_read, original_stat = Path.read_text, Path.stat
            def read(path, *args, **kwargs):
                return "0::" + proof["control_group"] + "\n" if str(path) == "/proc/123/cgroup" else original_read(path, *args, **kwargs)
            def stat(path, *args, **kwargs):
                return SimpleNamespace(st_uid=1000) if str(path) == "/proc/123" else original_stat(path, *args, **kwargs)
            manager = mock.Mock(return_value={"RuntimeMaxUSec": "1min"})
            with mock.patch.object(Path, "read_text", read), mock.patch.object(Path, "stat", stat), \
                    mock.patch.object(scope.os, "getpgid", return_value=123), \
                    mock.patch.object(scope.os, "getsid", return_value=123), \
                    mock.patch.object(scope, "read_boundary", return_value=boundary):
                result = scope.wait_and_ack(process, spec, cancel=None, deadline=time.monotonic() + 1,
                                            manager_readback=manager)
            manager.assert_called_once_with(proof)
            self.assertEqual(result["manager_properties"], {"RuntimeMaxUSec": "1min"})
            ack = admission.read_private_json(folder / ("resource-ack-" + spec["nonce"] + ".json"))
            self.assertEqual(ack["pid"], 123)
            self.assertEqual(ack["nonce"], spec["nonce"])

    def test_changed_worker_or_wrong_proof_pid_never_acks(self):
        for mismatch in ("worker", "pid"):
            with self.subTest(mismatch=mismatch), tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp).resolve()
                spec, boundary, proof, process = self._admission_fixture(folder)
                if mismatch == "pid":
                    proof["pid"] = 124
                else:
                    Path(spec["worker"]).write_text("# changed before ACK\n")
                admission.private_json(folder / ("resource-proof-" + spec["nonce"] + ".json"), proof)
                original_read, original_stat = Path.read_text, Path.stat
                def read(path, *args, **kwargs):
                    return "0::" + proof["control_group"] + "\n" if str(path) == "/proc/123/cgroup" else original_read(path, *args, **kwargs)
                def stat(path, *args, **kwargs):
                    return SimpleNamespace(st_uid=1000) if str(path) == "/proc/123" else original_stat(path, *args, **kwargs)
                with mock.patch.object(Path, "read_text", read), mock.patch.object(Path, "stat", stat), \
                        mock.patch.object(scope.os, "getpgid", return_value=123), \
                        mock.patch.object(scope.os, "getsid", return_value=123), \
                        mock.patch.object(scope, "read_boundary", return_value=boundary):
                    with self.assertRaisesRegex(ValueError, "PROOF_MISMATCH|WORKER_CHANGED"):
                        scope.wait_and_ack(process, spec, cancel=None, deadline=time.monotonic() + 1,
                                           manager_readback=mock.Mock(return_value={}))
                self.assertEqual(list(folder.glob("resource-ack-*")), [])

    def test_readback_error_leaves_scope_unsettled_for_retry(self):
        owned = scope.NativeObservationScope.__new__(scope.NativeObservationScope)
        owned._lock = threading.Lock()
        owned._settled = False
        owned._close_owned_scope = mock.Mock(side_effect=PermissionError("fixture readback denied"))
        self.assertFalse(owned.close())
        self.assertFalse(owned._settled)
        self.assertEqual(owned._close_owned_scope.call_count, 1)


class ProductScopeHookTests(unittest.TestCase):
    def test_global_scope_proof_readback_and_post_proof_envelope_limit_without_truncation(self):
        fixture = global_fixtures.ExternalGlobalObservationTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        runner = fixture.runner()
        runner.resource_scope_enabled = True
        for size in (0, 65536):
            with self.subTest(proof_size=size):
                owned = mock.Mock()
                owned.proof = {"schema": "fixture-no-kernel-scope", "trace": "r" * size}
                owned.admit.return_value = owned.proof
                def launch(**kwargs):
                    owned.process = subprocess.Popen([str(kwargs["python"]), "-I", str(kwargs["worker"]),
                        str(kwargs["folder"])], env=kwargs["environment"], stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, start_new_session=True)
                    return owned
                def stop():
                    if owned.process.poll() is None:
                        owned.process.terminate()
                    owned.process.wait(timeout=1)
                    return True
                owned.close.side_effect = stop
                with mock.patch.object(global_subject, "NativeObservationScope", side_effect=launch):
                    if size:
                        with self.assertRaisesRegex(global_subject.ExternalGlobalObservationError,
                                                    "ENVELOPED_RESULT_LIMIT_NO_TRUNCATION"):
                            fixture.run_one(runner)
                    else:
                        result = fixture.run_one(runner)
                        self.assertEqual(result["execution"]["resource_admission"], owned.proof)
                        self.assertEqual(result["input_points"], 2)
                owned.admit.assert_called_once()
                owned.close.assert_called_once()

    def test_global_failed_scope_cleanup_retains_inputs_blocks_new_run_then_retries(self):
        fixture = global_fixtures.ExternalGlobalObservationTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        runner = fixture.runner()
        runner.resource_scope_enabled = True
        child = SimpleNamespace(stdout=io.BytesIO(), stderr=io.BytesIO())
        owned = mock.Mock(process=child)
        owned.admit.side_effect = ValueError("fixture admission rejected")
        owned.close.side_effect = [False, PermissionError("fixture readback denied"), True]
        folders = []
        def launch(**kwargs):
            folders.append(kwargs["folder"])
            self.assertEqual(kwargs["kind"], "global")
            self.assertEqual(kwargs["environment"]["OMP_NUM_THREADS"], "1")
            return owned
        with mock.patch.object(global_subject, "NativeObservationScope", side_effect=launch) as constructor:
            with self.assertRaisesRegex(global_subject.ExternalGlobalObservationError, "CLEANUP_PENDING"):
                fixture.run_one(runner)
            self.assertEqual(constructor.call_count, 1)
            self.assertTrue((folders[0] / "input.json").is_file())
            self.assertTrue(child.stdout.closed)
            self.assertTrue(child.stderr.closed)
            gc.collect()
            self.assertTrue(folders[0].exists())
            with self.assertRaisesRegex(global_subject.ExternalGlobalObservationError, "CLEANUP_PENDING"):
                fixture.run_one(runner)
            self.assertEqual(constructor.call_count, 1)
            self.assertTrue(folders[0].exists())
            self.assertTrue(runner.cleanup_pending_scopes())
            self.assertFalse(folders[0].exists())

    def test_sensor_scope_hook_exposes_proof_and_retains_failed_cleanup(self):
        fixture = sensor_fixtures.SensorTrackingProcessTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        runner = sensor_fixtures.StubRunner()
        runner.resource_scope_enabled = True
        process = sensor_subject.SensorTrackingProcess(runner)
        self.addCleanup(process.close)
        proof = {"schema": "fixture-no-kernel-scope", "fixture": True}
        owned = mock.Mock()
        owned.proof = proof
        owned.admit.return_value = proof
        launched = []
        def launch(**kwargs):
            # Existing stdlib fake worker only; no ROS/systemd/native matching.
            child = subprocess.Popen([str(kwargs["python"]), "-I", str(kwargs["worker"]),
                str(kwargs["folder"]), str(kwargs["socket_fd"])], env=kwargs["environment"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                pass_fds=(kwargs["socket_fd"],), start_new_session=True)
            owned.process = child
            launched.append(child)
            return owned
        def stop_fake():
            child = launched[0]
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=1)
            return True
        self.addCleanup(lambda: stop_fake() if launched else None)
        owned.close.side_effect = lambda: launched[0].poll() is not None
        with mock.patch.object(sensor_subject, "NativeObservationScope", side_effect=launch) as constructor:
            process.start(fixture.map_bytes, fixture.context, fixture.cancel)
            self.assertEqual(process.resource_admission_snapshot(), proof)
            snapshot = process.resource_admission_snapshot()
            snapshot["fixture"] = False
            self.assertEqual(process.resource_admission_snapshot(), proof)
            folder = Path(process._folder.name)
            self.assertIsInstance(process._folder, scope.ScopeWorkDirectory)
            self.assertFalse(process.close())
            self.assertTrue(folder.exists())
            self.assertIs(process._resource_scope, owned)
            with self.assertRaisesRegex(sensor_subject.SensorTrackingError, "CLOSED|ALREADY_USED"):
                process.start(fixture.map_bytes, fixture.context, fixture.cancel)
            self.assertEqual(constructor.call_count, 1)
            # A successful retry is only simulated after the fake child is reaped.
            stop_fake()
            self.assertTrue(process.close())
            self.assertFalse(folder.exists())


if __name__ == "__main__":
    unittest.main()
