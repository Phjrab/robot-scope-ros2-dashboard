import unittest,json,math
import numpy as np
import simulate as s
class GeometryTests(unittest.TestCase):
 def test_actual_model_envelope(self):
  b=json.loads((s.ROOT/'rendering/standing_bounds.json').read_text())
  self.assertGreaterEqual(.358,max(abs(b['min_xyz'][0]),abs(b['max_xyz'][0])));self.assertGreaterEqual(.162,max(abs(b['min_xyz'][1]),abs(b['max_xyz'][1])))
 def test_cone_mesh_dimensions(self):
  c=dict(xy=[2,3],radius_m=.12,height_m=.32,base_side_m=.26,base_height_m=.04)
  v=np.array(s.cone_mesh(c));self.assertAlmostEqual(v[:,:,2].max(),.32);self.assertAlmostEqual(v[:,:,0].max(),2.13)
 def test_triangle_raycast_base(self):
  c=dict(xy=[2,3],radius_m=.12,height_m=.32,base_side_m=.26,base_height_m=.04)
  r,p=s.raycast(np.array(s.cone_mesh(c)),[1,3,0]);self.assertAlmostEqual(r[180],.87,places=8);self.assertTrue(any(x[3]==0 for x in p))
 def test_wall_occludes_cone(self):
  c=dict(xy=[2,3],radius_m=.12,height_m=.32,base_side_m=.26,base_height_m=.04)
  wall=s.quad([1.5,2,0],[1.5,4,0],[1.5,4,.6],[1.5,2,.6]);r,p=s.raycast(np.array(wall+s.cone_mesh(c)),[1,3,0]);self.assertAlmostEqual(r[180],.5)
 def test_arena_and_terrain(self):
  m=s.static_grid();self.assertFalse(m[int(3/s.RES),int(7/s.RES)]);self.assertTrue(m[int(3/s.RES),int(4/s.RES)]);self.assertTrue(m[int(3/s.RES),int(3.3/s.RES)])
 def test_final_records(self):
  for name in ['empty','cone_detour','blocked']:
   r=json.loads((s.ROOT/'results'/f'{name}.json').read_text());self.assertEqual(r['metrics']['contacts'],0);self.assertTrue(r['metrics']['pass'],name)
 def test_straight_reference_is_obstructed(self):
  r=json.loads((s.ROOT/'results/cone_detour.json').read_text());self.assertGreater(r['metrics']['straight_reference_contact_samples'],0)
if __name__=='__main__':unittest.main()
