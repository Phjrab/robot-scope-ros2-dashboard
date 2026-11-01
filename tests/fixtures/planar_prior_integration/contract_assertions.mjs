// Independent checks against C1.1 API_CONTRACT; values are synthetic.
import assert from 'node:assert/strict';
export function assertConditionalProof(response,body,expectedOriginalAmbiguity){
 assert.equal(response.state,'ready');assert.equal(response.classification,'CONDITIONAL_ON_OPERATOR_PRIOR');assert.equal(typeof expectedOriginalAmbiguity,'boolean');assert.equal(typeof response.quality.ambiguity_unresolved,'boolean');assert.equal(response.quality.ambiguity_unresolved,expectedOriginalAmbiguity);
 const p=response.operator_prior_resolution;assert.equal(p.schema,'robot-scope.operator-prior-resolution.v1');assert.match(p.prior_id,/^[a-f0-9]{32}$/);assert.deepEqual(p.operator_prior,body.operator_prior);
 assert.ok(Number.isFinite(p.accepted_monotonic_s)&&Number.isFinite(p.expires_monotonic_s)&&p.expires_monotonic_s>p.accepted_monotonic_s&&p.expires_monotonic_s-p.accepted_monotonic_s<=120);
 assert.match(p.prior_anchor_stamp_ns,/^[1-9][0-9]*$/);assert.equal(p.bundle_generation,body.bundle_generation);assert.equal(p.observation_session_id,body.observation_session_id);assert.equal(p.calibration_sha256,body.operator_prior.calibration_sha256);
 assert.deepEqual(p.localization_3d,response.pair.localization_3d);assert.deepEqual(p.navigation_2d,response.pair.navigation_2d);assert.match(p.source_contract_sha256,/^[a-f0-9]{64}$/);assert.match(p.original_observation_sha256,/^[a-f0-9]{64}$/);
 assert.ok(Number.isInteger(p.candidate_index)&&Number.isInteger(p.retained_candidate_count)&&Number.isInteger(p.eligible_candidate_count));assert.ok(p.retained_candidate_count>=1&&p.eligible_candidate_count>=1&&p.eligible_candidate_count<=p.retained_candidate_count&&p.candidate_index>=0&&p.candidate_index<p.retained_candidate_count);assert.equal(p.matching_candidate_count,1);
 assert.equal(p.projection_basis,'NAV_LOCALIZATION_CAPTURE_TO_PRIOR_ODOM_IMU_BASE');assert.equal(p.classification,'CONDITIONAL_ON_OPERATOR_PRIOR');assert.equal(p.original_ambiguity_preserved,true);assert.equal(typeof p.original_ambiguity_unresolved,'boolean');assert.equal(p.original_ambiguity_unresolved,expectedOriginalAmbiguity);assert.equal(p.original_ambiguity_unresolved,response.quality.ambiguity_unresolved);assert.equal(p.global_uniqueness_verified,false);assert.equal(p.absolute_accuracy_m,null);
 const d=p.candidate_vs_prior;assert.ok(Number.isFinite(d.xy_distance_m)&&d.xy_distance_m>=0&&Number.isFinite(d.absolute_wrapped_yaw_rad)&&d.absolute_wrapped_yaw_rad>=0);assert.equal(typeof d.within_existing_handoff_reference,'boolean');assert.equal(d.within_existing_handoff_reference,d.xy_distance_m<=.25&&d.absolute_wrapped_yaw_rad<=.20);
 return p;
}
export function assertConditionalConfirmation(body){
 assert.equal(body.confirmed,true);assert.equal(body.stationary_supervision_acknowledged,true);assert.equal(body.conditional_prior_acknowledged,true);assert.equal(Object.hasOwn(body,'operator_prior'),false);assert.equal(Object.hasOwn(body,'operator_prior_resolution'),false);
}
