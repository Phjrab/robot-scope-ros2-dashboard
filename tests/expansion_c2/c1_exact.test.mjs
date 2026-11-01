import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {createSession} from '../../robot_dashboard/static/features/multimap_fusion/session.js';
import {fromC1Source,toC1Request,fromC1Proposal,C1_CONTRACT_SHA} from '../../robot_dashboard/static/features/multimap_fusion/c1_contract.js';
test('published exact C1 descriptors survive UI request and strict external Python DTO validation', {skip:!process.env.C2_C1_FIXTURE},()=>{
 const data=JSON.parse(readFileSync(process.env.C2_C1_FIXTURE,'utf8')),s=createSession();s.select(data.request.sources.map(v=>fromC1Source(v)));const {token,request}=s.begin();const wire=toC1Request(request,{request_id:'c2-request-check'});
 assert.equal(wire.mode,'auto');assert.deepEqual(wire.sources,data.request.sources);assert.equal(wire.sources[0].mapping_session_id,null);assert.match(s.snapshot().draft.sources[0].session_id,/unverified/);
 const result=spawnSync(process.env.C2_PYTHON||'python3',['-c','import json,sys; from robot_dashboard.expansion_contracts.messages import FusionRequest; print(FusionRequest.from_dict(json.load(sys.stdin)).fingerprint)'],{input:JSON.stringify(wire),encoding:'utf8',timeout:10000,cwd:process.env.C2_C1_EXPORT,env:{...process.env,PYTHONPATH:process.env.C2_C1_EXPORT}});
 assert.equal(result.status,0,result.stderr);assert.match(result.stdout,/^[a-f0-9]{64}/);
 const keys=Object.keys(data.proposal.input_pins),diagnostic=fromC1Proposal({...data.proposal,pairwise_edges:[{target:keys[0],source:keys[1],accepted:true,metrics:{overlap_source:.8,overlap_target:.9,rmse_m:.01,distance_p95_m:.02}}]},request);assert.match(diagnostic.metrics.pairwise[0].overlap,/0.80 source.*0.90 target/);assert.equal(diagnostic.metrics.pairwise[0].distance_p95_m,.02);
 const proposal=fromC1Proposal(data.proposal,request);assert.equal(s.receive(token,proposal),true);assert.match(s.snapshot().proposal.warnings.join(),new RegExp(C1_CONTRACT_SHA));
 s.prior(s.snapshot().draft.sources[1].id,{x:1});assert.equal(s.receive(token,proposal),false);
 assert.throws(()=>fromC1Source({...data.request.sources[0],evidence_kind:'LIVE'}));
 assert.throws(()=>fromC1Proposal({...data.proposal,input_pins:{}},request));
 for(const [key,value] of [['frame_id','different-frame'],['session_id','different-session']]) {
   const changed=structuredClone(request);changed.sources[0][key]=value;
   assert.throws(()=>toC1Request(changed,{request_id:'identity-drift'}),/pin changed/);
 }
 const zero=fromC1Proposal({...data.proposal,pairwise_edges:[{target:keys[0],source:keys[1],accepted:true,metrics:{overlap_source:1,overlap_target:1,rmse_m:0,distance_p95_m:0}}]},request);
 assert.equal(zero.metrics.pairwise[0].rmse_m,0);
 assert.equal(zero.metrics.pairwise[0].distance_p95_m,0);
});
