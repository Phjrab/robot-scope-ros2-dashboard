import test from 'node:test';
import assert from 'node:assert/strict';
import { compatibleAnchorPreset, validAnchorPose } from '../robot_dashboard/static/features/maps/anchor_presets.js';

const map = { id:'a'.repeat(24), revision:'b'.repeat(64), frame:'camera_init' };
const pose = { x:.3, y:.4, z:.05, roll:1, pitch:-.5, yaw:30 };
const entry = { id:'user-'+'c'.repeat(32), label:'출입구', values:{ map_id:map.id, map_revision:map.revision,
  map_frame:map.frame, pose_reference:'FASTLIO_IMU', pose, units:'metres_degrees', saved_at:'2026-10-24T12:00:00+00:00' } };
test('presets are compatible only with the exact map revision and coordinate frame', () => {
  assert.equal(compatibleAnchorPreset(entry,map),true);
  for (const changed of [{...map,id:'d'.repeat(24)},{...map,revision:'e'.repeat(64)},{...map,frame:'map'}])
    assert.equal(compatibleAnchorPreset(entry,changed),false);
});
test('malformed numeric values and frame semantics cannot be loaded', () => {
  for (const value of [NaN,Infinity,true,'1',null,1001]) assert.equal(validAnchorPose({...pose,x:value}),false);
  assert.equal(validAnchorPose({...pose,yaw:361}),false);
  assert.equal(validAnchorPose({...pose,stamp_ns:'1'}),false);
  for (const values of [{...entry.values,pose_reference:'VERIFIED_BODY'},{...entry.values,units:'radians'},
    {...entry.values,saved_at:'bad'}]) assert.equal(compatibleAnchorPreset({...entry,values},map),false);
});
