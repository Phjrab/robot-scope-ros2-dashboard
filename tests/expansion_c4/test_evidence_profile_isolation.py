from copy import deepcopy
from dataclasses import replace
import importlib.util
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
import yaml

from robot_dashboard.obstacle_runtime_adapter.evidence import ObservationEvidence, scene_with_observations
from robot_dashboard.obstacle_runtime_adapter.isolation import RuntimeConfig, require_local_ros, review_topic
from robot_dashboard.obstacle_runtime_adapter.nav2 import review_profile
from .fixtures import identity, occupancy, path

ROOT = Path(__file__).resolve().parents[2]


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.e = ObservationEvidence(binding=identity().binding, native=True)
        self.e.published(identity(), topic="/review/lidar_points")

    def costmap(self, stamp="1000000001", sequence=1, **kwargs):
        return self.e.costmap(occupancy(stamp), identity(frame_id="map", stamp_ns=stamp, source_id="global_costmap", sequence=sequence), scope="global", **kwargs)

    def test_publication_never_implies_ingestion_or_enforcement(self):
        s = self.e.snapshot()
        self.assertTrue(s["published_to_nav2"])
        self.assertFalse(s["costmap_ingestion_observed"])
        self.assertFalse(s["controller_consumption_observed"])
        self.costmap(expected_lethal_indices=(1,), source="FIXTURE")
        self.assertFalse(self.e.snapshot()["costmap_ingestion_observed"])

    def test_actual_snapshots_and_plan_change_are_time_correlated_only(self):
        # Native-labelled injected doubles verify the observer branch, not a
        # native test run. HANDOFF classifies this entire test as UNIT.
        self.e.path(path("1000000000"), identity(frame_id="map", stamp_ns="1000000000", source_id="plan"), source="NATIVE_NAV2_SIM")
        self.costmap(expected_lethal_indices=(1,), source="NATIVE_NAV2_SIM")
        self.e.path(path(x=1.), identity(frame_id="map", stamp_ns="1000000002", source_id="plan", sequence=2), source="NATIVE_NAV2_SIM")
        s = self.e.snapshot()
        self.assertTrue(s["costmap_ingestion_observed"])
        self.assertTrue(s["actual_plan_change_observed"])
        self.assertFalse(s["controller_consumption_observed"])
        self.assertEqual(s["global_path"]["poses"][0]["position_m"][2], .2)
        self.assertIsNone(s["local_trajectory"])

    def test_wrong_time_clock_cell_or_generation_not_ingestion(self):
        self.costmap(stamp="999999999", expected_lethal_indices=(1,), source="NATIVE_NAV2_SIM")
        self.assertFalse(self.e.ingestion)
        self.costmap(sequence=2, expected_lethal_indices=(0,), source="NATIVE_NAV2_SIM")
        self.assertFalse(self.e.ingestion)
        with self.assertRaises(ValueError):
            self.e.costmap(occupancy(), identity(frame_id="map", stamp_ns="1000000001", tf_epoch="tf2"), scope="local")
        self.e.costmap(occupancy(frame="odom"), identity(frame_id="odom", stamp_ns="1000000001", clock_domain="unknown"), scope="local", source="NATIVE_NAV2_SIM", expected_lethal_indices=(1,))
        self.assertFalse(self.e.ingestion)

    def test_reordered_snapshot_and_oversize_reject(self):
        self.costmap()
        with self.assertRaises(ValueError):
            self.costmap()
        msg = occupancy()
        msg.info.width = 100000
        with self.assertRaises(ValueError):
            self.e.costmap(msg, identity(frame_id="map", stamp_ns="1000000001"), scope="local")

    def test_fixture_mode_cannot_promote_native_labels(self):
        self.e.native = False
        self.costmap(expected_lethal_indices=(1,), source="NATIVE_NAV2_SIM")
        self.assertFalse(self.e.ingestion)

    def test_actual_snapshot_scene_port_and_epoch_fence(self):
        self.costmap()
        packet = {**identity().packet(), "obstacle_frame": {}, "global_path": None}
        result = scene_with_observations(packet, self.e)
        self.assertEqual(result["costmap_snapshot"]["global"]["data"], (0,100,-1,0))
        self.assertFalse(result["nav2_observation"]["controller_consumption_observed"])
        self.assertIsNone(packet["global_path"])
        with self.assertRaises(ValueError):
            scene_with_observations(dict(packet,tf_epoch="other"),self.e)


class ProfileIsolationTests(unittest.TestCase):
    def test_profile_keeps_lidar_separate_mark_only_geometry_single_inflation(self):
        base = yaml.safe_load((ROOT/"config/nav2_params_go2_humble.yaml").read_text())
        original = deepcopy(base)
        p = review_profile(base, envelope_radius_m=.65, safety_padding_m=.1)
        self.assertEqual(base, original)
        for name in ("global_costmap", "local_costmap"):
            c = p[name][name]["ros__parameters"]
            self.assertEqual(c["plugins"].count("inflation_layer"), 1)
            self.assertEqual(c["robot_radius"], .65)
            self.assertGreaterEqual(c["inflation_layer"]["inflation_radius"], .8)
            obs = c["obstacle_layer"]
            self.assertTrue(obs["lidar"]["marking"] and obs["lidar"]["clearing"])
            for source in ("depth", "geometry"):
                self.assertTrue(obs[source]["marking"])
                self.assertFalse(obs[source]["clearing"])
            self.assertFalse(obs["footprint_clearing_enabled"])
        smaller = review_profile(base, envelope_radius_m=.1, safety_padding_m=0.)
        self.assertEqual(smaller["global_costmap"]["global_costmap"]["ros__parameters"]["robot_radius"], .22)

    def test_endpoint_namespace_and_topic_rejected_before_any_io(self):
        for endpoint in ("http://192.168.123.161/state", "rtsp://camera", "/dev/video0", "http://localhost/state", "dds://robot"):
            with self.assertRaisesRegex(ValueError, "REAL_ENDPOINT"):
                RuntimeConfig(endpoint=endpoint)
        with self.assertRaises(ValueError):
            RuntimeConfig(mode="live")
        for topic in ("/cmd_vel", "/review/../cmd_vel", "/scan", "/review//scan"):
            with self.assertRaises(ValueError):
                review_topic(topic)

    def test_local_domain_guard_without_any_discovery(self):
        env = {"ROS_LOCALHOST_ONLY": "1", "ROS_DOMAIN_ID": "171", "RMW_IMPLEMENTATION": "rmw_fastrtps_cpp"}
        c = RuntimeConfig(mode="isolated_ros")
        with TemporaryDirectory() as d:
            root = Path(d)
            for name in ("udp", "udp6"):
                (root/name).write_text("header\n")
            self.assertEqual(require_local_ros(c, environ=env, proc_root=root)["graph_discovery"], "NOT_RUN")
            with self.assertRaises(ValueError):
                require_local_ros(c, environ=dict(env, ROS_LOCALHOST_ONLY="0"), proc_root=root)
            with self.assertRaises(ValueError):
                require_local_ros(c, environ=dict(env, ROS_DISCOVERY_SERVER="robot:11811"), proc_root=root)
            port = 7400 + 250*171
            (root/"udp").write_text(f"header\n0: 00000000:{port:04X} rest\n")
            with self.assertRaisesRegex(ValueError, "ALREADY_IN_USE"):
                require_local_ros(c, environ=env, proc_root=root)

    def test_import_and_construction_no_io_process_thread_or_ros_model(self):
        script = '''
import builtins, socket, subprocess, threading, sys
def forbidden(*args, **kwargs): raise AssertionError("unexpected I/O")
socket.socket = subprocess.Popen = threading.Thread.start = forbidden
from robot_dashboard.obstacle_runtime_adapter import RuntimeConfig
from robot_dashboard.obstacle_runtime_adapter.runtime import RuntimeAdapter
from robot_dashboard.obstacle_runtime_adapter import nav2, evidence, messages, command
RuntimeConfig()
command.CommandGate(command.MockCommandSink(), command.Binding("g",1,"l","e","f","c"))
assert not any(x in sys.modules for x in ("rclpy","pyrealsense2","ultralytics","torch"))
'''
        subprocess.run([sys.executable, "-c", script], cwd=ROOT, check=True, timeout=10)


class NativeAvailabilityTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("rclpy"), "NOT_RUN: ROS Humble/native Nav2 1.1.20 not installed; no DDS init")
    def test_generated_ros_message_roundtrip(self):
        # If ROS is available, generated types can be tested with no ROS init.
        from sensor_msgs.msg import PointCloud2, PointField
        from robot_dashboard.obstacle_runtime_adapter.messages import pointcloud2
        from robot_dashboard.obstacle_runtime_adapter.nav2 import observation, ros_pointcloud
        from .fixtures import cloud
        sample = pointcloud2(cloud(), identity(), origin_m=(0,0,0))
        obs = observation(sample, topic="/review/test", source_kind="lidar", now_ns=1_000_000_000, receipt_clock_id="host-fixture")
        self.assertEqual(pointcloud2(ros_pointcloud(obs, pointcloud_type=PointCloud2, field_type=PointField), identity()).payload["xyz_m"], sample.payload["xyz_m"])
