import test from 'node:test';
import assert from 'node:assert/strict';
import { LiveMapObservation, inverseRigid, rpyMatrix } from '../robot_dashboard/static/features/maps/live_observation_contract.js';
import { identity, multiply, transformPoints } from '../robot_dashboard/static/features/experiments/recorded_report.js';

const stamp = 1792309179130175352n;
const map = { id: 'a'.repeat(24), revision: 'b'.repeat(64), kind: 'pointcloud3d' };
const guess = { x: 1, y: 2, z: .3, roll: .1, pitch: -.2, yaw: .3 };
function observation(seq, epoch = 'c', received = 10 + seq / 100) {
  return { observer_id: 'd'.repeat(32), publisher_epoch: epoch.repeat(32), publisher_gid: epoch.repeat(32),
    publisher_count: 1, identity_status: 'OBSERVED_PUBLISHER', source_stamp_ns: String(stamp + BigInt(seq)),
    received_monotonic_s: received, receipt_clock: 'OBSERVER_HOST_MONOTONIC' };
}
function pose(seq = 1, changes = {}) {
  return { topic: '/odom', frame_id: 'odom', child_frame_id: 'base_link', seq, state: 'ok', age_s: 0,
    position: { x: 2, y: 3, z: .5 }, orientation: { x: 0, y: 0, z: Math.SQRT1_2, w: Math.SQRT1_2 },
    observation: observation(seq, 'f'), ...changes };
}
function cloud(seq = 1, changes = {}) {
  return { topic: '/cloud_registered', pipeline_stage: 'registered', frame_id: 'odom', units: 'm', seq,
    points: new Float32Array([1, 2, 3, 4, 5, 6]), observation: observation(seq), ...changes };
}
function setup({ raw = false } = {}) {
  let now = 0; const model = new LiveMapObservation(() => now);
  model.enable(true); model.setMap(map, { revision: map.revision, frame_id: 'map', points: [1, 2, 3] });
  const c = cloud(1, raw ? { topic: '/velodyne_points', pipeline_stage: 'converted', frame_id: 'hesai_lidar',
    robot_pose_in_frame: { x: 0, y: .25, z: 0, roll: 0, pitch: 0, yaw: -Math.PI / 2,
      frame_id: 'hesai_lidar', source: 'configured_sensor_extrinsic' } } : {});
  model.ingestPose(pose()); model.ingestCloud(c); model.setAnchor(guess, true);
  return { model, c, setNow: v => { now = v; } };
}
function result(model, changes = {}) {
  const body = model.alignmentRequest();
  return { schema: 'robot-scope.observation-alignment.v1', experimental: true, operational_application: 'NOT_RUN',
    map_id: map.id, map_revision: map.revision, target_frame: 'map',
    source: { ...body, received_monotonic_s: model.cloud.value.observation.received_monotonic_s },
    status: 'CANDIDATE', reason: 'CANDIDATE', T_map_odom: model.anchor.T_map_odom, correspondence_gate_m: .75,
    metrics: { converged: true, rmse_m: .02, overlap_ratio: .8, geometry_min_max_eigen_ratio: .2, matched_geometry_min_max_eigen_ratio: .2 }, ...changes };
}
function close(a, b) { assert.ok(Math.abs(a - b) < 1e-8, `${a} != ${b}`); }

test('registered scan transforms once; raw scan composes inverse sensor extrinsic with noncommuting odom', () => {
  for (const raw of [false, true]) {
    const { model, c } = setup({ raw });
    const s = model.snapshot();
    for (const k of ['x','y','z','roll','pitch','yaw']) close(s.pose[k], guess[k]);
    let matrix = model.anchor.T_map_odom;
    if (raw) matrix = multiply(matrix, multiply(model.pose.matrix, inverseRigid(rpyMatrix(c.robot_pose_in_frame))));
    const expected = transformPoints([[1, 2, 3], [4, 5, 6]], matrix);
    s.points.flat().forEach((v, i) => close(v, expected.flat()[i]));
    assert.equal(model.exportRecord().samples[0].source_stamp_ns, String(stamp + 1n));
    assert.equal(s.absolute_accuracy_m, null); assert.equal(s.body_pose_verified, false);
  }
});

test('closer receipt-paired pose rebuilds same raw cloud geometry', () => {
  const { model } = setup({ raw: true });
  model.cloud.value.observation.received_monotonic_s += .05;
  const before = model.snapshot();
  model.ingestPose(pose(2, { position: { x: 2.1, y: 3, z: .5 }, observation: observation(2, 'f', 10.06) }));
  const after = model.snapshot();
  assert.notEqual(before.geometryKey, after.geometryKey); assert.notDeepEqual(before.points, after.points);
});

test('source epoch, map revision, reversal and jump clear candidate and exported old samples', () => {
  const mutations = [
    m => m.ingestCloud(cloud(2, { observation: observation(2, 'e') })),
    m => m.ingestPose(pose(2, { observation: observation(2, 'e') })),
    m => m.setMap({ ...map, revision: 'e'.repeat(64) }, { points: [1,2,3], revision: 'e'.repeat(64), frame_id: 'map' }),
    m => m.ingestPose(pose(2, { observation: { ...observation(2, 'f'), source_stamp_ns: '1' } })),
    m => m.ingestPose(pose(2, { position: { x: 10, y: 3, z: .5 } })),
  ];
  for (const mutate of mutations) {
    const { model } = setup(); model.snapshot(); mutate(model);
    assert.equal(model.snapshot().pose, null); assert.equal(model.anchor, null);
    assert.deepEqual(model.exportRecord().samples, []);
  }
});

test('stale pose uses backend age plus browser elapsed and duplicates do not refresh input', () => {
  const { model, setNow } = setup();
  model.ingestPose(pose(2, { age_s: .9 })); setNow(101);
  assert.equal(model.snapshot().status, 'STALE'); assert.equal(model.anchor, null);
  const second = setup(); second.setNow(1001); second.model.ingestPose(pose()); second.model.ingestCloud(cloud());
  assert.equal(second.model.snapshot().pose, null);
});

test('q and minus q match, unknown stage/body frame and skew fail closed', () => {
  const { model } = setup();
  model.ingestPose(pose(2, { orientation: { x: 0, y: 0, z: -Math.SQRT1_2, w: -Math.SQRT1_2 } }));
  assert.ok(model.snapshot().pose);
  for (const mutate of [
    m => m.ingestCloud(cloud(2, { pipeline_stage: 'map' })),
    m => m.ingestPose(pose(2, { child_frame_id: 'camera' })),
    m => m.ingestCloud(cloud(2, { observation: observation(2, 'c', 20) })),
    m => m.ingestCloud(cloud(2, { seq: NaN })),
  ]) {
    const f = setup(); mutate(f.model); assert.equal(f.model.snapshot().pose, null);
  }
});

test('reset removes all cached input; explicit anchor is required after source recovery', () => {
  const { model } = setup(); model.snapshot(); model.resetInputs('TARGET_CHANGED');
  assert.equal(model.pose, null); assert.equal(model.cloud, null); assert.deepEqual(model.history, []);
  assert.throws(() => model.setAnchor(guess, true));
  model.ingestPose(pose(2)); model.ingestCloud(cloud(2));
  assert.equal(model.snapshot().pose, null); model.setAnchor(guess, true); assert.ok(model.snapshot().pose);
});

test('registration corrections start separate trail segment; rejected and late results never stay current', () => {
  const { model } = setup(); model.snapshot(); model.registrationEnabled = true;
  const generation = model.generation;
  assert.equal(model.applyAlignment(result(model), generation), true);
  assert.deepEqual(model.samples, []); assert.deepEqual(model.trail, []);
  assert.equal(model.snapshot().status, 'SCAN_TO_MAP_CANDIDATE_UNVERIFIED');
  assert.equal(model.snapshot().map_registration, 'CANDIDATE');
  model.applyAlignment(result(model, { status: 'REJECTED', reason: 'HIGH_RESIDUAL' }), generation);
  assert.equal(model.snapshot().pose, null); assert.match(model.snapshot().status, /REJECTED/);
  const late = result(model); model.setAnchor(guess, true);
  assert.equal(model.registration, null); assert.match(model.snapshot().status, /WAITING/);
  assert.equal(model.applyAlignment(late, generation), false); model.alignmentFailed('old', generation);
  assert.equal(model.registration, null);
});

test('result latency does not become a new freshness window and correction checks displayed body jump', () => {
  const { model, setNow } = setup(); model.registrationEnabled = true; const value = result(model);
  setNow(1001); model.ingestPose(pose(2)); model.ingestCloud(cloud(2));
  assert.equal(model.applyAlignment(value, model.generation, 0), false); assert.equal(model.registration.reason, 'RESULT_STALE');
  const f = setup(); f.model.ingestPose(pose(2, { position: { x: 100, y: 0, z: 0 }, orientation: { x:0,y:0,z:0,w:1 } }));
  f.model.setAnchor({ x:100,y:0,z:0,roll:0,pitch:0,yaw:0 }, true); f.model.registrationEnabled = true;
  const rotated = rpyMatrix({ x:0,y:0,z:0,roll:0,pitch:0,yaw:.05 });
  assert.equal(f.model.applyAlignment(result(f.model, { T_map_odom: rotated }), f.model.generation), false);
  assert.equal(f.model.reason, 'ALIGNMENT_JUMP');
});
