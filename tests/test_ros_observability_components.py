import ast
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from robot_dashboard.ros.cameras import CameraHub
from robot_dashboard.ros.graph import RosGraphMonitor
from robot_dashboard.ros.pointcloud import PointCloudHub
from robot_dashboard.ros.runtime import RosRuntime
from robot_dashboard.ros.sources import SourceRegistry, pointcloud_source_metadata
from robot_dashboard.ros.telemetry import TelemetryHub


ROOT = Path(__file__).resolve().parents[1]
ROS_ROOT = ROOT / "robot_dashboard" / "ros"
AGENT_PATH = ROOT / "robot_dashboard" / "ros_agent.py"


class FakeGraphNode:
    def get_topic_names_and_types(self):
        return [
            ("/_hidden", ["std_msgs/msg/String"]),
            ("/scan", ["sensor_msgs/msg/LaserScan"]),
            ("/conflict", ["std_msgs/msg/String", "std_msgs/msg/Bool"]),
        ]

    @staticmethod
    def count_publishers(topic):
        return 1 if topic == "/scan" else 2

    @staticmethod
    def count_subscribers(topic):
        return 3 if topic == "/scan" else 0


class FakeReceiver:
    def __init__(self, source_id, configured=True):
        self.source_id = source_id
        self.configured = configured
        self.source_uri = f"fixed://{source_id}"
        self.starts = 0
        self.stops = 0

    def start(self):
        self.starts += 1
        return True

    def stop(self):
        self.stops += 1

    def status(self):
        return {
            "enabled": True,
            "configured": self.configured,
            "available": True,
            "live": self.starts > self.stops,
            "state": "ok" if self.starts > self.stops else "waiting",
            "source_label": self.source_id,
            "source": "test",
            "transport": "fixed_test",
            "uri": self.source_uri,
            "width": 640,
            "height": 480,
            "fps": 15.0,
            "age_s": 0.01,
            "last_error": "",
        }


class FakeDecoder:
    def __init__(self):
        self.stops = 0

    @staticmethod
    def feed(payload):
        return False

    def stop(self):
        self.stops += 1


class RosObservabilityComponentTests(unittest.TestCase):
    def test_runtime_instances_own_independent_threads_locks_and_status(self):
        first = RosRuntime()
        second = RosRuntime()
        self.assertIsNot(first.lock, second.lock)
        self.assertIsNot(first.stop_event, second.stop_event)
        completed = threading.Event()
        self.assertTrue(first.start(completed.set))
        first.join(1.0)
        self.assertTrue(completed.is_set())
        self.assertTrue(first.start(lambda: None))
        first.join(1.0)

    def test_graph_monitor_filters_hidden_topics_and_preserves_metric_contract(self):
        monitor = RosGraphMonitor(threading.RLock())
        monitor.graph = monitor.discover(FakeGraphNode())
        self.assertNotIn("/_hidden", monitor.graph)
        self.assertEqual(monitor.graph["/scan"]["category"], "lidar")
        self.assertEqual(monitor.graph["/conflict"]["category"], "conflict")
        monitor.tick("/scan", time.monotonic())
        snapshot = monitor.metric_snapshot("/scan", "lidar")
        self.assertEqual(snapshot["samples"], 1)
        self.assertEqual(snapshot["state"], "ok")
        topics = monitor.topics_snapshot({"/scan"})
        self.assertTrue(next(item for item in topics if item["name"] == "/scan")["selected"])

    def test_source_registry_keeps_fixed_identity_and_fail_closed_defaults(self):
        profile = {
            "name": "Unitree Go2",
            "robot_type": "go2",
            "source_selection": {
                "pointcloud": {
                    "persistent": True,
                    "fail_closed": True,
                    "allowed_offline": ["/velodyne_points"],
                    "default": "/velodyne_points",
                }
            },
        }
        registry = SourceRegistry(profile, None)
        self.assertEqual(registry.sources["pointcloud"], "/velodyne_points")
        self.assertIn("pointcloud", registry.pins)
        self.assertEqual(
            pointcloud_source_metadata("/velodyne_points")["sensor_id"],
            "hesai_xt16",
        )
        self.assertEqual(
            pointcloud_source_metadata("/lookalike_velodyne")["sensor_id"],
            "generic_pointcloud",
        )

    def test_camera_hub_owns_source_bound_exactly_once_demand(self):
        lock = threading.RLock()
        hub = CameraHub(lock, tick=lambda *_: None, selected_ros_topic=lambda: "")
        direct = FakeReceiver("go2_front")
        remote = FakeReceiver("realsense_color")
        decoder = FakeDecoder()
        hub.attach(direct, remote, decoder)
        self.assertFalse(hub.stream_open("go2_front")["accepted"])
        hub.accepting_demand = True
        first = hub.stream_open("go2_front")
        second = hub.stream_open("go2_front")
        self.assertTrue(first["accepted"])
        self.assertTrue(second["accepted"])
        self.assertEqual(direct.starts, 1)
        self.assertFalse(hub.stream_close("go2_front", "foreign")["released"])
        self.assertTrue(hub.stream_close("go2_front", first["token"])["released"])
        self.assertEqual(direct.stops, 0)
        self.assertTrue(hub.stream_close("go2_front", second["token"])["released"])
        self.assertEqual(direct.stops, 1)
        self.assertFalse(hub.stream_close("go2_front", second["token"])["released"])
        hub.shutdown()
        self.assertEqual(decoder.stops, 1)

    def test_pointcloud_hub_bounds_frame_and_preserves_binary_epoch(self):
        lock = threading.RLock()
        hub = PointCloudHub(
            lock,
            max_points=1_000,
            radius_limit_m=500.0,
            frame_interval_s=0.1,
        )
        values = np.asarray([(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)], dtype="<f4")
        message = SimpleNamespace(
            width=2,
            height=1,
            point_step=12,
            row_step=24,
            fields=[
                SimpleNamespace(name="x", offset=0, datatype=7),
                SimpleNamespace(name="y", offset=4, datatype=7),
                SimpleNamespace(name="z", offset=8, datatype=7),
            ],
            is_bigendian=False,
            data=values.tobytes(),
            header=SimpleNamespace(frame_id="map"),
        )
        self.assertTrue(
            hub.process(
                "/cloud",
                message,
                time.monotonic(),
                selected_topic=lambda: "/cloud",
                stamp_ns=lambda _: 123,
                robot_pose_in_frame=lambda _: None,
            )
        )
        binary = hub.binary_snapshot()
        self.assertEqual(binary["sent_points"], 2)
        self.assertEqual(len(binary["points_bytes"]), 24)
        self.assertEqual(binary["stream_id"], hub.stream_id)
        hub.reset("/replacement")
        self.assertEqual(hub.binary_snapshot()["points_bytes"], b"")
        with self.assertRaises(ValueError):
            hub.set_limit(PointCloudHub.MAX_CUSTOM_CLOUD_POINTS + 1, "/cloud")

    def test_telemetry_hub_rejects_oversize_maps_without_mutating_snapshot(self):
        hub = TelemetryHub(
            threading.RLock(),
            joint_stale_after_s=1.0,
            pose_stale_after_s=1.5,
            pose_position_limit_m=10_000.0,
        )
        before = hub.map_snapshot()
        message = SimpleNamespace(
            info=SimpleNamespace(width=4_001, height=4_000),
            data=[],
        )
        with self.assertRaisesRegex(ValueError, "dimensions/data"):
            hub.update_map("/map", message, time.monotonic(), stamp_ns=lambda _: 0)
        self.assertEqual(hub.map_snapshot(), before)


class RosAgentFacadeArchitectureTests(unittest.TestCase):
    def test_agent_constructs_each_observability_component_once(self):
        source = AGENT_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        init = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "__init__"
        )
        assigned_attributes = {
            node.targets[0].attr
            for node in ast.walk(init)
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Attribute)
        }
        self.assertTrue(
            {
                "_ros_runtime",
                "_graph_monitor",
                "_source_registry",
                "_telemetry_hub",
                "_camera_hub",
                "_pointcloud_hub",
            }.issubset(assigned_attributes)
        )
        self.assertLess(len(source.splitlines()), 4_000)

    def test_observability_components_do_not_depend_on_control_or_navigation(self):
        observability_modules = (
            "runtime.py",
            "graph.py",
            "sources.py",
            "telemetry.py",
            "cameras.py",
            "pointcloud.py",
        )
        for filename in observability_modules:
            path = ROS_ROOT / filename
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("from ..control", source, path.name)
            self.assertNotIn("from ..navigation", source, path.name)
            self.assertNotIn("fastapi", source, path.name)

    def test_public_observation_methods_delegate_through_components(self):
        source = AGENT_PATH.read_text(encoding="utf-8")
        for call in (
            "self._graph_monitor.topics_snapshot",
            "self._camera_hub.stream_open",
            "self._camera_hub.catalog_snapshot",
            "self._pointcloud_hub.json_snapshot",
            "self._telemetry_hub.map_snapshot",
            "self._source_registry.apply_selection",
        ):
            self.assertIn(call, source)
        self.assertIn("def navigation_activate", source)
        self.assertIn("def control_acquire", source)


if __name__ == "__main__":
    unittest.main()
