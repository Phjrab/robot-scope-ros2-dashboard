"""Synthetic policy tests: stored residual is not a physical accuracy reference."""
import copy
import math
import unittest
from unittest.mock import patch

import numpy as np

from robot_dashboard.relocalization.observation_alignment import ObservationAligner
from robot_dashboard.relocalization.observation_policy import qualify_observation
from test_observation_alignment import Agent, Catalog, inputs, request_body


def solver_result(rmse=.07, **metrics):
    return {"status": "REJECTED" if rmse > .05 else "CANDIDATE",
            "reason": "HIGH_RESIDUAL" if rmse > .05 else "CANDIDATE",
            "metrics": {"rmse_m": rmse, "converged": True, "overlap_ratio": .95,
                        "geometry_min_max_eigen_ratio": .1,
                        "matched_geometry_min_max_eigen_ratio": .1, **metrics}}


class ObservationPolicyTests(unittest.TestCase):
    def assess(self, result, inliers=95, query=100):
        before = copy.deepcopy(result)
        value = qualify_observation(result, inlier_count=inliers, query_count=query)
        self.assertEqual(result, before)
        self.assertIsNone(value['body_pose'])
        self.assertFalse(value['tracking_verified'])
        return value

    def test_exact_boundary_and_preserved_original_assessment(self):
        for value, passed in [(.05, True), (.07, True), (math.nextafter(.1, 0), True),
                              (.1, True), (math.nextafter(.1, math.inf), False)]:
            with self.subTest(value=value):
                result = self.assess(solver_result(value))
                self.assertEqual(result['status'] == 'CANDIDATE', passed)
                self.assertEqual(result['residual_evaluation']['residual_passed'], passed)
                self.assertEqual(result['residual_evaluation']['original_residual_passed'], value <= .05)
                self.assertEqual(result['original_assessment']['reason'], 'CANDIDATE' if value <= .05 else 'HIGH_RESIDUAL')
                self.assertFalse(result['residual_evaluation']['overall_candidate_acceptance_evaluated'])
                self.assertIsNone(result['residual_evaluation']['overall_candidate_accepted'])

    def test_residual_cannot_hide_nonconvergence_or_any_other_gate(self):
        cases = [(dict(converged=False), 'NOT_CONVERGED'),
                 (dict(overlap_ratio=.59), 'LOW_OVERLAP'),
                 (dict(geometry_min_max_eigen_ratio=.001), 'DEGENERATE_GEOMETRY'),
                 (dict(matched_geometry_min_max_eigen_ratio=.001), 'DEGENERATE_MATCHED_GEOMETRY')]
        for metrics, reason in cases:
            with self.subTest(reason=reason):
                value = self.assess(solver_result(**metrics))
                self.assertEqual(value['status'], 'REJECTED')
                self.assertIn(reason, value['gate_reasons'])
                self.assertTrue(value['residual_evaluation']['residual_passed'])
        for count in (59, 101, True):
            self.assertIn('INSUFFICIENT_INLIERS', self.assess(solver_result(), count)['gate_reasons'])

    def test_unknown_solver_failure_and_unavailable_scores_fail_closed(self):
        original = solver_result(); original['reason'] = 'FUTURE_SOLVER_FAILURE'
        self.assertIn('ORIGINAL_SOLVER_REJECTED', self.assess(original)['gate_reasons'])
        for bad in (None, float('inf'), -1, True, '.07'):
            original = solver_result(); original['metrics']['rmse_m'] = bad
            value = self.assess(original)
            self.assertEqual(value['status'], 'REJECTED')
            self.assertIsNone(value['residual_evaluation'])

    def test_live_wrapper_exposes_policy_without_changing_solver_default(self):
        # Real synthetic registration through the public live wrapper. No sensor.
        cloud, pose = inputs()
        reference = np.frombuffer(cloud['points_bytes'], dtype='<f4').reshape(-1, 3)
        result = ObservationAligner().estimate(Catalog(reference), Agent(cloud, pose), request_body())
        self.assertEqual(result['status'], 'CANDIDATE')
        self.assertEqual(result['original_assessment']['status'], 'CANDIDATE')
        self.assertEqual(result['residual_evaluation']['policy']['max_rmse_m'], .1)
        self.assertEqual(result['metrics']['inlier_count'], len(reference))
        self.assertIsNone(result['body_pose'])

    def test_explicit_nonresidual_failure_and_inconsistent_original_never_promote(self):
        for reason in ('NOT_CONVERGED', 'LOW_OVERLAP', 'DEGENERATE_GEOMETRY',
                       'DEGENERATE_MATCHED_GEOMETRY'):
            original = solver_result(); original['reason'] = reason
            with self.subTest(reason=reason):
                value = self.assess(original)
                self.assertEqual(value['status'], 'REJECTED')
                self.assertIn(reason, value['gate_reasons'])
        for status, reason, rmse in [('CANDIDATE', 'HIGH_RESIDUAL', .07),
                                    ('CANDIDATE', 'CANDIDATE', .07),
                                    ('REJECTED', 'HIGH_RESIDUAL', .03),
                                    ('REJECTED', 'CANDIDATE', .03)]:
            original = solver_result(rmse); original.update(status=status, reason=reason)
            self.assertIn('ORIGINAL_SOLVER_REJECTED', self.assess(original)['gate_reasons'])

    def test_wrapper_retains_rejected_geometry_and_never_changes_transform_or_rmse(self):
        cloud, pose = inputs()
        reference = np.frombuffer(cloud['points_bytes'], dtype='<f4').reshape(-1, 3)
        from robot_dashboard.relocalization.observation_alignment import register_se3
        captured = []
        def fixed_score(*args, **kwargs):
            result = register_se3(*args, **kwargs)
            result['metrics']['rmse_m'] = .07
            result['metrics']['converged'] = False
            result['status'], result['reason'] = 'REJECTED', 'HIGH_RESIDUAL'
            captured.append(copy.deepcopy(result))
            return result
        with patch('robot_dashboard.relocalization.observation_alignment.register_se3', side_effect=fixed_score):
            result = ObservationAligner().estimate(Catalog(reference), Agent(cloud, pose), request_body())
        self.assertEqual(result['metrics']['rmse_m'], captured[0]['metrics']['rmse_m'])
        self.assertEqual(result['original_assessment']['reason'], 'HIGH_RESIDUAL')
        self.assertEqual(result['reason'], 'NOT_CONVERGED')
        self.assertTrue(result['residual_evaluation']['residual_passed'])
        np.testing.assert_allclose(result['T_map_odom'], np.eye(4), atol=1e-6)


if __name__ == '__main__':
    unittest.main()
