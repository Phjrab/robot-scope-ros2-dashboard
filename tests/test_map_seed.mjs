import test from 'node:test';
import assert from 'node:assert/strict';
import {MapSeedDraft, validSeedCandidate} from '../robot_dashboard/static/features/maps/map_seed.js';
const map={id:'a'.repeat(24),revision:'b'.repeat(64),frame:'map'};
const pose={x:-201,y:302,z:2.4,roll:3,pitch:-2,yaw:179};
const inputs={mode:'native_publisher',cloud:{topic:'/cloud_registered',pipeline_stage:'registered',frame_id:'camera_init',
  observation:{observer_id:'d'.repeat(32),publisher_epoch:'c'.repeat(32)}},
  pose:{topic:'/Odometry',frame_id:'camera_init',child_frame_id:'body',observation:{observer_id:'d'.repeat(32),publisher_epoch:'f'.repeat(32)}}};
function draft() {const d=new MapSeedDraft();d.setMap(map);d.edit(pose,{heightSource:'preserved_prior'});return d;}
function candidate(d) {return {schema:'robot-scope.anchor-proposal.v1',search_mode:'seeded_local',job_id:'1'.repeat(24),
  seed_revision:d.revision,map,pose,pose_reference:'FASTLIO_IMU',units:'metres_degrees',
  T_map_odom:[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]],source_contract:d.request(inputs).source_contract,
  operational_application:'NOT_RUN',absolute_accuracy_m:null,body_extrinsic_verified:false,approximate_only:true,requires_reanchor:true,
  capture_stamp_ns:'1000',proposal_stamp_ns:'1100',pose_age_s:.1,bounds:d.bounds,delta:{xy_m:.1,yaw_deg:2,z_m:.02,tilt_deg:1},
  admissible:true,reason:'CANDIDATE',ambiguity_unresolved:true,runtime_ms:200,rmse_m:.02,overlap:.9,
  numerical:{status:'CANDIDATE',metrics:{converged:true,geometry_min_max_eigen_ratio:.2,matched_geometry_min_max_eigen_ratio:.2}}};}
test('draft keeps physical height, tracks every edit, and ignores name-only map updates',()=>{
  const d=draft(),before=d.revision;
  assert.equal(d.setMap({...map,name:'renamed',point_count:123}),false);assert.equal(d.revision,before);
  d.edit({...pose,x:99,yaw:-179,frameId:'map'});
  assert.equal(d.valid,true);assert.equal(d.pose.z,2.4);assert.equal(d.revision,before+1);
  assert.equal(d.request(inputs).pose.yaw,-179);
  assert.equal(d.request(inputs).height_source,'preserved_prior');
  assert.equal(d.setMap({...map,revision:'e'.repeat(64)}),true);assert.equal(d.pose,null);assert.equal(d.valid,false);
});
test('short click never confirms heading; missing source and malformed numeric drafts cannot be requested',()=>{
  const d=draft();d.edit(pose,{direction:false});assert.equal(d.valid,false);assert.throws(()=>d.request(inputs));
  d.edit({...pose,x:NaN});assert.equal(d.valid,false);
  d.edit(pose);assert.throws(()=>d.request({...inputs,pose:null}));
});
test('candidate fences revision, map, source, bounds, transform, stamps and numerical gates',()=>{
  const d=draft(),v=candidate(d);assert.equal(validSeedCandidate(v,d,inputs,v.job_id),true);
  const bad=[{seed_revision:d.revision-1},{job_id:'2'.repeat(24)},{map:{...map,frame:'odom'}},
    {source_contract:{...v.source_contract,cloud_epoch:'e'.repeat(32)}}, {delta:{...v.delta,xy_m:1}},
    {T_map_odom:[[1]]},{proposal_stamp_ns:'999'},{pose_age_s:2},{rmse_m:.07},{overlap:.3},
    {numerical:{...v.numerical,metrics:{...v.numerical.metrics,converged:false}}}];
  for(const changes of bad)assert.equal(validSeedCandidate({...v,...changes},d,inputs,v.job_id),false,JSON.stringify(changes));
  assert.equal(validSeedCandidate({...v,admissible:false,reason:'OUTSIDE_SEED_BOUNDS',delta:{...v.delta,xy_m:1}},d,inputs,v.job_id),true,
    'a rejected candidate can be compared, never applied');
});
test('residual limit is explicit per seed and an unlimited candidate cannot pass the default policy',()=>{
  const d=draft(),v=candidate(d);v.rmse_m=.07;
  v.residual_policy={enforced:false,max_rmse_m:null,original_max_rmse_m:.05,original_passed:false};
  assert.equal(validSeedCandidate(v,d,inputs,v.job_id),false);
  d.enforceResidualLimit=false;assert.equal(d.request(inputs).enforce_residual_limit,false);
  assert.equal(validSeedCandidate(v,d,inputs,v.job_id),true);
  assert.equal(validSeedCandidate({...v,residual_policy:null},d,inputs,v.job_id),false);
  assert.equal(validSeedCandidate({...v,overlap:.4},d,inputs,v.job_id),false);
  assert.equal(validSeedCandidate({...v,delta:{...v.delta,xy_m:1}},d,inputs,v.job_id),false);
  assert.equal(validSeedCandidate({...v,numerical:{...v.numerical,metrics:{...v.numerical.metrics,converged:false}}},d,inputs,v.job_id),false);
});
