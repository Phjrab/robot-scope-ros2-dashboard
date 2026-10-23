"""Synthetic, ROS-free checks of the historical stationary diagnostic record."""

from __future__ import annotations

from array import array
import hashlib
import json
import os
from pathlib import Path
import struct
from types import SimpleNamespace as NS
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from robot_dashboard.ros.observation_identity import (
    ObservationIdentity, make_subscription_evidence, subscription_graph_snapshot,
)
from robot_dashboard.stationary_lidar_capture import CapturePlan, StationaryCapture
from robot_dashboard.ros.raw_pointcloud_capture import capture_xyz


QOS = {"reliability": "RELIABLE", "durability": "VOLATILE", "history": "KEEP_LAST", "depth": 5}
TYPES = {"/cloud": "sensor_msgs/msg/PointCloud2", "/odom": "nav_msgs/msg/Odometry",
         "/tf": "tf2_msgs/msg/TFMessage", "/tf_static": "tf2_msgs/msg/TFMessage"}


def obj(**values):
    return NS(**values)


def header(frame: str, stamp: int):
    return obj(frame_id=frame, stamp=obj(sec=stamp // 1_000_000_000, nanosec=stamp % 1_000_000_000))


def cloud(stamp: int = 1_000_000_000):
    # Organized big-endian PCD-compatible rows with a non-XYZ attribute and
    # explicit padding. The received raw bytes must remain byte-identical.
    dtype = np.dtype({"names": ["intensity", "z", "x", "y"],
                      "formats": [">u4", ">f8", ">f8", ">f8"],
                      "offsets": [0, 4, 12, 20], "itemsize": 32})
    rows = np.zeros((2, 2), dtype=dtype)
    values = np.array([[1 + 2**-40, -0., 3.], [4., 5., 6.], [7., 8., 9.], [np.nan, 0., 0.]])
    for index, name in enumerate(("x", "y", "z")):
        rows[name][:] = values[:, index].reshape(2, 2)
    rows["intensity"][:] = np.array([[10, 20], [30, 40]])
    payload = rows[0].tobytes() + b"PADDING!" + rows[1].tobytes()
    fields = [obj(name=name, offset=offset, datatype=datatype, count=1)
              for name, offset, datatype in (("intensity", 0, 6), ("z", 4, 8), ("x", 12, 8), ("y", 20, 8))]
    return obj(header=header("lidar", stamp), height=2, width=2, fields=fields, is_bigendian=True,
               point_step=32, row_step=72, is_dense=False, data=payload), values


def odom(stamp: int):
    xyz = obj(x=1., y=2., z=3.)
    quat = obj(x=0., y=0., z=0., w=1.)
    return obj(header=header("odom", stamp), child_frame_id="base_link",
               pose=obj(pose=obj(position=xyz, orientation=quat), covariance=array("d", [0.] * 36)),
               twist=obj(twist=obj(linear=xyz, angular=xyz), covariance=array("d", [1.] * 36)))


def tf(parent: str, child: str, stamp: int):
    return obj(header=header(parent, stamp), child_frame_id=child,
               transform=obj(translation=obj(x=.171, y=0., z=.0908),
                             rotation=obj(x=0., y=0., z=0., w=1.)))


def observation(topic: str, stamp: int, receipt: float, *, epoch="a" * 32, gid=True,
                session="b" * 32, count=1, reset=None, tracker=None):
    endpoint = {"node_name": "synthetic", "node_namespace": "/", "topic_type": TYPES[topic],
                "endpoint_gid": "c" * 32, "qos": QOS}
    graph = subscription_graph_snapshot(topic, TYPES[topic], count, [endpoint], receipt)
    evidence = make_subscription_evidence(session, topic, TYPES[topic], QOS, graph)
    info = obj(publisher_gid=bytes([5]) * 16) if gid else None
    if tracker is not None:
        result = tracker.observe(topic=topic, frame="base_link" if topic.startswith("/tf") else topic,
                                 stamp_ns=stamp, received=receipt, message_info=info,
                                 publisher_count=count, observation_context=evidence)
    else:
        result = {"observer_id": "observer", "publisher_epoch": epoch,
                  "publisher_gid": "05" * 16 if gid else None,
                  "identity_status": "OBSERVED_PUBLISHER" if gid and count == 1 and stamp else "UNAVAILABLE",
                  "publisher_count": count, "source_stamp_ns": str(stamp),
                  "source_clock": "ROS_HEADER_UNVERIFIED", "received_monotonic_s": receipt,
                  "receipt_clock": "OBSERVER_HOST_MONOTONIC", "subscription_evidence": evidence,
                  "reset_reason": reset, "native_session_id": None}
    result["rmw_message_info"] = {"source_timestamp": 123, "received_timestamp": 456,
                                  "publication_sequence_number": 7, "reception_sequence_number": 8}
    return result


def plan(**changes):
    value = {"cloud_topic": "/cloud", "odom_topic": "/odom",
             "tf_edges": [{"parent": "odom", "child": "base_link", "static": False},
                          {"parent": "base_link", "child": "lidar", "static": True}],
             "duration_s": 1., "cloud_count": 1}
    value.update(changes)
    return CapturePlan.from_dict(value)


class StationaryDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.clock = [10.]
        self.path = Path(self.folder.name) / "capture"

    def recorder(self, capture_plan=None, **options):
        return StationaryCapture(capture_plan or plan(), self.path, now=lambda: self.clock[0],
                                 data_kind="SYNTHETIC", **options)

    def put(self, recorder, kind, receipt, stamp, *, source=None, **options):
        self.clock[0] = receipt
        if kind == "cloud":
            msg, _ = cloud(stamp)
            recorder.add_cloud(msg, receipt, source or observation("/cloud", stamp, receipt, **options))
        elif kind == "odom":
            recorder.add_odom(odom(stamp), receipt, source or observation("/odom", stamp, receipt, **options))
        elif kind == "dynamic":
            recorder.add_tf(tf("odom", "base_link", stamp), receipt,
                            source or observation("/tf", stamp, receipt, **options))
        elif kind == "static":
            recorder.add_tf(tf("base_link", "lidar", stamp), receipt,
                            source or observation("/tf_static", stamp, receipt, **options), static=True)

    def complete(self, recorder, *, cloud_stamp=1_000_000_000):
        self.put(recorder, "static", 10.1, 0)
        return self.complete_after_static(recorder, cloud_stamp=cloud_stamp)

    def complete_after_static(self, recorder, *, cloud_stamp=1_000_000_000):
        self.put(recorder, "odom", 10.4, 2_000_000_000)
        self.put(recorder, "dynamic", 10.4, 3_000_000_000)
        self.put(recorder, "cloud", 10.5, cloud_stamp)
        self.put(recorder, "odom", 10.6, 2_100_000_000)
        self.put(recorder, "dynamic", 10.6, 3_100_000_000)
        self.clock[0] = 11.
        return recorder.finish(now=11.)

    def test_full_original_data_layout_xyz_hashes_and_receipt_only_brackets(self):
        recorder = self.recorder(stationary_confirmed=True)
        manifest = self.complete(recorder)
        self.assertEqual(manifest["status"], "READY_FOR_OFFLINE_INSPECTION")
        self.assertEqual(manifest["data_kind"], "SYNTHETIC")
        self.assertTrue(manifest["operator_stationary_asserted"])
        self.assertFalse(manifest["physical_stationarity_verified"])
        self.assertIsNone(manifest["current_pose"])
        self.assertFalse(manifest["tracking_verified"])
        record = manifest["clouds"][0]
        raw, expected_xyz = cloud()
        raw_bytes = (self.path / record["raw_data"]["file"]).read_bytes()
        xyz_bytes = (self.path / record["full_xyz"]["file"]).read_bytes()
        self.assertEqual(raw_bytes, raw.data)
        self.assertEqual(hashlib.sha256(raw_bytes).hexdigest(), record["raw_data"]["sha256"])
        self.assertEqual(hashlib.sha256(xyz_bytes).hexdigest(), record["full_xyz"]["sha256"])
        unpacked_xyz = np.frombuffer(xyz_bytes, dtype="<f8").reshape(-1, 3)
        np.testing.assert_array_equal(unpacked_xyz, expected_xyz)
        self.assertTrue(np.signbit(unpacked_xyz[0, 1]))
        self.assertEqual(record["layout"]["fields"][0]["name"], "intensity")
        self.assertEqual(record["layout"]["row_step"], 72)
        self.assertEqual(record["full_xyz"]["captured_points"], 4)
        self.assertEqual(record["full_xyz"]["nonfinite_points"], 1)
        self.assertFalse(record["full_xyz"]["sampling_applied"])
        self.assertEqual(len(manifest["odometry"][0]["pose"]["covariance"]), 36)
        self.assertEqual(manifest["odometry"][0]["twist"]["covariance"][0], 1.)
        self.assertEqual(record["identity"]["rmw_message_info"]["source_timestamp"], 123)
        self.assertIsNone(record["identity"]["native_session_id"])
        self.assertFalse(record["identity"]["source_clock_verified"])
        self.assertAlmostEqual(manifest["receipt_associations"][0]["odometry"]["before_delta_s"], .1)
        self.assertEqual(manifest["receipt_associations"][0]["tf_edges"][1]["association"]["basis"],
                         "DECLARED_STATIC_NOT_FRESH_DYNAMIC")
        self.assertEqual(json.loads((self.path / "manifest.json").read_text())["status"], manifest["status"])
        self.assertEqual(manifest["callbacks_omitted"], {"cloud": 0, "odom": 0, "tf": 0})

    def test_pre_roll_and_after_target_callbacks_are_counted_without_sampling_claim(self):
        recorder = self.recorder()
        self.put(recorder, "cloud", 10.1, 900_000_000)
        result = self.complete(recorder)
        self.assertEqual(result["status"], "READY_FOR_OFFLINE_INSPECTION")
        self.assertEqual(result["callbacks_seen"]["cloud"], 2)
        self.assertEqual(result["callbacks_stored"]["cloud"], 1)
        self.assertEqual(result["callbacks_omitted"]["cloud"], 1)

    def test_missing_brackets_and_early_finish_never_become_complete(self):
        recorder = self.recorder()
        self.put(recorder, "cloud", 10.5, 1_000_000_000)
        self.clock[0] = 10.7
        manifest = recorder.finish(now=10.7)
        self.assertEqual(manifest["status"], "PARTIAL")
        self.assertIn("RECEIPT_BRACKET_INCOMPLETE", manifest["faults"])
        self.assertIn("EARLY_FINISH_BEFORE_DECLARED_INTERVAL", manifest["faults"])

    def test_duplicate_stamp_source_change_bad_clock_and_cancellation_remain_diagnostic(self):
        recorder = self.recorder(plan(cloud_count=2))
        self.put(recorder, "cloud", 10.5, 1_000_000_000)
        self.put(recorder, "cloud", 10.7, 1_000_000_000, epoch="d" * 32)
        self.clock[0] = 11.
        manifest = recorder.finish(now=11., cancelled=True, reason="OPERATOR_CANCELLED")
        self.assertEqual(manifest["status"], "CANCELLED")
        self.assertTrue(any(item.startswith("SOURCE_IDENTITY_CHANGED") for item in manifest["faults"]))
        self.assertTrue(any(item.startswith("SOURCE_STAMP_NOT_INCREASING") for item in manifest["faults"]))
        self.assertEqual(manifest["callbacks_seen"]["cloud"], 2)

    def test_size_and_event_caps_leave_labelled_omission_counts(self):
        recorder = self.recorder(plan(max_events=2, max_cloud_bytes=80))
        self.put(recorder, "cloud", 10.5, 1_000_000_000)
        self.put(recorder, "odom", 10.6, 2_000_000_000)
        self.put(recorder, "odom", 10.7, 2_100_000_000)
        self.clock[0] = 11.
        manifest = recorder.finish(now=11.)
        self.assertNotEqual(manifest["status"], "READY_FOR_OFFLINE_INSPECTION")
        self.assertIn("EVENT_LIMIT_EXCEEDED", manifest["faults"])
        self.assertEqual(manifest["callbacks_seen"], {"cloud": 1, "odom": 2, "tf": 0})
        self.assertEqual(manifest["callbacks_omitted"]["cloud"], 1)
        self.assertEqual(manifest["callbacks_omitted"]["odom"], 1)

    def test_static_stamp_zero_replay_does_not_invent_dynamic_freshness(self):
        recorder = self.recorder(plan(duration_s=2.))
        tracker = ObservationIdentity()
        first = observation("/tf_static", 0, 10.1, tracker=tracker)
        self.put(recorder, "static", 10.1, 0, source=first)
        self.put(recorder, "odom", 10.4, 2_000_000_000)
        self.put(recorder, "dynamic", 10.4, 3_000_000_000)
        self.put(recorder, "cloud", 10.5, 1_000_000_000)
        self.put(recorder, "odom", 10.6, 2_100_000_000)
        self.put(recorder, "dynamic", 10.6, 3_100_000_000)
        self.put(recorder, "static", 10.7, 0,
                 source=observation("/tf_static", 0, 10.7, tracker=tracker))
        replay = observation("/tf_static", 0, 11.3, tracker=tracker)
        self.assertEqual(replay["reset_reason"], "SOURCE_STAMP_STALLED")
        self.put(recorder, "static", 11.3, 0, source=replay)
        self.put(recorder, "static", 11.4, 0,
                 source=observation("/tf_static", 0, 11.4, tracker=tracker))
        self.put(recorder, "odom", 11.5, 2_200_000_000)
        self.put(recorder, "dynamic", 11.5, 3_200_000_000)
        self.put(recorder, "cloud", 11.45, 1_100_000_000)
        self.put(recorder, "odom", 11.6, 2_300_000_000)
        self.put(recorder, "dynamic", 11.6, 3_300_000_000)
        self.clock[0] = 12.
        manifest = recorder.finish(now=12.)
        self.assertEqual(manifest["status"], "READY_FOR_OFFLINE_INSPECTION")
        self.assertEqual(len([item for item in manifest["tf"] if item["static"]]), 4)
        self.assertTrue(any(item["identity"]["observer_reset_reason"] == "SOURCE_STAMP_STALLED"
                            for item in manifest["tf"]))
        self.assertFalse(manifest["faults"])
        self.assertFalse(manifest["source_clock_synchronized"])

    def test_changed_static_transform_and_failure_reason_block_readiness(self):
        recorder = self.recorder()
        self.put(recorder, "static", 10.1, 0)
        changed = tf("base_link", "lidar", 0)
        changed.transform.translation.x = .25
        self.clock[0] = 10.2
        recorder.add_tf(changed, 10.2, observation("/tf_static", 0, 10.2), static=True)
        self.put(recorder, "odom", 10.4, 2_000_000_000)
        self.put(recorder, "dynamic", 10.4, 3_000_000_000)
        self.put(recorder, "cloud", 10.5, 1_000_000_000)
        self.put(recorder, "odom", 10.6, 2_100_000_000)
        self.put(recorder, "dynamic", 10.6, 3_100_000_000)
        self.clock[0] = 11.
        manifest = recorder.finish(now=11., reason="ROS_CAPTURE_ERROR")
        self.assertEqual(manifest["status"], "PARTIAL")
        self.assertIn('STATIC_TF_CHANGED:["base_link","lidar",true]', manifest["faults"])

    def test_silent_dynamic_dropout_after_good_early_brackets_is_not_ready(self):
        recorder = self.recorder(plan(duration_s=5.))
        self.put(recorder, "static", 10.1, 0)
        for kind, receipt, stamp in (("odom", 10.4, 2_000_000_000),
                                      ("dynamic", 10.4, 3_000_000_000),
                                      ("cloud", 10.5, 1_000_000_000),
                                      ("odom", 10.6, 2_100_000_000),
                                      ("dynamic", 10.6, 3_100_000_000)):
            self.put(recorder, kind, receipt, stamp)
        self.clock[0] = 15.
        manifest = recorder.finish(now=15.)
        self.assertEqual(manifest["status"], "PARTIAL")
        self.assertIn("TAIL_RECEIPT_GAP:cloud", manifest["faults"])
        self.assertIn("TAIL_RECEIPT_GAP:odom", manifest["faults"])
        self.assertIn('TAIL_RECEIPT_GAP:tf:["odom","base_link",false]', manifest["faults"])
        self.assertFalse(any("lidar" in reason and "TAIL" in reason for reason in manifest["faults"]))
        self.assertEqual(len(manifest["receipt_associations"]), 1)
        self.assertTrue(all(not row["within_one_second"] for row in manifest["dynamic_tail_coverage"]))

    def test_static_epoch_rebase_retains_new_epoch_and_rejects_provenance_changes(self):
        for changed in ("subscription", "gid", "observer", "graph", "publisher_count"):
            with self.subTest(changed=changed):
                path = Path(self.folder.name) / ("capture-" + changed)
                self.clock[0] = 10.
                recorder = StationaryCapture(plan(), path, now=lambda: self.clock[0], data_kind="SYNTHETIC")
                self.clock[0] = 10.1
                recorder.add_tf(tf("base_link", "lidar", 0), 10.1,
                                observation("/tf_static", 0, 10.1, epoch="a" * 32), static=True)
                self.clock[0] = 10.2
                source = observation("/tf_static", 0, 10.2, epoch="d" * 32,
                                     reset="SOURCE_STAMP_STALLED")
                if changed == "subscription":
                    source["subscription_evidence"]["session_id"] = "e" * 32
                elif changed == "gid":
                    source["publisher_gid"] = "06" * 16
                elif changed == "observer":
                    source["observer_id"] = "other-observer"
                elif changed == "graph":
                    source["subscription_evidence"]["graph"]["fingerprint"] = "0" * 64
                else:
                    source["publisher_count"] = 2
                recorder.add_tf(tf("base_link", "lidar", 0), 10.2, source, static=True)
                self.complete_after_static(recorder)
                manifest = json.loads((path / "manifest.json").read_text())
                self.assertEqual(manifest["status"], "PARTIAL")
                self.assertTrue(any(reason.startswith(("SOURCE_IDENTITY_CHANGED", "INVALID_IDENTITY_OR_TIME"))
                                    for reason in manifest["faults"]))
        # A local stamp-stall reset with unchanged provenance can advance the
        # epoch, and its next ordinary callback uses that new epoch.
        path = Path(self.folder.name) / "capture-clean-rebase"
        self.clock[0] = 10.
        recorder = StationaryCapture(plan(), path, now=lambda: self.clock[0], data_kind="SYNTHETIC")
        for receipt, epoch, reset in ((10.1, "a" * 32, None), (10.2, "d" * 32, "SOURCE_STAMP_STALLED"),
                                      (10.3, "d" * 32, None)):
            self.clock[0] = receipt
            recorder.add_tf(tf("base_link", "lidar", 0), receipt,
                            observation("/tf_static", 0, receipt, epoch=epoch, reset=reset), static=True)
        manifest = self.complete_after_static(recorder)
        self.assertEqual(manifest["status"], "READY_FOR_OFFLINE_INSPECTION")
        self.assertEqual([item["identity"]["observer_epoch"] for item in manifest["tf"] if item["static"]],
                         ["a" * 32, "d" * 32, "d" * 32])

    def test_tf_edge_names_with_separators_cannot_collide(self):
        capture_plan = plan(tf_edges=[{"parent": "a->b", "child": "c", "static": False},
                                      {"parent": "a", "child": "b->c", "static": False}])
        recorder = self.recorder(capture_plan)
        for parent, child, receipt, stamp in (("a->b", "c", 10.4, 3_000_000_000),
                                               ("a", "b->c", 10.4, 3_000_000_000),
                                               ("a->b", "c", 10.6, 3_100_000_000)):
            self.clock[0] = receipt
            recorder.add_tf(tf(parent, child, stamp), receipt,
                            observation("/tf", stamp, receipt))
        self.put(recorder, "odom", 10.4, 2_000_000_000)
        self.put(recorder, "cloud", 10.5, 1_000_000_000)
        self.put(recorder, "odom", 10.6, 2_100_000_000)
        self.clock[0] = 11.
        manifest = recorder.finish(now=11.)
        self.assertEqual(manifest["status"], "PARTIAL")
        edges = manifest["receipt_associations"][0]["tf_edges"]
        self.assertEqual(len(edges), 2)
        self.assertEqual([(item["parent"], item["child"]) for item in edges],
                         [("a->b", "c"), ("a", "b->c")])
        self.assertIsNotNone(edges[0]["association"])
        self.assertIsNone(edges[1]["association"])
        self.assertIn("RECEIPT_BRACKET_INCOMPLETE", manifest["faults"])

    def test_stale_queued_future_and_expensive_copy_callbacks_cannot_store_clouds(self):
        recorder = self.recorder()
        message, _ = cloud()
        for processing, receipt in ((10.5, 9.9), (10.6, 10.7), (11.6, 10.5), (11.7, 11.1)):
            self.clock[0] = processing
            recorder.add_cloud(message, receipt, observation("/cloud", 1_000_000_000, receipt))
        manifest = recorder.finish(now=11.7)
        self.assertEqual(manifest["status"], "TIMED_OUT")
        self.assertEqual(manifest["clouds"], [])
        self.assertIn("INVALID_IDENTITY_OR_TIME:cloud", manifest["faults"])
        self.assertEqual(manifest["callbacks_omitted"]["cloud"], 4)

        self.clock[0] = 10.
        second = StationaryCapture(plan(), Path(self.folder.name) / "copy-expired",
                                   now=lambda: self.clock[0], data_kind="SYNTHETIC")
        def delayed_decode(value, **limits):
            decoded = capture_xyz(value, **limits)
            self.clock[0] = 11.2
            return decoded
        self.clock[0] = 10.5
        with patch("robot_dashboard.stationary_lidar_capture.capture_xyz", side_effect=delayed_decode):
            second.add_cloud(message, 10.5, observation("/cloud", 1_000_000_000, 10.5))
        manifest = second.finish(now=11.2)
        self.assertIn("CLOUD_COPY_EXPIRED", manifest["faults"])
        self.assertFalse(list(second.path.glob("cloud-*.bin")))

    def test_nonfinite_values_and_invalid_quaternions_cannot_be_ready(self):
        recorder = self.recorder()
        bad_tf = tf("base_link", "lidar", 0)
        bad_tf.transform.rotation.w = 0.
        self.clock[0] = 10.1
        recorder.add_tf(bad_tf, 10.1, observation("/tf_static", 0, 10.1), static=True)
        bad_odom = odom(2_000_000_000)
        bad_odom.pose.pose.orientation.w = 0.
        self.clock[0] = 10.2
        recorder.add_odom(bad_odom, 10.2, observation("/odom", 2_000_000_000, 10.2))
        bad_odom = odom(2_100_000_000)
        bad_odom.twist.twist.linear.x = float("nan")
        self.clock[0] = 10.3
        recorder.add_odom(bad_odom, 10.3, observation("/odom", 2_100_000_000, 10.3))
        self.put(recorder, "static", 10.35, 0)
        manifest = self.complete_after_static(recorder)
        self.assertEqual(manifest["status"], "PARTIAL")
        self.assertIn("INVALID_OR_UNDECLARED_TF", manifest["faults"])
        self.assertIn("INVALID_ODOMETRY", manifest["faults"])
        self.assertEqual(len(manifest["odometry"]), 2)

    def test_total_byte_budget_preserves_small_partial_manifest_and_summary_reserve(self):
        capture_plan = plan(max_total_bytes=64 * 1024)
        recorder = self.recorder(capture_plan)
        message, _ = cloud()
        message.height, message.width = 1, 2000
        message.point_step, message.row_step = 12, 24_000
        message.fields = [obj(name=name, offset=offset, datatype=7, count=1)
                          for name, offset in (("x", 0), ("y", 4), ("z", 8))]
        message.data = struct.pack("<fff", 1., 2., 3.) * 2000
        self.clock[0] = 10.5
        recorder.add_cloud(message, 10.5, observation("/cloud", 1_000_000_000, 10.5))
        self.clock[0] = 11.
        manifest = recorder.finish(now=11.)
        self.assertEqual(manifest["status"], "TIMED_OUT")
        self.assertIn("TOTAL_BYTE_LIMIT_EXCEEDED", manifest["faults"])
        self.assertEqual(manifest["callbacks_omitted"]["cloud"], 1)
        self.assertFalse(list(self.path.glob("cloud-*.bin")))
        self.assertLessEqual(sum(item.stat().st_size for item in self.path.iterdir()) + 512,
                             capture_plan.max_total_bytes)

        self.clock[0] = 10.
        fallback_path = Path(self.folder.name) / "metadata-overflow"
        fallback = StationaryCapture(capture_plan, fallback_path, now=lambda: self.clock[0],
                                     data_kind="SYNTHETIC")
        for index in range(500):
            receipt, stamp = 10.001 + index * .001, 2_000_000_000 + index
            self.clock[0] = receipt
            fallback.add_odom(odom(stamp), receipt, observation("/odom", stamp, receipt))
        self.clock[0] = 11.
        partial = fallback.finish(now=11.)
        self.assertEqual(partial["status"], "PARTIAL")
        self.assertEqual(partial["reason"], "MANIFEST_BYTE_LIMIT")
        self.assertTrue(partial["receipt_association_metadata_omitted_due_to_limit"])
        for key in ("source_clock_verified", "source_clock_synchronized", "native_session_verified",
                    "physical_stationarity_verified", "body_extrinsic_verified",
                    "body_pose_verified", "tracking_verified"):
            self.assertFalse(partial[key], key)
        self.assertIsNone(partial["current_pose"])
        self.assertEqual(partial["operational_application"], "NOT_RUN")
        self.assertLessEqual(sum(item.stat().st_size for item in fallback_path.iterdir()) + 512,
                             capture_plan.max_total_bytes)

    def test_manifest_write_failure_closes_directory_and_rejects_late_callbacks(self):
        recorder = self.recorder()
        self.clock[0] = 11.
        with patch.object(recorder, "_write", side_effect=OSError("synthetic manifest write failure")):
            with self.assertRaisesRegex(OSError, "synthetic manifest write failure"):
                recorder.finish(now=11.)
        with self.assertRaises(OSError):
            os.fstat(recorder._fd)
        with self.assertRaises(RuntimeError):
            recorder.add_odom(odom(2_000_000_000), 11., observation("/odom", 2_000_000_000, 11.))
        with self.assertRaises(RuntimeError):
            recorder.note_fault("LATE_FAULT")
        with self.assertRaises(RuntimeError):
            recorder.finish(now=11.)

    def test_plan_and_output_path_fail_closed(self):
        for invalid in (plan().as_dict() | {"unknown": 1},
                        {"cloud_topic": "/tf", "odom_topic": "/odom", "tf_edges": [{"parent": "a", "child": "b", "static": False}]},
                        {"cloud_topic": "/cloud", "odom_topic": "/cloud", "tf_edges": [{"parent": "a", "child": "b", "static": False}]}):
            with self.assertRaises(ValueError):
                CapturePlan.from_dict(invalid)
        first = self.recorder()
        with self.assertRaises(FileExistsError):
            self.recorder()
        self.clock[0] = 11.
        first.finish(now=11., cancelled=True)
        symlink = Path(self.folder.name) / "redirect"
        symlink.symlink_to(self.folder.name)
        with self.assertRaises(ValueError):
            StationaryCapture(plan(), symlink / "new", now=lambda: 10.)


if __name__ == "__main__":
    unittest.main()
