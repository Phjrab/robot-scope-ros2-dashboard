import {createRequire} from 'node:module';
import fs from 'node:fs';
import assert from 'node:assert/strict';
const require=createRequire(process.env.C6_PLAYWRIGHT_PACKAGE || new URL('../../package.json',import.meta.url));
const {chromium}=require('@playwright/test');
const browser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const errors=[],requests=[];
page.on('pageerror',e=>{errors.push(e.message);console.error('pageerror',e.message);});
page.on('response',r=>{if(r.status()>=400)console.error('HTTP',r.status(),r.url());});
page.on('request',r=>requests.push({url:r.url(),method:r.method()}));
await page.goto('http://127.0.0.1:8766/');
await page.waitForFunction(()=>!!window.c6Review);
const fixture=process.env.C6_FIXTURES;
const load=async(i,name)=>{await page.locator(`input[data-run="${i}"]`).setInputFiles(`${fixture}/${name}`);await page.waitForTimeout(100);};
await load(0,'review-0.json');await load(1,'review-1.json');
assert.match(await page.locator('.rr-comparison').textContent(),/동일 조건 A\/B 아님/);
await page.getByRole('button',{name:'한 단계 →',exact:true}).click();
await page.getByRole('button',{name:'재생',exact:true}).click();await page.waitForTimeout(100);
await page.getByRole('button',{name:'일시정지',exact:true}).click();
const stopped=await page.evaluate(()=>window.c6Review.replay.state().playhead);await page.waitForTimeout(150);
assert.equal(await page.evaluate(()=>window.c6Review.replay.state().playhead),stopped);
await load(0,'review-3.json');await page.waitForTimeout(150);
assert.equal(await page.evaluate(()=>window.c6Review.sceneFeature.snapshot().evidence_kind),'REPLAY');
await page.evaluate(()=>window.c6Review.replay.seek('1000000000'));await page.waitForTimeout(100);
assert.equal(await page.evaluate(()=>window.c6Review.sceneFeature.snapshot().path.value),null);
await page.evaluate(()=>window.c6Review.replay.seek('0'));await page.waitForTimeout(100);
assert.ok(await page.evaluate(()=>window.c6Review.sceneFeature.snapshot().path.value));
await page.evaluate(()=>window.c6Review.replay.seek(window.c6Review.replay.state().end));await page.waitForTimeout(100);
assert.equal(await page.evaluate(()=>window.c6Review.sceneFeature.snapshot().path.value),null);
assert.match(await page.locator('.rr-banner').textContent(),/REPLAY/);
// Untrusted strings are text nodes. No HTML/resource evaluation.
const hostile=JSON.parse(fs.readFileSync(`${fixture}/review-0.json`));hostile.provenance.source_id='<img src="https://invalid.example/x" onerror="window.c6Xss=1">';
await page.evaluate(r=>window.c6Review.load(r),hostile);
assert.equal(await page.evaluate(()=>window.c6Xss),undefined);
assert.equal(await page.locator('.rr-overview img').count(),0);
await page.locator('input[data-run="0"]').setInputFiles(process.env.C6_NATIVE_REVIEW);await page.waitForTimeout(150);
assert.ok(await page.evaluate(()=>window.c6Review.sceneFeature));
await page.evaluate(()=>window.c6Review.replay.seek('4000000000'));await page.waitForTimeout(150);
assert.equal(await page.evaluate(()=>window.c6Review.sceneFeature.snapshot().evidence_kind),'REPLAY');
const geometry = await page.evaluate(()=>{
 const v=window.c6Review.sceneFeature.snapshot(),r=window.c6Scene,c=document.querySelector('.os-overlay'),d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;
 return {path:v.path.value?.points_m.slice(0,2),projection:v.path.value?.points_m.slice(0,2).map(p=>r._project(p)),width:r.width,height:r.height,canvas:[c.width,c.height],drawn:d.filter((v,i)=>i%4===3&&v>0).length};
});
assert.ok(geometry.drawn>0,'actual C3 path pixels must be visible');
await page.screenshot({path:process.env.C6_SCREENSHOT,fullPage:true});
if(process.env.C6_REAL_REVIEW_DIR){
 const real=process.env.C6_REAL_REVIEW_DIR;
 for(const i of [0,1]){
  const file=`${real}/goal-${i}.private.json`;
  const r=JSON.parse(fs.readFileSync(file));
  await page.locator(`input[data-run="${i}"]`).setInputFiles(file);await page.waitForTimeout(100);
  if(i===0){
   const text=await page.locator('.rr-precision').textContent();
   assert.ok(text.includes(r.precision.near_result.stamp_ns));
   assert.ok(text.includes(String(r.precision.requested.x)));
   assert.ok(text.includes(String(r.precision.after_stop.pose.yaw)));
  }
 }
 assert.match(await page.locator('.rr-comparison').textContent(),/동일 조건 A\/B 아님/);
 assert.match(await page.locator('.rr-banner').textContent(),/REPLAY/);
}
assert.deepEqual(errors,[]);
assert.equal(requests.filter(r=>r.method!=='GET'||!r.url.startsWith('http://127.0.0.1:8766/')).length,0);
console.log(JSON.stringify({browser:'PASS',actual_c3_mount:true,external_requests:0,control_mutations:0,requests:requests.length,scenarios:['arrival','heading-comparison','paused','stale','seek-back','map-change','XSS','D3-native-replay']}));
await browser.close();
