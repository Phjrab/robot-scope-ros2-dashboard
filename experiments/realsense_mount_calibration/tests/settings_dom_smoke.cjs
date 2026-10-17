// Optional native Settings DOM + real router HTTP check; canvas is stubbed, not visual QA.
const {JSDOM}=require('jsdom');const fs=require('node:fs');const path=require('node:path');const assert=require('node:assert/strict');const{spawn}=require('node:child_process');const{pathToFileURL}=require('node:url');
const repo=path.resolve(__dirname,'../../..');const origin='http://127.0.0.1:18766';
const code="from fastapi import FastAPI; from robot_dashboard.api.routers.mount_calibration import router; import uvicorn; a=FastAPI(); a.include_router(router); uvicorn.run(a,host='127.0.0.1',port=18766)";
const server=spawn(process.env.PYTHON||'python3',['-c',code],{cwd:repo,stdio:['ignore','pipe','pipe']});let logs='';server.stderr.on('data',b=>logs+=b);let dom,feature;
async function waitFor(fn){for(let n=0;n<200;n++){if(await fn())return;await new Promise(r=>setTimeout(r,50));}throw Error('Timed out '+logs)}
(async()=>{
 await waitFor(async()=>{try{return(await fetch(origin+'/api/v1/settings/mount-calibration/status')).ok}catch{return false}});
 dom=new JSDOM(fs.readFileSync(path.join(repo,'robot_dashboard/static/index.html'),'utf8'),{url:origin+'/#settings'});const w=dom.window,d=w.document;
 w.HTMLCanvasElement.prototype.getContext=function(){return{createImageData:(x,y)=>({data:new Uint8ClampedArray(x*y*4)}),putImageData(){},drawImage(){},clearRect(){},beginPath(){},arc(){},fill(){},stroke(){},fillRect(){},fillText(){},measureText:t=>({width:t.length*6})}};
 w.HTMLAnchorElement.prototype.click=function(){};
 const requests=[];let latest,downloaded;
 const oldCreate=URL.createObjectURL,oldRevoke=URL.revokeObjectURL;URL.createObjectURL=b=>{downloaded=b;return'blob:test'};URL.revokeObjectURL=()=>{};
 const request=async(u,opts={})=>{requests.push({u,method:opts.method||'GET'});const r=await fetch(origin+u,{...opts,headers:{'Content-Type':'application/json',Origin:origin}});const data=await r.json();if(!r.ok)throw Error(data.detail);if(u.endsWith('/estimate'))latest=data;return data};
 const {initializeMountCalibrationFeature:init}=await import(pathToFileURL(path.join(repo,'robot_dashboard/static/features/settings/mount_calibration.js')));
 feature=init({document:d,api:request});const e=id=>d.getElementById('mount-calibration-'+id);
 await waitFor(()=>requests.length>0);assert.equal(feature.snapshot().sampleCount,0);assert.equal(requests.filter(x=>x.method!=='GET').length,0);assert.equal(init({document:d,api:request}),feature);
 assert(d.querySelector('[data-page="settings"] #mount-calibration-panel'));assert.equal(d.querySelector('#mount-calibration-panel iframe'),null);
 e('demo-button').click();assert.equal(feature.snapshot().sampleCount,3);assert(e('estimate-button').disabled);
 for(const id of ['stationary-check','wall-check','pitch-check']){e(id).checked=true;e(id).dispatchEvent(new w.Event('change'))}
 e('estimate-button').click();await waitFor(()=>feature.snapshot().hasResult);assert.equal(latest.status,'RELATIVE_ONLY');assert(!latest.body_extrinsic_validated);assert(Math.abs(latest.samples[1].relative_pitch_deg-10)<.15);
 e('export-button').click();await waitFor(()=>!!downloaded);assert.equal(JSON.parse(await downloaded.text()).analysis.status,'RELATIVE_ONLY');
 e('undo-button').click();assert(!feature.snapshot().hasResult);assert(e('export-button').disabled);
 feature.destroy();assert(feature.snapshot().destroyed);e('demo-button').click();assert.equal(feature.snapshot().sampleCount,0);
 assert(requests.every(x=>x.u.startsWith('/api/v1/settings/mount-calibration/')));
 console.log(JSON.stringify({status:'PASS',checks:['native settings card','empty lazy startup/status GET only','idempotent init','explicit synthetic demo','actual same-origin router estimate','relative-only export','editing invalidates','destroy removes listeners','no hardware endpoints'],pitch_deg:latest.samples.map(x=>x.relative_pitch_deg),visual_rendering:'NOT_TESTED_CANVAS_STUB',hardware:'NOT_TESTED'}));
 URL.createObjectURL=oldCreate;URL.revokeObjectURL=oldRevoke;
})().catch(e=>{console.error(e);process.exitCode=1}).finally(()=>{if(feature&&!feature.snapshot().destroyed)feature.destroy();if(dom)dom.window.close();server.kill('SIGTERM')});
