// Local synthetic UI acceptance. No operational server, ROS or robot connection.
import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
import {spawn, spawnSync} from 'node:child_process';
import {mkdtemp, mkdir, writeFile} from 'node:fs/promises';
import path from 'node:path';
const python = process.env.OFFLINE_SLAM_PYTHON || 'python3';
const workbench = process.argv.includes('--workbench');
const network = process.argv.includes('--network');
assert.ok(!network || workbench,'network smoke requires --workbench');
const testPassword='synthetic-browser-test-password-1234567890';
const authHeaders=network?{Authorization:'Basic '+Buffer.from('review:'+testPassword).toString('base64')}:{};
const root = path.resolve('runtime/offline-validation');
await mkdir(root,{recursive:true});
const run = await mkdtemp(path.join(root,'browser-'));
const fixture = path.join(run,'synthetic.json');
const passwordFile=path.join(run,'test-password.txt');
if(network)await writeFile(passwordFile,testPassword);
const generated=spawnSync(python,['-m','robot_dashboard.offline_slam.demo','--output',fixture],{encoding:'utf8',windowsHide:true});
assert.equal(generated.status,0,generated.stderr);
const server=spawn(python,['-m',`robot_dashboard.offline_slam.${workbench?'workbench':'server'}`,'--root',path.join(run,'store'),'--port','18091',...(workbench?['--synthetic-demo']:[]),...(network?['--allow-host','127.0.0.1:18091','--allow-network','192.168.50.0/24','--password-file',passwordFile]:[])],{stdio:'ignore',windowsHide:true});
let browser;
try {
  let ready=false;
  for(let i=0;i<100;i++) {
    if(server.exitCode !== null)throw new Error('offline server exited');
    try{if((await fetch(`http://127.0.0.1:18091/${workbench?'analysis/':''}api/sessions`,{headers:authHeaders})).ok){ready=true;break;}}catch{}
    await new Promise(resolve=>setTimeout(resolve,100));
  }
  assert.ok(ready,'server ready');
  if(network)assert.equal((await fetch('http://127.0.0.1:18091/analysis/api/sessions')).status,401);
  browser=await chromium.launch({headless:true});
  const shell=await browser.newPage({viewport:{width:1440,height:1100},...(network?{httpCredentials:{username:'review',password:testPassword}}:{})});
  const errors=[];shell.on('pageerror',error=>errors.push(error.message));
  await shell.goto('http://127.0.0.1:18091/');
  let page=shell;
  if(workbench){
    await shell.locator('.nav-item[href="/extensions"]').click();
    await shell.locator('#expansion-choices').waitFor();
    assert.equal(await shell.locator('#expansion-choices').isVisible(),true);
    assert.equal(await shell.locator('iframe').count(),0);
    await shell.locator('[data-open-feature="trajectory"]').click();
    await shell.locator('iframe[title="주행 기록 보정"]').waitFor();
    const frame=await shell.locator('iframe[title="주행 기록 보정"]').elementHandle();
    page=await frame.contentFrame();
  }
  assert.equal(await page.locator('#save').isEnabled(),false);
  await page.locator('#file').setInputFiles(fixture);
  await page.waitForFunction(()=>!document.querySelector('#run').disabled);
  await page.locator('#search_radius').fill('1.2');
  await page.locator('#min_separation').fill('10');
  await page.locator('#run').click();
  await page.waitForFunction(()=>!document.querySelector('#save').disabled,null,{timeout:60000});
  assert.match(await page.locator('#status').innerText(),/합성 시험 데이터/);
  assert.equal(await page.locator('#error').innerText(),'');
  await shell.screenshot({path:path.join(root,workbench?'integrated-comparison.png':'comparison.png'),fullPage:true});
  await page.locator('#save').click();
  await page.waitForFunction(()=>!document.querySelector('#download').hidden);
  assert.equal(await page.locator('#run').isEnabled(),false);
  const href=await page.locator('#download').getAttribute('href');
  const archive=await shell.request.get(new URL(href,page.url()).href);
  assert.equal(archive.status(),200);
  assert.ok((await archive.body()).length>10000);
  await page.goto(page.url());
  await page.waitForFunction(()=>document.querySelector('#sessions').options.length>1);
  await page.locator('#sessions').selectOption({index:1});
  await page.waitForFunction(()=>!document.querySelector('#download').hidden);
  await shell.setViewportSize({width:390,height:844});
  await shell.screenshot({path:path.join(root,workbench?'integrated-mobile.png':'mobile.png'),fullPage:true});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  if(workbench){
    await shell.setViewportSize({width:1440,height:1100});
    await shell.locator('[data-feature="multimap"]').click();
    await shell.locator('input[data-source]').first().waitFor();
    assert.equal(await shell.locator('input[data-source]').count(),2);
    await shell.locator('input[data-source]').nth(0).check();
    await shell.locator('input[data-source]').nth(1).check();
    await shell.locator('[data-action="start"]').click();
    await shell.waitForFunction(()=>document.querySelector('[data-slot="status"]')?.dataset.state==='SOLVED_CANDIDATE',null,{timeout:60000});
    await shell.locator('[data-field="ack"]').check();
    await shell.locator('[data-action="accept"]').click();
    await shell.locator('[data-field="name"]').fill('synthetic_browser_merge');
    await shell.locator('[data-action="save"]').click();
    await shell.waitForFunction(()=>document.querySelector('[data-slot="saved"]')?.textContent.includes('새 identity 확인'),null,{timeout:30000});
    const exports=await shell.request.get('http://127.0.0.1:18091/api/v1/extensions/multimap/exports');
    assert.equal((await exports.json()).exports.length,1);
    await shell.screenshot({path:path.join(root,'integrated-merge.png'),fullPage:true});
    await shell.locator('[data-feature="trajectory"]').click();
    await shell.frameLocator('iframe').locator('#sessions option').nth(1).waitFor({state:'attached'});
    await shell.locator('#expansion-home').click();
    await shell.locator('#appNavigation').waitFor();
    assert.equal(new URL(shell.url()).pathname,'/');
    await shell.locator('.nav-item[href="/extensions"]').click();
    await shell.locator('#expansion-choices').waitFor();
    assert.equal(await shell.locator('#expansion-choices').isVisible(),true);
    await shell.locator('[data-open-feature="multimap"]').click();
    await shell.locator('input[data-source]').first().waitFor();
    console.log('PASS: integrated modes → real merge → review → immutable export → return to saved trajectory');
  }
  assert.deepEqual(errors,[]);
  console.log('PASS: import → real optimization → compare → save → export → reload; desktop/mobile; synthetic only');
} finally {
  if(browser)await browser.close();
  server.kill();
}
