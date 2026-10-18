import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from scripts.inspect_se3_pair import alignment_metrics, inspect_pair, write_experiment
from robot_dashboard.relocalization.experimental_se3 import (
    Cloud, ExperimentalSE3Error, from_translation_rpy, inverse, transform_points,
)


class PairInspectionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_transform_direction_and_input_arrays_unchanged(self):
        points = np.random.default_rng(21).uniform(-2, 2, (100, 3))
        transform = from_translation_rpy([.12, -.08, .1], [.02, -.03, .04])
        query_points = transform_points(inverse(transform), points)
        saved = query_points.copy()
        target = Cloud(points, 'map', 'REGISTERED_MAP')
        query = Cloud(query_points, 'query', 'REGISTERED_QUERY', stamp_ns=123)
        correct = alignment_metrics(target, query, transform)
        wrong = alignment_metrics(target, query, inverse(transform))
        self.assertLess(correct['inlier_rmse_m'], 1e-7)
        self.assertGreater(wrong['inlier_rmse_m'], .1)
        row = inspect_pair(target, query, [np.eye(4)])[0]
        self.assertEqual(row['se3']['status'], 'CANDIDATE')
        self.assertLess(row['after']['inlier_rmse_m'], row['before']['inlier_rmse_m'])
        np.testing.assert_array_equal(query_points, saved)
        with self.assertRaises(ExperimentalSE3Error):
            inspect_pair(target, query, [])

    def test_no_overlap_has_null_residual_and_rejection_not_success(self):
        points = np.random.default_rng(21).uniform(-1, 1, (70, 3))
        row = inspect_pair(Cloud(points, 'map', 'REGISTERED_MAP'),
                           Cloud(points, 'query', 'REGISTERED_QUERY', stamp_ns=2),
                           [from_translation_rpy([20, 20, 20], [0, 0, 0])])[0]
        self.assertEqual(row['before']['overlap_ratio'], 0)
        self.assertIsNone(row['after']['inlier_rmse_m'])
        self.assertEqual(row['se3']['status'], 'REJECTED')

    def test_synthetic_saved_pair_seed_results_and_no_overwrite(self):
        output = self.root / 'demo'
        report = write_experiment(output, synthetic_demo=True)
        self.assertEqual(report['status'], 'EVALUATED')
        self.assertEqual(report['evidence_type'], 'synthetic_fixture')
        self.assertFalse(report['input']['independent_real_acquisitions'])
        self.assertEqual(len(report['measurements']), 3)
        self.assertEqual(report['global_relocalization'], 'NOT_RUN')
        self.assertIsNone(report['absolute_position_error_m'])
        self.assertEqual(report['measurements'][2]['se3']['status'], 'REJECTED')
        before = (output / 'reference.npy').read_bytes()
        with self.assertRaises(FileExistsError):
            write_experiment(output, synthetic_demo=True)
        self.assertEqual((output / 'reference.npy').read_bytes(), before)

    def test_unqualified_real_input_stays_blocked_with_no_synthetic_fallback(self):
        path = self.root / 'unqualified.json'
        manifest = {'schema': 'robot-scope.recorded-se3-input.v1', 'evidence_type': 'recorded_real',
                    'provenance': {'calibration_verified': False}}
        original = copy.deepcopy(manifest)
        path.write_text(json.dumps(manifest))
        report = write_experiment(self.root / 'blocked', manifest_path=path)
        self.assertEqual(report['status'], 'BLOCKED')
        self.assertIn('calibration_verified', report['reason'])
        self.assertEqual(report['measurements'], [])
        self.assertEqual(json.loads(path.read_text()), original)
        self.assertFalse((self.root / 'blocked/reference.npy').exists())

    @unittest.skipUnless(importlib.util.find_spec('matplotlib'), 'optional SVG plotting dependency absent')
    def test_overlay_artifacts_label_synthetic_and_not_operational(self):
        report = write_experiment(self.root / 'plots', synthetic_demo=True, plots=True)
        self.assertEqual(len(report['overlay_files']), 3)
        text = (self.root / 'plots/seed-0-overlay.svg').read_text()
        self.assertIn('synthetic_fixture', text)
        self.assertIn('operational application NOT_RUN', text)
        self.assertIn('T_target_source', text)


if __name__ == '__main__':
    unittest.main()
