// Synthetic input/registration fixtures; never connects to robot hardware.
import { expect, test } from '@playwright/test';
import { installDashboardBackend } from './dashboard_backend.mjs';

test.use({ viewport: { width: 1600, height: 2200 } });

const id = 'a'.repeat(24), revision = 'b'.repeat(64);
const points = [-2,-2,0, 2,-2,0, 2,2,0, -2,2,0, 0,0,1];
const meta = { id, revision, name: 'SYNTHETIC saved 3D reference', kind: 'pointcloud3d', frame_id: 'map',
  format:'pcd-binary', file_name:'fixture.pcd', point_count:5, size_bytes:1000, data_url:`/api/v1/saved-maps/${id}/data` };
function obs(seq, epoch='c') { return { observer_id:'d'.repeat(32), publisher_epoch:epoch.repeat(32), publisher_gid:epoch.repeat(32),
  publisher_count:1, identity_status:'OBSERVED_PUBLISHER', source_stamp_ns:String(1792309179130175352n+BigInt(seq)),
  received_monotonic_s:Date.now()/1000, receipt_clock:'OBSERVER_HOST_MONOTONIC' }; }
function binary(seq, observation) {
  const metadata = Buffer.from(JSON.stringify({ seq, stream_id:'synthetic-observer', topic:'/cloud_registered', pipeline_stage:'registered',
    frame_id:'odom', units:'m', encoding:'float32le', point_count:points.length/3, source_points:points.length/3, observation }));
  const offset=(16+metadata.length+3)&~3, frame=Buffer.alloc(offset+points.length*4);
  frame.write('RSPC'); frame.writeUInt8(1,4); frame.writeUInt16LE(metadata.length,6);
  frame.writeUInt32LE(points.length/3,8); frame.writeUInt32LE(points.length*4,12); metadata.copy(frame,16);
  points.forEach((v,i)=>frame.writeFloatLE(v,offset+i*4)); return frame;
}
async function fixture(page) {
  const state={ streaming:true, rejected:false, epoch:'c', lastCloud:null, jump:false }, writes=[], errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=> { if(r.method()!=='GET') writes.push(new URL(r.url()).pathname); });
  const backend=await installDashboardBackend(page,{ pointcloudFrame:seq=> {
    if(!state.streaming) return null; state.lastCloud=obs(seq,state.epoch); return binary(seq,state.lastCloud);
  }});
  backend.on('/api/v1/saved-maps',({json})=>json({maps:[meta],total_size_bytes:1000}));
  backend.on(meta.data_url,({json})=>json({...meta,map_id:id,seq:1,points,units:'m',source_points:5}));
  backend.on('/api/v1/observations/map-alignment',({json,body})=>json({schema:'robot-scope.observation-alignment.v1',experimental:true,
    operational_application:'NOT_RUN',map_id:id,map_revision:revision,target_frame:'map',
    source:{...body,received_monotonic_s:state.lastCloud.received_monotonic_s},
    status:state.rejected?'REJECTED':'CANDIDATE',reason:state.rejected?'HIGH_RESIDUAL':'CANDIDATE',
    T_map_odom:body.T_map_odom_seed,correspondence_gate_m:.75,
    metrics:{converged:true,rmse_m:.02,overlap_ratio:.8,geometry_min_max_eigen_ratio:.2,matched_geometry_min_max_eigen_ratio:.2}}));
  await page.routeWebSocket('**/api/v1/ws/pose',socket=>{
    let seq=0; const send=()=>{ if(state.streaming) socket.send(JSON.stringify({seq:++seq,topic:'/Odometry',frame_id:'odom',child_frame_id:'base_link',
      state:'ok',age_s:0,position:{x:state.jump?5:0,y:0,z:.3},orientation:{x:0,y:0,z:0,w:1},observation:obs(seq,'f')})); };
    send(); const timer=setInterval(send,150); socket.onClose(()=>clearInterval(timer));
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
  await page.locator('#savedLiveConfirm').check();
  await expect(page.locator('#savedLiveAnchor')).toBeEnabled();
  await page.locator('#savedLiveAnchor').click();
  await expect(page.locator('#savedLiveState')).toHaveText('ODOMETRY_PROPAGATED_UNVERIFIED');
  return {state,writes,errors};
}

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
