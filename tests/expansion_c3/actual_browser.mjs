import {createRequire} from 'node:module';
import {mkdir,writeFile,readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
const require=createRequire(import.meta.url),{chromium}=require(process.env.C3_PLAYWRIGHT || 'playwright');
const out=resolve(process.env.C3_EVIDENCE || '/tmp/c3-round2-results');await mkdir(out,{recursive:true});
const base=process.env.C3_ACTUAL_URL || 'http://127.0.0.1:4184';
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
const context=await browser.newContext({viewport:{width:1500,height:1100}});
const report={source_mode:'ACTUAL_C1_SERVICE',evidence_kind:'SYNTHETIC',browser:browser.version(),cases:[],requests:[],errors:[],http:[]};
context.on('request',r=>report.requests.push({method:r.method(),url:r.url()}));
await context.route('**/*',route=>{
  const r=route.request(),u=new URL(r.url());
  if(r.method()!=='GET'||u.origin!==base||u.pathname.startsWith('/api/')||u.pathname.includes('/actual/')&&!(u.pathname.endsWith('/api/v1/extensions/scene/snapshot')||/\/api\/v1\/extensions\/scene\/assets\/[a-f0-9]{24}\/[a-f0-9]{64}$/.test(u.pathname)))route.abort();else route.continue();
});
const page=await context.newPage();page.on('pageerror',e=>report.errors.push(String(e)));
try{
  for(const name of ['PREDICTED_CONTACT','NEAR','UNKNOWN_PARTIAL','SCOPED_SYNTHETIC_CLEAR','ACTIVE_UNKNOWN','EXPIRED']){
    const endpoint=`${base}/actual/${name}/api/v1/extensions/scene/snapshot`;
    const unauth=await context.request.get(endpoint);assert.equal(unauth.status(),401);
    const response=await context.request.get(endpoint,{headers:{Authorization:'Bearer public-c3-synthetic-offline-test-bearer'}});
    assert.equal(response.status(),200);const body=await response.text(),hash=createHash('sha256').update(body).digest('hex');
    await writeFile(resolve(out,`${name}.json`),body+'\n');
    report.http.push({name,status:response.status(),unauthorized_status:unauth.status(),sha256:hash,bytes:Buffer.byteLength(body)});
    await page.goto(`${base}/experiments/expansion_20261029/c3_scene_ui/fixture.html?actual=${name}`);
    await page.waitForFunction(()=>window.c3Actual?.last && window.c3Fixture.feature.snapshot()?.ready);
    await page.locator('[data-action=pause]').click();
    await page.evaluate(()=>window.c3Actual.stop());
    const v=await page.evaluate(()=>window.c3Fixture.feature.snapshot());
    assert.equal(await page.evaluate(()=>window.c3Actual.last.fingerprint),hash);
    assert.equal(v.source_mode,'ACTUAL_C1_SERVICE');assert.equal(v.evidence_kind,'SYNTHETIC');
    assert.equal(v.map_identity.generation,report.cases.length+1);
    assert.equal(v.availability.reference_cloud,'SUPPLIED_DISPLAY_ASSET');
    assert.equal(await page.evaluate(()=>window.c3Actual.last.reference_points),160);
    assert.equal(await page.evaluate(()=>window.c3Actual.last.cache.downloads),1);
    assert.equal(await page.evaluate(()=>window.c3Actual.last.wire.schema_version),'0.2');
    if(name==='EXPIRED')assert.equal(v.sources.length,0);
    else {assert.equal(v.sources[0].value.points_m.length,8);assert.deepEqual(v.sources[0].value.origin_m,[.08,0,.4]);}
    assert.equal(v.obstacles.value?.obstacles.length,name==='EXPIRED'?undefined:1);
    if(name==='EXPIRED')assert.equal(v.costmaps.length,0);
    else assert.deepEqual(v.costmaps[0].value.cells,[0,254,-1,0]);
    assert.equal(v.local.value,null);
    if(name==='EXPIRED')assert.equal(v.path.value,null);
    else assert.equal(v.path.value.points_m[1][0],name==='PREDICTED_CONTACT'?.6:0);
    if(name==='EXPIRED') {assert.equal(v.collision.value,null);assert.equal(v.pose.reason,'SERVER_EXPIRED');}
    else {
      assert.ok(v.collision.value,JSON.stringify(v));
      assert.equal(v.collision.value.severity,name==='PREDICTED_CONTACT'?'STOP_REQUIRED':name==='SCOPED_SYNTHETIC_CLEAR'?'CLEAR':'UNKNOWN');
      assert.equal(v.collision.value.protection_mode,name==='ACTIVE_UNKNOWN'?'ACTIVE_CONSTRAINT':'ADVISORY_ONLY');
      assert.equal(v.collision.value.envelopes.length,0);
      assert.equal(v.collision.value.coverage.complete_for_motion,name==='SCOPED_SYNTHETIC_CLEAR');
      assert.equal(v.collision.value.freshness.time_conversion.binding_id,'c3-synthetic-identity-only');
      assert.equal(v.collision.value.validity_interval.start_monotonic_ns,'9007199254740993');
      if(name==='PREDICTED_CONTACT')assert.equal(v.collision.value.contact_state,'PREDICTED_CONTACT');
      if(['NEAR','UNKNOWN_PARTIAL','ACTIVE_UNKNOWN'].includes(name))assert.ok(v.collision.value.min_clearance_m>0);
    }
    const model=await page.evaluate(()=>window.c3Fixture.renderer.getOfficialRobotModelStatus());assert.equal(model.state,'ready');
    assert.ok((await page.locator('[data-testid=mode]').textContent()).includes('ACTUAL_C1_SERVICE'));
    if(name==='UNKNOWN_PARTIAL'||name==='PREDICTED_CONTACT'){
      await page.locator('[data-testid=risk]').click();
      await page.screenshot({path:resolve(out,`${name}.png`),fullPage:true});
    }
    const d=await page.evaluate(()=>window.c3Fixture.feature.diagnostics());
    report.cases.push({name,result:'PASS',endpoint_sha256:hash,view:v,diagnostics:d});
    if(name==='UNKNOWN_PARTIAL'){
      await page.locator('[data-action=pause]').click();
      await page.evaluate(()=>window.c3Actual.start());
      await page.waitForFunction(()=>window.c3Fixture.feature.snapshot()?.pose.reason==='STALE');
      await page.waitForFunction(()=>window.c3Fixture.feature.snapshot()?.obstacles.reason==='STALE');
      const aged=await page.evaluate(()=>({v:window.c3Fixture.feature.snapshot(),d:window.c3Fixture.feature.diagnostics()}));
      assert.equal(aged.v.collision.value,null);assert.equal(aged.d.lastSequence,d.lastSequence);
      assert.ok(aged.d.accepted>d.accepted);assert.equal(aged.d.geometryCopies,d.geometryCopies);
      assert.deepEqual(await page.evaluate(()=>window.c3Actual.last.cache),{entries:1,downloads:1,decodes:1});
      report.frozen_time={result:'PASS',same_scene_sequence:aged.d.lastSequence,repeated_gets:aged.d.accepted-d.accepted,geometry_copies:aged.d.geometryCopies,pose:aged.v.pose.reason,obstacles:aged.v.obstacles.reason};
      await page.evaluate(()=>window.c3Actual.stop());
      await page.screenshot({path:resolve(out,'FROZEN_SOURCE_STALE.png'),fullPage:true});
    }
  }
  if(process.env.C3_NATIVE_REPLAY==='1'){
    const core=JSON.parse(await readFile(resolve(out,'core-results.json'),'utf8')),native=core.native_replay;
    await page.goto(`${base}/experiments/expansion_20261029/c3_scene_ui/fixture.html?actual=NATIVE_REPLAY`);
    await page.waitForFunction(()=>window.c3Actual?.last && window.c3Fixture.feature.snapshot()?.ready);
    await page.locator('[data-action=pause]').click();await page.evaluate(()=>window.c3Actual.stop());
    const v=await page.evaluate(()=>window.c3Fixture.feature.snapshot()),last=await page.evaluate(()=>window.c3Actual.last);
    assert.equal(v.evidence_kind,'REPLAY');assert.equal(v.source_mode,'ACTUAL_C1_SERVICE');
    assert.deepEqual(v.path.value.points_m,native.source_records.plan.points.map(p=>[...p,0]));
    assert.equal(v.path.value.stamp_ns,native.snapshot.global_path.stamp_ns);
    assert.equal(v.path.value.receipt_source_ns,native.snapshot.global_path.received_monotonic_ns);
    assert.equal(v.joints.value,null);assert.equal(v.collision.value,null);assert.equal(v.local.value,null);
    assert.equal(v.pose.value,null);assert.equal(v.pose.reason,'CALIBRATION_MISMATCH');
    const c=v.costmaps[0].value;assert.ok(c);assert.equal(c.width,40);assert.equal(c.height,30);
    assert.equal(c.resolution_m,native.source_records.costmap.resolution*5);
    assert.equal(c.cells.length,1200);assert.equal(c.cell_encoding,'OCCUPANCY_PERCENT');assert.ok(c.cells.includes(100));assert.ok(c.cells.includes(0));
    assert.equal(c.provenance.display_transform.kind,'DISPLAY_ONLY_BLOCK_MAX_UNKNOWN_PRESERVED');
    const endpoint=`${base}/actual/NATIVE_REPLAY/api/v1/extensions/scene/snapshot`;
    const response=await context.request.get(endpoint,{headers:{Authorization:'Bearer public-c3-synthetic-offline-test-bearer'}});
    const body=await response.text();assert.equal(createHash('sha256').update(body).digest('hex'),last.fingerprint);
    await writeFile(resolve(out,'NATIVE_REPLAY.json'),body+'\n');
    const assetPath=`${base}/actual/NATIVE_REPLAY/api/v1/extensions/scene/assets/${last.assets[0].ref.id}/${last.assets[0].ref.revision}`;
    assert.equal((await context.request.get(assetPath)).status(),401);
    assert.equal((await context.request.get(assetPath.replace(last.assets[0].ref.revision,'0'.repeat(64)),{headers:{Authorization:'Bearer public-c3-synthetic-offline-test-bearer'}})).status(),404);
    await page.evaluate(()=>window.c3Actual.poll());assert.equal(await page.evaluate(()=>window.c3Actual.last.cache.downloads),1);
    await page.screenshot({path:resolve(out,'NATIVE_REPLAY.png'),fullPage:true});
    report.native_replay={result:'PASS',artifact_id:native.artifact_id,zip_sha256:native.zip_sha256,native_sha:native.native_sha,
      endpoint_sha256:last.fingerprint,view:v,cache:last.cache,native_execution:'RECORDED_REMOTE; NOT_RUN_LOCAL',
      requests:'GET_ONLY',original_costmap_cells:30000,display_costmap_cells:c.cells.length};
  }
  assert.deepEqual(report.errors,[]);
  assert.ok(report.requests.every(r=>r.method==='GET'&&new URL(r.url).origin===base));
  report.status='PASS';
}catch(e){report.status='FAIL';report.error=e.stack;process.exitCode=1;}
finally{await writeFile(resolve(out,'actual-browser-results.json'),JSON.stringify(report,null,2)+'\n');await browser.close();}
console.log(JSON.stringify({status:report.status,cases:report.cases.map(c=>({name:c.name,result:c.result})),frozen_time:report.frozen_time,requests:report.requests.length,errors:report.errors,error:report.error},null,2));
