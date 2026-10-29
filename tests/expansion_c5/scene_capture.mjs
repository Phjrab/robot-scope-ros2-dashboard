// Full peer viewport capture supplements the detailed C3 panel matrix.
import { chromium, webkit, expect } from '@playwright/test';
import { readFile, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { root, urls, startHosts } from './hosts.mjs';
const out=`${root}/docs/parallel-expansion-20261030/C5/evidence`,stop=await startHosts(),report=[];
try{for(const [engine,type] of Object.entries({chromium,webkit})){
 const browser=await type.launch();
 try{for(const [width,theme] of [[1440,'dark'],[390,'light']]){
  const page=await browser.newPage({viewport:{width,height:1000},deviceScaleFactor:2});
  try{
   const requests=[];await page.route('**/*',r=>{requests.push({method:r.request().method(),url:r.request().url()});new URL(r.request().url()).origin===new URL(urls.c3).origin?r.continue():r.abort();});
   await page.goto(urls.c3);await page.waitForFunction(()=>window.c3Fixture?.feature.snapshot()?.ready);
   await page.evaluate(t=>document.body.dataset.theme=t,theme);await page.evaluate(()=>window.c3Fixture.emit('multi'));
   await page.locator('[data-action=pause]').click();await expect(page.locator('.os-mode')).toContainText('PAUSED');
   const model=await page.evaluate(()=>window.c3Fixture.renderer.getOfficialRobotModelStatus());assert.equal(model.state,'ready');
   const name=`${engine}-c3-full-${width}-${theme}`;
   await page.screenshot({path:`${out}/${name}-before.png`,fullPage:true});
   await page.addStyleTag({path:`${root}/robot_dashboard/static/features/operator_usability/operator_usability.css`});
   const helper=await readFile(`${root}/robot_dashboard/static/features/operator_usability/index.js`,'utf8');
   await page.addScriptTag({type:'module',content:helper+"\nmountOperatorUsability(document.querySelector('.obstacle-scene'),'obstacles');"});
   await page.screenshot({path:`${out}/${name}-after.png`,fullPage:true});
   assert.ok(requests.every(r=>r.method==='GET'&&!new URL(r.url).pathname.startsWith('/api/')));
   report.push({engine,width,theme,dpr:2,model,result:'PASS',name});
  }finally{await page.close();}
 }}finally{await browser.close();}
}}finally{stop();await writeFile(`${out}/scene-captures.json`,JSON.stringify(report,null,2)+'\n');}
