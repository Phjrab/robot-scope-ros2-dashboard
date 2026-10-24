import unittest,json,math
from pathlib import Path
import numpy as np
import simulate_flat as s
HERE=Path(__file__).resolve().parent

def independently_covered(pose,rectangles):
 # Exact interval union coverage for fixed axis-aligned body orientations.
 x,y,a=pose;hx=abs(math.cos(a))*.405+abs(math.sin(a))*.28;hy=abs(math.sin(a))*.405+abs(math.cos(a))*.28
 lo,hi=x-hx,x+hx;bottom,top=y-hy,y+hy
 cuts=sorted(set([bottom,top]+[v for r in rectangles.values() for v in (r[1],r[3]) if bottom<v<top]))
 for u,v in zip(cuts,cuts[1:]):
  mid=(u+v)/2;intervals=sorted((r[0],r[2]) for r in rectangles.values() if r[1]<=mid<=r[3]);edge=lo
  for left,right in intervals:
   if left<=edge+1e-10 and right>=edge:edge=max(edge,right)
  if edge<hi-1e-10:return False
 return True
class FlatTests(unittest.TestCase):
 def setUp(self):self.data={n:json.loads((HERE/'output'/f'{n}.json').read_text()) for n in ('in','parking','out','out_closed')}
 def test_outcomes(self):
  self.assertEqual(self.data['in']['metrics']['outcome'],'GOAL_REACHED');self.assertEqual(self.data['parking']['metrics']['outcome'],'POSITION_AND_HOLD_COMPLETE');self.assertEqual(self.data['out']['metrics']['outcome'],'GOAL_REACHED');self.assertEqual(self.data['out_closed']['metrics']['outcome'],'SAFE_WAIT')
 def test_swept_floor_independent(self):
  count=0
  for d in self.data.values():
   prev=d['scene']['start']
   for f in d['frames']:
    cur=f['pose'];steps=max(2,math.ceil(math.dist(prev[:2],cur[:2])/.001))
    for t in np.linspace(0,1,steps+1):
     p=[prev[i]+t*(cur[i]-prev[i]) for i in range(3)];self.assertTrue(independently_covered(p,d['scene']['rectangles']));count+=1
    prev=cur
  self.assertGreater(count,10000)
 def test_speed_and_acceleration(self):
  for d in self.data.values():
   old=np.zeros(2)
   for f in d['frames']:
    v=np.array([f['vx_world'],f['vy_world']]);self.assertLessEqual(np.linalg.norm(v),s.VMAX+1e-9);self.assertLessEqual(np.linalg.norm(v-old)/s.DT,s.AMAX+1e-9);old=v
 def test_parking_hold_and_containment(self):
  d=self.data['parking'];fs=[f for f in d['frames'] if f['state'] in ('ZERO_COMMAND_HOLD','POSITION_AND_HOLD_COMPLETE')];self.assertAlmostEqual(fs[-1]['t']-fs[0]['t'],5)
  for f in fs:self.assertEqual(f['pose'],fs[0]['pose']);self.assertEqual(f['vx_world'],0);self.assertEqual(f['vy_world'],0)
  self.assertTrue(d['metrics']['parking_full_body_contained']);self.assertFalse(d['metrics']['physical_stopping_evidence']);self.assertEqual(d['scene']['parking_sit'],'not simulated')
 def test_exit_is_proposed(self):
  d=self.data['out'];self.assertTrue(d['metrics']['whole_body_beyond_proposed_exit_plane']);self.assertGreater(d['metrics']['exit_body_rear_x'],8);self.assertIn('PROPOSED',d['scene']['opening']);self.assertFalse(d['metrics']['full_course_success'])
 def test_contiguous_parking_out_start(self):self.assertEqual(self.data['parking']['frames'][-1]['pose'],self.data['out']['scene']['start'])
 def test_closed_exit_no_apron(self):
  d=self.data['out_closed'];self.assertNotIn('PROPOSED_OUT_APRON',d['scene']['rectangles']);self.assertEqual(d['metrics']['path_length_m'],0)
if __name__=='__main__':unittest.main()
