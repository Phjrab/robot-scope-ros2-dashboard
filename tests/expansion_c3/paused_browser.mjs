// C5-H1 reproduction and C3-owned regression. Real wall time and real renderer;
// generated fixture / archived C1 bytes, never live sensors or ROS execution.
import {createRequire} from 'node:module';
import {mkdir,writeFile,readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import assert from 'node:assert/strict';
const {chromium,webkit}=createRequire(import.meta.url)(process.env.C3_PLAYWRIGHT || 'playwright');
const out=resolve(process.env.C3_EVIDENCE || '/tmp/c3-pause-browser');await mkdir(out,{recursive:true});
const url=process.env.C3_FIXTURE_URL || 'http://127.0.0.1:4183/experiments/expansion_20261029/c3_scene_ui/fixture.html';
const wire=JSON.parse(await readFile(new URL('../../docs/parallel-expansion-20261029/C3/evidence/round2-v02/PREDICTED_CONTACT.http-body.json',import.meta.url),'utf8'));
const report={classification:'REAL_BROWSER_RENDER; SYNTHETIC_FIXTURE / ARCHIVED_C1_0.2_BYTES',cases:[],observations:[],errors:[],requests:[]};
for(const [engine,type] of Object.entries({chromium,webkit})){
 const browser=await type.launch({headless:true});
 const context=await browser.newContext({viewport:{width:1440,height:1000}});
 await context.route('**/*',r=>{const q=r.request();report.requests.push({method:q.method(),url:q.url()});q.method()==='GET'&&new URL(q.url()).origin===new URL(url).origin?r.continue():r.abort();});
 const run=async(name,fn)=>{
  const page=await context.newPage();page.on('pageerror',e=>report.errors.push(String(e)));
  try{
   await page.goto(url);await page.waitForFunction(()=>window.c3Fixture?.feature.snapshot()?.ready);
   await fn(page);report.cases.push({engine,version:browser.version(),name,result:'PASS'});
  }catch(e){report.cases.push({engine,name,result:'FAIL',error:e.stack});process.exitCode=1;}
  finally{await page.close();}
 };
 const view=page=>page.evaluate(()=>window.c3Fixture.feature.snapshot());
 const send=async(page,name='multi')=>{const seq=await page.evaluate(n=>window.c3Fixture.emit(n).sequence,name);await page.waitForFunction(s=>window.c3Fixture.feature.snapshot()?.sequence===s,seq);return seq;};
 const pause=async page=>{await page.locator('[data-action=pause]').click();await page.waitForFunction(()=>document.querySelector('.os-mode').textContent.includes('PAUSED'));};
 const hidden=async page=>{await page.waitForFunction(()=>window.c3Fixture.renderer.robotVisible===false);assert.match(await page.locator('.os-risk').textContent(),/UNKNOWN/);};
 try{
  await run('C5-H1: fresh → paused → 2600ms; consumer and DOM agree',async page=>{
   await page.setViewportSize({width:390,height:1000});
   const seq=await send(page);await page.evaluate(async()=>{
    const f=window.c3Fixture;const {createSceneConsumer}=await import('/robot_dashboard/static/features/obstacle_scene/consumer.js');
    window.independent=createSceneConsumer({getMap:()=>f.context});window.independent.ingest(f.makePacket(f.feature.snapshot().sequence,'multi',f.context));
   });
   assert.match(await page.locator('.os-sources').textContent(),/Pose · FRESH/);assert.equal(await page.evaluate(()=>window.c3Fixture.renderer.robotVisible),true);
   await pause(page);const start=Date.now();await page.waitForTimeout(2600);
   const v=await view(page);assert.equal(v.sequence,seq);assert.equal(v.pose.reason,'STALE');assert.equal(v.joints.reason,'STALE');assert.equal(v.collision.value,null);
   assert.equal(await page.evaluate(()=>window.independent.snapshot().pose.reason),'STALE');
   assert.match(await page.locator('.os-sources').textContent(),/Pose · STALE \/ Joints · STALE/);await hidden(page);
   assert.match(await page.locator('.os-mode').textContent(),/과거 프레임/);
   await page.screenshot({path:resolve(out,`${engine}-paused-expired.png`),fullPage:true});
   report.observations.push({engine,name:'C5-H1 measured output',elapsedMs:Date.now()-start,consumerPose:v.pose.reason,consumerCollision:v.collision.reason,sources:await page.locator('.os-sources').textContent(),risk:await page.locator('.os-risk').textContent(),robotVisible:false,result:'PASS'});
   const next=await page.evaluate(()=>window.c3Fixture.emit('multi').sequence);assert.equal((await view(page)).sequence,seq);
   await page.locator('[data-action=pause]').click();await page.waitForFunction(s=>window.c3Fixture.feature.snapshot().sequence===s,next);
   await page.waitForFunction(()=>window.c3Fixture.renderer.robotVisible);assert.ok((await view(page)).pose.value);
  });
  await run('queued packet ages before first step; new packet after resume recovers',async page=>{
   await pause(page);await page.evaluate(()=>window.c3Fixture.emit('multi'));await page.waitForTimeout(2600);
   await page.locator('[data-action=step]').click();assert.equal((await view(page)).pose.reason,'STALE');await hidden(page);
   await page.locator('[data-action=pause]').click();await send(page);assert.ok((await view(page)).pose.value);
  });
  for(const field of ['revision','source_epoch','stream_epoch'])await run(`paused ${field} reset and delayed old response`,async page=>{
   await send(page);await pause(page);
   const old=await page.evaluate(field=>{const f=window.c3Fixture,old=f.makePacket(100,'multi',f.context);f.emitPacket(old);f.setContext({...f.context,[field]:'next-'+field});return old;},field);
   await page.waitForFunction(()=>!window.c3Fixture.feature.snapshot().ready);await hidden(page);
   await page.evaluate(p=>window.c3Fixture.emitPacket(p),old);assert.equal((await view(page)).ready,false);
   assert.equal(await page.evaluate(()=>window.c3Fixture.feature.diagnostics().pending),0);
   assert.equal(await page.locator('[data-action=step]').isDisabled(),true);
   const seq=await page.evaluate(()=>window.c3Fixture.emit('multi').sequence);await page.locator('[data-action=step]').click();await page.waitForFunction(s=>window.c3Fixture.feature.snapshot()?.sequence===s,seq);
   assert.ok((await view(page)).pose.value);await page.evaluate(p=>window.c3Fixture.emitPacket(p),old);assert.equal((await view(page)).sequence,seq);
  });
  await run('old packets cannot replace newer pending packets',async page=>{
   await pause(page);await page.evaluate(()=>{const f=window.c3Fixture;f.emitPacket(f.makePacket(12,'multi',f.context));f.emitPacket(f.makePacket(11,'multi',f.context));});
   await page.locator('[data-action=step]').click();assert.equal((await view(page)).sequence,12);
   assert.ok((await view(page)).pose.value);
  });
  for(const slot of ['robot_pose','joint_state'])await run(`missing ${slot} stays unavailable`,async page=>{
   await page.evaluate(slot=>{const f=window.c3Fixture,p=f.makePacket(12,'multi',f.context);p[slot]=null;f.emitPacket(p);},slot);
   await page.waitForFunction(()=>window.c3Fixture.feature.snapshot()?.sequence===12);
   assert.equal((await view(page))[slot==='robot_pose'?'pose':'joints'].reason,'MISSING');await hidden(page);
  });
  await run('source clock mismatch cannot display robot/risk',async page=>{
   await page.evaluate(()=>{const f=window.c3Fixture;f.setContext({...f.context,clock_domain:'new-clock'});const p=f.makePacket(12,'multi',f.context);p.clock_domain='foreign';f.emitPacket(p);});
   await page.waitForFunction(()=>!window.c3Fixture.feature.snapshot().ready);await hidden(page);
   assert.equal(await page.evaluate(()=>window.c3Fixture.feature.diagnostics().error),'CLOCK_MISMATCH');
   await send(page);assert.ok((await view(page)).pose.value);
  });
  await run('snapshot read ages even without a subsequent animation frame',async page=>{
   await send(page);await pause(page);
   const result=await page.evaluate(()=>{
    // Block this test page's event loop beyond pose TTL: no rAF can refresh a
    // cached displayed value before the synchronous public API read.
    const start=performance.now();while(performance.now()-start<550){};
    const v=window.c3Fixture.feature.snapshot();return {reason:v.pose.reason,collision:v.collision.value};
   });assert.equal(result.reason,'STALE');assert.equal(result.collision,null);await hidden(page);
  });
  await run('C1 expired notification during pause fences a coalesced late ready response',async page=>{
   await pause(page);
   const result=await page.evaluate(async wire=>{
    const f=window.c3Fixture,{adaptC1ScenePacket}=await import('/robot_dashboard/static/features/obstacle_scene/c1_adapter.js');
    const context={...wire.map_binding,frame_id:'map',units:'m',source_epoch:wire.robot_pose.source_epoch,stream_epoch:wire.stream_epoch,clock_domain:wire.robot_pose.clock_domain,calibration_id:'synthetic-calibration'};
    f.setContext(context);window.wire=wire;window.adapt=w=>adaptC1ScenePacket(w,context).packet;f.emitPacket(window.adapt(wire));return wire.sequence;
   },wire);
   await page.locator('[data-action=step]').click();await page.waitForFunction(s=>window.c3Fixture.feature.snapshot()?.sequence===s,result);
   assert.ok((await view(page)).pose.value);
   await page.evaluate(()=>{
    const w=structuredClone(window.wire);for(const slot of ['robot_pose','obstacle_frame','collision_assessment']){w[slot]=null;w.sources[slot].status='expired';}
    window.c3Fixture.emitPacket(window.adapt(w));window.c3Fixture.emitPacket(window.adapt(window.wire));
   });
   await page.waitForFunction(()=>window.c3Fixture.feature.snapshot().pose.reason==='SERVER_INVALIDATED');await hidden(page);
   await page.locator('[data-action=pause]').click();assert.equal((await view(page)).pose.reason,'SERVER_INVALIDATED');
  });
 }finally{await context.close();await browser.close();}
}
assert.deepEqual(report.errors,[]);assert.ok(report.requests.every(r=>r.method==='GET'&&new URL(r.url).origin===new URL(url).origin));
await writeFile(resolve(out,'paused-browser-results.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({cases:report.cases,errors:report.errors,requests:report.requests.length},null,2));
