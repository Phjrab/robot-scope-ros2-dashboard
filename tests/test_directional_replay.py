"""Replay data contracts and actual paired CLI with synthetic, public geometry."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np

from scripts.audit_directional_inputs import audit_case
from scripts.compare_directional_localization import load_case, phase_names
from robot_dashboard.relocalization.experimental_se3 import from_translation_rpy, matrix_to_quaternion_xyzw, transform_points
from tests.test_directional_weighting import room_points
from tests.test_operational_3d_localization import write_pcd


class DirectionalReplayTests(unittest.TestCase):
    def fixture(self):
        body = from_translation_rpy([.2,-.3,.4],[.2,-.25,1.2])
        local = room_points()
        # Avoid exact sector boundaries: floating inverse transforms cannot
        # establish which side of a diagonal an exactly-on-boundary ray lies.
        local[:, :2] += [.0123,.0049]
        points = transform_points(body, local)
        stamps = np.array([1_700_000_000_000_000_000,1_700_000_000_500_000_000],dtype=np.int64)
        d = dict(cloud_stamp_ns=stamps, cloud_receipt_ns=stamps,
            cloud_offsets=np.array([0,len(points),2*len(points)]), cloud_xyz=np.vstack([points,points]),
            odom_stamp_ns=stamps.copy(), odom_xyz=np.tile(body[:3,3],(2,1)),
            odom_quat=np.tile(matrix_to_quaternion_xyzw(body[:3,:3]),(2,1)),
            body_stamp_ns=stamps, body_offsets=np.array([0,len(points),2*len(points)]),
            body_xyz=np.tile(local,(2,1)))
        return {'A_'+k:v for k,v in d.items()}, points

    def test_axis_correct_input_audit_detects_representation_downsampling(self):
        data,_ = self.fixture()
        result = audit_case(data,'A',np.eye(4),[])
        json.dumps(result,allow_nan=False)
        self.assertEqual(result['current_scans'],2)
        self.assertEqual(result['dense_pairs'],2)
        self.assertEqual(result['original_lio_jump_threshold_exceedances'],0)
        self.assertGreater(result['estimator_stride_removed'],0)
        for sector in ['front','rear','left','right']:
            direction = result['stages'][0]['directions'][sector]
            self.assertEqual(direction['registered_to_dense_count_ratio']['median'],1.)
            self.assertLessEqual(direction['estimator_selected']['max'],direction['registered']['max'])

    def test_invalid_offsets_and_nonexact_odometry_fail_closed(self):
        data,_ = self.fixture()
        data['A_cloud_offsets'] = np.array([0,12,11])
        with self.assertRaisesRegex(ValueError,'INVALID_CASE_ARRAY_CONTRACT'):
            load_case(data,'A')
        data,_ = self.fixture()
        data['A_odom_stamp_ns'] += 1
        with self.assertRaisesRegex(ValueError,'EXACT_STAMP_ODOMETRY_REQUIRED'):
            audit_case(data,'A',np.eye(4),[])

    def test_batched_marker_is_not_invented_as_a_physical_entry_interval(self):
        stamp = '2023-11-14T22:13:20+00:00'
        intervals = [dict(case_id='A',phase_label='ENTRY',start_utc=stamp,end_utc=stamp)]
        names = phase_names(intervals,'A',1_700_000_000_000_000_000,1_700_000_000_000_000_000)
        self.assertIn('ENTRY_MARKER_APPROXIMATE',names)
        self.assertNotIn('ENTRY',names)

    def test_real_cli_pairs_same_inputs_and_prevents_overwriting_evidence(self):
        try:
            import scipy  # noqa: F401
        except ImportError:
            self.skipTest('paired native-index comparison requires installed scipy')
        data,points = self.fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            np.savez(root/'arrays.npz',**data)
            sha = write_pcd(root/'reference.pcd',points)
            for name,value in {
                'body.json':dict(verified=True,evidence='SYNTHETIC_BODY',T_imu_base=np.eye(4).tolist()),
                'priors.json':dict(cases={'A':dict(T_map_odom=np.eye(4).tolist())}),
                'intervals.json':[],
                'policy.json':dict(compute_budget_s=.5,max_rmse_m=.1,max_translation_step_m=.15,
                    max_rotation_step_rad=.1,directional_weighting=dict(mode='REAR_SIDE_QUALITY_V1',evidence='SYNTHETIC_REPLAY')),
            }.items():
                (root/name).write_text(json.dumps(value))
            script = Path(__file__).resolve().parents[1]/'scripts/compare_directional_localization.py'
            cmd = [sys.executable,str(script),'--arrays',str(root/'arrays.npz'),'--reference-pcd',str(root/'reference.pcd'),
                '--reference-sha256',sha,'--body-contract',str(root/'body.json'),'--frozen-priors',str(root/'priors.json'),
                '--stage-intervals',str(root/'intervals.json'),'--policy',str(root/'policy.json'),
                '--summary',str(root/'summary.json'),'--private-rows',str(root/'rows.jsonl'),'--cases','A']
            completed = subprocess.run(cmd,capture_output=True,text=True,timeout=20)
            self.assertEqual(completed.returncode,0,completed.stderr)
            rows = [json.loads(line) for line in (root/'rows.jsonl').read_text().splitlines()]
            self.assertEqual(len(rows),4)
            for before,after in zip(rows[::2],rows[1::2]):
                self.assertEqual(before['input_sha256'],after['input_sha256'])
                self.assertEqual(before['initial_transform_sha256'],after['initial_transform_sha256'])
                self.assertLess(before['common_unweighted_rmse_m'],1e-6)
                self.assertLess(after['common_unweighted_rmse_m'],1e-6)
                self.assertFalse(after['full_runtime_tracking_replay'])
            saved = hashlib.sha256((root/'rows.jsonl').read_bytes()).hexdigest()
            again = subprocess.run(cmd,capture_output=True,text=True,timeout=20)
            self.assertNotEqual(again.returncode,0)
            self.assertIn('outputs must be new distinct files',again.stderr)
            self.assertEqual(saved,hashlib.sha256((root/'rows.jsonl').read_bytes()).hexdigest())


if __name__ == '__main__':
    unittest.main()
