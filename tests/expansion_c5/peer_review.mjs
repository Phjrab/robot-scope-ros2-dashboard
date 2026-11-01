// Read-only replay of C3's published endpoint bytes through C3's real adapter
// and consumer. This does not execute C1/D2/D3 or reproduce their algorithms.
import { chromium, webkit, expect } from '@playwright/test';
import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { root, peers, urls, startHosts } from './hosts.mjs';
const out=`${root}/docs/parallel-expansion-20261030/C5/evidence`;
const stop=await startHosts();const report={classification:'C3 archived HTTP-byte replay; no current service/core/native execution',replay:[],findings:[]};
try{for(const [engine,type] of Object.entries({chromium,webkit})){
 const browser=await type.launch();
 try{
  for(const name of ['PREDICTED_CONTACT','ACTIVE_UNKNOWN','EXPIRED','NATIVE_REPLAY']){
   const source=`${peers}/c3/docs/parallel-expansion-20261029/C3/evidence/round2-v02/${name}.http-body.json`;
   const raw=await readFile(source,'utf8'),wire=JSON.parse(raw);
   const epoch=wire.robot_pose?.source_epoch||'sensor-6';
   const context={...wire.map_binding,frame_id:'map',source_epoch:epoch,stream_epoch:wire.stream_epoch,clock_domain:wire.robot_pose?.clock_domain||'synthetic-host-correspondence',calibration_id:name==='NATIVE_REPLAY'?'native-not-supplied':'synthetic-calibration',units:'m',source_identity:'C5_READ_ONLY_ARCHIVED_C3_HTTP_BYTES'};
   const page=await browser.newPage({viewport:{width:768,height:1100}});const requests=[];
   await page.route('**/*',r=>{requests.push({method:r.request().method(),url:r.request().url()});new URL(r.request().url()).origin===new URL(urls.c3).origin?r.continue():r.abort();});
   try{
    await page.goto(urls.c3);await page.waitForFunction(()=>!!window.c3Fixture);
    await page.locator('[data-action=pause]').click();await expect(page.locator('.os-mode')).toContainText('PAUSED');
    const result=await page.evaluate(async({wire,context})=>{
      const {adaptC1ScenePacket}=await import('/robot_dashboard/static/features/obstacle_scene/c1_adapter.js');
      const f=window.c3Fixture;f.setContext(context);const adapted=adaptC1ScenePacket(wire,context);if(!adapted.packet)throw new Error(adapted.reason);
      f.renderer.clearPointCloud();f.emitPacket(adapted.packet);
      document.querySelector('.fixture-banner strong').textContent='C5 · 기록된 C3 HTTP 응답 재생 · 현재 서비스/실장비 아님';
      document.querySelector('.fixture-caption').textContent='원본 HTTP 응답만 사용. Bulk geometry 파일 미제공: 새 geometry를 만들지 않음. 공식 URDF asset은 기존 renderer 사용. 합성/기록 재생은 원본 evidence_kind 그대로.';
      return {reason:adapted.reason};
    },{wire,context});
    await page.locator('[data-action=step]').click();
    await expect(page.locator('.os-mode')).toContainText(wire.evidence_kind);
    await page.addStyleTag({path:`${root}/robot_dashboard/static/features/operator_usability/operator_usability.css`});
    const helper=await readFile(`${root}/robot_dashboard/static/features/operator_usability/index.js`,'utf8');
    await page.addScriptTag({type:'module',content:helper+"\nmountOperatorUsability(document.querySelector('.obstacle-scene'),'obstacles');"});
    const risk=await page.locator('.os-risk').textContent();
    if(name==='PREDICTED_CONTACT'){assert.match(risk,/ADVISORY_ONLY/);assert.match(risk,/STOP_REQUIRED/);}
    if(name==='ACTIVE_UNKNOWN'){assert.match(risk,/ACTIVE_CONSTRAINT/);assert.match(risk,/UNKNOWN/);assert.match(risk,/HOLD_FOR_VALID_INPUT/);}
    if(['EXPIRED','NATIVE_REPLAY'].includes(name))assert.match(risk,/UNKNOWN/);
    assert.doesNotMatch(await page.locator('.os-mode').textContent(),/LIVE 입력/);
    await page.locator('.obstacle-scene').screenshot({path:`${out}/${engine}-recorded-${name}.png`});
    report.replay.push({engine,name,sha256:createHash('sha256').update(raw).digest('hex'),risk,mode:await page.locator('.os-mode').textContent(),result:'PASS',adapter:result,requests:requests.length});
   }finally{await page.close();}
  }
  // A current consumer snapshot expires, but C3's displayed snapshot is frozen
  // during pause. This is an upstream presentation/state ownership handoff.
  const page=await browser.newPage({viewport:{width:390,height:1000}});
  try{
   await page.goto(urls.c3);await page.waitForFunction(()=>window.c3Fixture?.feature.snapshot()?.ready);
   const packet=await page.evaluate(()=>window.c3Fixture.emit('multi'));await expect(page.locator('.os-sources')).toContainText('FRESH');
   await page.locator('[data-action=pause]').click();await expect(page.locator('.os-mode')).toContainText('PAUSED');
   // The public feature snapshot is itself the frozen displayed object. Use a
   // second, unchanged C3 consumer with the exact same packet to expose expiry.
   const expiry=await page.evaluate(async packet=>{
     const {createSceneConsumer}=await import('/robot_dashboard/static/features/obstacle_scene/consumer.js');
     let now=0;const c=createSceneConsumer({getMap:()=>window.c3Fixture.context,clock:()=>now});c.ingest(packet);now=2500;const v=c.snapshot();c.destroy();return {pose:v.pose.reason,collision:v.collision.reason};
   },packet);
   await page.waitForTimeout(2600);
   const evidence=await page.evaluate(()=>({poseReason:window.c3Fixture.feature.snapshot().pose.reason,collisionReason:window.c3Fixture.feature.snapshot().collision.reason,visibleSources:document.querySelector('.os-sources').textContent,visibleRisk:document.querySelector('.os-risk').textContent,robotVisible:window.c3Fixture.renderer.robotVisible}));
   assert.match(evidence.visibleSources,/FRESH/);assert.equal(evidence.robotVisible,true);
   assert.equal(expiry.pose,'STALE');
   report.findings.push({id:'C5-H1',engine,severity:'P1',owner:'C3',result:'REPRODUCED',elapsedMs:2600,independentC3Consumer:expiry,...evidence});
   await page.locator('.obstacle-scene').screenshot({path:`${out}/${engine}-paused-expired-original.png`});
  }finally{await page.close();}
 }finally{await browser.close();}
}}finally{stop();await writeFile(`${out}/peer-review.json`,JSON.stringify(report,null,2)+'\n');}
console.log(JSON.stringify(report,null,2));
