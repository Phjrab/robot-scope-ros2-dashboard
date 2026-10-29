import fs from 'node:fs';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
const input=JSON.parse(fs.readFileSync(0,'utf8'));
if(input.mode==='map'){
 const {createC1Ports}=await import(pathToFileURL(`${input.deps}/C2/robot_dashboard/static/features/multimap_fusion/c1_ports.js`));
 const {SCHEMA}=await import(pathToFileURL(`${input.deps}/C2/robot_dashboard/static/features/multimap_fusion/contract.js`));
 const request=async(path,{method,body})=>{
  const res=await fetch(input.url+path,{method,headers:{Authorization:'Bearer public-c1-composition-test-only',Origin:input.url,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});
  const value=await res.json();assert(res.ok,JSON.stringify(value));return value;
 };
 const ports=createC1Ports(request);
 const {sources}=await ports.catalogue.list();
 const ui={schema:SCHEMA,draft_revision:1,sources,anchor:sources[0].id,initial_guesses:Object.fromEntries(sources.map((s,i)=>[s.id,input.poses[i]])),correspondences:[]};
 let job=await ports.jobs.start(ui);
 for(let n=0;job.state==='RUNNING'&&n<500;n++){
  await new Promise(r=>setTimeout(r,20));job=await ports.jobs.get(job.job_id);
 }
 assert.equal(job.state,'SOLVED_CANDIDATE',JSON.stringify(job));
 const reviewed=await ports.jobs.accept(job);
 const saved=await ports.jobs.save({...reviewed,name:'actual_d1_c2_round2'});
 const listing=await request('/api/v1/extensions/multimap/exports',{method:'GET'});
 assert.equal(listing.exports[0].id,saved.map.id);
 assert.equal(saved.runtime_installed,false);
 process.stdout.write(JSON.stringify({job_id:job.job_id,proposal_revision:reviewed.proposal_revision,export_id:saved.map.id,state:job.state,c2:'ACTUAL_PORTS_HTTP_PASS'}));
}else if(input.mode==='scene'){
 const {adaptC1ScenePacket}=await import(pathToFileURL(`${input.deps}/C3/robot_dashboard/static/features/obstacle_scene/c1_adapter.js`));
 process.stdout.write(JSON.stringify(input.packets.map(wire=>adaptC1ScenePacket(wire,{...wire.map_binding,source_epoch:'synthetic-1',frame_id:'odom',units:'m'}))));
}else throw new Error('unknown consumer mode');
