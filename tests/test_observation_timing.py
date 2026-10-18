"""Diagnostics retain the original acceptance contract and no sensor payload."""
import threading
import unittest
from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor

from test_observation_alignment import Agent, Catalog, inputs, request_body
from robot_dashboard.relocalization.observation_alignment import ObservationAligner, ObservationAlignmentError
from robot_dashboard.relocalization.observation_timing import ObservationTiming, measure, measured_lock, note


class ObservationTimingTests(unittest.TestCase):
    def test_early_identity_rejection_does_not_prepare_reference(self):
        cloud, pose = inputs()
        cloud["observation"]["identity_status"] = "UNAVAILABLE"
        catalog = Catalog([[0, 0, 0]] * 100)
        trace = ObservationTiming()
        with trace.bind(), self.assertRaisesRegex(ObservationAlignmentError, "IDENTITY"):
            ObservationAligner().estimate(catalog, Agent(cloud, pose), request_body())
        self.assertEqual(catalog.reads, 0)
        self.assertEqual(trace.failed_stage, "input_snapshot_and_validation")

    def test_context_isolation_and_failure_release(self):
        barrier = threading.Barrier(2)
        def run(value):
            trace, lock = ObservationTiming(), threading.Lock()
            with trace.bind():
                note("value", value)
                barrier.wait(timeout=2)
                with self.assertRaisesRegex(ValueError, "fixture"):
                    with measured_lock(lock, "lock"), measure("inner"):
                        raise ValueError("fixture")
                self.assertFalse(lock.locked())
            note("outside", 99)
            return trace
        with ThreadPoolExecutor(max_workers=2) as pool:
            traces = list(pool.map(run, [1, 2]))
        for value, trace in zip([1, 2], traces):
            self.assertEqual(trace.values, {"value": value})
            self.assertEqual(trace.failed_stage, "inner")
            for row in trace.stages.values():
                self.assertEqual(row["calls"], 1)
                self.assertGreaterEqual(row["wall_ms"], 0)
                self.assertGreaterEqual(row["thread_cpu_ms"], 0)

    def test_aggregate_storage_is_bounded(self):
        trace = ObservationTiming()
        with trace.bind():
            for index in range(100):
                note(str(index), index)
                with measure(str(index)):
                    pass
        self.assertEqual(len(trace.stages), 32)
        self.assertEqual(len(trace.values), 16)
        nested = ObservationTiming()
        with nested.bind(), ExitStack() as stack:
            for index in range(100):
                stack.enter_context(measure(str(index)))
        self.assertEqual(len(nested.stages), 32)
