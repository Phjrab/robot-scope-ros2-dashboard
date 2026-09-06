import ast
import importlib.util
import json
import math
import os
import stat
import struct
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

import numpy as np
import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


bridge = load_script("repository_xt16_fastlio_bridge", "scripts/xt16_fastlio_bridge.py")
saver = load_script("repository_save_map", "scripts/save_map.py")
converter = load_script(
    "repository_convert_pcd_to_occupancy",
    "scripts/convert_pcd_to_occupancy.py",
)
readiness = load_script("repository_xt16_readiness", "scripts/check_xt16_lidar_ready.py")


def field(name, offset, datatype, count=1):
    return types.SimpleNamespace(
        name=name,
        offset=offset,
        datatype=datatype,
        count=count,
    )


def raw_cloud(
    width=4_000,
    *,
    duration=0.1,
    point_step=32,
    scan_start=1_000.0,
    header_stamp=None,
):
    dtype = np.dtype(
        {
            "names": ["x", "y", "z", "intensity", "ring", "timestamp"],
            "formats": ["<f4", "<f4", "<f4", "<f4", "<u2", "<f8"],
            "offsets": [0, 4, 8, 12, 16, 18],
            "itemsize": point_step,
        }
    )
    values = np.zeros(width, dtype=dtype)
    values["x"] = np.linspace(0.0, 4.0, width, dtype=np.float32)
    values["y"] = 1.0
    values["z"] = 0.2
    values["intensity"] = 7.0
    values["ring"] = np.arange(width, dtype=np.uint16) % 16
    values["timestamp"] = np.linspace(scan_start, scan_start + duration, width)
    header_value = scan_start if header_stamp is None else float(header_stamp)
    header_sec = int(math.floor(header_value))
    return types.SimpleNamespace(
        header=types.SimpleNamespace(
            frame_id="hesai_lidar",
            stamp=types.SimpleNamespace(
                sec=header_sec,
                nanosec=int(round((header_value - header_sec) * 1_000_000_000)),
            ),
        ),
        width=width,
        height=1,
        fields=[field(*contract) for contract in bridge.RAW_FIELDS],
        is_bigendian=False,
        point_step=point_step,
        row_step=width * point_step,
        data=values.tobytes(),
    )


def laser_map(rows=2, width=12, padding=8, *, include_intensity=True):
    point_step = 16
    row_step = width * point_step + padding
    payload = bytearray(row_step * rows)
    names = ["x", "y", "z"] + (["intensity"] if include_intensity else [])
    formats = ["<f4"] * len(names)
    offsets = [0, 4, 8] + ([12] if include_intensity else [])
    dtype = np.dtype(
        {"names": names, "formats": formats, "offsets": offsets, "itemsize": point_step}
    )
    for row in range(rows):
        values = np.ndarray(
            shape=(width,),
            dtype=dtype,
            buffer=payload,
            offset=row * row_step,
        )
        values["x"] = np.arange(width, dtype=np.float32) * 0.02
        values["y"] = row * 0.02
        values["z"] = 0.1
        if include_intensity:
            values["intensity"] = 3.0
    first = np.ndarray(shape=(width,), dtype=dtype, buffer=payload, offset=0)
    first["x"][0] = np.nan
    return types.SimpleNamespace(
        header=types.SimpleNamespace(frame_id="camera_init"),
        width=width,
        height=rows,
        fields=[
            field("x", 0, saver.FLOAT32),
            field("y", 4, saver.FLOAT32),
            field("z", 8, saver.FLOAT32),
        ]
        + ([field("intensity", 12, saver.FLOAT32)] if include_intensity else []),
        is_bigendian=False,
        point_step=point_step,
        row_step=row_step,
        data=payload,
    )


def prime_clock(clock, *, next_scan_start, offset, monotonic_start=9.7):
    """Feed three stable calibration scans, all of which must be rejected."""

    case = unittest.TestCase()
    for index in range(bridge.CLOCK_RELOCK_REQUIRED_SAMPLES):
        scan_start = next_scan_start - 0.3 + index * 0.1
        scan_end = scan_start + 0.1
        with case.assertRaisesRegex(
            bridge.BridgeContractError, "initial calibration"
        ):
            clock.stamp(
                scan_start,
                scan_end,
                scan_end + offset,
                monotonic_start + index * 0.1,
            )
    return clock


class Xt16BridgeArtifactTests(unittest.TestCase):
    def test_high_rate_imu_callbacks_are_serialized_away_from_cloud_worker(self):
        source = (ROOT / "scripts" / "xt16_fastlio_bridge.py").read_text(
            encoding="utf-8"
        )
        self.assertEqual(
            source.count("self._imu_group = MutuallyExclusiveCallbackGroup()"),
            1,
        )
        self.assertNotIn("ReentrantCallbackGroup", source)
        self.assertIn("CLOCK_RESIDUAL_LIMIT_S = 0.25", source)
        self.assertIn("CONVERTED_CLOUD_MAX_AGE_S = 0.50", source)

    def test_cpp_runtime_preserves_python_reference_safety_contract(self):
        source = (
            ROOT
            / "ros2"
            / "robot_scope_xt16_bridge"
            / "src"
            / "xt16_fastlio_bridge.cpp"
        ).read_text(encoding="utf-8")
        package = (
            ROOT / "ros2" / "robot_scope_xt16_bridge" / "package.xml"
        ).read_text(encoding="utf-8")
        for contract in (
            'constexpr char kRawTopic[] = "/lidar_points"',
            'constexpr char kOutputCloudTopic[] = "/velodyne_points"',
            'constexpr char kOutputImuTopic[] = "/imu/body"',
            "constexpr std::size_t kCloudDecimation = 4",
            "constexpr std::size_t kOutputPointStep = 22",
            "constexpr double kClockResidualLimitS = 0.25",
            "constexpr double kConvertedCloudMaxAgeS = 0.50",
            "sample rejected without clock rebase",
            'Node("xt16_fastlio_bridge")',
        ):
            self.assertIn(contract, source)
        self.assertIn("rclcpp::KeepLast(1)).reliable().durability_volatile()", source)
        self.assertIn("rclcpp::KeepLast(5)).best_effort().durability_volatile()", source)
        self.assertIn("<depend>unitree_go</depend>", package)
        self.assertNotIn("create_publisher<unitree_go", source)

    def test_conversion_matches_readiness_layout_and_decimates_to_bounded_output(self):
        clock = prime_clock(
            bridge.ClockOffsetTracker(), next_scan_start=1_000.0, offset=0.1
        )
        converted = bridge.convert_xt16_cloud(
            raw_cloud(),
            received_s=1_000.2,
            received_monotonic_s=10.0,
            clock=clock,
        )
        self.assertEqual(converted.width, 1_000)
        self.assertEqual(converted.frame_id, "hesai_lidar")
        self.assertEqual(len(converted.data), converted.width * bridge.OUTPUT_POINT_STEP)
        self.assertEqual(
            bridge.OUTPUT_FIELDS,
            tuple(
                (item.name, item.offset, item.datatype, item.count)
                for item in readiness.VELODYNE_FIELDS
            ),
        )
        output = np.frombuffer(converted.data, dtype=bridge.OUTPUT_DTYPE)
        self.assertAlmostEqual(float(output["time"][0]), 0.0, places=6)
        self.assertGreater(float(output["time"][-1]), 0.09)
        self.assertTrue(np.isfinite(output["x"]).all())
        self.assertEqual(set(np.unique(output["ring"])), set(range(0, 16, 4)))
        self.assertEqual(converted.stamp_sec, 1_000)
        self.assertGreater(converted.stamp_nanosec, 90_000_000)
        self.assertLess(converted.stamp_nanosec, 110_000_000)

    def test_malformed_layout_scan_duration_and_nonfinite_points_fail_closed(self):
        wrong = raw_cloud()
        wrong.fields[-1] = field("timestamp", 20, bridge.FLOAT64)
        with self.assertRaisesRegex(bridge.BridgeContractError, "timestamp"):
            bridge.convert_xt16_cloud(
                wrong,
                received_s=1_000.2,
                clock=bridge.ClockOffsetTracker(),
            )
        with self.assertRaisesRegex(bridge.BridgeContractError, "duration"):
            bridge.convert_xt16_cloud(
                raw_cloud(duration=1.0),
                received_s=1_000.2,
                clock=bridge.ClockOffsetTracker(),
            )
        too_small = raw_cloud(width=3_999)
        with self.assertRaisesRegex(bridge.BridgeContractError, "4000"):
            bridge.convert_xt16_cloud(
                too_small,
                received_s=1_000.2,
                clock=bridge.ClockOffsetTracker(),
            )

    def test_sustained_callback_backlog_is_rejected_without_clock_rebase(self):
        clock = prime_clock(
            bridge.ClockOffsetTracker(), next_scan_start=100.0, offset=900.1
        )
        clock.stamp(100.0, 100.1, 1_000.2, 10.0)
        for index in range(1, 7):
            scan_start = 100.0 + index * 0.1
            scan_end = scan_start + 0.1
            received = scan_end + 900.5
            with self.assertRaisesRegex(bridge.BridgeContractError, "backlog"):
                clock.stamp(
                    scan_start,
                    scan_end,
                    received,
                    10.0 + (received - 1_000.2),
                )
        self.assertEqual(clock.relock_count, 0)
        self.assertAlmostEqual(clock.offset_s, 900.1)

    def test_wall_clock_step_relocks_only_after_stable_rejected_samples(self):
        clock = prime_clock(
            bridge.ClockOffsetTracker(), next_scan_start=100.0, offset=900.1
        )
        clock.stamp(100.0, 100.1, 1_000.2, 10.0)
        for index in range(1, bridge.CLOCK_RELOCK_REQUIRED_SAMPLES + 1):
            scan_start = 100.0 + index * 0.1
            with self.assertRaisesRegex(bridge.BridgeContractError, "relock"):
                clock.stamp(
                    scan_start,
                    scan_start + 0.1,
                    1_001.2 + index * 0.1,
                    10.0 + index * 0.1,
                )
        self.assertEqual(clock.relock_count, 1)
        seconds, nanoseconds = clock.stamp(100.4, 100.5, 1_001.6, 10.4)
        self.assertAlmostEqual(seconds + nanoseconds * 1e-9, 1_001.5, places=6)

    def test_raw_clock_reset_requires_progress_and_full_window_stability(self):
        clock = prime_clock(
            bridge.ClockOffsetTracker(), next_scan_start=100.0, offset=900.1
        )
        clock.stamp(100.0, 100.1, 1_000.2, 10.0)
        for scan_end, offset in ((50.1, 950.1), (50.2, 950.119), (50.3, 950.138)):
            with self.assertRaises(bridge.BridgeContractError):
                clock.stamp(
                    scan_end - 0.1,
                    scan_end,
                    scan_end + offset,
                    10.0 + (scan_end - 50.0),
                )
        self.assertEqual(clock.relock_count, 0)

        replay = prime_clock(
            bridge.ClockOffsetTracker(), next_scan_start=100.0, offset=900.1
        )
        replay.stamp(100.0, 100.1, 1_000.2, 10.0)
        for index in range(4):
            with self.assertRaises(bridge.BridgeContractError):
                replay.stamp(50.0, 50.1, 1_000.2 + index * 0.001, 11.0 + index * 0.001)
        self.assertEqual(replay.relock_count, 0)

    def test_raw_clock_reset_relocks_after_stable_progressing_samples(self):
        clock = prime_clock(
            bridge.ClockOffsetTracker(), next_scan_start=100.0, offset=900.1
        )
        clock.stamp(100.0, 100.1, 1_000.2, 10.0)
        for index in range(bridge.CLOCK_RELOCK_REQUIRED_SAMPLES):
            scan_end = 50.1 + index * 0.1
            with self.assertRaisesRegex(bridge.BridgeContractError, "relock"):
                clock.stamp(
                    scan_end - 0.1,
                    scan_end,
                    scan_end + 950.1,
                    11.0 + index * 0.1,
                )
        self.assertEqual(clock.relock_count, 1)
        seconds, nanoseconds = clock.stamp(50.3, 50.4, 1_000.5, 11.3)
        self.assertAlmostEqual(seconds + nanoseconds * 1e-9, 1_000.4, places=6)

    def test_published_stamp_regression_is_rejected_without_mutating_offset(self):
        clock = prime_clock(
            bridge.ClockOffsetTracker(), next_scan_start=100.0, offset=900.2
        )
        clock.stamp(100.0, 100.1, 1_000.3, 10.0)
        trusted_offset = clock.offset_s
        with self.assertRaisesRegex(bridge.BridgeContractError, "did not increase"):
            clock.stamp(100.1, 100.2, 1_000.21, 10.1)
        self.assertEqual(clock.offset_s, trusted_offset)

    def test_device_epoch_header_matches_payload_not_host_wall_clock(self):
        clock = bridge.ClockOffsetTracker()
        for index in range(bridge.CLOCK_RELOCK_REQUIRED_SAMPLES):
            scan_start = 100.0 + index * 0.1
            with self.assertRaisesRegex(
                bridge.BridgeContractError, "initial calibration"
            ):
                bridge.convert_xt16_cloud(
                    raw_cloud(scan_start=scan_start, header_stamp=scan_start),
                    received_s=1_000.2 + index * 0.1,
                    received_monotonic_s=10.0 + index * 0.1,
                    clock=clock,
                )
        converted = bridge.convert_xt16_cloud(
            raw_cloud(scan_start=100.3, header_stamp=100.3),
            received_s=1_000.5,
            received_monotonic_s=10.3,
            clock=clock,
        )
        self.assertEqual(converted.stamp_sec, 1_000)
        self.assertGreater(converted.stamp_nanosec, 390_000_000)

        with self.assertRaisesRegex(bridge.BridgeContractError, "device scan start"):
            bridge.convert_xt16_cloud(
                raw_cloud(scan_start=200.0, header_stamp=201.0),
                received_s=1_100.2,
                received_monotonic_s=20.0,
                clock=bridge.ClockOffsetTracker(),
            )

    def test_initial_clock_window_rejects_outlier_before_first_publish(self):
        clock = bridge.ClockOffsetTracker()
        observations = (
            (100.0, 1_000.7, 10.0),
            (100.1, 1_000.3, 10.1),
            (100.2, 1_000.4, 10.2),
            (100.3, 1_000.5, 10.3),
        )
        for scan_start, received, monotonic in observations:
            with self.assertRaisesRegex(
                bridge.BridgeContractError, "initial calibration"
            ):
                clock.stamp(
                    scan_start,
                    scan_start + 0.1,
                    received,
                    monotonic,
                )
        self.assertAlmostEqual(clock.offset_s, 900.1)
        seconds, nanoseconds = clock.stamp(100.4, 100.5, 1_000.6, 10.4)
        self.assertAlmostEqual(seconds + nanoseconds * 1e-9, 1_000.5, places=6)

    def test_initial_calibration_cloud_replay_is_never_first_publish(self):
        clock = bridge.ClockOffsetTracker()
        calibration = ()
        for index in range(bridge.CLOCK_RELOCK_REQUIRED_SAMPLES):
            scan_start = 100.0 + index * 0.1
            calibration = (scan_start, scan_start + 0.1)
            with self.assertRaisesRegex(
                bridge.BridgeContractError, "initial calibration"
            ):
                clock.stamp(*calibration, 1_000.1 + index * 0.1, 10.0 + index * 0.1)

        with self.assertRaisesRegex(
            bridge.BridgeContractError, "device timestamp did not increase"
        ):
            clock.stamp(*calibration, 1_000.31, 10.31)
        self.assertIsNone(clock._last_published_host_stamp_s)

        seconds, nanoseconds = clock.stamp(100.3, 100.4, 1_000.4, 10.3)
        self.assertAlmostEqual(seconds + nanoseconds * 1e-9, 1_000.3, places=6)
        trusted_offset = clock.offset_s
        with self.assertRaisesRegex(
            bridge.BridgeContractError, "device timestamp did not increase"
        ):
            clock.stamp(100.3, 100.4, 1_000.41, 10.31)
        self.assertEqual(clock.offset_s, trusted_offset)

    def test_raw_reset_relock_requires_wall_and_monotonic_progress(self):
        clock = prime_clock(
            bridge.ClockOffsetTracker(), next_scan_start=100.0, offset=900.1
        )
        clock.stamp(100.0, 100.1, 1_000.2, 10.0)
        for index in range(bridge.CLOCK_RELOCK_REQUIRED_SAMPLES + 1):
            scan_end = 50.1 + index * 0.1
            with self.assertRaises(bridge.BridgeContractError):
                clock.stamp(
                    scan_end - 0.1,
                    scan_end,
                    scan_end + 950.1,
                    11.0 + index * 0.3,
                )
        self.assertEqual(clock.relock_count, 0)
        self.assertAlmostEqual(clock.offset_s, 900.1)

    def test_raw_cloud_qos_is_latest_only_and_outputs_remain_reliable(self):
        source = (ROOT / "scripts/xt16_fastlio_bridge.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        profiles = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            if not isinstance(node.targets[0], ast.Name) or not isinstance(node.value, ast.Call):
                continue
            if getattr(node.value.func, "id", "") != "QoSProfile":
                continue
            profiles[node.targets[0].id] = {
                keyword.arg: keyword.value for keyword in node.value.keywords
            }
        raw = profiles["raw_cloud_qos"]
        output = profiles["output_qos"]
        lowstate = profiles["lowstate_qos"]
        self.assertEqual(raw["depth"].id, "RAW_CLOUD_QOS_DEPTH")
        self.assertEqual(raw["history"].attr, "KEEP_LAST")
        self.assertEqual(raw["reliability"].attr, "RELIABLE")
        self.assertEqual(raw["durability"].attr, "VOLATILE")
        self.assertEqual(output["depth"].id, "OUTPUT_QOS_DEPTH")
        self.assertEqual(output["history"].attr, "KEEP_LAST")
        self.assertEqual(output["reliability"].attr, "RELIABLE")
        self.assertEqual(output["durability"].attr, "VOLATILE")
        self.assertEqual(lowstate["history"].attr, "KEEP_LAST")
        self.assertEqual(lowstate["depth"].value, 5)
        self.assertEqual(lowstate["reliability"].attr, "BEST_EFFORT")
        self.assertEqual(lowstate["durability"].attr, "VOLATILE")
        self.assertEqual(bridge.RAW_CLOUD_QOS_DEPTH, 1)
        self.assertEqual(bridge.OUTPUT_QOS_DEPTH, 5)
        raw_subscriptions = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and getattr(node.func, "attr", "") == "create_subscription"
            and len(node.args) >= 4
            and isinstance(node.args[1], ast.Name)
            and node.args[1].id == "RAW_TOPIC"
        ]
        self.assertEqual(len(raw_subscriptions), 1)
        self.assertEqual(raw_subscriptions[0].args[3].id, "raw_cloud_qos")

    def test_lowstate_imu_is_finite_normalized_and_reordered(self):
        message = types.SimpleNamespace(
            imu_state=types.SimpleNamespace(
                quaternion=[2.0, 0.0, 0.0, 0.0],
                gyroscope=[1.0, 2.0, 3.0],
                accelerometer=[4.0, 5.0, 6.0],
            )
        )
        # A norm of two is deliberately rejected instead of forwarding
        # malformed orientation metadata into the mapping process.
        with self.assertRaisesRegex(bridge.BridgeContractError, "quaternion norm"):
            bridge.extract_imu_sample(message)
        message.imu_state.quaternion = [1.0, 0.1, 0.2, 0.3]
        sample = bridge.extract_imu_sample(message)
        self.assertAlmostEqual(sum(value * value for value in sample.orientation_xyzw), 1.0)
        self.assertEqual(sample.angular_velocity_xyz, (1.0, 2.0, 3.0))
        del message.imu_state.gyroscope
        with self.assertRaisesRegex(bridge.BridgeContractError, "gyroscope"):
            bridge.extract_imu_sample(message)

    def test_bridge_has_only_fixed_observation_and_mapping_topics(self):
        topics = {
            bridge.RAW_TOPIC,
            bridge.LOWSTATE_TOPIC,
            bridge.OUTPUT_CLOUD_TOPIC,
            bridge.OUTPUT_IMU_TOPIC,
        }
        self.assertEqual(
            topics,
            {"/lidar_points", "/lowstate", "/velodyne_points", "/imu/body"},
        )
        source = (ROOT / "scripts/xt16_fastlio_bridge.py").read_text(encoding="utf-8")
        for forbidden in ("/cmd_vel", "sport/request", "create_client(", "create_service("):
            self.assertNotIn(forbidden, source)
        self.assertIn("rclpy.init(args=[])", source)


class MapRuntimeArtifactTests(unittest.TestCase):
    def test_laser_map_encoder_handles_row_padding_and_optional_intensity(self):
        with_intensity = saver.pointcloud_to_pcd(laser_map())
        self.assertEqual(with_intensity.points, 23)
        records = np.frombuffer(with_intensity.payload, dtype=saver.PCD_DTYPE)
        self.assertTrue(np.isfinite(records["x"]).all())
        self.assertTrue(np.all(records["intensity"] == 3.0))

        without_intensity = saver.pointcloud_to_pcd(laser_map(include_intensity=False))
        records = np.frombuffer(without_intensity.payload, dtype=saver.PCD_DTYPE)
        self.assertTrue(np.all(records["intensity"] == 0.0))

    def test_atomic_pcd_writer_refuses_existing_or_symlink_outputs(self):
        snapshot = saver.pointcloud_to_pcd(laser_map())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "map.pcd"
            saver.write_pcd_exclusive(output, snapshot)
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            with self.assertRaisesRegex(saver.MapCaptureError, "already exists"):
                saver.write_pcd_exclusive(output, snapshot)
            linked = root / "linked.pcd"
            linked.symlink_to(output)
            with self.assertRaisesRegex(saver.MapCaptureError, "already exists"):
                saver.write_pcd_exclusive(linked, snapshot)

    def test_repository_converter_creates_a_valid_local_yaml_pgm_pair(self):
        dtype = saver.PCD_DTYPE
        points = np.zeros(40, dtype=dtype)
        points["x"] = np.tile(np.arange(10, dtype=np.float32) * 0.01, 4)
        points["y"] = np.repeat(np.arange(4, dtype=np.float32) * 0.01, 10)
        points["z"] = 0.1
        snapshot = saver.PcdSnapshot(
            header=(
                b"# .PCD v0.7\nVERSION 0.7\nFIELDS x y z intensity\n"
                b"SIZE 4 4 4 4\nTYPE F F F F\nCOUNT 1 1 1 1\n"
                b"WIDTH 40\nHEIGHT 1\nVIEWPOINT 0 0 0 1 0 0 0\n"
                b"POINTS 40\nDATA binary\n"
            ),
            payload=points.tobytes(),
            points=40,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            publication_root = root / "published"
            publication_root.mkdir(mode=0o700)
            prefix = root / "room"
            saver.write_pcd_exclusive(prefix.with_suffix(".pcd"), snapshot)
            result = converter.convert_staged_pcd(
                prefix, publication_root=publication_root
            )
            self.assertEqual(set(result["files"]), {"room.yaml", "room.pgm"})
            yaml_text = prefix.with_suffix(".yaml").read_text(encoding="utf-8")
            self.assertIn("image: room.pgm", yaml_text)
            self.assertIn("mode: trinary", yaml_text)
            self.assertTrue(prefix.with_suffix(".pgm").read_bytes().startswith(b"P5\n"))
            lineage = json.loads(
                (root / "room.map-family.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                lineage["source"]["pcd_map_id"],
                converter.SavedMapCatalog._opaque_id(
                    "pointcloud3d", publication_root.resolve() / "room.pcd"
                ),
            )
            self.assertEqual(
                lineage["occupancy"]["map_id"],
                converter.SavedMapCatalog._opaque_id(
                    "occupancy2d", publication_root.resolve() / "room.yaml"
                ),
            )

    def test_malformed_or_oversized_map_layout_is_rejected(self):
        message = laser_map()
        message.data = message.data[:-1]
        with self.assertRaisesRegex(saver.MapCaptureError, "payload length"):
            saver.pointcloud_to_pcd(message)
        message = laser_map()
        message.width = saver.MAX_POINTS + 1
        with self.assertRaisesRegex(saver.MapCaptureError, "2000000"):
            saver.pointcloud_to_pcd(message)
        message = laser_map()
        message.width = 1
        message.height = saver.MAX_ROWS + 1
        message.point_step = 16
        message.row_step = 16
        message.data = bytes(message.row_step * message.height)
        with self.assertRaisesRegex(saver.MapCaptureError, "4096-row"):
            saver.pointcloud_to_pcd(message)

    def test_mapping_scripts_help_without_ros_and_shells_are_valid(self):
        for relative in (
            "scripts/xt16_fastlio_bridge.py",
            "scripts/save_map.py",
            "scripts/convert_pcd_to_occupancy.py",
        ):
            result = subprocess.run(
                [sys.executable, str(ROOT / relative), "--help"],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertIn("usage:", result.stdout.lower())
        for relative in (
            "scripts/build_xt16_bridge_humble.sh",
            "scripts/run_xt16_bridge_humble.sh",
            "scripts/run_hesai_driver_humble.sh",
            "scripts/run_hesai_fastlio_humble.sh",
            "scripts/save_hesai_map_humble.sh",
            "scripts/start_xt16_preview_humble.sh",
            "scripts/start_wireless_xt16_preview_humble.sh",
            "scripts/start_wireless_mapping_humble.sh",
            "scripts/start_hesai_mapping_humble.sh",
        ):
            subprocess.run(["bash", "-n", str(ROOT / relative)], check=True)
        saver_source = (ROOT / "scripts/save_map.py").read_text(encoding="utf-8")
        self.assertIn("rclpy.init(args=[])", saver_source)

    def test_xt16_sysctl_artifact_only_raises_the_udp_receive_ceiling(self):
        source = (
            ROOT / "deploy" / "robot-scope-xt16-buffer.sysctl.example"
        ).read_text(encoding="utf-8")
        assignments = [
            line.strip()
            for line in source.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertEqual(assignments, ["net.core.rmem_max = 8388608"])
        self.assertNotIn("rmem_default", source)


class MappingConfigurationArtifactTests(unittest.TestCase):
    def test_repo_configs_preserve_the_verified_fixed_topic_contract(self):
        hesai = yaml.safe_load((ROOT / "config/hesai_xt16.yaml").read_text(encoding="utf-8"))
        entry = hesai["lidar"][0]
        udp = entry["driver"]["lidar_udp_type"]
        ros = entry["ros"]
        self.assertEqual(udp["device_ip_address"], "192.168.123.20")
        self.assertEqual(udp["udp_port"], 2368)
        self.assertEqual(entry["driver"]["device_udp_src_port"], 0)
        self.assertEqual(ros["ros_send_point_cloud_topic"], "/lidar_points")
        self.assertTrue(ros["send_point_cloud_ros"])

        fastlio = yaml.safe_load(
            (ROOT / "config/fastlio_xt16.yaml").read_text(encoding="utf-8")
        )["/**"]["ros__parameters"]
        self.assertEqual(fastlio["common"]["lid_topic"], "/velodyne_points")
        self.assertEqual(fastlio["common"]["imu_topic"], "/imu/body")
        self.assertEqual(fastlio["preprocess"]["lidar_type"], 2)
        self.assertTrue(fastlio["publish"]["map_en"])
        self.assertFalse(fastlio["pcd_save"]["pcd_save_en"])

    def test_runners_use_only_repository_owned_custom_files(self):
        bridge_runner = (ROOT / "scripts/run_xt16_bridge_humble.sh").read_text()
        driver_runner = (ROOT / "scripts/run_hesai_driver_humble.sh").read_text()
        fastlio_runner = (ROOT / "scripts/run_hesai_fastlio_humble.sh").read_text()
        self.assertIn("xt16_bridge_ws/install/lib/robot_scope_xt16_bridge", bridge_runner)
        self.assertNotIn("xt16_fastlio_bridge.py", bridge_runner)
        self.assertIn("$PROJECT_DIR/config/hesai_xt16.yaml", driver_runner)
        self.assertIn('config_path:="$FASTLIO_CONFIG_PATH"', fastlio_runner)
        self.assertIn('FASTLIO_CONFIG_FILE="fastlio_xt16.yaml"', fastlio_runner)
        self.assertIn("ROBOT_SCOPE_GO2_INTERFACE", fastlio_runner)
        self.assertIn("ROBOT_SCOPE_GO2_INTERFACE_CIDR", fastlio_runner)
        self.assertIn("ROBOT_SCOPE_LIVOX_SDK_PREFIX", fastlio_runner)
        self.assertIn("liblivox_lidar_sdk_shared.so", fastlio_runner)
        self.assertNotIn("$4 ~ /^192\\.168\\.123\\./", fastlio_runner)
        combined = bridge_runner + driver_runner + fastlio_runner
        self.assertNotIn("~/ws/go2_3d", combined)
        self.assertNotIn("src/FAST_LIO/config/xt16.yaml", combined)

        preview = (ROOT / "scripts/start_xt16_preview_humble.sh").read_text()
        mapping = (ROOT / "scripts/start_hesai_mapping_humble.sh").read_text()
        self.assertIn("run_hesai_driver_humble.sh", preview)
        self.assertIn("run_xt16_bridge_humble.sh", preview)
        self.assertIn('xt16_fastlio_bridge(_node|\\.py)', preview)
        self.assertNotIn("run_hesai_fastlio_humble.sh", preview)
        self.assertNotIn('stop_existing "hesai_ros_driver_node"', mapping)
        self.assertNotIn('stop_existing "xt16_fastlio_bridge.py"', mapping)
        self.assertNotIn("run_hesai_driver_humble.sh", mapping)
        self.assertNotIn("run_xt16_bridge_humble.sh", mapping)
        self.assertIn("run_hesai_fastlio_humble.sh", mapping)

    def test_dependency_manifest_pins_the_verified_upstream_revisions(self):
        manifest = json.loads(
            (ROOT / "config/ros_dependencies_humble.json").read_text(encoding="utf-8")
        )
        repositories = manifest["repositories"]
        revisions = {
            "unitree_ros2": "668d1ec5a05d1c38d3306bdca7d59f2ba3581a88",
            "hesai_ros2": "e7e112f0809f0eed5e3c81c55a1a0376474db234",
            "livox_sdk2": "08f523c930b2f0ba1e98a6afaa8d7476bf479908",
            "livox_ros_driver2": "4a1def929e5b59c7a8122d19fce6efba581ce9f7",
            "fast_lio": "2fffc570a25d0df172720bac034fbdb6a13d2162",
        }
        for name, revision in revisions.items():
            self.assertEqual(repositories[name]["commit"], revision)
        self.assertEqual(
            repositories["hesai_ros2"]["submodule_commit"],
            "9d5dc4fc4ade5be5f6a6ca00e71dd4050b054168",
        )
        self.assertEqual(manifest["ros_distro"], "humble")
        for name in revisions:
            item = repositories[name]
            self.assertTrue(item["url"].startswith("https://github.com/"))
            self.assertRegex(item["commit"], r"^[0-9a-f]{40}$")
            self.assertIn("go2-xt16", item["modes"])


if __name__ == "__main__":
    unittest.main()
