import unittest,math
import simulate_curved as c
class Target(unittest.TestCase):
 def test_straight_exact_lookahead(self):
  q=c.target_at([[0,0,1],[0,1,1]],(0,.25,1),.05);self.assertAlmostEqual(q[1],.30)
 def test_corner_arclength(self):
  q=c.target_at([[0,0,1],[0,1,1],[1,1,1]],(0,.95,1),.1);self.assertAlmostEqual(q[0],.05);self.assertAlmostEqual(q[1],1)
 def test_clamps_goal(self):self.assertEqual(c.target_at([[0,0,1],[0,1,1]],(0,.99,1),.1),[0.,1.,1.])
 def test_duplicate_segment_finite(self):
  q=c.target_at([[0,0,1],[0,0,1],[0,1,1]],(0,0,1),.05);self.assertTrue(all(math.isfinite(x) for x in q))
 def test_body_and_margin_unchanged(self):self.assertEqual(c.CLEARANCE,.03);self.assertEqual(c.BODY[2],[.405,.28])
if __name__=='__main__':unittest.main()
