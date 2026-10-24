"""D0 geometry, policy, occlusion and reproducibility regressions."""
import importlib.util,json,math,sys,unittest,hashlib
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import regression as r

class RegressionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.static=r.old.static_grid();cls.strict=r.allowed_grid(cls.static,True)
 def test_counts_and_fixed_geometry(self):
  cases=list(r.scenarios());self.assertTrue({0,1,2,5,10}.issubset({len(c['cones']) for c in cases}));self.assertTrue(all(len(c['cones'])<=10 for c in cases))
  for c in cases:
   self.assertEqual(c['seed'],20261024)
   for o in c['cones']:self.assertEqual((o['base_side_m'],o['radius_m'],o['height_m']),(.26,.12,.32))
  self.assertEqual(r.BODY,r.old.FOOTPRINT);self.assertEqual(r.START,[5.99,1.65,math.pi/2]);self.assertEqual(r.GOAL,[5.99,4.35])
 def test_strict_adds_parking_without_removing_static_obstacles(self):
  self.assertTrue(np.all(self.strict[self.static]));self.assertTrue(self.strict[75,175]);self.assertFalse(self.static[75,175])
 def test_whole_footprint_parking_not_center_only(self):
  pose=(6.4,3.,math.pi/2)
  self.assertLess(pose[0],6.5)
  check=r.geometry_checks(pose,[],True);self.assertTrue(check['forbidden_parking'])
  self.assertTrue(r.polygon_collision(pose,r.BODY,self.strict,r.old.RES))
 def test_legacy_record_is_not_relabelled_success(self):
  a=r.historical_audit()['cone_detour'];self.assertGreater(a['strict_parking_violation_frame_samples'],0);self.assertGreater(a['max_footprint_x_intrusion_m'],.07)
 def test_segment_crossing_clearance_zero(self):self.assertEqual(r.edge_distance([0,0],[1,1],[0,1],[1,0]),0.)
 def test_cone_center_inside_body_is_contact(self):
  self.assertTrue(r.geometry_checks((5.99,3.,math.pi/2),[r.cone(1,5.99,3.)],False)['physical_contacts'])
 def test_known_static_cone_stays_in_collision(self):
  c=r.cone(1,5.99,3.);known=r.raster_cones(self.static,[c]);self.assertTrue(r.polygon_collision((5.99,3.,0),r.BODY,known,r.old.RES))
 def test_intertick_collision_detected(self):
  c=r.cone(1,5.99,3.);mask=r.raster_cones(self.static,[c]);start=(5.99,2.4,math.pi/2);end=(5.99,3.6,math.pi/2)
  self.assertFalse(r.polygon_collision(start,r.BODY,mask,r.old.RES));self.assertFalse(r.polygon_collision(end,r.BODY,mask,r.old.RES))
  self.assertFalse(r.swept_safe(start,1.2,0,1.,r.BODY,mask,r.old.RES))
 def test_occluded_rear_cone_does_not_erase_front(self):
  cones=[r.cone(1,5.99,2.65),r.cone(2,5.99,3.25)]
  ranges,_=r.old.raycast(r.triangles(cones),r.START)
  # ANGLES[180] is forward relative to +Y robot heading. First base at2.52.
  self.assertAlmostEqual(ranges[180],2.52-r.START[1],places=8)
 def test_terrain_added_as_first_hit_occluder(self):
  self.assertGreater(len(r.triangles([])),len(r.old.mesh([])))
 def test_delayed_scan_does_not_refresh_source_age(self):
  p=HERE/'fixtures/delayed_offset_1__legacy_parking_allowed.json'
  self.assertTrue(p.exists(),'required compact fixture missing')
  doc=json.loads(p.read_text());self.assertEqual(len(doc['frames']),doc['source_frame_count']);self.assertEqual(len(doc['source_file_sha256']),64)
  if (HERE/doc['source_file']).exists():self.assertEqual(hashlib.sha256((HERE/doc['source_file']).read_bytes()).hexdigest(),doc['source_file_sha256'])
  self.assertGreater(doc['metrics']['rejected_scans'],0)
  for f in doc['frames']:
   if f['t']>=1.1:self.assertEqual((f['v'],f['w']),(0.,0.));self.assertFalse(f['sensor_fresh'])
 def test_dropout_hold_then_fresh_resume(self):
  p=HERE/'fixtures/dropout_offset_1__legacy_parking_allowed.json'
  self.assertTrue(p.exists(),'required compact fixture missing')
  doc=json.loads(p.read_text());self.assertEqual(len(doc['frames']),doc['source_frame_count']);self.assertEqual(len(doc['source_file_sha256']),64)
  if (HERE/doc['source_file']).exists():self.assertEqual(hashlib.sha256((HERE/doc['source_file']).read_bytes()).hexdigest(),doc['source_file_sha256'])
  for f in doc['frames']:
   if 1.1<=f['t']<4.2:self.assertEqual((f['v'],f['w']),(0.,0.))
  self.assertTrue(any(f['t']>=4.2 and f['v']>0 for f in doc['frames']))
 def test_generated_repeat_and_safety_when_present(self):
  p=HERE/'results/summary.json'
  self.assertTrue(p.exists(),'required run summary missing')
  d=json.loads(p.read_text());self.assertTrue(d['cases'])
  for c in d['cases']:
   self.assertTrue(c['reproducible'],c['case']);self.assertTrue(c['metrics']['safety_pass'],c['case'])
   self.assertEqual(c['metrics']['swept_grid_contact_samples'],0)
   self.assertEqual(c['metrics']['exact_cone_fence_contact_samples'],0)
   if c['policy']=='strict_no_parking':self.assertEqual(c['metrics']['forbidden_parking_samples'],0)

if __name__=='__main__':unittest.main()
