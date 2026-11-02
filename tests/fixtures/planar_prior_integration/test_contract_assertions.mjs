import test from 'node:test';import assert from 'node:assert/strict';import {assertConditionalProof,assertConditionalConfirmation} from './contract_assertions.mjs';
const make=()=>{
 const prior={frame:'map',pose_reference:'base_link',units:'metres_radians',pose:{x:1,y:2,yaw:.1},bounds:{xy_m:.5,yaw_rad:.3},source:'OPERATOR_CURRENT_MAP_DRAFT',stationary_current_pose_confirmed:true,navigation_map_id:'a'.repeat(24),navigation_map_revision:'b'.repeat(64),calibration_sha256:'c'.repeat(64)};
 const body={bundle_generation:'d'.repeat(32),observation_session_id:'e'.repeat(32),operator_prior:prior};const loc={map_id:'f'.repeat(24),revision:'1'.repeat(64)},nav={map_id:prior.navigation_map_id,revision:prior.navigation_map_revision};
 return {body,response:{state:'ready',classification:'CONDITIONAL_ON_OPERATOR_PRIOR',quality:{ambiguity_unresolved:true},pair:{localization_3d:loc,navigation_2d:nav},operator_prior_resolution:{schema:'robot-scope.operator-prior-resolution.v1',prior_id:'2'.repeat(32),operator_prior:structuredClone(prior),accepted_monotonic_s:1,expires_monotonic_s:121,prior_anchor_stamp_ns:'123',bundle_generation:body.bundle_generation,observation_session_id:body.observation_session_id,calibration_sha256:prior.calibration_sha256,localization_3d:loc,navigation_2d:nav,source_contract_sha256:'3'.repeat(64),original_observation_sha256:'4'.repeat(64),candidate_index:0,retained_candidate_count:2,eligible_candidate_count:2,matching_candidate_count:1,projection_basis:'NAV_LOCALIZATION_CAPTURE_TO_PRIOR_ODOM_IMU_BASE',classification:'CONDITIONAL_ON_OPERATOR_PRIOR',original_ambiguity_preserved:true,original_ambiguity_unresolved:true,global_uniqueness_verified:false,absolute_accuracy_m:null,candidate_vs_prior:{xy_distance_m:.1,absolute_wrapped_yaw_rad:.1,within_existing_handoff_reference:true}}}};
};
test('matching conditional proof and explicit bounded acknowledgement',()=>{const {body,response}=make();assertConditionalProof(response,body,true);assertConditionalConfirmation({confirmed:true,stationary_supervision_acknowledged:true,conditional_prior_acknowledged:true});});
test('producer deadline is accepted when subtraction rounds above the TTL',()=>{
 const {body,response}=make(),p=response.operator_prior_resolution;
 p.accepted_monotonic_s=8.000000000000016;p.expires_monotonic_s=p.accepted_monotonic_s+120;
 assert.equal(p.expires_monotonic_s,128.00000000000003);assert.ok(p.expires_monotonic_s-p.accepted_monotonic_s>120);
 assertConditionalProof(response,body,true);
});
test('the next binary64 value above the producer deadline is rejected',()=>{
 const {body,response}=make(),p=response.operator_prior_resolution;
 p.accepted_monotonic_s=8.000000000000016;const deadline=p.accepted_monotonic_s+120;
 const bits=new DataView(new ArrayBuffer(8));bits.setFloat64(0,deadline);bits.setBigUint64(0,bits.getBigUint64(0)+1n);
 p.expires_monotonic_s=bits.getFloat64(0);assert.equal(p.expires_monotonic_s,128.00000000000006);assert.ok(p.expires_monotonic_s>deadline);
 assert.throws(()=>assertConditionalProof(response,body,true),{code:'ERR_ASSERTION'});
});
test('changed proof binding, expiry, candidate count, ambiguity and accuracy fail closed',()=>{
 for(const mutate of [r=>r.operator_prior_resolution.operator_prior.pose.x+=1,r=>r.operator_prior_resolution.expires_monotonic_s+=1,r=>r.operator_prior_resolution.matching_candidate_count=2,r=>r.quality.ambiguity_unresolved=false,r=>r.operator_prior_resolution.global_uniqueness_verified=true,r=>r.operator_prior_resolution.original_observation_sha256='bad',r=>r.operator_prior_resolution.candidate_vs_prior.xy_distance_m=.3]){const {body,response}=make();mutate(response);assert.throws(()=>assertConditionalProof(response,body,true));}
});
test('confirmation without explicit acknowledgement or with client-provided prior/proof fails',()=>{
 for(const body of [{},{confirmed:true,stationary_supervision_acknowledged:true,conditional_prior_acknowledged:false},{confirmed:true,stationary_supervision_acknowledged:true,conditional_prior_acknowledged:true,operator_prior:{}},{confirmed:true,stationary_supervision_acknowledged:true,conditional_prior_acknowledged:true,operator_prior_resolution:{}}])assert.throws(()=>assertConditionalConfirmation(body));
});

test('nonambiguous original stays conditional with false ambiguity and complete proof',()=>{const {body,response}=make();response.quality.ambiguity_unresolved=false;response.operator_prior_resolution.original_ambiguity_unresolved=false;response.operator_prior_resolution.retained_candidate_count=1;response.operator_prior_resolution.eligible_candidate_count=1;assertConditionalProof(response,body,false);});
test('missing proof, missing original ambiguity, or inconsistent ambiguity fail closed',()=>{for(const mutate of [r=>delete r.operator_prior_resolution,r=>delete r.operator_prior_resolution.original_ambiguity_unresolved,r=>r.operator_prior_resolution.original_ambiguity_unresolved=false]){const {body,response}=make();mutate(response);assert.throws(()=>assertConditionalProof(response,body,true));}});

function serverPolicy(){
 const value=make();delete value.body.operator_prior.bounds;delete value.response.operator_prior_resolution.operator_prior.bounds;
 Object.assign(value.response.operator_prior_resolution,{bounds_source:'server_policy',effective_bounds:{xy_m:.25,yaw_rad:.20}});return value;
}
test('bounds-free original prior stays unchanged while server policy is checked separately',()=>{
 const {body,response}=serverPolicy();assertConditionalProof(response,body,true);
 assert.equal(Object.hasOwn(body.operator_prior,'bounds'),false);assert.deepEqual(response.operator_prior_resolution.operator_prior,body.operator_prior);
});
test('bounds-free proof rejects missing, forged, mismatched and malformed provenance',()=>{
 const mutations=[
  p=>delete p.bounds_source,p=>delete p.effective_bounds,p=>{delete p.bounds_source;delete p.effective_bounds;},
  p=>p.bounds_source='operator_prior',p=>p.bounds_source='unknown',
  p=>p.effective_bounds.xy_m=.251,p=>p.effective_bounds.yaw_rad=.201,
  p=>p.effective_bounds.xy_m=NaN,p=>p.effective_bounds.yaw_rad=null,p=>p.effective_bounds.extra=1,
  p=>p.operator_prior.bounds={xy_m:.25,yaw_rad:.20},
  p=>{p.candidate_vs_prior.xy_distance_m=.251;p.candidate_vs_prior.within_existing_handoff_reference=false;},
  p=>{p.candidate_vs_prior.absolute_wrapped_yaw_rad=.201;p.candidate_vs_prior.within_existing_handoff_reference=false;},
 ];
 for(const mutate of mutations){const {body,response}=serverPolicy();mutate(response.operator_prior_resolution);assert.throws(()=>assertConditionalProof(response,body,true));}
});
test('explicit original bounds support both old proof and exact new provenance',()=>{
 const {body,response}=make(),p=response.operator_prior_resolution;assertConditionalProof(response,body,true);
 Object.assign(p,{bounds_source:'operator_prior',effective_bounds:structuredClone(body.operator_prior.bounds)});assertConditionalProof(response,body,true);
 for(const mutate of [p=>delete p.bounds_source,p=>delete p.effective_bounds,p=>p.bounds_source='server_policy',p=>p.effective_bounds.xy_m=.25]){
  const candidate=structuredClone(response);mutate(candidate.operator_prior_resolution);assert.throws(()=>assertConditionalProof(candidate,body,true));
 }
});
