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
        evaluation = result['residual_comparisons'][0]['evaluation']
        self.assertTrue(evaluation['residual_passed'])
        self.assertFalse(evaluation['original_residual_passed'])
        self.assertIsNone(evaluation['overall_candidate_accepted'])
        self.assertTrue(result['execution']['worker_reaped'])

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
