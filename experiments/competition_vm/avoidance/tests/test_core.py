import unittest,sys,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import *
from simulate import Sensor,FOOTPRINT,rectangle

class CoreTests(unittest.TestCase):
 def setUp(self): self.static=np.zeros((30,60),bool); self.static[[0,-1],:]=1; self.static[:,[0,-1]]=1
 def test_dropout_never_clears(self):
  o=Occupancy(self.static); t=self.static.copy(); rectangle(t,2,1,2.3,2)
  s=Sensor(); o.update(s.observe(t,(1,1.5,0),0,1),(1,1.5,0),0)
  before=o.dynamic.copy(); receipt=o.last_receipt; o.update(s.observe(t,(1,1.5,0),.1,2,True),(1,1.5,0),.1)
  self.assertTrue(np.array_equal(before,o.dynamic)); self.assertEqual(receipt,o.last_receipt)
 def test_observed_clear_removes(self):
  o=Occupancy(self.static); t=self.static.copy(); rectangle(t,2,1,2.3,2); s=Sensor()
  o.update(s.observe(t,(1,1.5,0),0,1),(1,1.5,0),0); self.assertEqual(o.dynamic[15,20],1)
  o.update(s.observe(self.static,(1,1.5,0),.1,2),(1,1.5,0),.1); self.assertEqual(o.dynamic[15,20],0)
 def test_occluded_cell_not_clear(self):
  o=Occupancy(self.static); o.epoch='sensor-1'; o.dynamic[15,30]=1; o.observed[15,30]=0
  t=self.static.copy(); rectangle(t,2,1,2.3,2); s=Sensor(); o.update(s.observe(t,(1,1.5,0),.1,1),(1,1.5,0),.1)
  self.assertEqual(o.dynamic[15,30],1)
  obstacles,unknown=o.masks(3); self.assertTrue(unknown[15,30]); self.assertFalse(obstacles[15,30])
 def test_static_immutable(self):
  o=Occupancy(self.static)
  with self.assertRaises(ValueError): o.static[0,0]=False
 def test_duplicate_rewind_rejected(self):
  o=Occupancy(self.static); s=Sensor(); a=s.observe(self.static,(1,1.5,0),1,1)
  self.assertTrue(o.update(a,(1,1.5,0),1)); self.assertFalse(o.update(a,(1,1.5,0),1.1))
  b=s.observe(self.static,(1,1.5,0),.5,2); self.assertFalse(o.update(b,(1,1.5,0),.5))
 def test_stale_tf_rejected(self):
  o=Occupancy(self.static); a=Sensor().observe(self.static,(1,1.5,0),1,1)
  self.assertFalse(o.update(a,(1,1.5,0),1,tf_age=.5))
 def test_wrong_frame_clock_rejected(self):
  a=Scan('a',1,'1','FOREIGN_MONOTONIC','vm_laser',np.array([0]),np.array([2.]),8,1)
  self.assertFalse(Occupancy(self.static).update(a,(1,1.5,0),1))
 def test_hold_release_does_not_replay(self):
  a=CommandArbiter(); self.assertEqual(a.apply(.25,0,1,sensor_fresh=True,tf_fresh=True,signal_hold=True)[:2],(0,0))
  self.assertEqual(a.apply(.25,0,1,sensor_fresh=True,tf_fresh=True)[:2],(0,0))
  self.assertGreater(a.apply(.25,0,2,sensor_fresh=True,tf_fresh=True)[0],0)
 def test_multiple_constraints(self):
  a=CommandArbiter(); self.assertEqual(a.apply(.25,.5,1,sensor_fresh=True,tf_fresh=True,estop=True,signal_hold=True)[2],'ESTOP')
 def test_session_no_automatic_resume(self):
  s=Session(Goal('r','s','g',1,'a',(2,2))); self.assertFalse(s.check('b',1)); self.assertFalse(s.check('a',1))
 def test_rotational_sweep(self):
  mask=np.zeros((40,40),bool); mask[23,20]=True
  self.assertFalse(swept_safe((2.05,2.05,0),0,math.pi/2,1,[[.4,.1],[.4,-.1],[-.4,-.1],[-.4,.1]],mask,.1))
 def test_polygon_not_center_only(self):
  mask=np.zeros((40,40),bool); mask[20,22]=True
  self.assertTrue(polygon_collision((2.05,2.05,0),FOOTPRINT,mask,.1))
 def test_ground_slope_low_obstacle_unknown_self_invalid(self):
  points=[[1,0,.1,0],[1,0,.16,1],[1,0,.125,2],[0,0,0,3],[float('nan'),0,0,4]]
  out,count=ground_filter(points,plane=(-.1,0,1,0)); self.assertEqual(count,{'input':5,'invalid':1,'self':1,'range':0,'ground':1,'obstacle':1,'unknown':1})
 def test_ring_sample_preserves_all(self):
  pts=[[i,0,1,r] for r in range(16) for i in range(100)]
  out=ring_sample(pts,4); self.assertEqual(len(out),64); self.assertEqual(set(int(p[3]) for p in out),set(range(16)))
 def test_unknown_blocks_plan(self):
  o=np.zeros((20,30),bool); u=np.zeros_like(o); u[:,15]=1
  self.assertEqual(plan((o,u),np.ones_like(o),(1,1),(2,1),.1,.2),[])
 def test_mission_corridor_no_shortcut(self):
  o=np.zeros((30,60),bool); rectangle(o,2,1,2.5,2); allowed=np.ones_like(o); allowed[:10,:]=0; allowed[20:,:]=0
  self.assertEqual(plan((o,np.zeros_like(o)),allowed,(1,1.5),(4,1.5),.1,.31),[])

if __name__=='__main__': unittest.main()
