// Synthetic input/registration fixtures; never connects to robot hardware.
import { expect, test } from '@playwright/test';
import { installDashboardBackend } from './dashboard_backend.mjs';
import { GO2_JOINT_NAMES } from '../../robot_dashboard/static/features/maps/observed_joints.js';

test.use({ viewport: { width: 1600, height: 2200 } });

const id = 'a'.repeat(24), revision = 'b'.repeat(64);
const points = [-2,-2,0, 2,-2,0, 2,2,0, -2,2,0, 0,0,1];
const meta = { id, revision, name: 'SYNTHETIC saved 3D reference', kind: 'pointcloud3d', frame_id: 'map',
  format:'pcd-binary', file_name:'fixture.pcd', point_count:5, size_bytes:1000, data_url:`/api/v1/saved-maps/${id}/data` };
function obs(seq, epoch='c', identityUnavailable=false, evidence=null) {
  const received=Date.now()/1000, type=evidence?.kind==='pose'?'nav_msgs/msg/Odometry':'sensor_msgs/msg/PointCloud2';
  const qos={reliability:'BEST_EFFORT',durability:'VOLATILE',history:'KEEP_LAST',depth:1};
  return { observer_id:'d'.repeat(32), publisher_epoch:epoch.repeat(32), publisher_gid:identityUnavailable?null:epoch.repeat(32),
  publisher_count:1, identity_status:identityUnavailable?'UNAVAILABLE':'OBSERVED_PUBLISHER', source_stamp_ns:String(1792309179130175352n+BigInt(seq)),
  received_monotonic_s:received, receipt_clock:'OBSERVER_HOST_MONOTONIC', ...(evidence?{subscription_evidence:{
    schema:'robot-scope.subscription-observation.v1',session_id:evidence.session,topic:evidence.kind==='pose'?'/Odometry':'/cloud_registered',
    type_name:type,subscription_qos:qos,per_message_publisher_verified:false,identity_basis:'LOCAL_SUBSCRIPTION_AND_ROS_GRAPH_ONLY',
    graph:{state:'ok',observed_monotonic_s:received-evidence.graphAge,endpoint_count:1,reported_publisher_count:1,fingerprint:evidence.fingerprint,
      endpoints:[{node_name:'synthetic',node_namespace:'/',topic_type:type,endpoint_gid:'3'.repeat(48),qos}]},
  }}:{}) }; }
function binary(seq, observation, frameId='odom') {
  const metadata = Buffer.from(JSON.stringify({ seq, stream_id:'synthetic-observer', topic:'/cloud_registered', pipeline_stage:'registered',
    frame_id:frameId, units:'m', encoding:'float32le', point_count:points.length/3, source_points:points.length/3, observation }));
  const offset=(16+metadata.length+3)&~3, frame=Buffer.alloc(offset+points.length*4);
  frame.write('RSPC'); frame.writeUInt8(1,4); frame.writeUInt16LE(metadata.length,6);
  frame.writeUInt32LE(points.length/3,8); frame.writeUInt32LE(points.length*4,12); metadata.copy(frame,16);
  points.forEach((v,i)=>frame.writeFloatLE(v,offset+i*4)); return frame;
}
async function fixture(page, {identityUnavailable=false,subscriptionEvidence=false,provisional=false,imu=false,httpFallback=false,joints=false}={}) {
  const state={ streaming:true, rejected:false, epoch:'c', lastCloud:null, jump:false, identityUnavailable,
    session:'1'.repeat(32),fingerprint:'2'.repeat(64),graphAge:.1,nonconverged:false,policyMismatch:false,
    x:0, z:.3, yaw:0, cloudSocketStreaming:true, httpClouds:0, jointsStreaming:true, sitting:false }, writes=[], errors=[];
  const evidence=kind=>subscriptionEvidence?{kind,session:state[`${kind}Session`]??state.session,fingerprint:state.fingerprint,graphAge:state.graphAge}:null;
  let poseSequence=0, cloudSequence=0;
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=> { if(r.method()!=='GET') writes.push(new URL(r.url()).pathname); });
  const nextCloud=()=> {
    if(!state.streaming) return null;
    const seq=++cloudSequence; state.lastCloud=obs(seq,state.epoch,state.identityUnavailable,evidence('cloud'));
    // FAST-LIO supplies a matching pose for each registered scan. Independent
    // timers alone could omit that exact stamp and fail setup on a busy runner.
    if(imu) state.emitPose?.(state.lastCloud.source_stamp_ns);
    return binary(seq,state.lastCloud,imu?'camera_init':'odom');
  };
  const backend=await installDashboardBackend(page,{pointcloudFrame:()=>state.cloudSocketStreaming?nextCloud():null});
  if(httpFallback) backend.on('/api/v1/pointcloud.bin',({route})=>{
    const frame=nextCloud();
    if(!frame) return route.fulfill({status:204,body:''});
    state.httpClouds++;
    return route.fulfill({status:200,contentType:'application/octet-stream',body:frame});
  });
  backend.on('/api/v1/saved-maps',({json})=>json({maps:[meta],total_size_bytes:1000}));
  backend.on(meta.data_url,({json})=>json({...meta,map_id:id,seq:1,points,units:'m',source_points:5}));
  backend.on('/api/v1/observations/map-alignment',({json,body})=>{
    const fallback=body.provenance_mode==='subscription_observation',candidate=fallback?'CANDIDATE_SOURCE_UNVERIFIED':'CANDIDATE';
    const provenance=fallback?{provenance_mode:'subscription_observation',per_message_publisher_verified:false,body_extrinsic_verified:false}:{};
    const originalPolicy={policy_id:'robot-scope.residual-policy.original-0.05m.v1',source_policy_id:'robot-scope.residual-policy.original-0.05m.v1',
      max_rmse_m:.05,original_max_rmse_m:.05,provisional:false,qualifier:'ORIGINAL_RESIDUAL_ONLY',unit:'m',
      evaluation_scope:'STORED_RMSE_ONLY',observation_only:true,no_accuracy_claim:true,accuracy_verified:false};
    const qualification=provisional?{provisional:true,candidate_kind:'PROVISIONAL_OBSERVATION_HYPOTHESIS',
      body_pose:null,tracking_verified:false,body_pose_verified:false,body_extrinsic_verified:false,absolute_accuracy_m:null,
      query_points:100,gate_reasons:state.nonconverged?['NOT_CONVERGED']:[],
      original_assessment:{status:'REJECTED',reason:'HIGH_RESIDUAL',max_rmse_m:.05},
      residual_evaluation:{rmse_m:.07,residual_passed:true,original_residual_passed:false,
        policy:{...originalPolicy,policy_id:'robot-scope.residual-policy.provisional-0.10m.v1',max_rmse_m:.10,
          provisional:true,qualifier:'PROVISIONAL_RESIDUAL_ONLY',unit:state.policyMismatch?'cm':'m'},original_policy:originalPolicy,
        overall_candidate_acceptance_evaluated:false,overall_candidate_accepted:null}}:{};
    return json({schema:'robot-scope.observation-alignment.v1',experimental:true,
    operational_application:'NOT_RUN',map_id:id,map_revision:revision,target_frame:'map',
    ...provenance,...(fallback?{body_pose_verified:false}:{}),...qualification,source:{...body,...provenance,received_monotonic_s:state.lastCloud.received_monotonic_s},
    status:state.rejected||state.nonconverged?'REJECTED':candidate,reason:state.nonconverged?'NOT_CONVERGED':state.rejected?'HIGH_RESIDUAL':candidate,
    T_map_odom:body.T_map_odom_seed,correspondence_gate_m:.75,
    metrics:{converged:!state.nonconverged,rmse_m:provisional?.07:.02,overlap_ratio:.8,geometry_min_max_eigen_ratio:.2,matched_geometry_min_max_eigen_ratio:.2,
      ...(provisional?{inlier_count:80}:{})}});
  });
  if (joints) await page.routeWebSocket('**/api/v1/ws/joints', socket => {
    let seq=0;
    const send=()=>{if(state.jointsStreaming) socket.send(JSON.stringify({state:'ok',topic:'/lowstate',source_order:'unitree_lowstate',
      seq:++seq,age_s:0,order:GO2_JOINT_NAMES,position_rad:Array.from({length:4},()=>state.sitting?[0,1.4,-2.7]:[0,.7,-1.5]).flat()}));};
    send(); const timer=setInterval(send,100); socket.onClose(()=>clearInterval(timer));
  });
  await page.routeWebSocket('**/api/v1/ws/pose',socket=>{
    const send=(sourceStamp=state.lastCloud?.source_stamp_ns)=>{ if(state.streaming) {
      const seq=++poseSequence;
      socket.send(JSON.stringify({seq,topic:'/Odometry',frame_id:imu?'camera_init':'odom',child_frame_id:imu?'body':'base_link',
        state:'ok',age_s:0,position:{x:state.jump?5:state.x,y:0,z:state.z},orientation:{x:0,y:0,z:Math.sin(state.yaw/2),w:Math.cos(state.yaw/2)},
        observation:{...obs(seq,'f',state.identityUnavailable,evidence('pose')),...(imu&&sourceStamp?{source_stamp_ns:sourceStamp}:{})}}));
    } };
    state.emitPose=send;
    send(); const timer=setInterval(()=>send(),150); socket.onClose(()=>{
      clearInterval(timer); if(state.emitPose===send) state.emitPose=null;
    });
  });
  await page.goto('/#maps');
  await page.locator('.saved-map-item').filter({hasText:meta.name}).click();
  await page.evaluate(()=>{
    const original=window.RobotScene3D.prototype.setPointCloudOverlay;
    window.RobotScene3D.prototype.setPointCloudOverlay=function(...args) {
      if(this.canvas.id==='savedSceneCanvas') window.observationScene=this;
      return original.apply(this,args);
    };
  });
  await page.locator('#savedLiveEnabled').check();
  await page.locator('#savedLiveAnchorDetails > summary').click();
  await page.locator('#savedLiveAdvancedDetails > summary').click();
  await page.locator('#savedLiveConfirm').check();
  if(identityUnavailable) await expect(page.locator('#savedLiveState')).toHaveText('SOURCE_IDENTITY_UNAVAILABLE');
  else {
    await expect(page.locator('#savedLiveAnchor')).toBeEnabled();
    await page.locator('#savedLiveAnchor').click();
    await expect(page.locator('#savedLiveState')).toHaveText('ODOMETRY_PROPAGATED_UNVERIFIED');
  }
  return {state,writes,errors,backend};
}

test('observation disclosures keep current result and qualifications visible on narrow screens',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  const {state,errors}=await fixture(page);
  const panel=page.locator('#savedLiveObservation');
  await page.locator('#savedLiveAnchorDetails > summary').click();
  await page.locator('#savedLiveAdvancedDetails > summary').click();
  await expect(page.locator('#savedLive_x')).toBeHidden();
  await expect(page.locator('#savedLiveRegistration')).toBeHidden();
  await expect(page.locator('#savedLiveSource')).toBeHidden();
  await expect(page.locator('#savedLiveState')).toBeVisible();
  await expect(page.locator('#savedLiveMetrics')).toBeVisible();
  await expect(panel.getByText('미검증 추정 · 운영 위치 적용 없음',{exact:true})).toBeVisible();
  expect(await panel.evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
  const sourceSummary=page.locator('#savedLiveSourceDetails > summary');
  await sourceSummary.focus(); await sourceSummary.press('Enter');
  await expect(page.locator('#savedLiveSource')).toBeVisible();
  expect(await panel.evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
  await sourceSummary.press('Enter');
  state.streaming=false;
  await expect(page.locator('#savedLiveState')).toHaveText('STALE');
  await expect(page.locator('#savedLiveState')).toBeVisible();
  await expect(page.locator('#savedLiveSource')).toBeHidden();
  expect(errors).toEqual([]);
});

test('3D observation keeps saved reference, separates scan estimate, and hides stale/rejected geometry',async({page},testInfo)=>{
  const {state,writes,errors}=await fixture(page);
  const original=await page.evaluate(()=>Array.from(window.observationScene.cloud.points));
  await expect(page.locator('#savedLiveCenter')).toBeEnabled();
  expect(await page.evaluate(()=>window.observationScene.pointCloudOverlay.points.length)).toBe(points.length);
  await page.locator('#savedLiveRegistration').check();
  await expect(page.locator('#savedLiveState')).toHaveText('SCAN_TO_MAP_CANDIDATE_UNVERIFIED');
  await page.locator('.saved-map-panel').screenshot({path:testInfo.outputPath('synthetic-3d-observation.png')});
  await page.locator('#savedLiveObservation').screenshot({path:testInfo.outputPath('synthetic-3d-observation-controls.png')});
  state.rejected=true;
  await expect(page.locator('#savedLiveState')).toContainText('REJECTED');
  expect(await page.evaluate(()=>window.observationScene.pointCloudOverlay)).toBeNull();
  await expect(page.locator('#savedLiveCenter')).toBeDisabled();
  expect(await page.evaluate(()=>Array.from(window.observationScene.cloud.points))).toEqual(original);
  await page.locator('#savedLiveRegistration').uncheck();
  state.streaming=false;
  await expect(page.locator('#savedLiveState')).toHaveText('STALE');
  expect(await page.evaluate(()=>window.observationScene.pointCloudOverlay)).toBeNull();
  expect(await page.evaluate(()=>window.observationScene.status.online)).toBeNull();
  expect(writes.every(p=>p==='/api/v1/observations/map-alignment')).toBe(true);
  expect(errors).toEqual([]);
});

test('source replacement and odometry jump require reanchor without robot commands',async({page})=>{
  const {state,writes,errors}=await fixture(page);
  state.epoch='e'; await expect(page.locator('#savedLiveState')).toHaveText('CLOUD_SOURCE_CHANGED');
  await expect(page.locator('#savedLiveCenter')).toBeDisabled();
  await page.locator('#savedLiveAnchor').click(); await expect(page.locator('#savedLiveCenter')).toBeEnabled();
  state.jump=true; await expect(page.locator('#savedLiveState')).toHaveText('POSE_JUMP');
  await expect(page.locator('#savedLiveCenter')).toBeDisabled();
  await page.locator('#slamPackageFilter').selectOption('vslam');
  await expect(page.locator('#savedLiveObservation')).toBeHidden();
  await page.locator('#slamPackageFilter').selectOption('lidar');
  await expect(page.locator('#savedLiveObservation')).toBeVisible();
  await expect(page.locator('#savedLiveCenter')).toBeDisabled();
  expect(writes).toEqual([]); expect(errors).toEqual([]);
});

test('missing publisher metadata shows raw receipt while numerical map alignment stays unavailable',async({page},testInfo)=>{
  const {state,writes,errors}=await fixture(page,{identityUnavailable:true});
  const source=page.locator('#savedLiveSource');
  await expect(page.locator('#savedLiveAvailability')).toContainText('이 ROS runtime에서 메시지별 publisher 정보가 제공되지 않습니다.');
  await expect(page.locator('#savedLiveAvailability')).toContainText('출처 연속성을 확인할 수 없어 기본 저장 지도 정합 계산은 사용할 수 없습니다.');
  await expect(source).toContainText('점군: 원본 수신 · /cloud_registered [odom]');
  await expect(source).toContainText('5점 · source 179230917913017');
  await expect(source).toContainText('native odometry: 원본 수신 · /Odometry [odom → base_link]');
  await expect(source).toContainText('저장 지도 위치·검증된 본체 자세가 아닙니다.');
  await expect(page.locator('#savedLiveMetrics')).toHaveText('지도 정합: UNAVAILABLE · NOT_RUN · 지도 기준 pose·잔차 없음');
  for(const id of ['Anchor','Center','Registration','Export']) await expect(page.locator(`#savedLive${id}`)).toBeDisabled();
  const original=await page.evaluate(()=>Array.from(window.observationScene.cloud.points));
  expect(await page.evaluate(()=>window.observationScene.pointCloudOverlay)).toBeNull();
  expect(await page.evaluate(()=>window.observationScene.robotPose)).toBeNull();
  expect(await page.locator('#savedLiveObservation').evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
  await page.locator('#savedLiveObservation').screenshot({path:testInfo.outputPath('synthetic-identity-unavailable.png')});
  state.streaming=false;
  await expect(source).toContainText('점군: 마지막 수신 · STALE');
  await expect(source).toContainText('native odometry: 마지막 수신 · STALE');
  await page.locator('#savedLiveClear').click();
  await expect(source).toContainText('점군: 현재 수신 요약 없음 | native odometry: 현재 수신 요약 없음');
  await expect(source).not.toContainText('/cloud_registered');
  await page.locator('#savedLiveEnabled').uncheck(); await page.locator('#savedLiveEnabled').check();
  await expect(source).not.toContainText('/Odometry');
  state.streaming=true;
  await expect(source).toContainText('점군: 원본 수신');
  state.identityUnavailable=false;
  await expect(page.locator('#savedLiveAnchor')).toBeEnabled();
  await expect(page.locator('#savedLiveCenter')).toBeDisabled();
  await expect(page.locator('#savedLiveAvailability')).toBeHidden();
  expect(await page.evaluate(()=>window.observationScene.pointCloudOverlay)).toBeNull();
  expect(await page.evaluate(()=>Array.from(window.observationScene.cloud.points))).toEqual(original);
  expect(writes).toEqual([]); expect(errors).toEqual([]);
});

test('subscription graph candidates require explicit opt-in and reanchor after mode or source changes',async({page},testInfo)=>{
  const {state,writes,errors}=await fixture(page,{identityUnavailable:true,subscriptionEvidence:true});
  const allow=page.locator('#savedLiveSourceUnverified'),confirm=page.locator('#savedLiveConfirm');
  await expect(allow).not.toBeChecked();
  await expect(page.locator('#savedLiveAnchor')).toBeDisabled(); expect(writes).toEqual([]);
  await allow.check();
  await expect(confirm).not.toBeChecked(); await expect(page.locator('#savedLiveProvenanceNote')).toBeVisible();
  await expect(page.locator('#savedLiveCenter')).toBeDisabled();
  await confirm.check(); await expect(page.locator('#savedLiveAnchor')).toBeEnabled();
  await page.locator('#savedLiveAnchor').click();
  await expect(page.locator('#savedLiveState')).toHaveText('ODOMETRY_PROPAGATED_SOURCE_UNVERIFIED');
  expect(writes).toEqual([]);
  await page.locator('#savedLiveRegistration').check();
  await expect(page.locator('#savedLiveState')).toHaveText('SCAN_TO_MAP_CANDIDATE_SOURCE_UNVERIFIED');
  await expect(page.locator('#savedLiveProvenanceNote')).toContainText('메시지별 publisher·센서 외부변환·본체 자세는 검증되지 않습니다.');
  expect(await page.evaluate(()=>window.observationScene.options.robotPoseLabel)).toBe('GO2 ESTIMATE · SOURCE UNVERIFIED');
  await page.locator('#savedLiveObservation').screenshot({path:testInfo.outputPath('synthetic-source-unverified-candidate.png')});
  // Deliver the two independent subscription replacements in order. Reanchoring
  // after only the first arrival is correctly invalidated by the second.
  state.poseSession='4'.repeat(32);
  await expect(page.locator('#savedLiveState')).toHaveText('POSE_SOURCE_CHANGED');
  state.cloudSession='4'.repeat(32);
  await expect(page.locator('#savedLiveState')).toHaveText('CLOUD_SOURCE_CHANGED');
  await expect(page.locator('#savedLiveCenter')).toBeDisabled();
  expect(await page.evaluate(()=>window.observationScene.pointCloudOverlay)).toBeNull();
  await page.locator('#savedLiveAnchor').click();
  await expect(page.locator('#savedLiveState')).toHaveText('SCAN_TO_MAP_CANDIDATE_SOURCE_UNVERIFIED');
  await allow.uncheck();
  await expect(confirm).not.toBeChecked(); await expect(page.locator('#savedLiveRegistration')).not.toBeChecked();
  await expect(page.locator('#savedLiveAnchor')).toBeDisabled(); await expect(page.locator('#savedLiveCenter')).toBeDisabled();
  expect(await page.evaluate(()=>window.observationScene.pointCloudOverlay)).toBeNull();
  await expect(page.locator('#savedLiveState')).toHaveText('SOURCE_IDENTITY_UNAVAILABLE');
  expect(writes.length).toBeGreaterThan(0); expect(writes.every(p=>p==='/api/v1/observations/map-alignment')).toBe(true);
  expect(errors).toEqual([]);
});

test('provisional 7cm observation preserves original rejection and clears nonconverged geometry while keeping residual',async({page},testInfo)=>{
  const {state,writes,errors}=await fixture(page,{provisional:true});
  const original=await page.evaluate(()=>Array.from(window.observationScene.cloud.points));
  await page.locator('#savedLiveRegistration').check();
  await expect(page.locator('#savedLiveState')).toHaveText('SCAN_TO_MAP_CANDIDATE_UNVERIFIED');
  const metrics=page.locator('#savedLiveMetrics');
  await expect(metrics).toContainText('RMSE 0.07000 m');
  await expect(metrics).toContainText('잠정 10cm 잔차 통과 · 원본 5cm 잔차 미통과');
  await expect(metrics).toContainText('원본 판정 REJECTED (HIGH_RESIDUAL)');
  await expect(metrics).toContainText('정합 잔차≠실제 위치오차 · 본체/추적 미검증');
  expect(await page.evaluate(()=>window.observationScene.options.robotPoseLabel)).toBe('GO2 ESTIMATE · PROVISIONAL · BODY UNVERIFIED');
  expect(await page.evaluate(()=>window.observationScene.pointCloudOverlay.points.length)).toBe(points.length);
  await page.locator('#savedLiveObservation').screenshot({path:testInfo.outputPath('synthetic-provisional-7cm.png')});
  state.nonconverged=true;
  await expect(page.locator('#savedLiveState')).toContainText('REJECTED · NOT_CONVERGED');
  await expect(metrics).toContainText('RMSE 0.07000 m');
  await expect(metrics).toContainText('잠정 10cm 잔차 통과 · 원본 5cm 잔차 미통과');
  expect(await page.evaluate(()=>window.observationScene.pointCloudOverlay)).toBeNull();
  expect(await page.evaluate(()=>window.observationScene.robotPose)).toBeNull();
  expect(await page.evaluate(()=>Array.from(window.observationScene.cloud.points))).toEqual(original);
  await expect(page.locator('#savedLiveCenter')).toBeDisabled();
  expect(writes.length).toBeGreaterThan(0); expect(writes.every(p=>p==='/api/v1/observations/map-alignment')).toBe(true);
  expect(errors).toEqual([]);
});

test('source-unverified provisional observation still rejects altered residual-policy metadata',async({page})=>{
  const {state,writes,errors}=await fixture(page,{identityUnavailable:true,subscriptionEvidence:true,provisional:true});
  await page.locator('#savedLiveSourceUnverified').check();
  await page.locator('#savedLiveConfirm').check();
  await expect(page.locator('#savedLiveAnchor')).toBeEnabled(); await page.locator('#savedLiveAnchor').click();
  await page.locator('#savedLiveRegistration').check();
  await expect(page.locator('#savedLiveState')).toHaveText('SCAN_TO_MAP_CANDIDATE_SOURCE_UNVERIFIED');
  await expect(page.locator('#savedLiveMetrics')).toContainText('잠정 10cm 잔차 통과 · 원본 5cm 잔차 미통과');
  expect(await page.evaluate(()=>window.observationScene.options.robotPoseLabel)).toBe('GO2 ESTIMATE · PROVISIONAL · SOURCE / BODY UNVERIFIED');
  state.policyMismatch=true;
  await expect(page.locator('#savedLiveState')).toContainText('RESULT_POLICY_MISMATCH');
  expect(await page.evaluate(()=>window.observationScene.pointCloudOverlay)).toBeNull();
  expect(await page.evaluate(()=>window.observationScene.robotPose)).toBeNull();
  await expect(page.locator('#savedLiveMetrics')).not.toContainText('잠정 10cm 잔차 통과');
  expect(writes.length).toBeGreaterThan(0); expect(writes.every(p=>p==='/api/v1/observations/map-alignment')).toBe(true);
  expect(errors).toEqual([]);
});


test('opted-in IMU estimate hides stale input and recovers only an approximate same-session connection', async({page},testInfo)=>{
  const {state,errors}=await fixture(page,{imu:true});
  await page.locator('#savedLiveContinuous').check();
  await page.locator('#savedLiveConfirm').check();
  await page.locator('#savedLiveAnchor').click();
  await expect(page.locator('#savedLiveState')).toContainText('SAME_START_ODOMETRY_ESTIMATE');
  await expect(page.locator('#savedLiveSource')).toContainText('FASTLIO_IMU (body)');
  await expect.poll(()=>page.evaluate(()=>Boolean(window.observationScene.sensorObservationOverlay))).toBe(true);
  expect(await page.evaluate(()=>window.observationScene.robotPose)).toBeNull();
  await page.locator('#savedLiveRegistration').check();
  await expect(page.locator('#savedLiveState')).toContainText('MAP_CORRECTED_ESTIMATE');
  state.rejected=true;
  await expect(page.locator('#savedLiveState')).toContainText('MAP_CORRECTION_UNAVAILABLE_ODOMETRY_CONTINUING');
  await expect(page.locator('#savedLiveCenter')).toBeEnabled();
  await page.locator('#savedLiveCenter').click();
  await page.locator('#savedLiveObservation').screenshot({path:testInfo.outputPath('synthetic-same-start-imu.png')});
  state.streaming=false;
  await expect(page.locator('#savedLiveState')).toHaveText('STALE');
  expect(await page.evaluate(()=>window.observationScene.sensorObservationOverlay)).toBeNull();
  state.streaming=true;
  await expect(page.locator('#savedLiveState')).toHaveText('RECOVERED_APPROXIMATE_ODOMETRY_ESTIMATE');
  await expect(page.locator('#savedLiveCenter')).toBeEnabled();
  state.rejected=false;
  await expect(page.locator('#savedLiveState')).toContainText('MAP_CORRECTED_ESTIMATE');
  state.streaming=false;
  await expect(page.locator('#savedLiveState')).toHaveText('STALE');
  state.epoch='e'; state.streaming=true;
  await expect(page.locator('#savedLiveState')).toHaveText('CLOUD_SOURCE_CHANGED');
  await expect(page.locator('#savedLiveCenter')).toBeDisabled();
  expect(errors).toEqual([]);
});

test('silent pointcloud socket keeps receiving fresh HTTP inputs but stopped sources still hide the pose', async({page})=>{
  const {state,errors}=await fixture(page,{imu:true,httpFallback:true});
  await page.locator('#savedLiveContinuous').check();
  await page.locator('#savedLiveConfirm').check();
  await page.locator('#savedLiveAnchor').click();
  state.cloudSocketStreaming=false;
  const start=state.httpClouds;
  await expect.poll(()=>state.httpClouds).toBeGreaterThan(start+2);
  state.x=.3;
  await expect.poll(()=>page.evaluate(()=>window.observationScene.sensorObservationOverlay?.pose.origin[0])).toBeCloseTo(.3,4);
  await expect(page.locator('#savedLiveCenter')).toBeEnabled();
  state.streaming=false;
  await expect(page.locator('#savedLiveState')).toHaveText('STALE');
  expect(await page.evaluate(()=>window.observationScene.sensorObservationOverlay)).toBeNull();
  expect(errors).toEqual([]);
});

test('moving IMU trail survives same revision and catalogue refresh; changed revision still clears it', async({page})=>{
  const {state,backend,writes,errors}=await fixture(page,{imu:true});
  await page.locator('#savedLiveContinuous').check();
  await page.locator('#savedLiveConfirm').check();
  await page.locator('#savedLiveAnchor').click();
  await page.locator('#savedLiveRegistration').check();
  await expect(page.locator('#savedLiveState')).toContainText('MAP_CORRECTED_ESTIMATE');
  await page.locator('#savedLiveRegistration').uncheck();
  const updated={...meta,name:'SYNTHETIC refreshed label',modified_at:'2026-10-23T08:00:00Z',point_count:6};
  backend.on('/api/v1/saved-maps',({json})=>json({maps:[updated],total_size_bytes:1000}));
  let release, requested=false;
  const pending=new Promise(resolve=>{release=resolve;});
  backend.on(meta.data_url,async({json})=>{
    requested=true; await pending;
    return json({...updated,map_id:id,seq:1,points,units:'m',source_points:6});
  });
  // A completed mapping readback clears the display cache and refreshes the
  // catalogue even when the selected immutable map is unchanged.
  backend.state.mapping.operation={state:'succeeded',kind:'save',job_id:'reload-same',map_name:'synthetic'};
  await expect.poll(()=>requested).toBe(true);
  state.x=.3; state.yaw=Math.PI/6;
  await page.waitForTimeout(350); // Let multiple live render ticks see the pending reload.
  await expect(page.locator('#savedLiveState')).toContainText('MAP_CORRECTED_ESTIMATE');
  await expect(page.locator('#savedLiveCenter')).toBeEnabled();
  await expect.poll(()=>page.evaluate(()=>window.observationScene.sensorObservationOverlay?.pose.origin[0])).toBeCloseTo(.3, 4);
  release();
  await expect(page.locator('#savedLiveState')).toContainText('MAP_CORRECTED_ESTIMATE');
  state.x=.5;
  await expect.poll(()=>page.evaluate(()=>window.observationScene.sensorObservationOverlay?.pose.origin[0])).toBeCloseTo(.5, 4);
  const moved=await page.evaluate(()=>window.observationScene.sensorObservationOverlay);
  expect(Math.atan2(moved.pose.axes[0][1],moved.pose.axes[0][0])).toBeCloseTo(Math.PI/6, 4);
  expect(moved.trail.length).toBeGreaterThan(1);
  expect(moved.trail[0].origin[0]).toBeCloseTo(0, 4);

  const changed={...meta,revision:'e'.repeat(64)};
  backend.on('/api/v1/saved-maps',({json})=>json({maps:[changed],total_size_bytes:1000}));
  let releaseChanged, changedRequested=false;
  const changedPending=new Promise(resolve=>{releaseChanged=resolve;});
  backend.on(meta.data_url,async({json})=>{
    changedRequested=true; await changedPending;
    return json({...changed,map_id:id,seq:1,points,units:'m',source_points:5});
  });
  backend.state.mapping.operation={state:'succeeded',kind:'save',job_id:'reload-changed',map_name:'synthetic'};
  await expect.poll(()=>changedRequested).toBe(true);
  await expect(page.locator('#savedLiveCenter')).toBeDisabled();
  releaseChanged();
  await expect(page.locator('#savedLiveState')).toHaveText('MAP_CHANGED');
  expect(await page.evaluate(()=>window.observationScene.sensorObservationOverlay)).toBeNull();
  expect(writes.every(path=>path==='/api/v1/observations/map-alignment')).toBe(true);
  expect(errors).toEqual([]);
});


test('Go2 URDF sits and moves vertically at IMU origin with measured joints, and expires safely',async({page},testInfo)=>{
  const {state,writes,errors}=await fixture(page,{imu:true,joints:true});
  await expect.poll(()=>page.evaluate(()=>window.observationScene.observedRobotModel?.joints.FR_thigh_joint)).toBe(.7);
  state.sitting=true; state.z=.18;
  await expect.poll(()=>page.evaluate(()=>window.observationScene.observedRobotModel?.joints.FR_thigh_joint)).toBe(1.4);
  await expect(page.locator('#savedLiveHeight')).toContainText('ΔZ -0.120 m');
  await expect.poll(()=>page.evaluate(()=>window.observationScene.observedRobotModel?.pose.z)).toBeCloseTo(-.12,5);
  state.z=.23;
  await expect(page.locator('#savedLiveHeight')).toContainText('ΔZ -0.070 m');
  await expect.poll(()=>page.evaluate(()=>window.observationScene.observedRobotModel?.pose.z)).toBeCloseTo(-.07,5);
  expect(await page.evaluate(()=>window.observationScene.robotPose)).toBeNull();
  await expect.poll(()=>page.evaluate(()=>window.observationScene.observedRobotModel?.body_extrinsic_verified)).toBe(false);
  await page.locator('#savedLiveJointsDetails > summary').click();
  await expect(page.locator('#savedLiveJoint_FR_thigh_joint')).toHaveText('80.2');
  await page.locator('#savedLiveCenter').click();
  await page.locator('#savedSceneCanvas').hover(); await page.mouse.wheel(0,-1600);
  await page.locator('.saved-map-panel').screenshot({path:testInfo.outputPath('synthetic-go2-sitting.png')});
  await page.setViewportSize({width:390,height:1100});
  expect(await page.locator('#savedLiveObservation').evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
  await page.locator('#savedLiveJointsDetails').screenshot({path:testInfo.outputPath('synthetic-go2-joints.png')});
  state.jointsStreaming=false;
  await expect.poll(()=>page.evaluate(()=>window.observationScene.observedRobotModel)).toBeNull();
  await expect(page.locator('#savedLiveJoint_FR_thigh_joint')).toHaveText('—');
  expect(await page.evaluate(()=>Boolean(window.observationScene.sensorObservationOverlay))).toBe(true);
  state.jointsStreaming=true;
  await expect.poll(()=>page.evaluate(()=>Boolean(window.observationScene.observedRobotModel))).toBe(true);
  state.streaming=false;
  await expect(page.locator('#savedLiveState')).toHaveText('STALE');
  expect(await page.evaluate(()=>window.observationScene.observedRobotModel)).toBeNull();
  state.streaming=true;
  await page.locator('#savedLiveConfirm').check(); await page.locator('#savedLiveAnchor').click();
  await expect.poll(()=>page.evaluate(()=>Boolean(window.observationScene.observedRobotModel))).toBe(true);
  state.epoch='e'; await expect(page.locator('#savedLiveState')).toHaveText('CLOUD_SOURCE_CHANGED');
  expect(await page.evaluate(()=>window.observationScene.observedRobotModel)).toBeNull();
  expect(writes).toEqual([]); expect(errors).toEqual([]);
});

test('alignment scheduling waits server cooldown after receipt despite slow dispatch and browser wall clock skew',async({page})=>{
  const {backend,errors}=await fixture(page);
  const calls=[],receipts=[];
  backend.on('/api/v1/observations/map-alignment',async({route})=>{
    const i=calls.length; calls.push(Date.now());
    await new Promise(resolve=>setTimeout(resolve,i===0?450:40));
    const headers=i===0?{'X-Observation-Retry-After-Ms':'730'}:i===1?{}:{'X-Observation-Retry-After-Ms':'1000'};
    receipts.push(Date.now());
    await route.fulfill({status:409,headers,contentType:'application/json',body:JSON.stringify({detail:'RATE_LIMIT_1HZ'})});
  });
  // Wall-clock skew must not affect request eligibility or local expiry.
  await page.evaluate(()=>{const real=Date.now;Date.now=()=>real()+86400000;});
  await page.locator('#savedLiveRegistration').check();
  await expect.poll(()=>calls.length,{timeout:7000}).toBeGreaterThanOrEqual(3);
  expect(calls[1]-receipts[0]).toBeGreaterThanOrEqual(720);
  expect(calls[2]-receipts[1]).toBeGreaterThanOrEqual(990);
  await page.locator('#savedLiveRegistration').uncheck(); expect(errors).toEqual([]);
});

test('Maps observation service start waits for input and requires a fresh anchor; stop uses exact session',async({page},testInfo)=>{
  const {backend,writes}=await fixture(page);
  let session={state:'STOPPED',active:false,session_id:null,can_start:true,can_stop:false,remaining_s:null},starts=0,stops=[];
  backend.on('/api/v1/observations/fastlio',({json})=>json(session));
  backend.on('/api/v1/observations/fastlio/start',({json,body})=>{
    expect(body).toEqual({confirmed:true}); starts++;
    session={state:'WAITING_INPUTS',active:true,session_id:'a'.repeat(32),can_start:false,can_stop:true,remaining_s:1800};
    return json(session);
  });
  backend.on('/api/v1/observations/fastlio/stop',({json,body})=>{
    stops.push(body);session={state:'STOPPED',active:false,session_id:'a'.repeat(32),can_start:true,can_stop:false};return json(session);
  });
  await expect(page.locator('#savedSessionStart')).toBeEnabled();
  await page.locator('#savedSessionStart').click();
  await expect(page.locator('#savedSessionState')).toHaveText('새 입력 수신 대기');
  await expect(page.locator('#savedSessionStart')).toBeDisabled();
  await expect(page.locator('#savedSessionAnchor')).toBeDisabled();
  await expect(page.locator('#savedLiveConfirm')).not.toBeChecked();
  await expect(page.locator('#savedLiveCenter')).toBeDisabled();
  session={...session,state:'READY'};
  await expect(page.locator('#savedSessionAnchor')).toBeEnabled();
  await page.locator('#savedSessionAnchor').click();
  await expect(page.locator('#savedLive_x')).toBeVisible();
  await page.locator('#savedLiveObservation').screenshot({path:testInfo.outputPath('synthetic-observation-session-ready.png')});
  await page.locator('#savedLiveConfirm').check();await page.locator('#savedLiveAnchor').click();
  await expect(page.locator('#savedLiveCenter')).toBeEnabled();
  await page.locator('#savedSessionStop').click();
  await expect(page.locator('#savedSessionState')).toHaveText('관측기 정지');
  await expect(page.locator('#savedLiveCenter')).toBeDisabled();
  expect(starts).toBe(1);expect(stops).toEqual([{confirmed:true,session_id:'a'.repeat(32)}]);
  expect(writes).toEqual(['/api/v1/observations/fastlio/start','/api/v1/observations/fastlio/stop']);
});

test('failed observation start is never retried automatically or shown as registered',async({page})=>{
  const {backend}=await fixture(page);let calls=0,reads=0;
  backend.on('/api/v1/observations/fastlio',({json})=>{reads++;return json({state:'STOPPED',active:false,can_start:true,can_stop:false});});
  backend.on('/api/v1/observations/fastlio/start',({json})=>{calls++;return json({detail:'다른 FAST-LIO가 실행 중입니다.'},409);});
  await expect(page.locator('#savedSessionStart')).toBeEnabled();
  await page.locator('#savedSessionStart').click();
  await expect(page.locator('#savedSessionError')).toContainText('다른 FAST-LIO');
  await expect(page.locator('#savedLiveCenter')).toBeDisabled();
  await expect(page.locator('#savedLiveConfirm')).not.toBeChecked();
  await expect(page.locator('#savedSessionStart')).toBeEnabled();
  const afterFailure=reads;
  await expect.poll(()=>reads).toBeGreaterThan(afterFailure+1);
  await expect(page.locator('#savedSessionError')).toContainText('다른 FAST-LIO');
  expect(calls).toBe(1);
});

test('slow status reads do not swallow start or anchor clicks or overwrite a newer session',async({page})=>{
  const {backend,errors}=await fixture(page);let hold=false,reading=false,release,starts=0;
  let session={state:'STOPPED',active:false,can_start:true,can_stop:false};
  backend.on('/api/v1/observations/fastlio',async({json})=>{
    const captured={...session};
    if(hold){reading=true;await new Promise(resolve=>{release=resolve;});}
    return json(captured);
  });
  backend.on('/api/v1/observations/fastlio/start',({json})=>{
    starts++;session={state:'READY',active:true,session_id:'d'.repeat(32),can_start:false,can_stop:true};return json(session);
  });
  await expect(page.locator('#savedSessionStart')).toBeEnabled();hold=true;
  await expect.poll(()=>reading).toBe(true);
  await expect(page.locator('#savedSessionStart')).toBeEnabled();
  await page.locator('#savedSessionStart').click();
  await expect(page.locator('#savedSessionState')).toHaveText('입력 준비 완료');
  hold=false;release();
  await expect(page.locator('#savedSessionStart')).toBeDisabled();
  reading=false;hold=true;
  await expect.poll(()=>reading).toBe(true);
  await expect(page.locator('#savedSessionAnchor')).toBeEnabled();
  await page.locator('#savedSessionAnchor').click();
  await expect(page.locator('#savedLive_x')).toBeVisible();
  hold=false;release();
  expect(starts).toBe(1);expect(errors).toEqual([]);
});

test('server anchor presets reload editable coordinates without starting or connecting observation',async({page})=>{
  const {backend,writes,errors}=await fixture(page,{imu:true});
  const saved=[], root=`/api/v1/observations/anchor-presets/${id}`;
  backend.on(root,({json,body,request})=>{
    if(request.method()==='POST') {
      const preset={id:'user-'+'c'.repeat(32),label:body.name,values:{map_id:id,...body,units:'metres_degrees',saved_at:'2026-10-24T12:00:00+00:00'}};
      delete preset.values.name; saved.push(preset);return json({preset,approximate_only:true,requires_reanchor:true},201);
    }
    return json({map:{map_id:id,map_revision:revision,map_frame:'map'},presets:saved,incompatible_count:0,approximate_only:true,requires_reanchor:true});
  });
  await page.locator('#savedAnchorPresetRefresh').click();
  await page.locator('#savedLive_x').fill('0.37');await page.locator('#savedLive_yaw').fill('30');
  await page.locator('#savedAnchorPresetName').fill('출입구 · 서 있음');
  await page.locator('#savedAnchorPresetSave').click();
  await expect(page.locator('#savedAnchorPresetStatus')).toContainText('저장 완료');
  await page.locator('#savedLive_x').fill('9');await page.locator('#savedAnchorPresetLoad').click();
  await expect(page.locator('#savedLive_x')).toHaveValue('0.37');
  await expect(page.locator('#savedLive_yaw')).toHaveValue('30');
  await expect(page.locator('#savedLiveConfirm')).not.toBeChecked();
  await expect(page.locator('#savedLiveAnchor')).toBeDisabled();
  await expect(page.locator('#savedLiveRegistration')).not.toBeChecked();
  await page.reload(); await page.locator('.saved-map-item').filter({hasText:meta.name}).click();
  await page.locator('#savedLiveAnchorDetails > summary').click();
  await expect(page.locator('#savedAnchorPresetLoad')).toBeEnabled();
  await page.locator('#savedAnchorPresetLoad').click();
  await expect(page.locator('#savedLive_x')).toHaveValue('0.37');
  await expect(page.locator('#savedLiveConfirm')).not.toBeChecked();
  expect(writes).toEqual([root]);expect(errors).toEqual([]);
});

test('a fresh corrected IMU pose fills editable anchor fields and still requires confirmation',async({page})=>{
  const {state,errors}=await fixture(page,{imu:true});
  await page.locator('#savedLiveRegistration').check();
  await expect(page.locator('#savedLiveState')).toHaveText('SCAN_TO_MAP_CANDIDATE_UNVERIFIED');
  state.x=.2;
  await expect(page.locator('#savedLiveMetrics')).toContainText('X 0.200');
  await expect(page.locator('#savedAnchorPresetCurrent')).toBeEnabled();
  await page.locator('#savedAnchorPresetCurrent').click();
  await expect(page.locator('#savedLive_x')).toHaveValue('0.2');
  await expect(page.locator('#savedLiveConfirm')).not.toBeChecked();
  await expect(page.locator('#savedLiveRegistration')).not.toBeChecked();
  await expect(page.locator('#savedAnchorPresetCurrent')).toBeDisabled();
  expect(errors).toEqual([]);
});

test('preset save errors do not retry writes and loaded body coordinates cannot replace an IMU anchor',async({page})=>{
  const {backend,writes,errors}=await fixture(page,{imu:true});
  const root=`/api/v1/observations/anchor-presets/${id}`;
  backend.on(root,({json,request})=>request.method()==='POST' ? json({detail:'SYNTHETIC_STORAGE_UNAVAILABLE'},503) : json({
    map:{map_id:id,map_revision:revision,map_frame:'map'},presets:[{id:'user-'+'c'.repeat(32),label:'different reference',
      values:{map_id:id,map_revision:revision,map_frame:'map',pose_reference:'UNVERIFIED_BODY',units:'metres_degrees',
        pose:{x:9,y:9,z:9,roll:0,pitch:0,yaw:0},saved_at:'2026-10-24T12:00:00+00:00'}}],
    incompatible_count:0,approximate_only:true,requires_reanchor:true}));
  await page.locator('#savedAnchorPresetRefresh').click();
  await expect(page.locator('#savedAnchorPresetLoad')).toBeEnabled();
  await page.locator('#savedAnchorPresetLoad').click();
  await expect(page.locator('#savedAnchorPresetStatus')).toContainText('기준이 현재 pose와 다릅니다');
  await expect(page.locator('#savedLive_x')).toHaveValue('0');
  await expect(page.locator('#savedLiveConfirm')).toBeChecked();
  await page.locator('#savedAnchorPresetName').fill('test');
  await page.locator('#savedAnchorPresetSave').click();
  await expect(page.locator('#savedAnchorPresetStatus')).toContainText('SYNTHETIC_STORAGE_UNAVAILABLE');
  await page.locator('#savedAnchorPresetRefresh').click();
  await expect(page.locator('#savedAnchorPresetStatus')).toContainText('불러올 수 있는 초기값');
  expect(writes).toEqual([root]);expect(errors).toEqual([]);
});
