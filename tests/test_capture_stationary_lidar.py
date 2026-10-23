"""Synthetic ROS-shaped checks for the subscription-only field adapter."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
from typing import Any

from scripts import capture_stationary_lidar as script
from robot_dashboard.stationary_lidar_capture import CapturePlan


def plan(*, duration: float = 1., cloud_count: int = 1,
         max_cloud_bytes: int | None = None) -> CapturePlan:
    value = {"cloud_topic": "/velodyne_points", "odom_topic": "/Odometry",
        "tf_edges": [{"parent": "odom", "child": "base_link", "static": False},
                     {"parent": "base_link", "child": "hesai_lidar", "static": True}],
        "duration_s": duration, "cloud_count": cloud_count}
    if max_cloud_bytes is not None:
        value["max_cloud_bytes"] = max_cloud_bytes
    return CapturePlan.from_dict(value)


def stamp(seconds: float) -> NS:
    sec = int(seconds)
    return NS(sec=sec, nanosec=round((seconds - sec) * 1_000_000_000))


def header(frame: str, seconds: float) -> NS:
    return NS(frame_id=frame, stamp=stamp(seconds))


def cloud(seconds: float) -> NS:
    fields = [NS(name=name, offset=offset, datatype=7, count=1)
              for name, offset in (("x", 0), ("y", 4), ("z", 8))]
    return NS(header=header("hesai_lidar", seconds), width=1, height=1,
              point_step=12, row_step=12, is_bigendian=False, is_dense=True,
              fields=fields, data=struct.pack("<fff", 1., 2., 3.))


def odom(seconds: float) -> NS:
    pose = NS(position=NS(x=0., y=0., z=0.), orientation=NS(x=0., y=0., z=0., w=1.))
    twist = NS(linear=NS(x=0., y=0., z=0.), angular=NS(x=0., y=0., z=0.))
    return NS(header=header("camera_init", seconds), child_frame_id="body",
              pose=NS(pose=pose, covariance=[0.] * 36),
              twist=NS(twist=twist, covariance=[0.] * 36))


def transform(parent: str, child: str, seconds: float) -> NS:
    value = NS(translation=NS(x=0., y=0., z=0.), rotation=NS(x=0., y=0., z=0., w=1.))
    return NS(header=header(parent, seconds), child_frame_id=child, transform=value)


class Clock:
    def __init__(self) -> None:
        self.value = 100.

    def __call__(self) -> float:
        return self.value


class FakeRclpy:
    def __init__(self, clock: Clock, events: list[tuple[float, str, object, object | None]] | None = None) -> None:
        self.clock = clock
        self.events = sorted(events or [], key=lambda event: event[0])
        self.started = False
        self.spins = 0

    def init(self, *, args: list[str]) -> None:
        assert args == []
        self.started = True

    def ok(self) -> bool:
        return self.started

    def shutdown(self) -> None:
        self.started = False

    def spin_once(self, node: Any, *, timeout_sec: float) -> None:
        self.spins += 1
        assert 0 <= timeout_sec <= .1 + 1e-9
        if self.events and self.events[0][0] <= self.clock.value + timeout_sec + 1e-9:
            at, topic, message, info = self.events.pop(0)
            self.clock.value = max(self.clock.value, at)
            if topic == "__interrupt__":
                raise KeyboardInterrupt
            if topic == "__error__":
                raise RuntimeError("synthetic executor failure with private detail")
            callback = node.subscriptions.get(topic)
            if callback is not None:
                if info is None:  # Actual Humble dispatch supplies only the message.
                    callback(message)
                else:
                    callback(message, info)
        else:
            self.clock.value += timeout_sec


def fake_ros(clock: Clock, events: list[tuple[float, str, object, object | None]] | None = None,
             *, graph_ready_at: float = 100., graph_never_ready: bool = False,
             fail_destroy: bool = False, graph_change_at: float | None = None,
             tf_publishers: int = 1) -> tuple[dict[str, Any], FakeRclpy, Any]:
    rclpy = FakeRclpy(clock, events)

    class Node:
        instance: Any = None

        def __init__(self, name: str, *, enable_rosout: bool, start_parameter_services: bool,
                     enable_logger_service: bool = False, use_global_arguments: bool = False) -> None:
            assert name == "robot_scope_stationary_lidar_capture"
            assert enable_rosout is False and start_parameter_services is False
            assert enable_logger_service is False and use_global_arguments is False
            self.subscriptions: dict[str, object] = {}
            self.handles: dict[str, NS] = {}
            self.all_callbacks: dict[str, object] = {}
            self.destroyed = False
            self.created_topics: list[str] = []
            type(self).instance = self

        def count_publishers(self, topic: str) -> int:
            if graph_never_ready or clock.value < graph_ready_at:
                return 0
            return tf_publishers if topic == "/tf" else 1

        def get_publishers_info_by_topic(self, topic: str) -> list[NS]:
            if self.count_publishers(topic) == 0:
                return []
            gid_byte = 2 if topic == "/tf" and graph_change_at is not None and clock.value >= graph_change_at else 1
            topic_type = {"/velodyne_points": "sensor_msgs/msg/PointCloud2",
                          "/Odometry": "nav_msgs/msg/Odometry",
                          "/tf": "tf2_msgs/msg/TFMessage",
                          "/tf_static": "tf2_msgs/msg/TFMessage"}[topic]
            durability = "TRANSIENT_LOCAL" if topic == "/tf_static" else "VOLATILE"
            qos = NS(history="KEEP_LAST", depth=5, reliability="RELIABLE", durability=durability)
            return [NS(node_name=f"producer_{index}", node_namespace="/", topic_type=topic_type,
                       endpoint_gid=bytes([gid_byte + index] * 16), qos_profile=qos)
                    for index in range(self.count_publishers(topic))]

        def create_subscription(self, _message_type: object, topic: str, callback: object, qos: object) -> NS:
            self.subscriptions[topic] = callback
            self.all_callbacks[topic] = callback
            self.created_topics.append(topic)
            handle = NS(qos_profile=qos)
            self.handles[topic] = handle
            return handle

        def destroy_subscription(self, subscription: object) -> None:
            for topic, handle in list(self.handles.items()):
                if handle is subscription:
                    del self.subscriptions[topic]
                    del self.handles[topic]

        def destroy_node(self) -> None:
            self.destroyed = True
            if fail_destroy:
                raise RuntimeError("synthetic teardown failure")

    def qos_profile(**kwargs: object) -> NS:
        return NS(**kwargs)

    ros = {"rclpy": rclpy, "Node": Node, "QoSProfile": qos_profile,
           "HistoryPolicy": NS(KEEP_LAST="KEEP_LAST"),
           "ReliabilityPolicy": NS(BEST_EFFORT="BEST_EFFORT", RELIABLE="RELIABLE"),
           "DurabilityPolicy": NS(VOLATILE="VOLATILE", TRANSIENT_LOCAL="TRANSIENT_LOCAL"),
           "PointCloud2": type("PointCloud2", (), {}), "Odometry": type("Odometry", (), {}),
           "TFMessage": type("TFMessage", (), {})}
    return ros, rclpy, Node


def complete_events() -> list[tuple[float, str, object, object | None]]:
    dynamic_before = NS(transforms=[transform("odom", "base_link", 100.42)])
    dynamic_after = NS(transforms=[transform("odom", "base_link", 100.61)])
    static = NS(transforms=[transform("base_link", "hesai_lidar", 0.)])
    info = NS(publisher_gid=bytes([1] * 16), source_timestamp=100_550_000_000,
              received_timestamp=100_552_000_000, publication_sequence_number=4,
              reception_sequence_number=5)
    return [(100.1, "/tf_static", static, None),
            (100.42, "/Odometry", odom(100.42), None),
            (100.42, "/tf", dynamic_before, None),
            (100.55, "/velodyne_points", cloud(100.55), info),
            (100.61, "/Odometry", odom(100.61), None),
            (100.61, "/tf", dynamic_after, None)]


class CaptureStationaryLidarScriptTests(unittest.TestCase):
    def test_default_only_validates_explicit_plan_without_ros_or_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            path.write_text(json.dumps({"cloud_topic": "/velodyne_points", "odom_topic": "/Odometry",
                "tf_edges": [{"parent": "odom", "child": "base_link", "static": False}]}), encoding="utf-8")
            output = io.StringIO()
            with patch.object(script, "load_ros", side_effect=AssertionError("ROS imported")), redirect_stdout(output):
                self.assertEqual(script.main(["--plan", str(path)]), 0)
            self.assertEqual(json.loads(output.getvalue())["status"], "PLAN_VALIDATED_ONLY")
            self.assertEqual([item.name for item in Path(directory).iterdir()], ["plan.json"])

    def test_duplicate_and_deep_json_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            path.write_text('{"cloud_topic":"/a","cloud_topic":"/b"}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                script.load_plan(path)
            path.write_text("[" * 1200 + "0" + "]" * 1200, encoding="utf-8")
            with self.assertRaises(ValueError):
                script.load_plan(path)
            path.write_bytes(b"{" + b" " * script.MAX_PLAN_BYTES)
            with self.assertRaisesRegex(ValueError, "16 KiB"):
                script.load_plan(path)

    def test_execute_flags_are_required_before_ros_import(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            path.write_text(json.dumps({"cloud_topic": "/velodyne_points", "odom_topic": "/Odometry",
                "tf_edges": [{"parent": "odom", "child": "base_link", "static": False}]}), encoding="utf-8")
            with patch.object(script, "load_ros", side_effect=AssertionError("ROS imported")):
                for args in (["--plan", str(path), "--execute"],
                             ["--plan", str(path), "--execute", "--stationary-confirmed"],
                             ["--plan", str(path), "--execute", "--output", str(Path(directory) / "out")]):
                    with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
                        script.main(args)
            self.assertFalse((Path(directory) / "out").exists())

    def test_preflight_waits_for_graph_then_real_recorder_saves_complete_synthetic_data(self) -> None:
        clock = Clock()
        shifted = [(at + .5, topic, msg, info) for at, topic, msg, info in complete_events()]
        ros, runtime, node_type = fake_ros(clock, shifted, graph_ready_at=100.3)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "capture"
            result = script.run_capture(plan(), output, ros=ros, monotonic=clock,
                                        stationary_confirmed=True, data_kind="SYNTHETIC")
            manifest = json.loads((output / "manifest.json").read_text())
            summary = json.loads((output / "runtime-summary.json").read_text())
            self.assertEqual(result["status"], "READY_FOR_OFFLINE_INSPECTION")
            self.assertEqual(manifest["status"], "READY_FOR_OFFLINE_INSPECTION")
            self.assertEqual(summary["data_kind"], "SYNTHETIC")
            self.assertEqual(summary["middleware_cleanup_status"], "COMPLETE")
            self.assertEqual([row["topic"] for row in manifest["clouds"]], ["/velodyne_points"])
            self.assertEqual((output / "cloud-000.pointcloud2-data.bin").read_bytes(),
                             struct.pack("<fff", 1., 2., 3.))
            self.assertEqual(manifest["clouds"][0]["identity"]["rmw_message_info"]["source_timestamp"],
                             100_550_000_000)
            sessions = {row["identity"]["subscription_session_id"] for row in
                        [manifest["clouds"][0], manifest["odometry"][0], manifest["tf"][0]]}
            self.assertEqual(len(sessions), 3)
            self.assertEqual(node_type.instance.created_topics[-1], "/velodyne_points")
            self.assertTrue(node_type.instance.destroyed)
            self.assertFalse(runtime.ok())
            # A queued callback from a destroyed local subscription is fenced.
            manifest_bytes = (output / "manifest.json").read_bytes()
            node_type.instance.all_callbacks["/Odometry"](odom(100.9))
            self.assertEqual((output / "manifest.json").read_bytes(), manifest_bytes)
            self.assertEqual(node_type.instance.subscriptions, {})

    def test_missing_graph_is_not_run_and_creates_no_output(self) -> None:
        clock = Clock()
        ros, runtime, _ = fake_ros(clock, graph_never_ready=True)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "capture"
            result = script.run_capture(plan(), output, ros=ros, monotonic=clock,
                                        stationary_confirmed=True, data_kind="SYNTHETIC")
            self.assertEqual(result["status"], "NOT_RUN")
            self.assertEqual(result["reason"], "SOURCE_GRAPH_PREFLIGHT_UNAVAILABLE")
            self.assertFalse(output.exists())
            self.assertLessEqual(runtime.spins, 32)
            self.assertFalse(runtime.ok())

    def test_empty_executor_hits_finite_deadline(self) -> None:
        clock = Clock()
        ros, runtime, _ = fake_ros(clock)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "capture"
            result = script.run_capture(plan(duration=.6), output, ros=ros, monotonic=clock,
                                        stationary_confirmed=True, data_kind="SYNTHETIC")
            self.assertEqual(result["status"], "TIMED_OUT")
            self.assertEqual(result["middleware_cleanup_status"], "COMPLETE")
            self.assertLessEqual(runtime.spins, 8)
            self.assertTrue((output / "runtime-summary.json").exists())

    def test_cancel_during_preflight_is_not_run_and_after_arming_is_recorded(self) -> None:
        clock = Clock()
        ros, runtime, _ = fake_ros(clock, [(100.1, "__interrupt__", None, None)], graph_never_ready=True)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "capture"
            result = script.run_capture(plan(), output, ros=ros, monotonic=clock,
                                        stationary_confirmed=True, data_kind="SYNTHETIC")
            self.assertEqual((result["status"], result["reason"]), ("NOT_RUN", "OPERATOR_CANCELLED"))
            self.assertFalse(output.exists())
            self.assertFalse(runtime.ok())
        clock = Clock()
        ros, runtime, _ = fake_ros(clock, [(100.7, "__interrupt__", None, None)])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "capture"
            result = script.run_capture(plan(), output, ros=ros, monotonic=clock,
                                        stationary_confirmed=True, data_kind="SYNTHETIC")
            self.assertEqual(result["status"], "CANCELLED")
            self.assertEqual(json.loads((output / "manifest.json").read_text())["reason"], "OPERATOR_CANCELLED")
            self.assertFalse(runtime.ok())

    def test_oversized_cloud_is_rejected_without_raw_payload_file(self) -> None:
        clock = Clock()
        events = complete_events()
        large = cloud(100.55)
        large.width = 3
        large.row_step = 36
        large.data = large.data * 3
        events = [(at, topic, large if topic == "/velodyne_points" else msg, info)
                  for at, topic, msg, info in events]
        ros, _, _ = fake_ros(clock, events)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "capture"
            result = script.run_capture(plan(max_cloud_bytes=24), output, ros=ros, monotonic=clock,
                                        stationary_confirmed=True, data_kind="SYNTHETIC")
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(result["status"], "TIMED_OUT")
            self.assertIn("INVALID_OR_OVERSIZED_CLOUD", manifest["faults"])
            self.assertEqual(list(output.glob("*.bin")), [])

    def test_repeated_zero_stamp_static_tf_and_ambiguous_dynamic_graph(self) -> None:
        clock = Clock()
        events = complete_events()
        events.append((100.3, "/tf_static", NS(transforms=[transform("base_link", "hesai_lidar", 0.)]), None))
        ros, _, _ = fake_ros(clock, events)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "capture"
            result = script.run_capture(plan(), output, ros=ros, monotonic=clock,
                                        stationary_confirmed=True, data_kind="SYNTHETIC")
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(result["status"], "READY_FOR_OFFLINE_INSPECTION")
            self.assertEqual(len([item for item in manifest["tf"] if item["static"]]), 2)
            self.assertNotIn("SOURCE_STAMP_NOT_INCREASING:tf:base_link->hesai_lidar:static", manifest["faults"])
        clock = Clock()
        ros, _, _ = fake_ros(clock, complete_events(), tf_publishers=2)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "capture"
            result = script.run_capture(plan(), output, ros=ros, monotonic=clock,
                                        stationary_confirmed=True, data_kind="SYNTHETIC")
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(result["status"], "PARTIAL")
            self.assertTrue(any(fault.startswith("INVALID_IDENTITY_OR_TIME:tf:")
                                for fault in manifest["faults"]))
        clock = Clock()
        native_tf = NS(publisher_gid=bytes([1] * 16))
        events = [(at, topic, msg, native_tf if topic == "/tf" else info)
                  for at, topic, msg, info in complete_events()]
        ros, _, _ = fake_ros(clock, events, tf_publishers=2)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "capture"
            result = script.run_capture(plan(), output, ros=ros, monotonic=clock,
                                        stationary_confirmed=True, data_kind="SYNTHETIC")
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(result["status"], "READY_FOR_OFFLINE_INSPECTION")
            self.assertTrue(all(item["identity"]["publisher_gid"] for item in manifest["tf"]
                                if not item["static"]))

    def test_graph_endpoint_set_change_fences_record(self) -> None:
        clock = Clock()
        ros, _, _ = fake_ros(clock, complete_events(), graph_change_at=101.)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "capture"
            result = script.run_capture(plan(duration=1.5), output, ros=ros, monotonic=clock,
                                        stationary_confirmed=True, data_kind="SYNTHETIC")
            self.assertEqual(result["status"], "PARTIAL")
            self.assertIn("TF_GRAPH_ENDPOINT_SET_CHANGED", result["faults"])

    def test_executor_error_preserves_partial_manifest(self) -> None:
        clock = Clock()
        ros, runtime, _ = fake_ros(clock, [(100.7, "__error__", None, None)])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "capture"
            with self.assertRaises(RuntimeError):
                script.run_capture(plan(), output, ros=ros, monotonic=clock,
                                   stationary_confirmed=True, data_kind="SYNTHETIC")
            manifest = json.loads((output / "manifest.json").read_text())
            summary = json.loads((output / "runtime-summary.json").read_text())
            self.assertEqual(manifest["reason"], "ROS_CAPTURE_ERROR")
            self.assertEqual(summary["runtime_error_type"], "RuntimeError")
            self.assertFalse(runtime.ok())

    def test_cli_error_output_does_not_echo_ros_or_environment_details(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            path.write_text(json.dumps({"cloud_topic": "/velodyne_points", "odom_topic": "/Odometry",
                "tf_edges": [{"parent": "odom", "child": "base_link", "static": False}]}), encoding="utf-8")
            stderr = io.StringIO()
            with patch.object(script, "run_capture", side_effect=RuntimeError("private runtime detail")):
                with redirect_stderr(stderr):
                    code = script.main(["--plan", str(path), "--execute", "--stationary-confirmed",
                                        "--output", str(Path(directory) / "capture")])
            self.assertEqual(code, 2)
            self.assertIn("RuntimeError", stderr.getvalue())
            self.assertNotIn("private runtime detail", stderr.getvalue())

    def test_competing_tf_parent_is_a_fault_and_cleanup_is_reported_separately(self) -> None:
        clock = Clock()
        events = complete_events()
        events.append((100.63, "/tf", NS(transforms=[transform("wrong_parent", "base_link", 100.63)]), None))
        ros, _, _ = fake_ros(clock, events, fail_destroy=True)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "capture"
            result = script.run_capture(plan(), output, ros=ros, monotonic=clock,
                                        stationary_confirmed=True, data_kind="SYNTHETIC")
            manifest = json.loads((output / "manifest.json").read_text())
            summary = json.loads((output / "runtime-summary.json").read_text())
            self.assertIn("INVALID_OR_UNDECLARED_TF", manifest["faults"])
            self.assertEqual(result["middleware_cleanup_status"], "ERROR")
            self.assertEqual(summary["middleware_cleanup_status"], "ERROR")


if __name__ == "__main__":
    unittest.main()
