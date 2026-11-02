// Actual index.html/app.js/map pointer handling; synthetic dashboard and Nav2/ROS.
import {createRequire} from 'node:module';
import {writeFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
import {assertConditionalProof,assertConditionalConfirmation,assertExecutorEvidence,assertExactStopReceipt} from './contract_assertions.mjs';
const root=process.env.PRIOR_SOURCE_ROOT,output=process.env.PRIOR_OUTPUT_DIR,run=process.env.PRIOR_RUN_LABEL;
const require=createRequire(`${process.env.PRIOR_NODE_ROOT}/package.json`),{chromium}=require('playwright'),{expect}=require('@playwright/test');
const {installDashboardBackend}=await import(pathToFileURL(`${root}/tests/e2e/dashboard_backend.mjs`));
const base='http://127.0.0.1:4397',steps=[],errors=[],responses=[];
async function local(path,body){const r=await fetch(base+path,body===undefined?{signal:AbortSignal.timeout(10000)}:{signal:AbortSignal.timeout(10000),method:'POST',headers:{'Content-Type':'application/json','Origin':base},body:JSON.stringify(body)});const j=await r.json();if(!r.ok)throw Error(`${r.status} ${JSON.stringify(j)}`);return j;}
const browser=await chromium.launch({headless:true,executablePath:process.env.PRIOR_CHROMIUM});
const page=await browser.newPage({viewport:{width:1440,height:1100}});page.setDefaultTimeout(8000);let backend,stage='mount',state='FAIL',failure;
async function step(name,fn){stage=name;await fn();steps.push({name,state:'PASS'});console.log(JSON.stringify(steps.at(-1)));}
const posts=(r,suffix)=>r.events.filter(e=>e.method==='POST'&&e.path.endsWith(suffix));
try{
 const ctx=await local('/__fixture/reset',{});
 page.on('pageerror',e=>errors.push(e.message));
 page.on('response',async r=>{if(r.url().includes('/initialization-proposals/'))try{responses.push(await r.json());}catch{}});
 await page.route('**/*',route=>new URL(route.request().url()).origin===base?route.fallback():route.abort('blockedbyclient'));
 backend=await installDashboardBackend(page);const nav=backend.state.navigation;
 Object.assign(nav,{pipeline:{state:'idle',job_id:null},goal:{state:'idle'},safety:{can_start:true,can_set_initial_pose:false,can_send_goal:false,blockers:[]}});
 const m=ctx.map,p=ctx.fixture_draft.pose;
 backend.on('/api/v1/saved-maps',({json})=>json({total_size_bytes:4096,maps:ctx.maps.map(v=>({...v,manageable:true,data_url:`/api/v1/saved-maps/${v.id}/data`}))}));
 backend.on(`/api/v1/saved-maps/${m.id}/data`,({json})=>json({map_id:m.id,revision:m.revision,name:m.name,frame_id:'map',width:64,height:64,resolution:.25,origin:[p.x-8,p.y-8,0],data_b64:Buffer.alloc(64*64).toString('base64')}));
 let started=false;
 async function navigation(){if(!started)return nav;const actual=await local('/__fixture/mock-nav2/state');return {...nav,...actual,available:true,robot_online:true,safety:{can_start:false,can_stop:true,can_set_initial_pose:true,can_send_goal:false,blockers:[]},readiness:{map_server:true,planner:true,controller:true,behavior:true,cmd_bridge:true,map:true,scan:true,odometry:true,tf:true,localization:false},localization:{state:'uninitialized',pose:null},runtime_health:{localized:false}};}
 backend.on('/api/v1/navigation',async ({json})=>json(await navigation()));
 backend.on('/api/v1/navigation/start',async ({body,json})=>{assert.equal(body.map_id,m.id);await local('/__fixture/mock-nav2/start',{});started=true;return json(await navigation(),202);});
 backend.on('/api/v1/navigation/initial-pose',async ({body,json})=>{const result=await local('/__fixture/mock-nav2/initial-pose',body);return json({...result,navigation:await navigation()});});
 // Actual ASGI for preparation, proposal, confirmation, handoff readback, stop, match.
 await page.route('**/api/v1/navigation/operational-3d**',route=>new URL(route.request().url()).origin===base?route.continue():route.abort('blockedbyclient'));
 await page.route('**/api/v1/observations/fastlio/**',route=>new URL(route.request().url()).origin===base?route.continue():route.abort('blockedbyclient'));
 await page.route('**/*',route=>new URL(route.request().url()).origin===base?route.fallback():route.abort('blockedbyclient'));
 await step('full_app_loaded_no_commands',async()=>{await page.goto(base+'/#navigation');await expect(page.locator('#navigationInitialPoseTool')).toBeEnabled();assert.deepEqual(backend.state.requests,[]);});
 await step('actual_canvas_draft_stage1_post_zero',async()=>{
  await page.locator('#navigationInitialPoseTool').click();const canvas=page.locator('#navigationMapCanvas');await canvas.scrollIntoViewIfNeeded();const box=await canvas.boundingBox();
  await page.mouse.move(box.x+box.width*.5,box.y+box.height*.5);await page.mouse.down();await page.mouse.move(box.x+box.width*.65,box.y+box.height*.5-Math.tan(p.yaw)*box.width*.15,{steps:5});await page.mouse.up();
  await expect(page.locator('#navigationPoseMode')).toContainText('미전송 로컬 초안');await expect(page.locator('#navigationPoseSend')).toBeDisabled();await expect(page.locator('[data-prep="proposal"]')).toBeDisabled();
  assert.equal(posts(await local('/__fixture/result'),'/initialization-proposals').length,0);assert.deepEqual(backend.state.requests,[]);
 });
 let original,proposal;
 await step('actual_draft_to_real_asgi_conditional_proof',async()=>{
  await page.locator('[data-prep="prior-xy"]').fill('.5');await page.locator('[data-prep="prior-yaw"]').fill('30');await page.locator('[data-prep="prior-stationary"]').check();
  await page.locator('[data-prep="proposal"]').click();await expect(page.locator('[data-prep="geometry-preview"]')).toContainText('미적용');
  const r=await local('/__fixture/result');original=posts(r,'/initialization-proposals')[0].body;proposal=Object.values(r.proposals)[0];assertConditionalProof(proposal,original,true);assertExecutorEvidence(r);assert.equal(r.solver_calls,1);assert.equal(r.state.selected.seed_geometry,null);assert.deepEqual(backend.state.requests,[]);
 });
 await step('explicit_confirm_then_stop_real_receipt',async()=>{
  await expect.poll(async()=>{const d=JSON.parse(await page.locator('[data-prep="details"]').textContent());return d.proposal_cleanup?.state==='SETTLED'&&d.proposal_display_valid===true;}).toBe(true);
  await page.locator('[data-prep="supervision"]').check();await page.locator('[data-prep="conditional-ack"]').check();await page.locator('[data-prep="confirm-handoff"]').click();await expect(page.locator('[data-prep="geometry-applied"]')).toContainText('서버 확인 적용값');
  let r=await local('/__fixture/result');assert.equal(posts(r,'/confirm-geometry').length,1);assertConditionalConfirmation(posts(r,'/confirm-geometry')[0].body);assert.equal(posts(r,'/fastlio/stop').length,0);assert.deepEqual(backend.state.requests,[]);
  await page.locator('[data-prep="observe-stop"]').click();await expect.poll(async()=>(await local('/__fixture/result')).state.initialization_handoff?.state).toBe('OBSERVATION_STOPPED');assertExactStopReceipt(await local('/__fixture/result'),original.observation_session_id);
 });
 await step('mock_nav2_start_no_old_draft_auto_send',async()=>{
  await expect(page.locator('#navigationStartButton')).toBeEnabled();await page.locator('#navigationStartButton').click();await expect(page.locator('#navigationPipelineState')).toHaveText('RUNNING');
  await expect(page.locator('#navigationPoseSend')).toBeDisabled();assert.equal(backend.state.requests.filter(e=>/initial-pose|\/goal$/.test(e.path)).length,0);
  assert.equal((await local('/__fixture/mock-nav2/state')).operational_localization.accepted_initial_pose,null);
 });
 await step('explicit_reconfirm_or_redraw_then_initialpose_receipt',async()=>{
  const mode=await page.locator('#navigationPoseMode').textContent();
  if(mode.includes('이전 미전송 초안')){
   page.once('dialog',d=>d.accept());await page.locator('#navigationInitialPoseTool').click();
   steps.push({name:'preserved_draft_explicit_reconfirmation',state:'PASS'});
  }else{
   if(process.env.PRIOR_REQUIRE_GROUPING==='1')throw Error('EXPECTED_PRESERVED_DRAFT_MISSING');
   assert.equal(mode,'NO TOOL');
   steps.push({name:'preserved_draft_explicit_reconfirmation',state:'NOT_REACHED',reason:'baseline cleared old draft; explicit fresh redraw exercised separately'});
   await page.locator('#navigationInitialPoseTool').click();const canvas=page.locator('#navigationMapCanvas');await canvas.scrollIntoViewIfNeeded();const box=await canvas.boundingBox();
   await page.mouse.move(box.x+box.width*.5,box.y+box.height*.5);await page.mouse.down();await page.mouse.move(box.x+box.width*.65,box.y+box.height*.5-Math.tan(p.yaw)*box.width*.15,{steps:5});await page.mouse.up();
  }
  await expect(page.locator('#navigationPoseSend')).toBeEnabled();
  assert.equal(backend.state.requests.filter(e=>e.path.endsWith('/initial-pose')).length,0);await page.locator('#navigationPoseSend').click();
  await expect.poll(()=>backend.state.requests.filter(e=>e.path.endsWith('/initial-pose')).length).toBe(1);
  const sent=backend.state.requests.find(e=>e.path.endsWith('/initial-pose')).body;assert.deepEqual(sent.pose,original.operator_prior.pose);
  await expect.poll(async()=>(await local('/__fixture/mock-nav2/state')).operational_localization.accepted_initial_pose?.accepted).toBe(true);
  const r=await local('/__fixture/mock-nav2/state');assert.equal(r.operational_localization.match_armed,false);assert.equal(r.operational_localization.accepted_initial_pose.geometry_source,'proposal_confirmed');
 });
 await step('explicit_real_asgi_match_gate_and_localizer_arm',async()=>{
  const before=await local('/__fixture/result');assert.equal(posts(before,'/operational-3d/match').length,0);
  await expect(page.getByRole('button',{name:'정합 시작',exact:true})).toBeEnabled();await page.getByRole('button',{name:'정합 시작',exact:true}).click();
  await expect.poll(async()=>(await local('/__fixture/mock-nav2/state')).operational_localization.match_armed).toBe(true);
  await expect.poll(async()=>(await local('/api/v1/navigation/operational-3d/preparation-inputs')).operational_state.initialization_handoff?.state).toBe('MATCH_ARMED');
  assert.equal(backend.state.requests.filter(e=>/\/goal$/.test(e.path)).length,0);const runtime=await local('/__fixture/mock-nav2/state');assert.equal(runtime.operational_localization.ready,false);assert.equal(runtime.operational_localization.estimated_pose,null);
 });
 assert.deepEqual(errors,[]);state='PASS';
}catch(e){failure=e.stack;steps.push({name:stage,state:'FAIL',error:failure});console.log(JSON.stringify({name:stage,state:'FAIL',error:e.message}));}
finally{
 const report={state,steps,failure,errors,requests:backend?.state.requests,responses,preparation:await local('/api/v1/navigation/operational-3d/preparation-inputs').catch(e=>({error:String(e)})),server:await local('/__fixture/result').catch(e=>({error:String(e)})),dom:await page.locator('body').innerText().catch(()=>null),synthetic_boundaries:['dashboard HTTP/ws','map pixels','solver candidates/execution','Nav2 launch','ROS receipt transport'],real:['index/app.js canvas draft','operational ASGI routers','proposal/global owner','manager','localizer reseed/start_matching','receipt waiters'],not_run:['ROS callbacks','external solver subprocess','Nav2 nodes/TF','actual registration convergence','device']};
 await writeFile(`${output}/full-app-${run}.json`,JSON.stringify(report,null,2));await page.screenshot({path:`${output}/full-app-${run}.png`,fullPage:true}).catch(()=>{});await browser.close();
}
process.exitCode=state==='PASS'?0:1;
