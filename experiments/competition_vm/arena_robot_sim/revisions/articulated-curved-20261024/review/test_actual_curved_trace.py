"""Independent checks against the exact external source trace, not synthetic fixtures."""
import os,json,hashlib,unittest
from pathlib import Path
import numpy as np
from review_helpers import independent_fk,rigid,ASSET,HERE,gait
SOURCE_ROOT=Path(os.environ.get('CURVED_TRACE_ROOT',str(gait.ROOT)))
class ActualCurved(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.path=Path(os.environ.get('CURVED_TRACE_FILE',str(SOURCE_ROOT/'experiments/competition_vm/arena_robot_sim/revisions/curved_slalom_20261024/results/slalom_5.json')));cls.source=json.loads(cls.path.read_text());jpath=Path(os.environ.get('CURVED_JOINT_FILE',str(HERE/'output/slalom_5_joints.json')));cls.joints=json.loads(jpath.read_text());cls.records=cls.joints['records']
 def test_hash_identity(self):self.assertEqual(self.joints['validation']['trace_sha256'],hashlib.sha256(self.path.read_bytes()).hexdigest())
 def test_source_pose_interpolation(self):
  t=np.array([f['t']for f in self.source['frames']]);p=np.array([f['pose']for f in self.source['frames']]);p[:,2]=np.unwrap(p[:,2])
  for f in self.records:np.testing.assert_allclose(f['pose'],[np.interp(f['t'],t,p[:,j])for j in range(3)],atol=1e-12)
 def test_yaw_contract(self):
  span=np.ptp([f['pose'][2]for f in self.records])
  if os.environ.get('EXPECTED_YAW_MODE','variable')=='fixed':self.assertAlmostEqual(span,0.,places=12)
  else:self.assertGreater(span,.05)
 def test_joint_limits(self):
  for f in self.records:
   for j in ASSET['skeleton']['joints']:
    if j['type']=='revolute':self.assertGreaterEqual(f['q'][j['name']],j['limit']['lower']);self.assertLessEqual(f['q'][j['name']],j['limit']['upper'])
 def test_independent_foot_fk(self):
  for f in self.records:
   ts=independent_fk(f['q']);root=rigid([*f['pose'][:2],gait.HEIGHT],[0,0,f['pose'][2]])
   for leg in gait.LEGS:np.testing.assert_allclose((root@ts[leg+'_foot'])[:3,3],f['feet_world'][leg],atol=1e-12)
 def test_all_vertices_ground_and_plan_envelope(self):
  bounds=np.max(np.abs(np.array(self.source['scene']['footprint'])),axis=0)
  for f in self.records:
   ts=independent_fk(f['q'])
   for link in ASSET['skeleton']['links']:
    m=ASSET['meshes'][link['mesh']];v=np.array(m['vertices_q']).reshape(-1,3)*m['quantization_m'];o=link['visual_origin'];T=ts[link['name']]@rigid(o['xyz'],o['rpy']);lv=v@T[:3,:3].T+T[:3,3];self.assertTrue((np.abs(lv[:,:2])<=bounds+1e-9).all());self.assertGreaterEqual(float(lv[:,2].min()+gait.HEIGHT),0)
 def test_stance_no_xy_slip(self):
  for a,b in zip(self.records,self.records[1:]):
   for leg in gait.LEGS:
    if a['stance'][leg] and b['stance'][leg]:np.testing.assert_array_equal(a['feet_world'][leg][:2],b['feet_world'][leg][:2])
 def test_joint_speed_sampled(self):
  q=np.array([list(f['q'].values())for f in self.records]);t=np.array([f['t']for f in self.records]);self.assertLess(float(np.max(np.abs(np.diff(q,axis=0)/np.diff(t)[:,None]))),20.07)
if __name__=='__main__':unittest.main()
