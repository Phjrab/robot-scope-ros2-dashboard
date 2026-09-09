import ast
import math
import struct
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from robot_dashboard.navigation_runtime import (
    NavigationRuntimeError,
    PlanarTransform,
    RmwSubscriptionTiming,
    ScanGeometry,
    bounded_pose_position,
    load_runtime_filter_settings,
    map_to_odom_transform,
    odometry_discontinuity_reason,
    odometry_frames_are_expected,
    project_xyz_to_scan,
    quaternion_to_yaw,
    xyz_from_pointcloud2_layout,
    yaw_to_quaternion,
    _build_rmw_timing_executor_class,
)


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "robot_dashboard" / "navigation_runtime.py"
SCRIPT = ROOT / "scripts" / "run_go2_navigation_humble.sh"


class PointCloudProjectionTests(unittest.TestCase):
    def test_projection_filters_nonfinite_height_and_range_then_keeps_nearest(self):
        geometry = ScanGeometry(
            angle_min=-math.pi,
            angle_max=math.pi,
            bins=9,
            range_min=0.2,
            range_max=5.0,
            z_min=-0.5,
            z_max=1.0,
        )
        points = np.asarray(
            [
                [2.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 2.0, 0.0],
                [-1.0, 0.0, 0.0],
                [1.0, 0.0, 2.0],
                [0.1, 0.0, 0.0],
                [float("nan"), 0.0, 0.0],
            ],
            dtype=np.float32,
        )
        projected = project_xyz_to_scan(points, geometry)
        self.assertEqual(projected.input_points, 7)
        self.assertEqual(projected.accepted_points, 4)
        self.assertAlmostEqual(float(projected.ranges[4]), 1.0)
        self.assertAlmostEqual(float(projected.ranges[6]), 2.0)
        self.assertAlmostEqual(float(projected.ranges[8]), 1.0)
        self.assertTrue(math.isinf(float(projected.ranges[0])))

    def test_decoder_handles_little_endian_organized_cloud_with_row_padding(self):
        point_step = 16
        width = 2
        height = 2
        row_step = width * point_step + 8
        payload = bytearray(row_step * height)
        expected = []
        for row in range(height):
            for column in range(width):
                values = (float(row), float(column), float(row + column))
                expected.append(values)
                struct.pack_into("<fff", payload, row * row_step + column * point_step, *values)
        xyz = xyz_from_pointcloud2_layout(
            payload,
            fields=[
                {"name": "x", "offset": 0, "datatype": 7, "count": 1},
                {"name": "y", "offset": 4, "datatype": 7, "count": 1},
                {"name": "z", "offset": 8, "datatype": 7, "count": 1},
            ],
            width=width,
            height=height,
            point_step=point_step,
            row_step=row_step,
            is_bigendian=False,
        )
        np.testing.assert_allclose(xyz, np.asarray(expected, dtype=np.float32))

    def test_decoder_rejects_missing_or_non_float_xyz(self):
        common = dict(
            data=bytes(16),
            width=1,
            height=1,
            point_step=16,
            row_step=16,
            is_bigendian=False,
        )
        with self.assertRaises(NavigationRuntimeError):
            xyz_from_pointcloud2_layout(
                fields=[{"name": "x", "offset": 0, "datatype": 7, "count": 1}],
                **common,
            )
        with self.assertRaises(NavigationRuntimeError):
            xyz_from_pointcloud2_layout(
                fields=[
                    {"name": name, "offset": index * 4, "datatype": 5, "count": 1}
                    for index, name in enumerate(("x", "y", "z"))
                ],
                **common,
            )

    def test_decoder_rejects_duplicate_or_overlapping_xyz(self):
        common = dict(
            data=bytes(16),
            width=1,
            height=1,
            point_step=16,
            row_step=16,
            is_bigendian=False,
        )
        duplicate = [
            {"name": "x", "offset": 0, "datatype": 7, "count": 1},
            {"name": "x", "offset": 4, "datatype": 7, "count": 1},
            {"name": "y", "offset": 4, "datatype": 7, "count": 1},
            {"name": "z", "offset": 8, "datatype": 7, "count": 1},
        ]
        with self.assertRaises(NavigationRuntimeError):
            xyz_from_pointcloud2_layout(fields=duplicate, **common)
        overlapping = [
            {"name": "x", "offset": 0, "datatype": 7, "count": 1},
            {"name": "y", "offset": 0, "datatype": 7, "count": 1},
            {"name": "z", "offset": 8, "datatype": 7, "count": 1},
        ]
        with self.assertRaises(NavigationRuntimeError):
            xyz_from_pointcloud2_layout(fields=overlapping, **common)

    def test_runtime_filter_sidecar_is_exact_and_fixed_topic_routed(self):
        valid = """
robot_scope_navigation_runtime:
  ros__parameters:
    scan_topic: /scan
    odom_topic: /Odometry
    cmd_vel_topic: /robot_scope/nav/cmd_vel_raw
    controller_odom_topic: /utlidar/robot_odom
    controller_odom_mode: strict_onboard
    min_obstacle_height: -0.5
    max_obstacle_height: 2.0
    obstacle_max_range: 8.0
    raytrace_max_range: 10.0
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "params.yaml"
            path.write_text(valid, encoding="utf-8")
            settings = load_runtime_filter_settings(path)
            self.assertEqual(settings.range_min, 0.4)
            self.assertEqual(settings.range_max, 10.0)
            self.assertEqual((settings.z_min, settings.z_max), (-0.5, 2.0))
            self.assertEqual(settings.controller_odom_topic, "/utlidar/robot_odom")
            self.assertEqual(settings.controller_odom_mode, "strict_onboard")

            path.write_text(valid.replace("/Odometry", "/other_odom"), encoding="utf-8")
            with self.assertRaises(NavigationRuntimeError):
                load_runtime_filter_settings(path)

            path.write_text(valid + "    extra_topic: /unsafe\n", encoding="utf-8")
            with self.assertRaises(NavigationRuntimeError):
                load_runtime_filter_settings(path)


class TransformMathTests(unittest.TestCase):
    def assertTransformAlmostEqual(self, actual, expected):
        self.assertAlmostEqual(actual.x, expected.x, places=7)
        self.assertAlmostEqual(actual.y, expected.y, places=7)
        self.assertAlmostEqual(actual.yaw, expected.yaw, places=7)

    def test_inverse_and_compose_form_identity(self):
        transform = PlanarTransform(1.2, -0.7, 1.1)
        self.assertTransformAlmostEqual(
            transform.compose(transform.inverse()),
            PlanarTransform(0.0, 0.0, 0.0),
        )

    def test_initial_pose_solves_map_to_odom(self):
        map_base = PlanarTransform(5.0, -2.0, math.pi / 2.0)
        odom_base = PlanarTransform(1.0, 2.0, math.pi / 4.0)
        map_odom = map_to_odom_transform(map_base, odom_base)
        self.assertTransformAlmostEqual(map_odom.compose(odom_base), map_base)

    def test_quaternion_round_trip_and_zero_rejection(self):
        quaternion = yaw_to_quaternion(-2.3)
        self.assertAlmostEqual(quaternion_to_yaw(*quaternion), -2.3)
        with self.assertRaises(NavigationRuntimeError):
            quaternion_to_yaw(0.0, 0.0, 0.0, 0.0)
        with self.assertRaises(NavigationRuntimeError):
            quaternion_to_yaw(0.0, 0.0, 0.0, 2.0)

    def test_pose_position_is_finite_and_bounded(self):
        self.assertEqual(bounded_pose_position(10, -20, 0.5), (10.0, -20.0, 0.5))
        for position in (
            (10_001.0, 0.0, 0.0),
            (0.0, -10_001.0, 0.0),
            (0.0, 0.0, 101.0),
            (float("nan"), 0.0, 0.0),
        ):
            with self.assertRaises(NavigationRuntimeError):
                bounded_pose_position(*position)

    def test_odometry_frame_contract_allows_only_optional_leading_slashes(self):
        self.assertTrue(odometry_frames_are_expected("camera_init", "body"))
        self.assertTrue(odometry_frames_are_expected("/camera_init", "/body"))
        self.assertFalse(odometry_frames_are_expected("odom", "base_link"))
        self.assertFalse(odometry_frames_are_expected("//camera_init", "body"))

    def test_fast_lio_discontinuity_is_detected_with_generous_margin(self):
        previous = PlanarTransform(1.0, 2.0, 0.2)
        self.assertEqual(
            odometry_discontinuity_reason(
                previous,
                PlanarTransform(1.03, 2.01, 0.22),
                0.02,
            ),
            "",
        )
        self.assertIn(
            "translation",
            odometry_discontinuity_reason(
                previous,
                PlanarTransform(4.0, 2.0, 0.2),
                0.02,
            ),
        )
        self.assertIn(
            "heading",
            odometry_discontinuity_reason(
                previous,
                PlanarTransform(1.0, 2.0, 2.5),
                0.02,
            ),
        )


class RmwSubscriptionTimingTests(unittest.TestCase):
    def test_humble_executor_forwards_message_and_captures_only_fixed_odometry(self):
        class FakeExecutor:
            def __init__(self):
                self.initialized = True

        fake_executors = types.ModuleType("rclpy.executors")
        fake_executors.SingleThreadedExecutor = FakeExecutor
        fake_rclpy = types.ModuleType("rclpy")
        node = mock.Mock()
        message = object()

        class FakeHandle:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def take_message(self, _message_type, _raw):
                return message, {
                    "source_timestamp": 900_000_000,
                    "received_timestamp": 1_000_000_000,
                }

        with mock.patch.dict(
            sys.modules,
            {"rclpy": fake_rclpy, "rclpy.executors": fake_executors},
        ):
            executor_type = _build_rmw_timing_executor_class()
        executor = executor_type(node)
        subscription = types.SimpleNamespace(
            handle=FakeHandle(),
            msg_type=object,
            raw=False,
            topic_name="/Odometry",
        )
        self.assertIs(executor._take_subscription(subscription), message)
        node._capture_odometry_rmw_metadata.assert_called_once_with(
            message,
            {
                "source_timestamp": 900_000_000,
                "received_timestamp": 1_000_000_000,
            },
        )

        node.reset_mock()
        subscription.topic_name = "/velodyne_points"
        self.assertIs(executor._take_subscription(subscription), message)
        node._capture_odometry_rmw_metadata.assert_not_called()

    def test_receive_and_executor_queue_windows_are_separate(self):
        timing = RmwSubscriptionTiming(maximum_samples=4)
        messages = [object(), object(), object()]
        received = [1_000_000_000, 1_100_000_000, 1_200_000_000]
        queued = [2_000_000, 4_000_000, 3_000_000]
        for message, received_ns, queue_ns in zip(messages, received, queued):
            self.assertTrue(
                timing.capture(
                    message,
                    {
                        "source_timestamp": received_ns - 10_000_000,
                        "received_timestamp": received_ns,
                    },
                )
            )
            self.assertTrue(
                timing.begin_callback(message, received_ns + queue_ns)
            )
        snapshot = timing.snapshot(1_205_000_000)
        self.assertAlmostEqual(
            snapshot["receive"]["frequency_hz_raw"], 10.0, places=9
        )
        self.assertAlmostEqual(snapshot["receive"]["max_gap_s"], 0.1, places=9)
        self.assertAlmostEqual(snapshot["queue"]["latest_s"], 0.003, places=9)
        self.assertAlmostEqual(snapshot["queue"]["max_s"], 0.004, places=9)
        self.assertEqual(snapshot["rejected_count"], 0)
        self.assertEqual(snapshot["missing_count"], 0)

    def test_metadata_is_fail_closed_but_diagnostic_only(self):
        timing = RmwSubscriptionTiming()
        for metadata in (
            None,
            {},
            {"received_timestamp": True},
            {"received_timestamp": "100"},
            {"received_timestamp": 0},
        ):
            self.assertFalse(timing.capture(object(), metadata))
        missing = object()
        self.assertFalse(timing.begin_callback(missing, 1_000_000_000))
        too_early = object()
        self.assertTrue(
            timing.capture(too_early, {"received_timestamp": 2_000_000_000})
        )
        self.assertFalse(timing.begin_callback(too_early, 1_999_999_999))
        too_late = object()
        self.assertTrue(
            timing.capture(too_late, {"received_timestamp": 1_000_000_000})
        )
        self.assertFalse(timing.begin_callback(too_late, 11_000_000_001))
        snapshot = timing.snapshot(12_000_000_000)
        self.assertEqual(snapshot["rejected_count"], 7)
        self.assertEqual(snapshot["missing_count"], 1)
        self.assertEqual(snapshot["queue"]["sample_count"], 0)

    def test_duplicate_receive_timestamp_does_not_fake_progression(self):
        timing = RmwSubscriptionTiming()
        first = object()
        second = object()
        metadata = {"received_timestamp": 1_000_000_000}
        timing.capture(first, metadata)
        timing.begin_callback(first, 1_001_000_000)
        timing.capture(second, metadata)
        timing.begin_callback(second, 1_002_000_000)
        snapshot = timing.snapshot(1_003_000_000)
        self.assertEqual(snapshot["receive"]["sample_count"], 1)
        self.assertEqual(snapshot["receive"]["interval_count"], 0)
        self.assertEqual(snapshot["queue"]["sample_count"], 2)


class NavigationLauncherSafetyTests(unittest.TestCase):
    def test_python_module_has_no_unitree_sport_publisher_or_dynamic_topics(self):
        source = MODULE.read_text(encoding="utf-8")
        ast.parse(source)
        self.assertNotIn("/api/sport/request", source)
        self.assertNotIn("cmd_vel_to_sport", source)
        self.assertIn('"/velodyne_points"', source)
        self.assertIn('"/Odometry"', source)
        self.assertIn('"/initialpose"', source)
        self.assertIn('"/robot_scope/nav/runtime_health"', source)
        self.assertIn("odometry_frames_are_expected(parent_frame, child_frame)", source)
        self.assertIn('self.count_publishers(topic)', source)
        self.assertIn("self._health_timer_rate.observe(started_at)", source)
        self.assertIn("self._publisher_count_durations.observe(", source)
        self.assertIn("class RmwTimingSingleThreadedExecutor", source)
        self.assertIn("message_info[1]", source)
        self.assertIn("rmw_received_timestamp.system_time", source)
        self.assertIn('self._publisher_counts["/velodyne_points"] == 1', source)
        self.assertIn('self._publisher_counts["/Odometry"] == 1', source)
        self.assertIn("rclpy.init(args=[])", source)
        self.assertIn("executor.spin()", source)
        self.assertNotIn("rclpy.spin(node)", source)
        self.assertNotIn("rclpy.init(args=None)", source)

    def test_launcher_syntax_and_fixed_raw_command_remap(self):
        subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertEqual(source.count("cmd_vel:=/robot_scope/nav/cmd_vel_raw"), 1)
        self.assertIn("cmd_vel:=/robot_scope/nav/recovery_cmd_vel_blocked", source)
        self.assertNotIn("/api/sport/request", source)
        self.assertNotIn("cmd_vel_to_sport", source)
        self.assertNotIn("pointcloud_to_laserscan", source)
        self.assertNotIn("go2_slam", source)
        self.assertNotIn("go2_tf", source)
        self.assertNotIn("eval ", source)
        self.assertNotIn("bash -c", source)
        self.assertIn("wait -n", source)

    def test_launcher_rejects_non_allowlisted_cli_shape_before_ros_setup(self):
        result = subprocess.run(
            [str(SCRIPT), "--map-yaml", "/tmp/example.yaml"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage:", result.stderr)


if __name__ == "__main__":
    unittest.main()
