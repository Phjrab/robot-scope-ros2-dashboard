// Observational reproduction of the protected URDF test. No shared file edits.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {writeFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
const root=process.env.C2_PROBE_ROOT;
const {chromium}=await import(process.env.C2_PLAYWRIGHT_MODULE||'playwright');
const {installDashboardBackend}=await import(pathToFileURL(root+'/tests/e2e/dashboard_backend.mjs'));
const server=spawn(process.execPath,['tests/e2e/static_server.mjs'],{cwd:root,stdio:'ignore'});
const origin='http://127.0.0.1:4173',report={node:process.version,root,console:[],network:[],page_errors:[],result:'FAIL'},pending=[];
let browser;
try{
 for(let i=0;i<100;i++){try{if((await fetch(origin)).ok)break;}catch{}await new Promise(r=>setTimeout(r,50));}
 browser=await chromium.launch({headless:true,args:['--no-sandbox']});report.browser=browser.version();
 const page=await browser.newPage({viewport:{width:1280,height:720}});
 page.on('console',m=>{if(['warning','error'].includes(m.type()))report.console.push({type:m.type(),text:m.text()});});page.on('pageerror',e=>report.page_errors.push(e.message));
 page.on('response',r=>{if(/go2|model|urdf|multimap_fusion/.test(r.url()))pending.push((async()=>{const body=await r.body().catch(()=>Buffer.alloc(0));report.network.push({url:new URL(r.url()).pathname,status:r.status(),bytes:body.length,sha256:createHash('sha256').update(body).digest('hex'),timing:r.request().timing()});})());});
 await page.addInitScript(()=>{
  window.c2ProbeScenes=[];let ctor;
  Object.defineProperty(window,'RobotScene3D',{configurable:true,get:()=>ctor,set:value=>{ctor=new Proxy(value,{construct(target,args,newTarget){const scene=Reflect.construct(target,args,newTarget);window.c2ProbeScenes.push(scene);return scene;}});}});
 });
 const backend=await installDashboardBackend(page);
 Object.assign(backend.state.navigation,{pipeline:{state:'running',job_id:'2'.repeat(32)},map:{id:backend.mapId,revision:backend.mapRevision}});
 backend.state.navigation.safety.can_set_initial_pose=true;
 await page.goto(origin+'/#navigation');
 await page.waitForFunction(()=>!document.querySelector('#navigationInitialPoseTool').disabled);
 report.before_drag=await page.evaluate(()=>({time:performance.now(),scenes:window.c2ProbeScenes.map(s=>({canvas:s.canvas?.id,status:s.getOfficialRobotModelStatus?.()}))}));
 await page.evaluate(()=>{window.mapModelDraws=[];window.c2DrawCalls=[];const draw=window.RobotScene3D.prototype.drawRobotMapPreview;window.RobotScene3D.prototype.drawRobotMapPreview=function(ctx,pose,project,...rest){const result=draw.call(this,ctx,pose,project,...rest);const observation={time:performance.now(),scene:this.canvas?.id,pose:{...pose},result,model:this.getOfficialRobotModelStatus()};window.c2DrawCalls.push(observation);if(result)window.mapModelDraws.push(observation);return result;};});
 await page.locator('#navigationInitialPoseTool').click();const canvas=page.locator('#navigationMapCanvas');await canvas.scrollIntoViewIfNeeded();const box=await canvas.boundingBox();
 await page.mouse.move(box.x+box.width*.5,box.y+box.height*.5);await page.mouse.down();await page.mouse.move(box.x+box.width*.58,box.y+box.height*.43,{steps:5});await page.mouse.up();
 // Same default 5s expectation budget as the protected config at both pinned SHAs.
 await page.waitForFunction(()=>window.mapModelDraws.length>0,null,{timeout:5000});
 report.draws=await page.evaluate(()=>window.c2DrawCalls);
 assert.ok(report.draws.some(d=>d.result&&d.pose.mode==='initial'&&d.pose.yaw>0&&d.model.model));
 assert.match(await page.locator('#navigationPoseCoordinates').textContent(),/URDF/);
 report.pose_mutations=backend.state.requests.filter(r=>r.path.includes('/navigation/initial-pose')||r.path.includes('/navigation/goal'));
 assert.deepEqual(report.pose_mutations,[]);report.result='PASS';
}catch(error){report.error=error.stack;throw error;}
finally{
 await Promise.all(pending);await browser?.close();server.kill('SIGTERM');await new Promise(r=>server.once('exit',r));
 await writeFile(process.env.C2_PROBE_REPORT,JSON.stringify(report,null,2)+'\n');
}
console.log(JSON.stringify({result:report.result,asset_responses:report.network.length,draws:report.draws.length,model:report.draws.at(-1).model}));
