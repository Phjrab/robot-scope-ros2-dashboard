"""Native callback compatibility without ROS connections or identity synthesis."""

import inspect
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from robot_dashboard.relocalization.observation_alignment import ObservationAlignmentError, project_query
from robot_dashboard.ros.observation_identity import ObservationIdentity, wrap_observation_callback
from robot_dashboard.ros.pointcloud import PointCloudHub
from robot_dashboard.ros.telemetry import TelemetryHub


MODULE_IMPORT = 'robot_dashboard.ros.observation_identity.import_module'


def observe(info, *, count=1, identity=None, stamp=1, received=10.0):
    return (identity or ObservationIdentity()).observe(
        topic='/odom', frame='odom', child='base_link', stamp_ns=stamp,
        received=received, message_info=info, publisher_count=count,
    )


class CallbackCompatibilityTests(unittest.TestCase):
    def test_humble_and_missing_rclpy_accept_message_only_and_fence_late_callbacks(self):
        for module in (None, SimpleNamespace(Subscription=type('Subscription', (), {}))):
            with self.subTest(module=module):
                active, calls = [True], []
                options = dict(side_effect=ImportError('no ROS')) if module is None else dict(return_value=module)
                with patch(MODULE_IMPORT, **options):
                    callback = wrap_observation_callback(
                        lambda *args, **kwargs: calls.append((args, kwargs)),
                        '/odom', 'nav_msgs/msg/Odometry', lambda: active[0],
                    )
                callback('message')  # Humble Executor._execute_subscription dispatches one argument.
                self.assertEqual(calls, [(('/odom', 'nav_msgs/msg/Odometry', 'message'), {'message_info': None})])
                active[0] = False
                callback('late')
                callback('late with info', object())
                self.assertEqual(len(calls), 1)

    def test_native_capability_preserves_metadata_under_one_bind_first_detection(self):
        for class_name in ('Subscription', 'BaseSubscription'):
            with self.subTest(class_name=class_name):
                # Presence matters; a zero-valued native enum member must still be supported.
                callback_type = SimpleNamespace(WithMessageInfo=0)
                module = SimpleNamespace(**{class_name: SimpleNamespace(CallbackType=callback_type)})
                active, calls = [True], []
                with patch(MODULE_IMPORT, return_value=module):
                    callback = wrap_observation_callback(
                        lambda *args, **kwargs: calls.append((args, kwargs)),
                        '/cloud_registered', 'sensor_msgs/msg/PointCloud2', lambda: active[0],
                    )
                info = {'publisher_gid': {'implementation_identifier': 'rmw_test_cpp', 'data': bytes([3]) * 24}}
                # Jazzy/Rolling select message-only first if binding one argument succeeds.
                try:
                    inspect.signature(callback).bind('message')
                except TypeError:
                    inspect.signature(callback).bind('message', info)
                    callback('message', info)
                else:
                    callback('message')
                self.assertIs(calls[0][1]['message_info'], info)
                active[0] = False
                callback('late', info)
                self.assertEqual(len(calls), 1)

    def test_callback_failure_is_not_swallowed_or_retried(self):
        calls = []
        def broken(*args, **kwargs):
            calls.append((args, kwargs))
            raise TypeError('inside callback')
        with patch(MODULE_IMPORT, side_effect=ImportError('no ROS')):
            callback = wrap_observation_callback(broken, '/odom', 'nav_msgs/msg/Odometry', lambda: True)
        with self.assertRaisesRegex(TypeError, 'inside callback'):
            callback('message')
        self.assertEqual(len(calls), 1)

    def test_humble_pose_and_cloud_keep_updating_but_numerical_alignment_rejects_identity(self):
        lock = threading.RLock()
        pose_hub = TelemetryHub(lock, joint_stale_after_s=1, pose_stale_after_s=1, pose_position_limit_m=1000)
        cloud_hub = PointCloudHub(lock, max_points=1000, radius_limit_m=10, frame_interval_s=.1)
        now, stamp = [10.0], [1]
        message = SimpleNamespace(header=SimpleNamespace(frame_id='odom'), child_frame_id='base_link')
        parsed_pose = dict(frame_id='odom', child_frame_id='base_link', position=dict(x=0, y=0, z=0),
                           orientation=dict(x=0, y=0, z=0, w=1))
        points = np.random.default_rng(4).uniform(-1, 1, (80, 3)).astype(np.float32)
        def on_pose(topic, type_name, value, *, message_info):
            pose_hub.update_pose(topic, type_name, value, now[0], selected_topic=lambda: '/odom',
                                 stamp_ns=lambda _: stamp[0], message_info=message_info, publisher_count=1)
        def on_cloud(topic, type_name, value, *, message_info):
            cloud_hub.process(topic, value, now[0], selected_topic=lambda: '/cloud_registered',
                              stamp_ns=lambda _: stamp[0], robot_pose_in_frame=lambda _: None,
                              message_info=message_info, publisher_count=1)
        with patch(MODULE_IMPORT, return_value=SimpleNamespace(Subscription=object)), \
                patch('robot_dashboard.ros.telemetry.extract_odometry_pose', return_value=parsed_pose), \
                patch('robot_dashboard.ros.pointcloud.extract_xyz', return_value=(points, len(points))):
            pose_callback = wrap_observation_callback(on_pose, '/odom', 'nav_msgs/msg/Odometry', lambda: True)
            cloud_callback = wrap_observation_callback(on_cloud, '/cloud_registered', 'sensor_msgs/msg/PointCloud2', lambda: True)
            for _ in range(2):
                pose_callback(message)
                cloud_callback(message)
                now[0] += .2
                stamp[0] += 1
        pose = pose_hub.pose_snapshot_locked(now[0])
        cloud = cloud_hub.binary_snapshot()
        self.assertEqual(pose['state'], 'ok')
        self.assertEqual(pose['stamp_ns'], 2)
        self.assertGreaterEqual(pose['seq'], 2)
        self.assertEqual(cloud['seq'], 2)
        self.assertEqual(cloud['sent_points'], 80)
        for sample in (pose, cloud):
            self.assertEqual(sample['observation']['identity_status'], 'UNAVAILABLE')
            self.assertIsNone(sample['observation']['publisher_gid'])
        with self.assertRaisesRegex(ObservationAlignmentError, 'SOURCE_IDENTITY_UNAVAILABLE'):
            project_query(cloud, pose, now[0])


class NativeMetadataIdentityTests(unittest.TestCase):
    def test_native_attribute_and_mapping_shapes_preserve_supplied_gid(self):
        for data in (bytes([1]) * 16, bytearray([1]) * 16, memoryview(bytes([1]) * 16), [1] * 16, (1,) * 16):
            for info in (SimpleNamespace(publisher_gid=data), {'publisher_gid': data}):
                with self.subTest(data=type(data), info=type(info)):
                    result = observe(info)
                    self.assertEqual(result['identity_status'], 'OBSERVED_PUBLISHER')
                    self.assertEqual(result['publisher_gid'], '01' * 16)
        gid = {'implementation_identifier': 'rmw_custom_cpp', 'data': bytes([2]) * 24}
        for info in ({'publisher_gid': gid}, SimpleNamespace(publisher_gid=SimpleNamespace(**gid))):
            with self.subTest(info=info):
                result = observe(info)
                self.assertEqual(result['identity_status'], 'OBSERVED_PUBLISHER')
                self.assertEqual(result['publisher_gid'], '02' * 24)
                self.assertEqual(result['publisher_implementation_identifier'], 'rmw_custom_cpp')

    def test_missing_and_malformed_metadata_never_invent_publisher_identity(self):
        malformed_gids = [
            None, True, 16, '01' * 16, bytes(16), b'\x01' * 15, b'\x01' * 17,
            b'\x01' * 23, b'\x01' * 25, [True] * 16, [1.0] * 16, [-1] * 16, [256] * 16,
            {'data': b'\x01' * 24}, {'implementation_identifier': 'rmw_test_cpp'},
            {'implementation_identifier': '', 'data': b'\x01' * 24},
            {'implementation_identifier': 1, 'data': b'\x01' * 24},
            {'implementation_identifier': 'bad\nidentifier', 'data': b'\x01' * 24},
            SimpleNamespace(data=b'\x01' * 24),
        ]
        infos = [None, {}, {'source_timestamp': 123, 'received_timestamp': 0}]
        infos.extend({'publisher_gid': gid} for gid in malformed_gids)
        for info in infos:
            with self.subTest(info=info):
                result = observe(info)
                self.assertEqual(result['identity_status'], 'UNAVAILABLE')
                self.assertIsNone(result['publisher_gid'])

    def test_publisher_count_and_stamp_are_exact_native_integers(self):
        info = SimpleNamespace(publisher_gid=bytes([1]) * 16)
        for count in (None, 0, 2, True, False, 1.0, '1'):
            with self.subTest(count=count):
                self.assertEqual(observe(info, count=count)['identity_status'], 'UNAVAILABLE')
        for stamp in (True, False, 0, -1, 1.0):
            with self.subTest(stamp=stamp):
                self.assertEqual(observe(info, stamp=stamp)['identity_status'], 'UNAVAILABLE')

    def test_implementation_change_and_metadata_loss_rotate_epoch(self):
        identity = ObservationIdentity()
        info = {'publisher_gid': {'implementation_identifier': 'rmw_first_cpp', 'data': bytes([1]) * 24}}
        first = observe(info, identity=identity)
        changed_info = {'publisher_gid': dict(info['publisher_gid'], implementation_identifier='rmw_second_cpp')}
        second = observe(changed_info, identity=identity, stamp=2, received=10.1)
        self.assertNotEqual(first['publisher_epoch'], second['publisher_epoch'])
        self.assertEqual(second['reset_reason'], 'SOURCE_CHANGED')
        missing = observe({'source_timestamp': 3, 'received_timestamp': 0}, identity=identity, stamp=3, received=10.2)
        self.assertNotEqual(second['publisher_epoch'], missing['publisher_epoch'])
        self.assertEqual(missing['identity_status'], 'UNAVAILABLE')
        restored = observe(changed_info, identity=identity, stamp=4, received=10.3)
        self.assertNotEqual(missing['publisher_epoch'], restored['publisher_epoch'])
        self.assertEqual(restored['identity_status'], 'OBSERVED_PUBLISHER')


if __name__ == '__main__':
    unittest.main()
