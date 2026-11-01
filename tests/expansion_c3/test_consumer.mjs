import test from 'node:test';
import assert from 'node:assert/strict';
import { createSceneConsumer, LIMITS } from '../../robot_dashboard/static/features/obstacle_scene/consumer.js';
import { makeContext, makePacket, SCENARIOS } from '../../experiments/expansion_20261029/c3_scene_ui/fixture.js';
function harness() {
  let context=makeContext(), now=0;
  const consumer=createSceneConsumer({getMap:()=>context,clock:()=>now});
  return {consumer,context,advance:t=>{now+=t;},setContext:c=>{context=c;}};
}
test('synthetic scenarios execute without generating paths or collisions',()=>{
  const {consumer}=harness();
  for(const [i,name] of SCENARIOS.entries()) assert.equal(consumer.ingest(makePacket(i,name)),true,name);
  const view=consumer.snapshot();
  assert.equal(view.evidence_kind,'SYNTHETIC'); assert.equal(view.obstacles.value.obstacles.length,3);
  assert.equal(view.local.value,null); assert.equal(view.collision.value.min_clearance_m,null);
  assert.equal(view.collision.value.contact_state,'CONTACT_UNCONFIRMED');
});
test('empty/no local trajectory is explicit and preserves no previous objects',()=>{
  const {consumer}=harness();consumer.ingest(makePacket(1));consumer.ingest(makePacket(2,'empty'));
  const v=consumer.snapshot();assert.equal(v.obstacles.value.obstacles.length,0);assert.equal(v.local.reason,'MISSING');
  assert.equal(v.path.value,null);assert.equal(v.collision.value,null);
});
test('all identity changes clear history and reject old packets before new input',()=>{
  for(const field of ['map_id','revision','frame_id','source_epoch','stream_epoch','clock_domain','calibration_id']){
    const h=harness(),old=makePacket(10); h.consumer.ingest(old);
    h.setContext({...h.context,[field]:'new-value'});
    assert.equal(h.consumer.snapshot().ready,false,field);assert.equal(h.consumer.diagnostics().history,0);
    if(field!=='calibration_id')assert.equal(h.consumer.ingest(old),false,field);
    const next=makePacket(1,'multi',{...h.context,[field]:'new-value'});
    assert.equal(h.consumer.ingest(next),true,field);
    assert.equal(h.consumer.snapshot().history.length,1,field);
  }
});
test('trusted context unavailable, unknown units and source clock are rejected',()=>{
  const h=harness();h.setContext(null);assert.equal(h.consumer.ingest(makePacket(1)),false);
  h.setContext(h.context);
  for(const field of ['units','clock_domain']){
    const p=makePacket(1);if(field==='units')p.map_identity.units='mm';else p.clock_domain='foreign';
    assert.equal(h.consumer.ingest(p),false);
  }
});
test('sequence, duplicate, epoch reconnect and source stamp rollback are fenced',()=>{
  const h=harness();assert.equal(h.consumer.ingest(makePacket(5)),true);
  assert.equal(h.consumer.ingest(makePacket(5)),false);assert.equal(h.consumer.ingest(makePacket(4)),false);
  const rolled=makePacket(6);rolled.stamp_ns='1';assert.equal(h.consumer.ingest(rolled),false);
  const old=makePacket(100);h.setContext({...h.context,stream_epoch:'reconnected'});
  assert.equal(h.consumer.ingest(old),false);
  assert.equal(h.consumer.ingest(makePacket(1,'multi',{...h.context,stream_epoch:'reconnected'})),true);
  assert.equal(h.consumer.ingest(old),false);
});
test('ns remain exact beyond Number.MAX_SAFE_INTEGER and source clocks are never subtracted from host',()=>{
  const h=harness(),p=makePacket(1),big=12345678901234567890n,delta=big-BigInt(p.stamp_ns);
  p.stamp_ns=String(big);
  for(const layer of [p.robot_pose,p.joint_state,...p.sources,p.obstacle_frame,p.global_path,...p.costmaps,p.collision_assessment])layer.stamp_ns=String(BigInt(layer.stamp_ns)+delta);
  p.collision_assessment.valid_until_ns=String(big+500000000n);
  assert.equal(h.consumer.ingest(p),true);assert.equal(h.consumer.snapshot().pose.age_ms,0);
  h.advance(501);assert.equal(h.consumer.snapshot().pose.reason,'STALE');
});
test('bad calibration, unknown clock, sensor skew fail closed without losing single sensor geometry',()=>{
  for(const name of ['bad-calibration','clock-mismatch','sensor-skew']){
    const h=harness();h.consumer.ingest(makePacket(1,name));const v=h.consumer.snapshot();
    assert.equal(v.obstacles.value?.obstacles.length||0,0,name);assert.equal(v.collision.value,null,name);
  }
  for(const name of ['lidar-only','depth-only','unmatched-yolo']){
    const h=harness();h.consumer.ingest(makePacket(1,name));const v=h.consumer.snapshot();
    assert.equal(v.obstacles.value.obstacles.length,1);assert.equal(v.obstacles.value.obstacles[0].class_name,'unknown');
  }
});
test('future, wrong frame, invalid quaternion and source geometry oversize never draw',()=>{
  const mutations=[p=>{p.obstacle_frame.stamp_ns='999999999999999999';},p=>{p.obstacle_frame.frame_key={frame_id:'odom'};},
    p=>{p.obstacle_frame.obstacles[0].geometry.orientation_xyzw=[0,0,0,2];},
    p=>{p.sources[0].points_m=Array.from({length:LIMITS.points+1},()=>[0,0,0]);}];
  for(const mutate of mutations){const h=harness(),p=makePacket(1,'cone');mutate(p);h.consumer.ingest(p);
    assert.equal(h.consumer.snapshot().obstacles.value?.obstacles.length||0,0);assert.equal(h.consumer.snapshot().collision.value,null);}
});
test('pose/joints stale hide robot inputs and suppress derived risk immediately',()=>{
  for(const name of ['stale-pose','stale-joints']){const h=harness();h.consumer.ingest(makePacket(1,name));assert.equal(h.consumer.snapshot().collision.value,null);}
  const h=harness();h.consumer.ingest(makePacket(1));h.advance(501);
  assert.equal(h.consumer.snapshot().pose.value,null);assert.equal(h.consumer.snapshot().collision.value,null);
  h.advance(800);assert.equal(h.consumer.snapshot().joints.value,null);assert.equal(h.consumer.snapshot().obstacles.value,null);
});
test('fresh but temporally incompatible pose/joints or obstacle source are blocked',()=>{
  const h=harness(),p=makePacket(1);p.joint_state.stamp_ns=String(BigInt(p.stamp_ns)-300000000n);
  h.consumer.ingest(p);assert.equal(h.consumer.snapshot().joints.reason,'POSE_JOINT_TIME_SKEW');assert.equal(h.consumer.snapshot().collision.value,null);
  const q=makePacket(2);q.obstacle_frame.stamp_ns=String(BigInt(q.stamp_ns)-300000000n);h.consumer.ingest(q);
  assert.equal(h.consumer.snapshot().obstacles.value.obstacles.length,0);
});
test('collision validity interval, refs and unsupported physical contact are not accepted',()=>{
  const changes=[p=>{p.collision_assessment.robot_pose_ref='goal-marker';},p=>{p.collision_assessment.joint_state_ref='other';},
    p=>{p.collision_assessment.obstacle_frame_ref=9;},p=>{p.collision_assessment.path_ref='different';},
    p=>{p.collision_assessment.contact_state='CONTACT_CONFIRMED';},p=>{p.collision_assessment.valid_until_ns='1';}];
  for(const change of changes){const h=harness(),p=makePacket(1);change(p);h.consumer.ingest(p);assert.equal(h.consumer.snapshot().collision.value,null);}
  const h=harness(),p=makePacket(1);p.collision_assessment.valid_until_ns=String(BigInt(p.stamp_ns)+10000000n);
  h.consumer.ingest(p);assert.ok(h.consumer.snapshot().collision.value);h.advance(11);assert.equal(h.consumer.snapshot().collision.reason,'VALIDITY_EXPIRED');
});
test('costmap and XY path must explicitly declare their display plane',()=>{
  const h=harness(),p=makePacket(1);delete p.global_path.plane_z_m;p.costmaps[0].representation='XYZ';
  h.consumer.ingest(p);assert.equal(h.consumer.snapshot().path.value,null);assert.equal(h.consumer.snapshot().costmaps[0].value,null);
});
test('path generations bounded; missing current path is never substituted by history',()=>{
  const h=harness();for(let i=0;i<20;i++){const p=makePacket(i);p.global_path.generation=`g-${i}`;h.consumer.ingest(p);}
  assert.equal(h.consumer.snapshot().history.length,LIMITS.pathHistory);
  h.consumer.ingest(makePacket(21,'empty'));assert.equal(h.consumer.snapshot().path.value,null);
  h.advance(5001);assert.equal(h.consumer.snapshot().history.length,0);
});
test('retained geometry and metadata are isolated from producer reuse',()=>{
  const h=harness(),p=makePacket(1);h.consumer.ingest(p);p.sources[0].points_m[0][0]=10000;
  p.obstacle_frame.obstacles[0].geometry.center_m[0]=10000;p.global_path.points_m[0][0]=10000;
  assert.notEqual(h.consumer.snapshot().sources[0].value.points_m[0][0],10000);
  assert.notEqual(h.consumer.snapshot().obstacles.value.obstacles[0].geometry.center_m[0],10000);
  assert.notEqual(h.consumer.snapshot().path.value.points_m[0][0],10000);
});
test('1200 synchronous packets retain one packet, at most 3 path generations, and destroy releases all',()=>{
  const h=harness();for(let i=0;i<1200;i++){const p=makePacket(i);p.global_path.generation=`g-${i}`;h.consumer.ingest(p);}
  assert.equal(h.consumer.diagnostics().accepted,1200);assert.equal(h.consumer.diagnostics().retainedPackets,1);
  assert.equal(h.consumer.diagnostics().history,3);h.consumer.destroy();assert.equal(h.consumer.diagnostics().retainedPackets,0);
  assert.equal(h.consumer.ingest(makePacket(1201)),false);
});
test('module import has no DOM, network, model-loading or process side effects',async()=>{
  const originalFetch=globalThis.fetch;let calls=0;
  globalThis.fetch=()=>{calls++;throw new Error('network on import');};
  try{const module=await import('../../robot_dashboard/static/features/obstacle_scene/index.js');assert.equal(typeof module.mountObstacleScene,'function');assert.equal(calls,0);}
  finally{globalThis.fetch=originalFetch;}
});

test('paused queue residence counts from offer, including first display and step',()=>{
  const h=harness(),p=makePacket(1),arrival=h.consumer.offer(p);
  h.advance(2600);assert.ok(h.consumer.ingest(p,arrival));const v=h.consumer.snapshot();
  assert.equal(v.pose.reason,'STALE');assert.equal(v.joints.reason,'STALE');assert.equal(v.collision.value,null);
  assert.ok(h.consumer.ingest(makePacket(2)));assert.ok(h.consumer.snapshot().pose.value);
});
test('a delayed older offer cannot replace the latest pending frame or revive an expired one',()=>{
  const h=harness(),p=makePacket(2),arrival=h.consumer.offer(p);
  assert.equal(h.consumer.offer(makePacket(1)),false);assert.ok(h.consumer.ingest(p,arrival));
  h.advance(2600);assert.equal(h.consumer.offer(makePacket(1)),false);assert.equal(h.consumer.snapshot().pose.reason,'STALE');
});
test('superseded arrival token is rejected and cannot restore previous geometry',()=>{
  const h=harness(),old=makePacket(1),arrival=h.consumer.offer(old),next=makePacket(2),nextArrival=h.consumer.offer(next);
  assert.equal(h.consumer.ingest(old,arrival),false);
  assert.equal(h.consumer.ingest({...next,clock_domain:'foreign'},nextArrival),false);
  assert.ok(h.consumer.ingest(next,nextArrival));
  assert.equal(h.consumer.snapshot().sequence,2);
  assert.equal(h.consumer.ingest(next,nextArrival),false); // An arrival is consumed once.
});
test('queued frames cannot cross revision, source epoch, reconnect or clock changes',()=>{
  for(const field of ['revision','source_epoch','stream_epoch','clock_domain']){
    const h=harness(),p=makePacket(1),arrival=h.consumer.offer(p);
    const context={...h.context,[field]:'new'};h.setContext(context);
    assert.equal(h.consumer.snapshot().ready,false);assert.equal(h.consumer.ingest(p,arrival),false);
    assert.equal(h.consumer.offer(p),false);assert.ok(h.consumer.ingest(makePacket(1,'multi',context)));
  }
});
test('queued missing pose/joints stay unavailable; no standby robot is synthesized',()=>{
  for(const slot of ['robot_pose','joint_state']){
    const h=harness(),p=makePacket(1);p[slot]=null;
    const arrival=h.consumer.offer(p);h.consumer.ingest(p,arrival);const v=h.consumer.snapshot();
    assert.equal(v[slot==='robot_pose'?'pose':'joints'].reason,'MISSING');assert.equal(v.collision.value,null);
  }
});
test('collision validity is shorter than pose TTL and includes pending residence',()=>{
  const h=harness(),p=makePacket(1);p.collision_assessment.valid_until_ns=String(BigInt(p.stamp_ns)+10000000n);
  const arrival=h.consumer.offer(p);h.advance(11);h.consumer.ingest(p,arrival);
  assert.ok(h.consumer.snapshot().pose.value);assert.equal(h.consumer.snapshot().collision.reason,'VALIDITY_EXPIRED');
});
