"""Synthetic unit fixtures only. No planner result or physics claim."""
import math,json,unittest,hashlib
import numpy as np
from review_helpers import independent_fk,rigid,ASSET,HERE,gait

def traces():
 times=np.arange(0,12.0001,.1)
 def make(fn):return {'frames':[{'t':float(t),'pose':list(fn(float(t)))}for t in times]}
 def pause(t):
  u=t if t<=5 else 5 if t<=7 else t-2
  return (1.5*math.sin(.08*u),1.5*(1-math.cos(.08*u)),.08*u)
 return {'gradual_arc':make(lambda t:(1.5*math.sin(.10*t),1.5*(1-math.cos(.10*t)),.10*t)),
 'sideways_forward':make(lambda t:(.12*t,.12*math.sin(.5*t),.25*math.sin(.2*t))),
 'curve_pause_resume':make(pause),
 'turn_in_place':make(lambda t:(0,0,.25*t))}

class SyntheticCurves(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.cases={};cls.metrics={}
  for name,trace in traces().items():
   r=gait.build(trace,ASSET);cls.cases[name]=r;cls.metrics[name]=gait.validate(r,ASSET)
  (HERE/'review/synthetic_curve_metrics.json').write_text(json.dumps({'gait_sha256':hashlib.sha256((HERE/'gait.py').read_bytes()).hexdigest(),'type':'SYNTHETIC_UNIT_FIXTURES_NOT_MISSION','cases':cls.metrics},indent=2))
 def test_independent_fk_targets(self):
  for r in self.cases.values():
   for f in r:
    ts=independent_fk(f['q']);root=rigid([*f['pose'][:2],gait.HEIGHT],[0,0,f['pose'][2]])
    for leg in gait.LEGS:np.testing.assert_allclose((root@ts[leg+'_foot'])[:3,3],f['feet_world'][leg],atol=1e-12)
 def test_joint_ranges(self):
  for r in self.cases.values():
   for f in r:
    for j in ASSET['skeleton']['joints']:
     if j['type']=='revolute':self.assertGreaterEqual(f['q'][j['name']],j['limit']['lower']);self.assertLessEqual(f['q'][j['name']],j['limit']['upper'])
 def test_ground_nonpenetration(self):
  for m in self.metrics.values():self.assertGreater(m['min_mesh_ground_clearance_m'],0)
 def test_stance_anchor_slip_zero(self):
  for r in self.cases.values():
   for a,b in zip(r,r[1:]):
    for leg in gait.LEGS:
     if a['stance'][leg] and b['stance'][leg]:np.testing.assert_array_equal(a['feet_world'][leg][:2],b['feet_world'][leg][:2])
 def test_pause_all_stance_and_frozen(self):
  paused=[f for f in self.cases['curve_pause_resume']if 5.1<f['t']<6.9]
  for f in paused:self.assertTrue(all(f['stance'].values()));self.assertEqual(f['q'],paused[0]['q'])
 def test_default_envelope_characterization(self):
  # Characterization guard is intentionally broader than the previous planner.
  # This does not authorize reusing an unverified planner footprint.
  for m in self.metrics.values():
   b=np.max(np.abs(np.array(m['articulated_local_bounds_m'])),axis=0);self.assertLess(b[0],.46);self.assertLess(b[1],.32)

if __name__=='__main__':unittest.main()
