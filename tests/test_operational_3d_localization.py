"""Robot-free software checks of stored-map math and asynchronous admission.

All PCD and odometry values in this file are synthetic fixtures. Passing these
checks is not evidence of Jetson calibration, localization accuracy, or motion.
"""
from __future__ import annotations

import copy
import hashlib
import math
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest import mock

import numpy as np

from robot_dashboard.relocalization.experimental_se3 import (
    from_translation_rpy,
    inverse,
    rotation_error_rad,
    transform_points,
)
from robot_dashboard.relocalization.operational import (
    OperationalLocalizer,
    SCHEMA,
    read_reference,
    sanitize_status,
)
from robot_dashboard.relocalization.observation_alignment import solve_prepared


class ManualClock:
    def __init__(self):
        self.value = time.monotonic()

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def write_pcd(path, points):
    """Synthetic little-endian records with attributes beyond XYZ."""
    dtype = np.dtype([('x', '<f4'), ('y', '<f4'), ('z', '<f4'), ('intensity', '<f4'), ('ring', '<u2')])
    records = np.zeros(len(points), dtype=dtype)
    for column, name in enumerate(('x', 'y', 'z')):
        records[name] = points[:, column]
    records['intensity'] = np.arange(len(points)) + .25
    records['ring'] = np.arange(len(points)) % 16
    header = ("VERSION 0.7\nFIELDS x y z intensity ring\nSIZE 4 4 4 4 2\n"
              "TYPE F F F F U\nCOUNT 1 1 1 1 1\n"
              f"WIDTH {len(points)}\nHEIGHT 1\nVIEWPOINT 0 0 0 1 0 0 0\nPOINTS {len(points)}\nDATA binary\n").encode('ascii')
    data = header + records.tobytes()
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def fixture_bundle(sha256, *, correction=None, odom=None, nav_map=None, imu_base=None):
    correction = np.eye(4) if correction is None else correction
    odom = np.eye(4) if odom is None else odom
    nav_map = np.eye(4) if nav_map is None else nav_map
    imu_base = np.eye(4) if imu_base is None else imu_base
    return {
        'schema': SCHEMA,
        'generation': 'a' * 32,
        'localization_3d': {'map_id': 'b' * 24, 'revision': 'c' * 64,
                            'sha256': sha256, 'frame': 'survey_map', 'units': 'm'},
        'navigation_2d': {'map_id': 'd' * 24, 'revision': 'e' * 64, 'frame': 'map'},
        'calibration': {'verified': True, 'evidence': 'SYNTHETIC_SOFTWARE_FIXTURE',
                        'localization_root': {'map_id': 'b' * 24, 'revision': 'c' * 64,
                            'sha256': sha256, 'frame_id': 'survey_map', 'units': 'm'},
                        'T_nav_map_from_localization_map': nav_map.tolist(),
                        'T_imu_base': imu_base.tolist()},
        'seed_T_map_imu': (correction @ odom).tolist(),
        'policy': {'max_rmse_m': .1, 'max_correction_age_s': 1.,
                   'max_translation_step_m': .3, 'max_rotation_step_rad': .2,
                   'compute_budget_s': 1., 'max_propagation_m': .5,
                   'evidence': 'SYNTHETIC_SOFTWARE_FIXTURE'},
    }


class Operational3DLocalizationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'reference.pcd'
        self.clock = ManualClock()
        self.stamp = 1_700_000_000_000_000_000
        rng = np.random.default_rng(3811)
        self.points = rng.uniform([-3, -2, -.8], [4, 3, 2.6], (384, 3))
        self.sha256 = write_pcd(self.path, self.points)

    def make_engine(self, **kwargs):
        bundle = fixture_bundle(self.sha256, **kwargs)
        engine = OperationalLocalizer(bundle, self.path, clock=self.clock)
        # Cold reference-index imports are setup time, before the fixture's
        # source receipt and real worker deadline are sampled.
        self.clock.value = time.monotonic()
        self.addCleanup(engine.close)
        return engine

    def finish(self, engine):
        future = engine.future
        self.assertIsNotNone(future, 'the numerical task should have been submitted')
        future.result(timeout=5.)
        engine.poll()

    def observe(self, engine, pose, seconds=.1):
        self.clock.advance(seconds)
        self.stamp += round(seconds * 1e9)
        return engine.observe_odometry(self.stamp, pose, self.clock())

    def track(self, engine, query, odom):
        engine.observe_odometry(self.stamp, odom, self.clock())
        self.assertTrue(engine.submit(query, self.stamp, odom, self.clock()))
        self.finish(engine)
        self.assertTrue(engine.status()['ready'], engine.status())

    def test_actual_fit_composes_nonidentity_maps_and_imu_lever_arm_at_current_pose(self):
        correction = from_translation_rpy([2., -.5, .8], [.08, -.1, .3])
        odom_at_scan = from_translation_rpy([.6, -.3, .15], [-.06, .2, -.25])
        nav_map = from_translation_rpy([-.8, 1.4, -.25], [.04, -.03, -.45])
        imu_base = from_translation_rpy([.32, -.12, -.21], [.02, -.05, .17])
        query = transform_points(inverse(correction), self.points)
        engine = self.make_engine(correction=correction, odom=odom_at_scan,
                                  nav_map=nav_map, imu_base=imu_base)
        self.track(engine, query, odom_at_scan)
        odom_now = from_translation_rpy([.64, -.28, .19], [-.05, .22, -.23])
        body_now = self.observe(engine, odom_now)
        actual_nav_body = engine.nav_odom() @ body_now
        expected_nav_body = nav_map @ correction @ odom_now @ imu_base
        np.testing.assert_allclose(actual_nav_body[:3, 3], expected_nav_body[:3, 3], atol=2e-6)
        self.assertLess(rotation_error_rad(actual_nav_body, expected_nav_body), 2e-6)
        self.assertEqual(engine.status()['correction_stamp_ns'], str(self.stamp - 100_000_000))
        self.assertEqual(engine.status()['correction_sequence'], 1)
        self.assertGreater(engine.status()['propagated_distance_m'], .04)

    def test_accepted_correction_never_stays_ready_from_fresh_odom_alone(self):
        engine = self.make_engine()
        self.track(engine, self.points, np.eye(4))
        for _ in range(11):
            self.observe(engine, np.eye(4))
        status = engine.status()
        self.assertFalse(status['ready'])
        self.assertEqual(status['state'], 'MAP_CORRECTION_STALE')
        self.assertIsNone(engine.nav_odom())
        self.assertEqual(status['correction_sequence'], 1)

    def test_saved_exclusions_filter_only_localization_queries_in_reference_map_frame(self):
        correction = from_translation_rpy([.2, -.4, .1], [.03, -.02, .4])
        bundle = fixture_bundle(self.sha256, correction=correction,
            nav_map=from_translation_rpy([20, -10, 3], [0, 0, 1.]))
        region = {'kind': 'localization', 'selection': 'outside',
            'polygon': [[-4, -3], [5, -3], [5, 4], [-4, 4]], 'z_min': -2., 'z_max': 4.}
        bundle['localization_3d']['edit_history'] = [{'purpose': 'localization', 'annotation': {
            'source': {'frame_id': 'survey_map'}, 'regions': [region,
                {**region, 'kind': 'visibility', 'selection': 'inside'},
                {**region, 'kind': 'keepout', 'selection': 'inside'}]}}]
        outside = np.random.default_rng(45).uniform([8, -1, 0], [10, 2, 2], (96, 3))
        query = transform_points(inverse(correction), np.vstack([self.points, outside]))
        before = query.copy()
        engine = OperationalLocalizer(bundle, self.path, clock=self.clock)
        self.addCleanup(engine.close)
        self.track(engine, query, np.eye(4))
        np.testing.assert_array_equal(query, before)
        np.testing.assert_allclose(engine.correction, correction, atol=2e-6)
        self.assertEqual(engine.metrics['registered_input_points'], 480)
        self.assertEqual(engine.metrics['localization_selected_points'], 384)
        self.assertEqual(engine.metrics['localization_excluded_points'], 96)

    def test_exclusion_without_enough_points_expires_previous_correction(self):
        engine = self.make_engine()
        self.track(engine, self.points, np.eye(4))
        from robot_dashboard.pcd_editing.geometry import _compile_region
        engine.exclusions = [_compile_region({'kind': 'localization', 'selection': 'inside',
            'polygon': [[-4, -3], [5, -3], [5, 4], [-4, 4]], 'z_min': -2., 'z_max': 4.})]
        for _ in range(6):
            self.observe(engine, np.eye(4))
        self.assertTrue(engine.submit(self.points, self.stamp, np.eye(4), self.clock()))
        with self.assertRaisesRegex(ValueError, 'INSUFFICIENT_LOCALIZATION_POINTS_AFTER_EXCLUSION'):
            engine.future.result(timeout=5.)
        engine.poll()
        for _ in range(5):
            self.observe(engine, np.eye(4))
        self.assertFalse(engine.status()['ready'])
        self.assertIsNone(engine.nav_odom())

    def test_propagation_distance_is_bounded_even_with_fresh_correction(self):
        engine = self.make_engine()
        self.track(engine, self.points, np.eye(4))
        moved = from_translation_rpy([.6, 0, 0], [0, 0, 0])
        self.observe(engine, moved, seconds=.3)
        self.assertFalse(engine.status()['ready'])
        self.assertAlmostEqual(engine.status()['propagated_distance_m'], .6)
        self.assertIsNone(engine.nav_odom())

    def test_actual_fit_that_exceeds_correction_step_requires_reseed(self):
        bundle = fixture_bundle(self.sha256)
        bundle['policy']['max_translation_step_m'] = .05
        bundle['seed_T_map_imu'] = from_translation_rpy([-.12, 0, 0], [0, 0, 0]).tolist()
        engine = OperationalLocalizer(bundle, self.path, clock=self.clock)
        self.addCleanup(engine.close)
        engine.observe_odometry(self.stamp, np.eye(4), self.clock())
        self.assertTrue(engine.submit(self.points, self.stamp, np.eye(4), self.clock()))
        self.finish(engine)
        self.assertFalse(engine.status()['ready'])
        self.assertEqual(engine.status()['state'], 'CORRECTION_JUMP_RESEED_REQUIRED')
        self.assertIsNone(engine.seed)
        self.assertIsNone(engine.nav_odom())

    def test_old_worker_cannot_apply_after_source_generation_invalidation(self):
        engine = self.make_engine()
        engine.observe_odometry(self.stamp, np.eye(4), self.clock())
        computed = threading.Event()
        release = threading.Event()
        self.addCleanup(release.set)

        def delayed(*args, **kwargs):
            result = solve_prepared(*args, **kwargs)
            computed.set()
            if not release.wait(timeout=3.):
                raise AssertionError('test did not release numerical worker')
            return result

        with mock.patch('robot_dashboard.relocalization.operational.solve_prepared', delayed):
            self.assertTrue(engine.submit(self.points, self.stamp, np.eye(4), self.clock()))
            self.assertTrue(computed.wait(timeout=3.))
            generation = engine.generation
            engine.invalidate('SYNTHETIC_SOURCE_REPLACED')
            release.set()
            self.finish(engine)
        self.assertEqual(engine.generation, generation + 1)
        self.assertIsNone(engine.correction)
        self.assertEqual(engine.status()['correction_sequence'], 0)
        self.assertEqual(engine.status()['state'], 'SYNTHETIC_SOURCE_REPLACED')

    def test_stationary_dwell_requires_advancing_source_and_fresh_receipts(self):
        engine = self.make_engine()
        engine.observe_odometry(self.stamp, np.eye(4), self.clock())
        for _ in range(23):
            self.observe(engine, np.eye(4))
        self.assertGreaterEqual(engine.stopped_seconds(), 2.)
        self.clock.advance(.6)
        self.assertEqual(engine.stopped_seconds(), 0.)
        # Repeated source time is a discontinuity, not another stop sample.
        engine.observe_odometry(self.stamp, np.eye(4), self.clock())
        self.assertEqual(engine.stopped_seconds(), 0.)
        self.assertIsNone(engine.seed)

    def test_new_planar_click_preserves_body_height_tilt_and_calibration(self):
        nav_map = from_translation_rpy([2., -1., .4], [.1, -.2, .3])
        imu_base = from_translation_rpy([.3, -.15, -.2], [.02, -.04, .12])
        staged = from_translation_rpy([.5, .2, .6], [.08, -.15, .4])
        engine = self.make_engine(correction=staged, nav_map=nav_map, imu_base=imu_base)
        engine.observe_odometry(self.stamp, np.eye(4), self.clock())
        for _ in range(23): self.observe(engine, np.eye(4))
        before = nav_map @ staged @ imu_base
        yaw = math.atan2(before[1, 0], before[0, 0]) + .6
        requested = from_translation_rpy([before[0, 3]+.8, before[1, 3]-.4, 0.], [0., 0., yaw])
        immutable = copy.deepcopy(engine.bundle)
        engine.reseed(requested)
        after = nav_map @ engine.seed @ imu_base
        np.testing.assert_allclose(after[:2, 3], requested[:2, 3], atol=1e-12)
        self.assertAlmostEqual(after[2, 3], before[2, 3])
        self.assertAlmostEqual(math.atan2(after[1, 0], after[0, 0]), yaw)
        np.testing.assert_allclose(after[2, :3], before[2, :3], atol=1e-12)
        self.assertEqual(engine.bundle, immutable)
        self.assertIsNone(engine.correction, 'a click is not a successful map fit')

    def test_rotating_imu_lever_arm_changes_body_velocity_in_body_frame(self):
        imu_base = from_translation_rpy([.4, .1, -.2], [0, 0, .2])
        engine = self.make_engine(imu_base=imu_base)
        engine.observe_odometry(self.stamp, np.eye(4), self.clock())
        odom_now = from_translation_rpy([0, 0, 0], [0, 0, .05])
        body_now = self.observe(engine, odom_now)
        previous_body = imu_base
        expected_linear = body_now[:3, :3].T @ (body_now[:3, 3] - previous_body[:3, 3]) / .1
        linear, angular = engine.body_velocity
        np.testing.assert_allclose(linear, expected_linear, atol=1e-10)
        np.testing.assert_allclose(angular, [0, 0, .5], atol=1e-10)
        self.assertGreater(engine.speed, .2)
        self.assertEqual(engine.stopped_seconds(), 0.)

    def test_duplicate_query_stamp_and_stale_capture_do_not_launch_another_fit(self):
        engine = self.make_engine()
        self.track(engine, self.points, np.eye(4))
        self.clock.advance(.6)
        self.assertFalse(engine.submit(self.points, self.stamp, np.eye(4), self.clock()))
        self.assertFalse(engine.submit(self.points, self.stamp + 600_000_000, np.eye(4), self.clock() - .6))
        self.assertIsNone(engine.future)
        self.assertEqual(engine.sequence, 1)

    def test_sector_counts_use_body_heading_not_map_or_sensor_x(self):
        # More points lie toward O:+Y, which is body front at yaw +90 degrees.
        rng = np.random.default_rng(975)
        points = rng.uniform([-.3, 1., -.5], [.3, 3., 1.], (192, 3))
        sha = write_pcd(self.path, points)
        odom = from_translation_rpy([0, 0, 0], [0, 0, math.pi / 2])
        bundle = fixture_bundle(sha, odom=odom)
        engine = OperationalLocalizer(bundle, self.path, clock=self.clock)
        self.addCleanup(engine.close)
        self.track(engine, points, odom)
        self.assertEqual(engine.metrics['body_sectors'], {'front': 192, 'rear': 0, 'left': 0, 'right': 0})
        self.assertEqual(engine.status()['weighting'], 'ALL_DIRECTION_BASELINE')

    def test_hash_covers_non_xyz_attributes_and_source_is_unchanged(self):
        before = self.path.read_bytes()
        points, count = read_reference(self.path, self.sha256)
        self.assertEqual(count, len(self.points))
        np.testing.assert_allclose(points, self.points, atol=2e-7)
        self.assertEqual(before, self.path.read_bytes())
        mutated = bytearray(before)
        # The final ring byte is outside XYZ and must remain in the hash contract.
        mutated[-1] ^= 1
        self.path.write_bytes(mutated)
        with self.assertRaisesRegex(ValueError, 'REFERENCE_HASH_CHANGED'):
            read_reference(self.path, self.sha256)

    def test_reference_sampling_reaches_records_beyond_any_browser_preview(self):
        rng = np.random.default_rng(614)
        full_source = rng.uniform(-1., 1., (105_000, 3))
        # The marker is in a late source record, far beyond preview-sized inputs.
        full_source[-2] = [17., 23., 31.]
        sha = write_pcd(self.path, full_source)
        loaded, source_count = read_reference(self.path, sha)
        self.assertEqual(source_count, 105_000)
        self.assertLessEqual(len(loaded), 100_000)
        self.assertGreater(len(loaded), 512)
        self.assertTrue(np.any(np.all(loaded == [17., 23., 31.], axis=1)))

    def test_reference_rejects_symlink_and_empty_geometry(self):
        linked = self.path.parent / 'linked.pcd'
        linked.symlink_to(self.path)
        with self.assertRaisesRegex(ValueError, 'REFERENCE_FILE_INVALID'):
            read_reference(linked, self.sha256)
        sha = write_pcd(self.path, self.points[:40])
        with self.assertRaisesRegex(ValueError, 'REFERENCE_TOO_SMALL'):
            read_reference(self.path, sha)

    def test_untrusted_status_cannot_supply_nonfinite_stop_evidence(self):
        engine = self.make_engine()
        status = engine.status()
        self.assertIsNotNone(sanitize_status(status))
        for key in ('stopped_seconds', 'linear_speed_mps', 'angular_speed_rps', 'correction_age_s'):
            invalid = copy.deepcopy(status)
            invalid[key] = float('nan')
            self.assertIsNone(sanitize_status(invalid), key)


if __name__ == '__main__':
    unittest.main()
