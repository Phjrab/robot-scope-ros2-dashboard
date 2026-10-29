"""Read only an exact D3 native artifact. No ROS process or new simulation.

C1 receives a historical slice at its original recorded host receipt time. No
source->host equality is inferred. Full source records stay in display-only
assets; the browser's explicit test profile only decimates display cost cells.
"""
import base64
import hashlib
import json
import zipfile
import zlib

ARTIFACT_ID=12882393645
ZIP_SHA256='0f09cf101555dbef3368fc6913acd9cdd61e380ad45c51472ea5e6b1b3cdc6aa'
NATIVE_SHA='fa8e26e02194d3c99ccc7b8e45eb3177a6fce19d'

def add_native_replay(path,host,output,apps,contexts,token):
    raw=path.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==ZIP_SHA256,'Native artifact hash mismatch'
    with zipfile.ZipFile(path) as archive:
        assert archive.read('source-sha.txt').decode().strip()==NATIVE_SHA
        prefix='diagnostic_appearing_obstacle/run/'
        records=[json.loads(line) for line in archive.read(prefix+'observations.jsonl').splitlines()]
        traces=[json.loads(line) for line in archive.read(prefix+'trace.jsonl').splitlines()]
        result=json.loads(archive.read(prefix+'result.json'))
        input_hashes={name:hashlib.sha256(archive.read(prefix+name)).hexdigest() for name in ('observations.jsonl','trace.jsonl','result.json','validation.json')}
    plan=next(r for r in records if r['kind']=='path' and r['source_elapsed_s']>=3.7)
    cost=next(r for r in records if r['kind']=='costmap' and r['source_elapsed_s']>=3.6)
    pose=min(traces,key=lambda r:abs(r['sim_t']-plan['sim_t']))
    # These records expose receipt as double seconds, not original integer ns.
    # Conversion is explicitly rounded and never advertised as nanosecond capture precision.
    receipt=lambda r,key='receipt_monotonic':round(r[key]*1e9)
    now=max(receipt(plan),receipt(cost),receipt(pose,'monotonic'))
    name='NATIVE_REPLAY';app=host.create_test_host(output/'native-replay',token);scene=app.state.c1[2]
    binding=dict(map_id=result['fixture_sha256'][:24],revision=result['fixture_sha256'],generation=7)
    scene.schema_version='0.2';scene.host_clock_id='native-recording-fa8e26e';scene.reset(binding,'native-recorded-scene');scene.clock=lambda:now
    def observation(r,seq,data,clock_key='source_sim_s',receipt_key='receipt_monotonic'):
        return dict(schema_version='0.2',evidence_kind='REPLAY',producer='d3.native-recorded',sequence=seq,
            source_epoch='native-recorded',frame_key=dict(source_epoch='native-recorded',frame_id='map'),
            stamp_ns=str(round(r[clock_key]*1e9)),clock_domain='native-recorded-sim',host_clock_id='native-recording-fa8e26e',
            received_monotonic_ns=str(receipt(r,receipt_key)),map_binding=binding,
            data=data,health=dict(state='RECORDED_NATIVE_SIM',artifact_id=ARTIFACT_ID,native_sha=NATIVE_SHA,
                receipt_precision='RECORDED_FLOAT_SECONDS_ROUNDED_TO_NS',source_record=r))
    path_data=dict(points_m=plan['points'],dimensions=2,representation='2D_GROUND_PLANE',plane_z_m=0,
        generation='native-plan-after-appearance',replanning_reason='RECORDED_NATIVE_PLAN',provenance=dict(artifact_id=ARTIFACT_ID,record=plan))
    # C1 generic per-sample payload stays bounded; the full repeated record is kept in the report.
    plan_wire=observation(plan,1,path_data);plan_wire['health'].pop('source_record');path_data['provenance'].pop('record')
    raw_cells=zlib.decompress(base64.b64decode(cost['data_zlib_base64']))
    assert len(raw_cells)==cost['width']*cost['height']
    cells=[v if v<128 else v-256 for v in raw_cells]
    assert all(-1<=v<=100 for v in cells)
    payload=dict(profile='c3-test-display-v1',map_binding=binding,costmap=dict(id='native-costmap',width=cost['width'],height=cost['height'],
        cell_encoding='OCCUPANCY_PERCENT',cells=cells,origin=[*cost['origin'],0],resolution_m=cost['resolution'],plane_z_m=0,representation='2D_GROUND_PLANE'),
        provenance=dict(artifact_id=ARTIFACT_ID,native_sha=NATIVE_SHA,original=cost,usage='DISPLAY_ONLY'))
    asset=scene.publish_asset('costmap','costmap_snapshot',json.dumps(payload,separators=(',',':')).encode(),media_type='application/json')
    cost_wire=observation(cost,1,dict(asset_ref=asset));cost_wire['health'].pop('source_record')
    pose_wire=observation(pose,1,dict(position_m=[*pose['pose'][:2],0],rpy_rad=[0,0,pose['pose'][2]],
        provenance=dict(pose_source='RECORDED_SIM_GT',joints='UNAVAILABLE',calibration='UNAVAILABLE')),clock_key='sim_t',receipt_key='monotonic')
    for slot,value in [('robot_pose',pose_wire),('global_path',plan_wire),('costmap_snapshot',cost_wire)]:assert scene.ingest(slot,value),slot
    apps[name]=app
    contexts[name]=dict(binding,frame_id='map',source_epoch='native-recorded',stream_epoch='native-recorded-scene',
        clock_domain='native-recorded-sim',calibration_id='native-not-supplied',units='m',source_identity='D3_NATIVE_FIXTURE_NOT_MERGED_MAP')
    return dict(artifact_id=ARTIFACT_ID,zip_sha256=ZIP_SHA256,native_sha=NATIVE_SHA,input_hashes=input_hashes,
        source_records=dict(plan=plan,costmap=cost,pose=pose),replay_clock_ns=str(now),snapshot=scene.snapshot(),
        classification='ACTUAL_C1_HTTP_REPLAY_OF_RECORDED_NATIVE_SIM; NO_LOCAL_ROS_OR_NATIVE_EXECUTION',
        missing=['joint_state','collision_assessment','controller_local_trajectory'],
        protection='NEW_D3_URDF_ADVISORY_ONLY_IN_NATIVE_SOURCE; NO_C3_COMMAND_AUTHORITY',
        full_costmap_cells=len(cells),source_costmap_cells_sha256=hashlib.sha256(raw_cells).hexdigest())
