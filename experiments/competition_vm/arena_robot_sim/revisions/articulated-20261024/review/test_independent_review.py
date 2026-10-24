"""Independent artifact/FK checks, no robot connection or renderer required."""
import unittest,json,sys,math
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE));import gait
ASSET=json.loads(gait.ASSET.read_text())

def rigid(xyz,rpy):
 r,p,y=rpy
 Rx=np.array([[1,0,0],[0,math.cos(r),-math.sin(r)],[0,math.sin(r),math.cos(r)]])
 Ry=np.array([[math.cos(p),0,math.sin(p)],[0,1,0],[-math.sin(p),0,math.cos(p)]])
 Rz=np.array([[math.cos(y),-math.sin(y),0],[math.sin(y),math.cos(y),0],[0,0,1]])
 T=np.eye(4);T[:3,:3]=Rz@Ry@Rx;T[:3,3]=xyz;return T

def independent_fk(q):
 ts={'base':np.eye(4)}
 for j in ASSET['skeleton']['joints']:
  o=j['origin'];R=np.eye(4)
  if j['type']=='revolute':R=rigid([0,0,0],np.asarray(j['axis'])*q[j['name']])
  ts[j['child']]=ts[j['parent']]@rigid(o['xyz'],o['rpy'])@R
 return ts

class Review(unittest.TestCase):
 def setUp(self):
  self.records={n:json.loads((HERE/'output'/f'{n}_joints.json').read_text())['records']for n in ('cone_detour','blocked')}
 def test_joint_limits(self):
  for records in self.records.values():
   for f in records:
    for j in ASSET['skeleton']['joints']:
     if j['type']=='revolute':self.assertGreaterEqual(f['q'][j['name']],j['limit']['lower']);self.assertLessEqual(f['q'][j['name']],j['limit']['upper'])
 def test_fk_and_mesh_floor(self):
  self.min_ground=float('inf')
  for records in self.records.values():
   for f in records:
    ts=independent_fk(f['q']);root=rigid([*f['pose'][:2],gait.HEIGHT],[0,0,f['pose'][2]])
    for leg,target in f['feet_world'].items():np.testing.assert_allclose((root@ts[leg+'_foot'])[:3,3],target,atol=1e-12)
    for link in ASSET['skeleton']['links']:
     m=ASSET['meshes'][link['mesh']];v=np.array(m['vertices_q']).reshape(-1,3)*m['quantization_m'];o=link['visual_origin'];T=root@ts[link['name']]@rigid(o['xyz'],o['rpy']);z=(v@T[:3,:3].T+T[:3,3])[:,2];self.assertGreaterEqual(float(z.min()),0)
 def test_saved_trace_pose_integrity(self):
  for name,records in self.records.items():
   original=json.loads((HERE.parents[1]/'results'/f'{name}.json').read_text())['frames']
   for f in original:
    rec=min(records,key=lambda r:abs(r['t']-f['t']));self.assertAlmostEqual(rec['t'],f['t'],places=10);np.testing.assert_allclose(rec['pose'],f['pose'],atol=1e-12)
 def test_static_blocked_trace_all_stance(self):
  r=self.records['blocked']
  for f in r:
   self.assertTrue(all(f['stance'].values()));self.assertEqual(f['q'],r[0]['q']);self.assertEqual(f['feet_world'],r[0]['feet_world'])
 def test_stance_horizontal_no_slip(self):
  for records in self.records.values():
   for a,b in zip(records,records[1:]):
    for leg in gait.LEGS:
     if a['stance'][leg] and b['stance'][leg]:np.testing.assert_array_equal(a['feet_world'][leg][:2],b['feet_world'][leg][:2])
 def test_moving_trace_actual_joint_change(self):
  q=np.array([list(f['q'].values())for f in self.records['cone_detour']]);self.assertGreater(float(np.ptp(q,axis=0).max()),.1)
 def test_mid_route_pause_ground_stance(self):
  trace={'frames':[{'t':i*.1,'pose':[min(i*.01,.3) if i<=50 else .3+(i-50)*.01,0,0]}for i in range(101)]}
  r=gait.build(trace,ASSET);pause=[f for f in r if 3.1<f['t']<4.9]
  for f in pause:self.assertTrue(all(f['stance'].values()),f['t']);self.assertEqual(f['q'],pause[0]['q'])
 def test_no_unbounded_joint_jump(self):
  for records in self.records.values():
   q=np.array([list(f['q'].values())for f in records]);t=np.array([f['t']for f in records]);self.assertLess(float(np.max(np.abs(np.diff(q,axis=0)/np.diff(t)[:,None]))),20.07)

if __name__=='__main__':unittest.main()
