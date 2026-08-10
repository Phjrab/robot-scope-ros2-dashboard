import importlib.util
import json
import os
import stat
import sys
import tempfile
import types
import unittest
from pathlib import Path


if importlib.util.find_spec("rclpy") is None:
    class Dummy:
        pass

    rclpy = types.ModuleType("rclpy")
    rclpy.ok = lambda: False
    rclpy.init = lambda **kwargs: None
    rclpy.shutdown = lambda: None
    stubs = {
        "rclpy": rclpy,
        "rclpy.callback_groups": types.ModuleType("rclpy.callback_groups"),
        "rclpy.executors": types.ModuleType("rclpy.executors"),
        "rclpy.node": types.ModuleType("rclpy.node"),
        "rclpy.qos": types.ModuleType("rclpy.qos"),
        "rosidl_runtime_py": types.ModuleType("rosidl_runtime_py"),
        "rosidl_runtime_py.utilities": types.ModuleType("rosidl_runtime_py.utilities"),
        "std_msgs": types.ModuleType("std_msgs"),
        "std_msgs.msg": types.ModuleType("std_msgs.msg"),
    }
    stubs["rclpy.callback_groups"].MutuallyExclusiveCallbackGroup = Dummy
    stubs["rclpy.executors"].MultiThreadedExecutor = Dummy
    stubs["rclpy.node"].Node = Dummy
    for name in ("DurabilityPolicy", "HistoryPolicy", "QoSProfile", "ReliabilityPolicy"):
        setattr(stubs["rclpy.qos"], name, Dummy)
    stubs["rosidl_runtime_py.utilities"].get_message = lambda value: Dummy
    stubs["std_msgs.msg"].String = Dummy
    sys.modules.update(stubs)


from robot_dashboard.ros_agent import (  # noqa: E402
    RosAgent,
    SOURCE_SELECTION_STATE_MAX_BYTES,
)


POINT_TYPE = "sensor_msgs/msg/PointCloud2"
DEFAULT_XT16_TOPIC = "/velodyne_points"


def pointcloud(topic: str, publishers: int = 1) -> dict:
    return {
        "name": topic,
        "type": POINT_TYPE,
        "category": "pointcloud",
        "publishers": publishers,
    }


class SourceSelectionPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.profile_path = self.root / "go2.json"
        self.state_path = self.root / "state" / "sources.json"
        self.profile = {
            "name": "Unitree Go2",
            "robot_type": "go2",
            "control": {"enabled": False},
            "preferred_topics": {
                "pointcloud": [
                    "/cloud_registered",
                    "/Laser_map",
                    DEFAULT_XT16_TOPIC,
                    "/lidar_points",
                    "/utlidar/cloud_deskewed",
                ]
            },
            "source_selection": {
                "pointcloud": {
                    "default": DEFAULT_XT16_TOPIC,
                    "persistent": True,
                    "fail_closed": True,
                    "allowed_offline": [
                        "/lidar_points",
                        DEFAULT_XT16_TOPIC,
                        "/cloud_registered",
                        "/Laser_map",
                        "/utlidar/cloud_deskewed",
                    ],
                }
            },
        }
        self.profile_path.write_text(json.dumps(self.profile), encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def agent(self) -> RosAgent:
        return RosAgent(
            profile_path=str(self.profile_path),
            source_selection_path=str(self.state_path),
        )

    @staticmethod
    def refresh(agent: RosAgent, graph: dict) -> None:
        with agent._lock:
            agent._graph = graph
            agent._pick_default_sources_locked()

    def test_profile_default_stays_pinned_waiting_while_only_go2_lidar_is_live(self):
        agent = self.agent()
        self.refresh(
            agent,
            {"/utlidar/cloud_deskewed": pointcloud("/utlidar/cloud_deskewed")},
        )

        snapshot = agent.sources_snapshot()
        self.assertEqual(snapshot["selected"]["pointcloud"], DEFAULT_XT16_TOPIC)
        self.assertEqual(
            snapshot["selection"]["pointcloud"],
            {
                "mode": "pinned",
                "requested": DEFAULT_XT16_TOPIC,
                "origin": "profile_default",
                "persistent": True,
                "fail_closed": True,
            },
        )
        options = {item["topic"]: item for item in snapshot["options"]["pointcloud"]}
        self.assertIn("/utlidar/cloud_deskewed", options)
        self.assertIn(DEFAULT_XT16_TOPIC, options)
        selected = snapshot["selected_descriptors"]["pointcloud"]
        self.assertEqual(selected, options[DEFAULT_XT16_TOPIC])
        self.assertTrue(selected["pinned"])
        self.assertTrue(selected["configured"])
        self.assertFalse(selected["available"])
        self.assertFalse(selected["live"])
        self.assertEqual(selected["state"], "waiting")
        self.assertFalse(self.state_path.exists())

    def test_explicit_xt16_choice_persists_and_restores_without_a_publisher(self):
        first = self.agent()
        self.refresh(
            first,
            {
                "/lidar_points": pointcloud("/lidar_points"),
                "/utlidar/cloud_deskewed": pointcloud("/utlidar/cloud_deskewed"),
            },
        )
        selected = first.set_sources({"pointcloud": "/lidar_points"})
        self.assertEqual(selected["selected"]["pointcloud"], "/lidar_points")
        self.assertEqual(selected["selection"]["pointcloud"]["origin"], "user")

        mode = stat.S_IMODE(self.state_path.stat().st_mode)
        self.assertEqual(mode, 0o600)
        document = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(document["version"], 1)
        self.assertEqual(document["profile"]["robot_type"], "go2")
        self.assertEqual(
            document["selections"]["pointcloud"],
            {"mode": "pinned", "topic": "/lidar_points"},
        )

        restarted = self.agent()
        self.refresh(
            restarted,
            {"/utlidar/cloud_deskewed": pointcloud("/utlidar/cloud_deskewed")},
        )
        restored = restarted.sources_snapshot()
        self.assertEqual(restored["selected"]["pointcloud"], "/lidar_points")
        self.assertEqual(restored["selection"]["pointcloud"]["origin"], "persisted")
        self.assertEqual(
            restored["selected_descriptors"]["pointcloud"]["state"],
            "waiting",
        )

    def test_empty_selection_deletes_override_and_restores_profile_default(self):
        agent = self.agent()
        self.refresh(agent, {"/lidar_points": pointcloud("/lidar_points")})
        agent.set_sources({"pointcloud": "/lidar_points"})
        restored = agent.set_sources({"pointcloud": ""})

        self.assertEqual(restored["selected"]["pointcloud"], DEFAULT_XT16_TOPIC)
        self.assertEqual(
            restored["selection"]["pointcloud"]["origin"],
            "profile_default",
        )
        document = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(document["selections"], {})

        restarted = self.agent()
        self.refresh(
            restarted,
            {"/utlidar/cloud_deskewed": pointcloud("/utlidar/cloud_deskewed")},
        )
        self.assertEqual(
            restarted.sources_snapshot()["selected"]["pointcloud"],
            DEFAULT_XT16_TOPIC,
        )

    def test_configured_offline_topic_is_accepted_but_arbitrary_topics_are_rejected(self):
        agent = self.agent()
        self.refresh(
            agent,
            {
                "/utlidar/cloud_deskewed": pointcloud("/utlidar/cloud_deskewed"),
                "/custom_live": pointcloud("/custom_live"),
            },
        )

        offline = agent.set_sources({"pointcloud": "/Laser_map"})
        self.assertEqual(offline["selected"]["pointcloud"], "/Laser_map")
        self.assertEqual(
            offline["selected_descriptors"]["pointcloud"]["state"],
            "waiting",
        )
        with self.assertRaisesRegex(ValueError, "unknown ROS topic"):
            agent.set_sources({"pointcloud": "/not_configured"})
        with self.assertRaisesRegex(ValueError, "not allowed for persistent"):
            agent.set_sources({"pointcloud": "/custom_live"})
        self.assertEqual(agent.sources_snapshot()["selected"]["pointcloud"], "/Laser_map")

    def test_state_file_must_be_small_regular_owned_0600_and_profile_scoped(self):
        target = self.root / "target.json"
        target.write_text("{}", encoding="utf-8")
        self.state_path.parent.mkdir()
        self.state_path.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "regular file"):
            self.agent()
        self.state_path.unlink()

        self.state_path.write_bytes(b"x" * (SOURCE_SELECTION_STATE_MAX_BYTES + 1))
        self.state_path.chmod(0o600)
        with self.assertRaisesRegex(ValueError, "size limit"):
            self.agent()
        self.state_path.unlink()

        mismatch = {
            "version": 1,
            "profile": {"robot_type": "turtlebot", "name": "TurtleBot ROS 2"},
            "selections": {
                "pointcloud": {"mode": "pinned", "topic": "/lidar_points"}
            },
        }
        self.state_path.write_text(json.dumps(mismatch), encoding="utf-8")
        self.state_path.chmod(0o600)
        agent = self.agent()
        self.assertEqual(
            agent.sources_snapshot()["selected"]["pointcloud"],
            DEFAULT_XT16_TOPIC,
        )

    def test_persisted_topic_is_revalidated_against_profile_allowlist(self):
        self.state_path.parent.mkdir()
        document = {
            "version": 1,
            "profile": {"robot_type": "go2", "name": "Unitree Go2"},
            "selections": {
                "pointcloud": {"mode": "pinned", "topic": "/arbitrary"}
            },
        }
        self.state_path.write_text(json.dumps(document), encoding="utf-8")
        self.state_path.chmod(0o600)
        with self.assertRaisesRegex(ValueError, "not allowed by this profile"):
            self.agent()


if __name__ == "__main__":
    unittest.main()
