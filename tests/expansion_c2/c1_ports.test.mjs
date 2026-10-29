import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createSession} from '../../robot_dashboard/static/features/multimap_fusion/session.js';
import {createC1Ports} from '../../robot_dashboard/static/features/multimap_fusion/c1_ports.js';
import {fromC1Source} from '../../robot_dashboard/static/features/multimap_fusion/c1_contract.js';
test('C1 HTTP normalization preserves full sources, advances reviewed revision, verifies exported reload', {skip:!process.env.C2_C1_FIXTURE},async()=>{
 const external=JSON.parse(readFileSync(process.env.C2_C1_FIXTURE,'utf8')),calls=[];let revision=1;
 const raw=()=>({job_id:external.proposal.job_id,state:'SOLVED_CANDIDATE',progress:1,operational_installed:false,proposal:{...external.proposal,proposal_revision:revision}});
 const manifest={schema:'robot-scope.multimap-fusion.v1',id:'e'.repeat(24),name:'copy',revision:'e'.repeat(64),frame_id:'fused',point_count:6,output_hashes:{'map.pcd':'d'.repeat(64)},sources:external.request.sources,operational_installed:false,job_id:external.proposal.job_id,proposal_revision:2};
 const ports=createC1Ports(async(path,options)=>{calls.push({path,...options});if(path.endsWith('/sources'))return{sources:external.request.sources};if(path.endsWith('/review')){revision=2;return{...raw(),state:'REVIEWED',proposal_revision:2,review:{accepted:true}};}if(path.includes('/exports'))return manifest;return raw();});
 const s=createSession();s.select((await ports.catalogue.list()).sources);const {token,request}=s.begin();s.receive(token,await ports.jobs.start(request));const r=s.reviewRequest();s.reviewed(r,await ports.jobs.accept(r));assert.equal(s.snapshot().proposal.proposal_revision,2);
 const req=s.saveRequest('copy');s.saved(req,await ports.jobs.save(req));assert.equal(s.snapshot().status,'SAVED');assert.deepEqual(calls.find(c=>c.path.endsWith('/review')).body,{expected_proposal_revision:1,accepted:true,manual_selection:null});assert.equal(calls.find(c=>c.path.endsWith('/exports')&&c.method==='POST').body.expected_proposal_revision,2);
 assert.deepEqual(calls.find(c=>c.path.endsWith('/jobs')).body.sources,external.request.sources);assert.ok(calls.every(c=>c.path.startsWith('/api/v1/extensions/multimap/')));
});
test('C1 review revision bump cannot be forged without candidate identity',async()=>{
 const {createFixture}=await import('../../experiments/expansion_20261029/c2_map_ui/fixture.mjs'),f=createFixture({delay:0}),s=createSession();s.select(f.maps.slice(0,2));const{token,request}=s.begin(),j=await f.jobs.start(request);s.receive(token,await f.jobs.get(j.job_id));const r=s.reviewRequest();assert.throws(()=>s.reviewed(r,{proposal_id:r.proposal_id,proposal_revision:2,review_id:'r'}));s.reviewed(r,{proposal_id:r.proposal_id,proposal_revision:2,reviewed_candidate_revision:1,review_id:'r'});assert.equal(s.saveRequest('copy').proposal_revision,2);
});
