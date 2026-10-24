import unittest,json,math,hashlib
import numpy as np
from gait import *
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.asset=json.loads(ASSET.read_text());cls.trace=json.loads((HERE.parents[1]/'results/cone_detour.json').read_text());cls.records=build(cls.trace,cls.asset)
 def test_limits_and_ground(self):
  x=validate(self.records,self.asset);self.assertGreaterEqual(x['min_mesh_ground_clearance_m'],0);self.assertLess(x['max_foot_ik_residual_m'],1e-10);self.assertLess(x['max_consecutive_stance_xy_slip_m'],1e-10)
 def test_trace_pose_not_replanned(self):
  for r in self.records:np.testing.assert_allclose(r['pose'],sample(self.trace,r['t']),atol=1e-12)
 def test_blocked_freezes_all_joints(self):
  d=json.loads((HERE.parents[1]/'results/blocked.json').read_text());r=build(d,self.asset)
  for f in r:self.assertEqual(r[0]['q'],f['q']);self.assertTrue(all(f['stance'].values()))
 def test_all_twelve_joints_move(self):
  # Lateral hip articulation accounts for turning/anchored feet, not only knees.
  for name in self.asset['skeleton']['joint_order']:
   self.assertGreater(np.ptp([r['q'][name] for r in self.records]),.005,name)
 def test_middle_stop_returns_stance(self):
  frames=[]
  for i in range(101):
   x=min(.01*i,.3) if i<=50 else .3+.01*(i-50)
   frames.append({'t':i*.1,'pose':[x,0,0]})
  records=build({'frames':frames},self.asset)
  stop=[r for r in records if 3.2<=r['t']<=4.9]
  for r in stop:self.assertTrue(all(r['stance'].values()));self.assertEqual(r['q'],stop[0]['q'])
 def test_reproducible(self):self.assertEqual(self.records,build(self.trace,self.asset))
 def test_original_metrics_retained(self):self.assertEqual(self.trace['metrics']['outcome'],'GOAL_REACHED')
 def test_bad_parameters_rejected(self):
  for value in [0,-1,float('nan')]:
   with self.assertRaises(ValueError):build(self.trace,self.asset,stride_m=value)
 def test_duplicate_time_rejected(self):
  with self.assertRaises(ValueError):build({'frames':[{'t':0,'pose':[0,0,0]},{'t':0,'pose':[0,0,0]}]},self.asset)
 def test_official_limits_verified(self):self.assertTrue(json.loads((HERE/'official_urdf_check.json').read_text())['all_match'])
if __name__=='__main__':unittest.main()
