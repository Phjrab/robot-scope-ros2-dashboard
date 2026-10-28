"""Software-only ROS adapter checks, using production runtime callbacks.

ROS message, graph, and clock surfaces are a harness. The PCD reader, loaded
localizer, exact-stamp ring, registration, TF gating, and callbacks are real.
No result in this module is a hardware or field-navigation qualification.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

import numpy as np

from robot_dashboard import navigation_runtime as runtime
from robot_dashboard.relocalization.experimental_se3 import from_translation_rpy
from test_localization_startup_diagnostics import (
    FakeNode, PoseMessage, header, obj, odometry, ros_modules,
)
from test_operational_3d_localization import fixture_bundle, write_pcd


class OperationalHarnessNode(FakeNode):
    def __init__(self, name):
        super().__init__(name)
        self.publisher_counts['/cloud_registered'] = 1
        self.gids['/cloud_registered'] = b'\x03' * 16

    def get_name(self):
        return 'robot_scope_navigation_runtime'

    def get_namespace(self):
        return '/'

    def get_publishers_info_by_topic(self, topic):
        if topic in ('/tf', '/tf_static'):
            return [obj(node_name=self.get_name(), node_namespace='/',
                        endpoint_gid=(b'\x04' if topic == '/tf' else b'\x05') * 16)]
        return super().get_publishers_info_by_topic(topic)


def operational_ros_modules():
    modules = ros_modules()
    modules['rclpy.node'].Node = OperationalHarnessNode
    for package, attributes in {
        'tf2_msgs.msg': {'TFMessage': type('TFMessage', (), {})},
        'builtin_interfaces.msg': {'Time': lambda **kwargs: obj(**kwargs)},
    }.items():
        modules[package.split('.')[0]] = types.ModuleType(package.split('.')[0])
        modules[package] = types.ModuleType(package)
        modules[package].__dict__.update(attributes)
    return modules


class OperationalRuntimeBindingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.params = root / 'nav2_params.yaml'
        self.params.write_text('{}')
        self.points = np.random.default_rng(762).uniform([-2, -1, -.5], [3, 2, 2.5], (384, 3))
        self.sha = write_pcd(root / 'localization-reference.pcd', self.points)
        bundle = fixture_bundle(self.sha)
        bundle['calibration']['tf_publishers'] = {'/tf': [], '/tf_static': []}
        (root / 'operational-3d.json').write_text(json.dumps(bundle))
        self.monotonic = 1000.
        patches = [
            mock.patch.dict(sys.modules, operational_ros_modules()),
            mock.patch.object(runtime.time, 'monotonic', side_effect=lambda: self.monotonic),
            mock.patch.object(runtime.time, 'monotonic_ns', side_effect=lambda: int(self.monotonic * 1e9)),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        node_type = runtime._build_ros_runtime_node_class()
        options = obj(scan_bins=1441, range_min=.4, range_max=10., z_min=-.5, z_max=2.,
            cloud_frame='hesai_lidar', lidar_x=.25, lidar_y=0., lidar_z=0., lidar_yaw=0.,
            cloud_timeout=.75, odom_timeout=.5, controller_odom_mode='strict_onboard',
            controller_odom_topic=runtime.STRICT_CONTROLLER_ODOM_TOPIC, runtime_params_file=str(self.params))
        self.node = node_type(options)
        self.engine = self.node._operational
        self.engine.clock = lambda: self.monotonic
        self.node._transform_authority.clock = lambda: self.monotonic
        self.addCleanup(self.engine.close)
        self.node._on_health_timer()

    def tick(self, seconds=.1, *, observe=True):
        self.monotonic += seconds
        self.node.now_ns += round(seconds * 1e9)
        self.node._on_health_timer()
        if observe:
            self.node._on_odometry(odometry(self.node.now_ns))

    def registered(self, stamp=None):
        xyz = self.points.astype('<f4')
        return obj(header=header(self.node.now_ns if stamp is None else stamp, 'camera_init'),
            data=xyz.tobytes(), width=len(xyz), height=1, point_step=12,
            row_step=12 * len(xyz), is_bigendian=False,
            fields=[obj(name=name, offset=index * 4, datatype=7, count=1)
                    for index, name in enumerate(('x', 'y', 'z'))])

    def observe_stop(self):
        self.node._on_odometry(odometry(self.node.now_ns))
        for _ in range(23):
            self.tick()
        self.assertGreaterEqual(self.engine.stopped_seconds(), 2.)
        self.assertTrue(self.node._transform_authority.ready)

    def confirm_initial(self):
        initial = PoseMessage()
        initial.header = header(self.node.now_ns, 'map')
        self.node._on_initial_pose(initial)

    def complete_fit(self):
        self.assertIsNotNone(self.engine.future)
        self.engine.future.result(timeout=5.)
        self.node._poll_operational()

    def test_job_loads_real_reference_but_staged_seed_cannot_auto_initialize(self):
        self.assertEqual(self.engine.bundle['localization_3d']['sha256'], self.sha)
        self.assertEqual(self.engine.full_count, len(self.points))
        np.testing.assert_allclose(self.engine.reference, self.points, atol=2e-7)
        self.assertIsNone(self.engine.seed)
        self.assertEqual(self.engine.reason, 'WAITING_EXPLICIT_INITIAL_POSE')
        self.node._on_odometry(odometry(self.node.now_ns))
        self.node._on_registered(self.registered())
        self.assertIsNone(self.engine.future)
        self.observe_stop()
        self.node._on_registered(self.registered())
        self.assertIsNone(self.engine.future, 'a stop alone must not activate the staged seed')
        self.confirm_initial()
        self.assertIsNotNone(self.engine.seed)
        self.node._on_registered(self.registered())
        self.complete_fit()
        self.assertTrue(self.engine.status()['ready'], self.engine.status())

    def test_early_initialpose_is_rejected_until_observed_stop(self):
        self.node._on_odometry(odometry(self.node.now_ns))
        self.confirm_initial()
        self.assertIsNone(self.engine.seed)
        for _ in range(11):
            self.tick()
        self.confirm_initial()
        self.assertIsNone(self.engine.seed)
        for _ in range(12):
            self.tick()
        self.confirm_initial()
        self.assertIsNotNone(self.engine.seed)

    def test_registered_cloud_waits_for_exact_source_stamp_not_nearest_receipt(self):
        self.observe_stop()
        self.confirm_initial()
        source_stamp = self.node.now_ns + 10_000_000
        self.node._on_registered(self.registered(source_stamp))
        self.assertIsNone(self.engine.future)
        self.assertIsNotNone(self.node._registered_pending)
        # Fresh nearby odometry is deliberately not the exact cloud stamp.
        self.tick(.005)
        self.node._poll_operational()
        self.assertIsNone(self.engine.future)
        self.tick(.005)
        self.node._poll_operational()
        self.complete_fit()
        self.assertEqual(self.engine.last_accepted_stamp, source_stamp)
        self.assertEqual(self.engine.sequence, 1)

    def test_unpaired_registered_cloud_expires_without_retiming_or_fit(self):
        self.observe_stop()
        self.confirm_initial()
        self.node._on_registered(self.registered(self.node.now_ns + 10_000_000))
        for _ in range(6):
            self.tick()
        self.node._poll_operational()
        self.assertIsNone(self.node._registered_pending)
        self.assertIsNone(self.engine.future)
        self.assertEqual(self.engine.sequence, 0)

    def test_protected_tf_is_suppressed_until_actual_authority_preflight(self):
        self.node._on_odometry(odometry(self.node.now_ns))
        self.assertFalse(self.node._transform_authority.ready)
        self.assertEqual(self.node._tf_broadcaster.messages, [])
        for _ in range(12):
            self.tick()
        self.assertTrue(self.node._transform_authority.ready)
        edges = [(msg.header.frame_id, msg.child_frame_id) for msg in self.node._tf_broadcaster.messages]
        self.assertIn(('odom', 'base_link'), edges)
        self.assertNotIn(('map', 'odom'), edges)
        self.assertEqual(self.node._pose_publisher.messages, [])

    def test_fit_is_consumed_by_existing_tf_and_pose_publishers_at_source_stamp(self):
        self.observe_stop()
        self.confirm_initial()
        self.node._on_registered(self.registered())
        self.complete_fit()
        self.tick()
        map_tf = [message for message in self.node._tf_broadcaster.messages
                  if (message.header.frame_id, message.child_frame_id) == ('map', 'odom')][-1]
        stamp = self.node.now_ns
        self.assertEqual(map_tf.header.stamp.sec * 1_000_000_000 + map_tf.header.stamp.nanosec, stamp)
        self.assertEqual(self.node._pose_publisher.messages[-1].header.frame_id, 'map')
        self.assertEqual(self.node._pose_publisher.messages[-1].header.stamp, map_tf.header.stamp)
        self.assertEqual(self.engine.status()['correction_stamp_ns'], str(stamp - 100_000_000))

    def test_registered_publisher_replacement_invalidates_existing_map_correction(self):
        self.observe_stop()
        self.confirm_initial()
        self.node._on_registered(self.registered())
        self.complete_fit()
        self.assertIsNotNone(self.engine.correction)
        self.node.gids['/cloud_registered'] = b'\x06' * 16
        self.node._on_registered(self.registered())
        self.assertIsNone(self.engine.correction)
        self.assertIsNone(self.engine.seed)
        self.assertEqual(self.engine.reason, 'REGISTERED_SOURCE_CHANGED')

    def test_existing_competition_odom_consumer_receives_same_body_pose_and_body_velocity(self):
        bundle_path = self.params.parent / 'operational-3d.json'
        bundle = json.loads(bundle_path.read_text())
        bundle['calibration']['T_imu_base'] = from_translation_rpy([.3, .1, -.2], [0, 0, .2]).tolist()
        bundle_path.write_text(json.dumps(bundle))
        options = obj(**{**vars(self.node._options), 'controller_odom_mode': 'competition_fastlio',
                         'controller_odom_topic': runtime.FASTLIO_CONTROLLER_ODOM_TOPIC})
        self.node = runtime._build_ros_runtime_node_class()(options)
        self.engine = self.node._operational
        self.engine.clock = lambda: self.monotonic
        self.node._transform_authority.clock = lambda: self.monotonic
        self.addCleanup(self.engine.close)
        self.node._on_health_timer()
        self.node._on_odometry(odometry(self.node.now_ns))
        for index in range(1, 14):
            self.tick(observe=False)
            message = odometry(self.node.now_ns, x=.02 * index)
            # Raw source twist is zero in this fixture; body speed must come
            # from consecutive source-stamped poses, not be copied as zero.
            self.node._on_odometry(message)
        canonical = self.node._controller_odom_publisher.messages[-1]
        odom_tf = [message for message in self.node._tf_broadcaster.messages
                   if (message.header.frame_id, message.child_frame_id) == ('odom', 'base_link')][-1]
        self.assertEqual(canonical.header.frame_id, 'odom')
        self.assertEqual(canonical.child_frame_id, 'base_link')
        self.assertEqual(canonical.header.stamp, odom_tf.header.stamp)
        self.assertAlmostEqual(canonical.pose.pose.position.x, odom_tf.transform.translation.x)
        self.assertAlmostEqual(canonical.pose.pose.position.y, odom_tf.transform.translation.y)
        self.assertAlmostEqual(canonical.pose.pose.position.z, odom_tf.transform.translation.z)
        self.assertAlmostEqual(canonical.twist.twist.linear.x, .2 * np.cos(.2), places=8)
        self.assertAlmostEqual(canonical.twist.twist.linear.y, -.2 * np.sin(.2), places=8)
        self.assertEqual(canonical.twist.twist.angular.z, 0.)


if __name__ == '__main__':
    unittest.main()
