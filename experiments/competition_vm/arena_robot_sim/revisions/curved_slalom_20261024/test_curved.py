from pathlib import Path
import unittest,json,math,numpy as np
import simulate_curved as c
P=Path(__file__).resolve().parent/'results/final_regressions'
def read(n):return json.loads((P/f'{n}.json').read_text())
class Regression(unittest.TestCase):
 def test_footprint_not_reduced(self):self.assertEqual(c.BODY,[[-.405,-.28],[.405,-.28],[.405,.28],[-.405,.28]]);self.assertEqual(c.CLEARANCE,.03)
 def test_open_goal_stopped(self):
  d=read('open_normal');self.assertEqual(d['metrics']['outcome'],'GOAL_REACHED');self.assertTrue(all(abs(d['frames'][-1][k])<1e-9 for k in ['vx_world','vy_world','w']))
 def test_velocity_and_yaw_rate_limits(self):
  for f in read('open_normal')['frames']:self.assertLessEqual(math.hypot(f['vx_world'],f['vy_world']),.1600001);self.assertLessEqual(abs(f['w']),.1800001)
 def test_normal_slew_limits(self):
  prev=np.zeros(3)
  for f in read('open_normal')['frames']:
   v=np.array([f['vx_world'],f['vy_world'],f['w']]);self.assertLessEqual(np.linalg.norm(v[:2]-prev[:2]),.020001);self.assertLessEqual(abs(v[2]-prev[2]),.035001);prev=v
 def test_no_emergency_override_normal(self):self.assertEqual(read('open_normal')['metrics']['emergency_slew_overrides'],0)
 def test_goal_and_pose_timestamps_monotonic(self):
  frames=read('open_normal')['frames'];self.assertTrue(all(a['t']<b['t'] and a['pose_t']<b['pose_t'] for a,b in zip(frames,frames[1:])))
 def test_dropout_stops(self):
  d=read('open_dropout');self.assertEqual(d['metrics']['outcome'],'SAFE_WAIT')
  for f in d['frames']:
   if not f['sensor_fresh']:self.assertEqual([f['vx_world'],f['vy_world'],f['w']],[0.,0.,0.])
 def test_delayed_input_rejected(self):self.assertGreater(read('open_delay')['metrics']['rejected_delayed_samples'],0)
 def test_receiver_and_source_age_separate(self):
  for n in ['open_normal','open_delay','open_dropout']:
   for f in read(n)['frames']:
    if f['sensor_fresh']:self.assertLessEqual(f['receiver_age_s'],.250001);self.assertLessEqual(f['source_age_s'],.250001)
 def test_blocked_safe_wait(self):self.assertEqual(read('blocked_5')['metrics']['outcome'],'SAFE_WAIT');self.assertEqual(read('blocked_5')['metrics']['path_length_m'],0.)
 def test_shared_open_fixture(self):self.assertEqual(read('open_baseline')['scene']['cones'],read('open_normal')['scene']['cones'])
 def test_qualification_and_clearance(self):
  a=json.loads((P/'COMPARISON.json').read_text());self.assertTrue(all(x['geometry']['pass_geometry'] for x in a.values()));self.assertGreaterEqual(a['open_normal']['geometry']['min_polygon_clearance_m'],.03)
 def test_no_collision_any_case(self):
  for n in ['open_normal','open_delay','open_dropout','blocked_5']:self.assertEqual(read(n)['metrics']['contacts'],0)
 def test_metrics_do_not_claim_native(self):self.assertIn('NOT PHYSICAL',read('open_normal')['scene']['kinematics'])
if __name__=='__main__':unittest.main()
