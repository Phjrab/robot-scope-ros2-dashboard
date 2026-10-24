import unittest,json,math
from pathlib import Path
import simulate_slalom as s
from core import polygon_collision
import numpy as np
P=Path(__file__).resolve().parent
class SlalomTests(unittest.TestCase):
 def test_cones_nonoverlapping(self):
  for name,cones in s.configs().items():
   for i,a in enumerate(cones):
    for b in cones[i+1:]:
     self.assertTrue(abs(a['xy'][0]-b['xy'][0])>=.26-1e-9 or abs(a['xy'][1]-b['xy'][1])>=.26-1e-9,(name,a,b))
 def test_cones_full_bases_inside_floor(self):
  floor=s.geo.FLOORS['floor_left_straight']
  for cones in s.configs().values():
   for c in cones:
    for dx in [-.13,.13]:
     for dy in [-.13,.13]:self.assertTrue(s.geo.contains(floor,[c['xy'][0]+dx,c['xy'][1]+dy]))
 def test_count_bound(self):
  self.assertEqual([len(x) for x in s.configs().values()],[0,3,5,5]);self.assertTrue(all(len(x)<=10 for x in s.configs().values()))
 def test_envelope_not_shrunk(self):self.assertEqual(s.BODY,[[-.405,-.28],[.405,-.28],[.405,.28],[-.405,.28]])
 def test_kinematic_speed(self):
  for n in s.configs():
   data=json.loads((P/'results'/f'{n}.json').read_text())
   for f in data['frames']:
    self.assertLessEqual(math.hypot(f['vx_world'],f['vy_world']),.1600001);self.assertEqual(f['w'],0.)
 def test_outcomes(self):
  for n in s.configs():
   data=json.loads((P/'results'/f'{n}.json').read_text());self.assertEqual(data['metrics']['outcome'],'SAFE_WAIT' if n=='blocked_5' else 'GOAL_REACHED');self.assertEqual(data['metrics']['contacts'],0)
 def test_repeat(self):
  data=json.loads((P/'results/reproducibility.json').read_text());self.assertTrue(all(x['identical_excluding_wall_time'] for x in data.values()))
 def test_dense_polygon_audit(self):
  data=json.loads((P/'results/audit.json').read_text());self.assertEqual(sum(x['polygon_floor_or_cone_violations'] for x in data.values()),0);self.assertGreater(data['slalom_5']['min_polygon_clearance_m'],.03)
 def test_real_weaving_required(self):
  data=json.loads((P/'results/audit.json').read_text());self.assertGreater(data['slalom_5']['straight_reference_contact_samples'],0)
  d=json.loads((P/'results/slalom_5.json').read_text());self.assertLess(d['metrics']['x_min'],.4);self.assertGreater(d['metrics']['x_max'],.6)
 def test_sweep_stops_mid_segment_contact(self):
  m=np.zeros((300,400),bool);m[100:104,30:34]=True
  self.assertFalse(s.safe((.3,1.6,math.pi/2),.4,.8,1.,m))
if __name__=='__main__':unittest.main()
