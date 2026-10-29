import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {startServer} from '../../experiments/expansion_20261029/c2_map_ui/server.mjs';
const {chromium}=await import(process.env.C2_PLAYWRIGHT_MODULE||'playwright');
const output=fileURLToPath(new URL('../../docs/parallel-expansion-20261029/C2/screenshots/',import.meta.url));await mkdir(output,{recursive:true});
const server=await startServer(0),base=`http://127.0.0.1:${server.address().port}`;
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
const results=[],screenshots=[],contexts=[];
let violations=[],apiAudit=[],pageErrors=[],httpAudit=[],exactEvidence=null;
async function pageFor(scenario='normal',options={}){
  const context=await browser.newContext({viewport:{width:1440,height:1080},deviceScaleFactor:options.dpr||1,...options});contexts.push(context);
  const page=await context.newPage();page.errors=[];page.on('pageerror',e=>page.errors.push(e.message));
  await page.route('**/*',route=>{const req=route.request(),url=new URL(req.url());if(scenario==='c1-service'&&url.pathname.startsWith('/api/v1/extensions/multimap/'))httpAudit.push({path:url.pathname,method:req.method()});if(url.origin!==base||(req.method()!=='GET'&&!(scenario==='c1-service'&&req.method()==='POST'&&url.pathname.startsWith('/api/v1/extensions/multimap/')))){violations.push({url:req.url(),method:req.method()});return route.abort();}return route.continue();});
  await page.goto(`${base}/?scenario=${scenario}&delay=20`);await page.waitForFunction(()=>!!window.module);await page.evaluate(()=>window.module.ready);return page;
}
async function closePage(p){apiAudit.push(...await calls(p));pageErrors.push(...p.errors);await p.close();}
const status=p=>p.locator('[data-slot=status]');
async function ready(p,text){await p.waitForFunction(t=>document.querySelector('[data-slot=status]')?.textContent.includes(t),text);}
async function select(p,three=false){await p.getByRole('checkbox',{name:'Select West hall',exact:true}).check();await ready(p,'previews ready');await p.getByRole('checkbox',{name:'Select East hall',exact:true}).check();await ready(p,'previews ready');if(three){await p.getByRole('checkbox',{name:'Select Upper wing',exact:true}).check();await ready(p,'previews ready');}}
async function solve(p){await p.locator('[data-action=start]').click();await ready(p,'SOLVED_CANDIDATE');}
async function shot(p,name){if(process.env.C2_SKIP_SCREENSHOTS==='1')return;await p.screenshot({path:output+name+'.png',fullPage:true});screenshots.push(name+'.png');}
async function check(name,fn){try{await fn();results.push({name,result:'PASS'});console.log('PASS',name);}catch(e){results.push({name,result:'FAIL',error:e.stack});console.error('FAIL',name,e.message);}}
const snap=p=>p.evaluate(()=>window.module.snapshot());
const calls=p=>p.evaluate(()=>window.fixture.calls);
async function drag(p,{dx=45,dy=20,yaw=false}={}){await p.locator('[data-canvas=xy]').scrollIntoViewIfNeeded();const box=await p.locator('[data-canvas=xy]').boundingBox();const x=yaw?box.x+box.width-34:box.x+box.width/2,y=yaw?box.y+46:box.y+box.height/2;await p.mouse.move(x,y);await p.mouse.down();await p.mouse.move(x+dx,y+dy,{steps:5});await p.mouse.up();}
try{
 await check('open/click/keyboard/drag, rotated non-square scale, no API mutations',async()=>{
  const p=await pageFor();assert.equal((await calls(p)).filter(c=>!['sources','preview'].includes(c.operation)).length,0);
  await select(p);await p.locator('[data-field=rotation]').fill('.65');await p.locator('[data-field=rotation]').press('Tab');await drag(p);
  const s=await snap(p);assert.ok(s.draft.priors['map-b'].x>0);assert.ok(s.draft.priors['map-b'].y<0);
  await p.locator('[data-canvas=xy]').focus();await p.keyboard.press('ArrowRight');await p.keyboard.press('q');assert.ok((await snap(p)).revision>s.revision);
  await drag(p,{dx:24,dy:0,yaw:true});assert.ok((await snap(p)).draft.priors['map-b'].yaw>.1);
  for(const [label,value,key]of [['Z m (advanced)','0.35','z'],['Roll rad (advanced)','0.1','roll'],['Pitch rad (advanced)','0.15','pitch']]){await p.getByRole('spinbutton',{name:label,exact:true}).fill(value);await p.getByRole('spinbutton',{name:label,exact:true}).press('Tab');assert.equal((await snap(p)).draft.priors['map-b'][key],Number(value));}
  assert.equal((await calls(p)).filter(c=>!['sources','preview'].includes(c.operation)).length,0);
  assert.equal(p.errors.length,0);await shot(p,'01-manual-prior-dark-1440');await closePage(p);
 });
 await check('dirty source selector confirmation keeps/replaces draft, anchor and duplicate ancestry',async()=>{
  const p=await pageFor();await select(p);await drag(p);const before=await snap(p);
  p.once('dialog',d=>d.dismiss());await p.getByRole('checkbox',{name:'Select Upper wing',exact:true}).click();await ready(p,'Selection unchanged');assert.deepEqual((await snap(p)).draft,before.draft);
  p.once('dialog',d=>d.accept());await p.getByRole('checkbox',{name:'Select Previous merge',exact:true}).check();await ready(p,'previews ready');assert.match(await p.locator('[data-slot=warnings]').textContent(),/Duplicate ancestor/);
  await p.locator('[data-field=anchor]').selectOption('map-b');assert.equal((await snap(p)).draft.anchor,'map-b');await closePage(p);
 });
 await check('late automatic response after manual hint is ignored; undo/redo/reset draft only',async()=>{
  const p=await pageFor();await select(p);await p.evaluate(()=>window.fixture.setDelay(350));await p.locator('[data-action=start]').click();await p.waitForFunction(()=>window.fixture.calls.some(c=>c.operation==='job-status'));await drag(p);const prior=(await snap(p)).draft.priors['map-b'];await ready(p,'Late job response ignored');assert.deepEqual((await snap(p)).draft.priors['map-b'],prior);assert.equal((await snap(p)).proposal,null);
  await p.locator('[data-action=undo]').click();await p.locator('[data-action=redo]').click();assert.equal((await snap(p)).proposal,null);await p.locator('[data-action=reset]').click();assert.equal((await snap(p)).draft.priors['map-b'].x,0);await closePage(p);
 });
 await check('cancel pending start, cancel polling, retry with explicit server progress',async()=>{
  const p=await pageFor();await select(p);await p.evaluate(()=>window.fixture.setDelay(180));await p.locator('[data-action=start]').click();await p.locator('[data-action=cancel]').click();await ready(p,'CANCELLED');await p.waitForFunction(()=>window.fixture.calls.some(c=>c.operation==='cancel'));
  await p.evaluate(()=>window.fixture.setDelay(20));await solve(p);assert.equal((await snap(p)).status,'SOLVED_CANDIDATE');await closePage(p);
 });
 await check('failure reason then retry recovers; no false success from low RMSE',async()=>{
  const p=await pageFor('job-failure');await select(p);await p.locator('[data-action=start]').click();await ready(p,'FAILED');assert.match(await status(p).textContent(),/insufficient overlap/);await solve(p);assert.equal(await p.locator('[data-action=accept]').isDisabled(),true);await closePage(p);
 });
 await check('3-map disconnected components block candidate accept',async()=>{
  const p=await pageFor('disconnected');await select(p,true);await solve(p);await p.locator('[data-field=ack]').check();assert.equal(await p.locator('[data-action=accept]').isDisabled(),true);assert.equal((await snap(p)).proposal.connected_components.length,2);await shot(p,'02-disconnected-three-maps');await closePage(p);
 });
 await check('ambiguous metrics/heatmap and before/after remain reviewable; manual/solved separate',async()=>{
  const p=await pageFor('ambiguous');await select(p);await solve(p);assert.match(await p.locator('[data-slot=warnings]').textContent(),/AMBIGUOUS/);assert.match(await p.locator('[data-slot=diagnostics]').textContent(),/Low RMSE alone/);
  assert.equal((await snap(p)).draft.priors['map-b'].x,0);assert.notEqual((await snap(p)).proposal.transforms['map-b'][3],0);
  await p.locator('[data-field=view]').selectOption('before');await shot(p,'03-before-ambiguous');await p.locator('[data-field=view]').selectOption('after');await shot(p,'04-after-ambiguous');await closePage(p);
 });
 await check('3D XYZ pairs validate non-collinear and additional spread points; pick exact sample',async()=>{
  const p=await pageFor();await select(p);await p.locator('summary').click();
  for(const xyz of ['0,0,0','2,0,0','0,2,1','2,2,-1']){await p.locator('[data-field=sourceXYZ]').fill(xyz);await p.locator('[data-field=anchorXYZ]').fill(xyz);await p.locator('[data-action=pair]').click();}
  assert.equal((await snap(p)).draft.correspondences.length,4);await solve(p);const job=(await calls(p)).find(c=>c.operation==='job');assert.equal(job.body.correspondences.length,4);assert.equal(job.body.correspondences[0].source_xyz.length,3);
  await p.locator('[data-action=clearPairs]').click();await p.locator('[data-field=tool]').selectOption('source');
  await p.locator('[data-canvas=xy]').scrollIntoViewIfNeeded();const point=await p.evaluate(async()=>{const {generatePoints}=await import('/experiments/expansion_20261029/c2_map_ui/generator.mjs');const {xyProjection}=await import('/robot_dashboard/static/features/multimap_fusion/contract.js');const arrays=[generatePoints(0),generatePoints(1)],bounds={min:[Infinity,Infinity],max:[-Infinity,-Infinity]};for(const a of arrays)for(let i=0;i<a.length;i+=3)for(let k=0;k<2;k++){bounds.min[k]=Math.min(bounds.min[k],a[i+k]);bounds.max[k]=Math.max(bounds.max[k],a[i+k]);}const c=document.querySelector('[data-canvas=xy]'),r=c.getBoundingClientRect(),q=xyProjection(bounds,r.width,r.height).project(arrays[1].slice(0,3));return{x:r.x+q[0],y:r.y+q[1]};});await p.mouse.click(point.x,point.y);await ready(p,'Selected actual sample XYZ');assert.match(await status(p).textContent(),/Selected actual sample XYZ/);await closePage(p);
 });
 await check('explicit accept then new server ID/revision/hash export, originals kept and catalogue refreshed',async()=>{
  const p=await pageFor();await select(p);await solve(p);await p.locator('[data-field=name]').fill('new_fused_map');assert.equal(await p.locator('[data-action=save]').isDisabled(),true);
  await p.locator('[data-field=ack]').check();await p.locator('[data-action=accept]').click();await ready(p,'ACCEPTED');await p.locator('[data-action=save]').click();await ready(p,'Saved and listed');
  const s=await snap(p);assert.equal(s.status,'SAVED');assert.equal(s.draft.sources.length,2);assert.equal(await p.getByRole('checkbox',{name:'Select West hall',exact:true}).isChecked(),true);assert.equal(await p.getByRole('checkbox',{name:'Select new_fused_map',exact:true}).count(),1);
  const all=await calls(p);assert.equal(all.filter(c=>c.operation==='review').length,1);assert.equal(all.filter(c=>c.operation==='export').length,1);assert.equal(all.find(c=>c.operation==='export').body.activate,false);assert.equal(JSON.stringify(all.find(c=>c.operation==='export').body).includes('points'),false);assert.equal(await p.evaluate(()=>window.reviews.length),1);
  await shot(p,'05-new-pcd-saved');await closePage(p);
 });
 await check('save failure preserves accepted proposal and allows retry',async()=>{
  const p=await pageFor('save-failure');await select(p);await solve(p);await p.locator('[data-field=ack]').check();await p.locator('[data-action=accept]').click();await ready(p,'ACCEPTED');await p.locator('[data-field=name]').fill('retry_copy');await p.locator('[data-action=save]').click();await ready(p,'export failure');assert.equal((await snap(p)).status,'ACCEPTED');await p.locator('[data-action=save]').click();await ready(p,'Saved and listed');await closePage(p);
 });
 for(const scenario of ['empty','unsupported','loading-failure','preview-failure'])await check(`${scenario} state and recovery`,async()=>{
  const p=await pageFor(scenario);
  if(scenario==='empty'){assert.match(await p.locator('[data-slot=empty]').textContent(),/Empty/);assert.equal(await p.locator('[data-action=start]').isDisabled(),true);}
  else if(scenario==='preview-failure'){await p.getByRole('checkbox',{name:'Select West hall',exact:true}).check();await ready(p,'preview failure');await p.locator('[data-action=reload]').click();await ready(p,'previews ready');}
  else{assert.match(await status(p).textContent(),scenario==='unsupported'?/Unsupported/:/catalogue failure/);await p.evaluate(()=>window.fixture.setScenario('normal'));await p.locator('[data-action=reload]').click();await ready(p,'Catalogue ready');assert.equal(await p.locator('[data-source]').count(),5);}
  await closePage(p);
 });
 await check('dark/light 390/1440, resize + HiDPI, bounded large preview, show/hide opacity',async()=>{
  const p=await pageFor('large',{viewport:{width:390,height:844},deviceScaleFactor:2});await select(p);assert.ok(await p.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
  const size=await p.locator('[data-canvas=xy]').evaluate(c=>({w:c.width,css:c.getBoundingClientRect().width}));assert.ok(Math.abs(size.w-size.css*2)<2);
  await p.locator('#theme').click();await shot(p,'06-mobile-light-hidpi');await p.getByRole('checkbox',{name:'Show East hall',exact:true}).uncheck();await p.locator('[data-opacity="map-a"]').fill('0.3');await p.locator('[data-opacity="map-a"]').dispatchEvent('change');
  await p.setViewportSize({width:1440,height:1080});await p.waitForFunction(()=>document.querySelector('[data-canvas=xy]').width>1000);assert.ok(await p.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));await shot(p,'07-desktop-light-resize');assert.equal(p.errors.length,0);await closePage(p);
 });
 if(process.env.C2_C1_FIXTURE)await check('exact C1 external contract fixture in identical host; no solver/service claim',async()=>{
  const p=await pageFor('c1-exact');await p.getByRole('checkbox',{name:'Select C1 exact contract source 1',exact:true}).check();await ready(p,'previews ready');await p.getByRole('checkbox',{name:'Select C1 exact contract source 2',exact:true}).check();await ready(p,'previews ready');await solve(p);assert.match(await p.locator('[data-slot=warnings]').textContent(),/EXTERNAL C1 CONTRACT FIXTURE ONLY/);assert.equal(await p.locator('[data-action=accept]').isDisabled(),true);await shot(p,'08-c1-exact-contract-fixture');await closePage(p);
 });
 if(process.env.C2_C1_SERVICE_URL)await check('exact C1 HTTP + actual D1 synthetic solve/review/export/reload in identical host',async()=>{
  const p=await pageFor('c1-service');await p.getByRole('checkbox',{name:'Select Exact D1 synthetic map 1',exact:true}).check();await ready(p,'previews ready');await p.getByRole('checkbox',{name:'Select Exact D1 synthetic map 2',exact:true}).check();await ready(p,'previews ready');
  for(const [key,value]of Object.entries({x:.35,y:-.2,z:.15,roll:.06,pitch:-.04,yaw:.18})){await p.locator(`[data-pose="${key}"]`).fill(String(value));await p.locator(`[data-pose="${key}"]`).press('Tab');}
  await solve(p);const solved=await snap(p);assert.equal(solved.proposal.connected_components.length,1);assert.ok(solved.proposal.warnings.some(w=>w.includes('d1-rigid')));assert.ok(solved.proposal.accepted_edges.length>0);await shot(p,'09-exact-c1-d1-synthetic-solved');
  await p.locator('[data-field=ack]').check();await p.locator('[data-action=accept]').click();await ready(p,'ACCEPTED');assert.equal((await snap(p)).accepted.proposal_revision,2);await p.locator('[data-field=name]').fill(`exact_synthetic_${Date.now()}`);await p.locator('[data-action=save]').click();await ready(p,'catalogue has not returned it yet');assert.match(await p.locator('[data-slot=saved]').textContent(),/새 identity 확인/);assert.equal((await snap(p)).draft.sources.length,2);assert.equal(await p.getByRole('checkbox',{name:'Select Exact D1 synthetic map 1',exact:true}).isChecked(),true);exactEvidence={classification:'SYNTHETIC: actual D1 solver and C1 HTTP, DEVICE_NOT_RUN',c1_sha:'54629c793ad4ae0ea88127f00ed1b7f8805fc4e2',d1_sha:'cbedd05ba6f97dad5506e8003302f689ed8fcb4c',sources:solved.draft.sources.map(s=>({id:s.id,revision:s.revision,sha256:s.sha256,point_count:s.point_count})),components:solved.proposal.connected_components.length,accepted_edges:solved.proposal.accepted_edges.length,metrics:solved.proposal.metrics,reviewed_revision:(await snap(p)).accepted.proposal_revision,export_confirmation:await p.locator('[data-slot=saved]').textContent(),catalogue_status:await status(p).textContent()};await shot(p,'10-exact-c1-d1-new-export');await closePage(p);
 });
 await check('all fixture APIs and browser traffic stay within explicit review surface, device mutations zero',async()=>{
  assert.ok(httpAudit.filter(c=>c.method==='POST').every(c=>/^\/api\/v1\/extensions\/multimap\/jobs(?:\/[a-f0-9]{24}\/(review|exports|cancel))?$/.test(c.path)));assert.deepEqual(violations,[]);assert.deepEqual(pageErrors,[]);assert.ok(apiAudit.every(c=>['sources','preview','job','job-status','cancel','review','export'].includes(c.operation)));
  assert.equal(apiAudit.filter(c=>/nav|initialpose|goal|cmd|control/.test(c.operation)).length,0);
  for(const context of contexts)for(const p of context.pages())assert.deepEqual(p.errors,[]);
  // Each test audits port calls where relevant; no robot client exists in this test host.
  assert.deepEqual(violations.filter(v=>/nav|initialpose|goal|cmd|control/.test(v.url)),[]);
 });
}finally{
 await browser.close();await new Promise(resolve=>server.close(resolve));
 const report={classification:'UI_FIXTURE / SYNTHETIC',module:'UI_MODULE_TESTED',product:'PRODUCT_WIRING_DEFERRED',device:'DEVICE_NOT_RUN',results,screenshots,exact_dependency_evidence:exactEvidence,exact_dependency_http_operations:httpAudit,forbidden_network_mutations:violations.length,forbidden_api_mutations:apiAudit.filter(c=>/nav|initialpose|goal|cmd|control/.test(c.operation)).length,api_operation_counts:Object.fromEntries([...new Set(apiAudit.map(c=>c.operation))].map(op=>[op,apiAudit.filter(c=>c.operation===op).length]))};
 await writeFile(process.env.C2_REPORT_PATH||fileURLToPath(new URL('../../experiments/expansion_20261029/c2_map_ui/browser-results.json',import.meta.url)),JSON.stringify(report,null,2)+'\n');
}
if(results.some(r=>r.result==='FAIL'))process.exitCode=1;
