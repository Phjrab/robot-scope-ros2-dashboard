import math
import unittest
import numpy as np
from collision import Snapshot, polygon_collision

BOX = [[-.1, -.1], [.1, -.1], [.1, .1], [-.1, .1]]

class ClosedCells(unittest.TestCase):
    def test_left_contact_includes_previous_cell(self):
        a=np.zeros((100,100),bool);a[50,39]=1
        self.assertTrue(Snapshot(a,.01).collides((.5,.5,0),BOX))
    def test_bottom_contact_includes_previous_cell(self):
        a=np.zeros((100,100),bool);a[39,50]=1
        self.assertTrue(Snapshot(a,.01).collides((.5,.5,0),BOX))
    def test_upper_roundoff_contact(self):
        a=np.zeros((200,200),bool);a[50,116]=1
        self.assertTrue(Snapshot(a,.01).collides((1.06,.5,0),BOX))
    def test_rotated_contact(self):
        a=np.zeros((200,200),bool);a[99,100]=1
        box=[[0.,0.],[.2,0.],[.2,.2],[0.,.2]]
        self.assertTrue(Snapshot(a,.01).collides((1.,1.,math.pi/4),box))
    def test_microscopic_gap_conservative(self):
        a=np.zeros((100,100),bool);a[50,39]=1
        self.assertTrue(Snapshot(a,.01).collides((.5+1e-13,.5,0),BOX))
    def test_positive_resolved_gap_is_clear(self):
        a=np.zeros((100,100),bool);a[50,39]=1
        self.assertFalse(Snapshot(a,.01).collides((.5+1e-7,.5,0),BOX))
    def test_negative_world_origin(self):
        a=np.zeros((100,100),bool);a[50,39]=1
        self.assertTrue(Snapshot(a,.01,(-1,-1)).collides((-.5,-.5,0),BOX))
    def test_new_snapshot_sees_mutation_old_does_not(self):
        a=np.zeros((100,100),bool);old=Snapshot(a,.01);a[50,50]=1
        self.assertFalse(old.collides((.5,.5,0),BOX))
        self.assertTrue(Snapshot(a,.01).collides((.5,.5,0),BOX))
    def test_removed_obstacle_not_cached(self):
        a=np.zeros((100,100),bool);a[50,50]=1;old=Snapshot(a,.01);a[:]=0
        self.assertTrue(old.collides((.5,.5,0),BOX))
        self.assertFalse(Snapshot(a,.01).collides((.5,.5,0),BOX))
    def test_guard_always_current_mask(self):
        a=np.zeros((100,100),bool)
        self.assertFalse(polygon_collision((.5,.5,0),BOX,a,.01));a[50,50]=1
        self.assertTrue(polygon_collision((.5,.5,0),BOX,a,.01))
    def test_world_edges_closed(self):
        s=Snapshot(np.zeros((100,100),bool),.01)
        for p in [(.1,.5,0),(.9,.5,0),(.5,.1,0),(.5,.9,0)]:
            with self.subTest(p=p):self.assertTrue(s.collides(p,BOX))
    def test_invalid_geometry_fails_closed(self):
        s=Snapshot(np.zeros((100,100),bool),.01)
        for shape in [[],[[0,0]],[[0,0],[0,0],[1,1]],[[float('nan'),0]]*3,'bad',[[0,0],[1]]]:
            with self.subTest(shape=shape):self.assertTrue(s.collides((.5,.5,0),shape))
    def test_self_crossing_star_rejected(self):
        s=Snapshot(np.zeros((100,100),bool),.01)
        star=[[.1*math.cos(i*2*math.pi/5),.1*math.sin(i*2*math.pi/5)] for i in [0,2,4,1,3]]
        self.assertTrue(s.collides((.5,.5,0),star))
    def test_invalid_resolution_raises(self):
        for res in [0,-.1,float('nan')]:
            with self.assertRaises(ValueError):Snapshot(np.zeros((10,10)),res)

class FastClosedCells(ClosedCells):
    def test_tolerance_boundary_equivalent_to_generic(self):
        from collision import Snapshot as Generic
        from fast_snapshot import Snapshot as Fast
        a=np.zeros((12,12),bool);a[5,5]=1
        shape=[[-.25,-.25],[.25,-.25],[.25,.25],[-.25,.25]]
        for origin,pose in [((-8,-12),(-1.7499999999988296,-6.5,0)),
                            ((1e8,-1e8),(100000006.25000142,-99999994.5,0))]:
            self.assertEqual(Fast(a,1.,origin).collides(pose,shape),Generic(a,1.,origin).collides(pose,shape))

    def setUp(self):
        from unittest.mock import patch
        from fast_snapshot import Snapshot as FastSnapshot
        self.patch = patch(__name__ + '.Snapshot', FastSnapshot)
        self.patch.start()
        self.addCleanup(self.patch.stop)

if __name__=='__main__':unittest.main()
