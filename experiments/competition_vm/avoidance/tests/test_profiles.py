import unittest,sys,copy
from pathlib import Path
import yaml
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from profiles import build,assert_effective,MPPI,RPP
class ProfileTests(unittest.TestCase):
 def setUp(self): self.base=yaml.safe_load((root.parents[2]/'config/nav2_params_go2_humble.yaml').read_text())
 def test_versioned_mppi(self):
  p=build(self.base,'MPPI','polygon'); self.assertEqual(p['controller_server']['ros__parameters']['FollowPath']['plugin'],MPPI)
  self.assertTrue(assert_effective(p,p)); self.assertNotEqual(self.base,p)
 def test_silent_rpp_overwrite_rejected(self):
  p=build(self.base,'MPPI'); actual=copy.deepcopy(p); actual['controller_server']['ros__parameters']['FollowPath']['plugin']=RPP
  with self.assertRaises(ValueError):assert_effective(p,actual)
 def test_layer_or_footprint_overwrite_rejected(self):
  p=build(self.base,'MPPI','polygon'); actual=copy.deepcopy(p); actual['global_costmap']['global_costmap']['ros__parameters']['footprint']='[]'
  with self.assertRaises(ValueError):assert_effective(p,actual)
 def test_no_hardware_topics(self):
  p=build(self.base,'RPP'); text=yaml.safe_dump(p)
  self.assertNotIn('/utlidar',text)
  self.assertNotIn('/robot_scope',text)
  self.assertNotIn('/Odometry',text)
  self.assertNotIn('robot_scope_navigation_runtime',p)
if __name__=='__main__':unittest.main()
