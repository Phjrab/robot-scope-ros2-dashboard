"""Synthetic timers/IPC only: no robot, ROS, Open3D or native registration."""
from __future__ import annotations

import os
from pathlib import Path
import signal
import threading
import time
import unittest
from types import SimpleNamespace
from unittest import mock

import test_sensor_tracking_owner as owner_fixtures
import test_sensor_tracking_process as process_fixtures
from robot_dashboard.application.sensor_tracking import SensorTrackingOwner, configure_sensor_tracking
from robot_dashboard.relocalization import sensor_tracking_process as subject


class ExecutionPolicyConfigurationTests(unittest.TestCase):
    def test_explicit_disable_and_restore_default_are_distinct_from_watchdog(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            restored = subject.SensorTrackingExecutionPolicy.from_environment().snapshot()
        with mock.patch.dict(os.environ, {subject.PROCESSING_BUDGET_ENV: "disabled"}, clear=True):
            disabled = subject.SensorTrackingExecutionPolicy.from_environment().snapshot()
        self.assertEqual(restored["processing_budget_s"], .6)
        self.assertTrue(restored["processing_budget_enabled"])
        self.assertIsNone(disabled["processing_budget_s"])
        self.assertFalse(disabled["processing_budget_enabled"])
        self.assertEqual(disabled["operation_watchdog_s"], 60.)
        self.assertEqual(disabled["legacy_processing_budget_s"], .6)
        self.assertFalse(disabled["legacy_budget_override_supported"])

    def test_invalid_disable_spellings_and_nonfinite_limits_are_rejected(self):
        for text in ("", "false", "none", "Disabled", "0", "-1", "nan", "inf", "-inf"):
            with self.subTest(text=text), mock.patch.dict(os.environ, {subject.PROCESSING_BUDGET_ENV: text}):
                with self.assertRaises(ValueError):
                    subject.SensorTrackingExecutionPolicy.from_environment()
        for field in ("processing_budget_s", "operation_watchdog_s"):
            for value in (False, True, 0, -1, float("nan"), float("inf")):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    subject.SensorTrackingExecutionPolicy(**{field: value})
        with self.assertRaises(ValueError):
            subject.SensorTrackingExecutionPolicy(operation_watchdog_s=None)
        with self.assertRaises(TypeError):
            subject.SensorTrackingProcess(process_fixtures.StubRunner(), execution_policy=False)

    def test_runtime_factory_uses_same_server_policy_as_status_readback(self):
        runtime = SimpleNamespace(saved_maps=object(), require_agent=lambda: object(),
                                  global_observation=object(), sensor_tracking=None)
        runner = process_fixtures.StubRunner()
        runner.resource_scope_enabled = True
        with mock.patch.dict(os.environ, {subject.PROCESSING_BUDGET_ENV: "disabled"}), \
                mock.patch.object(subject.ExternalGlobalObservationRunner, "from_environment", return_value=runner):
            configure_sensor_tracking(runtime)
        self.addCleanup(runtime.sensor_tracking.close)
        process = runtime.sensor_tracking._process_factory()
        self.addCleanup(process.close)
        self.assertIsNone(process._execution_policy.processing_budget_s)
        expected = process._execution_policy.snapshot()
        expected["resource_mode"] = "user_scope_v1"
        self.assertEqual(runtime.sensor_tracking.snapshot()["execution_policy"], expected)
        self.assertEqual(runtime.sensor_tracking.snapshot()["session_watchdog"]["timeout_s"], 60.)

    def test_runtime_budget_disable_without_resource_mode_fails_before_process_launch(self):
        runtime = SimpleNamespace(saved_maps=object(), require_agent=lambda: object(),
                                  global_observation=object(), sensor_tracking=None)
        with mock.patch.dict(os.environ, {subject.PROCESSING_BUDGET_ENV: "disabled"}), \
                mock.patch.object(subject.ExternalGlobalObservationRunner, "from_environment",
                                  return_value=process_fixtures.StubRunner()), \
                mock.patch.object(subject, "SensorTrackingProcess") as launch:
            with self.assertRaisesRegex(ValueError, "requires user_scope_v1"):
                configure_sensor_tracking(runtime)
            launch.assert_not_called()


class ExecutionPolicyProcessTests(unittest.TestCase):
    def setUp(self):
        process_fixtures.SensorTrackingProcessTests.setUp(self)
        worker = Path(self.temp.name) / "fake_worker.py"
        worker.write_text(worker.read_text()
            .replace("import json, os, struct, sys, time", "import json, os, struct, sys, time, signal")
            .replace("if not piece: raise EOFError()", "if not piece:\n            if mode == 'close-hang': time.sleep(2)\n            raise EOFError()")
            .replace("sock = int(sys.argv[2])", "sock = int(sys.argv[2])\nif mode == 'stubborn': signal.signal(signal.SIGTERM, signal.SIG_IGN)")
            .replace("if mode == 'late': time.sleep(2)",
                     "if mode in ('late', 'stubborn'): time.sleep(2)\n        if mode == 'over-budget': time.sleep(.7)"))

    _start = process_fixtures.SensorTrackingProcessTests._start
    _align = process_fixtures.SensorTrackingProcessTests._align

    def replacement(self, *, budget=None, watchdog=60.):
        self.process.close()
        self.process = subject.SensorTrackingProcess(process_fixtures.StubRunner(),
            execution_policy=subject.SensorTrackingExecutionPolicy(
                processing_budget_s=budget, operation_watchdog_s=watchdog))
        self.addCleanup(self.process.close)

    def test_point_seven_second_reply_accepts_only_with_budget_explicitly_disabled(self):
        self._start("over-budget")
        child = self.process._process
        with self.assertRaisesRegex(subject.SensorTrackingError, "SENSOR_DEADLINE_EXCEEDED"):
            self._align()
        self.assertIsNotNone(child.poll())
        self.replacement()
        self._start("over-budget")
        result = self._align()
        self.assertEqual(result["source_stamp_ns"], self.context["source_stamp_ns"])
        self.assertEqual(result["input_points"], self.context["scan"]["point_count"])
        self.assertEqual(result["reference_points"], self.context["map"]["point_count"])
        self.assertFalse(result["tracking_verified"])
        self.assertIsNone(result["body_pose"])
        self.assertIsNone(result["current_pose"])
        self.assertIsNone(self.process._operation_timer)

    def test_disabled_budget_still_times_out_and_reaps_worker(self):
        self.replacement(watchdog=.08)
        self._start("late")
        child, folder = self.process._process, Path(self.process._folder.name)
        with self.assertRaisesRegex(subject.SensorTrackingError, "SENSOR_OPERATION_WATCHDOG_EXCEEDED"):
            self._align()
        self.assertIsNotNone(child.poll())
        self.assertFalse(folder.exists())
        self.assertTrue(self.process.close())

    def test_watchdog_kills_os_fake_worker_that_ignores_term(self):
        self.replacement(watchdog=.08)
        self._start("stubborn")
        child = self.process._process
        with self.assertRaisesRegex(subject.SensorTrackingError, "SENSOR_OPERATION_WATCHDOG_EXCEEDED"):
            self._align()
        self.assertEqual(child.returncode, -signal.SIGKILL)
        self.assertTrue(self.process.close())

    def test_watchdog_reaps_during_parent_validation_then_rejects_its_late_return(self):
        self.replacement(watchdog=.08)
        self._start()
        child = self.process._process
        entered, release = threading.Event(), threading.Event()
        original = self.process._runner._array

        def delayed_validation(*args):
            entered.set()
            release.wait(1.)
            return original(*args)

        outcomes = []
        with mock.patch.object(self.process._runner, "_array", side_effect=delayed_validation):
            thread = threading.Thread(target=lambda: self.record_align(outcomes))
            thread.start()
            try:
                self.assertTrue(entered.wait(1.))
                child.wait(timeout=1.)
                self.assertIsNotNone(child.poll())
                self.assertTrue(thread.is_alive())  # Python validation is not forcibly killed.
            finally:
                release.set()
                thread.join(timeout=1.)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(outcomes), 1)
        self.assertIsInstance(outcomes[0], subject.SensorTrackingError)
        self.assertIn("SENSOR_OPERATION_WATCHDOG_EXCEEDED", str(outcomes[0]))
        self.assertEqual(self.process._sequence, 0)

    def test_cancel_and_close_still_reap_when_processing_budget_disabled(self):
        for method in ("cancel", "close"):
            with self.subTest(method=method):
                self.replacement()
                self.cancel = threading.Event()
                self._start("late")
                child = self.process._process
                timer = threading.Timer(.04, self.cancel.set if method == "cancel" else self.process.close)
                timer.start()
                try:
                    with self.assertRaises(subject.SensorTrackingError):
                        self._align()
                finally:
                    timer.join(timeout=1.)
                self.assertIsNotNone(child.poll())
                self.assertEqual(self.process._sequence, 0)

    def test_old_timer_cannot_close_completed_or_subsequent_operation(self):
        self.replacement()
        tokens = []
        begin = self.process._begin_alignment_watchdog

        def remember():
            token, deadline = begin()
            tokens.append(token)
            return token, deadline

        with mock.patch.object(self.process, "_begin_alignment_watchdog", side_effect=remember):
            self._start()
            self._align()
            old = tokens[0]
            original = self.process._runner._array

            def expire_previous(*args):
                self.process._expire_alignment(old)
                return original(*args)

            with mock.patch.object(self.process._runner, "_array", side_effect=expire_previous):
                self._align(source_stamp_ns="1001")
        self.assertFalse(self.process._closed)
        self.assertEqual(self.process._sequence, 2)
        self.assertIsNone(self.process._operation_timer)

    def test_disabled_budget_preserves_duplicate_epoch_frame_map_and_full_array_guards(self):
        for changes, code in (({}, "SENSOR_SOURCE_STAMP_NOT_ADVANCING"),
                              ({"observer_epoch": "new", "source_stamp_ns": "1001"}, "SENSOR_SOURCE_EPOCH_CHANGED"),
                              ({"source_frame": "body", "source_stamp_ns": "1001"}, "SENSOR_MAP_OR_FRAME_CHANGED"),
                              ({"map_revision": "new", "source_stamp_ns": "1001"}, "SENSOR_MAP_OR_FRAME_CHANGED"),
                              ({"scan": {**self.context["scan"], "point_count": 1},
                                "source_stamp_ns": "1001"}, "SENSOR_INPUT_OR_RESULT_INVALID")):
            with self.subTest(changes=changes):
                self.replacement()
                self._start()
                self._align()
                with self.assertRaisesRegex(subject.SensorTrackingError, code):
                    self._align(**changes)
                self.assertTrue(self.process._closed)

    def test_failed_reap_preserves_owned_handle_and_files_for_retry(self):
        self.replacement()
        self._start()
        child, folder = self.process._process, Path(self.process._folder.name)
        stop = subject._stop_group
        with mock.patch.object(subject, "_stop_group", return_value=False):
            self.assertFalse(self.process.close())
            self.assertIs(self.process._reap_pending_process, child)
            self.assertTrue(folder.exists())
            self.assertFalse(self.process.close())
        with mock.patch.object(subject, "_stop_group", side_effect=PermissionError("synthetic signal denial")):
            self.assertFalse(self.process.close())
            self.assertIs(self.process._reap_pending_process, child)
        with mock.patch.object(subject, "_stop_group", wraps=stop) as retry:
            self.assertTrue(self.process.close())
            retry.assert_called_once_with(child)
        self.assertIsNotNone(child.poll())
        self.assertIsNone(self.process._reap_pending_process)
        self.assertFalse(folder.exists())

    def test_concurrent_close_waits_for_owned_reap_and_retries_after_false(self):
        self.replacement()
        self._start("close-hang")
        child = self.process._process
        entered, release = threading.Event(), threading.Event()
        stop = subject._stop_group
        count, outcomes = [], []

        def delayed_stop(process):
            count.append(process)
            if len(count) == 1:
                entered.set()
                release.wait(1.)
                return False
            return stop(process)

        with mock.patch.object(subject, "_stop_group", side_effect=delayed_stop):
            first = threading.Thread(target=lambda: outcomes.append(self.process.close()))
            second = threading.Thread(target=lambda: outcomes.append(self.process.close()))
            first.start()
            self.assertTrue(entered.wait(1.))
            second.start()
            time.sleep(.02)
            self.assertEqual(count, [child])
            self.assertTrue(second.is_alive())
            release.set()
            first.join(timeout=1.)
            second.join(timeout=1.)
        self.assertEqual(count, [child, child])
        self.assertCountEqual(outcomes, [False, True])
        self.assertIsNotNone(child.poll())

    def record_align(self, outcomes):
        try:
            outcomes.append(self._align())
        except Exception as exc:
            outcomes.append(exc)


class SessionWatchdogOwnerTests(unittest.TestCase):
    setUp = owner_fixtures.SensorTrackingOwnerTests.setUp
    tearDown = owner_fixtures.SensorTrackingOwnerTests.tearDown
    wait_for = owner_fixtures.SensorTrackingOwnerTests.wait_for
    begin = owner_fixtures.SensorTrackingOwnerTests.begin

    def test_session_timeout_invalidates_generation_cancels_capture_and_clears_pose(self):
        self.owner._session_watchdog_s = .08
        initial = self.begin()
        self.wait_for(lambda: self.owner._state == "SENSOR_CANDIDATE")
        process = self.processes[0]
        self.wait_for(lambda: self.owner._reason == "SENSOR_SESSION_WATCHDOG_EXCEEDED")
        self.wait_for(lambda: process.closed)
        view = self.owner.snapshot()
        self.assertGreater(view["generation"], initial["generation"])
        self.assertEqual(view["state"], "LOST")
        self.assertIsNone(view["sensor_pose"])
        self.assertIsNone(view["source"])
        self.assertEqual(view["trail"], [])
        self.assertFalse(view["session_watchdog"]["active"])
        self.assertFalse(view["tracking_verified"])
        self.assertIsNone(view["body_pose"])
        self.assertIsNone(self.agent.pending)

    def test_session_expiry_during_startup_cannot_publish_late_initialization(self):
        self.owner._session_watchdog_s = .08
        entered, release = threading.Event(), threading.Event()
        original = owner_fixtures.LocalProcess.start

        def slow_start(process, *args):
            entered.set()
            release.wait(1.)
            if not args[-1].is_set():
                original(process, *args)

        with mock.patch.object(owner_fixtures.LocalProcess, "start", slow_start):
            initial = self.begin()
            self.assertTrue(entered.wait(1.))
            self.wait_for(lambda: self.owner._reason == "SENSOR_SESSION_WATCHDOG_EXCEEDED")
            self.assertTrue(self.processes[0].closed)
            release.set()
            self.wait_for(lambda: not self.owner.snapshot()["worker_active"])
        self.assertGreater(self.owner.snapshot()["generation"], initial["generation"])
        self.assertEqual(self.owner.snapshot()["state"], "LOST")
        self.assertEqual(self.processes[0].calls, [])

    def test_late_align_reply_after_session_expiry_cannot_reappear(self):
        self.owner._session_watchdog_s = .08
        self.options["pause_at"] = 3
        initial = self.begin()
        self.assertTrue(self.processes[0].entered.wait(1.))
        self.wait_for(lambda: self.owner._reason == "SENSOR_SESSION_WATCHDOG_EXCEEDED")
        self.wait_for(lambda: not self.owner.snapshot()["worker_active"])
        view = self.owner.snapshot()
        self.assertGreater(view["generation"], initial["generation"])
        self.assertIsNone(view["sensor_pose"])
        self.assertEqual(view["trail"], [])
        self.assertEqual(view["state"], "LOST")

    def test_stop_disarms_timer_and_old_generation_callback_cannot_change_stop(self):
        self.options["pause_at"] = 1
        initial = self.begin()
        process = self.processes[0]
        self.assertTrue(process.entered.wait(1.))
        self.assertTrue(self.owner.snapshot()["session_watchdog"]["active"])
        stopped = self.owner.stop()
        self.owner._expire_session(initial["generation"], process)
        view = self.owner.snapshot()
        self.assertEqual(view["state"], "STOPPED")
        self.assertEqual(view["generation"], stopped["generation"])
        self.assertFalse(view["session_watchdog"]["active"])

    def test_deferred_timer_cannot_accept_reply_after_absolute_session_deadline(self):
        self.options["pause_at"] = 3
        with mock.patch.object(threading.Timer, "start"):
            initial = self.begin()
        process = self.processes[0]
        self.assertTrue(process.entered.wait(1.))
        with self.owner._lock:
            self.owner._session_deadline = time.monotonic() - 1.
        process.release.set()
        # Deliberately avoid snapshot: the commit gate must reject by itself.
        self.wait_for(lambda: self.owner._reason == "SENSOR_SESSION_WATCHDOG_EXCEEDED")
        self.wait_for(lambda: process.closed)
        self.assertGreater(self.owner._generation, initial["generation"])
        self.assertIsNone(self.owner._sensor_pose)
        self.assertEqual(self.owner._trail, [])

    def test_snapshot_hides_pose_at_absolute_deadline_if_callback_is_deferred(self):
        with mock.patch.object(threading.Timer, "start"):
            initial = self.begin()
        self.wait_for(lambda: self.owner._state == "SENSOR_CANDIDATE")
        with self.owner._lock:
            self.owner._session_deadline = time.monotonic() - 1.
        view = self.owner.snapshot()
        self.assertEqual(view["reason"], "SENSOR_SESSION_WATCHDOG_EXCEEDED")
        self.assertGreater(view["generation"], initial["generation"])
        self.assertIsNone(view["sensor_pose"])
        self.assertEqual(view["trail"], [])

    def test_capture_wait_has_absolute_deadline_with_deferred_callback(self):
        self.agent.stamps.clear()
        with mock.patch.object(threading.Timer, "start"):
            self.begin()
        self.wait_for(lambda: self.owner._capture_id is not None)
        with self.owner._lock:
            self.owner._session_deadline = time.monotonic() - 1.
        self.wait_for(lambda: self.owner._reason == "SENSOR_SESSION_WATCHDOG_EXCEEDED")
        self.wait_for(lambda: self.processes[0].closed)
        self.assertIsNone(self.agent.pending)

    def test_failed_watchdog_reap_is_visible_blocks_admission_and_can_retry(self):
        self.options["pause_at"] = 3
        initial = self.begin()
        process = self.processes[0]
        self.assertTrue(process.entered.wait(1.))
        def unreaped():
            process.release.set()
            return False

        with mock.patch.object(process, "close", side_effect=unreaped):
            self.owner._expire_session(initial["generation"], process)
            self.wait_for(lambda: not self.owner.snapshot()["worker_active"])
            self.assertIs(self.owner._process, process)
            self.assertFalse(self.owner.snapshot()["cleanup_complete"])
            # A new request cannot start another process while one remains owned.
            with self.assertRaisesRegex(owner_fixtures.SensorTrackingConflict,
                                        "SENSOR_PREVIOUS_PROCESS_CLEANUP_PENDING"):
                self.owner.start(self.global_job_id, "retry-with-unreaped-process")
            self.assertFalse(self.owner.close())
            self.assertFalse(self.owner.close())
        self.assertTrue(self.owner.close())
        self.assertIsNone(self.owner._process)
        self.assertTrue(self.owner.snapshot()["cleanup_complete"])
        self.assertTrue(process.closed)

    def test_completion_freshness_remains_one_second_with_budget_disabled_policy(self):
        self.options["pause_at"] = 1
        self.begin()
        process = self.processes[0]
        self.assertTrue(process.entered.wait(1.))
        # Only the receipt age is old; the live source/map identity stays valid.
        original = self.owner._now
        self.owner._current_matches = lambda *_args, **_kwargs: True
        self.owner._now = lambda: original() + 1.01
        process.release.set()
        self.wait_for(lambda: self.owner._state == "STALE")
        view = self.owner.snapshot()
        self.assertEqual(view["reason"], "ALIGNMENT_REPLY_STALE_OR_SOURCE_CHANGED")
        self.assertIsNone(view["sensor_pose"])
        self.assertEqual(view["trail"], [])

    def test_invalid_session_watchdog_rejected_and_readback_is_not_mutable(self):
        for value in (False, 0, -1, float("nan"), float("inf"), None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                SensorTrackingOwner(self.catalog, self.agent, self.global_owner,
                                    self.owner._process_factory, session_watchdog_s=value)
        policy = subject.SensorTrackingExecutionPolicy(processing_budget_s=None).snapshot()
        owner = SensorTrackingOwner(self.catalog, self.agent, self.global_owner,
            self.owner._process_factory, execution_policy=policy)
        self.addCleanup(owner.close)
        policy["operation_watchdog_s"] = float("inf")
        readback = owner.snapshot()
        self.assertIsNone(readback["execution_policy"]["processing_budget_s"])
        self.assertEqual(readback["execution_policy"]["operation_watchdog_s"], 60.)
        self.assertEqual(readback["session_watchdog"]["timeout_s"], 60.)
        readback["execution_policy"]["operation_watchdog_s"] = 999
        self.assertEqual(owner.snapshot()["execution_policy"]["operation_watchdog_s"], 60.)


if __name__ == "__main__":
    unittest.main()
