// Optional DOM/API integration smoke. Not a browser rendering or camera test.
// Install jsdom in a temporary prefix, set NODE_PATH to its node_modules.
const {JSDOM}=require('jsdom');
const fs=require('node:fs'); const path=require('node:path'); const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const root=path.resolve(__dirname,'..'); const port=18765; const origin=`http://127.0.0.1:${port}`;
const server=spawn(process.env.PYTHON||'python3',['-m','uvicorn','app:app','--host','127.0.0.1','--port',String(port)],{cwd:root,stdio:['ignore','pipe','pipe']});
let logs='';server.stderr.on('data',b=>logs+=b); let dom;
async function waitFor(f){for(let i=0;i<200;i++){if(await f())return;await new Promise(r=>setTimeout(r,50));}throw Error('Timed out '+logs)}
(async()=>{
 await waitFor(async()=>{try{return(await fetch(origin+'/api/health')).ok}catch{return false}});
 const html=await(await fetch(origin+'/')).text();
 assert.equal((await fetch(origin+'/static/app.js')).status,200);
 dom=new JSDOM(html,{url:origin,runScripts:'outside-only'});const w=dom.window,d=w.document;
 w.HTMLCanvasElement.prototype.getContext=function(){return{createImageData:(x,y)=>({data:new Uint8ClampedArray(x*y*4)}),putImageData(){},drawImage(){},beginPath(){},arc(){},fill(){},stroke(){},fillRect(){},fillText(){},measureText:t=>({width:t.length*6})}};
 w.AbortController=AbortController;w.Blob=Blob;let downloaded=null,captured=null,latest=null;
 w.URL.createObjectURL=b=>{downloaded=b;return'blob:test'};w.URL.revokeObjectURL=()=>{};
 w.HTMLAnchorElement.prototype.click=function(){};
 w.fetch=async(u,o)=>{if(String(u).endsWith('/estimate'))captured=JSON.parse(o.body);let r=await fetch(new URL(u,origin),o);if(String(u).endsWith('/estimate')&&r.ok)latest=await r.clone().json();return r};
 w.eval(fs.readFileSync(path.join(root,'static/app.js'),'utf8'));
 const el=id=>d.getElementById(id);
 assert.equal(d.querySelectorAll('.sample-card').length,3);assert(el('estimate-button').disabled);assert(el('export-button').disabled);
 for(const id of ['stationary-check','wall-check','pitch-check']){el(id).checked=true;el(id).dispatchEvent(new w.Event('change'))}
 assert(!el('estimate-button').disabled);el('estimate-button').click();
 await waitFor(()=>!el('results-content').hidden);
 assert.equal(latest.status,'RELATIVE_ONLY');assert.equal(latest.body_extrinsic_validated,false);assert(latest.synthetic);
 assert.equal(d.querySelectorAll('#results-body tr').length,3);
 assert(Math.abs(latest.samples[1].relative_pitch_deg-10)<.15);assert(Math.abs(latest.samples[2].relative_pitch_deg+8)<.15);
 d.querySelectorAll('.sample-select')[1].click();assert(!el('results-content').hidden);assert(Math.abs(Number(el('camera-rotation').getAttribute('transform').match(/rotate\(([-.0-9e+]+)/)[1])-10)<.15);
 el('export-button').click();await waitFor(()=>downloaded!==null);const exported=JSON.parse(await downloaded.text());assert.equal(exported.analysis.status,'RELATIVE_ONLY');assert.equal(exported.input.samples.length,3);
 el('point-u').value='70';el('point-v').value='80';el('point-form').dispatchEvent(new w.Event('submit',{cancelable:true}));assert(el('results-content').hidden);assert(el('export-button').disabled);
 // Inputs cannot submit when an assertion is removed.
 el('stationary-check').checked=false;el('stationary-check').dispatchEvent(new w.Event('change'));assert(el('estimate-button').disabled);
 assert.equal(new Set(captured.samples.map(s=>s.metadata.frame_id)).size,1);
 console.log(JSON.stringify({status:'PASS',checks:['HTTP health/static','unchecked conditions','synthetic UI→HTTP estimate','0/+10/-8 pitch','view sample preserves results','downward schematic sign','export recomputation','point edit invalidates','assertion removal blocks'],relative_pitch_deg:latest.samples.map(s=>s.relative_pitch_deg),visual_rendering:'NOT_TESTED_CANVAS_STUB',hardware:'NOT_TESTED'}));
})().catch(e=>{console.error(e);process.exitCode=1}).finally(()=>{if(dom)dom.window.close();server.kill('SIGTERM')});
