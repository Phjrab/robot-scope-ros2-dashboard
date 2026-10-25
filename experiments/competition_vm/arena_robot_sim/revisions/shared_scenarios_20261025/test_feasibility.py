"""Compact regression tests, no renderer, ROS or robot access."""
import copy
import json
import unittest
import numpy as np
import feasibility as f
from export_fixtures import scenes

class FeasibilityTests(unittest.TestCase):
    def test_fixed_inputs_and_witness_hashes(self):
        all_scenes=scenes()
        for name in ('empty','feasible1','feasible2','original_tight5','open_diagnostic'):
            with self.subTest(name=name):
                scene=all_scenes[name]
                w=json.loads((f.HERE/'witnesses'/f'{name}.json').read_text())
                self.assertEqual(w['input_sha256'],f.canonical_hash(scene))
                self.assertEqual(w['poses'][0],scene['start'])
                self.assertEqual(w['poses'][-1],scene['goal'])
                self.assertTrue(f.sweep(w['poses'],scene)['certified'])
    def test_actual_cone_base_contact_rejected(self):
        s=scenes()['feasible1']
        # Base right x=.31; body left at x=.31: exact closed contact.
        p=[.59,2.5,np.pi/2]
        self.assertFalse(f.search_valid([p],s)[0])
        self.assertFalse(f.sweep([p,p],s)['certified'])
    def test_segment_tunnel_rejected(self):
        s=scenes()['feasible1'];p=[.5,1.5,np.pi/2];q=[.5,3.5,np.pi/2]
        self.assertFalse(f.sweep([p,q],s)['certified'])
    def test_forbidden_polygon_independent(self):
        s=copy.deepcopy(scenes()['empty'])
        s['forbidden_polygons'].append([[.3,2.4],[.7,2.4],[.7,2.6],[.3,2.6]])
        self.assertFalse(f.sweep([s['start'],s['goal']],s)['certified'])
    def test_full_polygon_not_circle_proxy(self):
        s=scenes()['empty']
        self.assertTrue(f.search_valid([s['start']],s)[0])
        self.assertFalse(f.search_valid([s['start']],s,np.hypot(.405,.28))[0])
    def test_scene_hash_changes_on_geometry_change(self):
        s=scenes()['original_tight5'];other=copy.deepcopy(s)
        other['cones'][0]['xy'][0]+=.001
        self.assertNotEqual(f.canonical_hash(s),f.canonical_hash(other))
    def test_report_certification_not_native_execution(self):
        r=json.loads((f.HERE/'feasibility_results.json').read_text())
        self.assertEqual(r['results']['original_tight5']['status'],'CERTIFIED_FEASIBLE_WITNESS')
        self.assertEqual(r['results']['blocked']['status'],'NO_WITNESS_WITHIN_BOUNDS')
        self.assertIn('NOT_NATIVE_NAV2',r['scope'])

if __name__=='__main__':unittest.main()
