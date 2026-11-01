"""Actual pinned dependencies only. No mock validator or simulated C4 algorithms."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import struct
import unittest

import numpy as np
import robot_dashboard
from robot_dashboard.obstacle_fusion_core import Tracker, process_lidar, lift_detections, associate
from robot_dashboard.obstacle_fusion_core.consumer_port import C4CorePort, compact_frame
from experiments.expansion_20261029.d2_perception.scenarios import metadata, rgbd_fixture

ROOT = os.environ.get('D2_DEPENDENCY_ROOT')
MEASUREMENTS = []
if ROOT:
    for role in ('c1','c4'):
        robot_dashboard.__path__.append(str(Path(ROOT)/role/'robot_dashboard'))
    from robot_dashboard.expansion_contracts import ObstacleFrame, canonical, ContractError
    from robot_dashboard.expansion_services.scene import SceneSnapshotService
    from robot_dashboard.obstacle_runtime_adapter.messages import Identity, pointcloud2, Sample
    from robot_dashboard.obstacle_runtime_adapter.c1_ports import C1ObstacleProjection, C1SceneSink
    from robot_dashboard.obstacle_runtime_adapter.runtime import RuntimeAdapter
    from robot_dashboard.obstacle_runtime_adapter.isolation import RuntimeConfig
    from robot_dashboard.obstacle_runtime_adapter.nav2 import observation as nav_observation


def sample(n=1, seq=1, stamp=1_000_000_000, calibration='cal-a'):
    identity=Identity(source_id='lidar',source_epoch='epoch',sequence=seq,stamp_ns=str(stamp),
                      clock_domain='source',frame_id='odom',received_ns=stamp,
                      receipt_clock_id='receiver',tf_epoch='tf-a',map_id='a'*24,revision='b'*64)
    points=[(float(i%8)*.5, float(i//8)*.5,1.) for i in range(n)]
    raw=b''.join(struct.pack('<fff',*p) for p in points)
    message={'header':{'stamp':{'sec':stamp//10**9,'nanosec':stamp%10**9},'frame_id':'odom'},
             'width':n,'height':1,'point_step':12,'row_step':n*12,'data':raw,'is_bigendian':False,
             'fields':[{'name':name,'offset':i*4,'datatype':7,'count':1} for i,name in enumerate('xyz')]}
    value=pointcloud2(message,identity,origin_m=(.2,.1,.3))
    value.payload['metadata']={'calibration_id':calibration}
    return value,message


def port():
    return C4CorePort(canonical=canonical,validate_frame=ObstacleFrame.from_dict,
                      clock_ns=lambda:9_000_000_000)


@unittest.skipUnless(ROOT, 'exact C1/C4 exports required: run round2_check')
class ActualPorts(unittest.TestCase):
    def test_actual_c4_normalization_d2_c1_service(self):
        value,_=sample(8); core=port(); frame=core.process(value)
        projection=C1ObstacleProjection(ObstacleFrame)
        projected=projection(frame).to_dict()
        service=SceneSnapshotService(frame['map_binding'],host_clock_id='receiver',clock=lambda:2_000_000_000)
        self.assertTrue(service.ingest('obstacle_frame',projected))
        snap=service.snapshot()
        self.assertEqual(snap['sources']['obstacle_frame']['received_age_ms'],1000.)
        self.assertEqual(frame['stamp_ns'],'1000000000')
        self.assertEqual(frame['sequence'],1)
        self.assertEqual(frame['received_monotonic_ns'],1_000_000_000)
        self.assertEqual(frame['calibration_id'],'cal-a')
        self.assertEqual(list(frame['input_sources'][0]['sensor_origin_m']),[.2,.1,.3])
        self.assertEqual(frame['obstacles'][0]['geometry'],core.last_result['obstacle_frame']['obstacles'][0]['geometry'])
        self.assertEqual(frame['input_sources'][0]['field_layout'],value.payload['fields'])
        self.assertFalse(frame['health']['postprocess']['renews_observation'])

    def test_actual_c4_async_worker_to_actual_c1_sink(self):
        async def run():
            value,message=sample(16); projection=C1ObstacleProjection(ObstacleFrame)
            service=SceneSnapshotService(value.identity.packet()['map_binding'],host_clock_id='receiver',clock=lambda:1_050_000_000)
            sink=C1SceneSink(service,obstacle_projection=projection)
            runtime=RuntimeAdapter(d2=port(),scene_sink=sink,validate_obstacle=ObstacleFrame.from_dict,
                source_epochs={'lidar':'epoch'},binding=value.identity.binding,receipt_clock_id='receiver',
                config=RuntimeConfig(mode='synthetic'),clock_ns=lambda:1_050_000_000)
            runtime.start()
            try:
                self.assertTrue(runtime.offer_raw(message,value.identity,pointcloud2,origin_m=(.2,.1,.3)))
                for _ in range(100):
                    if runtime.latest_scene is not None or runtime.worker.error: break
                    await asyncio.sleep(.01)
                self.assertIsNone(runtime.worker.error)
                self.assertIsNotNone(runtime.latest_scene)
                frame=service.snapshot()['obstacle_frame']; self.assertEqual(len(frame['obstacles']),16)
                self.assertEqual(frame['stamp_ns'],value.identity.stamp_ns)
                self.assertEqual(frame['received_monotonic_ns'],value.identity.received_ns)
                self.assertFalse(runtime.offer_raw(message,value.identity,pointcloud2))
            finally: await runtime.close()
        asyncio.run(run())

    def test_payload_limits_no_geometry_truncation(self):
        for n in (1,8,16,32,64):
            value,_=sample(n); core=port()
            try: frame=core.process(value)
            except ValueError as exc:
                self.assertIn('FRAME_BUDGET_EXCEEDED',str(exc))
                self.assertEqual(len(core.last_result['obstacle_frame']['obstacles']),n)
                MEASUREMENTS.append({'objects':n,'port':'REJECTED_NO_TRUNCATION','reason':str(exc)})
                continue
            projected=C1ObstacleProjection(ObstacleFrame)(frame).to_dict()
            service=SceneSnapshotService(frame['map_binding'])
            self.assertTrue(service.ingest('obstacle_frame',projected))
            self.assertEqual(len(projected['obstacles']),n)
            MEASUREMENTS.append({'objects':n,'port':'ACCEPTED','d2_bytes':len(canonical(frame)),
                                 'c4_projection_bytes':len(canonical(projected)),
                                 'sha256':hashlib.sha256(canonical(projected)).hexdigest()})
        value,_=sample(64); full=port()
        with self.assertRaises(ValueError): full.process(value)
        frame=full.last_result['obstacle_frame']
        ObstacleFrame.from_dict(frame)  # 128 KiB wire validator permits this.
        with self.assertRaises(ContractError): SceneSnapshotService(frame['map_binding']).ingest('obstacle_frame',frame)

    def test_actual_negative_contract_and_source_fences(self):
        value,_=sample(); core=port(); first=core.process(value)
        for mutate in (lambda f:f.update(stamp_ns=1000),lambda f:f.update(schema_version='v99'),lambda f:f.update(published_to_nav2=True)):
            bad=deepcopy(first);mutate(bad)
            with self.assertRaises(ContractError): ObstacleFrame.from_dict(bad)
        invalid=replace(value,identity=replace(value.identity,map_id='not-c1-map-id'))
        with self.assertRaises(ContractError): port().process(invalid)
        malformed=deepcopy(value)
        malformed.payload['xyz_m']=((float('nan'),0.,0.),)
        # Transport/core invalid-point evidence is not an invented obstacle.
        self.assertEqual(port().process(malformed)['obstacles'],[])
        with self.assertRaisesRegex(ValueError,'DUPLICATE'): core.process(value)
        changed,_=sample(seq=2,stamp=1_100_000_000,calibration='cal-b')
        second=core.process(changed)
        self.assertNotEqual(first['obstacles'][0]['track_id'],second['obstacles'][0]['track_id'])
        backward,_=sample(seq=3,stamp=1_050_000_000,calibration='cal-c')
        with self.assertRaisesRegex(ValueError,'REORDERED'): core.process(backward)
        old,_=sample(seq=3,stamp=1_200_000_000,calibration='cal-a')
        with self.assertRaisesRegex(ValueError,'RETIRED'): core.process(old)
        wrong,_=sample(seq=3,stamp=1_200_000_000,calibration='cal-b')
        wrong=replace(wrong,identity=replace(wrong.identity,revision='c'*64))
        with self.assertRaisesRegex(ValueError,'MAP_GENERATION'): core.process(wrong)

    def test_multi_sensor_origins_extent_and_no_detection_clearing(self):
        m=metadata();m['sensor_origin_m']=[0,0,0]
        lidar=process_lidar([[0,0,1],[.03,0,1]],m)
        d,z,c,model=rgbd_fixture(m); c['meta']=deepcopy(m)
        dm=deepcopy(m);dm['sensor_origin_m']=[.2,0,0]
        depth=lift_detections(d,z,dm,calibration=c,model_manifest=model)
        fused=associate(lidar,depth)
        result=Tracker().step(fused)
        compact=compact_frame(result['obstacle_frame'],canonical=canonical)
        sources=compact['input_sources']
        self.assertEqual({tuple(s['sensor_origin_m']) for s in sources},{(0,0,0),(.2,0,0)})
        self.assertEqual(compact['obstacles'][0]['geometry'],result['obstacle_frame']['obstacles'][0]['geometry'])
        self.assertEqual(result['clearing_evidence'],[])
        self.assertEqual(associate(lidar,{'meta':dm,'obstacles':[]})['obstacles'],lidar['obstacles'])
        c['verified']=False
        self.assertEqual(lift_detections(d,z,dm,calibration=c,model_manifest=model)['obstacles'],[])
        self.assertEqual(lift_detections([],z,dm)['obstacles'],[])
        self.assertEqual(lift_detections(d,np.zeros_like(z),dm,calibration=c,model_manifest=model)['obstacles'],[])

    def test_epoch_clock_reset_occupancy_ttl_not_free(self):
        value,_=sample(); core=port(); first=core.process(value)
        next_value,_=sample(seq=2,stamp=1_100_000_000)
        next_value=replace(next_value,identity=replace(next_value.identity,clock_domain='other-clock'))
        second=core.process(next_value)
        self.assertNotEqual(first['obstacles'][0]['track_id'],second['obstacles'][0]['track_id'])
        new_epoch,_=sample(seq=1,stamp=100)
        new_epoch=replace(new_epoch,identity=replace(new_epoch.identity,source_epoch='epoch-2'))
        core.process(new_epoch)
        with self.assertRaisesRegex(ValueError,'RETIRED'): core.process(value)
        self.assertEqual(core.last_result['clearing_evidence'],[])
        with self.assertRaisesRegex(ValueError,'PAIRED_RGBD'): core.process(Sample(new_epoch.identity,'detections',{'detections':[]}))

    def test_c4_marking_reuses_source_time_and_two_ray_origins(self):
        value,_=sample()
        core=port(); core.process(value)
        marked=nav_observation(value,topic='/review/geometry_marking',source_kind='geometry',
                               now_ns=1_100_000_000,receipt_clock_id='receiver')
        self.assertEqual(marked.sample.identity.stamp_ns,'1000000000')
        self.assertFalse(marked.clearing)
        with self.assertRaisesRegex(ValueError,'STALE'):
            nav_observation(value,topic='/review/geometry_marking',source_kind='geometry',
                            now_ns=9_000_000_000,receipt_clock_id='receiver')
        m=metadata(); rays=[{'meta':deepcopy(m),'origin':origin,'free_endpoint':[1,0,0]}
                            for origin in ([0,0,0],[.2,0,0])]
        tracker=Tracker(); result=tracker.step(process_lidar([[1,0,1]],m),clearing_rays=rays)
        self.assertEqual(result['clearing_evidence'],rays)
        empty=process_lidar(np.empty((0,3)),metadata(1_100_000_000,2))
        occluded=tracker.step(empty)
        compact=compact_frame(occluded['obstacle_frame'],canonical=canonical)
        obj=compact['obstacles'][0]
        self.assertEqual(obj['state'],'OCCLUDED')
        source=compact['input_sources'][obj['provenance']['source_ref']]
        self.assertEqual(source['stamp_ns'],'1000000000')
        self.assertEqual(obj['last_seen_ns'],'1000000000')
        self.assertEqual(occluded['clearing_evidence'],[])
