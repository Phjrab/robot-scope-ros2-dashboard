"""Persisted user course boundaries and real weighted registration, no hardware."""
import copy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import threading
import unittest

import numpy as np
from fastapi import FastAPI

from robot_dashboard.api.routers.course_regions import router
from robot_dashboard.application.runtime import ApplicationRuntime
from robot_dashboard.course_regions import CourseRegionStore, course_values, course_membership
from robot_dashboard.navigation_presets import PresetConflict, PresetInvalid
from robot_dashboard.relocalization.seeded_initialization import run_seeded_arrays
from robot_dashboard.relocalization.experimental_se3 import transform_points
from robot_dashboard.relocalization.observation_alignment import ReferenceIndex
from test_navigation_presets import LocalASGIClient

MAP='a'*24
REV='b'*64

def region(**changes):
    return dict(map_id=MAP,map_revision=REV,map_frame='map',polygon=[[-2,-2],[2,-2],[2,2],[-2,2]],
                outside_weight=.25,confirmed=True,units='m',**changes)


class CourseRegionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.meta=dict(kind='pointcloud3d',revision=REV,frame_id='map')
        self.catalog=SimpleNamespace(metadata=lambda _:dict(self.meta))
        self.directory=Path(self.temp.name)/'courses';self.store=CourseRegionStore(self.directory,self.catalog)
        self.body={k:v for k,v in region().items() if k not in {'map_id','units'}};self.body['name']='경기장 본선 코스'
        app=FastAPI();app.state.runtime=ApplicationRuntime(course_regions=self.store);app.include_router(router)
        self.client=LocalASGIClient(app);self.url='/api/v1/observations/course-regions/'+MAP

    def test_api_save_reload_scoped_to_map_revision_without_any_robot_component(self):
        self.assertEqual(self.client.post(self.url,json=self.body,headers={'Origin':'http://other'}).status_code,403)
        response=self.client.post(self.url,json=self.body);self.assertEqual(response.status_code,201,response.text)
        saved=response.json()['preset'];self.assertEqual(saved['values'],region())
        loaded=CourseRegionStore(self.directory,self.catalog).snapshot(MAP)
        self.assertEqual(loaded['presets'],[saved]);self.assertEqual(self.store.snapshot('c'*24)['presets'],[])
        self.meta['name']='metadata-only rename';self.assertEqual(self.store.snapshot(MAP)['presets'],[saved])
        self.meta['revision']='c'*64
        self.assertEqual(self.store.snapshot(MAP)['presets'],[]);self.assertEqual(self.store.snapshot(MAP)['incompatible_count'],1)
        self.assertEqual(self.client.post(self.url,json=self.body).status_code,409)
        self.meta['revision']=REV;self.meta['frame_id']='other'
        self.assertEqual(self.store.snapshot(MAP)['presets'],[])

    def test_invalid_geometry_confirmation_weights_and_duplicate_do_not_overwrite(self):
        for changes in [{'polygon':[[0,0],[1,1],[0,1],[1,0]]},{'polygon':[[0,0],[1,0],[2,0]]},
                        {'polygon':[[0,0],[1,0],[1,1],[0,0]]},{'outside_weight':0},{'outside_weight':True},
                        {'confirmed':False},{'polygon':[[True,0],[1,0],[1,1]]},{'units':'pixels'}]:
            with self.subTest(changes=changes),self.assertRaises(PresetInvalid):course_values({**region(),**changes})
        self.assertFalse(self.directory.exists())
        self.store.create(MAP,**self.body);path=self.directory/MAP/'presets.json';before=path.read_bytes()
        with self.assertRaises(PresetConflict):self.store.create(MAP,**{**self.body,'outside_weight':.5})
        self.assertEqual(path.read_bytes(),before)
        for changes in [{'apply':True},{'confirmed':False},{'outside_weight':True},{'polygon':[['0',0],[1,0],[1,1]]}]:
            self.assertEqual(self.client.post(self.url,json={**self.body,**changes}).status_code,422)
        with self.assertRaises(PresetInvalid):self.store.snapshot('../escape')

    def test_existing_polygon_membership_includes_edges_and_all_heights(self):
        self.assertEqual(course_membership(np.array([[0,0,100],[2,2,-100],[3,0,0]]),region()).tolist(),[True,True,False])

    def solve(self,points,target,course,*,enforce_residual_limit=True):
        seed=dict(revision=1,bounds=dict(xy_m=.75,yaw_deg=25,z_m=.3,tilt_deg=10))
        seed['enforce_residual_limit']=enforce_residual_limit
        if course is not None:seed['course_region']=course
        initial=np.eye(4);initial[:3,3]=[.02,.01,.01]
        return run_seeded_arrays(scan_bytes=points.astype('<f8').tobytes(),map_bytes=target.astype('<f8').tobytes(),
            context=dict(map_id=MAP,map_revision=REV,map_frame='map',source_stamp_ns='123456',seed=seed,
                         T_map_imu_seed_capture=initial.tolist()),cancel_event=threading.Event(),timeout_s=10)

    def test_real_isolated_worker_uses_region_weights_and_keeps_full_input_quality_gate(self):
        rng=np.random.default_rng(71)
        points=np.vstack((rng.uniform(-1,1,(100,3)),rng.uniform(-1,1,(150,3))+[5,0,0],rng.uniform(-1,1,(150,3))+[-5,0,0]))
        target=points.copy();target[100:,0]+=.06
        plain=self.solve(points,target,None);weighted=self.solve(points,target,region())
        self.assertTrue(plain['admissible'],plain);self.assertTrue(weighted['admissible'],weighted)
        self.assertLess(abs(weighted['map_from_scan'][0][3]),abs(plain['map_from_scan'][0][3])-.01)
        info=weighted['region_weighting'];self.assertEqual(info['course_matches'],100);self.assertEqual(info['surrounding_matches'],300)
        self.assertAlmostEqual(info['course_weight_share'],100/175)
        _,squared=ReferenceIndex(target).nearest(transform_points(weighted['map_from_scan'],points))
        self.assertAlmostEqual(weighted['numerical']['metrics']['rmse_m'],float(np.sqrt(squared.mean())))
        equal=self.solve(points,target,{**region(),'outside_weight':1})
        np.testing.assert_allclose(equal['map_from_scan'],plain['map_from_scan'],atol=1e-9)
        # Better course fit cannot hide a poor full-capture residual.
        bad=target.copy();bad[100:,0]+=.2
        rejected=self.solve(points,bad,region());self.assertFalse(rejected['admissible']);self.assertEqual(rejected['reason'],'HIGH_RESIDUAL')
        self.assertGreater(rejected['numerical']['metrics']['rmse_m'],.05)
        unlimited=self.solve(points,bad,region(),enforce_residual_limit=False)
        self.assertTrue(unlimited['admissible'],unlimited)
        self.assertEqual(unlimited['residual_policy'],dict(enforced=False,max_rmse_m=None,original_max_rmse_m=.05,original_passed=False))
        np.testing.assert_allclose(unlimited['map_from_scan'],rejected['map_from_scan'],atol=1e-9)
        self.assertEqual(unlimited['numerical']['metrics']['rmse_m'],rejected['numerical']['metrics']['rmse_m'])
        wrong=copy.deepcopy(region());wrong['polygon']=[[20,20],[21,20],[21,21],[20,21]]
        self.assertEqual(self.solve(points,target,wrong)['reason'],'NO_COURSE_MATCHES')
        self.assertEqual(self.solve(points,target,wrong,enforce_residual_limit=False)['reason'],'NO_COURSE_MATCHES')
        with self.assertRaisesRegex(ValueError,'COURSE_MAP_CHANGED'):self.solve(points,target,{**region(),'map_revision':'c'*64})
