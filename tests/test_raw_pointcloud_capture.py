from array import array
import hashlib
from types import SimpleNamespace
import threading
import time
import unittest
from unittest.mock import patch

import numpy as np

from robot_dashboard.ros.pointcloud import PointCloudHub
from robot_dashboard.ros.raw_pointcloud_capture import (
    RawCaptureBusy, RawCaptureNotFound, RawCaptureUnavailable,
    RawCaptureValidationError, RawPointCloudCaptureLatch, capture_xyz,
)


def message(points=None, *, datatype=8, endian="<", width=None, height=1, padding=0):
    kinds = {1: "i1", 2: "u1", 3: "i2", 4: "u2", 5: "i4", 6: "u4", 7: "f4", 8: "f8"}
    values = np.asarray(points if points is not None else [[1, 2, 3], [4, 5, 6]], dtype=endian + kinds[datatype])
    width = len(values) // height if width is None else width
    scalar = values.dtype.itemsize
    step = 3 * scalar
    packed = values.reshape(height, width, 3).tobytes()
    data = b"".join(packed[row * width * step:(row + 1) * width * step] + b"p" * padding
                    for row in range(height))
    return SimpleNamespace(width=width, height=height, point_step=step, row_step=width * step + padding,
                           fields=[SimpleNamespace(name=name, datatype=datatype, offset=index * scalar, count=1)
                                   for index, name in enumerate(("x", "y", "z"))],
                           is_bigendian=endian == ">", data=data, header=SimpleNamespace(frame_id="lidar"))


def decode(captured):
    return np.frombuffer(captured["xyz_bytes"], dtype="<f8").reshape(-1, 3)


class RawXYZDecoderTests(unittest.TestCase):
    def capture(self, value, **limits):
        return capture_xyz(value, max_points=limits.get("max_points", 100),
                           max_bytes=limits.get("max_bytes", 10_000))

    def test_full_float64_precision_nonfinite_signed_zero_and_order_are_preserved(self):
        values = np.asarray([[1 + 2 ** -40, -0., 0.], [np.nan, np.inf, -np.inf], [9., 8., 7.]])
        result = self.capture(message(values))
        np.testing.assert_array_equal(decode(result), values)
        self.assertTrue(np.signbit(decode(result)[0, 1]))
        self.assertEqual(result["captured_points"], 3)
        self.assertEqual(result["finite_points"], 2)
        self.assertEqual(result["nonfinite_points"], 1)
        self.assertEqual(result["xyz_sha256"], hashlib.sha256(result["xyz_bytes"]).hexdigest())
        for key in ("source_order_preserved", "nonfinite_rows_preserved", "zero_rows_preserved"):
            self.assertIs(result[key], True)
        for key in ("sampling_applied", "spatial_filter_applied", "transform_applied", "raw_message_archive"):
            self.assertIs(result[key], False)

    def test_all_scalar_pointfield_types_and_endianness(self):
        for datatype in range(1, 9):
            for endian in ("<", ">"):
                with self.subTest(datatype=datatype, endian=endian):
                    values = [[0, 2, 3], [4, 5, 6]]
                    result = self.capture(message(values, datatype=datatype, endian=endian))
                    np.testing.assert_array_equal(decode(result), values)
                    self.assertEqual(result["source_is_bigendian"], endian == ">")
        for datatype, value in ((5, -2147483648), (6, 4294967295)):
            result = self.capture(message([[value, 0, 1]], datatype=datatype))
            self.assertEqual(decode(result)[0, 0], value)

    def test_organized_rows_with_padding_extra_fields_and_offsets(self):
        dtype = np.dtype({"names": ["intensity", "z", "x", "y"],
                          "formats": [">u4", ">f8", ">f8", ">f8"],
                          "offsets": [0, 4, 12, 20], "itemsize": 32})
        rows = np.zeros((2, 2), dtype=dtype)
        values = np.arange(12).reshape(4, 3)
        for index, name in enumerate(("x", "y", "z")):
            rows[name][:] = values[:, index].reshape(2, 2)
        value = message()
        value.width, value.height, value.point_step, value.row_step = 2, 2, 32, 72
        value.is_bigendian = True
        value.data = array("B", rows[0].tobytes() + b"padding!" + rows[1].tobytes())
        value.fields = [SimpleNamespace(name=name, offset=offset, datatype=8, count=1)
                        for name, offset in (("z", 4), ("x", 12), ("y", 20))]
        result = self.capture(value)
        np.testing.assert_array_equal(decode(result), values)
        self.assertEqual(result["source_row_step"], 72)
        self.assertEqual(result["source_payload_bytes"], 136)

    def test_point_and_source_and_output_byte_limits_precede_allocation(self):
        for value, limits in ((message(), {"max_points": 1}),
                              (message(), {"max_bytes": 47}),
                              (message([[1, 2, 3]], padding=100), {"max_bytes": 50})):
            with self.subTest(limits=limits), patch("robot_dashboard.ros.raw_pointcloud_capture.np.empty") as allocate:
                with self.assertRaises(RawCaptureValidationError):
                    self.capture(value, **limits)
                allocate.assert_not_called()
        value = message()
        value.width = 2 ** 63
        with patch("robot_dashboard.ros.raw_pointcloud_capture.np.empty") as allocate:
            with self.assertRaises(RawCaptureValidationError):
                self.capture(value)
            allocate.assert_not_called()

    def test_malformed_layouts_fail_without_silent_sampling_or_field_substitution(self):
        changes = (lambda value: setattr(value, "data", value.data[:-1]),
                   lambda value: setattr(value, "row_step", 1),
                   lambda value: setattr(value, "width", 0),
                   lambda value: setattr(value, "fields", value.fields[:2]),
                   lambda value: value.fields.append(value.fields[0]),
                   lambda value: setattr(value.fields[0], "count", 3),
                   lambda value: setattr(value.fields[0], "offset", 23),
                   lambda value: setattr(value.fields[0], "datatype", 99),
                   lambda value: setattr(value, "data", memoryview(value.data)[::2]))
        for change in changes:
            value = message()
            change(value)
            with self.subTest(change=change), self.assertRaises(RawCaptureValidationError):
                self.capture(value)

    def test_legacy_zero_row_step_and_missing_scalar_count_are_explicitly_supported(self):
        value = message()
        value.row_step = 0
        for field in value.fields:
            del field.count
        np.testing.assert_array_equal(decode(self.capture(value)), [[1, 2, 3], [4, 5, 6]])


class RawCaptureLatchTests(unittest.TestCase):
    def setUp(self):
        self.clock = [10.]
        self.latch = RawPointCloudCaptureLatch(threading.RLock(), now=lambda: self.clock[0])
        self.request = self.latch.request("/cloud", "epoch", timeout_s=10)

    def tearDown(self):
        self.latch.invalidate("TEST_CLEANUP")

    def begin(self, **changes):
        options = {"topic": "/cloud", "frame_id": "lidar", "source_stamp_ns": 1780000000123456789,
                   "received_monotonic_s": 10., "observation": {
                       "publisher_epoch": "epoch", "observer_id": "observer",
                       "source_stamp_ns": "1780000000123456789", "received_monotonic_s": 10.,
                       "receipt_clock": "OBSERVER_HOST_MONOTONIC", "identity_status": "UNAVAILABLE"}}
        options.update(changes)
        return self.latch.begin(**options)

    def finish(self, ticket, result=None, **changes):
        options = {"current_topic": "/cloud", "observer_epoch": "epoch"}
        options.update(changes)
        self.latch.finish(ticket, result or capture_xyz(message(), max_points=100, max_bytes=10_000), **options)

    def test_ready_metadata_is_immutable_and_take_transfers_payload_once(self):
        ticket = self.begin()
        self.finish(ticket)
        snapshot = self.latch.snapshot(self.request["capture_id"])
        self.assertEqual(snapshot["state"], "ready")
        self.assertEqual(snapshot["source_stamp_ns"], "1780000000123456789")
        self.assertEqual(snapshot["observer_epoch"], "epoch")
        self.assertEqual(snapshot["received_monotonic_s"], 10.)
        self.assertNotIn("xyz_bytes", snapshot)
        snapshot["observation"]["observer_id"] = "mutated"
        self.assertEqual(self.latch.snapshot()["observer_id"], "observer")
        with self.assertRaises(RawCaptureBusy):
            self.latch.request("/cloud", "epoch")
        captured = self.latch.take(self.request["capture_id"])
        self.assertEqual(captured["state"], "consumed")
        self.assertIsInstance(captured["xyz_bytes"], bytes)
        self.assertNotIn("xyz_bytes", self.latch._record)
        with self.assertRaises(RawCaptureUnavailable):
            self.latch.take(self.request["capture_id"])

    def test_old_receipt_does_not_satisfy_new_request(self):
        self.assertIsNone(self.begin(received_monotonic_s=9.99))
        self.assertEqual(self.latch.snapshot()["state"], "awaiting")
        self.assertIsNotNone(self.begin(received_monotonic_s=10.01))

    def test_cancel_pending_clears_deadline_and_allows_another_request(self):
        result = self.latch.cancel(self.request["capture_id"])
        self.assertEqual(result["state"], "cancelled")
        self.assertIsNone(self.latch._timer)
        replacement = self.latch.request("/cloud", "epoch")
        self.assertGreater(replacement["generation"], result["generation"])
        with self.assertRaises(RawCaptureNotFound):
            self.latch.snapshot(result["capture_id"])

    def test_cancel_and_invalidation_keep_physical_copy_slot_until_finish(self):
        for action in ("cancel", "invalidate"):
            with self.subTest(action=action):
                if self.latch.snapshot()["state"] != "awaiting":
                    self.request = self.latch.request("/cloud", "epoch")
                ticket = self.begin()
                if action == "cancel":
                    self.latch.cancel(ticket.capture_id)
                else:
                    self.latch.invalidate("MAP_CHANGED")
                self.assertTrue(self.latch.snapshot()["capture_active"])
                with self.assertRaises(RawCaptureBusy):
                    self.latch.request("/cloud", "epoch")
                self.finish(ticket)
                self.assertFalse(self.latch.snapshot()["capture_active"])
                self.assertNotIn("xyz_bytes", self.latch._record)
                self.assertEqual(self.latch.snapshot()["state"], "cancelled" if action == "cancel" else "stale")

    def test_epoch_topic_and_generation_completion_fences(self):
        for changes in ({"observer_epoch": "new"}, {"current_topic": "/new"}):
            ticket = self.begin()
            self.finish(ticket, **changes)
            self.assertEqual(self.latch.snapshot()["state"], "stale")
            self.request = self.latch.request("/cloud", "epoch")
        ticket = self.begin()
        self.latch._generation += 1
        self.finish(ticket)
        self.assertEqual(self.latch.snapshot()["state"], "stale")

    def test_timeout_without_any_callback_and_late_copy_never_publishes(self):
        self.latch.cancel(self.request["capture_id"])
        self.request = self.latch.request("/cloud", "epoch", timeout_s=.02)
        deadline = time.monotonic() + 1
        while self.latch.snapshot()["state"] == "awaiting" and time.monotonic() < deadline:
            time.sleep(.005)
        self.assertEqual(self.latch.snapshot()["state"], "timed_out")
        self.request = self.latch.request("/cloud", "epoch", timeout_s=1)
        ticket = self.begin()
        self.clock[0] = 11.
        self.finish(ticket)
        self.assertEqual(self.latch.snapshot()["state"], "timed_out")
        self.assertNotIn("xyz_bytes", self.latch._record)

    def test_request_validation_and_missing_frame_stamp_fail_closed(self):
        self.latch.cancel(self.request["capture_id"])
        for options in ({"timeout_s": 0}, {"timeout_s": float("nan")}, {"max_points": True},
                        {"max_bytes": 23}, {"max_points": 4_000_001}):
            with self.subTest(options=options), self.assertRaises(RawCaptureValidationError):
                self.latch.request("/cloud", "epoch", **options)
        self.request = self.latch.request("/cloud", "epoch")
        self.assertIsNone(self.begin(frame_id=""))
        self.assertEqual(self.latch.snapshot()["reason"], "SOURCE_FRAME_OR_STAMP_UNAVAILABLE")


class HubRawCaptureTests(unittest.TestCase):
    def setUp(self):
        self.clock = [10.]
        self.hub = PointCloudHub(threading.RLock(), max_points=1000, radius_limit_m=500., frame_interval_s=.1)
        self.hub._raw_capture._now = lambda: self.clock[0]

    def tearDown(self):
        self.hub.invalidate_raw_capture("TEST_CLEANUP")

    def process(self, value=None, **changes):
        options = {"selected_topic": lambda: "/cloud", "stamp_ns": lambda _: 1780000000123456789,
                   "robot_pose_in_frame": lambda _: {"unverified": True}}
        options.update(changes)
        return self.hub.process("/cloud", value or message(), self.clock[0], **options)

    def test_no_request_has_no_raw_decoder_copy_or_timer_and_ui_behavior_is_preserved(self):
        with patch("robot_dashboard.ros.pointcloud.capture_xyz") as raw, \
                patch("robot_dashboard.ros.raw_pointcloud_capture.threading.Timer") as timer:
            self.assertTrue(self.process())
            self.assertEqual(self.hub.binary_snapshot()["sent_points"], 2)
            self.assertEqual(len(self.hub.binary_snapshot()["points_bytes"]), 24)
            self.assertIsNone(self.hub.raw_capture_snapshot())
        raw.assert_not_called()
        timer.assert_not_called()

    def test_capture_is_before_ui_throttle_cap_and_filter(self):
        self.hub.last_processed = 10.
        request = self.hub.request_raw_capture("/cloud")
        values = np.arange(3600, dtype=np.float64).reshape(1200, 3)
        values[0] = [0., -0., 0.]
        values[1] = [np.nan, np.inf, -np.inf]
        values[2] = [1e12, 2e12, 3e12]
        with patch("robot_dashboard.ros.pointcloud.extract_xyz") as viewport, \
                patch("robot_dashboard.ros.pointcloud.reject_spatial_outliers") as spatial:
            self.assertFalse(self.process(message(values)))
        viewport.assert_not_called()
        spatial.assert_not_called()
        captured = self.hub.take_raw_capture(request["capture_id"])
        np.testing.assert_array_equal(decode(captured), values)
        self.assertEqual(captured["source_frame"], "lidar")
        self.assertEqual(captured["source_stamp_ns"], "1780000000123456789")
        self.assertIsNone(captured["body_pose"])
        self.assertFalse(captured["body_extrinsic_verified"])
        self.assertNotIn("robot_pose_in_frame", captured)
        self.assertEqual(self.hub.binary_snapshot()["points_bytes"], b"")

    def test_capture_failure_keeps_existing_ui_output_and_does_not_truncate_raw(self):
        request = self.hub.request_raw_capture("/cloud", max_points=1)
        self.assertTrue(self.process())
        self.assertEqual(self.hub.raw_capture_snapshot(request["capture_id"])["state"], "failed")
        self.assertEqual(self.hub.binary_snapshot()["sent_points"], 2)
        with self.assertRaises(RawCaptureUnavailable):
            self.hub.take_raw_capture(request["capture_id"])

    def test_original_capture_and_display_cap_filter_remain_independent(self):
        request = self.hub.request_raw_capture("/cloud")
        values = np.arange(3600, dtype=np.float64).reshape(1200, 3)
        values[0] = [1 + 2 ** -40, 0, 0]
        with patch("robot_dashboard.ros.pointcloud.reject_spatial_outliers",
                   side_effect=lambda points, _: points[:3]) as spatial:
            self.assertTrue(self.process(message(values)))
        self.assertEqual(len(spatial.call_args.args[0]), 600)
        self.assertEqual(self.hub.binary_snapshot()["sent_points"], 3)
        self.assertEqual(len(self.hub.binary_snapshot()["points_bytes"]), 36)
        captured = self.hub.take_raw_capture(request["capture_id"])
        np.testing.assert_array_equal(decode(captured), values)
        self.assertEqual(captured["captured_points"], 1200)

    def test_reset_during_copy_suppresses_late_payload_and_keeps_slot_bounded(self):
        request = self.hub.request_raw_capture("/cloud")
        entered, release = threading.Event(), threading.Event()
        original = capture_xyz

        def blocked(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(1))
            return original(*args, **kwargs)

        outcomes = []
        with patch("robot_dashboard.ros.pointcloud.capture_xyz", side_effect=blocked):
            worker = threading.Thread(target=lambda: outcomes.append(self.process()))
            worker.start()
            self.assertTrue(entered.wait(1))
            self.hub.reset("/cloud")
            with self.assertRaises(RawCaptureBusy):
                self.hub.request_raw_capture("/cloud")
            release.set()
            worker.join(1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(outcomes, [False])
        self.assertEqual(self.hub.raw_capture_snapshot(request["capture_id"])["state"], "stale")
        self.assertFalse(self.hub.raw_capture_snapshot()["capture_active"])
        self.assertNotIn("xyz_bytes", self.hub._raw_capture._record)
        self.assertEqual(self.hub.binary_snapshot()["points_bytes"], b"")

    def test_source_replacement_and_old_subscription_callback_cannot_capture(self):
        self.assertTrue(self.process())
        request = self.hub.request_raw_capture("/cloud")
        value = message()
        value.header.frame_id = "new_lidar"
        self.clock[0] += .2
        self.process(value)
        self.assertEqual(self.hub.raw_capture_snapshot(request["capture_id"])["state"], "stale")
        request = self.hub.request_raw_capture("/cloud")
        with patch("robot_dashboard.ros.pointcloud.capture_xyz") as raw:
            self.assertFalse(self.process(observation_context=lambda: None))
        raw.assert_not_called()
        self.assertEqual(self.hub.raw_capture_snapshot(request["capture_id"])["state"], "awaiting")


if __name__ == "__main__":
    unittest.main()
