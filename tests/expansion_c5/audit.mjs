import { chromium } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { installDashboardBackend } from '../e2e/dashboard_backend.mjs';
import { root, urls, startHosts } from './hosts.mjs';
const out = `${root}/docs/parallel-expansion-20261030/C5/evidence`;
await mkdir(out, { recursive: true });
const stop = await startHosts();
const browser = await chromium.launch({ headless: true });
const report = [];
try {
  for (const surface of ['main', 'c2', 'c3']) {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    const errors = []; page.on('pageerror', e => errors.push(String(e)));
    if (surface === 'main') {
      const backend = await installDashboardBackend(page);
      const map = {map_id:backend.mapId,revision:backend.mapRevision,frame_id:'map',width:64,height:48,resolution:.05,origin:[.2,-.4,.7],data_b64:Buffer.alloc(64*48).toString('base64')};
      backend.on(`/api/v1/saved-maps/${backend.mapId}/data`,({json})=>json(map));
      Object.assign(backend.state.navigation,{pipeline:{state:'running'},map:{id:backend.mapId,revision:backend.mapRevision},localization:{state:'localized'},safety:{can_set_initial_pose:true,can_send_goal:true,blockers:[]}});
    }
    await page.goto(urls[surface] + (surface === 'main' ? '/#navigation' : ''));
    await page.waitForTimeout(1200);
    if (surface === 'main') {
      await page.locator('#navigationGoalPoseTool').click();
      const canvas=page.locator('#navigationMapCanvas');await canvas.scrollIntoViewIfNeeded();
      const b=await canvas.boundingBox();await page.mouse.move(b.x+b.width*.5,b.y+b.height*.5);await page.mouse.down();await page.mouse.move(b.x+b.width*.6,b.y+b.height*.4);await page.mouse.up();
      await page.locator('.navigation-map-panel').screenshot({path:`${out}/audit-main-panel-before.png`});
      report.push({surface:'main-readout',metrics:await page.locator('#navigationPoseCoordinates').evaluate(e=>({text:e.textContent,width:e.clientWidth,scroll:e.scrollWidth,whiteSpace:getComputedStyle(e).whiteSpace}))});
    }
    if (surface === 'c3') { await page.evaluate(() => window.c3Fixture.emit('multi')); await page.locator('[data-action=pause]').click(); }
    if (surface === 'c2') {
      await page.getByRole('checkbox', {name:'Select West hall',exact:true}).check();
      await page.waitForTimeout(200);
      await page.getByRole('checkbox', {name:'Select East hall',exact:true}).check();
      await page.waitForTimeout(200);
    }
    report.push({surface, errors, metrics:await page.evaluate(() => ({
      width:innerWidth, scrollWidth:document.documentElement.scrollWidth,
      text:document.body.innerText,
      overflow:[...document.querySelectorAll('body *')].filter(e=>{const r=e.getBoundingClientRect(); return r.width>0 && (r.right>innerWidth+1 || r.left< -1);}).slice(0,30).map(e=>({tag:e.tagName,id:e.id,class:e.className,text:e.textContent.slice(0,120),width:e.getBoundingClientRect().width})),
      small:[...document.querySelectorAll('button,label,[role=status],.os-risk,.mmf-note')].filter(e=>e.getBoundingClientRect().width).map(e=>({id:e.id,text:e.textContent.slice(0,100),font:getComputedStyle(e).fontSize,height:e.getBoundingClientRect().height})),
    }))});
    await page.screenshot({path:`${out}/audit-${surface}-390-before.png`,fullPage:true});
    await page.close();
  }
} finally { await browser.close(); stop(); }
await writeFile(`${out}/audit-before.json`,JSON.stringify(report,null,2)+'\n');
console.log(report.map(r=>({surface:r.surface,metrics:r.surface==='main-readout'?r.metrics:{width:r.metrics.scrollWidth},errors:r.errors})))
