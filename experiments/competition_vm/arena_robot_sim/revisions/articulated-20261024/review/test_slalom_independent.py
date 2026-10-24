"""Additional final left-slalom artifact audit; source root is explicit for separated clones."""
import unittest,json,sys,math,os,hashlib
from pathlib import Path
import numpy as np
from test_independent_review import ASSET,HERE,independent_fk,rigid
import test_independent_review as original_review
sys.path.insert(0,str(HERE));import gait
SOURCE_ROOT=Path(os.environ.get('ARENA_SLALOM_SOURCE_ROOT',str(gait.ROOT)))

class SlalomReview(unittest.TestCase):
 def setUp(self):
  self.records={n:json.loads((HERE/'output'/f'{n}_joints.json').read_text())['records']for n in ('slalom_5','blocked_5')}
  self.sources={n:json.loads((SOURCE_ROOT/'experiments/competition_vm/arena_robot_sim/revisions/left_slalom_20261024/results'/f'{n}.json').read_text())for n in self.records}
 test_joint_limits=original_review.Review.test_joint_limits
 test_fk_and_mesh_floor=original_review.Review.test_fk_and_mesh_floor
 test_stance_horizontal_no_slip=original_review.Review.test_stance_horizontal_no_slip
 test_no_unbounded_joint_jump=original_review.Review.test_no_unbounded_joint_jump
 def test_interpolated_source_poses_unchanged(self):
  for n,records in self.records.items():
   src=self.sources[n];t=np.array([f['t']for f in src['frames']]);p=np.array([f['pose']for f in src['frames']]);p[:,2]=np.unwrap(p[:,2])
   for f in records:np.testing.assert_allclose(f['pose'],[np.interp(f['t'],t,p[:,j])for j in range(3)],atol=1e-12)
 def test_source_hash_identity(self):
  for n in self.records:
   f=SOURCE_ROOT/'experiments/competition_vm/arena_robot_sim/revisions/left_slalom_20261024/results'/f'{n}.json';d=json.loads((HERE/'output'/f'{n}_joints.json').read_text());self.assertEqual(hashlib.sha256(f.read_bytes()).hexdigest(),d['validation']['trace_sha256'])
 def test_stationary_all_stance_and_frozen(self):
  r=self.records['blocked_5']
  for f in r:self.assertTrue(all(f['stance'].values()));self.assertEqual(f['q'],r[0]['q'])
 def test_articulated_vertices_fit_replanned_footprint(self):
  for n,records in self.records.items():
   bounds=np.max(np.abs(np.array(self.sources[n]['scene']['footprint'])),axis=0)
   for f in records:
    ts=independent_fk(f['q'])
    for link in ASSET['skeleton']['links']:
     m=ASSET['meshes'][link['mesh']];v=np.array(m['vertices_q']).reshape(-1,3)*m['quantization_m'];o=link['visual_origin'];T=ts[link['name']]@rigid(o['xyz'],o['rpy']);local=v@T[:3,:3].T+T[:3,3];self.assertTrue((np.abs(local[:,:2])<=bounds+1e-9).all())

if __name__=='__main__':unittest.main()
