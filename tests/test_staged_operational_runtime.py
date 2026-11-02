"""Synthetic staged-navigation regressions; never field accuracy evidence."""
from __future__ import annotations

import copy
import json
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock

import numpy as np

from robot_dashboard.control import CommandValidationError, ControlDisabled
from robot_dashboard.relocalization.experimental_se3 import from_translation_rpy
from robot_dashboard.relocalization.operational import (
    MATCH_TOPIC, STAGED_WORKFLOW, OperationalLocalizer, sanitize_status, validate_bundle,
)
from robot_dashboard.ros.initial_pose_receipt import wait_match_receipt
import test_operational_3d_localization as localizer_fixture
import test_operational_runtime_binding as runtime_fixture

fixture_bundle = localizer_fixture.fixture_bundle


def staged(bundle, *, geometry=True):
    result = copy.deepcopy(bundle)
    result.update(workflow=STAGED_WORKFLOW, seed_T_map_imu=None)
    if geometry:
        result['seed_geometry'] = {'z': 0., 'roll': 0., 'pitch': 0., 'frame': 'map',
                                   'source': 'operator', 'confirmed_at': 1_800_000_000.}
    return result


class StagedGeometryTests(unittest.TestCase):
    setUp = localizer_fixture.Operational3DLocalizationTests.setUp
    observe = localizer_fixture.Operational3DLocalizationTests.observe
    finish = localizer_fixture.Operational3DLocalizationTests.finish

    def engine(self, bundle=None):
        engine = OperationalLocalizer(bundle or staged(fixture_bundle(self.sha256)), self.path, clock=self.clock)
        self.addCleanup(engine.close)
        engine.observe_odometry(self.stamp, np.eye(4), self.clock())
        for _ in range(23):
            self.observe(engine, np.eye(4))
        return engine

    def test_missing_geometry_cannot_be_defaulted_and_legacy_seed_remains_required(self):
        bundle = fixture_bundle(self.sha256)
        bundle['seed_T_map_imu'] = None
        with self.assertRaisesRegex(ValueError, 'INITIAL_SEED_REQUIRED'):
            validate_bundle(bundle)
        engine = self.engine(staged(bundle, geometry=False))
        with self.assertRaisesRegex(ValueError, 'INITIAL_HEIGHT_TILT_REQUIRED'):
            engine.reseed(np.eye(4), stamp_ns=self.stamp)
        self.assertIsNone(engine.seed)
        self.assertIsNone(engine.status()['accepted_initial_pose'])
        for missing in ('z', 'roll', 'pitch', 'confirmed_at'):
            invalid = staged(bundle)
            del invalid['seed_geometry'][missing]
            with self.assertRaises(ValueError):
                validate_bundle(invalid)

    def test_explicit_body_geometry_is_composed_through_nonidentity_calibration(self):
        nav_map = from_translation_rpy([2., -1., .4], [.1, -.2, .3])
        imu_base = from_translation_rpy([.3, -.15, -.2], [.02, -.04, .12])
        bundle = staged(fixture_bundle(self.sha256, nav_map=nav_map, imu_base=imu_base))
        bundle['seed_geometry'].update(z=.7, roll=.12, pitch=-.18)
        engine = self.engine(bundle)
        request = from_translation_rpy([1.2, -2.3, 0.], [0., 0., .6])
        engine.reseed(request, stamp_ns=self.stamp)
        expected = from_translation_rpy([1.2, -2.3, .7], [.12, -.18, .6])
        np.testing.assert_allclose(nav_map @ engine.seed @ imu_base, expected, atol=1e-12)
        marker = engine.status()['accepted_initial_pose']
        self.assertAlmostEqual(marker['pose']['z'], .7)
        self.assertAlmostEqual(marker['pose']['pitch'], -.18)
        self.assertEqual(marker['map_id'], bundle['navigation_2d']['map_id'])
        self.assertFalse(engine.match_armed)
        self.assertIsNone(engine.status()['estimated_pose'])

    def test_initial_marker_waits_for_explicit_match_then_stale_pose_freezes(self):
        engine = self.engine()
        engine.reseed(np.eye(4), stamp_ns=self.stamp)
        initial_stamp = str(self.stamp)
        marker = copy.deepcopy(engine.status()['accepted_initial_pose'])
        self.assertFalse(engine.submit(self.points, self.stamp, np.eye(4), self.clock()))
        with self.assertRaisesRegex(ValueError, 'CURRENT_INITIAL_POSE_REQUIRED'):
            engine.start_matching('1')
        engine.start_matching(initial_stamp)
        for index in range(3):
            if index:
                for _ in range(6):
                    self.observe(engine, np.eye(4))
            self.assertTrue(engine.submit(self.points, self.stamp, np.eye(4), self.clock()))
            self.finish(engine)
        status = engine.status()
        self.assertTrue(status['ready'])
        self.assertFalse(status['estimated_pose']['stale'])
        self.assertEqual(status['accepted_initial_pose'], marker)
        original_pose = status['estimated_pose']['pose']
        original_stamp = status['estimated_pose']['stamp_ns']
        self.clock.advance(1.1)
        status = engine.status()
        self.assertFalse(status['ready'])
        self.assertTrue(status['estimated_pose']['stale'])
        self.assertEqual(status['estimated_pose']['pose'], original_pose)
        self.assertEqual(status['estimated_pose']['stamp_ns'], original_stamp)
        self.assertIsNone(engine.nav_odom())
        self.assertIsNotNone(sanitize_status(status))
        poisoned = copy.deepcopy(status)
        poisoned['estimated_pose']['map_revision'] = 'f' * 64
        self.assertIsNone(sanitize_status(poisoned))
        poisoned = copy.deepcopy(status)
        poisoned['estimated_pose']['runtime_instance_generation'] = 'previous-process'
        self.assertIsNone(sanitize_status(poisoned))
        engine.invalidate('SOURCE_CHANGED')
        self.assertIsNone(engine.status()['accepted_initial_pose'])
        self.assertIsNone(engine.status()['estimated_pose'])

    def test_new_initial_pose_disarms_previous_match(self):
        engine = self.engine()
        engine.reseed(np.eye(4), stamp_ns=self.stamp)
        engine.start_matching(str(self.stamp))
        self.observe(engine, np.eye(4))
        engine.reseed(np.eye(4), stamp_ns=self.stamp)
        self.assertFalse(engine.match_armed)
        self.assertEqual(engine.reason, 'WAITING_EXPLICIT_MAP_MATCH')


class StagedRuntimeCommandTests(unittest.TestCase):
    setUp = runtime_fixture.OperationalRuntimeBindingTests.setUp
    tick = runtime_fixture.OperationalRuntimeBindingTests.tick
    observe_stop = runtime_fixture.OperationalRuntimeBindingTests.observe_stop
    confirm_initial = runtime_fixture.OperationalRuntimeBindingTests.confirm_initial
    registered = runtime_fixture.OperationalRuntimeBindingTests.registered

    def prepare(self):
        self.engine.bundle = staged(self.engine.bundle)
        self.engine.match_armed = False
        self.node.publisher_counts[MATCH_TOPIC] = 1
        self.observe_stop()
        self.confirm_initial()
        self.assertEqual(self.engine.reason, 'WAITING_EXPLICIT_MAP_MATCH')

    def command(self, **override):
        body = {**self.engine.pose_context(), 'request_id': 'synthetic-match',
                'stamp_ns': str(self.node.now_ns),
                'runtime_instance_generation': self.node._runtime_instance_generation,
                'reference_sha256': self.sha,
                'initial_pose_stamp_ns': self.engine.accepted_initial_pose['stamp_ns'], **override}
        self.node._on_operational_match(NS(data=json.dumps(body)))
        return self.engine.match_receipt

    def test_matching_stage_requires_real_generation_bound_command(self):
        self.prepare()
        self.node._on_registered(self.registered())
        self.assertIsNone(self.engine.future)
        for key in ('map_revision', 'bundle_generation', 'runtime_instance_generation', 'initial_pose_stamp_ns'):
            receipt = self.command(**{key: 'wrong'})
            self.assertFalse(receipt['accepted'], key)
            self.assertFalse(self.engine.match_armed)
        self.assertTrue(self.command()['accepted'])
        self.node._on_registered(self.registered())
        self.assertIsNotNone(self.engine.future)

    def test_stale_duplicate_publisher_and_moving_commands_cannot_arm(self):
        self.prepare()
        self.assertEqual(self.command(stamp_ns=str(self.node.now_ns - 600_000_000))['reason'],
                         'MAP_MATCH_COMMAND_STALE')
        self.node.publisher_counts[MATCH_TOPIC] = 2
        self.assertEqual(self.command()['reason'], 'MAP_MATCH_PUBLISHER_NOT_UNIQUE')
        self.node.publisher_counts[MATCH_TOPIC] = 1
        self.engine.stopped_since = None
        self.assertEqual(self.command()['reason'], 'RESEED_REQUIRES_OBSERVED_STOP')
        self.assertFalse(self.engine.match_armed)


class MatchReceiptTests(unittest.TestCase):
    def test_ack_is_bound_to_request_and_runtime_generation(self):
        now = [10.]
        source = {'bundle_generation': 'bundle', 'localization_generation': 2,
                  'match_receipt': {'accepted': True, 'request_id': 'request',
                                    'localization_generation': 2, 'reason': 'WAITING_MAP_CORRECTION'}}
        health = {'fresh': True, 'runtime_instance_generation': 'runtime', 'operational_3d': source}
        def wait():
            return wait_match_receipt(lambda _: health, ('runtime', 'bundle'), 'request', 2,
                clock=lambda: now[0], sleep=lambda delta: now.__setitem__(0, now[0] + delta))
        self.assertTrue(wait()['accepted'])
        source['match_receipt']['request_id'] = 'previous'
        with self.assertRaisesRegex(ControlDisabled, 'UNCONFIRMED'):
            wait()
        source['localization_generation'] = 3
        with self.assertRaisesRegex(ControlDisabled, 'SOURCE_CHANGED'):
            wait()

    def test_gateway_publishes_only_match_and_waits_for_runtime_ack(self):
        from test_navigation_ros import NavigationControlTests
        gateway = NavigationControlTests.gateway()
        gateway._navigation.update(active=True, map={'id': 'map', 'revision': 'rev'}, goal={'state': 'idle'})
        gateway._navigation_sensor_interlock_reason = lambda *a, **kw: None
        source = {'workflow': STAGED_WORKFLOW, 'bundle_generation': 'bundle', 'localization_generation': 2,
            'map_id': 'map', 'map_revision': 'rev', 'localization_map_id': 'pcd',
            'localization_map_revision': 'pcdrev', 'reference_sha256': 'sha', 'stopped_seconds': 3.,
            'accepted_initial_pose': {'accepted': True, 'stamp_ns': '123'}}
        health = {'fresh': True, 'runtime_instance_generation': 'runtime', 'operational_3d': source}
        gateway._navigation_runtime_health_snapshot = lambda _: health
        gateway._node_getter = lambda: NS(get_clock=lambda: NS(now=lambda: NS(to_msg=lambda: NS(sec=1, nanosec=0))))
        gateway._navigation_string_type = NS
        gateway._navigation_match_publisher = Mock()
        def publish(message):
            command = json.loads(message.data)
            self.assertEqual(command['initial_pose_stamp_ns'], '123')
            source['match_receipt'] = {'accepted': True, 'request_id': command['request_id'],
                                      'localization_generation': 2, 'reason': 'WAITING_MAP_CORRECTION'}
        gateway._navigation_match_publisher.publish.side_effect = publish
        args = dict(map_id='map', map_revision='rev', bundle_generation='bundle',
                    localization_generation=2, initial_pose_stamp_ns='123')
        self.assertTrue(gateway.start_operational_match(**args)['accepted'])
        gateway._navigation_match_publisher.publish.assert_called_once()
        args['map_revision'] = 'changed'
        with self.assertRaises(CommandValidationError):
            gateway.start_operational_match(**args)
        gateway._navigation_match_publisher.publish.assert_called_once()


if __name__ == '__main__':
    unittest.main()
