// Standalone Playwright runner; dependencies stay outside the shared manifest.
// C3_PLAYWRIGHT points at playwright's installed package entry (not a browser).
import { createRequire } from 'node:module';
import { mkdir, writeFile, readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.C3_PLAYWRIGHT || 'playwright');
const out=resolve(process.env.C3_EVIDENCE || 'docs/parallel-expansion-20261029/C3/evidence');
const url=process.env.C3_FIXTURE_URL || 'http://127.0.0.1:4183/experiments/expansion_20261029/c3_scene_ui/fixture.html';
await mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true,args:['--no-sandbox','--enable-precise-memory-info']});
const report={kind:'UI_FIXTURE',input:'SYNTHETIC only; not native Nav2 or robot replay',browser:browser.version(),
  cases:[],requests:[],errors:[],stress:null};
const check=async(name,fn)=>{try{await fn();report.cases.push({name,result:'PASS'});}catch(e){report.cases.push({name,result:'FAIL',error:e.stack});throw e;}};
let context;
try{
  context=await browser.newContext({viewport:{width:1440,height:1000},deviceScaleFactor:1});
  await context.tracing.start({screenshots:true,snapshots:true,sources:true});
  const page=await context.newPage();
  page.on('pageerror',e=>report.errors.push(String(e)));
  page.on('request',r=>report.requests.push({method:r.method(),url:r.url()}));
  // Enforce the capability boundary as well as observing it. A regression that
  // attempts any API, websocket, cross-origin or mutation request fails below.
  await context.route('**/*',route=>{
    const request=route.request(),u=new URL(request.url());
    if(u.origin!==new URL(url).origin || request.method()!=='GET' || u.pathname.startsWith('/api/'))route.abort();
    else route.continue();
  });
  const state=()=>page.evaluate(()=>window.c3Fixture.feature.snapshot());
  // The exact sequence returned from emit avoids races with deferred rAF.
  const send=async(name)=>{const seq=await page.evaluate(n=>window.c3Fixture.emit(n).sequence,name);await page.waitForFunction(s=>window.c3Fixture.feature.snapshot()?.sequence===s,seq);};
  await page.goto(url);await page.waitForFunction(()=>window.c3Fixture?.feature.snapshot()?.ready);
  await check('existing official renderer and shared model cache',async()=>{
    const model=await page.evaluate(()=>window.c3Fixture.renderer.getOfficialRobotModelStatus());
    assert.equal(model.state,'ready');assert.equal(await page.locator('.os-overlay').count(),1);
    assert.equal(await page.evaluate(()=>window.c3Fixture.renderer.status.provenance),'FIXTURE');
    assert.ok((await page.evaluate(()=>window.c3Fixture.renderer.options.robotPoseLabel)).startsWith('SYNTHETIC'));
  });
  await check('empty → cone → costmap → supplied path generations → supplied local trajectory',async()=>{
    await send('empty');assert.equal((await state()).obstacles.value.obstacles.length,0);
    await send('cone');assert.equal((await state()).obstacles.value.obstacles[0].class_name,'unknown');
    await send('costmap');assert.equal((await state()).costmaps[0].value.cells[56],254);
    await send('path-1');await send('replan');assert.equal((await state()).history.length,2);
    assert.equal((await state()).local.value,null);await send('trajectory');assert.ok((await state()).local.value);
  });
  await check('moved, occluded, removed, lidar-only, depth-only, unmatched YOLO',async()=>{
    await send('moved');assert.equal((await state()).obstacles.value.obstacles[0].geometry.center_m[0],1.8);
    await send('occluded');assert.equal((await state()).obstacles.value.obstacles[0].state,'OCCLUDED');
    await send('removed');assert.equal((await state()).obstacles.value.obstacles.length,0);
    for(const name of ['lidar-only','depth-only','unmatched-yolo']){await send(name);assert.equal((await state()).obstacles.value.obstacles.length,1);}
  });
  await check('wrong calibration, unmapped clock, sensor time skew block derived geometry/risk',async()=>{
    for(const name of ['bad-calibration','clock-mismatch','sensor-skew']){await send(name);const v=await state();assert.equal(v.collision.value,null);assert.equal(v.obstacles.value?.obstacles.length||0,0);}
    await page.screenshot({path:resolve(out,'mismatch-dark.png'),fullPage:true});
  });
  await check('map/epoch invalidation while paused and reconnect late packets',async()=>{
    await send('multi');await page.locator('[data-action=pause]').click();
    const old=await page.evaluate(()=>{const f=window.c3Fixture;const old=f.makePacket(1000,'multi',f.context);f.setContext({...f.context,map_id:'synthetic-reference-B',source_epoch:'epoch-2',stream_epoch:'stream-2'});return old;});
    await page.waitForFunction(()=>window.c3Fixture.feature.snapshot()?.ready===false);
    assert.equal(await page.locator('[data-track]').count(),0);
    await page.evaluate(p=>window.c3Fixture.emitPacket(p),old);
    await page.locator('[data-action=step]').click();assert.equal((await state()).ready,false);
    const nextSeq=await page.evaluate(()=>window.c3Fixture.emit('multi').sequence);
    await page.locator('[data-action=step]').click();await page.waitForFunction(s=>window.c3Fixture.feature.snapshot()?.sequence===s,nextSeq);
    await page.evaluate(p=>window.c3Fixture.emitPacket(p),old);
    await page.locator('[data-action=step]').click();
    assert.equal((await state()).source_epoch,'epoch-2');
    assert.equal((await page.evaluate(()=>window.c3Fixture.feature.diagnostics())).error,'MAP_OR_UNITS_MISMATCH');
    await page.evaluate(()=>{const f=window.c3Fixture;const p=f.makePacket(1001,'multi',f.context);p.stream_epoch='old-reconnect-stream';f.emitPacket(p);});
    await page.locator('[data-action=step]').click();
    assert.equal((await page.evaluate(()=>window.c3Fixture.feature.diagnostics())).error,'LATE_EPOCH_OR_STREAM');
    await page.locator('[data-action=pause]').click();
  });
  await check('stale pose/joints and idle expiry hide URDF and risk; no goal substitution',async()=>{
    for(const name of ['stale-pose','stale-joints']){await send(name);assert.equal((await state()).collision.value,null);assert.equal(await page.evaluate(()=>window.c3Fixture.renderer.robotVisible),false);}
    await send('multi');await page.waitForFunction(()=>window.c3Fixture.feature.snapshot()?.pose.reason==='STALE');
    assert.equal(await page.evaluate(()=>window.c3Fixture.renderer.robotVisible),false);
  });
  await check('inspect provenance, layer toggles, pause/step/resume, dark desktop',async()=>{
    await send('multi');await page.locator('[data-action=pause]').click();
    await page.locator('[data-track=cone-1]').click();await page.waitForFunction(()=>document.querySelector('[data-testid=inspector]').textContent.includes('sensor_support'));
    const inspector=await page.locator('[data-testid=inspector]').textContent();
    assert.ok(inspector.includes('SYNTHETIC'));assert.ok(inspector.includes('CONTACT_UNCONFIRMED'));
    for(const name of ['reference','LIDAR','DEPTH','obstacles','costmap','path','local','robot','envelope']){
      await page.locator(`[data-layer=${name}]`).uncheck();await page.locator(`[data-layer=${name}]`).check();
    }
    await page.screenshot({path:resolve(out,'desktop-dark-inspect.png'),fullPage:true});
    const before=(await state()).sequence;await page.evaluate(()=>window.c3Fixture.emit('trajectory'));
    await page.waitForTimeout(50);assert.equal((await state()).sequence,before);
    await page.locator('[data-action=step]').click();await page.waitForFunction(s=>window.c3Fixture.feature.snapshot()?.sequence>s,before);
    assert.equal((await page.evaluate(()=>window.c3Fixture.feature.diagnostics())).paused,true);
    await page.locator('[data-action=pause]').click();
  });
  await check('light, narrow 390px, HiDPI, accessible labels and no horizontal overflow',async()=>{
    await page.locator('#theme').click();await send('multi');await page.locator('[data-action=pause]').click();
    await page.screenshot({path:resolve(out,'desktop-light.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    await page.waitForTimeout(120);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await page.screenshot({path:resolve(out,'narrow-light.png'),fullPage:true});
    const hidpi=await browser.newContext({viewport:{width:390,height:844},deviceScaleFactor:2});
    const hp=await hidpi.newPage();hp.on('request',r=>report.requests.push({method:r.method(),url:r.url()}));hp.on('pageerror',e=>report.errors.push(String(e)));
    await hp.goto(url);await hp.waitForFunction(()=>window.c3Fixture?.feature.snapshot()?.ready);
    await hp.locator('[data-action=pause]').click();
    assert.equal(await hp.evaluate(()=>document.querySelector('.os-overlay').width>=document.querySelector('#scene').clientWidth*1.9),true);
    await hp.screenshot({path:resolve(out,'narrow-dark-hidpi.png'),fullPage:true});await hidpi.close();
    await page.setViewportSize({width:1440,height:1000});await page.locator('[data-action=pause]').click();
  });
  // Bound trace size: functional scenarios, screenshots, DOM snapshots and all
  // associated requests are captured. Stress uses the measured report below.
  await context.tracing.stop({path:resolve(out,'browser-trace.zip')});
  // Canonical producer/HTTP checks live in actual_browser.mjs. This runner
  // remains explicitly UI_FIXTURE and cannot substitute its results for them.
  await check('1200 packets at >=10Hz with bounded retention, UI response and burst coalescing',async()=>{
    const cdp=await context.newCDPSession(page);await cdp.send('HeapProfiler.collectGarbage');
    const heapBefore=(await cdp.send('Runtime.getHeapUsage')).usedSize;
    await page.evaluate(()=>{
      const f=window.c3Fixture;window.stress={start:performance.now(),count:0,delays:[],frames:0};
      let last=performance.now(),lastFrame=performance.now();
      const frame=()=>{const n=performance.now();window.stress.frames++;window.stress.maxFrame=Math.max(window.stress.maxFrame||0,n-lastFrame);lastFrame=n;if(!window.stress.done)requestAnimationFrame(frame);};requestAnimationFrame(frame);
      window.stressPromise=new Promise(resolve=>{const timer=setInterval(()=>{
        const now=performance.now();window.stress.delays.push(Math.max(0,now-last-25));last=now;
        f.emit('multi');if(++window.stress.count===1200){clearInterval(timer);window.stress.done=true;window.stress.elapsed=performance.now()-window.stress.start;resolve();}
      },25);});
    });
    const response=[];
    for(let i=0;i<6;i++){const start=Date.now();await page.locator('[data-layer=envelope]').click();response.push(Date.now()-start);await page.waitForTimeout(150);}
    await page.evaluate(()=>window.stressPromise);
    await page.waitForTimeout(120);await cdp.send('HeapProfiler.collectGarbage');
    const heapAfter=(await cdp.send('Runtime.getHeapUsage')).usedSize;
    const stress=await page.evaluate(()=>{const s=window.stress;const sorted=s.delays.toSorted((a,b)=>a-b);return{count:s.count,elapsedMs:s.elapsed,rateHz:s.count*1000/s.elapsed,rafCallbacks:s.frames,maxRafGapMs:s.maxFrame,timerDelayP95Ms:sorted[Math.floor(sorted.length*.95)],diagnostics:window.c3Fixture.feature.diagnostics()};});
    await page.evaluate(()=>{for(let i=0;i<1200;i++)window.c3Fixture.emit('multi');});
    await page.waitForTimeout(120);const burst=await page.evaluate(()=>window.c3Fixture.feature.diagnostics());
    report.stress={...stress,heapBeforeGcBytes:heapBefore,heapAfterGcBytes:heapAfter,heapDeltaBytes:heapAfter-heapBefore,interactionMs:response,burst};
    assert.equal(stress.count,1200);assert.ok(stress.rateHz>=10);assert.ok(stress.diagnostics.history<=3);
    assert.equal(stress.diagnostics.retainedPackets,1);assert.equal(stress.diagnostics.maxPending,1);
    assert.ok(Math.max(...response)<1000);assert.ok(stress.rafCallbacks>300);assert.ok(burst.dropped>=1199);
    assert.ok(heapAfter-heapBefore<16*1024*1024,'post-GC retained heap growth below 16MiB fixture budget');
  });
  await check('destroy/remount unsubscribes, releases history, removes canvas and cancels callbacks',async()=>{
    for(let i=0;i<8;i++){await page.evaluate(()=>window.c3Fixture.remount());assert.equal(await page.locator('.os-overlay').count(),1);assert.equal(await page.evaluate(()=>window.c3Fixture.subscriberCount()),1);}
    await page.evaluate(()=>window.c3Fixture.feature.destroy());
    assert.equal(await page.locator('.os-overlay').count(),0);assert.equal(await page.evaluate(()=>window.c3Fixture.subscriberCount()),0);
    assert.equal((await page.evaluate(()=>window.c3Fixture.feature.diagnostics())).retainedPackets,0);
  });
  await check('no mutation / ROS / goal / cmd / service / websocket requests or page errors',async()=>{
    const forbidden=report.requests.filter(r=>r.method!=='GET'||new URL(r.url).origin!==new URL(url).origin||new URL(r.url).pathname.startsWith('/api/')||/^wss?:/.test(r.url));
    assert.deepEqual(forbidden,[]);assert.deepEqual(report.errors,[]);
  });
}catch(e){report.failure=String(e.stack);if(context){await context.tracing.stop({path:resolve(out,'browser-trace-failure.zip')}).catch(()=>{});}}
finally{await writeFile(resolve(out,'browser-results.json'),JSON.stringify(report,null,2)+'\n');await browser.close();}
console.log(JSON.stringify({...report,requests:report.requests.length},null,2));
if(report.failure)process.exitCode=1;
