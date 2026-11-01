import { expect, test } from '@playwright/test';
import { installDashboardBackend } from './dashboard_backend.mjs';

async function fixture(page, fill = 0) {
  const b = await installDashboardBackend(page);
  const id3='f'.repeat(24), rev3='e'.repeat(64);
  const loc={map_id:id3,revision:rev3}, nav={map_id:b.mapId,revision:b.mapRevision};
  const selected={workflow:'staged_navigation_pair',generation:'a'.repeat(32),localization_3d:loc,navigation_2d:nav,calibration:{verified:true},seed_geometry:null};
  const pair={valid:true,can_start:false,generation:selected.generation,localization_3d:loc,navigation_2d:nav,checks:[{code:'INITIAL_HEIGHT_TILT_REQUIRED'}]};
  const status={selected,pair,activation:'NEXT_NAVIGATION_START',initialization_handoff:null};
  const cells=Buffer.alloc(64*48, fill);
  b.on('/api/v1/saved-maps',({json})=>json({total_size_bytes:4096,maps:[
    {id:b.mapId,revision:b.mapRevision,name:'2d',kind:'occupancy2d',format:'map-server-pgm',frame_id:'map',data_url:`/api/v1/saved-maps/${b.mapId}/data`},
    {id:id3,revision:rev3,name:'3d',kind:'pointcloud3d',format:'pcd',frame_id:'camera_init'}]}));
  b.on(`/api/v1/saved-maps/${b.mapId}/data`,({json})=>json({map_id:b.mapId,revision:b.mapRevision,name:'2d',frame_id:'map',width:64,height:48,resolution:.05,origin:[0,0,0],data_b64:cells.toString('base64')}));
  b.on('/api/v1/navigation/operational-3d/preparation-inputs',({json})=>json({schema:'robot-scope.navigation-preparation-inputs.v1',pair,observation:{state:'STOPPED',active:false,can_start:false,can_stop:false},evidence:{valid:false,reason:'OBSERVATION_INACTIVE'},start_blockers:{items:['CONTROL_BRIDGE_NOT_INACTIVE']},candidates:{},operational_state:status,operational_state_error:null}));
  Object.assign(b.state.navigation,{pipeline:{state:'idle',job_id:null},safety:{can_set_initial_pose:false,can_send_goal:false,blockers:[]}});
  await page.goto('/#navigation');
  await expect(page.locator('#navigationInitialPoseTool')).toBeEnabled();
  return {b,selected,pair,status};
}
async function stage(page) {
 await page.locator('#navigationInitialPoseTool').click(); const canvas=page.locator('#navigationMapCanvas'); await canvas.scrollIntoViewIfNeeded(); const box=await canvas.boundingBox();
 await page.mouse.move(box.x+box.width*.5,box.y+box.height*.5);await page.mouse.down();await page.mouse.move(box.x+box.width*.58,box.y+box.height*.43,{steps:4});await page.mouse.up();
 await expect(page.locator('#navigationPoseMode')).toContainText('미전송 로컬 초안');
}
test('idle draft is local, non-sendable, invalidated by pair change and runtime start', async ({page})=>{
 const {b,selected,pair}=await fixture(page); await stage(page);
 await expect(page.locator('#navigationPoseCoordinates')).toContainText('실제 위치와 높이·기울기 확인 아님');
 await expect(page.locator('#navigationPoseSend')).toBeDisabled();await expect(page.locator('#navigationGoalPoseTool')).toBeDisabled();
 expect(b.state.requests).toEqual([]);
 selected.generation=pair.generation='b'.repeat(32);
 await expect(page.locator('#navigationPoseMode')).not.toContainText('초안');
 await stage(page);
 b.state.navigation.pipeline={state:'running',job_id:'2'.repeat(32)};
 b.state.navigation.safety.can_set_initial_pose=true;
 b.state.navigation.map={id:b.mapId,revision:b.mapRevision};
 await expect(page.locator('#navigationPoseMode')).toContainText('이전 미전송 초안 · 미확인');
 await expect(page.locator('#navigationPoseSend')).toBeDisabled();
 expect(b.state.requests).toEqual([]);
});
test('reload clears draft and active runtime initial placement retains existing send gate', async ({page})=>{
 const {b}=await fixture(page);await stage(page);await page.reload();
 await expect(page.locator('#navigationInitialPoseTool')).toBeEnabled();await expect(page.locator('#navigationPoseMode')).not.toContainText('초안');
 b.state.navigation.pipeline={state:'running',job_id:'2'.repeat(32)};b.state.navigation.map={id:b.mapId,revision:b.mapRevision};b.state.navigation.safety.can_set_initial_pose=true;
 await expect(page.locator('#navigationPipelineState')).toHaveText('RUNNING');
 await expect(page.locator('#navigationInitialPoseTool')).toBeEnabled();
 await page.locator('#navigationInitialPoseTool').click();const canvas=page.locator('#navigationMapCanvas');await canvas.scrollIntoViewIfNeeded();const box=await canvas.boundingBox();
 await page.mouse.move(box.x+box.width*.5,box.y+box.height*.5);await page.mouse.down();await page.mouse.move(box.x+box.width*.58,box.y+box.height*.43);await page.mouse.up();
 await expect(page.locator('#navigationPoseMode')).toHaveText('INITIAL · STAGED');await expect(page.locator('#navigationPoseSend')).toBeEnabled();
 expect(b.state.requests).toEqual([]);
});

for (const [label, fill] of [['unknown', 255], ['occupied', 100]]) {
 test(`pre-draft rejects ${label} map cells`, async ({page}) => {
  const {b}=await fixture(page,fill); await page.locator('#navigationInitialPoseTool').click();
  const canvas=page.locator('#navigationMapCanvas');await canvas.scrollIntoViewIfNeeded();const box=await canvas.boundingBox();
  await page.mouse.move(box.x+box.width*.5,box.y+box.height*.5);await page.mouse.down();await page.mouse.move(box.x+box.width*.58,box.y+box.height*.43);await page.mouse.up();
  await expect(page.locator('#navigationMapHint')).toContainText(label === 'unknown' ? 'UNKNOWN' : 'OCCUPIED');
  await expect(page.locator('#navigationPoseCoordinates')).toContainText('X —');await expect(page.locator('#navigationPoseSend')).toBeDisabled();
  expect(b.state.requests).toEqual([]);
 });
}
test('pre-draft is discarded when runtime changes during a drag', async ({page}) => {
 const {b}=await fixture(page); await page.locator('#navigationInitialPoseTool').click();
 const canvas=page.locator('#navigationMapCanvas');await canvas.scrollIntoViewIfNeeded();const box=await canvas.boundingBox();
 await page.mouse.move(box.x+box.width*.5,box.y+box.height*.5);await page.mouse.down();await page.mouse.move(box.x+box.width*.56,box.y+box.height*.45);
 await expect(page.locator('#navigationPoseMode')).toContainText('미전송 로컬 초안');
 b.state.navigation.pipeline={state:'running',job_id:'2'.repeat(32)};b.state.navigation.map={id:b.mapId,revision:b.mapRevision};b.state.navigation.safety.can_set_initial_pose=true;
 await expect(page.locator('#navigationPipelineState')).toHaveText('RUNNING');
 await page.mouse.move(box.x+box.width*.58,box.y+box.height*.43);await page.mouse.up();
 await expect(page.locator('#navigationPoseMode')).toHaveText('NO TOOL');await expect(page.locator('#navigationPoseSend')).toBeDisabled();
 await page.locator('#navigationPoseSend').dispatchEvent('click');expect(b.state.requests).toEqual([]);
});

test('pending pair mutation invalidates drafts until a fresh preparation read succeeds', async ({page}) => {
 const {b,pair,status}=await fixture(page);await stage(page);
 let releasePair,releaseRead,releaseClear,pairEntered=false,readEntered=false,clearEntered=false,holdRead=true,failRead=false;
 const pairGate=new Promise(r=>releasePair=r),readGate=new Promise(r=>releaseRead=r),clearGate=new Promise(r=>releaseClear=r);
 b.on('/api/v1/navigation/operational-3d/pair',async ({json})=>{pairEntered=true;await pairGate;return json(status);});
 b.on('/api/v1/navigation/operational-3d',async ({json})=>{clearEntered=true;await clearGate;return json({detail:'synthetic conflict'},409);});
 b.on('/api/v1/navigation/operational-3d/preparation-inputs',async ({json})=>{
  if (holdRead) {readEntered=true;await readGate;}
  if (failRead) return json({detail:'synthetic read failure'},503);
  return json({schema:'robot-scope.navigation-preparation-inputs.v1',pair,observation:{state:'STOPPED',active:false,can_start:false,can_stop:false},evidence:{valid:false,reason:'OBSERVATION_INACTIVE'},start_blockers:{items:['CONTROL_BRIDGE_NOT_INACTIVE']},candidates:{},operational_state:status,operational_state_error:null});
 });
 await page.locator('[data-prep="pair"]').click();await expect.poll(()=>pairEntered).toBe(true);
 await expect(page.locator('#navigationPoseMode')).toHaveText('NO TOOL');await expect(page.locator('#navigationInitialPoseTool')).toBeDisabled();
 await page.locator('#navigationInitialPoseTool').dispatchEvent('click');await page.locator('#navigationPoseSend').dispatchEvent('click');
 releasePair();await expect.poll(()=>readEntered).toBe(true);await expect(page.locator('#navigationInitialPoseTool')).toBeDisabled();
 holdRead=false;releaseRead();await expect(page.locator('#navigationInitialPoseTool')).toBeEnabled();
 await stage(page);failRead=true;
 await page.locator('[data-prep="clear"]').click();await expect.poll(()=>clearEntered).toBe(true);
 await expect(page.locator('#navigationPoseMode')).toHaveText('NO TOOL');await expect(page.locator('#navigationInitialPoseTool')).toBeDisabled();
 releaseClear();await expect(page.locator('[data-prep="issues"]')).toContainText('현재 준비 상태 수신 실패');
 await expect(page.locator('#navigationInitialPoseTool')).toBeDisabled();await page.locator('#navigationPoseSend').dispatchEvent('click');
 failRead=false;await page.locator('[data-prep="refresh"]').click();
 await page.locator('#navigationLocalizationMapSelect').selectOption('f'.repeat(24));await expect(page.locator('#navigationInitialPoseTool')).toBeEnabled();
 expect(b.state.requests.filter(r=>/\/navigation\/(initial-pose|goal)$/.test(r.path))).toEqual([]);
});

for (const oldResult of ['success', 'failure']) {
test(`old preparation ${oldResult} cannot roll back state or revalidate a draft across a pair mutation`, async ({page}) => {
 const {b,selected,pair,status}=await fixture(page);await stage(page);
 let releaseOld,releaseNew,oldEntered=false,newEntered=false,pairEntered=false,readNumber=0;
 const oldGate=new Promise(r=>releaseOld=r),newGate=new Promise(r=>releaseNew=r);
 const response=()=>({schema:'robot-scope.navigation-preparation-inputs.v1',pair,observation:{state:'STOPPED',active:false,can_start:false,can_stop:false},evidence:{valid:false,reason:'OBSERVATION_INACTIVE'},start_blockers:{items:['CONTROL_BRIDGE_NOT_INACTIVE']},candidates:{},operational_state:status,operational_state_error:null});
 b.on('/api/v1/navigation/operational-3d/preparation-inputs',async ({json})=>{
  const snapshot=structuredClone(response());const n=++readNumber;
  if(n===1){oldEntered=true;await oldGate;if(oldResult==='failure')return json({detail:'old read failed'},503);}else if(n===2){newEntered=true;await newGate;}
  return json(snapshot);
 });
 b.on('/api/v1/navigation/operational-3d/pair',({json})=>{pairEntered=true;selected.generation=pair.generation='b'.repeat(32);return json(status);});
 await page.locator('[data-prep="refresh"]').click();await expect.poll(()=>oldEntered).toBe(true);
 await page.locator('[data-prep="pair"]').click();await expect.poll(()=>pairEntered).toBe(true);
 await expect(page.locator('#navigationPoseMode')).toHaveText('NO TOOL');await expect(page.locator('#navigationInitialPoseTool')).toBeDisabled();
 releaseOld();await expect.poll(()=>newEntered).toBe(true);await expect(page.locator('#navigationInitialPoseTool')).toBeDisabled();
 await expect.poll(async () => JSON.parse(await page.locator('[data-prep="details"]').textContent()).selected?.generation).toBe('b'.repeat(32));
 releaseNew();await expect(page.locator('#navigationInitialPoseTool')).toBeEnabled();await expect(page.locator('#navigationPoseMode')).toHaveText('NO TOOL');
 await page.locator('#navigationPoseSend').dispatchEvent('click');
 expect(b.state.requests.filter(r=>/\/navigation\/(initial-pose|goal)$/.test(r.path))).toEqual([]);
});
}


test('draft survives transient preparation read failure as unconfirmed without sending', async ({page}) => {
 const {b,selected,pair,status}=await fixture(page); await stage(page);
 const coords=await page.locator('#navigationPoseCoordinates').textContent(); let failing=true;
 b.on('/api/v1/navigation/operational-3d/preparation-inputs',({json})=> failing ? json({detail:'temporary offline'},503) : json({schema:'robot-scope.navigation-preparation-inputs.v1',pair,observation:{state:'STOPPED',active:false,can_start:false,can_stop:false},evidence:{valid:false,reason:'OBSERVATION_INACTIVE'},start_blockers:{items:['CONTROL_BRIDGE_NOT_INACTIVE']},candidates:{},operational_state:status,operational_state_error:null}));
 await page.locator('[data-prep="refresh"]').click(); await expect(page.locator('[data-prep="issues"]')).toContainText('현재 준비 상태 수신 실패');
 await expect(page.locator('#navigationPoseCoordinates')).toContainText(coords.match(/X [^·]+ · Y [^·]+ · YAW [^·]+/)[0]);
 await expect(page.locator('#navigationPoseMode')).toContainText('미확인');
 await expect(page.locator('#navigationInitialPoseTool')).toBeDisabled(); await expect(page.locator('#navigationPoseSend')).toBeDisabled();
 await page.locator('#navigationPoseSend').dispatchEvent('click');
 failing=false; await page.locator('[data-prep="refresh"]').click();
 await expect(page.locator('#navigationInitialPoseTool')).toBeEnabled();
 await expect(page.locator('#navigationPoseCoordinates')).toContainText(coords.match(/X [^·]+ · Y [^·]+ · YAW [^·]+/)[0]);
 await expect(page.locator('#navigationPoseMode')).toContainText('미확인');
 selected.generation=pair.generation='b'.repeat(32);
 await expect(page.locator('#navigationPoseMode')).toHaveText('NO TOOL');
 expect(b.state.requests.filter(r=>/\/navigation\/(initial-pose|goal|start)$/.test(r.path))).toEqual([]);
});


test('draft survives transient navigation read failure and remains unconfirmed on recovery', async ({page}) => {
 const {b}=await fixture(page);await stage(page);const before=(await page.locator('#navigationPoseCoordinates').textContent()).split(' · ').slice(0,3).join(' · ');
 let failing=true;b.on('/api/v1/navigation',({json})=>failing?json({detail:'offline'},503):json(b.state.navigation));
 await expect(page.locator('#navigationPoseMode')).toContainText('미확인');await expect(page.locator('#navigationPoseCoordinates')).toContainText(before);
 await expect(page.locator('#navigationPoseSend')).toBeDisabled();
 failing=false;await expect(page.locator('#navigationInitialPoseTool')).toBeEnabled();
 await expect(page.locator('#navigationPoseCoordinates')).toContainText(before);await expect(page.locator('#navigationPoseMode')).toContainText('미확인');
 await page.locator('#navigationPoseSend').dispatchEvent('click');
 expect(b.state.requests.filter(r=>/\/navigation\/(initial-pose|goal|start)$/.test(r.path))).toEqual([]);
});

test('changing selected map while preparation is unavailable discards the preserved draft', async ({page}) => {
 const {b}=await fixture(page);await stage(page);
 b.on('/api/v1/navigation/operational-3d/preparation-inputs',({json})=>json({detail:'temporary offline'},503));
 await page.locator('[data-prep="refresh"]').click();await expect(page.locator('#navigationPoseMode')).toContainText('미확인');
 await page.locator('#navigationLocalizationMapSelect').selectOption('');
 await expect(page.locator('#navigationPoseMode')).toHaveText('NO TOOL');
 await expect(page.locator('#navigationPoseCoordinates')).toHaveText('X — · Y — · YAW —');
 expect(b.state.requests.filter(r=>/\/navigation\/(initial-pose|goal|start)$/.test(r.path))).toEqual([]);
});

test('historical draft requires same running context and explicit reconfirm before SEND', async ({page})=>{
 const {b}=await fixture(page);await stage(page);const before=(await page.locator('#navigationPoseCoordinates').textContent()).split(' · ').slice(0,3).join(' · ');
 b.state.navigation.pipeline={state:'running',job_id:'2'.repeat(32)};b.state.navigation.map={id:b.mapId,revision:b.mapRevision};b.state.navigation.safety.can_set_initial_pose=true;
 b.state.navigation.operational_localization={fresh:true,bundle_generation:'a'.repeat(32),localization_map_id:'f'.repeat(24),localization_map_revision:'e'.repeat(64),localization_generation:1,runtime_instance_generation:'runtime-one'};
 await expect(page.locator('#navigationPoseMode')).toContainText('이전 미전송 초안 · 미확인');await expect(page.locator('#navigationPoseCoordinates')).toContainText(before);
 await expect(page.locator('#navigationPoseSend')).toBeDisabled();
 page.once('dialog', dialog=>dialog.accept());await page.locator('#navigationInitialPoseTool').click();
 await expect(page.locator('#navigationPoseMode')).toContainText('이전 초안 재확인 · 미전송');await expect(page.locator('#navigationPoseSend')).toBeEnabled();
 b.state.navigation.operational_localization.runtime_instance_generation='runtime-two';
 await expect(page.locator('#navigationPoseSend')).toBeDisabled();await expect(page.locator('#navigationPoseMode')).toContainText('이전 미전송 초안 · 미확인');
 await expect(page.locator('#navigationPoseCoordinates')).toContainText(before);await page.locator('#navigationPoseSend').dispatchEvent('click');
 expect(b.state.requests.filter(r=>/\/navigation\/(initial-pose|goal|start)$/.test(r.path))).toEqual([]);
});

test('stage one displays the draft and expected observation startup does not discard it', async ({page}) => {
 const {b,pair,status}=await fixture(page);pair.calibration_sha256='c'.repeat(64);
 const session={state:'STOPPED',active:false,can_start:true,can_stop:false,session_id:null};
 const evidence={valid:false,reason:'OBSERVATION_INACTIVE'};
 b.on('/api/v1/navigation/operational-3d/preparation-inputs',({json})=>json({schema:'robot-scope.navigation-preparation-inputs.v1',pair,observation:session,evidence,start_blockers:{items:[]},candidates:{},operational_state:status,operational_state_error:null}));
 let release,entered=false;const gate=new Promise(resolve=>release=resolve);
 b.on('/api/v1/observations/fastlio/start',async ({json})=>{entered=true;await gate;Object.assign(session,{state:'READY',active:true,can_start:false,can_stop:true,session_id:'a'.repeat(32)});
  Object.assign(evidence,{valid:true,reason:null,cloud:{observer_id:'1'.repeat(32),publisher_epoch:'2'.repeat(32),source_stamp_ns:'123'},pose:{observer_id:'1'.repeat(32),publisher_epoch:'3'.repeat(32),source_stamp_ns:'123'}});return json(session);});
 await page.locator('[data-prep="refresh"]').click();await expect(page.getByRole('button',{name:'센서 관측 시작'})).toBeEnabled();
 await stage(page);await expect(page.locator('[data-prep="prior-status"]')).toContainText('미전송 사용자 초안');
 await page.getByLabel('위치 불확실 반경 (m)').fill('.75');await page.getByLabel('방향 불확실 ± (도)').fill('25');await page.getByLabel(/이 초안이 현재 지도에서 정지/).check();
 await page.getByRole('button',{name:'센서 관측 시작'}).click();await expect.poll(()=>entered).toBe(true);
 await page.evaluate(()=>new Promise(resolve=>setTimeout(resolve,1500)));
 await expect(page.locator('#navigationPoseMode')).toContainText('미전송 로컬 초안');release();
 await expect(page.getByRole('button',{name:'초기 위치 제안 계산'})).toBeEnabled();
 await expect(page.locator('[data-prep="steps"] > li').first()).toHaveAttribute('data-state','완료');
 b.on('/api/v1/observations/fastlio/stop',({json})=>{Object.assign(session,{state:'STOPPED',active:false,can_start:true,can_stop:false,session_id:null});Object.assign(evidence,{valid:false,reason:'OBSERVATION_INACTIVE'});return json(session);});
 await page.getByRole('button',{name:'센서 관측 종료'}).click();await expect(page.locator('#navigationPoseMode')).toContainText('미확인');
 await expect(page.getByRole('button',{name:'센서 관측 시작'})).toBeEnabled();await page.getByRole('button',{name:'센서 관측 시작'}).click();
 await expect(page.getByRole('button',{name:'센서 관측 종료'})).toBeEnabled();await expect(page.getByRole('button',{name:'초기 위치 제안 계산'})).toBeDisabled();
 await expect(page.locator('#navigationPoseMode')).toContainText('미확인');
 expect(b.state.requests.filter(r=>/\/navigation\/(initial-pose|goal|start)$/.test(r.path))).toEqual([]);
});

test('blur keeps the old point visibly unconfirmed without send or implicit reactivation', async ({page})=>{
 const {b}=await fixture(page);await stage(page);const before=(await page.locator('#navigationPoseCoordinates').textContent()).split(' · ').slice(0,3).join(' · ');
 await page.evaluate(()=>window.dispatchEvent(new Event('blur')));
 await expect(page.locator('#navigationPoseMode')).toContainText('미확인');await expect(page.locator('#navigationPoseCoordinates')).toContainText(before);
 await expect(page.locator('#navigationPoseSend')).toBeDisabled();await page.locator('#navigationPoseSend').dispatchEvent('click');
 await page.evaluate(()=>window.dispatchEvent(new Event('focus')));await expect(page.locator('#navigationPoseMode')).toContainText('미확인');
 expect(b.state.requests.filter(r=>/\/navigation\/(initial-pose|goal|start)$/.test(r.path))).toEqual([]);
});
