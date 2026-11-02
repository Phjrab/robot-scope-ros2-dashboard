import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = readFileSync(new URL('../robot_dashboard/static/features/navigation/preparation.js', import.meta.url), 'utf8');
const { validConditionalResolution: valid, validPriorCurrentMembers: validCurrent } = await import(`data:text/javascript;base64,${Buffer.from(source + '\nexport { validConditionalResolution, validPriorCurrentMembers };').toString('base64')}`);
function fixture() {
  const ctx = { generation: 'b'.repeat(32), session_id: 'a'.repeat(32), calibration_sha256: 'c'.repeat(64),
    localization_3d: { map_id: 'd'.repeat(24), revision: 'e'.repeat(64) }, navigation_2d: { map_id: 'f'.repeat(24), revision: '1'.repeat(64) } };
  const prior = { frame: 'map', pose_reference: 'base_link', units: 'metres_radians', pose: {x:1,y:2,yaw:.1},
    bounds: {xy_m:.75,yaw_rad:.4}, source:'OPERATOR_CURRENT_MAP_DRAFT', stationary_current_pose_confirmed:true,
    navigation_map_id:ctx.navigation_2d.map_id, navigation_map_revision:ctx.navigation_2d.revision, calibration_sha256:ctx.calibration_sha256 };
  ctx.operatorPrior = structuredClone(prior);
  const proof = { schema:'robot-scope.operator-prior-resolution.v1', classification:'CONDITIONAL_ON_OPERATOR_PRIOR',
    original_ambiguity_preserved:true, original_ambiguity_unresolved:true, global_uniqueness_verified:false, absolute_accuracy_m:null,
    prior_id:'9'.repeat(32), source_contract_sha256:'8'.repeat(64), original_observation_sha256:'7'.repeat(64), prior_anchor_stamp_ns:'123',
    accepted_monotonic_s:100, expires_monotonic_s:220, bundle_generation:ctx.generation, observation_session_id:ctx.session_id,
    calibration_sha256:ctx.calibration_sha256, localization_3d:ctx.localization_3d, navigation_2d:ctx.navigation_2d, operator_prior:prior,
    candidate_index:0, retained_candidate_count:2, eligible_candidate_count:2, matching_candidate_count:1,
    projection_basis:'NAV_LOCALIZATION_CAPTURE_TO_PRIOR_ODOM_IMU_BASE', candidate_vs_prior:{xy_distance_m:.1,absolute_wrapped_yaw_rad:.1,within_existing_handoff_reference:true} };
  return {ctx,proof};
}

test('legacy proof requires a single raw matching candidate and still checks the original context', () => {
  const {ctx,proof} = fixture();
  assert.equal(valid(proof,ctx),true);
  proof.matching_candidate_count = 2;
  assert.equal(valid(proof,ctx),false);
  proof.matching_candidate_count = 1; proof.global_uniqueness_verified = true;
  assert.equal(valid(proof,ctx),false);
});

function groupedFixture() {
  const value = fixture();
  Object.assign(value.proof, { grouping_policy:'PINNED_V031_SE3_FIRST_REPRESENTATIVE_V1', matching_candidate_count:2,
    matching_hypothesis_count:1, matching_retained_candidate_count:2, matching_member_indices:[0,1], verified_duplicate_count:1,
    matching_member_geometry:[
      {candidate_index:0,z_m:.8,roll_rad:.1,pitch_rad:.2,z_delta_m:0,roll_delta_rad:0,pitch_delta_rad:0},
      {candidate_index:1,z_m:.81,roll_rad:.11,pitch_rad:.19,z_delta_m:.01,roll_delta_rad:.01,pitch_delta_rad:-.01},
    ] });
  return value;
}

test('one explicitly verified group may contain several retained candidates', () => {
  const {ctx,proof}=groupedFixture(); assert.equal(valid(proof,ctx),true);
});

test('grouped proof fails closed on count, index, geometry, digest or policy inconsistency', () => {
  const changes = [
    p=>p.matching_hypothesis_count=2, p=>p.matching_hypothesis_count=0, p=>p.matching_candidate_count=1,
    p=>p.matching_retained_candidate_count=1, p=>p.eligible_candidate_count=1, p=>p.matching_member_indices=[0,0],
    p=>p.matching_member_indices=[1,0], p=>p.matching_member_indices=[0,2], p=>p.candidate_index=1,
    p=>p.matching_member_geometry.pop(), p=>p.matching_member_geometry[1].candidate_index=0,
    p=>p.matching_member_geometry[1].z_m=null, p=>p.matching_member_geometry[1].pitch_delta_rad=.3,
    p=>p.matching_member_geometry[0].z_delta_m=.1, p=>p.verified_duplicate_count=0,
    p=>p.grouping_policy='unknown', p=>p.original_observation_sha256='bad', p=>p.global_uniqueness_verified=true,
    p=>delete p.grouping_policy, p=>delete p.matching_hypothesis_count, p=>delete p.matching_member_geometry,
  ];
  for (const change of changes) { const {ctx,proof}=groupedFixture(); change(proof); assert.equal(valid(proof,ctx),false,change.toString()); }
});

test('partial grouping fields cannot fall back to the legacy proof branch', () => {
  for (const field of ['grouping_policy','matching_hypothesis_count','matching_retained_candidate_count','matching_member_indices','matching_member_geometry','verified_duplicate_count']) {
    const {ctx,proof}=fixture(); proof[field]=null; assert.equal(valid(proof,ctx),false,field);
  }
});

function currentFixture() {
  const {ctx,proof}=groupedFixture();
  const current={pose_stamp_ns:'1234',pose_age_s:.1,xy_distance_m:.1,yaw_delta_rad:.1,within_prior_bounds:true,within_existing_handoff_reference:true,all_members_within_prior_bounds:true,
    member_checks:[{candidate_index:0,xy_distance_m:.1,absolute_wrapped_yaw_rad:.1,within_prior_bounds:true},{candidate_index:1,xy_distance_m:.11,absolute_wrapped_yaw_rad:.09,within_prior_bounds:true}]};
  return {ctx,proof,current};
}
test('all grouped members and confirmation-time evidence must match and fit the prior', () => {
  const {proof,current}=currentFixture(); assert.equal(validCurrent(proof,current),true); assert.equal(validCurrent(proof,current,true),true);
  const changes=[c=>delete c.member_checks,c=>c.member_checks.pop(),c=>c.member_checks[1].candidate_index=0,c=>c.member_checks.reverse(),
    c=>c.member_checks[1].xy_distance_m=null,c=>c.member_checks[1].within_prior_bounds=false,c=>c.all_members_within_prior_bounds=false,
    c=>c.within_prior_bounds=false,c=>c.within_existing_handoff_reference=false,c=>c.xy_distance_m=.2,c=>c.yaw_delta_rad=.3,
    c=>c.pose_age_s=1.1,c=>c.pose_stamp_ns='0'];
  for(const change of changes){const {proof,current}=currentFixture();change(current);assert.equal(validCurrent(proof,current),false,change.toString());}
  const other=currentFixture();other.current.member_checks[1].xy_distance_m=1;other.current.member_checks[1].within_prior_bounds=false;other.current.all_members_within_prior_bounds=false;
  assert.equal(validCurrent(other.proof,other.current),true,'an accurate outside report is informational');
  assert.equal(validCurrent(other.proof,other.current,true),false,'confirmation evidence requires every member inside');
});

function nextRepresentablePositive(value) {
  const buffer = new ArrayBuffer(8), view = new DataView(buffer);
  view.setFloat64(0, value, false);
  view.setBigUint64(0, view.getBigUint64(0, false) + 1n, false);
  return view.getFloat64(0, false);
}

test('proof TTL accepts the generated absolute deadline and rejects the next representable value', () => {
  const accepted = 8.000000000000016, deadline = accepted + 120;
  assert.ok(deadline - accepted > 120, 'the generator and subtraction differ at this deterministic boundary');
  for (const make of [fixture, groupedFixture]) {
    const {ctx,proof} = make(); proof.accepted_monotonic_s = accepted; proof.expires_monotonic_s = deadline;
    assert.equal(valid(proof,ctx),true,'exact generated deadline is allowed');
    proof.expires_monotonic_s = nextRepresentablePositive(deadline);
    assert.ok(proof.expires_monotonic_s > accepted + 120);
    assert.equal(valid(proof,ctx),false,'the immediately larger float is rejected');
    proof.expires_monotonic_s = accepted + 119;
    assert.equal(valid(proof,ctx),true,'shorter positive duration is allowed');
    for (const value of [accepted, 0, -1, NaN, Infinity, -Infinity, null, '128']) {
      proof.expires_monotonic_s = value; assert.equal(valid(proof,ctx),false,`invalid expiry ${value}`);
    }
    for (const value of [-1, NaN, Infinity, -Infinity, null, '8']) {
      proof.accepted_monotonic_s = value; proof.expires_monotonic_s = deadline;
      assert.equal(valid(proof,ctx),false,`invalid accepted time ${value}`);
    }
    proof.accepted_monotonic_s = 0; proof.expires_monotonic_s = 120;
    assert.equal(valid(proof,ctx),true,'zero accepted time is valid with a generated deadline');
    proof.expires_monotonic_s = nextRepresentablePositive(120);
    assert.equal(valid(proof,ctx),false,'a deadline beyond the generated bound remains invalid at zero');
    proof.accepted_monotonic_s = Number.MAX_VALUE; proof.expires_monotonic_s = Number.MAX_VALUE;
    assert.equal(valid(proof,ctx),false,'equal times remain invalid even if addition rounds');
  }
});
