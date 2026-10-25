import test from 'node:test';
import assert from 'node:assert/strict';
import { anchorSourceContract, validateAnchorProposal } from '../robot_dashboard/static/features/maps/anchor_proposal.js';

const map={id:'a'.repeat(24),revision:'b'.repeat(64),frame:'map'}, jobId='c'.repeat(24);
function fixture() {
  const observation={observer_id:'d'.repeat(32),publisher_epoch:'e'.repeat(32)};
  const inputs={mode:'native_publisher',cloud:{topic:'/cloud_registered',pipeline_stage:'registered',frame_id:'camera_init',observation},
    pose:{topic:'/Odometry',frame_id:'camera_init',child_frame_id:'body',observation}};
  const value={schema:'robot-scope.anchor-proposal.v1',job_id:jobId,map,pose_reference:'FASTLIO_IMU',units:'metres_degrees',
    pose:{x:.5,y:.4,z:.3,roll:1,pitch:2,yaw:30},approximate_only:true,requires_reanchor:true,operational_application:'NOT_RUN',
    absolute_accuracy_m:null,body_extrinsic_verified:false,ambiguity_unresolved:false,rmse_m:.07,overlap:.9,pose_age_s:.1,
    capture_stamp_ns:'1792309179130175352',proposal_stamp_ns:'1792309179130175353',source_contract:anchorSourceContract(inputs)};
  return {value,inputs};
}
test('automatic anchor proposals retain exact stamps and map/source fences',()=>{
  const {value,inputs}=fixture();assert.equal(validateAnchorProposal(value,jobId,map,inputs),true);
  for(const change of [{proposal_stamp_ns:'1'},{capture_stamp_ns:1792309179130175352},{pose_age_s:1.01},
    {map:{...map,revision:'x'}},{pose_reference:'UNVERIFIED_BODY'},{requires_reanchor:false}]) {
    assert.equal(validateAnchorProposal({...value,...change},jobId,map,inputs),false);
  }
  const changed=structuredClone(inputs);changed.pose.observation.publisher_epoch='f'.repeat(32);
  assert.equal(validateAnchorProposal(value,jobId,map,changed),false);
});
test('unverified subscription proposals cannot silently change permission or session',()=>{
  const {value,inputs}=fixture();inputs.mode='subscription_observation';
  inputs.cloud.observation.subscription_evidence={session_id:'1'.repeat(32),graph:{fingerprint:'2'.repeat(64)}};
  value.source_contract=anchorSourceContract(inputs);
  assert.equal(validateAnchorProposal(value,jobId,map,inputs),true);
  const changed=structuredClone(inputs);changed.pose.observation.subscription_evidence.session_id='3'.repeat(32);
  assert.equal(validateAnchorProposal(value,jobId,map,changed),false);
  inputs.mode='native_publisher';assert.equal(validateAnchorProposal(value,jobId,map,inputs),false);
});
