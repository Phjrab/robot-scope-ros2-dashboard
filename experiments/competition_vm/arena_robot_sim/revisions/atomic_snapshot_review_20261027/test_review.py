import copy
import importlib.util
import json
import os
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('d0_atomic_review',HERE/'review.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)


class GeometryAndIdentity(unittest.TestCase):
    def test_raw_and_published_encoding(self):
        self.assertFalse(r.is_blocked(253));self.assertTrue(r.is_blocked(254));self.assertTrue(r.is_blocked(255))
        self.assertFalse(r.is_blocked(99,True));self.assertTrue(r.is_blocked(100,True));self.assertTrue(r.is_blocked(255,True))

    def test_clipping_rejects_touch_and_overlap(self):
        poly=[[0,0],[1,0],[1,1],[0,1]]
        self.assertTrue(r.old.clip(poly,[1,0,2,1]))
        self.assertEqual(r.old.area(r.old.clip(poly,[.5,.5,2,2])),.25)
        self.assertFalse(r.old.clip(poly,[1.001,0,2,1]))

    def test_inflation_not_circle_veto(self):
        grid={'resolution':.02,'origin':[0,0],'width':100,'height':100}
        poly=r.transformed([[-.435,-.31],[.435,-.31],[.435,.31],[-.435,.31]],[1,1,0])
        self.assertFalse(r.grid_hits(poly,grid,bytes([253])*10000))

    def test_synthetic_lethal_pair(self):
        grid={'resolution':.02,'origin':[0,0],'width':100,'height':100}
        poly=[[.99,.99],[1.01,.99],[1.01,1.01],[.99,1.01]]
        data=bytearray([253])*10000
        self.assertFalse(r.grid_hits(poly,grid,data))
        data[50*100+50]=254
        self.assertTrue(r.grid_hits(poly,grid,data))

    def test_subdivision_includes_endpoints(self):
        a=[0,0,0];b=[.03,0,.03];body=[[-.435,-.31],[.435,-.31],[.435,.31],[-.435,.31]]
        values=r.interval(a,b,body)
        self.assertEqual(values[0],a);self.assertEqual(values[-1],b);self.assertGreater(len(values),16)

    def test_path_matching_requires_xyz_quaternion_stamp_frame(self):
        packet={'frame':'map','path_header_ros_ns':5,'path':[{'position':[1,2,3],'quaternion':[0,0,0,1]}]}
        record={'frame':'map','source_sim_s':5e-9,'points':[[1,2]],'z':[3],'quaternions':[[0,0,0,1]]}
        self.assertTrue(r.matched(packet,record))
        for key,value in [('frame','odom'),('source_sim_s',6e-9),('points',[[1.001,2]]),('z',[0]),('quaternions',[[0,0,1,0]])]:
            self.assertFalse(r.matched(packet,record|{key:value}))

    def test_saved_result_bounded_claim(self):
        result=json.loads((HERE/'result.json').read_text())
        self.assertEqual(len(result['packet_identity_checks']),33)
        self.assertEqual(result['native_execution_by_d0'],'NOT_RUN')
        self.assertEqual(result['historical_round6_atomic_attribution'],'INPUT_REQUIRED_EXACT_HISTORICAL_BYTES')
        for pair in result['selected_interval_checks']:
            self.assertEqual(pair['raw_byte'],253);self.assertEqual(pair['preceding_occupancy'],100)
            self.assertFalse(pair['raw_hits']);self.assertTrue(pair['preceding_published_hits'])
            self.assertTrue(pair['synthetic_254_hit_samples']);self.assertFalse(pair['cone_hit_samples'])

    @unittest.skipUnless(os.environ.get('D0_ATOMIC_ARTIFACT_ROOT'),'private preserved artifact is optional')
    def test_private_archive_reconstruction_and_guards(self):
        root=Path(os.environ['D0_ATOMIC_ARTIFACT_ROOT']);archive=Path(os.environ['D0_ATOMIC_ARTIFACT_ZIP'])
        self.assertEqual(r.review(root,archive),json.loads((HERE/'result.json').read_text()))
        p=root/'atomic/mppi-d0_feasible1-0/atomic-planner'
        packet=json.loads((p/'plan-3.json').read_text());data=(p/'plan-3.bin').read_bytes()
        for key,value in [('source_sha','bad'),('raw_unchanged_under_lock',False),('raw_costmap_update_stamp',0),('origin',[1,0]),('allow_unknown',True)]:
            with self.assertRaises(AssertionError):r.validate_packet(packet|{key:value},data)
        with self.assertRaises(AssertionError):r.validate_packet(packet,data[:-1])


if __name__=='__main__':unittest.main()
