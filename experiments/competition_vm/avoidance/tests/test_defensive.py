import unittest,sys,math
from pathlib import Path
from dataclasses import replace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import *
from simulate import Sensor
class DefensiveTests(unittest.TestCase):
 def test_invalid_command_is_stop(self):
  for field in ('v','w','cap','sequence'):
   for bad in (float('nan'),float('inf'),-float('inf')):
    kw=dict(v=.25,w=.2,cap=.25,sequence=1,sensor_fresh=True,tf_fresh=True);kw[field]=bad
    self.assertEqual(CommandArbiter().apply(**kw)[:2],(0.,0.))
 def test_bad_scan_never_mutates(self):
  grid=np.zeros((30,60),bool);s=Sensor().observe(grid,(1,1,0),1,1)
  for field,bad in [('receipt_s',float('nan')),('sequence',1.5),('sequence',-1),('sequence',True),('source_stamp_ns','-1'),('source_stamp_ns',str(2**63)),('epoch','')]:
   o=Occupancy(grid);self.assertFalse(o.update(replace(s,**{field:bad}),(1,1,0),1));self.assertEqual(o.last_receipt,-np.inf);self.assertIsNone(o.epoch)
 def test_bad_planner_inputs(self):
  z=np.zeros((30,60),bool)
  for point in [(-.01,1),(100,1),(1,-.01),(1,100),(float('nan'),1)]:
   self.assertEqual(plan((z,z),~z,point,(2,1),.1,.3),[])
   self.assertEqual(plan((z,z),~z,(1,1),point,.1,.3),[])
  for res in (0,-1,float('nan')):self.assertEqual(plan((z,z),~z,(1,1),(2,1),res,.3),[])
 def test_invalid_sweep_fails_closed(self):
  self.assertFalse(swept_safe((1,1,0),float('nan'),0,.1,[[-1,-1],[1,-1],[1,1]],np.zeros((30,60),bool),.1))
 def test_offset_map_obstacle_all_observations_kept(self):
  from simulate import scene,truth_at,Sensor
  static,allowed,goal,pose=scene('map_misalignment',0);truth=truth_at(static,'map_misalignment',0,0)
  self.assertTrue(np.any(truth & ~static));o=Occupancy(static,.1)
  self.assertTrue(o.update(Sensor().observe(truth,pose,0,0),pose,0))
  occupied,unknown=o.masks(0)
  self.assertTrue(np.any(occupied & ~static));self.assertTrue(np.all(occupied[static]))
 def test_retired_epoch_cannot_clear(self):
  from simulate import rectangle
  z=np.zeros((30,60),bool);truth=z.copy();rectangle(truth,2,1,2.3,2)
  o=Occupancy(z);sensor=Sensor();old=sensor.observe(z,(1,1.5,0),1,100)
  self.assertTrue(o.update(old,(1,1.5,0),1))
  new=replace(sensor.observe(truth,(1,1.5,0),2,1),epoch='sensor-2')
  self.assertTrue(o.update(new,(1,1.5,0),2));self.assertEqual(o.dynamic[15,20],1)
  self.assertFalse(o.update(replace(old,receipt_s=2.1),(1,1.5,0),2.1))
  self.assertEqual(o.dynamic[15,20],1);self.assertEqual(o.epoch,'sensor-2')
 def test_grid_validation(self):
  for r in (0,-1,float('nan')):
   with self.assertRaises(ValueError):Occupancy(np.zeros((2,2)),r)
if __name__=='__main__':unittest.main()

class TransformTests(unittest.TestCase):
 def test_metre_transform_ring_preserved(self):
  t=np.array([[0,-1,0,1],[1,0,0,2],[0,0,1,3],[0,0,0,1]])
  out=transform_cloud([[1,0,0,15]],t,source_kind='raw',source_frame='lidar',target_frame='odom',tf_age=.1)
  np.testing.assert_allclose(out,[[1,3,3,15]])
 def test_registered_double_transform_rejected(self):
  with self.assertRaises(ValueError):transform_cloud([[1,0,0,15]],np.eye(4),source_kind='registered',source_frame='odom',target_frame='base',tf_age=.1)
 def test_stale_transform_rejected(self):
  with self.assertRaises(ValueError):transform_cloud([[1,0,0,15]],np.eye(4),source_kind='raw',source_frame='lidar',target_frame='base',tf_age=.5)
