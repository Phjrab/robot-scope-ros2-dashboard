"""Synthetic ROS contract tests. These do not require a ROS installation."""
import json
import math
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock

from robot_dashboard.control import ControlDisabled, EmergencyStopLatched, LeaseBusy
from robot_dashboard.navigation_runtime import NavigationRuntimeError, PlanarTransform, _build_ros_runtime_node_class
from robot_dashboard.ros.initial_pose_receipt import wait_manual_seed_receipt
from robot_dashboard.ros.manual_navigation import MODE, OPERATIONAL_MODE, ManualSeed, context, load_manual_binding
from test_ros_navigation_gateway import CountNode, StubControlPort, gateway


PINS = {"mode": MODE, "job_id": "a" * 32, "map_id": "saved-map", "map_revision": "b" * 64}
INSTANCE = "123:456"
ODOM_NS = 9_800_000_000
REQUEST_NS = 9_900_000_000


def tf_batch(source_stamp):
    def transform(parent, child):
        sec, nanosec = divmod(source_stamp, 1_000_000_000)
        return NS(header=NS(frame_id=parent, stamp=NS(sec=sec, nanosec=nanosec)), child_frame_id=child)
    return NS(transforms=[transform("odom", "base_link"), transform("map", "odom")])


class ManualRuntimeTests(unittest.TestCase):
    def setUp(self):
        class StubNode:
            def __init__(self, _name):
                pass

        modules = {
            "geometry_msgs.msg": NS(PoseWithCovarianceStamped=object, TransformStamped=object),
            "nav_msgs.msg": NS(Odometry=object),
            "rclpy.node": NS(Node=StubNode),
            "rclpy.qos": NS(DurabilityPolicy=object, HistoryPolicy=object, QoSProfile=object,
                            ReliabilityPolicy=object, qos_profile_sensor_data=object()),
            "sensor_msgs.msg": NS(LaserScan=object, PointCloud2=object),
            "std_msgs.msg": NS(String=object),
            "tf2_ros": NS(StaticTransformBroadcaster=object, TransformBroadcaster=object),
        }
        with mock.patch.dict("sys.modules", modules):
            self.runtime_type = _build_ros_runtime_node_class()
            runtime = object.__new__(self.runtime_type)
        runtime._manual = ManualSeed(PINS, .5)
        runtime._manual.observe_sources((b"current graph",))
        runtime._runtime_instance_generation = INSTANCE
        runtime._options = NS(odom_timeout=.5)
        runtime._last_odom_source_stamp_ns = ODOM_NS
        runtime._odom_to_base = PlanarTransform(4., -2., -3.08)
        runtime.get_clock = lambda: NS(now=lambda: NS(nanoseconds=10_000_000_000))
        runtime._refresh_operational_authority = mock.Mock()
        runtime._refresh_manual_sources = mock.Mock()
        runtime._manual_input_reason = mock.Mock(return_value="")
        runtime._broadcast_dynamic_transforms = mock.Mock()
        runtime._map_to_odom = None
        self.runtime = runtime

    def _stopped(self):
        for index in range(12):
            now = 10. + index * .2
            stamp = 1_000_000_000 + index * 200_000_000
            self.runtime._manual.odom_stop.observe(stamp, now, 0., 0.)
            self.runtime._manual.controller_stop.observe(stamp, now, 0., 0.)

    def _request(self, **overrides):
        payload = {**PINS, "source_epoch": self.runtime._manual.source_epoch,
                   "runtime_instance_generation": INSTANCE, "stamp_ns": str(REQUEST_NS),
                   "operation": "seed", "seed_generation": self.runtime._manual.seed_generation,
                   "x": -1.5, "y": 6.5, "yaw": 3.09, **overrides}
        with mock.patch("robot_dashboard.navigation_runtime.time.monotonic", return_value=12.2):
            self.runtime._on_manual_seed(NS(data=json.dumps(payload)))

    def test_seed_binds_rotated_nonzero_odometry_and_requires_fresh_tf_echo(self):
        self._stopped()
        state = self.runtime._manual
        self._request()
        self.assertTrue(state.receipt["accepted"])
        self.assertEqual(state.receipt["odometry_stamp_ns"], str(ODOM_NS))
        self.assertEqual(state.receipt["accepted_ros_ns"], "10000000000")
        self.assertEqual(state.state, "checking_tf")
        expected = PlanarTransform(-1.5, 6.5, 3.09)
        anchor = self.runtime._map_to_odom
        mapped = anchor.compose(self.runtime._odom_to_base)
        for field in ("x", "y", "yaw"):
            self.assertAlmostEqual(getattr(mapped, field), getattr(expected, field))
        moved = anchor.compose(self.runtime._odom_to_base.compose(PlanarTransform(1., 0., .1)))
        self.assertAlmostEqual(moved.x, expected.x + math.cos(expected.yaw))
        self.assertAlmostEqual(moved.y, expected.y + math.sin(expected.yaw))
        self.assertLess(moved.yaw, -3.0)

        self.assertTrue(state.note_map_tf_publication(ODOM_NS))
        state.observe_tf(tf_batch(ODOM_NS - 1))
        self.assertFalse(state.tf_readback)
        state.observe_tf(tf_batch(ODOM_NS))
        self.assertTrue(state.tf_readback)
        self.assertEqual(state.state, "ready_manual")

        self._request(stamp_ns=str(REQUEST_NS + 1))
        self.assertFalse(state.note_map_tf_publication(ODOM_NS))
        state.observe_tf(tf_batch(ODOM_NS))
        self.assertFalse(state.tf_readback)
        self.assertTrue(state.note_map_tf_publication(ODOM_NS + 1))
        state.observe_tf(tf_batch(ODOM_NS + 1))
        self.assertTrue(state.tf_readback)

    def test_replays_foreign_context_old_stamp_and_unobserved_stop(self):
        state = self.runtime._manual
        for override in ({"map_revision": "d" * 64}, {"job_id": "e" * 32},
                         {"runtime_instance_generation": "retired"}, {"source_epoch": 1},
                         {"stamp_ns": "0"}, {"stamp_ns": "1"}):
            self._request(**override)
            self.assertIsNone(state.receipt)
        self._request()
        self.assertFalse(state.receipt["accepted"])
        self.assertEqual(state.receipt["reason"], "MANUAL_RESEED_REQUIRES_OBSERVED_STOP")
        self._stopped()
        self._request()
        self.assertFalse(state.receipt["accepted"])
        self.assertIsNone(self.runtime._map_to_odom)
        self._request(stamp_ns=str(REQUEST_NS + 1))
        self.assertTrue(state.receipt["accepted"])

    def test_source_epoch_change_revokes_a_seed_and_requires_new_stop(self):
        self._stopped()
        self._request()
        state = self.runtime._manual
        old = state.source_epoch
        self.assertTrue(state.observe_sources((b"replacement endpoint",)))
        self.assertGreater(state.source_epoch, old)
        self.assertEqual(state.state, "reseed_required")
        self.assertEqual(state.stopped_seconds(12.2), 0.)
        self.assertFalse(state.tf_readback)
        self.assertGreater(state.seed_generation, state.receipt["seed_generation"])

    def test_control_fence_expiry_never_restores_anchor_on_late_heartbeat(self):
        self._stopped()
        self._request()
        state = self.runtime._manual
        generation = state.seed_generation
        state.keepalive(generation, 13.5)
        self.assertTrue(state.control_fresh(14.5))
        state.keepalive(generation, 15.5)
        self.assertFalse(state.control_fresh(15.5))
        self.assertEqual(state.state, "reseed_required")
        self.assertGreater(state.seed_generation, generation)
        state.keepalive(generation, 15.6)
        self.assertFalse(state.control_fresh(15.6))

    def test_explicit_operational_mode_rejects_a_missing_bundle(self):
        options = NS(scan_bins=100, range_min=.15, range_max=30., z_min=-.2, z_max=.8,
                     mode=OPERATIONAL_MODE, runtime_params_file=None)
        with self.assertRaisesRegex(NavigationRuntimeError, "OPERATIONAL_NAVIGATION_BUNDLE_REQUIRED"):
            self.runtime_type(options)

    def test_manual_input_gate_checks_readback_scan_and_both_odometry_feeds(self):
        runtime = self.runtime
        del runtime._manual_input_reason
        self._stopped()
        runtime._transform_authority = NS(ready=True, reason="")
        runtime._options.cloud_timeout = .75
        runtime._last_cloud_monotonic = 12.2
        runtime._last_odom_monotonic = 12.2
        runtime._manual_static_tf_seen = True
        runtime._manual_odom_tf_stamp_ns = ODOM_NS
        with mock.patch("robot_dashboard.navigation_runtime.time.monotonic", return_value=12.2):
            self.assertEqual(runtime._manual_input_reason(12.2), "")
            runtime._manual_odom_tf_stamp_ns = 1
            self.assertEqual(runtime._manual_input_reason(12.2), "MANUAL_TF_READBACK_UNAVAILABLE")
            runtime._manual_odom_tf_stamp_ns = ODOM_NS
            runtime._last_cloud_monotonic = 11.
            self.assertEqual(runtime._manual_input_reason(12.2), "MANUAL_SCAN_STALE")
            runtime._last_cloud_monotonic = 12.2
            runtime._last_odom_monotonic = 11.
            self.assertEqual(runtime._manual_input_reason(12.2), "MANUAL_ODOMETRY_STALE")
            runtime._last_odom_monotonic = 12.2
            runtime._manual.controller_stop.clear()
            self.assertEqual(runtime._manual_input_reason(12.2), "MANUAL_CONTROLLER_ODOMETRY_STALE")

    def test_job_snapshot_requires_expected_directory_and_no_3d_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            job_dir = Path(directory) / PINS["job_id"]
            job_dir.mkdir()
            params = job_dir / "nav2_params.yaml"
            manifest = job_dir / "manual-navigation.json"
            with self.assertRaisesRegex(ValueError, "SNAPSHOT_REQUIRED"):
                load_manual_binding(params)
            manifest.write_text(json.dumps(PINS))
            self.assertEqual(load_manual_binding(params), PINS)
            (job_dir / "operational-3d.json").touch()
            with self.assertRaisesRegex(ValueError, "CONTAINS_3D_REFERENCE"):
                load_manual_binding(params)


class ManualGatewayTests(unittest.TestCase):
    def setUp(self):
        self.port = StubControlPort()
        self.node = CountNode()
        self.node.get_publishers_info_by_topic = lambda _: [
            NS(endpoint_gid=b"a" * 24, node_name="robot_scope_agent", node_namespace="/")
        ]
        self.node.get_clock = lambda: NS(now=lambda: NS(nanoseconds=REQUEST_NS))
        self.gateway = gateway(port=self.port, node=self.node)
        self.port.manager.acquire_navigation_lease()
        self.gateway.state.update(active=True, map={"id": PINS["map_id"], "revision": PINS["map_revision"]},
                                  goal={"state": "idle"})
        self.gateway._manual_session = (PINS, INSTANCE)
        self.gateway._navigation_string_type = NS
        self.gateway._manual_seed_publisher = mock.Mock()
        self.gateway._manual_seed_publisher.publish.side_effect = self._runtime_apply
        self.manual = ManualSeed(PINS, .5)
        for index in range(12):
            now = 10. + index * .2
            stamp = 1_000_000_000 + index * 200_000_000
            self.manual.odom_stop.observe(stamp, now, 0., 0.)
            self.manual.controller_stop.observe(stamp, now, 0., 0.)
        self._health(ready=False)

    def _health(self, *, ready):
        now = time.monotonic()
        self.gateway._navigation_runtime_health_received = now
        self.gateway._navigation_runtime_health = {
            "runtime_instance_generation": INSTANCE, "cloud_fresh": True, "odom_fresh": True,
            "manual_seed": self.manual.snapshot(12.2, True, ""), "ready": ready, "localized": ready,
        }
        for topic in self.gateway.validated_receipts:
            self.gateway.validated_receipts[topic] = now

    def _runtime_apply(self, message):
        data = json.loads(message.data)
        self.assertEqual({key: data[key] for key in PINS}, PINS)
        self.assertEqual(data["runtime_instance_generation"], INSTANCE)
        if data["operation"] == "invalidate":
            self.manual.invalidate("MANUAL_CONTROL_INVALIDATED")
            self._health(ready=False)
            return
        self.assertEqual(data["source_epoch"], self.manual.source_epoch)
        self.manual.acknowledge(REQUEST_NS, "MANUAL_ANCHOR_APPLIED", now=12.2, odom_stamp=ODOM_NS,
                                accepted_ros_ns=10_000_000_000)
        self.manual.note_map_tf_publication(ODOM_NS)
        self.manual.observe_tf(tf_batch(ODOM_NS))
        self._health(ready=True)

    def _seed(self, *, job_id=PINS["job_id"], seed_generation=None, source_epoch=None):
        return self.gateway.set_initial_pose(
            map_id=PINS["map_id"], map_revision=PINS["map_revision"], job_id=job_id,
            seed_generation=self.manual.seed_generation if seed_generation is None else seed_generation,
            source_epoch=self.manual.source_epoch if source_epoch is None else source_epoch,
            x=1., y=2., yaw=.25)

    def test_accepted_receipt_gates_goal_and_lease_release_invalidates_anchor(self):
        with self.assertRaises(ControlDisabled):
            self._seed(job_id="e" * 32)
        self.gateway._manual_seed_publisher.publish.assert_not_called()
        result = self._seed()
        self.assertTrue(result["manual_seed"]["tf_readback"])
        self.assertEqual(result["manual_seed"]["state"], "ready_manual")
        self.assertEqual(result["session_mode"], MODE)
        with self.assertRaisesRegex(ControlDisabled, "GENERATION_OR_SOURCE_CHANGED"):
            self._seed(seed_generation=0)
        with self.assertRaisesRegex(ControlDisabled, "GENERATION_OR_SOURCE_CHANGED"):
            self._seed(source_epoch=2)
        self.gateway._manual_seed_publisher.publish.assert_called_once()
        self._health(ready=True)  # Fresh pose after receipt.
        self.assertIsNone(self.gateway._navigation_sensor_interlock_reason(
            time.monotonic(), require_localized=True))
        self.gateway._require_goal_seed_locked(self.manual.seed_generation)
        with self.assertRaisesRegex(ControlDisabled, "GOAL_SEED_CHANGED"):
            self.gateway._require_goal_seed_locked(self.manual.seed_generation + 1)
        stopped = self.gateway.deactivate("operator_stop")
        self.assertFalse(stopped["active"])
        self.assertEqual(self.manual.state, "reseed_required")
        self.assertFalse(stopped["manual_seed"]["tf_readback"])

    def test_delayed_compatibility_pose_before_tf_readback_cannot_open_goal_gate(self):
        self._seed()
        def pose(stamp):
            sec, nanosec = divmod(stamp, 1_000_000_000)
            return NS(header=NS(frame_id="map", stamp=NS(sec=sec, nanosec=nanosec)),
                      pose=NS(pose=NS(position=NS(x=1., y=2.), orientation=NS(x=0., y=0., z=0., w=1.))))
        self.gateway._navigation_localization_callback(pose(ODOM_NS - 1))
        self.assertEqual(self.gateway.validated_receipts["/amcl_pose"], 0.)
        self.gateway._navigation_localization_callback(pose(ODOM_NS))
        self.assertGreater(self.gateway.validated_receipts["/amcl_pose"], 0.)
        self.assertEqual(self.gateway.state["localization"]["state"], "manual_seeded")

    def test_goal_dispatch_is_fenced_by_seed_and_fault_cancels_after_stop(self):
        self._seed()
        self._health(ready=True)
        self.gateway.state["localization"] = {"state": "manual_seeded", "pose": {"x": 1, "y": 2, "yaw": .25}}
        self.gateway._navigation_action_type = NS(Goal=lambda: NS(pose=NS()))
        self.gateway._navigation_action_client = mock.Mock()
        self.gateway._new_stamped_pose = lambda *args: NS(header=NS(), pose=NS(pose=NS()))
        self.gateway._navigation_token = "test-navigation-token"
        self.gateway._navigation_binding = "test-navigation-binding"
        self.gateway._navigation_goal_handle = None
        goal = dict(map_id=PINS["map_id"], map_revision=PINS["map_revision"], x=3., y=3., yaw=0.)
        with self.assertRaisesRegex(ControlDisabled, "GOAL_SEED_CHANGED"):
            self.gateway.send_goal(**goal, seed_generation=self.manual.seed_generation + 1)
        self.gateway._navigation_action_client.send_goal_async.assert_not_called()
        self.gateway.send_goal(**goal, seed_generation=self.manual.seed_generation)
        self.gateway._navigation_action_client.send_goal_async.assert_called_once()
        self.gateway._navigation_goal_handle = NS(cancel_goal_async=lambda: self.port.events.append("cancel"))

        self.manual.invalidate("MANUAL_ODOMETRY_STALE")
        self._health(ready=False)
        reason = self.gateway.reconcile_control_locked(time.monotonic())
        self.assertEqual(reason, "MANUAL_SEED_REQUIRED")
        stopped = self.gateway.deactivate(reason)
        self.assertEqual(stopped["goal"]["state"], "canceled")
        self.assertLess(self.port.events.index("release"), self.port.events.index("cancel"))

    def test_reseed_blocked_during_goal_and_estop(self):
        self.gateway.state["goal"]["state"] = "active"
        with self.assertRaises(LeaseBusy):
            self._seed()
        self.gateway.state["goal"]["state"] = "idle"
        self.port.manager._snapshot["estop"]["latched"] = True
        with self.assertRaises(EmergencyStopLatched):
            self._seed()
        self.gateway._manual_seed_publisher.publish.assert_not_called()

    def test_manual_preflight_refuses_foreign_tf_and_cold_odometry_owner(self):
        self.gateway.start_preflight = mock.Mock(return_value={"ready": True})
        self.gateway._navigation_action_client = NS(server_is_ready=lambda: False)
        self.node.count_publishers = lambda topic: int(topic == "/Odometry")
        self.assertEqual(self.gateway.manual_start_preflight(), {"ready": True})
        with self.assertRaisesRegex(LeaseBusy, "/Odometry"):
            self.gateway.manual_start_preflight(cold_odometry=True)
        self.node.count_publishers = lambda topic: int(topic == "/tf")
        with self.assertRaisesRegex(LeaseBusy, "/tf"):
            self.gateway.manual_start_preflight()

    def test_receipt_without_tf_readback_cannot_confirm_seed(self):
        self.manual.acknowledge(REQUEST_NS, "MANUAL_ANCHOR_APPLIED", now=12.2, odom_stamp=ODOM_NS,
                                accepted_ros_ns=10_000_000_000)
        self._health(ready=True)
        current = time.monotonic()
        health = self.gateway._navigation_runtime_health_snapshot(current)
        def sleep(seconds):
            nonlocal current
            current += seconds
        with self.assertRaisesRegex(ControlDisabled, "UNCONFIRMED"):
            wait_manual_seed_receipt(lambda _: health, context(health), REQUEST_NS,
                                     clock=lambda: current, sleep=sleep)
