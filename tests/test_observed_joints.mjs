import test from 'node:test';
import assert from 'node:assert/strict';
import { ObservedJoints, GO2_JOINT_NAMES } from '../robot_dashboard/static/features/maps/observed_joints.js';
const snapshot = (seq = 1) => ({ state: 'ok', topic: '/lowstate', source_order: 'unitree_lowstate',
  seq, age_s: .1, order: GO2_JOINT_NAMES, position_rad: [0,.7,-1.5,0,.7,-1.5,0,.7,-1.5,0,.7,-1.5] });
test('joint name mapping, duplicate freshness, stale and malformed data', () => {
  let now = 100; const joints = new ObservedJoints(() => now);
  const input = snapshot(); input.order = [...input.order].reverse(); input.position_rad = [...input.position_rad].reverse();
  joints.ingest(input); assert.equal(joints.snapshot().positions.FR_thigh_joint, .7);
  now = 1100; joints.ingest(input); assert.equal(joints.snapshot().age_ms, 1100);
  now = 1201; joints.ingest(input); assert.equal(joints.snapshot(), null);
  joints.ingest(snapshot(2)); assert.ok(joints.snapshot());
  for (const invalid of [{state:'stale'}, {age_s:-1}, {topic:'/other'}, {order:Array(12).fill('FR_hip_joint')}, {position_rad:Array(12).fill(NaN)}]) {
    joints.ingest({...snapshot(3),...invalid}); assert.equal(joints.snapshot(), null);
  }
});
test('sitting joint angles remain measured; missing input never becomes a standing pose', () => {
  const joints = new ObservedJoints(() => 0); assert.equal(joints.snapshot(), null);
  joints.ingest({...snapshot(), position_rad:[0,1.4,-2.7,0,1.4,-2.7,0,1.6,-2.7,0,1.6,-2.7]});
  assert.equal(joints.snapshot().positions.RR_thigh_joint, 1.6);
  joints.clear(); assert.equal(joints.snapshot(), null);
});
