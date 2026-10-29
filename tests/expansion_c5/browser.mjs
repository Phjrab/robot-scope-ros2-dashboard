import { chromium, webkit, expect } from '@playwright/test';
import assert from 'node:assert/strict';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { installDashboardBackend } from '../e2e/dashboard_backend.mjs';
import { root, urls, startHosts } from './hosts.mjs';
const out = `${root}/docs/parallel-expansion-20261030/C5/evidence`;
await mkdir(out,{recursive:true});
const css = `${root}/robot_dashboard/static/features/operator_usability/operator_usability.css`;
const helper = await readFile(`${root}/robot_dashboard/static/features/operator_usability/index.js`,'utf8');
const report={classification:'UI_FIXTURE / local static hosts and mock backend; no robot or solver execution',matrix:[],checks:[],findings:[],errors:[]};
const stop=await startHosts();
let browser;
const roots={main:'[data-page="navigation"]',c2:'.mmf',c3:'.obstacle-scene'};
const surfaces={main:'navigation',c2:'multimap',c3:'obstacles'};
async function enhance(page,surface){
  await page.addStyleTag({path:css});
  await page.addScriptTag({type:'module',content:helper+`\nwindow.ouMount=mountOperatorUsability;window.ouHandle=mountOperatorUsability(document.querySelector('${roots[surface]}'),'${surfaces[surface]}');`});
  await page.waitForFunction(()=>!!window.ouHandle);
}
async function setup(surface,width=390,theme='dark',options={}){
  const context=await browser.newContext({viewport:{width,height:1000},deviceScaleFactor:options.dpr||1,hasTouch:options.touch||false});
  const page=await context.newPage();const requests=[],errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  await context.route('**/*',route=>{
    const req=route.request();requests.push({method:req.method(),url:req.url()});
    if(new URL(req.url()).origin!==new URL(urls[surface]).origin)return route.abort();
    return route.continue();
  });
  let backend;
  if(surface==='main'){
    backend=await installDashboardBackend(page);
    const map={map_id:backend.mapId,revision:backend.mapRevision,frame_id:'map',width:64,height:48,resolution:.05,origin:[.2,-.4,.7],data_b64:Buffer.alloc(64*48).toString('base64')};
    backend.on(`/api/v1/saved-maps/${backend.mapId}/data`,({json})=>json(map));
    Object.assign(backend.state.navigation,{pipeline:{state:'running',job_id:'2'.repeat(32)},map:{id:backend.mapId,revision:backend.mapRevision},localization:{state:'localized',pose:{x:2.8,y:.3,yaw:.1}},safety:{can_set_initial_pose:true,can_send_goal:true,blockers:[]}});
    await page.addInitScript(()=>{
      window.navDraws=[];
      window.addEventListener('load',()=>{
        const original=window.RobotScene3D.prototype.drawRobotMapPreview;
        window.RobotScene3D.prototype.drawRobotMapPreview=function(ctx,pose,...rest){const ok=original.call(this,ctx,pose,...rest);if(ok){window.navDraws.push({pose:{...pose},color:rest.at(-1),status:this.getOfficialRobotModelStatus()});window.navDraws=window.navDraws.slice(-80);}return ok;};
      });
    });
  }
  await page.goto(urls[surface]+(surface==='main'?'/#navigation':options.query||''));
  await page.evaluate(t=>{document.documentElement.dataset.theme=t;document.body.dataset.theme=t;},theme);
  if(surface==='main')await expect(page.locator('#navigationGoalPoseTool')).toBeEnabled();
  if(surface==='c2')await page.waitForFunction(()=>!!window.module);
  if(surface==='c3')await page.waitForFunction(()=>window.c3Fixture?.feature.snapshot()?.ready);
  await page.evaluate(()=>document.fonts.ready);
  return {page,context,backend,requests,errors};
}
async function selectMaps(page){
  for(const name of ['West hall','East hall']){await page.getByRole('checkbox',{name:`Select ${name}`,exact:true}).check();await expect(page.locator('[data-slot=status]')).toContainText('previews ready');}
}
async function drag(page,mode='goal'){
  await page.locator(mode==='goal'?'#navigationGoalPoseTool':'#navigationInitialPoseTool').click();
  const canvas=page.locator('#navigationMapCanvas');await canvas.scrollIntoViewIfNeeded();const b=await canvas.boundingBox();
  await page.mouse.move(b.x+b.width*.5,b.y+b.height*.5);await page.mouse.down();await page.mouse.move(b.x+b.width*.6,b.y+b.height*.4,{steps:5});await page.mouse.up();
  await expect.poll(()=>page.evaluate(m=>window.navDraws.filter(x=>x.pose.mode===m).length,mode)).toBeGreaterThan(0);
  return page.evaluate(m=>window.navDraws.filter(x=>x.pose.mode===m).at(-1).pose,mode);
}
async function emit(page,name){const seq=await page.evaluate(n=>window.c3Fixture.emit(n).sequence,name);await page.waitForFunction(s=>window.c3Fixture.feature.snapshot().sequence===s,seq);}
async function dimensions(page,surface){return page.locator(roots[surface]).evaluate((root,surface)=>{
  const selectors=surface==='main'?['#navigationPoseCoordinates','#navigationPoseSend','#navigationStopButton','#navigationCancelGoal']:surface==='c2'?['[data-action=start]','.mmf-note','[data-slot=status]','th','td']:['.os-layers label','.os-toolbar button','.os-summary','.os-risk'];
  return {viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,items:selectors.flatMap(s=>[...root.querySelectorAll(s)].map(e=>{const r=e.getBoundingClientRect(),c=getComputedStyle(e);return {selector:s,text:e.textContent,font:c.fontSize,width:r.width,height:r.height,client:e.clientWidth,scroll:e.scrollWidth,whiteSpace:c.whiteSpace};}))};
},surface);}
async function contrast(page,surface){
 return page.evaluate(surface=>{
  const selectors=surface==='c2'?['.mmf th','.mmf td','.mmf-note']:surface==='c3'?['.os-summary','.os-risk','.os-layers label']:['.ou-navigation-guide'];
  const rgba=s=>s.match(/[\d.]+/g).map(Number);
  const blend=(a,b)=>a.slice(0,3).map((n,i)=>n*(a[3]??1)+b[i]*(1-(a[3]??1)));
  const luminance=a=>a.map(n=>n/255).map(n=>n<=.04045?n/12.92:((n+.055)/1.055)**2.4).reduce((s,n,i)=>s+n*[.2126,.7152,.0722][i],0);
  return selectors.flatMap(selector=>{const e=document.querySelector(selector);if(!e)return [];const ancestors=[];for(let n=e;n;n=n.parentElement)ancestors.unshift(n);let bg=[255,255,255];for(const n of ancestors)bg=blend(rgba(getComputedStyle(n).backgroundColor),bg);const fg=blend(rgba(getComputedStyle(e).color),bg);const [hi,lo]=[luminance(fg),luminance(bg)].sort((a,b)=>b-a);return [{selector,ratio:(hi+.05)/(lo+.05),foreground:fg,background:bg}];});
 },surface);
}
async function shot(page,surface,name){
  const target=surface==='main'?'.navigation-map-panel':surface==='c2'?'.mmf main':'.obstacle-scene';
  await page.locator(target).screenshot({path:`${out}/${name}.png`});
}
async function check(name,fn){try{const evidence=await fn();report.checks.push({name,result:'PASS',evidence});console.log(`PASS ${name}`);}catch(e){report.checks.push({name,result:'FAIL',error:String(e.stack)});console.error(`FAIL ${name}: ${e.message}`);}}
try{
for(const [engine,type] of Object.entries({chromium,webkit})){
  try{browser=await type.launch({headless:true});}catch(e){report.errors.push({engine,launch:String(e)});continue;}
  for(const width of [390,768,1440])for(const theme of ['dark','light'])for(const surface of ['main','c2','c3']){
    const entry={engine,width,theme,surface};let fixture;
    try{
      fixture=await setup(surface,width,theme);const {page,backend,errors}=fixture;
      if(surface==='main')await drag(page);
      if(surface==='c2'){await selectMaps(page);await page.locator('[data-action=start]').click();await expect(page.locator('[data-slot=status]')).toContainText('SOLVED_CANDIDATE');}
      if(surface==='c3'){await emit(page,'multi');await page.locator('[data-action=pause]').click();await expect(page.locator('.os-mode')).toContainText('PAUSED');}
      entry.before=await dimensions(page,surface);
      entry.contrastBefore=await contrast(page,surface);
      const capture=(width===390 || width===1440&&theme==='dark'&&engine==='chromium' || width===768&&theme==='light'&&engine==='webkit');
      const name=`${engine}-${surface}-${width}-${theme}`;
      if(capture)await shot(page,surface,`${name}-before`);
      const protectedState=await page.evaluate(s=>s==='main'?document.querySelector('#navigationPoseCoordinates').textContent:s==='c2'?window.module.snapshot():document.querySelector('.os-mode').textContent,surface);
      await enhance(page,surface);
      entry.after=await dimensions(page,surface);
      entry.contrastAfter=await contrast(page,surface);
      assert.ok(entry.contrastAfter.every(x=>x.ratio>=4.5),'scoped normal text contrast below 4.5');
      assert.ok(entry.after.documentWidth<=width,`${surface} page overflow`);
      const afterState=await page.evaluate(s=>s==='main'?document.querySelector('#navigationPoseCoordinates').textContent:s==='c2'?window.module.snapshot():document.querySelector('.os-mode').textContent,surface);
      assert.deepEqual(afterState,protectedState);
      if(surface==='main'){const coord=entry.after.items.find(i=>i.selector==='#navigationPoseCoordinates');assert.ok(coord.scroll<=coord.client+1);assert.equal(backend.state.requests.filter(r=>r.method!=='GET').length,0);}
      if(surface==='c2')assert.ok(entry.after.items.find(i=>i.selector==='[data-action=start]').height>=44);
      if(surface==='c3')assert.ok(entry.after.items.filter(i=>i.selector==='.os-layers label').every(i=>i.height>=44));
      assert.deepEqual(errors,[]);
      if(capture)await shot(page,surface,`${name}-after`);
      entry.result='PASS';
    }catch(e){entry.result='FAIL';entry.error=String(e.stack);console.error(entry.error);}
    finally{await fixture?.context.close();report.matrix.push(entry);}
  }
  await check(`${engine}: goal coordinates/yaw and explicit payload are identical before/after; cancel and resize`,async()=>{
    const results=[];
    for(const enhanced of [false,true]){
      const f=await setup('main',390,'light',{dpr:2});const {page,backend}=f;
      try{
        if(enhanced)await enhance(page,'main');
        const pose=await drag(page);
        const stateText=await page.locator('#navigationPoseCoordinates').textContent();
        assert.equal(backend.state.requests.filter(r=>r.method!=='GET').length,0);
        page.once('dialog',d=>d.dismiss());await page.locator('#navigationPoseSend').click();assert.equal(backend.mutations('/api/v1/navigation/goal').length,0);
        await page.setViewportSize({width:768,height:1000});await expect(page.locator('#navigationPoseCoordinates')).toHaveText(stateText);
        page.once('dialog',d=>d.accept());await page.locator('#navigationPoseSend').click();await expect.poll(()=>backend.mutations('/api/v1/navigation/goal').length).toBe(1);
        const payload=backend.mutations('/api/v1/navigation/goal')[0].body;
        assert.deepEqual(payload,{map_id:backend.mapId,map_revision:backend.mapRevision,pose:{x:pose.x,y:pose.y,yaw:pose.yaw},confirmed:true});
        results.push({pose,payload,model:await page.evaluate(()=>window.navDraws.at(-1).status.url)});
      }finally{await f.context.close();}
    }
    assert.deepEqual(results[0],results[1]);return results;
  });
  await check(`${engine}: alignment pending/rejected/complete and API disconnect/reconnect remain authoritative`,async()=>{
    const f=await setup('main');const {page,backend}=f;
    try{
      await enhance(page,'main');
      backend.state.navigation.safety.can_send_goal=false;
      backend.state.navigation.operational_localization={fresh:true,ready:false,state:'INITIAL_REFINEMENT_CONFIRMING',metrics:{initial_confirmations:2}};
      await expect(page.locator('#navigationLocalizationState')).toHaveText('ALIGNING');await expect(page.locator('#navigationGoalPoseTool')).toBeDisabled();
      backend.state.navigation.operational_localization.state='CORRECTION_JUMP_RESEED_REQUIRED';
      await expect(page.locator('#navigationLocalizationState')).toHaveText('BLOCKED');await expect(page.locator('#navigationGoalPoseTool')).toBeDisabled();
      await page.locator('.navigation-status-grid').screenshot({path:`${out}/${engine}-alignment-rejected.png`});
      backend.state.navigation.operational_localization=null;backend.state.navigation.safety.can_send_goal=true;
      await expect(page.locator('#navigationGoalPoseTool')).toBeEnabled();
      let offline=true;backend.on('/api/v1/navigation',({json})=>json(offline?{error:'C5 simulated connection lost'}:backend.state.navigation,offline?503:200));
      await expect(page.locator('#navigationSafetyMessage')).toContainText('상태 API');await expect(page.locator('#navigationGoalPoseTool')).toBeDisabled();
      offline=false;await expect(page.locator('#navigationGoalPoseTool')).toBeEnabled();
      assert.equal(backend.state.requests.filter(r=>r.method!=='GET').length,0);
      return {mutations:0};
    }finally{await f.context.close();}
  });
  await check(`${engine}: C2 selection/edit/compare/review/save and failed job; no operating-map apply`,async()=>{
    const f=await setup('c2',390,'light',{touch:true,dpr:2});const {page}=f;
    try{
      await enhance(page,'c2');await selectMaps(page);
      const canvas=page.locator('[data-canvas=xy]');await canvas.focus();await page.keyboard.press('ArrowRight');
      assert.equal(await page.evaluate(()=>window.module.snapshot().draft.priors['map-b'].x),.1);
      await page.locator('[data-action=start]').click();await expect(page.locator('[data-slot=status]')).toContainText('SOLVED_CANDIDATE');
      for(const value of ['before','after','both'])await page.locator('[data-field=view]').selectOption(value);
      await expect(page.locator('[data-action=accept]')).toBeDisabled();await page.locator('[data-field=ack]').check();await page.locator('[data-action=accept]').click();
      await expect(page.locator('[data-slot=status]')).toContainText('ACCEPTED');
      await page.locator('[data-field=name]').fill('긴한글지도이름_검토후새사본저장_운영지도적용아님');await page.locator('[data-field=name]').press('Tab');
      await page.locator('[data-action=save]').click();await expect(page.locator('[data-slot=status]')).toContainText('Use a new name');
      assert.equal(await page.evaluate(()=>window.fixture.calls.filter(c=>c.operation==='export').length),0);
      await expect(page.locator('.ou-name-guide')).toContainText('영문');
      await page.locator('[data-field=name]').fill('c5_reviewed_copy');await page.locator('[data-field=name]').press('Tab');
      await page.locator('[data-action=save]').click();await expect(page.locator('[data-slot=saved]')).toContainText('운영');
      const calls=await page.evaluate(()=>window.fixture.calls);assert.equal(calls.filter(c=>c.operation==='export').length,1);
      assert.ok(calls.every(c=>['sources','preview','job','job-status','review','export'].includes(c.operation)));
      await shot(page,'c2',`${engine}-c2-saved-after`);
      return {operations:calls.map(c=>c.operation),saved:await page.locator('[data-slot=saved]').textContent()};
    }finally{await f.context.close();}
  });
  await check(`${engine}: C2 loading/empty/error/retry/disconnected result retain original reasons`,async()=>{
    const states=[];
    for(const scenario of ['empty','loading-failure','job-failure','disconnected']){
      const f=await setup('c2',768,'dark',{query:`?scenario=${scenario}`});const {page}=f;
      try{
        await enhance(page,'c2');
        if(scenario==='loading-failure'){await expect(page.locator('[data-slot=status]')).toContainText('Synthetic catalogue failure');await page.locator('[data-action=reload]').click();await expect(page.locator('[data-source]')).toHaveCount(5);}
        else if(scenario==='empty')await expect(page.locator('[data-slot=empty]')).toContainText('Empty');
        else{await selectMaps(page);if(scenario==='disconnected'){await page.getByRole('checkbox',{name:'Select Upper wing',exact:true}).check();await expect(page.locator('[data-slot=status]')).toContainText('previews ready');}await page.locator('[data-action=start]').click();await expect(page.locator('[data-slot=status]')).toContainText(scenario==='job-failure'?'FAILED':'SOLVED_CANDIDATE');await page.locator('[data-field=ack]').check();await expect(page.locator('[data-action=accept]')).toBeDisabled();}
        states.push({scenario,status:await page.locator('[data-slot=status]').textContent()});
      }finally{await f.context.close();}
    }return states;
  });
  await check(`${engine}: C3 obstacles/costmap/path generations, risk keyboard inspector, stale and reconnect`,async()=>{
    const f=await setup('c3',390,'light',{dpr:2,touch:true});const {page}=f;
    try{
      await enhance(page,'c3');
      for(const scenario of ['empty','cone','costmap','path-1','replan','trajectory'])await emit(page,scenario);
      assert.ok(await page.evaluate(()=>window.c3Fixture.feature.snapshot().history.length>=2));
      await page.locator('.os-risk').focus();await page.keyboard.press('Enter');await expect(page.locator('.os-inspector')).toContainText('assessment');
      await page.locator('[data-layer=costmap]').tap();await expect(page.locator('[data-layer=costmap]')).not.toBeChecked();await page.locator('[data-layer=costmap]').tap();
      for(const scenario of ['bad-calibration','clock-mismatch','stale-pose','stale-joints']){await emit(page,scenario);assert.equal(await page.evaluate(()=>window.c3Fixture.feature.snapshot().collision.value),null);await expect(page.locator('.os-risk')).toContainText('UNKNOWN');}
      await emit(page,'multi');await expect.poll(()=>page.evaluate(()=>window.c3Fixture.feature.snapshot().pose.reason)).toBe('STALE');await expect(page.locator('.os-sources')).toContainText('STALE');
      await emit(page,'multi');await expect(page.locator('.os-sources')).toContainText('FRESH');
      const old=await page.evaluate(()=>{const f=window.c3Fixture,p=f.makePacket(1000,'multi',f.context);f.setContext({...f.context,map_id:'other-map',source_epoch:'epoch-next',stream_epoch:'stream-next'});return p;});
      await page.evaluate(p=>window.c3Fixture.emitPacket(p),old);await expect(page.locator('.os-risk')).toContainText('UNKNOWN');
      assert.ok(f.requests.every(r=>r.method==='GET'&&!new URL(r.url).pathname.startsWith('/api/')));assert.deepEqual(f.errors,[]);
      return {mutations:0,staleAndInvalidFrames:'UNKNOWN retained'};
    }finally{await f.context.close();}
  });
  await check(`${engine}: helper lifecycle, keyboard focus, 200% root text and long Korean/SHA`,async()=>{
    const f=await setup('main',390);const {page,backend}=f;
    try{
      await page.locator('#navigationInitialPoseTool').focus();await enhance(page,'main');await expect(page.locator('#navigationInitialPoseTool')).toBeFocused();
      await page.evaluate(()=>{const r=document.querySelector('[data-page=navigation]');window.ouMount(r,'navigation');});assert.equal(await page.locator('.ou-navigation-guide').count(),1);
      await drag(page);await page.addStyleTag({content:'html{font-size:32px}'});
      assert.equal(await page.locator('.ou-navigation-guide').evaluate(e=>getComputedStyle(e).fontSize),'28px');
      await expect(page.locator('#navigationPoseCoordinates')).toContainText('URDF');
      const raw='미검증_정합거절_원본유지_'.repeat(12)+'a'.repeat(64);
      backend.state.navigation.pipeline={state:'failed',error:raw};await expect(page.locator('#navigationSafetyMessage')).toHaveText(raw);
      await page.locator(roots.main).evaluate(e=>e.removeAttribute('data-operator-usability'));
      const beforeWidth=await page.evaluate(()=>document.documentElement.scrollWidth);
      await page.locator('#navigationSafetyBanner').screenshot({path:`${out}/${engine}-long-error-before.png`});
      await page.locator(roots.main).evaluate(e=>e.setAttribute('data-operator-usability','navigation'));
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
      await page.locator('#navigationSafetyBanner').screenshot({path:`${out}/${engine}-long-error-after.png`});
      await page.evaluate(()=>window.ouHandle.destroy());assert.equal(await page.locator('.ou-navigation-guide').count(),0);
      assert.equal(await page.locator('#navigationPoseSend').getAttribute('aria-describedby'),null);
      assert.equal(backend.state.requests.filter(r=>r.method!=='GET').length,0);
      return {dpr:1,rootTextPercent:200,beforeWidth,afterWidth:390,unmodifiedRawError:raw};
    }finally{await f.context.close();}
  });
  await check(`${engine}: C2/C3 text enlargement and scoped style removal`,async()=>{
    const evidence=[];
    for(const surface of ['c2','c3']){
      const f=await setup(surface,390,'light',{dpr:2,touch:true});
      try{
        const {page}=f;await enhance(page,surface);
        await page.addStyleTag({content:'html{font-size:32px}'});
        if(surface==='c2'){
          await selectMaps(page);await page.locator('[data-action=start]').click();await expect(page.locator('[data-slot=status]')).toContainText('SOLVED_CANDIDATE');
        }
        assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
        const selector=surface==='c2'?'[data-action=start]':'.os-layers label';
        const font=await page.locator(selector).first().evaluate(e=>getComputedStyle(e).fontSize);
        assert.ok(parseFloat(font)>=28);
        await shot(page,surface,`${engine}-${surface}-large-text-after`);
        await page.evaluate(()=>window.ouHandle.destroy());
        assert.equal(await page.locator('[data-operator-usability]').count(),0);
        evidence.push({surface,font,dpr:2,rootTextPercent:200});
      }finally{await f.context.close();}
    }return evidence;
  });
  if(engine==='chromium')await check('Chromium emulated touch drag preserves pose/payload and does not scroll the map',async()=>{
    const results=[];
    for(const enhanced of [false,true]){
      const f=await setup('main',390,'dark',{touch:true,dpr:2});const {page,backend}=f;
      try{
        if(enhanced)await enhance(page,'main');
        await page.locator('#navigationGoalPoseTool').tap();
        const canvas=page.locator('#navigationMapCanvas');await canvas.scrollIntoViewIfNeeded();const b=await canvas.boundingBox();
        const beforeScroll=await page.evaluate(()=>scrollY);const cdp=await f.context.newCDPSession(page);
        await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:b.x+b.width*.5,y:b.y+b.height*.5}]});
        await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:b.x+b.width*.6,y:b.y+b.height*.4}]});
        await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
        await expect(page.locator('#navigationPoseCoordinates')).toContainText('URDF');
        assert.equal(await page.evaluate(()=>scrollY),beforeScroll);
        const pose=await page.evaluate(()=>window.navDraws.filter(d=>d.pose.mode==='goal').at(-1).pose);
        assert.equal(backend.state.requests.filter(r=>r.method!=='GET').length,0);
        results.push({pose,automaticMutations:0});await cdp.detach();
      }finally{await f.context.close();}
    }assert.deepEqual(results[0],results[1]);return results;
  });
  await browser.close();browser=null;
}
}finally{await browser?.close();stop();await writeFile(`${out}/browser-results.json`,JSON.stringify(report,null,2)+'\n');}
console.log(JSON.stringify({matrix:report.matrix.reduce((s,x)=>(s[x.result]=(s[x.result]||0)+1,s),{}),checks:report.checks.map(x=>({name:x.name,result:x.result})),errors:report.errors},null,2));
if(report.errors.length||report.matrix.some(x=>x.result==='FAIL')||report.checks.some(x=>x.result==='FAIL'))process.exitCode=1;
