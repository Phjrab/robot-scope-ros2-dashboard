"""Event-controlled lifecycle tests; no ROS, native registration or real scans."""
import copy
import json
import threading
import time
import unittest

from robot_dashboard.relocalization.global_observation_jobs import (
    GlobalObservationBusy, GlobalObservationConflict, GlobalObservationJobManager,
    GlobalObservationNotFound, GlobalObservationUnavailable, GlobalObservationValidationError,
)


def context(**changes):
    return {"map_id": "saved-map", "map_revision": "revision-one", "map_frame": "map-cloud",
            "source_frame": "hesai_lidar", "observer_id": "observer-one", "observer_epoch": "epoch-one",
            "source_stamp_ns": "1792326073857333183", "received_monotonic_s": 123.25,
            "receipt_clock": "OBSERVER_HOST_MONOTONIC", "clock_relation": "UNVERIFIED", **changes}


class GlobalObservationJobTests(unittest.TestCase):
    def fixture(self, **options):
        current, entered, release = context(), threading.Event(), threading.Event()
        records, cancellations = [], []
        def runner(payload, *, cancel_event):
            records.append(payload)
            cancellations.append(cancel_event)
            entered.set()
            if not release.wait(2):
                raise RuntimeError("test runner was not released")
            return {"status": "OBSERVATION_ONLY_UNVERIFIED", "source_stamp_ns": payload.get("stamp"),
                    "candidate": {"rmse_m": .07}}
        manager = GlobalObservationJobManager(runner, lambda captured: copy.deepcopy(current), **options)
        self.addCleanup(manager.close)
        self.addCleanup(release.set)
        return manager, current, entered, release, records, cancellations

    def test_success_is_immutable_captured_historical_observation_never_current_pose(self):
        manager, current, entered, release, records, _ = self.fixture()
        captured, payload = context(), {"stamp": context()["source_stamp_ns"], "points": [[1., 2., 3.]]}
        job = manager.start("capture-1", captured, payload)
        self.assertTrue(entered.wait(1))
        captured["source_stamp_ns"] = "1"
        payload["points"][0][0] = 999.
        records[0]["points"][0][1] = 888.
        job["captured_context"]["source_frame"] = "mutated-browser-copy"
        current["source_stamp_ns"] = str(int(current["source_stamp_ns"]) + 100)
        release.set()
        self.assertTrue(manager.wait(job["job_id"]))
        finished = manager.job(job["job_id"])
        self.assertEqual(finished["state"], "succeeded")
        self.assertEqual(finished["captured_context"], context())
        self.assertEqual(finished["observed_completion_context"]["source_stamp_ns"], current["source_stamp_ns"])
        result = finished["result"]
        self.assertEqual(result["captured_context"]["source_stamp_ns"], "1792326073857333183")
        self.assertEqual(result["observation"]["source_stamp_ns"], "1792326073857333183")
        for value in (finished, result, manager.snapshot()):
            self.assertTrue(value["historical_only"])
            self.assertIsNone(value["current_result"])
            self.assertIsNone(value["body_pose"])
            self.assertFalse(value["tracking_verified"])
        finished["result"]["observation"]["candidate"]["rmse_m"] = 0.
        self.assertEqual(manager.job(job["job_id"])["result"]["observation"]["candidate"]["rmse_m"], .07)
        json.dumps(manager.snapshot(), allow_nan=False)

    def test_canonical_duplicate_is_idempotent_and_busy_differs_from_request_id_conflict(self):
        manager, _, entered, release, records, _ = self.fixture()
        payload = {"a": 1, "b": {"x": 2, "y": 3}}
        job = manager.start("same-id", context(), payload)
        self.assertTrue(entered.wait(1))
        duplicate = manager.start("same-id", dict(reversed(list(context().items()))), {"b": {"y": 3, "x": 2}, "a": 1})
        self.assertEqual(duplicate["job_id"], job["job_id"])
        with self.assertRaises(GlobalObservationConflict):
            manager.start("same-id", context(), {"a": 2})
        with self.assertRaises(GlobalObservationConflict):
            manager.start("same-id", context(source_stamp_ns="1792326073857333184"), payload)
        with self.assertRaises(GlobalObservationBusy):
            manager.start("different-id", context(), payload)
        self.assertEqual(len(records), 1)
        release.set()
        self.assertTrue(manager.wait(job["job_id"]))
        self.assertEqual(manager.start("same-id", context(), payload)["job_id"], job["job_id"])
        retry = manager.start("explicit-retry", context(), payload)
        self.assertTrue(manager.wait(retry["job_id"]))
        self.assertEqual(len(records), 2)
        self.assertGreater(retry["generation"], job["generation"])

    def test_cancel_is_idempotent_discards_late_success_and_holds_slot_until_cleanup(self):
        manager, _, entered, release, _, cancellations = self.fixture()
        job = manager.start("cancel-1", context(), {})
        self.assertTrue(entered.wait(1))
        cancelled = manager.cancel(job["job_id"])
        generation = manager.snapshot()["generation"]
        self.assertEqual(cancelled["state"], "cancelled")
        self.assertTrue(cancelled["worker_active"])
        self.assertTrue(cancellations[0].is_set())
        self.assertIsNone(cancelled["result"])
        manager.cancel(job["job_id"])
        self.assertEqual(manager.snapshot()["generation"], generation)
        with self.assertRaises(GlobalObservationBusy):
            manager.start("cancel-retry", context(), {})
        release.set()
        self.assertTrue(manager.wait(job["job_id"]))
        self.assertEqual(manager.job(job["job_id"])["state"], "cancelled")
        self.assertIsNone(manager.job(job["job_id"])["result"])
        newer = manager.start("cancel-retry", context(), {})
        self.assertTrue(manager.wait(newer["job_id"]))
        self.assertEqual(manager.snapshot()["latest"]["job_id"], newer["job_id"])
        self.assertEqual(manager.job(job["job_id"])["state"], "cancelled")

    def test_explicit_invalidation_discards_old_generation_and_allows_new_context_after_settlement(self):
        manager, current, entered, release, _, cancellations = self.fixture()
        job = manager.start("old-map", context(), {})
        self.assertTrue(entered.wait(1))
        current["map_revision"] = "revision-two"
        manager.invalidate("MAP_REVISION_CHANGED")
        stale = manager.job(job["job_id"])
        self.assertEqual(stale["state"], "stale")
        self.assertEqual(stale["reason"], "MAP_REVISION_CHANGED")
        self.assertTrue(cancellations[0].is_set())
        release.set()
        self.assertTrue(manager.wait(job["job_id"]))
        self.assertIsNone(manager.job(job["job_id"])["result"])
        newer = manager.start("new-map", current, {})
        self.assertTrue(manager.wait(newer["job_id"]))
        self.assertEqual(manager.snapshot()["latest"]["state"], "succeeded")
        self.assertGreater(newer["generation"], job["generation"])

    def test_completion_rechecks_every_map_frame_observer_epoch_and_time_reversal_fence(self):
        for key in ("map_id", "map_revision", "map_frame", "source_frame", "observer_id", "observer_epoch", "source_stamp_ns"):
            with self.subTest(key=key):
                manager, current, entered, release, _, _ = self.fixture()
                job = manager.start("fence", context(), {})
                self.assertTrue(entered.wait(1))
                current[key] = "1" if key == "source_stamp_ns" else "replacement"
                release.set()
                self.assertTrue(manager.wait(job["job_id"]))
                self.assertEqual(manager.job(job["job_id"])["state"], "stale")
                self.assertIsNone(manager.job(job["job_id"])["result"])
                self.assertIsNone(manager.snapshot()["current_result"])

    def test_pre_admission_context_change_fails_without_running(self):
        manager, current, entered, _, _, _ = self.fixture()
        current["observer_epoch"] = "replacement"
        with self.assertRaises(GlobalObservationConflict):
            manager.start("stale-admission", context(), {})
        self.assertFalse(entered.is_set())
        self.assertIsNone(manager.snapshot()["active"])

    def test_generation_change_during_admission_blocks_old_request_before_runner_start(self):
        entered, release = threading.Event(), threading.Event()
        runner_calls, errors = [], []
        def provider(captured):
            entered.set()
            if not release.wait(2):
                raise RuntimeError("test provider was not released")
            return context()
        manager = GlobalObservationJobManager(lambda payload, **kwargs: runner_calls.append(payload) or {}, provider)
        self.addCleanup(manager.close)
        self.addCleanup(release.set)
        def start():
            try:
                manager.start("old-admission", context(), {})
            except GlobalObservationConflict as error:
                errors.append(error)
        thread = threading.Thread(target=start, daemon=True)
        thread.start()
        self.assertTrue(entered.wait(1))
        manager.invalidate("VIEW_GENERATION_CHANGED")
        release.set()
        thread.join(1)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertEqual(runner_calls, [])
        self.assertIsNone(manager.snapshot()["latest"])

    def test_independent_deadline_cancels_even_noncooperative_runner_and_rejects_late_output(self):
        manager, _, entered, release, _, cancellations = self.fixture(timeout_s=.03)
        job = manager.start("timeout", context(), {})
        self.assertTrue(entered.wait(1))
        self.assertTrue(cancellations[0].wait(1))
        timed_out = manager.job(job["job_id"])
        self.assertEqual(timed_out["state"], "timed_out")
        self.assertEqual(timed_out["reason"], "DEADLINE_EXCEEDED")
        self.assertTrue(timed_out["worker_active"])
        with self.assertRaises(GlobalObservationBusy):
            manager.start("too-early", context(), {})
        release.set()
        self.assertTrue(manager.wait(job["job_id"]))
        self.assertEqual(manager.job(job["job_id"])["state"], "timed_out")
        self.assertIsNone(manager.job(job["job_id"])["result"])

    def test_close_is_bounded_cancels_owner_and_never_admits_new_work(self):
        manager, _, entered, release, _, cancellations = self.fixture(close_timeout_s=.01)
        job = manager.start("close", context(), {})
        self.assertTrue(entered.wait(1))
        started = time.monotonic()
        self.assertFalse(manager.close())
        self.assertLess(time.monotonic() - started, .5)
        self.assertTrue(cancellations[0].is_set())
        self.assertEqual(manager.job(job["job_id"])["reason"], "OWNER_CLOSED")
        with self.assertRaises(GlobalObservationUnavailable):
            manager.start("new-after-close", context(), {})
        release.set()
        self.assertTrue(manager.wait(job["job_id"]))
        self.assertTrue(manager.close())
        self.assertIsNone(manager.job(job["job_id"])["result"])

    def test_cancel_while_completion_context_check_waits_wins_over_late_publication(self):
        entered, release = threading.Event(), threading.Event()
        calls = []
        def provider(captured):
            calls.append(captured)
            if len(calls) > 1:
                entered.set()
                if not release.wait(2):
                    raise RuntimeError("test provider was not released")
            return context()
        manager = GlobalObservationJobManager(lambda payload, **kwargs: {"candidate": 1}, provider)
        self.addCleanup(manager.close)
        self.addCleanup(release.set)
        job = manager.start("completion-race", context(), {})
        self.assertTrue(entered.wait(1))
        manager.cancel(job["job_id"])
        release.set()
        self.assertTrue(manager.wait(job["job_id"]))
        self.assertEqual(manager.job(job["job_id"])["state"], "cancelled")
        self.assertIsNone(manager.job(job["job_id"])["result"])

    def test_runner_and_completion_provider_failures_and_oversized_outputs_never_publish(self):
        def fail(payload, **kwargs):
            raise RuntimeError("backend failed")
        for runner, expected in ((fail, "failed"),
                                 (lambda payload, **kwargs: {"bad": float("nan")}, "failed"),
                                 (lambda payload, **kwargs: [1, 2], "failed"),
                                 (lambda payload, **kwargs: {"large": "x" * 100}, "failed")):
            with self.subTest(runner=runner):
                manager = GlobalObservationJobManager(runner, lambda captured: context(), max_result_bytes=64)
                self.addCleanup(manager.close)
                job = manager.start("failure", context(), {})
                self.assertTrue(manager.wait(job["job_id"]))
                self.assertEqual(manager.job(job["job_id"])["state"], expected)
                self.assertIsNone(manager.job(job["job_id"])["result"])
        calls = []
        def provider(captured):
            calls.append(1)
            if len(calls) > 1:
                raise RuntimeError("catalogue unavailable")
            return context()
        manager = GlobalObservationJobManager(lambda payload, **kwargs: {}, provider)
        self.addCleanup(manager.close)
        job = manager.start("context-failure", context(), {})
        self.assertTrue(manager.wait(job["job_id"]))
        self.assertEqual(manager.job(job["job_id"])["state"], "failed")

    def test_runner_timeout_is_distinct_from_failure(self):
        def runner(payload, **kwargs):
            raise TimeoutError("process deadline expired")
        manager = GlobalObservationJobManager(runner, lambda captured: context())
        self.addCleanup(manager.close)
        job = manager.start("runner-timeout", context(), {})
        self.assertTrue(manager.wait(job["job_id"]))
        self.assertEqual(manager.job(job["job_id"])["state"], "timed_out")
        self.assertIsNone(manager.job(job["job_id"])["result"])

    def test_invalid_stamps_json_and_configuration_fail_before_runner(self):
        manager, _, entered, _, _, _ = self.fixture(max_payload_bytes=64)
        for stamp in (1792326073857333183, "0", "-1", "01", "1.0", "1e9", True, "9" * 21):
            with self.subTest(stamp=stamp), self.assertRaises(GlobalObservationValidationError):
                manager.start("invalid-stamp", context(source_stamp_ns=stamp), {})
        for payload in ({"value": float("inf")}, {"value": object()}, {"nested": {1: "numeric-key"}}, {"large": "x" * 100}):
            with self.assertRaises(GlobalObservationValidationError):
                manager.start("invalid-json", context(), payload)
        self.assertFalse(entered.is_set())
        for options in ({"timeout_s": True}, {"timeout_s": 0}, {"timeout_s": float("nan")},
                        {"close_timeout_s": 6}, {"max_jobs": True}):
            with self.assertRaises(GlobalObservationValidationError):
                GlobalObservationJobManager(lambda payload, **kwargs: {}, lambda captured: context(), **options)

    def test_history_is_bounded_and_retained_successes_remain_historical_after_invalidate(self):
        manager = GlobalObservationJobManager(lambda payload, **kwargs: {}, lambda captured: context(), max_jobs=2)
        self.addCleanup(manager.close)
        jobs = []
        for i in range(3):
            job = manager.start(f"history-{i}", context(), {})
            self.assertTrue(manager.wait(job["job_id"]))
            jobs.append(job)
        with self.assertRaises(GlobalObservationNotFound):
            manager.job(jobs[0]["job_id"])
        manager.invalidate("VIEW_SELECTION_CHANGED")
        historical = manager.job(jobs[-1]["job_id"])
        self.assertTrue(historical["result"]["historical_only"])
        self.assertIsNone(manager.snapshot()["current_result"])
        self.assertGreater(manager.snapshot()["generation"], historical["generation"])


if __name__ == "__main__":
    unittest.main()
