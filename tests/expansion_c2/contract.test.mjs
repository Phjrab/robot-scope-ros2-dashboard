import test from 'node:test';
import assert from 'node:assert/strict';
import {createSession} from '../../robot_dashboard/static/features/multimap_fusion/session.js';
import {SCHEMA,CONVENTION,sourceDescriptor,pin,identity,poseMatrix,rigidMatrix,transformPoint,boundedPreview,xyProjection,validateCorrespondences,selectionWarnings,createHttpPorts} from '../../robot_dashboard/static/features/multimap_fusion/contract.js';
import {createFixture} from '../../experiments/expansion_20261029/c2_map_ui/fixture.mjs';
const maps=()=>createFixture().maps.slice(0,3);
const selected=()=>{const s=createSession();s.select(maps().slice(0,2));return s;};
async function solved(s,fixture=createFixture()){const {token,request}=s.begin(),r=await fixture.jobs.start(request),p=await fixture.jobs.get(r.job_id);assert.equal(s.receive(token,p),true);return{token,request,p,fixture};}

test('source descriptors pin identity and reject missing units / session / hash',()=>{
  const s=maps()[0];assert.deepEqual(pin(sourceDescriptor(s)),pin(s));
  for(const change of [{units:'mm'},{session_id:''},{sha256:'x'},{point_count:-1},{kind:'occupancy2d'},{revision:null}])assert.throws(()=>sourceDescriptor({...s,...change}));
});
test('SE3 contract uses column vectors, radians and row-major translation; scale/reflection rejected',()=>{
  assert.equal(CONVENTION,'row-major,column-vector,p_fused=T_fused_source@p_source');
  const m=poseMatrix({x:2,y:-3,yaw:Math.PI/2});const p=transformPoint(m,[1,0,0]);assert.ok(Math.abs(p[0]-2)<1e-10);assert.ok(Math.abs(p[1]+2)<1e-10);
  rigidMatrix(m);for(const idx of [0,5,10,15]){const bad=identity();bad[idx]=2;assert.throws(()=>rigidMatrix(bad));}const bad=identity();bad[0]=-1;assert.throws(()=>rigidMatrix(bad));
  assert.throws(()=>poseMatrix({yaw:NaN}));
});
test('rotated non-square projection and CSS pixel inverse preserve meters without x/y scale distortion',()=>{
  const p=xyProjection({min:[-20,-2],max:[20,2]},350,680,.73),origin=p.project([0,0]);
  for(const world of [[2,3],[-5,7]]){const pixel=p.project(world),back=p.delta(pixel[0]-origin[0],pixel[1]-origin[1]);world.forEach((v,i)=>assert.ok(Math.abs(v-back[i])<1e-9));}
  const x=p.project([1,0]),y=p.project([0,1]);assert.ok(Math.abs(Math.hypot(x[0]-origin[0],x[1]-origin[1])-Math.hypot(y[0]-origin[0],y[1]-origin[1]))<1e-10);
});
test('preview LOD bounds buffers and refuses stale pinned identity and unsupported schema',()=>{
  const s=maps()[0],payload={schema:SCHEMA,input_pin:pin(s),units:'m',points:Array.from({length:90000},(_,i)=>i/100)};
  assert.ok(boundedPreview(payload,s).points.length<=6000);assert.equal(boundedPreview(payload,s).sampled,true);
  assert.throws(()=>boundedPreview({...payload,input_pin:{...pin(s),revision:'stale'}},s));assert.throws(()=>boundedPreview({...payload,schema:'v99'},s));
});
test('duplicate session revisions and merged ancestors remain explicit warnings',()=>{
  const f=createFixture(),w=selectionWarnings([f.maps[0],f.maps[3],f.maps[4]]).join('\n');assert.match(w,/Duplicate ancestor/);assert.match(w,/Duplicate revision/);assert.match(w,/Unverified/);
});
test('3D correspondence validation rejects 2D, insufficient, collinear, duplicate, clustered; advises extra spread',()=>{
  const pair=p=>({source_xyz:p,anchor_xyz:p});assert.throws(()=>validateCorrespondences([pair([0,0,0])]));
  assert.throws(()=>validateCorrespondences([[0,0,0],[1,0,0],[2,0,0]].map(pair)));
  assert.throws(()=>validateCorrespondences([[0,0],[1,0],[0,1]].map(pair)));
  assert.equal(validateCorrespondences([[0,0,0],[2,0,0],[0,2,1]].map(pair)).length,1);
  assert.deepEqual(validateCorrespondences([[0,0,0],[2,0,0],[0,2,1],[2,2,-1]].map(pair)),[]);
  assert.throws(()=>validateCorrespondences([[0,0,0],[2,0,0],[0,2,1],[0,0,0]].map(pair)));
});
test('manual changes, undo, redo, reset and source switch invalidate late proposals without restoring identity',async()=>{
  for(const operation of [s=>s.prior('map-b',{x:3}),s=>s.undo(),s=>s.reset(),s=>s.select(maps().slice(1)),s=>s.anchor('map-b')]){
    const s=selected(),{token,request}=s.begin(),f=createFixture(),job=await f.jobs.start(request),p=await f.jobs.get(job.job_id);operation(s);const before=s.snapshot();assert.equal(s.receive(token,p),false);assert.deepEqual(s.snapshot().draft,before.draft);assert.equal(s.snapshot().proposal,null);assert.ok(s.snapshot().stale>0);
  }
  const s=selected();s.prior('map-b',{x:2});const rev=s.snapshot().revision;s.undo();assert.equal(s.snapshot().draft.priors['map-b'].x,0);s.redo();assert.equal(s.snapshot().draft.priors['map-b'].x,2);assert.ok(s.snapshot().revision>rev);
});
test('only newest job ticket can replace candidate; source pins and job revision checked',async()=>{
  const s=selected(),old=s.begin(),f=createFixture(),r=await f.jobs.start(old.request),p=await f.jobs.get(r.job_id),current=s.begin();assert.equal(s.receive(old.token,p),false);
  assert.throws(()=>s.receive(current.token,{...p,input_pins:[]}));assert.throws(()=>s.receive(current.token,{...p,schema:'unsupported'}));
  assert.equal(s.receive(current.token,p),true);assert.throws(()=>s.receive(current.token,{...p,proposal_revision:0,job_revision:3}));assert.throws(()=>s.receive(current.token,{...p,job_id:'different'}));assert.throws(()=>s.receive(current.token,{...p,job_revision:0}));
});
test('solved candidate requires complete transforms and connectivity, anchor identity',async()=>{
  for(const alter of [p=>({...p,transforms:{}}),p=>({...p,connected_components:[['map-a']]}),p=>({...p,transforms:{...p.transforms,'map-a':poseMatrix({x:1})}})]){
    const s=selected(),{token,request}=s.begin(),f=createFixture(),r=await f.jobs.start(request),p=await f.jobs.get(r.job_id);assert.throws(()=>s.receive(token,alter(p)));
  }
});
test('disconnected 3-map components block accept; ambiguous warnings preserved',async()=>{
  const s=createSession();s.select(maps());await solved(s,createFixture({scenario:'disconnected'}));assert.throws(()=>s.reviewRequest(),/Disconnected/);
  const a=selected();await solved(a,createFixture({scenario:'ambiguous'}));assert.match(a.snapshot().proposal.warnings.join(),/AMBIGUOUS/);assert.equal(a.snapshot().status,'SOLVED_CANDIDATE');
});
test('requests contain full descriptors / pins, priors and XYZ without any preview or runtime control',()=>{
  const s=selected();s.prior('map-b',{z:1,roll:.2});const {request}=s.begin();assert.equal(request.sources[0].session_id,maps()[0].session_id);assert.equal(request.convention,CONVENTION);assert.equal(request.options.activate,false);assert.equal(request.initial_guesses['map-b'][11],1);assert.equal(JSON.stringify(request).includes('points'),false);
});
test('accept and export verify server identity; originals immutable and catalogue refresh independent',async()=>{
  const s=selected(),{fixture:f}=await solved(s);assert.throws(()=>s.saveRequest('copy'));
  const review=s.reviewRequest();s.reviewed(review,await f.jobs.accept(review));const request=s.saveRequest('new_copy');assert.equal(request.activate,false);assert.ok(!('points'in request));assert.throws(()=>s.saveRequest('West hall'));
  const before=s.snapshot().draft.sources,result=await f.jobs.save(request),saved=s.saved(request,result);assert.equal(saved.id,'new-map-1');assert.equal(s.snapshot().status,'SAVED');assert.deepEqual(s.snapshot().draft.sources,before);assert.equal(f.maps.length,6);
});
test('stale review/save and server reuse of original identity fail closed',async()=>{
  const s=selected(),{fixture:f}=await solved(s),r=s.reviewRequest();const ack=await f.jobs.accept(r);s.prior('map-b',{x:4});assert.throws(()=>s.reviewed(r,ack));
  await solved(s,f);const r2=s.reviewRequest();s.reviewed(r2,await f.jobs.accept(r2));const req=s.saveRequest('copy'),saved=await f.jobs.save(req);assert.throws(()=>s.saved(req,{...saved,runtime_installed:true}));assert.throws(()=>s.saved(req,{map:{...saved.map,id:'map-a'},runtime_installed:false}));s.reset();assert.throws(()=>s.saved(req,saved));
});
test('cancel invalidates in-flight response, failure remains retryable',async()=>{
  const s=selected(),{token,request}=s.begin(),f=createFixture(),r=await f.jobs.start(request);s.cancel();assert.equal(s.receive(token,await f.jobs.get(r.job_id)),false);assert.equal(s.snapshot().status,'CANCELLED');s.begin();s.fail();assert.equal(s.snapshot().status,'FAILED');assert.doesNotThrow(()=>s.begin());
});
test('HTTP adapter centralizes only extension paths; no calls until explicit actions',async()=>{
  const calls=[],ports=createHttpPorts(async(p,o)=>{calls.push({p,...o});return{};});assert.equal(calls.length,0);
  await ports.catalogue.list();await ports.catalogue.preview(maps()[0]);await ports.jobs.start({});await ports.jobs.get('j');await ports.jobs.cancel('j');await ports.jobs.accept({proposal_id:'p'});await ports.jobs.save({});
  assert.ok(calls.every(c=>c.p.startsWith('/api/v1/extensions/multimap/')));assert.ok(calls.every(c=>!/(nav|initialpose|goal|cmd|control|activate)/i.test(c.p)));assert.equal(calls.filter(c=>c.method==='POST').length,4);assert.throws(()=>createHttpPorts(()=>{},'/api/v1/navigation'));
});
test('diagnostic NEEDS_PRIOR / DISCONNECTED retain partial transforms and warnings without acceptance',async()=>{
 for(const state of ['NEEDS_PRIOR','DISCONNECTED','REJECTED']){const s=selected(),{token,request}=s.begin(),f=createFixture({delay:0}),j=await f.jobs.start(request),p=await f.jobs.get(j.job_id);p.state=state;p.transforms={'map-a':identity()};p.connected_components=[['map-a'],['map-b']];p.warnings=['Actual provider requires more distributed priors'];assert.equal(s.receive(token,p),true);assert.equal(s.snapshot().status,state);assert.match(s.snapshot().proposal.warnings.join(),/Actual provider/);assert.throws(()=>s.reviewRequest());}
});
test('frontend imports create no network or runtime process',async()=>{
 const original=globalThis.fetch;let calls=0;globalThis.fetch=()=>{calls++;throw new Error('unexpected network');};try{const module=await import('../../robot_dashboard/static/features/multimap_fusion/index.js');assert.equal(typeof module.mount,'function');assert.equal(calls,0);}finally{globalThis.fetch=original;}
});
