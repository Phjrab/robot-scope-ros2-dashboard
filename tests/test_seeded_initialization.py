"""Actual local ICP, API seed propagation and immutable capture tests (synthetic)."""
import copy
import hashlib
import math
import threading
import time
import unittest
from unittest.mock import patch

import numpy as np
from fastapi import FastAPI

from robot_dashboard.api.routers.global_observation import router
from robot_dashboard.application.anchor_proposal import source_contract, capture_registered_imu
from robot_dashboard.application.global_observation import GlobalObservationCoordinator
from robot_dashboard.application.runtime import ApplicationRuntime
from robot_dashboard.relocalization.experimental_se3 import from_translation_rpy, transform_points
from robot_dashboard.relocalization.global_observation_jobs import GlobalObservationConflict, GlobalObservationValidationError
from robot_dashboard.relocalization.seeded_initialization import run_seeded_arrays, validate_seed, prior_delta
from test_anchor_proposal import Catalog, Runner, set_pose, MAP_ID, REVISION
from test_navigation_presets import LocalASGIClient
from test_observation_alignment import Agent, inputs


class FreshSyntheticAgent(Agent):
    def _fresh(self):
        for value in (self.cloud, self.pose):
            value['observation']['received_monotonic_s'] = time.monotonic()
    def pointcloud_binary_snapshot(self):
        self._fresh(); return super().pointcloud_binary_snapshot()
    def pose_snapshot(self):
        self._fresh(); return super().pose_snapshot()
    def observation_pose_near(self, value):
        self._fresh(); return super().observation_pose_near(value)


class SeededInitializationTests(unittest.TestCase):
    def setUp(self):
        self.points = np.random.default_rng(40).uniform(-2, 2, (240, 3))
        self.truth = from_translation_rpy([4, -3, 2.4], [.1, -.08, .4])
        self.target = transform_points(self.truth, self.points)
        self.initial = from_translation_rpy([4.15, -3.1, 2.42], [.12, -.06, .46])
        self.bounds = dict(xy_m=.75, yaw_deg=25, z_m=.3, tilt_deg=10)

    def solve(self, initial=None, bounds=None, target=None, cancel=None):
        return run_seeded_arrays(scan_bytes=self.points.astype('<f8').tobytes(),
            map_bytes=(self.target if target is None else target).astype('<f8').tobytes(),
            context=dict(map_id=MAP_ID,map_revision=REVISION,map_frame='map',source_stamp_ns='1792309179130175352',
                         seed=dict(revision=1,bounds=bounds or self.bounds),
                         T_map_imu_seed_capture=(self.initial if initial is None else initial).tolist()),
            cancel_event=cancel or threading.Event(),timeout_s=10)

    def test_actual_numeric_icp_uses_seed_near_correct_repeated_region(self):
        repeated=np.vstack((self.target,self.target+[14,-9,0]))
        result=self.solve(target=repeated)
        self.assertTrue(result['admissible'],result)
        np.testing.assert_allclose(result['map_from_scan'],self.truth,atol=1e-6)
        other=self.initial.copy();other[:3,3]+=[14,-9,0]
        result2=self.solve(initial=other,target=repeated)
        expected=self.truth.copy();expected[:3,3]+=[14,-9,0]
        np.testing.assert_allclose(result2['map_from_scan'],expected,atol=1e-6)
        self.assertTrue(result2['admissible']);self.assertTrue(result2['ambiguity_unresolved'])
        self.assertEqual(result['scan_points'],len(self.points))
        self.assertEqual(result['numerical']['metrics']['overlap_ratio'],1)
        self.assertGreater(result['target_radius_m'],result['bounds']['xy_m'])

    def test_out_of_bounds_candidate_is_retained_not_clamped_or_accepted(self):
        bounds={**self.bounds,'xy_m':.1}
        result=self.solve(bounds=bounds)
        self.assertEqual(result['reason'],'OUTSIDE_SEED_BOUNDS');self.assertFalse(result['admissible'])
        np.testing.assert_allclose(result['map_from_scan'],self.truth,atol=1e-6)
        self.assertGreater(result['delta']['xy_m'],.1)

    def test_wrong_seed_is_not_global_search_or_forced_success(self):
        wrong=self.initial.copy();wrong[:2,3]=[100,100]
        with self.assertRaisesRegex(ValueError,'LOCAL_REFERENCE_POINT_LIMIT'):self.solve(initial=wrong)
        unrelated=np.random.default_rng(45).uniform(-2,2,(240,3))+[4,-3,2.4]
        result=self.solve(target=unrelated)
        self.assertFalse(result['admissible']);self.assertNotEqual(result['reason'],'CANDIDATE')

    def test_angle_wrap_and_all_six_bound_dimensions(self):
        a=from_translation_rpy([0,0,2],[0,0,math.radians(179)])
        b=from_translation_rpy([0,0,2.1],[.1,.2,math.radians(-179)])
        delta=prior_delta(a,b)
        self.assertAlmostEqual(delta['yaw_deg'],2)
        self.assertAlmostEqual(delta['z_m'],.1)
        self.assertGreater(delta['tilt_deg'],10)

    def fixture(self):
        odom=from_translation_rpy([1,-2,.8],[.1,.05,.3])
        cloud,pose=inputs(transform_points(odom,self.points));cloud.update(frame_id='camera_init',source_points=len(self.points))
        pose.update(topic='/Odometry',frame_id='camera_init',child_frame_id='body');set_pose(pose,odom)
        agent=FreshSyntheticAgent(cloud,pose);catalog=Catalog()
        def reference(*args,**kwargs):
            data=self.target.astype('<f8').tobytes()
            return dict(xyz_bytes=data,sha256=hashlib.sha256(data).hexdigest(),encoding='float64_le_xyz',point_count=len(self.target),frame_id='map',units='m')
        catalog.raw_global_reference=reference
        runner=Runner(np.eye(4));runner.status=lambda:dict(available=False,backend_id='GLOBAL_UNAVAILABLE')
        owner=GlobalObservationCoordinator(catalog,agent,runner);self.addCleanup(owner.close)
        seed=dict(revision=1,pose=dict(x=4.15,y=-3.1,z=2.42,roll=math.degrees(.12),pitch=math.degrees(-.06),yaw=math.degrees(.46)),
                  pose_reference='FASTLIO_IMU',units='metres_degrees',map_frame='map',height_source='manual',bounds=self.bounds,
                  source_contract=source_contract(agent.cloud,agent.pose,'native_publisher',time.monotonic()))
        return owner,agent,seed,runner,odom

    def wait(self,owner,job):
        until=time.monotonic()+8
        while time.monotonic()<until:
            value=owner.job(job['job_id'])
            if not value['worker_active']:return value
            time.sleep(.01)
        self.fail('worker did not settle')

    def test_api_to_real_worker_and_seed_capture_current_propagation(self):
        owner,agent,seed,global_runner,odom=self.fixture()
        delta=from_translation_rpy([.08,-.03,.02],[.01,-.01,.02]);odom_capture=odom@delta
        def capture(*args,**kwargs):
            set_pose(agent.pose,odom_capture)
            agent.cloud['points_bytes']=transform_points(odom_capture,self.points).astype('<f4').tobytes()
            for v in (agent.cloud,agent.pose):v['observation']['source_stamp_ns']=str(int(v['observation']['source_stamp_ns'])+100)
            return capture_registered_imu(*args,**kwargs)
        app=FastAPI();app.state.runtime=ApplicationRuntime(global_observation=owner);app.include_router(router)
        client=LocalASGIClient(app)
        body=dict(request_id='seed-api',map_id=MAP_ID,map_revision=REVISION,input_kind='fastlio_imu',search_mode='seeded_local',seed=seed)
        with patch('robot_dashboard.application.anchor_proposal.capture_registered_imu',capture):
            response=client.post('/api/v1/observations/global-jobs',json=body)
            self.assertEqual(response.status_code,202,response.text)
            job=self.wait(owner,response.json())
        self.assertEqual(job['state'],'succeeded',job)
        result=job['result']['observation'];self.assertTrue(result['admissible'],result)
        np.testing.assert_allclose(job['captured_context']['T_map_imu_seed_capture'],self.initial@delta,atol=1e-10)
        self.assertIsNone(global_runner.context,'seeded jobs must not invoke an unavailable global backend')
        current=odom_capture@from_translation_rpy([.05,0,0],[0,0,.01]);set_pose(agent.pose,current)
        agent.pose['observation']['source_stamp_ns']=str(int(agent.pose['observation']['source_stamp_ns'])+10)
        proposal=owner.anchor_proposal(job['job_id'])
        np.testing.assert_allclose(proposal['T_map_odom'],self.truth@np.linalg.inv(odom_capture),atol=1e-6)
        self.assertEqual(proposal['seed_revision'],1)
        self.assertNotEqual(proposal['seed_stamp_ns'],proposal['capture_stamp_ns'])
        self.assertNotEqual(proposal['proposal_stamp_ns'],proposal['capture_stamp_ns'])
        changed={**seed,'pose':{**seed['pose'],'x':8}}
        with self.assertRaises(GlobalObservationConflict):owner.start('seed-api',MAP_ID,REVISION,input_kind='fastlio_imu',search_mode='seeded_local',seed=changed)
        agent.pose['observation']['publisher_epoch']='a'*32
        with self.assertRaises(GlobalObservationConflict):owner.anchor_proposal(job['job_id'])

    def test_seed_validation_rejects_units_nonfinite_unknown_fields_and_bounds(self):
        _,_,seed,_,_=self.fixture()
        for key,value in [('units','pixels'),('pose_reference','BODY_VERIFIED'),('revision',True),('extra',1),
                          ('bounds',{**self.bounds,'xy_m':100}),('pose',{**seed['pose'],'x':float('nan')})]:
            with self.subTest(key=key),self.assertRaises(GlobalObservationValidationError):
                validate_seed({**seed,key:value})

    def test_capture_waits_for_scan_at_or_after_seed_binding_stamp(self):
        _,agent,_,_,_=self.fixture()
        old=int(agent.cloud['observation']['source_stamp_ns']);calls=0
        original=agent.pointcloud_binary_snapshot
        def next_scan():
            nonlocal calls
            calls+=1
            if calls>=3:
                for value in (agent.cloud,agent.pose):value['observation']['source_stamp_ns']=str(old+20)
            return original()
        agent.pointcloud_binary_snapshot=next_scan
        _,scan,_=capture_registered_imu(agent,mode='native_publisher',cancel=threading.Event(),
            deadline=time.monotonic()+1,max_points=4000,max_bytes=100000,minimum_stamp_ns=str(old+10))
        self.assertEqual(scan['source_stamp_ns'],str(old+20));self.assertEqual(calls,3)

    def test_http_validation_and_stale_source_never_start_a_worker(self):
        owner,agent,seed,_,_=self.fixture()
        app=FastAPI();app.state.runtime=ApplicationRuntime(global_observation=owner);app.include_router(router)
        client=LocalASGIClient(app)
        body=dict(request_id='invalid-seed',map_id=MAP_ID,map_revision=REVISION,input_kind='fastlio_imu',search_mode='seeded_local',seed=seed)
        for changes in [{'seed':{**seed,'units':'pixels'}},{'search_mode':'global'},{'input_kind':'raw'},
                        {'seed':{**seed,'bounds':{**seed['bounds'],'xy_m':0}}}]:
            self.assertEqual(client.post('/api/v1/observations/global-jobs',json={**body,**changes}).status_code,422)
        agent.pose['observation']['publisher_epoch']='a'*32
        self.assertEqual(client.post('/api/v1/observations/global-jobs',json=body).status_code,409)
        self.assertIsNone(owner.snapshot()['active']);self.assertEqual(owner.snapshot()['generation'],0)

    def test_cancelled_isolated_worker_is_reaped(self):
        cancel=threading.Event();cancel.set()
        with self.assertRaisesRegex(ValueError,'NUMERICAL_WORKER_UNAVAILABLE'):
            self.solve(cancel=cancel)
