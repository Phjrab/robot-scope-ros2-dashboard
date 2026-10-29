import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {startServer} from '../../experiments/expansion_20261029/c2_map_ui/server.mjs';
const {chromium}=await import(process.env.C2_PLAYWRIGHT_MODULE||'playwright');
assert.ok(process.env.C2_C1_SERVICE_URL,'Start exact_service_host.py --round2');
const evidence=JSON.parse(await readFile(process.env.C2_ROUND2_SERVICE_REPORT,'utf8'));
const server=await startServer(0),origin=`http://127.0.0.1:${server.address().port}`;
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
const results=[],violations=[],errors=[],posts=[];
const ready=(p,text)=>p.waitForFunction(t=>document.querySelector('[data-slot=status]')?.textContent.includes(t),text);
const snapshot=p=>p.evaluate(()=>window.module.snapshot());
async function page(scenario='c1-service'){
 const p=await browser.newPage({viewport:{width:1440,height:1080}});p.on('pageerror',e=>errors.push(e.message));
 await p.route('**/*',r=>{const q=r.request(),u=new URL(q.url());if(u.origin!==origin||(!['GET','HEAD'].includes(q.method())&&!/^\/api\/v1\/extensions\/multimap\/jobs(?:\/[a-f0-9]{24}\/(review|exports|cancel))?$/.test(u.pathname))){violations.push(q.url());return r.abort();}if(q.method()==='POST')posts.push(u.pathname);return r.continue();});
 await p.goto(`${origin}/?scenario=${scenario}`);await p.waitForFunction(()=>!!window.module);await p.evaluate(()=>window.module.ready);return p;
}
async function select(p,ids){for(const id of ids){await p.locator(`[data-source="${id}"]`).check();await ready(p,'previews ready');}}
async function prior(p,id,pose){await p.locator('[data-field=target]').selectOption(id);for(const[key,value]of Object.entries(pose)){await p.locator(`[data-pose="${key}"]`).fill(String(value));await p.locator(`[data-pose="${key}"]`).press('Tab');}}
async function solve(p){await p.locator('[data-action=start]').click();await ready(p,'SOLVED_CANDIDATE');assert.equal((await snapshot(p)).proposal.connected_components.length,1);}
async function save(p,name){
 await p.locator('[data-field=ack]').check();await p.locator('[data-action=accept]').click();await ready(p,'ACCEPTED');
 assert.equal(await p.locator('[data-action=accept]').isDisabled(),true);
 await p.locator('[data-field=name]').fill(name);const response=p.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/exports'));
 await p.locator('[data-action=save]').click();const manifest=await(await response).json();await ready(p,'Saved and listed');
 assert.match(await p.locator('[data-slot=saved]').textContent(),/offline BundleStore/);
 assert.equal(manifest.operational_installed,false);return manifest;
}
try{
 const ids=[1,2,3].map(i=>i.toString(16).padStart(24,'0'));
 const b={x:.35,y:-.2,z:.15,roll:.06,pitch:-.04,yaw:.18},c={x:-.3,y:.15,z:-.1,roll:-.03,pitch:.08,yaw:-.13};
 let p=await page();await select(p,ids.slice(0,2));await prior(p,ids[1],b);await solve(p);const ab=await save(p,`round2_AB_${Date.now()}`);assert.equal(ab.point_count,800);await p.close();
 results.push({name:'2-map actual TCP HTTP/core + offline save/refresh',result:'PASS'});
 p=await page();await select(p,ids);await prior(p,ids[1],b);await prior(p,ids[2],c);await solve(p);const abc=await save(p,`round2_ABC_${Date.now()}`);assert.equal(abc.point_count,1200);await p.close();
 results.push({name:'3-map actual TCP HTTP/core + offline save/refresh',result:'PASS'});
 p=await page();await select(p,[ab.id,ids[2]]);await p.locator('[data-field=anchor]').selectOption(ab.id);await prior(p,ids[2],c);await solve(p);const incremental=await save(p,`round2_AB_C_${Date.now()}`);
 assert.equal(incremental.point_count,1200);assert.notEqual(incremental.id,abc.id);
 assert.ok(ids.every(id=>Object.keys(incremental.provenance_dag).some(k=>k.startsWith(id+':'))));await p.close();
 results.push({name:'(A+B)+C actual UI/core/export preserves all three roots and new identity',result:'PASS'});
 p=await page();await select(p,[ab.id,abc.id]);await p.locator('[data-action=start]').click();await ready(p,'C1 HTTP 409: stale input/revision or immutable conflict');assert.equal((await snapshot(p)).draft.sources.length,2);assert.equal(await p.locator('[data-action=accept]').isDisabled(),true);await p.close();
 results.push({name:'overlapping roots: actual HTTP refusal displayed unchanged, both inputs retained',result:'PASS',limitation:'C1 HTTP detail does not expose duplicate-ancestor reason'});
 p=await page('normal');await select(p,['map-a','map-b']);
 await p.evaluate(metrics=>{const get=window.fixture.jobs.get;window.fixture.jobs.get=async(...args)=>{const value=await get(...args);if(value.state==='SOLVED_CANDIDATE')value.metrics={pairwise:[{pair:['map-a','map-b'],overlap:1,rmse_m:metrics.rmse_m,distance_p95_m:metrics.distance_p95_m}]};return value;};},evidence.zero_residual.metrics);
 await solve(p);assert.match(await p.locator('[data-slot=diagnostics]').textContent(),/0\.0000 p95 \/ 0\.0000 RMSE/);assert.equal((await snapshot(p)).proposal.metrics.pairwise[0].rmse_m,0);await p.close();
 results.push({name:'exact zero residual displayed as 0.0000',result:'PASS',classification:'UI_FIXTURE with ACTUAL_CORE_METRIC; not corrected D1 candidate ranking'});
 assert.deepEqual(errors,[]);assert.deepEqual(violations,[]);
}finally{
 await browser.close();await new Promise(r=>server.close(r));
 await writeFile(process.env.C2_ROUND2_BROWSER_REPORT,JSON.stringify({classification:'ACTUAL_TCP_HTTP + ACTUAL_CORE / SYNTHETIC, plus separately labeled UI_FIXTURE',results,errors,violations,post_count:posts.length,product_ros_native:'NOT_RUN'},null,2)+'\n');
}
console.log(JSON.stringify(results,null,2));
