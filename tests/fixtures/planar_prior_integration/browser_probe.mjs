// Only synthetic UI component + loopback ASGI. Requires C0-pinned integrated snapshot.
import { createRequire } from 'node:module';
import { writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import {assertHandoffMembers} from './group_assertions.mjs';
import {assertConditionalProof,assertConditionalConfirmation,assertExecutorEvidence,assertExactStopReceipt} from './contract_assertions.mjs';
const root=process.env.PRIOR_SOURCE_ROOT, output=process.env.PRIOR_OUTPUT_DIR;
if(!root || !output || !process.env.PRIOR_HASH_MANIFEST)throw Error('EXACT_PINNED_SNAPSHOT_AND_OUTPUT_REQUIRED');
const require=createRequire(`${process.env.PRIOR_NODE_ROOT || root}/package.json`),{chromium}=require('playwright'),{expect}=require('@playwright/test');
const base='http://127.0.0.1:4397';const run=process.env.PRIOR_RUN_LABEL;
if(!/^[a-z0-9_-]+$/.test(run||''))throw Error('EXPLICIT_DISTINCT_RUN_LABEL_REQUIRED');
const browser=await chromium.launch({headless:true,executablePath:process.env.PRIOR_CHROMIUM});const results=[];
async function local(path,body){const r=await fetch(base+path,body===undefined?{signal:AbortSignal.timeout(10000)}:{signal:AbortSignal.timeout(10000),method:'POST',headers:{'Content-Type':'application/json','Origin':base},body:JSON.stringify(body)});const j=await r.json();if(!r.ok)throw Error(JSON.stringify({status:r.status,body:j}));return j;}
async function fresh(page){await local('/__fixture/reset',{});await page.goto(base+'/exercise');await page.waitForFunction(()=>window.mounted===true);}
function posts(result,suffix){return result.events.filter(x=>x.method==='POST'&&x.path.endsWith(suffix));}
async function noAuto(page){const r=await local('/__fixture/result');assert.equal(posts(r,'/initialization-proposals').length,0);assert.deepEqual(await page.evaluate(()=>window.actions),[]);}
async function setupPrior(page){await page.locator('[data-prep="prior-xy"]').fill('0.5');await page.locator('[data-prep="prior-yaw"]').fill('30');await page.locator('[data-prep="prior-stationary"]').check();}
async function settledPreview(page){
 await expect.poll(async()=>{const d=JSON.parse(await page.locator('[data-prep="details"]').textContent());return d.proposal_cleanup?.state==='SETTLED' && d.proposal_display_valid===true && Date.now()-(page.lastReadyReceivedAt||0)<300;},{intervals:[50,50,100],timeout:8000}).toBe(true);
}
async function runCase(name,fn){
 if(process.env.PRIOR_CASE_FILTER && !new RegExp(process.env.PRIOR_CASE_FILTER).test(name))return;
 const page=await browser.newPage({viewport:{width:1440,height:1600}});page.setDefaultTimeout(6000);
 page.on('response',async r=>{if(r.request().method()==='GET'&&/initialization-proposals\/[a-f0-9]+$/.test(new URL(r.url()).pathname))try{const v=await r.json();if(v.state==='ready'&&v.cleanup?.state==='SETTLED')page.lastReadyReceivedAt=Date.now();}catch{}});let result={name,state:'FAIL'};const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',route=>{const u=new URL(route.request().url());return u.origin===base?route.continue():route.abort('blockedbyclient')});
 try{await fresh(page);await fn(page);assert.deepEqual(errors,[]);result.state='PASS';}
 catch(e){result.error=e.stack;await page.screenshot({path:`${output}/${run}-${name}.png`,fullPage:true}).catch(()=>{});}
 finally{result.errors=errors;result.server=await local('/__fixture/result').catch(e=>({unavailable:String(e)}));result.details=await page.locator('[data-prep="details"]').textContent().then(JSON.parse).catch(()=>null);result.dom=await page.locator('#host').innerText().catch(()=>null);await page.close();results.push(result);await writeFile(`${output}/cases-${run}.json`,JSON.stringify(results,null,2));console.log(JSON.stringify({case:name,state:result.state,error:result.error?.split('\n')[0]}));}
}
try{
 await runCase('missing_prior_draft_or_bounds_never_posts',async page=>{
  await page.evaluate(()=>window.changeFixtureDraft({status:'none'}));await expect(page.locator('[data-prep="proposal"]')).toBeDisabled();await noAuto(page);
  await page.evaluate(()=>window.changeFixtureDraft({status:'ready'}));await expect(page.locator('[data-prep="proposal"]')).toBeDisabled();await noAuto(page);
  await page.locator('[data-prep="prior-xy"]').fill('0.5');await expect(page.locator('[data-prep="proposal"]')).toBeDisabled();await noAuto(page);
  await page.locator('[data-prep="prior-yaw"]').fill('30');await expect(page.locator('[data-prep="proposal"]')).toBeDisabled();await noAuto(page);
 });
 await runCase('prior_wire_exact_and_one_conditional',async page=>{
  await setupPrior(page);const draft=await page.evaluate(()=>structuredClone(window.fixtureDraft));await expect(page.locator('[data-prep="proposal"]')).toBeEnabled();
  await page.locator('[data-prep="proposal"]').click();
  await expect.poll(async()=>posts(await local('/__fixture/result'),'/initialization-proposals').length).toBe(1);
  let r=await local('/__fixture/result');const body=posts(r,'/initialization-proposals')[0].body;assert.deepEqual(body.operator_prior.pose,draft.pose);assert.equal(body.operator_prior.navigation_map_id,draft.navigation_map.id);assert.equal(body.operator_prior.navigation_map_revision,draft.navigation_map.revision);assert.equal(body.operator_prior.bounds.xy_m,.5);assert.ok(Math.abs(body.operator_prior.bounds.yaw_rad-Math.PI/6)<1e-12);assert.equal(body.operator_prior.stationary_current_pose_confirmed,true);
  await expect(page.locator('[data-prep="geometry-preview"]')).toContainText('미적용');r=await local('/__fixture/result');assert.equal(r.state.selected.seed_geometry,null);assert.deepEqual(await page.evaluate(()=>window.actions),[]);
  // Server proof must be read from the real proposal GET, never fabricated by this harness.
  const gets=r.events.filter(e=>e.method==='GET'&&/initialization-proposals\/[a-f0-9]+$/.test(e.path));assert.ok(gets.length>0,'proposal polling expected');
  const response=await local(gets.at(-1).path);const proof=assertConditionalProof(response,body,true);if(process.env.PRIOR_REQUIRE_GROUPING==='1')await expect(page.locator('[data-prep="proposal-result"]')).toContainText('원본 판정: 모호성 미해결');assert.equal(proof.candidate_index,0);assert.equal(proof.retained_candidate_count,6);assert.equal(proof.eligible_candidate_count,2);assert.equal(proof.candidate_vs_prior.within_existing_handoff_reference,true);
  for(const input of await page.locator('[data-geometry]').all())await expect(input).toHaveValue('');assert.deepEqual(await page.evaluate(()=>window.fixtureDraft.pose),draft.pose);
  assertExecutorEvidence(r);
  const duplicate=await local('/api/v1/navigation/operational-3d/initialization-proposals',body);assert.equal(duplicate.proposal_id,response.proposal_id);r=await local('/__fixture/result');assert.equal(r.solver_calls,1);

  await settledPreview(page);await page.locator('[data-prep="supervision"]').check();await page.locator('[data-prep="conditional-ack"]').check();await expect(page.locator('[data-prep="confirm-handoff"]')).toBeEnabled();await page.locator('[data-prep="confirm-handoff"]').click();
  await expect(page.locator('[data-prep="geometry-applied"]')).toContainText('서버 확인 적용값');r=await local('/__fixture/result');const confirmations=posts(r,'/confirm-geometry');assert.equal(confirmations.length,1);assertConditionalConfirmation(confirmations[0].body);
  assert.equal(posts(r,'/fastlio/stop').length,0);const geometry=r.state.selected.seed_geometry;assert.equal(geometry.source,'proposal_confirmed');assert.equal(geometry.handoff.policy_id,'robot-scope.proposal-handoff.operator-prior-v1');assert.ok(geometry.handoff.expires_monotonic_s<=proof.expires_monotonic_s);assert.equal(response.quality.ambiguity_unresolved,true);assert.deepEqual(await page.evaluate(()=>window.fixtureDraft.pose),draft.pose);for(const input of await page.locator('[data-geometry]').all())await expect(input).toHaveValue('');assert.deepEqual(await page.evaluate(()=>window.actions),[]);
  await page.locator('[data-prep="observe-stop"]').click();await expect.poll(async()=>(await local('/__fixture/result')).state.initialization_handoff?.state).toBe('OBSERVATION_STOPPED');r=await local('/__fixture/result');assert.equal(posts(r,'/fastlio/stop').length,1);assertExactStopReceipt(r,body.observation_session_id);assert.deepEqual(await page.evaluate(()=>window.actions),[]);
 });
 await runCase('unique_global_inside_still_conditional',async page=>{
  await local('/__fixture/change/unique-in',{});await setupPrior(page);await page.locator('[data-prep="proposal"]').click();await expect(page.locator('[data-prep="geometry-preview"]')).toContainText('미적용');const r=await local('/__fixture/result');assert.deepEqual(r.synthetic_observation.gate_reasons,[]);assert.equal(r.synthetic_observation.candidate_count,1);const body=posts(r,'/initialization-proposals')[0].body;const gets=r.events.filter(e=>e.method==='GET'&&/initialization-proposals\/[a-f0-9]+$/.test(e.path));assert.ok(gets.length);const response=await local(gets.at(-1).path);const proof=assertConditionalProof(response,body,false);assert.equal(proof.retained_candidate_count,6);assert.equal(proof.matching_candidate_count,1);if(process.env.PRIOR_REQUIRE_GROUPING==='1'){await expect(page.locator('[data-prep="proposal-result"]')).toContainText('원본 판정: 비모호');await expect(page.locator('[data-prep="proposal-result"]')).not.toContainText('원래 모호성은 유지');}assert.equal(r.state.selected.seed_geometry,null);assert.equal(posts(r,'/confirm-geometry').length,0);assert.deepEqual(await page.evaluate(()=>window.actions),[]);
 });
 await runCase('unique_global_outside_prior_rejected',async page=>{
  await local('/__fixture/change/unique-out',{});await setupPrior(page);await page.locator('[data-prep="proposal"]').click();let response;
  await expect.poll(async()=>{const r=await local('/__fixture/result');const g=r.events.filter(e=>e.method==='GET'&&/initialization-proposals\/[a-f0-9]+$/.test(e.path));if(!g.length)return 'pending';response=await local(g.at(-1).path);return response.state;}).toBe('rejected');
  const r=await local('/__fixture/result');assert.deepEqual(r.synthetic_observation.gate_reasons,[]);assert.equal(r.synthetic_observation.candidate_count,1);assert.equal(response.reason,'PRIOR_NO_MATCH');assert.equal(r.state.selected.seed_geometry,null);assert.equal(posts(r,'/confirm-geometry').length,0);assert.deepEqual(await page.evaluate(()=>window.actions),[]);
 });
 for(const variant of ['missing-proof','missing-original-ambiguity']) await runCase(`${variant}_cannot_show_conditional_ready`,async page=>{
  let stripped=0;await page.route('**/api/v1/navigation/operational-3d/initialization-proposals/*',async route=>{if(new URL(route.request().url()).origin!==base)return route.abort('blockedbyclient');if(route.request().method()!=='GET')return route.fallback();const response=await route.fetch();const payload=await response.json();if(payload.state==='ready'){if(variant==='missing-proof')delete payload.operator_prior_resolution;else if(payload.operator_prior_resolution)delete payload.operator_prior_resolution.original_ambiguity_unresolved;stripped++;}return route.fulfill({response,json:payload});});
  await setupPrior(page);await page.locator('[data-prep="proposal"]').click();await expect.poll(()=>stripped).toBeGreaterThan(0);await expect(page.locator('[data-prep="geometry-preview"]')).not.toContainText('미리 본 제안값');await expect(page.locator('[data-prep="confirm-handoff"]')).toBeDisabled();const r=await local('/__fixture/result');assert.equal(posts(r,'/confirm-geometry').length,0);assert.equal(r.state.selected.seed_geometry,null);assert.deepEqual(await page.evaluate(()=>window.actions),[]);
 });
 await runCase('confirm_rejects_missing_ack_and_client_proof',async page=>{
  await setupPrior(page);await page.locator('[data-prep="proposal"]').click();await expect(page.locator('[data-prep="geometry-preview"]')).toContainText('미적용');let r=await local('/__fixture/result');const original=posts(r,'/initialization-proposals')[0].body;const gets=r.events.filter(e=>e.method==='GET'&&/initialization-proposals\/[a-f0-9]+$/.test(e.path));assert.ok(gets.length);const proposal=await local(gets.at(-1).path);
  const confirmPath=`/api/v1/navigation/operational-3d/initialization-proposals/${proposal.proposal_id}/confirm-geometry`;const basic={request_id:'synthetic-missing-ack',bundle_generation:original.bundle_generation,observation_session_id:original.observation_session_id,confirmed:true,stationary_supervision_acknowledged:true};
  const missing=await fetch(base+confirmPath,{method:'POST',headers:{'Content-Type':'application/json','Origin':base},body:JSON.stringify(basic)});assert.equal(missing.status,409);assert.match(JSON.stringify(await missing.json()),/CONDITIONAL_PRIOR_CONFIRMATION_REQUIRED/);
  const tampered=await fetch(base+confirmPath,{method:'POST',headers:{'Content-Type':'application/json','Origin':base},body:JSON.stringify({...basic,request_id:'synthetic-client-proof',conditional_prior_acknowledged:true,operator_prior_resolution:proposal.operator_prior_resolution})});assert.equal(tampered.status,422);
  r=await local('/__fixture/result');assert.equal(r.state.selected.seed_geometry,null);assert.equal(posts(r,'/fastlio/stop').length,0);assert.deepEqual(await page.evaluate(()=>window.actions),[]);
 });
 await runCase('confirm_response_lost_and_status_failure_no_retry',async page=>{
  await setupPrior(page);await page.locator('[data-prep="proposal"]').click();await expect(page.locator('[data-prep="geometry-preview"]')).toContainText('미적용');
  await local('/__fixture/change/lose-confirm-response',{});await settledPreview(page);await page.locator('[data-prep="supervision"]').check();await page.locator('[data-prep="conditional-ack"]').check();await expect(page.locator('[data-prep="confirm-handoff"]')).toBeEnabled();await page.locator('[data-prep="confirm-handoff"]').click();
  await expect.poll(async()=>posts(await local('/__fixture/result'),'/confirm-geometry').length).toBe(1);
  await local('/__fixture/change/fail-next-status',{});await page.evaluate(()=>window.preparation.refresh(true));
  await expect(page.locator('[data-prep="confirm-handoff"]')).toBeDisabled();const r=await local('/__fixture/result');assert.equal(posts(r,'/confirm-geometry').length,1);assert.equal(posts(r,'/fastlio/stop').length,0);assert.deepEqual(await page.evaluate(()=>window.actions),[]);
  assert.equal(r.state.selected.seed_geometry.source,'proposal_confirmed');await page.reload();await page.waitForFunction(()=>window.mounted===true);
  await expect(page.locator('[data-prep="geometry-applied"]')).toContainText('서버 확인 적용값');assert.equal(posts(await local('/__fixture/result'),'/confirm-geometry').length,1);
  await page.locator('[data-prep="observe-stop"]').click();await expect.poll(async()=>(await local('/__fixture/result')).state.initialization_handoff?.state).toBe('OBSERVATION_STOPPED');assertExactStopReceipt(await local('/__fixture/result'),'a'.repeat(32));
 });
 for(const variant of ['zero','multiple','bad-quality','truncated','unknown-quality','missing-metadata','tampered-metadata']) await runCase(`ambiguous_${variant}_does_not_confirm`,async page=>{
  await local(`/__fixture/change/${variant}`,{});await setupPrior(page);await page.locator('[data-prep="proposal"]').click();
  await expect.poll(async()=>{const r=await local('/__fixture/result');const g=r.events.filter(e=>e.method==='GET'&&/initialization-proposals\/[a-f0-9]+$/.test(e.path));if(!g.length)return 'pending';return (await local(g.at(-1).path)).state;}).toBe('rejected');
  const r=await local('/__fixture/result');assert.equal(r.state.selected.seed_geometry,null);assert.equal(posts(r,'/confirm-geometry').length,0);assert.deepEqual(await page.evaluate(()=>window.actions),[]);
 });
 await runCase('transient_status_preserves_unconfirmed_draft_no_post',async page=>{
  const draft=await page.evaluate(()=>structuredClone(window.fixtureDraft));await local('/__fixture/change/fail-next-status',{});await page.evaluate(()=>window.preparation.refresh(true));await expect(page.locator('[data-prep="proposal"]')).toBeDisabled();assert.deepEqual(await page.evaluate(()=>window.fixtureDraft.pose),draft.pose);await noAuto(page);
 });
 await runCase('draft_change_clears_ack_and_no_auto_post',async page=>{
  await setupPrior(page);await page.evaluate(()=>window.changeFixtureDraft({revision:2,pose:{...window.fixtureDraft.pose,x:window.fixtureDraft.pose.x+.1}}));await expect(page.locator('[data-prep="prior-stationary"]')).not.toBeChecked();await expect(page.locator('[data-prep="proposal"]')).toBeDisabled();await noAuto(page);
 });

 await runCase('duplicate_id_changed_prior_rejected',async page=>{
  await setupPrior(page);await page.locator('[data-prep="proposal"]').click();await expect(page.locator('[data-prep="geometry-preview"]')).toContainText('미적용');let r=await local('/__fixture/result');const body=posts(r,'/initialization-proposals')[0].body;
  const altered=structuredClone(body);altered.operator_prior.pose.x+=.1;const conflict=await fetch(base+'/api/v1/navigation/operational-3d/initialization-proposals',{method:'POST',headers:{'Content-Type':'application/json','Origin':base},body:JSON.stringify(altered)});assert.equal(conflict.status,409);r=await local('/__fixture/result');assert.equal(r.solver_calls,1);
  assert.equal(r.state.selected.seed_geometry,null);assert.equal(posts(r,'/confirm-geometry').length,0);
 });
 for(const mode of ['source-epoch','session','generation','map-revision','calibration','expire-prior']) await runCase(`invalidate_${mode}`,async page=>{
  await setupPrior(page);await page.locator('[data-prep="proposal"]').click();await expect(page.locator('[data-prep="geometry-preview"]')).toContainText('미적용');
  const before=await local('/__fixture/result'),id=Object.keys(before.proposals)[0];assert.ok(id);
  await local(`/__fixture/change/${mode}`,{});await page.evaluate(()=>window.preparation.refresh(true));
  await expect.poll(async()=> (await local(`/api/v1/navigation/operational-3d/initialization-proposals/${id}`)).state).toBe('stale');
  await expect(page.locator('[data-prep="confirm-handoff"]')).toBeDisabled();const r=await local('/__fixture/result');assert.equal(r.state.selected.seed_geometry,null);assert.equal(posts(r,'/confirm-geometry').length,0);assert.deepEqual(await page.evaluate(()=>window.actions),[]);
 });
 await runCase('prior_bounds_change_invalidates_confirmation',async page=>{
  await setupPrior(page);await page.locator('[data-prep="proposal"]').click();await expect(page.locator('[data-prep="geometry-preview"]')).toContainText('미적용');
  await page.locator('[data-prep="prior-xy"]').fill('.6');await expect(page.locator('[data-prep="prior-stationary"]')).not.toBeChecked();await expect(page.locator('[data-prep="confirm-handoff"]')).toBeDisabled();const r=await local('/__fixture/result');assert.equal(posts(r,'/initialization-proposals').length,1);assert.equal(posts(r,'/confirm-geometry').length,0);
 });
 await runCase('legacy_no_prior_backend_preserved',async page=>{
  await local('/__fixture/change/legacy',{});const r=await local('/__fixture/result');const started=await local('/api/v1/navigation/operational-3d/initialization-proposals',{request_id:'legacy-no-prior',bundle_generation:r.state.pair.generation,observation_session_id:'a'.repeat(32)});
  let response;await expect.poll(async()=>{response=await local(`/api/v1/navigation/operational-3d/initialization-proposals/${started.proposal_id}`);return response.state;}).toBe('ready');assert.equal(response.operator_prior_resolution,undefined);assert.equal(response.classification,undefined);assert.equal(response.quality.ambiguity_unresolved,false);assert.equal((await local('/__fixture/result')).state.selected.seed_geometry,null);
 });

 await runCase('wide_prior_does_not_relax_existing_handoff',async page=>{
  await local('/__fixture/change/handoff-out',{});await setupPrior(page);await page.locator('[data-prep="proposal"]').click();await expect(page.locator('[data-prep="geometry-preview"]')).toContainText('미적용');
  const r=await local('/__fixture/result'),body=posts(r,'/initialization-proposals')[0].body,response=Object.values(r.proposals)[0];const proof=assertConditionalProof(response,body,true);assert.equal(proof.candidate_vs_prior.within_existing_handoff_reference,false);
  await page.locator('[data-prep="supervision"]').check();await page.locator('[data-prep="conditional-ack"]').check();await expect(page.locator('[data-prep="confirm-handoff"]')).toBeDisabled();assert.equal(posts(await local('/__fixture/result'),'/confirm-geometry').length,0);
 });
 if(process.env.PRIOR_REQUIRE_GROUPING==='1'){
  await runCase('grouped_two_members_one_hypothesis_real_confirmation',async page=>{
   await local('/__fixture/change/duplicate-in',{});await setupPrior(page);await page.locator('[data-prep="proposal"]').click();await expect(page.locator('[data-prep="geometry-preview"]')).toContainText('미적용');
   let r=await local('/__fixture/result');const response=Object.values(r.proposals)[0],body=posts(r,'/initialization-proposals')[0].body;const p=assertConditionalProof(response,body,true);assert.equal(p.matching_candidate_count,2);assert.equal(p.matching_hypothesis_count,1);assert.deepEqual(p.matching_member_indices,[0,1]);
   await settledPreview(page);await page.locator('[data-prep="supervision"]').check();await page.locator('[data-prep="conditional-ack"]').check();await page.locator('[data-prep="confirm-handoff"]').click();await expect(page.locator('[data-prep="geometry-applied"]')).toContainText('서버 확인 적용값');r=await local('/__fixture/result');assertHandoffMembers(r.state.selected.seed_geometry.handoff,response);assert.equal(posts(r,'/fastlio/stop').length,0);
  });
  for(const variant of ['duplicate-bad-marker','multiple-roll'])await runCase(`grouped_reject_${variant}`,async page=>{
   await local(`/__fixture/change/${variant}`,{});await setupPrior(page);await page.locator('[data-prep="proposal"]').click();await expect.poll(async()=>Object.values((await local('/__fixture/result')).proposals)[0]?.state).toBe('rejected');assert.equal((await local('/__fixture/result')).state.selected.seed_geometry,null);
  });
  await runCase('grouped_current_member_drift_blocks_confirm',async page=>{
   await local('/__fixture/change/duplicate-current-drift',{});await setupPrior(page);await page.locator('[data-prep="prior-xy"]').fill('.1');await page.locator('[data-prep="prior-stationary"]').check();await page.locator('[data-prep="proposal"]').click();await expect(page.locator('[data-prep="geometry-preview"]')).toContainText('미적용');
   const before=await local('/__fixture/result'),id=Object.keys(before.proposals)[0],body=posts(before,'/initialization-proposals')[0].body;
   await local('/__fixture/change/odom-drift',{});let response;await expect.poll(async()=>{response=await local(`/api/v1/navigation/operational-3d/initialization-proposals/${id}`);return response.current_vs_prior?.all_members_within_prior_bounds;}).toBe(false);
   assertConditionalProof(response,body,true,{requireCurrentMembersInBounds:false});assert.equal(response.current_vs_prior.within_prior_bounds,true);assert.equal(response.current_vs_prior.member_checks[1].within_prior_bounds,false);
   const r=await fetch(`${base}/api/v1/navigation/operational-3d/initialization-proposals/${id}/confirm-geometry`,{method:'POST',headers:{'Content-Type':'application/json','Origin':base},body:JSON.stringify({request_id:'member-drift',bundle_generation:body.bundle_generation,observation_session_id:body.observation_session_id,confirmed:true,stationary_supervision_acknowledged:true,conditional_prior_acknowledged:true})});assert.equal(r.status,409);
   await expect(page.locator('[data-prep="confirm-handoff"]')).toBeDisabled();assert.equal((await local('/__fixture/result')).state.selected.seed_geometry,null);
  });
 }
}finally{await browser.close();}
const failures=results.filter(r=>r.state!=='PASS').length;console.log(JSON.stringify({summary:{total:results.length,pass:results.length-failures,fail:failures,synthetic_only:true}}));process.exitCode=failures?1:0;
