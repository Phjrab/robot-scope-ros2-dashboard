"""Synthetic geometry and real numerical/runtime paths; no robot or ROS output."""
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

from robot_dashboard.relocalization.directional_weighting import (
    BASELINE, CANDIDATE, DirectionalFrame, SurfaceSupport, body_coordinates,
    sector_counts, validate_weighting,
)
from robot_dashboard.relocalization.experimental_se3 import (
    Cloud, ExperimentalSE3Error, from_translation_rpy, register_se3, transform_points,
)
from robot_dashboard.relocalization.observation_alignment import ReferenceIndex, solve_prepared
from robot_dashboard.relocalization.operational import OperationalLocalizer, validate_bundle
from tests.test_operational_3d_localization import fixture_bundle, write_pcd


def room_points():
    u, v = np.meshgrid(np.linspace(-3., 3., 19), np.linspace(-3., 3., 19))
    floor = np.column_stack([u.ravel(), v.ravel(), np.full(u.size, -1.)])
    y, z = np.meshgrid(np.linspace(-3., 3., 19), np.linspace(-.8, 2., 15))
    rear = np.column_stack([np.full(y.size, -3.), y.ravel(), z.ravel()])
    x, z = np.meshgrid(np.linspace(-2.8, 2.8, 19), np.linspace(-.8, 2., 15))
    sides = [np.column_stack([x.ravel(), np.full(x.size, s), z.ravel()]) for s in [-3., 3.]]
    return np.vstack([floor, rear, *sides])


class DirectionalWeightingTests(unittest.TestCase):
    def setUp(self):
        self.config = validate_weighting({'mode': CANDIDATE, 'evidence': 'SYNTHETIC_REGRESSION'})
        self.body = from_translation_rpy([.2, -.3, .4], [0., math.radians(14), .2])
        self.local = room_points()
        self.world = transform_points(self.body, self.local)
        self.index = ReferenceIndex(self.world)
        self.support = SurfaceSupport(self.index)
        self.stamp = 1_700_000_000_000_000_000

    def frame(self, points=None, body=None, previous=None):
        return DirectionalFrame(self.config, self.support,
            self.world if points is None else points, self.body if body is None else body,
            self.stamp, previous, time.monotonic()+10., frame_verified=True)

    def evaluate(self, frame, moved=None, squared_override=None):
        moved = self.world if moved is None else moved
        ids, squared = self.index.nearest(moved)
        if squared_override is not None:
            squared = squared_override
        weights = frame(moved, ids, squared, squared <= .75**2)
        return weights, frame.diagnostics

    def native(self):
        if self.index.tree is None:
            self.skipTest('candidate surface neighbourhoods require optional installed scipy')

    def test_disabled_is_explicit_and_invalid_overrides_fail_closed(self):
        self.assertEqual(validate_weighting(), {'mode': BASELINE})
        self.assertEqual(validate_weighting({'mode': BASELINE}), {'mode': BASELINE})
        for bad in [{'mode': CANDIDATE}, {'mode': 'rear'}, {'mode': BASELINE, 'rear_max_gain': 2.},
                    {'mode': CANDIDATE, 'evidence': 'x', 'rear_max_gain': 20.},
                    {'mode': CANDIDATE, 'evidence': 'x', 'transition_s': False},
                    {'mode': CANDIDATE, 'evidence': 'x', 'pitch_full_deg': 3.}]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_weighting(bad)

    def test_full_body_rotation_and_lever_arm_define_directions(self):
        body = from_translation_rpy([5., -3., 2.], [.4, -.5, 2.2])
        points = np.array([[2., .1, 1.], [-2., .1, 1.], [.1, 2., 1.], [.1, -2., 1.]])
        world = transform_points(body, points)
        np.testing.assert_allclose(body_coordinates(world, body), points, atol=1e-12)
        self.assertEqual(sector_counts(world, body), dict(front=1, rear=1, left=1, right=1))
        with self.assertRaisesRegex(ValueError, 'VERIFIED_BODY_FRAME'):
            DirectionalFrame(self.config, self.support, self.world, self.body,
                self.stamp, None, time.monotonic()+1, frame_verified=False)

    def test_ramp_quality_boost_has_rate_limit_and_iteration_count_does_not_advance_it(self):
        self.native()
        previous = {'stamp_ns': self.stamp-500_000_000, 'gains': [1., 1., 1., 1.]}
        frame = self.frame(previous=previous)
        weights, metrics = self.evaluate(frame)
        self.assertTrue(metrics['structure_observable'], metrics)
        gains = frame.next_state['gains']
        self.assertGreater(gains[1], 1.)
        self.assertTrue(all(1 <= x <= 1.125+1e-12 for x in gains))
        for _ in range(4):
            self.evaluate(frame)
        np.testing.assert_array_equal(gains, frame.next_state['gains'])
        self.assertTrue(np.all(weights > 0.), 'valid front/side observations must remain')
        self.assertAlmostEqual(sum(x['contribution_ratio'] for x in metrics['sectors']), 1.)
        self.assertEqual(metrics['direction_basis'], 'FULL_EXACT_STAMP_BODY_AXES_NOT_TRAVEL_DIRECTION')

    def test_ascent_top_descent_transitions_and_stamp_reset(self):
        self.native()
        previous = {'stamp_ns': self.stamp-500_000_000, 'gains': [1., 1.3, 1.1, 1.1]}
        for pitch in [14., 0., -14.]:
            body = from_translation_rpy([0., 0., 0.], [0., math.radians(pitch), 0.])
            frame = self.frame(body=body, previous=previous)
            self.evaluate(frame)
            self.assertLessEqual(abs(frame.next_state['gains'][1]-1.3), .125+1e-12)
        for offset in [0, -1_000_000_000, 1_000_000_000]:
            frame = self.frame(previous={'stamp_ns': self.stamp+offset, 'gains': [1., 1.3, 1.1, 1.1]})
            self.evaluate(frame)
            self.assertEqual(frame.next_state['gains'], [1., 1., 1., 1.])

    def test_single_plane_cannot_gain_confidence_from_many_low_residual_points(self):
        self.native()
        points = self.world[:361]
        index = ReferenceIndex(points)
        frame = DirectionalFrame(self.config, SurfaceSupport(index), points, self.body,
            self.stamp, {'stamp_ns': self.stamp-500_000_000, 'gains': [1.]*4},
            time.monotonic()+10, frame_verified=True)
        ids, squared = index.nearest(points)
        frame(points, ids, squared, squared <= .75**2)
        result = register_se3(Cloud(points, 'map', 'REGISTERED_MAP'),
            Cloud(points, 'odom', 'REGISTERED_QUERY', stamp_ns=self.stamp), np.eye(4))
        frame.finish(result)
        self.assertFalse(frame.diagnostics['structure_observable'])
        self.assertLess(frame.diagnostics['information_rank'], 6)
        self.assertEqual(frame.next_state['gains'], [1.]*4)
        self.assertEqual(result['status'], 'REJECTED')

    def test_duplicate_current_returns_do_not_multiply_evidence(self):
        self.native()
        one = self.frame()
        w1, d1 = self.evaluate(one)
        points = np.repeat(self.world, 3, axis=0)
        duplicate = self.frame(points=points)
        w2, d2 = self.evaluate(duplicate, points)
        self.assertAlmostEqual(float(w1.sum()), float(w2.sum()), places=8)
        self.assertEqual(d1['information_rank'], d2['information_rank'])
        self.assertTrue(d2['cached_map_normals_are_not_new_observations'])
        np.testing.assert_allclose([x['contribution_ratio'] for x in d1['sectors']],
            [x['contribution_ratio'] for x in d2['sectors']], atol=1e-10)

    def test_loss_of_structure_rejects_even_while_previous_gain_decays(self):
        self.native()
        points = self.world[:361]
        index = ReferenceIndex(points)
        frame = DirectionalFrame(self.config, SurfaceSupport(index), points, self.body,
            self.stamp, {'stamp_ns': self.stamp-500_000_000, 'gains': [1.,1.4,1.2,1.2]},
            time.monotonic()+10, frame_verified=True)
        ids,squared = index.nearest(points)
        frame(points,ids,squared,squared <= .75**2)
        result = dict(status='CANDIDATE',reason='CANDIDATE',metrics=dict(rmse_m=0.,overlap_ratio=1.))
        frame.finish(result)
        self.assertEqual(result['reason'],'DIRECTIONAL_STRUCTURE_INSUFFICIENT')
        self.assertGreater(frame.next_state['gains'][1],1.)
        self.assertLess(frame.next_state['gains'][1],1.4)

    def test_empty_overlap_has_no_invented_information(self):
        self.native()
        frame = self.frame()
        weights = frame(self.world,np.zeros(len(self.world),dtype=int),
            np.full(len(self.world),np.inf),np.zeros(len(self.world),dtype=bool))
        self.assertFalse(weights.any())
        self.assertFalse(frame.diagnostics['structure_observable'])
        self.assertIsNone(frame.diagnostics['weighted_objective_rmse_m'])

    def test_duplicate_rear_only_does_not_change_information_or_contribution(self):
        self.native()
        one = self.frame()
        _, d1 = self.evaluate(one)
        points = np.vstack([self.world, np.repeat(self.world[one.ids == 1], 4, axis=0)])
        duplicate = self.frame(points=points)
        _, d2 = self.evaluate(duplicate, points)
        np.testing.assert_allclose(d1['normal_information_eigenvalues'], d2['normal_information_eigenvalues'], atol=1e-10)
        np.testing.assert_allclose([x['contribution_ratio'] for x in d1['sectors']],
            [x['contribution_ratio'] for x in d2['sectors']], atol=1e-10)

    def test_bad_rear_correspondences_do_not_receive_blind_gain(self):
        self.native()
        previous = {'stamp_ns': self.stamp-500_000_000, 'gains': [1.]*4}
        good = self.frame(previous=previous)
        self.evaluate(good)
        bad = self.frame(previous=previous)
        squared = np.zeros(len(self.world))
        squared[bad.ids == 1] = .6**2
        self.evaluate(bad, squared_override=squared)
        self.assertLess(bad.next_state['gains'][1], good.next_state['gains'][1])
        self.assertLess(bad.next_state['gains'][1], 1.001)

    def test_common_unweighted_residual_is_not_replaced_by_weighted_objective(self):
        self.native()
        query = self.world.copy()
        query[:130, 2] += .2
        def low_weights(moved, ids, squared, mask):
            return np.r_[np.full(130, .001), np.ones(len(query)-130)]
        result = register_se3(Cloud(self.world, 'map', 'REGISTERED_MAP'),
            Cloud(query, 'odom', 'REGISTERED_QUERY', stamp_ns=self.stamp), np.eye(4),
            reference_limit=100_000, nearest=lambda p, _: self.index.nearest(p), query_weighting=low_weights)
        self.assertGreater(result['metrics']['rmse_m'], .05)
        self.assertEqual(result['reason'], 'HIGH_RESIDUAL')
        self.assertEqual(result['status'], 'REJECTED')
        with self.assertRaisesRegex(ExperimentalSE3Error, 'query weights'):
            register_se3(Cloud(self.world, 'map', 'REGISTERED_MAP'),
                Cloud(self.world, 'odom', 'REGISTERED_QUERY', stamp_ns=self.stamp), np.eye(4),
                query_weighting=lambda *args: np.full(len(self.world), np.nan))

    def test_missing_native_surface_support_fails_candidate_confidence_closed(self):
        ids, squared = self.index.nearest(self.world)
        frame = self.frame()
        with mock.patch.object(self.index, 'tree', None):
            frame(self.world, ids, squared, squared <= .75**2)
        self.assertFalse(frame.diagnostics['structure_observable'])
        self.assertEqual(frame.next_state['gains'], [1.]*4)

    def test_real_operational_opt_in_baseline_restore_and_source_invalidation(self):
        self.native()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'map.pcd'
            sha = write_pcd(path, self.world)
            baseline = fixture_bundle(sha, odom=self.body)
            enabled = copy.deepcopy(baseline)
            enabled['policy']['directional_weighting'] = {'mode': CANDIDATE, 'evidence': 'SYNTHETIC_RUNTIME'}
            validate_bundle(enabled)
            engine = OperationalLocalizer(enabled, path)
            self.addCleanup(engine.close)
            engine.observe_odometry(self.stamp, self.body)
            self.assertTrue(engine.submit(self.world, self.stamp, self.body, time.monotonic()))
            engine.future.result(timeout=5)
            engine.poll()
            self.assertTrue(engine.status()['ready'], engine.status())
            self.assertEqual(engine.status()['weighting'], CANDIDATE)
            self.assertIsNotNone(engine.directional_state)
            engine.invalidate('SOURCE_CHANGED')
            self.assertIsNone(engine.directional_state)
            self.assertFalse(engine.status()['ready'])
            # A new immutable bundle with the optional setting absent restores
            # the original numerical path; no sensor/map changes are needed.
            explicit = copy.deepcopy(baseline)
            explicit['policy']['directional_weighting'] = {'mode': BASELINE}
            engines = [OperationalLocalizer(b, path) for b in [baseline, explicit]]
            for e in engines:
                self.addCleanup(e.close)
                e.observe_odometry(self.stamp, self.body)
                e.submit(self.world, self.stamp, self.body, time.monotonic())
                e.future.result(timeout=5)
                e.poll()
                self.assertIsNone(e.surface_support)
                self.assertEqual(e.status()['weighting'], BASELINE)
                self.assertTrue(e.status()['ready'], e.status())
            np.testing.assert_array_equal(engines[0].correction, engines[1].correction)
            self.assertEqual(sha, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_inflight_old_generation_cannot_commit_weighting_state(self):
        self.native()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'map.pcd'
            sha = write_pcd(path, self.world)
            bundle = fixture_bundle(sha, odom=self.body)
            bundle['policy']['directional_weighting'] = {'mode': CANDIDATE, 'evidence': 'SYNTHETIC_RUNTIME'}
            engine = OperationalLocalizer(bundle, path)
            self.addCleanup(engine.close)
            entered, release = threading.Event(), threading.Event()
            def delayed(*args, **kwargs):
                entered.set()
                release.wait(2)
                return solve_prepared(*args, **kwargs)
            with mock.patch('robot_dashboard.relocalization.operational.solve_prepared', side_effect=delayed):
                engine.observe_odometry(self.stamp, self.body)
                engine.submit(self.world, self.stamp, self.body, time.monotonic())
                self.assertTrue(entered.wait(1))
                engine.invalidate('SOURCE_CHANGED')
                release.set()
                engine.future.result(timeout=5)
                engine.poll()
            self.assertIsNone(engine.directional_state)
            self.assertIsNone(engine.correction)


if __name__ == '__main__':
    unittest.main()
