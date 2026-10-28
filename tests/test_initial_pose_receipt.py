import copy
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock

from robot_dashboard.control import ControlDisabled
from robot_dashboard.ros.initial_pose_receipt import operational_initial_pose_context, wait_initial_pose_receipt


class InitialPoseReceiptTests(unittest.TestCase):
    def setUp(self):
        self.now = 10.
        self.health = {'fresh': True, 'runtime_instance_generation': 'runtime-a',
            'operational_3d': {'bundle_generation': 'bundle-a', 'stopped_seconds': 3.,
                'localization_generation': 2, 'initial_pose_receipt': {
                    'stamp_ns': '123', 'accepted': True, 'reason': 'WAITING_MAP_CORRECTION',
                    'localization_generation': 2}}}
        self.context = operational_initial_pose_context(self.health)

    def wait(self, health):
        def sleep(seconds): self.now += seconds
        return wait_initial_pose_receipt(lambda _: health, self.context, 123,
            clock=lambda: self.now, sleep=sleep)

    def test_legacy_path_does_not_require_new_runtime_receipt(self):
        self.assertIsNone(operational_initial_pose_context({}))

    def test_fresh_measured_stop_required_before_publish(self):
        for stopped in (0., 1.99, True, float('nan'), None):
            self.health['operational_3d']['stopped_seconds'] = stopped
            with self.assertRaisesRegex(ControlDisabled, 'OBSERVED_STOP'):
                operational_initial_pose_context(self.health)
        self.health['operational_3d']['stopped_seconds'] = 3.
        self.health['fresh'] = False
        with self.assertRaises(ControlDisabled): operational_initial_pose_context(self.health)

    def test_matching_runtime_application_is_accepted(self):
        self.wait(self.health)

    def test_runtime_rejection_is_not_a_successful_publish(self):
        self.health['operational_3d']['initial_pose_receipt'].update(
            accepted=False, reason='RESEED_REQUIRES_OBSERVED_STOP')
        with self.assertRaisesRegex(ControlDisabled, 'RESEED_REQUIRES_OBSERVED_STOP'):
            self.wait(self.health)

    def test_old_stale_or_missing_receipt_times_out(self):
        for case in ('stamp', 'stale', 'missing'):
            h = copy.deepcopy(self.health)
            if case == 'stamp': h['operational_3d']['initial_pose_receipt']['stamp_ns'] = '122'
            if case == 'stale': h['fresh'] = False
            if case == 'missing': h['operational_3d']['initial_pose_receipt'] = None
            with self.assertRaisesRegex(ControlDisabled, 'UNCONFIRMED'): self.wait(h)

    def test_source_replacement_or_invalidation_cannot_confirm_old_seed(self):
        for key in ('runtime_instance_generation', 'bundle_generation', 'localization_generation'):
            h = copy.deepcopy(self.health)
            target = h if key == 'runtime_instance_generation' else h['operational_3d']
            target[key] = 'changed'
            with self.assertRaises(ControlDisabled): self.wait(h)

    def test_actual_gateway_propagates_runtime_rejection_after_ros_publish(self):
        from test_navigation_ros import NavigationControlTests
        gateway = NavigationControlTests.gateway()
        gateway._navigation.update(active=True, map={'id': 'map', 'revision': 'rev'}, goal={'state': 'idle'})
        gateway._navigation_sensor_interlock_reason = lambda *a, **kw: None
        gateway._navigation_runtime_health_snapshot = lambda _: self.health
        gateway.runtime_snapshot = lambda: {}
        gateway._new_stamped_pose = lambda *a: NS(header=NS(stamp=NS(sec=0, nanosec=123)), pose=NS())
        def publish(_message):
            self.health['operational_3d']['initial_pose_receipt'].update(
                accepted=False, reason='RESEED_REQUIRES_OBSERVED_STOP')
        gateway._navigation_initial_pose_publisher = Mock()
        gateway._navigation_initial_pose_publisher.publish.side_effect = publish
        with self.assertRaisesRegex(ControlDisabled, 'RESEED_REQUIRES_OBSERVED_STOP'):
            gateway.set_initial_pose(map_id='map', map_revision='rev', x=0., y=0., yaw=0.)
        gateway._navigation_initial_pose_publisher.publish.assert_called_once()

    def test_actual_gateway_blocks_early_pose_before_ros_publish(self):
        from test_navigation_ros import NavigationControlTests
        gateway = NavigationControlTests.gateway()
        gateway._navigation.update(active=True, map={'id': 'map', 'revision': 'rev'}, goal={'state': 'idle'})
        gateway._navigation_sensor_interlock_reason = lambda *a, **kw: None
        self.health['operational_3d']['stopped_seconds'] = 1.
        gateway._navigation_runtime_health_snapshot = lambda _: self.health
        gateway._navigation_initial_pose_publisher = Mock()
        with self.assertRaisesRegex(ControlDisabled, 'RESEED_REQUIRES_OBSERVED_STOP'):
            gateway.set_initial_pose(map_id='map', map_revision='rev', x=0., y=0., yaw=0.)
        gateway._navigation_initial_pose_publisher.publish.assert_not_called()
