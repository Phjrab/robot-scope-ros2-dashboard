// Local synthetic UI acceptance. No operational server, ROS or robot connection.
import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
import {spawn, spawnSync} from 'node:child_process';
import {mkdtemp, mkdir} from 'node:fs/promises';
import path from 'node:path';
const python = process.env.OFFLINE_SLAM_PYTHON || 'python3';
const root = path.resolve('runtime/offline-validation');
await mkdir(root,{recursive:true});
const run = await mkdtemp(path.join(root,'browser-'));
const fixture = path.join(run,'synthetic.json');
const generated=spawnSync(python,['-m','robot_dashboard.offline_slam.demo','--output',fixture],{encoding:'utf8',windowsHide:true});
assert.equal(generated.status,0,generated.stderr);
const server=spawn(python,['-m','robot_dashboard.offline_slam.server','--root',path.join(run,'store'),'--port','18091'],{stdio:'ignore',windowsHide:true});
let browser;
try {
  let ready=false;
  for(let i=0;i<100;i++) {
    if(server.exitCode !== null)throw new Error('offline server exited');
    try{if((await fetch('http://127.0.0.1:18091/api/sessions')).ok){ready=true;break;}}catch{}
    await new Promise(resolve=>setTimeout(resolve,100));
  }
  assert.ok(ready,'server ready');
  browser=await chromium.launch({headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1100}});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto('http://127.0.0.1:18091/');
  assert.equal(await page.locator('#save').isEnabled(),false);
  await page.locator('#file').setInputFiles(fixture);
  await page.waitForFunction(()=>!document.querySelector('#run').disabled);
  await page.locator('#search_radius').fill('1.2');
  await page.locator('#min_separation').fill('10');
  await page.locator('#run').click();
  await page.waitForFunction(()=>!document.querySelector('#save').disabled,null,{timeout:60000});
  assert.match(await page.locator('#status').innerText(),/합성 시험 데이터/);
  assert.equal(await page.locator('#error').innerText(),'');
  await page.screenshot({path:path.join(root,'comparison.png'),fullPage:true});
  await page.locator('#save').click();
  await page.waitForFunction(()=>!document.querySelector('#download').hidden);
  assert.equal(await page.locator('#run').isEnabled(),false);
  const href=await page.locator('#download').getAttribute('href');
  const archive=await page.request.get(new URL(href,page.url()).href);
  assert.equal(archive.status(),200);
  assert.ok((await archive.body()).length>10000);
  await page.reload();
  await page.waitForFunction(()=>document.querySelector('#sessions').options.length>1);
  await page.locator('#sessions').selectOption({index:1});
  await page.waitForFunction(()=>!document.querySelector('#download').hidden);
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:path.join(root,'mobile.png'),fullPage:true});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  assert.deepEqual(errors,[]);
  console.log('PASS: import → real optimization → compare → save → export → reload; desktop/mobile; synthetic only');
} finally {
  if(browser)await browser.close();
  server.kill();
}
