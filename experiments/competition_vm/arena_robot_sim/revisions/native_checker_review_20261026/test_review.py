import json, math, os, unittest
from pathlib import Path
import review

class GeometryReview(unittest.TestCase):
    def test_disjoint(self):
        self.assertFalse(review.clip([[0,0],[1,0],[1,1],[0,1]],[2,2,3,3]))
    def test_contained_cell(self):
        self.assertAlmostEqual(review.area(review.clip([[0,0],[2,0],[2,2],[0,2]],[.5,.5,1,1])),.25)
    def test_closed_contact(self):
        self.assertTrue(review.clip([[0,0],[1,0],[1,1],[0,1]],[1,.3,2,.6]))
    def test_rotated(self):
        self.assertAlmostEqual(review.area(review.clip([[0,1],[1,0],[2,1],[1,2]],[.5,.5,1.5,1.5])),1)
    def test_unknown_policy(self):
        c={'id':'x','pose':[1,1,0],'raw_cells':[[50,50,255]]}
        self.assertTrue(review.case_geometry(c)['collision'])
        self.assertFalse(review.case_geometry(c|{'allow_unknown':True})['collision'])
    def test_positive_corridor(self):
        c={'id':'x','pose':[.5,2,math.pi/2],'wall_columns':[7,42]}
        self.assertFalse(review.case_geometry(c)['collision'])
        self.assertGreater(2*review.prior.RC,.68)
    def test_frozen_cases_independent_match(self):
        r=json.loads((review.HERE/'result.json').read_text())
        self.assertEqual(len(r['cases']),16)
        self.assertTrue(all(c['fixed_matches_independent_geometry'] for c in r['cases']))
    def test_rotation_endpoints_middle(self):
        r=json.loads((review.HERE/'result.json').read_text())
        c=next(c for c in r['cases'] if c['id']=='rotation_endpoints_clear')
        self.assertEqual(c['primitive_geometry'],[False,True,False])
        self.assertTrue(c['stock_primitive_valid']); self.assertFalse(c['fixed_primitive_valid'])
    def test_returned_segment_not_endpoints_only(self):
        r=json.loads((review.HERE/'result.json').read_text())['returned_segment'];s=r['samples']
        self.assertFalse(s[0]['grid_intersects']); self.assertFalse(s[-1]['grid_intersects'])
        self.assertEqual(sum(x['grid_intersects'] for x in s),13)
        self.assertFalse(any(x['cone_intersects'] for x in s))
        self.assertEqual([m['occupancy'] for m in r['maps']],[100,100])
        self.assertLess(r['maps'][0]['receipt_monotonic'],r['path_receipt_monotonic'])
        self.assertGreater(r['maps'][1]['receipt_monotonic'],r['path_receipt_monotonic'])
    @unittest.skipUnless(os.getenv('D0_R6_RAW'),'private retained artifact not supplied')
    def test_private_reconstruction(self):
        r=review.review(Path(os.environ['D0_R6_EVIDENCE']),Path(os.environ['D0_R6_RAW']),Path(os.environ['D0_R6_ZIP']))
        self.assertEqual(r,json.loads((review.HERE/'result.json').read_text()))

if __name__=='__main__': unittest.main()
