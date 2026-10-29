import copy
from dataclasses import replace
import os
import unittest

from robot_dashboard.expansion_runtime import FinalIntentPort
from robot_dashboard.expansion_runtime.ports import ingest_scene

ENABLED = bool(os.environ.get('C4_ROUND2_DEP_ROOT'))
if os.environ.get('C4_ROUND2_REQUIRED') == '1' and not ENABLED:
    raise RuntimeError('C4_ROUND2_DEP_ROOT required; actual owner dependencies cannot be replaced by mocks')


@unittest.skipUnless(ENABLED, 'NOT_RUN: exact SHA read-only C1/D2/D3 exports required')
class RealCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from experiments.expansion_20261029.c4_runtime.round2.dependencies import load
        load()
        from . import fixtures
        cls.f = fixtures

    def test_scoped_clear_actual_cores_and_mock_motion(self):
        rt,p,s,c=self.f.setup()
        r=self.f.run(rt,p,s,complete=True)
        self.assertEqual(r.assessment['severity'],'CLEAR',r.intent.reason)
        self.assertEqual(r.intent.severity,'CLEAR')
        gate=FinalIntentPort(rt.context,mode=rt.mode)
        checked=gate.apply(r.intent,now_ns=c.now,issued_ns=c.now,expires_ns=c.now+100_000_000)
        self.assertFalse(checked.hold)
        self.assertEqual(checked.velocity,(.1,0.,0.))
        self.assertFalse(r.adapter_published)
        self.assertFalse(r.native_costmap_ingestion_observed)
        self.assertEqual(r.assessment['validity_interval']['end_monotonic_ns'],1_200_000_000)
        self.assertEqual(r.assessment['freshness']['c4']['original_validity_interval']['until_ns'],'1250000000')
        self.assertEqual(r.intent.valid_until_ns,1_200_000_000)

    def test_model_contact_is_not_physical_contact(self):
        rt,p,s,c=self.f.setup(point_x=.1)
        r=self.f.run(rt,p,s)
        self.assertEqual(r.assessment['reason'],'MODEL_OVERLAP')
        self.assertLess(r.assessment['unpadded_envelope']['min_clearance'],0)
        gate=FinalIntentPort(rt.context,mode=rt.mode)
        checked=gate.apply(r.intent,now_ns=c.now,issued_ns=c.now,expires_ns=c.now+100_000_000)
        self.assertTrue(checked.hold)
        self.assertEqual(checked.velocity,(0.,0.,0.))

    def test_partial_and_empty_are_unknown(self):
        for point in (2.,None):
            rt,p,s,c=self.f.setup(point_x=point)
            r=self.f.run(rt,p,s)
            self.assertEqual(r.assessment['severity'],'UNKNOWN')
            self.assertIn('SPARSE_COVERAGE_NOT_FREE_SPACE',r.assessment['freshness']['issues'])
            self.assertTrue(FinalIntentPort(rt.context,mode=rt.mode).apply(r.intent,now_ns=c.now,issued_ns=c.now,expires_ns=c.now+10).hold)

    def test_scope_mismatch_and_replay_cannot_claim_synthetic_coverage(self):
        for change in ('motion','evidence'):
            rt,p,s,c=self.f.setup()
            att=self.f.coverage(rt,p)
            if change=='motion': att=replace(att,motion_hash='not-this-motion')
            else:
                meta=dict(p.meta,evidence_kind='REPLAY'); sensor=copy.deepcopy(p.sensor_evidence)
                sensor['lidar']['meta']=meta
                p=replace(p,meta=meta,sensor_evidence=sensor); s=dict(s,evidence_kind='REPLAY')
            r=self.f.run(rt,p,s,coverage=att)
            self.assertEqual(r.intent.reason,'COVERAGE_OUTSIDE_MOTION_SCOPE')
            self.assertEqual(r.intent.severity,'UNKNOWN')

    def test_no_camera_detection_invalid_depth_retains_lidar(self):
        for invalid,detected in ((False,False),(True,True),(False,True)):
            rt,p,s,c=self.f.setup()
            p=self.f.rgbd(p,invalid=invalid,detections=detected)
            r=self.f.run(rt,p,s)
            self.assertTrue(r.sensor_processed,r.intent.reason)
            self.assertTrue(any(o['sensor_support']=='LIDAR' for o in r.obstacle_frame['obstacles']))
            self.assertFalse(r.clearing_evidence)

    def test_free_rays_and_source_loss_are_distinct(self):
        rt,p,s,c=self.f.setup()
        sensor=copy.deepcopy(p.sensor_evidence); src=sensor['lidar']
        ray=dict(meta=copy.deepcopy(p.meta),origin=src['origin_m'],free_endpoint=[3.,0.,.3],measurement_valid=True,raw_reference=src['raw_reference'])
        src['free_rays']=[ray]
        r=self.f.run(rt,replace(p,sensor_evidence=sensor),s)
        self.assertEqual(len(r.clearing_evidence),1)
        self.assertTrue(r.raw_observations['lidar']['clearing_candidate'])
        self.assertFalse(r.native_costmap_ingestion_observed)
        rt,p,s,c=self.f.setup(); src['valid_measurement']=False
        r=self.f.run(rt,replace(p,sensor_evidence=sensor),s)
        self.assertEqual(r.intent.severity,'UNKNOWN')
        self.assertFalse(r.clearing_evidence)

    def test_duplicate_reverse_late_and_clock_fail_closed(self):
        rt,p,s,c=self.f.setup(); self.f.run(rt,p,s,complete=True)
        self.assertEqual(self.f.run(rt,p,s).intent.reason,'DUPLICATE_OR_REORDERED_INPUT')
        for change in ('late','clock','future','reverse'):
            rt,p,s,c=self.f.setup()
            if change=='late': c.now+=200_000_000
            elif change=='clock': p=replace(p,clock_epoch='restarted')
            elif change=='future': c.now=999_000_000
            else:
                self.f.run(rt,p,s); p=replace(p,meta=dict(p.meta,sequence=0,stamp_ns='999999999'))
            r=self.f.run(rt,p,s)
            self.assertEqual(r.intent.severity,'UNKNOWN')
            self.assertIsNone(r.assessment)

    def test_all_binding_changes_reject_previous_clear(self):
        for name,value in dict(map_generation=1,family_revision='family-r2',footprint_revision='footprint-r2',controller_goal_id='goal2',authority_generation=2,tf_epoch='tf2').items():
            rt,p,s,c=self.f.setup(); old=self.f.run(rt,p,s,complete=True)
            ctx=replace(rt.context,runtime_generation=2,**{name:value})
            rt.rebind(ctx,rt.mapping)
            gate=FinalIntentPort(ctx,mode=rt.mode)
            self.assertTrue(gate.apply(old.intent,now_ns=c.now,issued_ns=c.now,expires_ns=c.now+10).hold)
            self.assertEqual(self.f.run(rt,p,s).intent.reason,'INPUT_BINDING_MISMATCH')

    def test_advisory_default_missing_authority_and_disconnect(self):
        rt,p,s,c=self.f.setup(active=False)
        r=self.f.run(rt,p,s)
        gate=FinalIntentPort(rt.context)
        self.assertEqual(gate.apply(r.intent,now_ns=c.now,issued_ns=c.now,expires_ns=c.now+10)['action'],'DIAGNOSTIC_ONLY')
        self.assertEqual(len(gate.sink.history),0)
        rt,p,s,c=self.f.setup(); r=self.f.run(rt,p,s,complete=True,authority_present=False)
        self.assertEqual(r.intent.reason,'MISSING_TRUSTED_AUTHORITY')
        self.assertEqual(rt.mode,'ACTIVE_CONSTRAINT')
        rt,p,s,c=self.f.setup(); r=self.f.run(rt,p,s,complete=True)
        gate=FinalIntentPort(rt.context,mode=rt.mode)
        gate.apply(r.intent,now_ns=c.now,issued_ns=c.now,expires_ns=c.now+100_000_000)
        self.assertTrue(gate.tick(now_ns=c.now+100_000_000).hold)

    def test_actual_c1_snapshot_refs_and_expiry(self):
        from robot_dashboard.expansion_services.scene import SceneSnapshotService
        rt,p,s,c=self.f.setup(); r=self.f.run(rt,p,s,complete=True)
        service=SceneSnapshotService(rt.context.map_binding,host_clock_id=rt.context.host_clock_id,clock=c)
        snap=ingest_scene(service,r)
        self.assertEqual(snap['collision_assessment']['severity'],'CLEAR')
        self.assertEqual(snap['collision_assessment']['obstacle_frame_ref'],dict(source_epoch=p.meta['source_epoch'],sequence=1))
        self.assertEqual(snap['obstacle_frame']['received_monotonic_ns'],p.meta['received_monotonic_ns'])
        with self.assertRaisesRegex(ValueError,'C1_OBSTACLE_REJECTED'): ingest_scene(service,r)
        c.now=1_250_000_001
        self.assertIsNone(service.snapshot()['collision_assessment'])

    def test_normalized_pointcloud_to_actual_cores(self):
        from expansion_c4.fixtures import cloud, identity
        from robot_dashboard.obstacle_runtime_adapter.messages import pointcloud2
        from robot_dashboard.expansion_runtime.sensor import packet_from_pointcloud
        rt,p,s,c=self.f.setup()
        ident=identity(source_epoch=rt.context.source_epoch,clock_domain='fixture-clock',receipt_clock_id=rt.context.host_clock_id,
                       map_id=rt.context.map_id,revision=rt.context.map_revision)
        sample=pointcloud2(cloud(),ident,origin_m=(0.,0.,0.))
        tf=dict(verified=True,source_frame='review_lidar',target_frame='odom',stamp_ns=ident.stamp_ns,
                source_epoch=ident.source_epoch,tf_epoch=ident.tf_epoch,clock_domain=ident.clock_domain,
                matrix=[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]])
        packet=packet_from_pointcloud(sample,context=rt.context,clock_epoch=rt.context.clock_epoch,
            transform=tf,calibration_id='synthetic-tf',max_range_m=10.,fov_rad=3.14)
        result=self.f.run(rt,packet,s)
        self.assertTrue(result.sensor_processed,result.intent.reason)
        self.assertEqual(len(result.obstacle_frame['obstacles']),2)
        self.assertEqual(packet.meta['stamp_ns'],ident.stamp_ns)
        self.assertEqual(packet.sensor_evidence['lidar']['sensor_frame'],'review_lidar')
        self.assertFalse(result.clearing_evidence)
        self.assertEqual(sample.payload['raw_data'],cloud().data)
        tf['verified']=False
        with self.assertRaisesRegex(ValueError,'TRANSFORM_REQUIRED'):
            packet_from_pointcloud(sample,context=rt.context,clock_epoch=rt.context.clock_epoch,
                transform=tf,calibration_id='synthetic-tf',max_range_m=10.,fov_rad=3.14)

    def test_real_http_c1_snapshot_and_auth(self):
        from fastapi import FastAPI, HTTPException, Request
        from fastapi.testclient import TestClient
        from robot_dashboard.expansion_services.scene import SceneSnapshotService
        from robot_dashboard.expansion_services.router import create_router
        rt,p,s,c=self.f.setup(); result=self.f.run(rt,p,s,complete=True)
        service=SceneSnapshotService(rt.context.map_binding,host_clock_id=rt.context.host_clock_id,clock=c)
        ingest_scene(service,result)
        async def authorize(request: Request):
            if request.headers.get('authorization') != 'Bearer synthetic-fixture':
                raise HTTPException(401,'fixture authorization required')
        def origin(request):
            raise AssertionError('read-only GET cannot invoke mutation origin policy')
        app=FastAPI()
        app.include_router(create_router(None,None,service,None,authorize=authorize,require_origin=origin))
        with TestClient(app) as client:
            self.assertEqual(client.get('/api/v1/extensions/scene/snapshot').status_code,401)
            response=client.get('/api/v1/extensions/scene/snapshot',headers={'authorization':'Bearer synthetic-fixture'})
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json()['collision_assessment']['severity'],'CLEAR')
            c.now=1_200_000_001
            response=client.get('/api/v1/extensions/scene/snapshot',headers={'authorization':'Bearer synthetic-fixture'})
            self.assertIsNone(response.json()['collision_assessment'])

    def test_processing_delay_does_not_restart_expiry(self):
        rt,p,s,c=self.f.setup()
        original=rt.ports.assess
        def delayed(*args,**kwargs):
            value=original(*args,**kwargs)
            c.now=1_300_000_000
            return value
        rt.ports.assess=delayed  # Delay only; real D3 executes unchanged.
        r=self.f.run(rt,p,s)
        self.assertEqual(r.intent.reason,'ASSESSMENT_EXPIRED_OR_UNMAPPED')
        self.assertEqual(r.assessment['validity_interval']['end_monotonic_ns'],1_250_000_000)
        self.assertEqual(r.assessment['received_monotonic_ns'],s['received_monotonic_ns'])
        self.assertEqual(r.timing['observation_received_monotonic_ns'],p.meta['received_monotonic_ns'])
        self.assertEqual(r.timing['d3_finished_monotonic_ns'],c.now)
        self.assertTrue(FinalIntentPort(rt.context,mode=rt.mode).apply(r.intent,now_ns=c.now,issued_ns=c.now,expires_ns=c.now+10).hold)

    def test_unknown_robot_calibration_has_no_invented_interval(self):
        rt,p,s,c=self.f.setup(); s['calibration_known']=False
        r=self.f.run(rt,p,s)
        self.assertEqual(r.assessment['severity'],'UNKNOWN')
        self.assertEqual(r.assessment['validity_interval'],{})
        self.assertEqual(r.intent.severity,'UNKNOWN')

    def test_free_ray_requires_original_measurement_proof(self):
        rt,p,s,c=self.f.setup()
        sensor=copy.deepcopy(p.sensor_evidence)
        sensor['lidar']['free_rays']=[dict(meta=p.meta,origin=[0.,0.,.3],free_endpoint=[2.,0.,.3])]
        r=self.f.run(rt,replace(p,sensor_evidence=sensor),s)
        self.assertEqual(r.intent.reason,'UNSUPPORTED_FREE_RAY_EVIDENCE')
        self.assertFalse(r.clearing_evidence)

    def test_high_source_stamp_preserved_with_verified_mapping(self):
        from robot_dashboard.expansion_runtime.binding import ClockMapping
        rt,p,s,c=self.f.setup()
        high=2**63
        meta=dict(p.meta,stamp_ns=str(high))
        sensor=copy.deepcopy(p.sensor_evidence); sensor['lidar']['meta']=meta
        p=replace(p,meta=meta,sensor_evidence=sensor)
        s=dict(s,stamp_ns=str(high),joint_stamp_ns=str(high))
        rt.mapping=ClockMapping('fixture-clock',rt.context.source_epoch,rt.context.clock_epoch,rt.context.host_clock_id,
            1_000_000_000-high,0,high-1000,high+1_000_000_000,'SYNTHETIC_EPOCH_OFFSET')
        r=self.f.run(rt,p,s,complete=True)
        self.assertEqual(r.intent.severity,'CLEAR',r.intent.reason)
        self.assertEqual(r.assessment['stamp_ns'],str(high))
        self.assertEqual(r.assessment['freshness']['c4']['original_validity_interval']['until_ns'],str(high+250_000_000))
        self.assertEqual(r.intent.valid_until_ns,1_200_000_000)
