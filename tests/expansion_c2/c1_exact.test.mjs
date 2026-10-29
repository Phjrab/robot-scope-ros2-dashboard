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
 const proposal=fromC1Proposal(data.proposal,request);assert.equal(s.receive(token,proposal),true);assert.match(s.snapshot().proposal.warnings.join(),new RegExp(C1_CONTRACT_SHA));
 s.prior(s.snapshot().draft.sources[1].id,{x:1});assert.equal(s.receive(token,proposal),false);
 assert.throws(()=>fromC1Source({...data.request.sources[0],evidence_kind:'LIVE'}));
 assert.throws(()=>fromC1Proposal({...data.proposal,input_pins:{}},request));
});
