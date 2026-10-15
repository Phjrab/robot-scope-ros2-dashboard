"""Run production runtime callbacks with ROS-shaped messages and graph data."""

import copy
import json
import sys
import types
import unittest
from unittest import mock

import numpy as np

from robot_dashboard import navigation_runtime as runtime
from robot_dashboard.localization_diagnostics import MAX_TRACE, sanitize_localization_diagnostics


def obj(**values):
    return types.SimpleNamespace(**values)


def vector(x=0.0, y=0.0, z=0.0):
    return obj(x=x, y=y, z=z)


def pose():
    return obj(position=vector(), orientation=obj(x=0.0, y=0.0, z=0.0, w=1.0))


def header(stamp_ns=100_000_000_000, frame="camera_init"):
    return obj(stamp=obj(sec=stamp_ns // 1_000_000_000, nanosec=stamp_ns % 1_000_000_000), frame_id=frame)


def odometry(stamp_ns=100_000_000_000, frame="camera_init", child="body", x=0.0):
    value = obj(header=header(stamp_ns, frame), child_frame_id=child,
                pose=obj(pose=pose(), covariance=[0.0] * 36),
                twist=obj(twist=obj(linear=vector(), angular=vector()), covariance=[0.0] * 36))
    value.pose.pose.position.x = x
    return value


def cloud(stamp_ns=100_000_000_000):
    xyz = np.asarray([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, -1.0, 0.0]], dtype=np.float32)
    return obj(header=header(stamp_ns, "hesai_lidar"), data=xyz.tobytes(), width=4, height=1,
               point_step=12, row_step=48, is_bigendian=False,
               fields=[obj(name=name, offset=index * 4, datatype=7, count=1) for index, name in enumerate(("x", "y", "z"))])


class PoseMessage:
    def __init__(self):
        self.header = header()
        self.pose = obj(pose=pose(), covariance=[0.0] * 36)


class TransformMessage:
    def __init__(self):
        self.header = header()
        self.child_frame_id = ""
        self.transform = obj(translation=vector(), rotation=obj(x=0.0, y=0.0, z=0.0, w=1.0))


class Publisher:
    def __init__(self):
        self.messages = []

    def publish(self, message):
        self.messages.append(message)


class Broadcaster:
    def __init__(self, _node):
        self.messages = []

    def sendTransform(self, message):
        self.messages.append(message)


class FakeNode:
    def __init__(self, _name):
        self.now_ns = 100_000_000_000
        self.publisher_counts = {"/velodyne_points": 1, "/Odometry": 1, "/initialpose": 1,
                                 runtime.FASTLIO_CONTROLLER_ODOM_TOPIC: 1}
        self.gids = {topic: b"\x01" for topic in self.publisher_counts}
        self.offered_reliability = "BEST_EFFORT"
        self.graph_calls = 0
        self.subscriptions = []

    def get_clock(self):
        return obj(now=lambda: obj(nanoseconds=self.now_ns, to_msg=lambda: header(self.now_ns).stamp))

    def create_publisher(self, *_args):
        return Publisher()

    def create_subscription(self, message_type, topic, callback, qos):
        self.subscriptions.append(obj(message_type=message_type, topic=topic, callback=callback, qos=qos))

    def create_timer(self, *_args):
        pass

    def count_publishers(self, topic):
        return self.publisher_counts.get(topic, 0)

    def get_publishers_info_by_topic(self, topic):
        self.graph_calls += 1
        return [obj(endpoint_gid=self.gids[topic] + bytes([index]), node_name="fastlio", node_namespace="/",
                    qos_profile=obj(reliability=obj(name=self.offered_reliability), durability=obj(name="VOLATILE")))
                for index in range(self.publisher_counts[topic])]

    def get_logger(self):
        return mock.Mock()


def ros_modules():
    modules = {}
    for package, attributes in {
        "geometry_msgs.msg": {"PoseWithCovarianceStamped": PoseMessage, "TransformStamped": TransformMessage},
        "nav_msgs.msg": {"Odometry": type("Odometry", (), {})},
        "rclpy.node": {"Node": FakeNode},
        "rclpy.qos": {
            "DurabilityPolicy": obj(TRANSIENT_LOCAL="TRANSIENT_LOCAL", VOLATILE="VOLATILE"),
            "HistoryPolicy": obj(KEEP_LAST="KEEP_LAST"),
            "ReliabilityPolicy": obj(RELIABLE="RELIABLE"),
            "QoSProfile": lambda **kwargs: obj(**kwargs),
            "qos_profile_sensor_data": obj(reliability="BEST_EFFORT", durability="VOLATILE", history="KEEP_LAST", depth=5),
        },
        "sensor_msgs.msg": {"LaserScan": PoseMessage, "PointCloud2": type("PointCloud2", (), {})},
        "std_msgs.msg": {"String": type("String", (), {})},
        "tf2_ros": {"StaticTransformBroadcaster": Broadcaster, "TransformBroadcaster": Broadcaster},
    }.items():
        if "." in package:
            parent = package.split(".")[0]
            modules.setdefault(parent, types.ModuleType(parent))
        module = types.ModuleType(package)
        module.__dict__.update(attributes)
        modules[package] = module
    return modules


class ProductionLocalizationStartupTests(unittest.TestCase):
    def setUp(self):
        self.monotonic_s = 1000.0
        self.patches = [
            mock.patch.dict(sys.modules, ros_modules()),
            mock.patch.object(runtime.time, "monotonic", side_effect=lambda: self.monotonic_s),
            mock.patch.object(runtime.time, "monotonic_ns", side_effect=lambda: int(self.monotonic_s * 1e9)),
            mock.patch.object(runtime.time, "time_ns", side_effect=lambda: 1_800_000_000_000_000_000 + int(self.monotonic_s * 1e9)),
        ]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.node_type = runtime._build_ros_runtime_node_class()
        self.node = self.make_node()

    def make_node(self, competition=False):
        options = obj(scan_bins=1441, range_min=0.4, range_max=10.0, z_min=-0.5, z_max=2.0,
                      cloud_frame="hesai_lidar", lidar_x=0.25, lidar_y=0.0, lidar_z=0.0, lidar_yaw=0.0,
                      cloud_timeout=0.75, odom_timeout=0.50,
                      controller_odom_mode="competition_fastlio" if competition else "strict_onboard",
                      controller_odom_topic=runtime.FASTLIO_CONTROLLER_ODOM_TOPIC if competition else runtime.STRICT_CONTROLLER_ODOM_TOPIC)
        return self.node_type(options)

    def health(self):
        self.node._on_health_timer()
        return json.loads(self.node._health_publisher.messages[-1].data)

    def tick(self, seconds=0.1):
        self.monotonic_s += seconds
        self.node.now_ns += int(seconds * 1e9)

    def snapshot(self):
        return self.node._input_diagnostics["odometry"].snapshot(self.monotonic_s)

    def test_no_input_discovery_and_qos_are_observable_without_readiness(self):
        health = self.health()
        diag = sanitize_localization_diagnostics(health["localization_diagnostics"])
        self.assertIsNotNone(diag)
        self.assertFalse(health["odom_fresh"])
        self.assertIsNone(health["odometry_age_s"])
        self.assertEqual(diag["inputs"]["odometry"]["age_null_reason"], "no_callbacks")
        odom_sub = next(sub for sub in self.node.subscriptions if sub.topic == "/Odometry")
        self.assertEqual(odom_sub.qos.reliability, "BEST_EFFORT")
        self.assertEqual(diag["inputs"]["odometry"]["publishers"][0]["gid"], "0100")
        # A discovered endpoint without delivered callbacks is not proof of
        # compatibility. Record offered QoS, and keep no-input unavailable.
        self.node.offered_reliability = "UNKNOWN"
        self.tick(1.0)
        no_delivery = self.health()["localization_diagnostics"]["inputs"]["odometry"]
        self.assertEqual(no_delivery["publishers"][0]["reliability"], "UNKNOWN")
        self.assertEqual(no_delivery["callback_count"], 0)
        self.assertEqual(no_delivery["age_null_reason"], "no_callbacks")

    def test_first_callback_before_discovery_recovers_without_stamp_rebasing(self):
        first = odometry()
        self.node._on_odometry(first)
        self.assertEqual(self.snapshot()["reject_counts"]["publisher_not_unique"], 1)
        self.health()
        self.node._on_odometry(first)
        self.assertTrue(self.node._odom_fresh())
        self.assertEqual(self.node._last_odom_source_stamp_ns, 100_000_000_000)
        self.assertEqual(self.snapshot()["last_accepted"]["source_stamp_ns"], 100_000_000_000)
        self.assertEqual(self.snapshot()["rate_null_reason"], "insufficient_accepted_samples")
        self.tick()
        self.node._on_odometry(odometry(self.node.now_ns))
        self.node._on_cloud(cloud(self.node.now_ns))
        health = self.health()
        self.assertTrue(health["cloud_fresh"])
        self.assertTrue(health["odom_fresh"])
        self.assertFalse(health["localized"])
        self.assertAlmostEqual(health["odometry_frequency_hz_raw"], 10.0)

    def test_stale_future_missing_frames_duplicates_and_numeric_pose_are_distinct(self):
        self.health()
        fixtures = [
            (odometry(99_499_999_999), "stale_stamp"),
            (odometry(100_250_000_001), "future_stamp"),
            (odometry(0), "missing_stamp"),
            (odometry(frame="odom"), "unexpected_frame"),
            (odometry(x=float("nan")), "invalid_pose"),
        ]
        for message, reason in fixtures:
            self.node._on_odometry(message)
            self.assertEqual(self.snapshot()["trace"][-1]["reason"], reason)
            self.assertFalse(self.node._odom_fresh())
        self.assertEqual(self.snapshot()["age_null_reason"], "all_received_rejected")
        malformed = odometry()
        malformed.header.stamp.nanosec = 1_000_000_000
        self.node._on_odometry(malformed)
        self.assertEqual(self.snapshot()["trace"][-1]["reason"], "invalid_stamp")
        self.node._on_odometry(odometry())
        self.node._on_odometry(odometry())
        self.assertEqual(self.snapshot()["trace"][-1]["reason"], "nonincreasing_stamp")
        self.assertEqual(self.snapshot()["accepted_count"], 1)

    def test_existing_freshness_boundaries_and_stamp_preservation(self):
        self.health()
        original = odometry(99_500_000_000)
        before = copy.deepcopy(original)
        self.node._on_odometry(original)
        self.assertTrue(self.node._odom_fresh())
        self.assertEqual(original, before)
        self.tick()
        self.node._on_odometry(odometry(self.node.now_ns + 250_000_000))
        self.assertTrue(self.node._odom_fresh())
        self.assertEqual(self.snapshot()["last_accepted"]["source_stamp_ns"], self.node.now_ns + 250_000_000)

    def test_duplicate_publishers_fail_closed_then_new_valid_input_recovers(self):
        self.health()
        self.node.publisher_counts["/Odometry"] = 2
        self.tick()
        self.health()
        self.node._on_odometry(odometry(self.node.now_ns))
        self.assertEqual(self.snapshot()["trace"][-1]["reason"], "publisher_not_unique")
        self.assertFalse(self.node._odom_fresh())
        self.node.publisher_counts["/Odometry"] = 1
        self.health()
        self.node._on_odometry(odometry(self.node.now_ns))
        self.assertTrue(self.node._odom_fresh())

    def test_rejected_input_cannot_silently_revive_old_map_alignment(self):
        self.health()
        self.node._on_odometry(odometry())
        self.node._map_to_odom = runtime.PlanarTransform(1.0, 2.0, 0.0)
        self.tick(0.6)
        self.node._on_odometry(odometry(100_000_000_000))
        self.assertIsNone(self.node._map_to_odom)
        self.node._on_odometry(odometry(self.node.now_ns))
        self.assertTrue(self.node._odom_fresh())
        self.assertIsNone(self.node._map_to_odom)

    def test_source_outage_then_resume_requires_new_initial_pose(self):
        self.health()
        self.node._on_odometry(odometry())
        self.node._map_to_odom = runtime.PlanarTransform(1.0, 2.0, 0.0)
        self.tick(0.6)
        self.assertFalse(self.node._odom_fresh())
        self.node._on_odometry(odometry(self.node.now_ns))
        self.assertTrue(self.node._odom_fresh())
        self.assertIsNone(self.node._map_to_odom)

    def test_publisher_restart_resets_samples_and_competition_gate_without_retiming(self):
        self.node = self.make_node(competition=True)
        self.health()
        self.node._on_odometry(odometry())
        self.assertEqual(len(self.node._controller_odom_publisher.messages), 1)
        self.node._map_to_odom = runtime.PlanarTransform(1.0, 2.0, 0.0)
        first_generation = self.snapshot()["source_generation"]
        self.node.gids["/Odometry"] = b"\x02"
        self.tick(1.1)
        changed = self.health()
        self.assertFalse(changed["odom_fresh"])
        self.assertIsNone(changed["odometry_age_s"])
        self.assertIsNone(self.node._map_to_odom)
        self.assertEqual(self.snapshot()["source_generation"], first_generation + 1)
        self.assertEqual(self.snapshot()["age_null_reason"], "rewarming_after_source_change")
        self.node._on_odometry(odometry(self.node.now_ns))
        self.assertTrue(self.node._odom_fresh())
        canonical = self.node._controller_odom_publisher.messages[-1]
        self.assertEqual(canonical.header.stamp, header(self.node.now_ns).stamp)
        self.assertEqual(canonical.header.frame_id, "odom")

    def test_process_instance_restart_and_health_sequence_are_separate(self):
        old = self.health()
        self.node._on_odometry(odometry())
        self.tick(0.1)
        progressed = self.health()
        self.assertEqual(progressed["health_sequence"], old["health_sequence"] + 1)
        self.assertEqual(old["runtime_instance_generation"], progressed["runtime_instance_generation"])
        self.node = self.make_node()
        restarted = self.health()
        self.assertEqual(restarted["process_generation"], old["process_generation"])
        self.assertNotEqual(restarted["runtime_instance_generation"], old["runtime_instance_generation"])
        self.assertEqual(restarted["health_sequence"], 1)
        self.assertEqual(restarted["odometry_sequence"], 0)

    def test_ring_is_bounded_and_diagnostic_publication_is_at_most_one_hz(self):
        first = self.health()
        self.assertIn("localization_diagnostics", first)
        for _ in range(20):
            self.tick(0.01)
            self.node._on_odometry(odometry(self.node.now_ns))
            self.assertNotIn("localization_diagnostics", self.health())
        self.assertEqual(self.node.graph_calls, 2)
        self.assertEqual(len(self.snapshot()["trace"]), MAX_TRACE)
        self.assertEqual(self.snapshot()["callback_count"], 20)
        self.tick(1.0)
        latest = self.health()["localization_diagnostics"]
        self.assertEqual(latest["inputs"]["odometry"]["callback_count"], 20)
        self.assertEqual(len(latest["inputs"]["odometry"]["trace"]), MAX_TRACE)
        self.assertIsNone(latest["executor_lock_wait_s"])

    def test_api_sanitizer_rejects_oversize_nonfinite_and_extra_fields(self):
        raw = self.health()["localization_diagnostics"]
        raw["secret"] = "not projected"
        self.assertNotIn("secret", sanitize_localization_diagnostics(raw))
        for change in (
            lambda value: value.update(observed_monotonic_s=float("nan")),
            lambda value: value["inputs"]["odometry"].update(trace=[{}] * (MAX_TRACE + 1)),
            lambda value: value["inputs"]["odometry"].update(callback_count=True),
        ):
            invalid = copy.deepcopy(raw)
            change(invalid)
            self.assertIsNone(sanitize_localization_diagnostics(invalid))

    def test_unavailable_graph_metadata_does_not_invent_identity_or_grant_readiness(self):
        self.node.get_publishers_info_by_topic = mock.Mock(side_effect=RuntimeError("unsupported"))
        first = self.health()
        self.assertFalse(first["odom_fresh"])
        odom_diag = first["localization_diagnostics"]["inputs"]["odometry"]
        self.assertIsNone(odom_diag["publishers"])
        self.assertEqual(odom_diag["source_generation"], 0)
        self.node._on_odometry(odometry())
        self.assertTrue(self.node._odom_fresh())
        self.assertIsNone(self.node._map_to_odom)

    def test_cloud_callback_reports_rejection_before_accepted_scan(self):
        self.health()
        self.node._on_cloud(cloud(99_249_999_999))
        diag = self.node._input_diagnostics["cloud"].snapshot(self.monotonic_s)
        self.assertEqual(diag["trace"][-1]["reason"], "stale_stamp")
        self.assertEqual(diag["age_null_reason"], "all_received_rejected")
        invalid = cloud()
        invalid.fields = []
        self.node._on_cloud(invalid)
        self.node._on_cloud(cloud())
        diag = self.node._input_diagnostics["cloud"].snapshot(self.monotonic_s)
        self.assertEqual(diag["reject_counts"]["invalid_cloud_layout"], 1)
        self.assertEqual(diag["accepted_count"], 1)
        self.assertEqual(diag["last_accepted"]["source_stamp_ns"], 100_000_000_000)
        self.assertTrue(self.node._cloud_fresh())


if __name__ == "__main__":
    unittest.main()
