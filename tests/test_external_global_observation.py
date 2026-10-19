import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest

import numpy as np

from robot_dashboard.relocalization.external_global_observation import (
    ExternalGlobalObservationError, ExternalGlobalObservationRunner,
)
from robot_dashboard.relocalization.global_observation_jobs import GlobalObservationJobManager


FAKE = '''import hashlib,json
from pathlib import Path
import numpy as np
def run_se3_isolated(manifest_path, timeout_s, max_results):
 p=Path(manifest_path);m=json.loads(p.read_text());f=m['frames'][0]
 world=np.load(p.parent/m['map_file']);scan=np.load(p.parent/f['points_file'])
 return [{'status':'OBSERVATION_ONLY_UNVERIFIED','map_frame':m['map_frame'],
 'scan_frame':m['sensor_frame'],'frame_id':f['frame_id'],'session_id':f['session_id'],
 'source_stamp_ns':f['source_stamp_ns'],'source_record':f,
 'map_id':'sha256:'+hashlib.sha256(world.tobytes()).hexdigest(),
 'input_points':len(scan),'reference_points':len(world),'selected_candidate':None,
 'candidates':[{'rmse_m':.07,'map_from_scan':np.eye(4).tolist(),
 'gate_reasons':['RMSE_ABOVE_0.05M','REFINEMENT_NOT_STATIONARY']}]}]
'''

# Mirrors a valid, diagnostics-heavy backend result near the unchanged 64 KiB
# worker limit. Repeating policy metadata for each candidate makes the enclosing
# result exceed that limit, even though the worker's raw result fits.
NEAR_LIMIT = FAKE + '''
_base_run_se3_isolated = run_se3_isolated
def run_se3_isolated(manifest_path, timeout_s, max_results):
 values=_base_run_se3_isolated(manifest_path, timeout_s, max_results)
 value=values[0];template=value['candidates'][0]
 value['candidates']=[dict(template,attempt=i,overlap=.95,inlier_count=15200,
   refinement_stages=[{'stage':'robust_full_reference','map_from_scan':template['map_from_scan'],
                       'rmse_m':.07,'overlap':.95,'gate_reasons':template['gate_reasons'],
                       'refinement_diagnostics':{'fit_support':15200}} for _ in range(4 if i<6 else 1)],
   refinement_diagnostics={'trace':''}) for i in range(18)]
 target=61556
 raw=json.dumps(value,allow_nan=False,separators=(',',':')).encode()
 assert len(raw)<target
 value['candidates'][0]['refinement_diagnostics']['trace']='d'*(target-len(raw))
 assert len(json.dumps(value,allow_nan=False,separators=(',',':')).encode())==target
 return values
'''

# Model the reviewed v0.3.1 adapter's extra selection policy and original 5 cm
# residual-gate evidence on all 18 candidates and 36 stages, on top of the
# same 61,556-byte original diagnostic payload.
NEAR_LIMIT_WITH_SELECTION = NEAR_LIMIT + '''
_original_run_se3_isolated = run_se3_isolated
def run_se3_isolated(manifest_path, timeout_s, max_results):
 values=_original_run_se3_isolated(manifest_path, timeout_s, max_results)
 value=values[0]
 value['selection_policy']={'schema':'robot-scope.global-provisional-selection.v1',
   'adapter':'dashboard-v031-residual-gate-v1','original_max_rmse_m':.05,
   'provisional_max_rmse_m':.10,'scoring':'UNCHANGED_ORIGINAL_REFERENCE_POPULATION',
   'scope':'PROVISIONAL_OBSERVATION_ONLY','original_selection_replayed':False}
 for candidate in value['candidates']:
  candidate['original_residual_gate']='RMSE_ABOVE_0.05M'
  candidate['gate_reasons']=['REFINEMENT_NOT_STATIONARY']
  for stage in candidate['refinement_stages']:
   stage['original_residual_gate']='RMSE_ABOVE_0.05M'
   stage['gate_reasons']=['REFINEMENT_NOT_STATIONARY']
 return values
'''


class ExternalGlobalObservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.package = self.root / 'auto_localization'
        self.package.mkdir()
        (self.package / '__init__.py').write_text('')
        self.pin = self.root / 'pin.json'
        self.raw = np.array([[0., 0., 0.], [1., 2., 3.]], dtype='<f8').tobytes()
        self.context = dict(map_id='map', map_revision='revision', map_frame='camera_init',
                            source_frame='hesai_lidar', observer_id='observer', observer_epoch='epoch',
                            source_stamp_ns='1792380422951489687')
        for name in ('map', 'scan'):
            self.context[name] = dict(encoding='float64_le_xyz', point_count=2,
                                      sha256=hashlib.sha256(self.raw).hexdigest())

    def runner(self, source=FAKE, timeout=5.):
        (self.package / 'isolated.py').write_text(source)
        files = {str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in self.package.glob('*.py')}
        self.pin.write_text(json.dumps({'schema':'robot-scope.global-source-pin.v1','files':files}))
        return ExternalGlobalObservationRunner(sys.executable, str(self.root), str(self.pin), timeout_s=timeout)

    def run_one(self, runner, cancel=None):
        return runner.run_arrays(scan_bytes=self.raw, map_bytes=self.raw,
                                 context=self.context, cancel_event=cancel or threading.Event())

    def test_unconfigured_and_modified_package_fail_closed(self):
        self.assertFalse(ExternalGlobalObservationRunner().status()['available'])
        runner = self.runner()
        self.assertTrue(runner.status()['available'])
        (self.package / 'isolated.py').write_text(FAKE + '\n# changed')
        self.assertFalse(runner.status()['available'])
        with self.assertRaisesRegex(ExternalGlobalObservationError, 'HASH_MISMATCH'):
            self.run_one(runner)

    def test_success_keeps_stamp_zero_population_and_rejections(self):
        result = self.run_one(self.runner())
        self.assertEqual(result['source_stamp_ns'], self.context['source_stamp_ns'])
        self.assertEqual(result['input_points'], 2)
        self.assertIsNone(result['selected_candidate'])
        self.assertEqual(result['candidates'][0]['gate_reasons'], ['RMSE_ABOVE_0.05M', 'REFINEMENT_NOT_STATIONARY'])
        policy = result['residual_comparison_policy']
        self.assertEqual(policy['schema'], 'robot-scope.residual-comparison-policy.v1')
        self.assertEqual(policy['policy']['max_rmse_m'], .10)
        self.assertEqual(policy['original_policy']['max_rmse_m'], .05)
        self.assertEqual(policy['candidate_index_basis'], 'CANDIDATE_ARRAY_INDEX')
        self.assertFalse(policy['overall_candidate_acceptance_evaluated'])
        self.assertIsNone(policy['overall_candidate_accepted'])
        self.assertEqual(policy['comparison_fields'], ['residual_passed', 'original_residual_passed'])
        comparison = result['residual_comparisons'][0]
        self.assertEqual(comparison, [True, False])
        self.assertTrue(result['execution']['worker_reaped'])

    def test_missing_rmse_is_explicitly_unverified(self):
        source = FAKE.replace("'rmse_m':.07", "'rmse_m':None")
        result = self.run_one(self.runner(source))
        self.assertIsNone(result['candidates'][0]['rmse_m'])
        self.assertEqual(result['residual_comparisons'], [{'reason': 'INVALID_STORED_RMSE'}])

    def test_near_limit_backend_diagnostics_survive_sidecar_and_job_envelope(self):
        runner = self.runner(NEAR_LIMIT)
        result = self.run_one(runner)
        self.assertEqual(len(result['candidates']), 18)
        self.assertEqual(sum(len(candidate['refinement_stages']) for candidate in result['candidates']), 36)
        self.assertTrue(result['candidates'][0]['refinement_diagnostics']['trace'].startswith('d'))
        self.assertEqual(len(result['residual_comparisons']), 18)
        self.assertLessEqual(len(json.dumps(result, allow_nan=False, separators=(',', ':')).encode()), 65_536)

        manager = GlobalObservationJobManager(
            lambda payload, *, cancel_event: runner.run_arrays(
                scan_bytes=self.raw, map_bytes=self.raw, context=self.context,
                cancel_event=cancel_event),
            lambda captured: captured,
            max_result_bytes=65_536,
        )
        self.addCleanup(manager.close)
        job_id = manager.start('near-limit', self.context, {})['job_id']
        self.assertTrue(manager.wait(job_id, 5.))
        job = manager.job(job_id)
        self.assertEqual(job['state'], 'succeeded', job['reason'])
        observation = job['result']['observation']
        self.assertEqual(len(observation['candidates']), 18)
        self.assertEqual(observation['candidates'][0]['refinement_diagnostics']['trace'],
                         result['candidates'][0]['refinement_diagnostics']['trace'])

    def test_near_limit_with_provisional_selection_metadata_still_fits(self):
        runner = self.runner(NEAR_LIMIT_WITH_SELECTION)
        result = self.run_one(runner)
        self.assertEqual(result['selection_policy']['scope'], 'PROVISIONAL_OBSERVATION_ONLY')
        self.assertEqual(len(result['candidates']), 18)
        self.assertEqual(sum(len(candidate['refinement_stages']) for candidate in result['candidates']), 36)
        self.assertTrue(all(candidate['original_residual_gate'] == 'RMSE_ABOVE_0.05M'
                            for candidate in result['candidates']))
        self.assertTrue(all(stage['original_residual_gate'] == 'RMSE_ABOVE_0.05M'
                            for candidate in result['candidates'] for stage in candidate['refinement_stages']))
        self.assertTrue(result['candidates'][0]['refinement_diagnostics']['trace'].startswith('d'))
        self.assertLessEqual(len(json.dumps(result, allow_nan=False, separators=(',', ':')).encode()), 65_536)
        manager = GlobalObservationJobManager(
            lambda payload, *, cancel_event: runner.run_arrays(
                scan_bytes=self.raw, map_bytes=self.raw, context=self.context,
                cancel_event=cancel_event),
            lambda captured: captured,
            max_result_bytes=65_536,
        )
        self.addCleanup(manager.close)
        job_id = manager.start('near-limit-adapter', self.context, {})['job_id']
        self.assertTrue(manager.wait(job_id, 5.))
        job = manager.job(job_id)
        self.assertEqual(job['state'], 'succeeded', job['reason'])
        observation = job['result']['observation']
        self.assertEqual(observation['selection_policy'], result['selection_policy'])
        self.assertEqual(observation['candidates'][0]['refinement_diagnostics']['trace'],
                         result['candidates'][0]['refinement_diagnostics']['trace'])

    def test_frame_identity_mismatch_rejected(self):
        with self.assertRaisesRegex(ExternalGlobalObservationError, 'IDENTITY_MISMATCH'):
            self.run_one(self.runner(FAKE.replace("'frame_id':f['frame_id']", "'frame_id':'body'")))

    def test_nonfinite_not_silently_filtered(self):
        self.raw = np.array([[np.nan, 0., 1.]], dtype='<f8').tobytes()
        for value in (self.context['scan'], self.context['map']):
            value.update(point_count=1, sha256=hashlib.sha256(self.raw).hexdigest())
        with self.assertRaisesRegex(ExternalGlobalObservationError, 'NONFINITE_INPUT'):
            self.run_one(self.runner())

    def test_hash_mismatch_before_execution(self):
        self.context['scan']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ExternalGlobalObservationError, 'ARRAY_CONTRACT'):
            self.run_one(self.runner())

    def test_deadline_includes_import_hang_and_returns_bounded(self):
        started = time.monotonic()
        with self.assertRaisesRegex(ExternalGlobalObservationError, 'DEADLINE'):
            self.run_one(self.runner('import time\ntime.sleep(20)\n', timeout=.2))
        self.assertLess(time.monotonic() - started, 2.)

    def test_cancel_hanging_worker(self):
        cancel = threading.Event()
        timer = threading.Timer(.2, cancel.set)
        timer.start()
        self.addCleanup(timer.cancel)
        with self.assertRaisesRegex(ExternalGlobalObservationError, 'CANCELLED'):
            self.run_one(self.runner('import time\ntime.sleep(20)\n'), cancel)

    def test_backend_failure_or_oversize_never_returns_partial(self):
        for source in ['raise RuntimeError("fixture")\n', FAKE.replace("'candidates':[", "'padding':'x'*70000,'candidates':[")]:
            with self.subTest(source=source[:20]):
                with self.assertRaisesRegex(ExternalGlobalObservationError, 'WORKER_FAILED'):
                    self.run_one(self.runner(source))

    def test_invalid_matrix_is_rejected(self):
        source = FAKE.replace('np.eye(4).tolist()', '(np.eye(4)*2).tolist()')
        with self.assertRaisesRegex(ExternalGlobalObservationError, 'TRANSFORM_INVALID'):
            self.run_one(self.runner(source))

    def test_source_coverage_new_file_is_rejected(self):
        runner = self.runner()
        (self.package / 'extra.py').write_text('')
        self.assertEqual(runner.status()['reason'], 'GLOBAL_SOURCE_COVERAGE_MISMATCH')


if __name__ == '__main__':
    unittest.main()
