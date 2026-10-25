"""Exact-stamp rebasing and editable global priors; synthetic inputs only."""
import copy
import hashlib
import threading
import time
import unittest

import numpy as np

from robot_dashboard.application.anchor_proposal import capture_registered_imu, proposal_from_job
from robot_dashboard.application.global_observation import GlobalObservationCoordinator
from robot_dashboard.relocalization.experimental_se3 import from_translation_rpy, matrix_to_quaternion_xyzw, transform_points
from robot_dashboard.relocalization.global_observation_jobs import GlobalObservationConflict, GlobalObservationUnavailable
from robot_dashboard.relocalization.v031_observation_compat import SELECTION_POLICY
from test_observation_alignment import inputs, Agent
from test_observation_subscription_alignment import SubscriptionAgent, evidence
from test_navigation_presets import LocalASGIClient
from fastapi import FastAPI
from robot_dashboard.api.routers.global_observation import router
from robot_dashboard.application.runtime import ApplicationRuntime


MAP_ID, REVISION = 'a'*24, 'b'*64


def set_pose(pose, matrix):
    pose['position'] = dict(zip(('x','y','z'), matrix[:3,3].tolist()))
    pose['orientation'] = dict(zip(('x','y','z','w'), matrix_to_quaternion_xyzw(matrix[:3,:3])))


class Catalog:
    revision = REVISION
    frame = 'map'
    def metadata(self, _):
        return dict(kind='pointcloud3d',format='pcd-binary',revision=self.revision,frame_id=self.frame)
    def raw_global_reference(self, *args, **kwargs):
        data = np.random.default_rng(2).normal(size=(200,3)).astype('<f8').tobytes()
        return dict(xyz_bytes=data,sha256=hashlib.sha256(data).hexdigest(),encoding='float64_le_xyz',
                    point_count=200,frame_id=self.frame,units='m')


def result_for(context, matrix):
    n=context['scan']['point_count']
    return dict(status='OBSERVATION_ONLY_UNVERIFIED',map_frame=context['map_frame'],scan_frame=context['source_frame'],
                frame_id=context['source_frame'],source_stamp_ns=context['source_stamp_ns'],session_id=context['observer_epoch'],
                map_id='sha256:'+context['map']['sha256'],input_points=n,reference_points=context['map']['point_count'],
                selection_policy=SELECTION_POLICY,gate_reasons=[],selected_candidate=0,
                candidates=[dict(map_from_scan=matrix.tolist(),gate_reasons=[],rmse_m=.07,full_scan_rmse_m=.08,
                overlap=.95,geometry_min_max_eigen_ratio=.1,inlier_geometry_min_max_eigen_ratio=.1,
                distinct_inlier_voxel_count=n,inlier_count=n,scan_count=n,refinement_stationary=True)])


class Runner:
    def __init__(self,matrix):
        self.matrix=matrix; self.entered=threading.Event(); self.release=threading.Event();self.release.set()
        self.context=None
    def status(self): return dict(available=True,backend_id='synthetic',allow_ambiguous=False)
    def run_arrays(self,*,scan_bytes,map_bytes,context,cancel_event):
        self.context=copy.deepcopy(context);self.entered.set();self.release.wait(2)
        return result_for(context,self.matrix)


class AnchorProposalTests(unittest.TestCase):
    def setUp(self):
        self.imu_points=np.random.default_rng(14).uniform(-2,2,(1024,3))
        self.odom0=from_translation_rpy([2,-3,.7],[.12,-.2,.8])
        cloud,pose=inputs(transform_points(self.odom0,self.imu_points))
        cloud.update(frame_id='camera_init',source_points=1024)
        pose.update(topic='/Odometry',frame_id='camera_init',child_frame_id='body')
        set_pose(pose,self.odom0)
        self.agent=Agent(cloud,pose);self.catalog=Catalog()
        self.map0=from_translation_rpy([6,-1,.4],[.2,-.3,-.7])

    def capture(self,mode='native_publisher',**changes):
        return capture_registered_imu(self.agent,mode=mode,cancel=threading.Event(),
                                     deadline=time.monotonic()+.04,max_points=10000,max_bytes=1000000,**changes)

    def job(self):
        data,scan,capture=self.capture();reference=self.catalog.raw_global_reference()
        reference.pop('xyz_bytes')
        context=dict(map_id=MAP_ID,map_revision=REVISION,map_frame='map',source_frame='body',
                     observer_id=capture['contract']['observer_id'],observer_epoch=capture['contract']['cloud_epoch'],
                     source_stamp_ns=scan['source_stamp_ns'],scan=scan,map=reference,anchor_capture=capture)
        return dict(job_id='1'*24,input_kind='fastlio_imu',state='succeeded',worker_active=False,map_id=MAP_ID,
                    map_revision=REVISION,captured_context=context,result=dict(captured_context=copy.deepcopy(context),
                    historical_only=True,observation=result_for(context,self.map0)))

    def test_registered_points_rebase_once_including_all_cached_points(self):
        self.agent.cloud['robot_pose_in_frame']={'x':999,'source':'configured_sensor_extrinsic'}
        data,scan,capture=self.capture()
        np.testing.assert_allclose(np.frombuffer(data,dtype='<f8').reshape(-1,3),self.imu_points,atol=1e-6)
        self.assertEqual(scan['point_count'],1024)
        self.assertTrue(scan['transform_applied']);self.assertFalse(scan['sampling_applied'])
        self.assertEqual(capture['provenance']['pair_method'],'FASTLIO_OUTPUT_STAMP_EXACT')

    def test_exact_stamp_and_freshness_are_required_without_raw_fallback(self):
        original=copy.deepcopy(self.agent.cloud)
        for change in ['stamp','frame','stale','nonfinite']:
            with self.subTest(change=change):
                self.agent.cloud=copy.deepcopy(original)
                if change=='stamp':self.agent.cloud['observation']['source_stamp_ns']='1792309179130175353'
                if change=='frame':self.agent.cloud['frame_id']='hesai_lidar'
                if change=='stale':self.agent.cloud['observation']['received_monotonic_s']-=10
                if change=='nonfinite':self.agent.cloud['points_bytes']=np.full((100,3),np.nan,dtype='<f4').tobytes()
                with self.assertRaises(GlobalObservationUnavailable):self.capture()

    def test_proposal_propagates_capture_to_new_pose_with_nonzero_xyz_rpy(self):
        job=self.job();odom_now=from_translation_rpy([2.3,-2.8,.2],[-.1,.15,1.1]);set_pose(self.agent.pose,odom_now)
        self.agent.pose['observation']['source_stamp_ns']=str(int(self.agent.pose['observation']['source_stamp_ns'])+100)
        result=proposal_from_job(job,self.catalog,self.agent)
        values=result['pose'];actual=from_translation_rpy([values[k] for k in ('x','y','z')],np.radians([values[k] for k in ('roll','pitch','yaw')]))
        np.testing.assert_allclose(actual,self.map0@np.linalg.inv(self.odom0)@odom_now,atol=1e-10)
        self.assertTrue(result['requires_reanchor']);self.assertIsNone(result['absolute_accuracy_m'])
        self.assertEqual(result['capture_stamp_ns'],job['captured_context']['source_stamp_ns'])
        self.assertNotEqual(result['capture_stamp_ns'],result['proposal_stamp_ns'])
        self.assertEqual(job['result']['observation']['source_stamp_ns'],result['capture_stamp_ns'])

    def test_finished_result_cannot_cross_map_frame_epoch_time_or_stale_inputs(self):
        job=self.job();cloud,pose=copy.deepcopy(self.agent.cloud),copy.deepcopy(self.agent.pose)
        for change in ['map','map_frame','pose_epoch','cloud_epoch','backward','stale']:
            with self.subTest(change=change):
                self.agent.cloud,self.agent.pose=copy.deepcopy(cloud),copy.deepcopy(pose)
                self.catalog.revision,self.catalog.frame=REVISION,'map'
                if change=='map':self.catalog.revision='e'*64
                if change=='map_frame':self.catalog.frame='different'
                if change=='pose_epoch':self.agent.pose['observation']['publisher_epoch']='a'*32
                if change=='cloud_epoch':self.agent.cloud['observation']['publisher_epoch']='a'*32
                if change=='backward':self.agent.pose['observation']['source_stamp_ns']='1'
                if change=='stale':self.agent.pose['observation']['received_monotonic_s']-=10
                with self.assertRaises((GlobalObservationConflict,ValueError)):
                    proposal_from_job(job,self.catalog,self.agent)

    def test_missing_or_rejected_selected_candidate_never_fills_a_prior(self):
        for field,value in [('selected_candidate',None),('gate_reasons',['LOW_OVERLAP'])]:
            job=self.job();job['result']['observation'][field]=value
            with self.subTest(field=field),self.assertRaises((GlobalObservationConflict,RuntimeError)):
                proposal_from_job(job,self.catalog,self.agent)

    def test_existing_global_worker_accepts_imu_capture_and_returns_editable_proposal(self):
        runner=Runner(self.map0);owner=GlobalObservationCoordinator(self.catalog,self.agent,runner)
        self.addCleanup(owner.close)
        first=owner.start('imu-test',MAP_ID,REVISION,input_kind='fastlio_imu')
        self.assertTrue(runner.entered.wait(1))
        for _ in range(100):
            job=owner.job(first['job_id'])
            if not job['worker_active']:break
            time.sleep(.005)
        self.assertEqual(job['state'],'succeeded',job)
        self.assertEqual(owner.anchor_proposal(job['job_id'])['pose_reference'],'FASTLIO_IMU')
        self.assertEqual(owner.start('imu-test',MAP_ID,REVISION,input_kind='fastlio_imu')['job_id'],job['job_id'])
        with self.assertRaises(GlobalObservationConflict):owner.start('imu-test',MAP_ID,REVISION)
        self.assertEqual(runner.context['full_original_scope'],'CACHED_REGISTERED_XYZ_REBASED_TO_IMU')

    def test_cancelled_calculation_cannot_return_late_proposal(self):
        runner=Runner(self.map0);runner.release.clear()
        owner=GlobalObservationCoordinator(self.catalog,self.agent,runner);self.addCleanup(owner.close)
        first=owner.start('cancel-imu',MAP_ID,REVISION,input_kind='fastlio_imu')
        self.assertTrue(runner.entered.wait(1));owner.cancel(first['job_id']);runner.release.set()
        with self.assertRaises(GlobalObservationConflict):owner.anchor_proposal(first['job_id'])

    def test_subscription_opt_in_remains_unverified_and_changed_graph_or_session_rejects(self):
        for v,kind in [(self.agent.cloud,'sensor_msgs/msg/PointCloud2'),(self.agent.pose,'nav_msgs/msg/Odometry')]:
            v['observation'].update(identity_status='UNAVAILABLE',publisher_gid=None,
                                    subscription_evidence=evidence(v['topic'],kind))
        self.agent=SubscriptionAgent(self.agent.cloud,self.agent.pose)
        with self.assertRaises(GlobalObservationUnavailable):self.capture()
        data,scan,capture=self.capture(mode='subscription_observation')
        self.assertFalse(capture['provenance']['per_message_publisher_verified'])
        from robot_dashboard.application.anchor_proposal import current_imu
        context=dict(anchor_capture=capture,source_stamp_ns=scan['source_stamp_ns'])
        current_imu(self.agent,context)
        self.agent.pose['observation']['subscription_evidence']=evidence('/Odometry','nav_msgs/msg/Odometry',session='3')
        with self.assertRaises(GlobalObservationConflict):current_imu(self.agent,context)
        self.agent.pose['observation']['subscription_evidence']=evidence('/Odometry','nav_msgs/msg/Odometry',endpoint='3')
        with self.assertRaises(GlobalObservationConflict):current_imu(self.agent,context)

    def test_api_explicit_kind_origin_and_read_only_proposal(self):
        runner=Runner(self.map0);owner=GlobalObservationCoordinator(self.catalog,self.agent,runner);self.addCleanup(owner.close)
        app=FastAPI();app.state.runtime=ApplicationRuntime(global_observation=owner);app.include_router(router)
        client=LocalASGIClient(app);root='/api/v1/observations/global-jobs'
        body=dict(request_id='api-imu',map_id=MAP_ID,map_revision=REVISION,input_kind='fastlio_imu')
        self.assertEqual(client.post(root,json=body,headers={'Origin':'http://other'}).status_code,403)
        self.assertEqual(client.post(root,json={**body,'provenance_mode':'skip_checks'}).status_code,422)
        response=client.post(root,json=body);self.assertEqual(response.status_code,202,response.text)
        job_id=response.json()['job_id'];self.assertTrue(runner.entered.wait(1))
        for _ in range(100):
            if not owner.job(job_id)['worker_active']:break
            time.sleep(.005)
        response=client.get(root+'/'+job_id+'/anchor-proposal')
        self.assertEqual(response.status_code,200,response.text)
        self.assertTrue(response.json()['requires_reanchor'])
