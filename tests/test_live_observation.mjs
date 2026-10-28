import test from 'node:test';
import assert from 'node:assert/strict';
import { LiveMapObservation, ObservationSourcePreference, inverseRigid, rpyMatrix } from '../robot_dashboard/static/features/maps/live_observation_contract.js';
import { observationAvailabilityText, observationRegistrationText, observationTelemetryText } from '../robot_dashboard/static/features/maps/live_observation.js';
import { identity, multiply, transformPoints } from '../robot_dashboard/static/features/experiments/recorded_report.js';

const stamp = 1792309179130175352n;
const map = { id: 'a'.repeat(24), revision: 'b'.repeat(64), kind: 'pointcloud3d' };
const guess = { x: 1, y: 2, z: .3, roll: .1, pitch: -.2, yaw: .3 };

test('Maps distinguishes an unavailable server link from server-reported robot telemetry loss', () => {
  const disconnected = observationAvailabilityText({ status: 'AGENT_CONNECTION_LOST' });
  assert.match(disconnected, /대시보드 연결이 끊겨/);
  assert.match(disconnected, /LiDAR·pose 수신 상태를 확인할 수 없습니다/);
  assert.doesNotMatch(disconnected, /로봇.*변경|센서.*고장/);
  assert.match(observationAvailabilityText({ status: 'ROBOT_TELEMETRY_UNAVAILABLE' }), /서버가 로봇 관측 불가/);
  assert.equal(observationAvailabilityText({ status: 'STALE' }), '', 'data staleness retains its existing warning');
});
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
function unavailable(value) {
  return { ...value, observation: { ...value.observation, publisher_gid: null, identity_status: 'UNAVAILABLE' } };
}
function subscription(value, kind, {session = '1'.repeat(32), fingerprint = '2'.repeat(64), graphAge = .1} = {}) {
  const type = kind === 'pose' ? 'nav_msgs/msg/Odometry' : 'sensor_msgs/msg/PointCloud2';
  const qos = { reliability: 'BEST_EFFORT', durability: 'VOLATILE', history: 'KEEP_LAST', depth: 1 };
  value = unavailable(value);
  return { ...value, observation: { ...value.observation, subscription_evidence: {
    schema: 'robot-scope.subscription-observation.v1', session_id: session, topic: value.topic, type_name: type,
    subscription_qos: qos, per_message_publisher_verified: false, identity_basis: 'LOCAL_SUBSCRIPTION_AND_ROS_GRAPH_ONLY',
    graph: { state: 'ok', observed_monotonic_s: value.observation.received_monotonic_s - graphAge,
      endpoint_count: 1, reported_publisher_count: 1, fingerprint,
      endpoints: [{ node_name: 'synthetic', node_namespace: '/', topic_type: type, endpoint_gid: '3'.repeat(48), qos }] },
  } } };
}
function setupSubscription() {
  const fixture = setup(), { model } = fixture;
  model.setProvenanceMode('subscription_observation');
  model.ingestPose(subscription(pose(2), 'pose')); model.ingestCloud(subscription(cloud(2), 'cloud'));
  model.setAnchor(guess, true);
  return fixture;
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
  const fallback = body.provenance_mode === 'subscription_observation';
  const provenance = fallback ? { provenance_mode: 'subscription_observation', per_message_publisher_verified: false, body_extrinsic_verified: false } : {};
  return { schema: 'robot-scope.observation-alignment.v1', experimental: true, operational_application: 'NOT_RUN',
    map_id: map.id, map_revision: map.revision, target_frame: 'map',
    ...provenance, ...(fallback ? { body_pose_verified: false } : {}),
    source: { ...body, ...provenance, received_monotonic_s: model.cloud.value.observation.received_monotonic_s },
    status: fallback ? 'CANDIDATE_SOURCE_UNVERIFIED' : 'CANDIDATE', reason: fallback ? 'CANDIDATE_SOURCE_UNVERIFIED' : 'CANDIDATE', T_map_odom: model.anchor.T_map_odom, correspondence_gate_m: .75,
    metrics: { converged: true, rmse_m: .02, overlap_ratio: .8, geometry_min_max_eigen_ratio: .2, matched_geometry_min_max_eigen_ratio: .2 }, ...changes };
}
function provisionalResult(model, rmse = .07) {
  const originalPolicy = { policy_id: 'robot-scope.residual-policy.original-0.05m.v1',
    source_policy_id: 'robot-scope.residual-policy.original-0.05m.v1', max_rmse_m: .05,
    provisional: false, qualifier: 'ORIGINAL_RESIDUAL_ONLY', original_max_rmse_m: .05,
    unit: 'm', evaluation_scope: 'STORED_RMSE_ONLY', observation_only: true, no_accuracy_claim: true, accuracy_verified: false };
  return result(model, { provisional: true, candidate_kind: 'PROVISIONAL_OBSERVATION_HYPOTHESIS',
    body_pose: null, body_pose_verified: false, body_extrinsic_verified: false, tracking_verified: false, absolute_accuracy_m: null,
    query_points: 100, gate_reasons: [],
    metrics: { converged: true, rmse_m: rmse, overlap_ratio: .8, inlier_count: 80,
      geometry_min_max_eigen_ratio: .2, matched_geometry_min_max_eigen_ratio: .2 },
    original_assessment: { status: rmse <= .05 ? 'CANDIDATE' : 'REJECTED', reason: rmse <= .05 ? 'CANDIDATE' : 'HIGH_RESIDUAL', max_rmse_m: .05 },
    residual_evaluation: { rmse_m: rmse, residual_passed: rmse <= .10, original_residual_passed: rmse <= .05,
      policy: { ...originalPolicy, policy_id: 'robot-scope.residual-policy.provisional-0.10m.v1', max_rmse_m: .10,
        provisional: true, qualifier: 'PROVISIONAL_RESIDUAL_ONLY' }, original_policy: originalPolicy,
      overall_candidate_acceptance_evaluated: false, overall_candidate_accepted: null },
  });
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

test('same map identity retains the accepted correction and moving trail across catalogue metadata refresh', () => {
  const { model, setNow } = setup();
  model.registrationEnabled = true;
  assert.equal(model.applyAlignment(result(model), model.generation), true);
  model.snapshot();
  setNow(300);
  model.ingestPose(pose(2, { position: { x: 2.2, y: 3, z: .5 } }));
  model.ingestCloud(cloud(2));
  const before = model.snapshot(), generation = model.generation;
  const anchor = model.anchor, registration = model.registration;
  const samples = structuredClone(model.exportRecord().samples);
  assert.ok(before.trail.length > 1);
  const updated = { ...map, name: 'Updated catalogue label', point_count: 41073, modified_at: '2026-10-23T08:00:00Z' };
  model.setMap(updated, { revision: map.revision, frame_id: 'map', points: [1, 2, 3] });
  const after = model.snapshot();
  assert.equal(model.generation, generation);
  assert.equal(model.anchor, anchor); assert.equal(model.registration, registration);
  assert.deepEqual(after.pose, before.pose); assert.deepEqual(after.trail, before.trail);
  assert.deepEqual(model.exportRecord().samples, samples);
  assert.equal(after.map.name, updated.name); assert.equal(after.map.point_count, updated.point_count);
  assert.equal(after.map.saved_at, updated.modified_at);
  assert.equal(after.status, 'SCAN_TO_MAP_CANDIDATE_UNVERIFIED');
});

test('changed map identity, frame or unavailable reference still clears the connection', () => {
  const loaded = { revision: map.revision, frame_id: 'map', points: [1, 2, 3] };
  for (const [meta, reference] of [
    [{ ...map, id: 'e'.repeat(24) }, loaded],
    [{ ...map, revision: 'e'.repeat(64) }, { ...loaded, revision: 'e'.repeat(64) }],
    [map, { ...loaded, frame_id: 'other-map-frame' }],
    [map, { ...loaded, revision: 'e'.repeat(64) }],
    [map, { ...loaded, demo_snapshot: true }],
    [map, { ...loaded, points: [] }], [map, null], [null, loaded],
  ]) {
    const { model } = setup(); model.snapshot();
    const generation = model.generation;
    model.setMap(meta, reference);
    assert.ok(model.generation > generation); assert.equal(model.anchor, null);
    assert.equal(model.snapshot().pose, null);
    assert.deepEqual(model.exportRecord().samples, []); assert.deepEqual(model.trail, []);
  }
});

test('stale pose uses backend age plus browser elapsed and duplicates do not refresh input', () => {
  const { model, setNow } = setup();
  model.ingestPose(pose(2, { age_s: .9 })); setNow(101);
  assert.equal(model.snapshot().status, 'STALE'); assert.equal(model.anchor, null);
  const second = setup(); second.setNow(1001); second.model.ingestPose(pose()); second.model.ingestCloud(cloud());
  assert.equal(second.model.snapshot().pose, null);
});

test('a delayed cloud cannot display an old paired pose while the latest pose is fresh', () => {
  for (const raw of [false, true]) {
    const { model, c, setNow } = setup({ raw });
    model.snapshot(); setNow(1100);
    model.ingestPose(pose(2, { observation: observation(2, 'f', 11.2) }));
    model.ingestCloud({ ...c, seq: 2, observation: observation(2, 'c', 10.02) });
    assert.equal(model.pair().paired.value.seq, 1);
    assert.equal(model.pose.value.seq, 2);
    assert.throws(() => model.alignmentRequest(), /STALE/);
    const state = model.snapshot();
    assert.equal(state.status, 'STALE'); assert.equal(state.pose, null); assert.equal(state.points, null);
    assert.equal(model.anchor, null); assert.deepEqual(model.samples, []); assert.deepEqual(model.trail, []);
  }
  const { model, c, setNow } = setup();
  model.pose.value.age_s = .9; setNow(101);
  model.ingestPose(pose(2, { observation: observation(2, 'f', 10.14) }));
  model.ingestCloud({ ...c, seq: 2, observation: observation(2, 'c', 10.02) });
  assert.equal(model.snapshot().status, 'STALE');
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

test('missing per-message publisher identity keeps only raw receipt metadata and blocks all geometry', () => {
  const { model } = setup();
  model.snapshot();
  model.ingestPose(unavailable(pose(2))); model.ingestCloud(unavailable(cloud(2)));
  const state = model.snapshot();
  assert.equal(state.status, 'SOURCE_IDENTITY_UNAVAILABLE');
  assert.equal(model.pose, null); assert.equal(model.cloud, null); assert.equal(model.anchor, null);
  assert.equal(state.pose, null); assert.equal(state.points, null); assert.equal(state.body_pose_verified, false);
  assert.equal(Boolean(state.canAnchor), false); assert.equal(state.map_registration, 'NOT_RUN');
  assert.deepEqual(model.samples, []); assert.deepEqual(model.trail, []);
  assert.throws(() => model.setAnchor(guess, true), /SOURCE_IDENTITY_UNAVAILABLE/);
  assert.throws(() => model.alignmentRequest(), /SOURCE_IDENTITY_UNAVAILABLE/);
  assert.equal(state.telemetry.pose.topic, '/odom'); assert.equal(state.telemetry.pose.frame_id, 'odom');
  assert.equal(state.telemetry.pose.child_frame_id, 'base_link');
  assert.equal(state.telemetry.cloud.topic, '/cloud_registered'); assert.equal(state.telemetry.cloud.point_count, 2);
  for (const kind of ['pose', 'cloud']) {
    const summary = state.telemetry[kind];
    assert.equal(summary.seq, 2); assert.equal(summary.source_stamp_ns, String(stamp + 2n));
    assert.equal(summary.publisher_gid_present, false); assert.equal(summary.freshness, 'RECEIVED');
    assert.equal(summary.identity_status, 'UNAVAILABLE');
    for (const value of [summary, model.telemetrySummary[kind]]) {
      assert.equal(Object.values(value).some(item => item && typeof item === 'object'), false);
      for (const key of ['points', 'position', 'orientation', 'matrix', 'T_map_odom', 'publisher_gid']) assert.equal(key in value, false);
    }
  }
});

test('raw telemetry freshness uses original receipt and server pose age even when identity fails', () => {
  const { model, setNow } = setup();
  model.ingestPose(unavailable(pose(2, { age_s: .9 }))); model.ingestCloud(unavailable(cloud(2)));
  setNow(101);
  assert.equal(model.snapshot().telemetry.pose.freshness, 'STALE');
  assert.equal(model.snapshot().telemetry.cloud.freshness, 'RECEIVED');
  setNow(1001); model.ingestPose(unavailable(pose(2))); model.ingestCloud(unavailable(cloud(2)));
  const state = model.snapshot();
  assert.equal(state.status, 'SOURCE_IDENTITY_UNAVAILABLE');
  assert.equal(state.telemetry.pose.freshness, 'STALE'); assert.equal(state.telemetry.pose.age_ms, 1901);
  assert.equal(state.telemetry.cloud.freshness, 'STALE'); assert.equal(state.telemetry.cloud.age_ms, 1001);
});

test('cached or older samples cannot revive diagnostics after clear, source change or disable', () => {
  for (const clear of [m => m.invalidate('CLEARED'), m => m.resetInputs('TARGET_CHANGED'), m => { m.enable(false); m.enable(true); }]) {
    const { model, setNow } = setup();
    model.ingestPose(unavailable(pose(2))); model.ingestCloud(unavailable(cloud(2)));
    setNow(2000); clear(model);
    model.ingestPose(unavailable(pose(2))); model.ingestCloud(unavailable(cloud(2)));
    assert.deepEqual(model.snapshot().telemetry, { pose: null, cloud: null });
    model.ingestPose(unavailable(pose(3))); model.ingestCloud(unavailable(cloud(3)));
    assert.equal(model.snapshot().telemetry.cloud.freshness, 'RECEIVED');
  }
  const { model, setNow } = setup();
  model.ingestPose(unavailable(pose(3))); model.ingestCloud(unavailable(cloud(3)));
  setNow(100); model.ingestCloud(unavailable(cloud(2)));
  assert.equal(model.snapshot().telemetry.cloud.seq, 3);
  assert.equal(model.snapshot().telemetry.cloud.source_stamp_ns, String(stamp + 3n));
  model.ingestCloud(unavailable(cloud(4, { observation: observation(4, 'e') })));
  model.ingestPose(unavailable(pose(3)));
  assert.equal(model.snapshot().telemetry.pose, null);
  model.ingestCloud(unavailable(cloud(4, { observation: { ...observation(4, 'e'), invalidated: true } })));
  assert.equal(model.snapshot().telemetry.cloud.freshness, 'INVALIDATED');
});

test('diagnostic source replacement, reset, map change and disable discard previous summaries', () => {
  const changes = [
    { topic: '/replacement' }, { frame_id: 'replacement' },
    { observation: { ...observation(3, 'e'), publisher_gid: null, identity_status: 'UNAVAILABLE' } },
  ];
  for (const change of changes) {
    const { model } = setup();
    model.ingestPose(unavailable(pose(2))); model.ingestCloud(unavailable(cloud(2)));
    model.ingestCloud(unavailable(cloud(3, change)));
    assert.equal(model.snapshot().telemetry.pose, null); assert.equal(model.snapshot().telemetry.cloud.seq, 3);
    assert.equal(model.snapshot().pose, null);
  }
  for (const clear of [
    m => m.invalidate('CLEARED'), m => m.resetInputs('TARGET_CHANGED'), m => m.enable(false),
    m => m.setMap({ ...map, revision: 'e'.repeat(64) }, { points: [1,2,3], revision: 'e'.repeat(64), frame_id: 'map' }),
  ]) {
    const { model } = setup();
    model.ingestPose(unavailable(pose(2))); model.ingestCloud(unavailable(cloud(2)));
    clear(model); assert.deepEqual(model.snapshot().telemetry, { pose: null, cloud: null });
  }
  const { model } = setup(); model.ingestPose(unavailable(pose(2))); model.ingestCloud(unavailable(cloud(2)));
  model.resetInputs('CLEARED'); model.ingestPose(pose(3)); model.ingestCloud(cloud(3));
  assert.equal(model.snapshot().pose, null); assert.equal(model.snapshot().canAnchor, true);
});

test('subscription observation requires explicit mode, fresh graph evidence and a new approximate anchor', () => {
  const { model } = setup();
  assert.equal(model.provenanceMode, 'native_publisher');
  model.ingestPose(subscription(pose(2), 'pose')); model.ingestCloud(subscription(cloud(2), 'cloud'));
  assert.equal(model.snapshot().status, 'SOURCE_IDENTITY_UNAVAILABLE');
  assert.equal(model.snapshot().pose, null); assert.throws(() => model.alignmentRequest(), /SOURCE_IDENTITY_UNAVAILABLE/);
  model.setProvenanceMode('subscription_observation');
  assert.equal(model.anchor, null); assert.equal(model.pose, null); assert.equal(model.cloud, null);
  model.ingestPose(subscription(pose(3), 'pose')); model.ingestCloud(subscription(cloud(3), 'cloud'));
  assert.equal(model.snapshot().canAnchor, true); assert.equal(model.snapshot().pose, null);
  assert.throws(() => model.setAnchor(guess, false), /CONFIRMATION_REQUIRED/);
  model.setAnchor(guess, true);
  const state = model.snapshot();
  assert.equal(state.status, 'ODOMETRY_PROPAGATED_SOURCE_UNVERIFIED'); assert.ok(state.pose); assert.ok(state.points);
  assert.equal(state.map_registration, 'NOT_RUN'); assert.equal(state.per_message_publisher_verified, false);
  assert.equal(state.body_pose_verified, false); assert.equal(state.body_extrinsic_verified, false);
  assert.equal(model.alignmentRequest().provenance_mode, 'subscription_observation');
  assert.equal(model.exportRecord().per_message_publisher_verified, false);
  model.setProvenanceMode('native_publisher');
  assert.equal(model.anchor, null); assert.equal(model.registration, null); assert.deepEqual(model.samples, []);
  assert.deepEqual(model.trail, []); assert.deepEqual(model.snapshot().telemetry, { pose: null, cloud: null });
  model.ingestPose(subscription(pose(4), 'pose')); model.ingestCloud(subscription(cloud(4), 'cloud'));
  assert.equal(model.snapshot().pose, null); assert.throws(() => model.alignmentRequest(), /SOURCE_IDENTITY_UNAVAILABLE/);
});

test('subscription evidence fails closed for missing graph, nonunique endpoints, malformed QoS and stale graph', () => {
  const mutations = [
    e => { delete e.graph; }, e => { e.schema = 'unknown'; }, e => { e.session_id = ''; },
    e => { e.topic = '/other'; }, e => { e.type_name = 'other'; }, e => { e.subscription_qos = {}; }, e => { e.subscription_qos.reliability = 'UNKNOWN'; },
    e => { e.identity_basis = 'NATIVE_PUBLISHER'; }, e => { e.per_message_publisher_verified = true; },
    e => { e.graph.state = 'unavailable'; }, e => { e.graph.endpoint_count = 2; }, e => { e.graph.reported_publisher_count = 2; },
    e => { e.graph.endpoints = []; }, e => { e.graph.endpoints[0].qos = {}; },
    e => { e.graph.endpoints[0].endpoint_gid = '0'.repeat(48); }, e => { e.graph.endpoints[0].endpoint_gid = 'c'; },
    e => { e.graph.endpoints[0].node_namespace = ''; }, e => { e.graph.fingerprint = ''; },
    e => { e.graph.observed_monotonic_s -= 4; }, e => { e.graph.observed_monotonic_s += 1; },
  ];
  for (const mutate of mutations) {
    const { model } = setupSubscription(), value = subscription(cloud(3), 'cloud');
    mutate(value.observation.subscription_evidence); model.ingestCloud(value);
    assert.equal(model.anchor, null); assert.equal(model.snapshot().pose, null);
    assert.equal(model.snapshot().status, 'SOURCE_IDENTITY_UNAVAILABLE');
  }
  const { model, setNow } = setupSubscription();
  model.ingestPose(subscription(pose(3), 'pose', { graphAge: 2.9 }));
  model.ingestCloud(subscription(cloud(3), 'cloud', { graphAge: 2.9 }));
  setNow(101);
  assert.equal(model.snapshot().status, 'SUBSCRIPTION_GRAPH_STALE'); assert.equal(model.anchor, null);
});

test('subscription source changes clear candidates and mode switches fence late results', () => {
  for (const options of [{ session: '4'.repeat(32) }, { fingerprint: '5'.repeat(64) }]) {
    const { model } = setupSubscription(); model.registrationEnabled = true;
    const generation = model.generation, candidate = result(model);
    assert.equal(model.applyAlignment(candidate, generation), true); model.snapshot();
    model.ingestCloud(subscription(cloud(3), 'cloud', options));
    assert.equal(model.anchor, null); assert.equal(model.registration, null); assert.equal(model.snapshot().pose, null);
    assert.deepEqual(model.samples, []); assert.equal(model.applyAlignment(candidate, generation), false);
  }
  const { model } = setupSubscription(); model.registrationEnabled = true;
  const generation = model.generation, candidate = result(model);
  model.setProvenanceMode('native_publisher');
  model.ingestPose(pose(3)); model.ingestCloud(cloud(3)); model.setAnchor(guess, true); model.registrationEnabled = true;
  assert.equal(model.applyAlignment(candidate, generation), false); assert.equal(model.registration, null);
});

test('source replacement waits for a fresh counterpart receipt before reanchor', () => {
  for (const first of ['cloud', 'pose']) {
    const { model } = setupSubscription();
    const oldGeneration = model.generation;
    const changed = first === 'cloud'
      ? subscription(cloud(3), 'cloud', { session: '4'.repeat(32) })
      : subscription(pose(3), 'pose', { session: '4'.repeat(32) });
    const staleCounterpart = first === 'cloud'
      ? subscription(pose(3, { observation: observation(3, 'f', 10.02) }), 'pose')
      : subscription(cloud(3, { observation: observation(3, 'c', 10.02) }), 'cloud');
    const refreshedCounterpart = first === 'cloud'
      ? subscription(pose(4, { observation: observation(4, 'f', 10.04) }), 'pose')
      : subscription(cloud(4, { observation: observation(4, 'c', 10.04) }), 'cloud');
    const ingestCounterpart = first === 'cloud' ? value => model.ingestPose(value) : value => model.ingestCloud(value);
    first === 'cloud' ? model.ingestCloud(changed) : model.ingestPose(changed);
    assert.equal(model.anchor, null);
    assert.equal(model.snapshot().canAnchor, undefined);
    assert.throws(() => model.setAnchor(guess, true), /SOURCE_CHANGED/);
    ingestCounterpart(staleCounterpart);
    assert.equal(model.snapshot().canAnchor, undefined);
    assert.throws(() => model.setAnchor(guess, true), /SOURCE_CHANGED/);
    // Repeating the same seq with a later receipt cannot reopen a freshness window.
    const repeated = structuredClone(staleCounterpart);
    repeated.observation.received_monotonic_s = 10.04;
    repeated.observation.subscription_evidence.graph.observed_monotonic_s = 9.94;
    ingestCounterpart(repeated);
    assert.equal(model.snapshot().canAnchor, undefined);
    ingestCounterpart(refreshedCounterpart);
    assert.equal(model.snapshot().canAnchor, true);
    assert.equal(model.pair().paired.value.seq, first === 'cloud' ? 4 : 3);
    model.setAnchor(guess, true);
    assert.ok(model.snapshot().pose);
    assert.ok(model.generation > oldGeneration);
  }
});

test('staggered changes in both subscription streams need a second refresh', () => {
  const { model } = setupSubscription();
  model.ingestCloud(subscription(cloud(3), 'cloud', { session: '4'.repeat(32) }));
  assert.equal(model.snapshot().canAnchor, undefined);
  model.ingestPose(subscription(pose(3), 'pose', { session: '5'.repeat(32) }));
  assert.equal(model.snapshot().status, 'POSE_SOURCE_CHANGED');
  assert.equal(model.snapshot().canAnchor, undefined);
  model.ingestCloud(subscription(cloud(4), 'cloud', { session: '4'.repeat(32) }));
  assert.equal(model.snapshot().canAnchor, true);
  model.setAnchor(guess, true);
  assert.equal(model.snapshot().status, 'ODOMETRY_PROPAGATED_SOURCE_UNVERIFIED');
});

test('subscription candidates require explicit unverified result labels and all original numeric gates', () => {
  const { model, setNow } = setupSubscription(); model.registrationEnabled = true;
  assert.equal(model.applyAlignment(result(model), model.generation), true);
  assert.equal(model.snapshot().status, 'SCAN_TO_MAP_CANDIDATE_SOURCE_UNVERIFIED');
  assert.equal(model.snapshot().map_registration, 'CANDIDATE_SOURCE_UNVERIFIED');
  for (const mutate of [
    v => { v.status = 'CANDIDATE'; v.reason = 'CANDIDATE'; },
    v => { v.provenance_mode = 'native_publisher'; }, v => { delete v.source.provenance_mode; },
    v => { v.per_message_publisher_verified = true; }, v => { v.source.per_message_publisher_verified = true; },
    v => { v.body_pose_verified = true; }, v => { v.body_extrinsic_verified = true; }, v => { v.source.body_extrinsic_verified = true; },
    v => { v.metrics.rmse_m = .051; }, v => { v.metrics.overlap_ratio = .59; },
  ]) {
    const f = setupSubscription(); f.model.registrationEnabled = true; const value = result(f.model); mutate(value);
    assert.equal(f.model.applyAlignment(value, f.model.generation), false); assert.equal(f.model.snapshot().pose, null);
  }
  const stale = result(model); setNow(1001);
  model.ingestPose(subscription(pose(3), 'pose')); model.ingestCloud(subscription(cloud(3), 'cloud'));
  assert.equal(model.applyAlignment(stale, model.generation, 0), false); assert.equal(model.registration.reason, 'RESULT_STALE');
});

test('identity guidance distinguishes received raw data from unavailable map registration', () => {
  const { model } = setup(); model.ingestPose(unavailable(pose(2))); model.ingestCloud(unavailable(cloud(2)));
  const state = model.snapshot(), guidance = observationAvailabilityText(state), source = observationTelemetryText(state.telemetry);
  assert.match(guidance, /이 ROS runtime에서 메시지별 publisher 정보가 제공되지 않습니다/);
  assert.match(guidance, /원본 점군·native odometry 관측은 가능/); assert.match(guidance, /저장 지도 정합 계산은 사용할 수 없습니다/);
  assert.match(source, /점군: 원본 수신 · \/cloud_registered \[odom\] · seq 2 · 2점/);
  assert.match(source, /native odometry: 원본 수신 · \/odom \[odom → base_link\]/);
  assert.match(source, new RegExp(String(stamp + 2n))); assert.match(source, /검증된 본체 자세가 아닙니다/);
  assert.match(source, /센서→화면 전체 지연은 미측정/);
  assert.equal(observationAvailabilityText({ status: 'OFF', telemetry: state.telemetry }), '');
  assert.match(observationAvailabilityText({ status: 'SOURCE_IDENTITY_UNAVAILABLE' }), /publisher 유일성·시각·출처 정보/);
  model.invalidate('CLEARED');
  assert.match(observationTelemetryText(model.snapshot().telemetry), /점군: 현재 수신 요약 없음 \| native odometry: 현재 수신 요약 없음/);
  assert.doesNotMatch(observationTelemetryText(model.snapshot().telemetry), /\/cloud_registered|source 1792/);
});

test('explicit provisional policy permits 10cm boundary while preserving original 5cm assessment', () => {
  for (const prepare of [setup, setupSubscription]) for (const rmse of [.05, .07, .10]) {
    const { model } = prepare(); model.registrationEnabled = true;
    const value = provisionalResult(model, rmse);
    assert.equal(model.applyAlignment(value, model.generation), true);
    const state = model.snapshot(), exported = model.exportRecord();
    assert.ok(state.pose); assert.ok(state.points);
    assert.deepEqual(state.registration.original_assessment, value.original_assessment);
    assert.equal(state.registration.residual_evaluation.original_residual_passed, rmse <= .05);
    assert.equal(exported.map_registration.residual_evaluation.overall_candidate_acceptance_evaluated, false);
    assert.equal(exported.map_registration.residual_evaluation.overall_candidate_accepted, null);
    assert.equal(exported.body_pose, null); assert.equal(exported.tracking_verified, false);
    assert.equal(state.body_pose_verified, false); assert.equal(state.tracking_verified, false);
    assert.match(observationRegistrationText(state.registration), /잠정 10cm 잔차 통과/);
  }
  const { model } = setup(); model.registrationEnabled = true;
  const legacy = result(model); legacy.metrics.rmse_m = .07;
  assert.equal(model.applyAlignment(legacy, model.generation), false);
  assert.equal(model.registration.reason, 'RESULT_GATE_MISMATCH');
});

test('provisional residual boundary is direct and failed results keep scores and original reason', () => {
  const { model } = setup(); model.registrationEnabled = true;
  const value = provisionalResult(model, .10 + Number.EPSILON * .10);
  assert.equal(value.residual_evaluation.residual_passed, false);
  // A forged candidate above the exact threshold is rejected even when its
  // displayed decimal value would round to 0.10000 m.
  assert.equal(model.applyAlignment(value, model.generation), false);
  assert.equal(model.registration.reason, 'RESULT_GATE_MISMATCH');
  value.status = 'REJECTED'; value.reason = 'HIGH_RESIDUAL'; value.gate_reasons = ['HIGH_RESIDUAL'];
  assert.equal(model.applyAlignment(value, model.generation), false);
  assert.equal(model.registration.metrics.rmse_m, value.metrics.rmse_m);
  assert.equal(model.snapshot().pose, null);
  const text = observationRegistrationText(model.snapshot().registration);
  assert.match(text, /RMSE 0.10000 m/); assert.match(text, /잠정 10cm 잔차 미통과/);
  assert.match(text, /원본 5cm 잔차 미통과/); assert.match(text, /원본 판정 REJECTED \(HIGH_RESIDUAL\)/);
  assert.match(text, /정합 잔차≠실제 위치오차 · 본체\/추적 미검증/);
  const missing = provisionalResult(model); missing.status = 'REJECTED'; missing.reason = 'RESIDUAL_UNAVAILABLE';
  missing.gate_reasons = ['RESIDUAL_UNAVAILABLE']; missing.metrics.rmse_m = null; missing.residual_evaluation = null;
  assert.equal(model.applyAlignment(missing, model.generation), false);
  assert.equal(model.registration.reason, 'RESIDUAL_UNAVAILABLE');
  assert.match(observationRegistrationText(model.registration), /RMSE 미제공.*잠정 10cm 잔차 미평가/);
});

test('provisional metadata fails closed for altered identity, flags, values and partial policy', () => {
  const mutations = [
    v => { delete v.residual_evaluation; }, v => { v.residual_evaluation = null; },
    v => { v.residual_evaluation.policy.policy_id = 'unknown'; },
    v => { v.residual_evaluation.policy.source_policy_id = 'unknown'; },
    v => { v.residual_evaluation.policy.max_rmse_m = .20; },
    v => { v.residual_evaluation.policy.original_max_rmse_m = .10; },
    v => { v.residual_evaluation.policy.unit = 'cm'; },
    v => { v.residual_evaluation.policy.evaluation_scope = 'FULL_ACCEPTANCE'; },
    v => { v.residual_evaluation.policy.provisional = false; },
    v => { v.residual_evaluation.policy.qualifier = 'ORIGINAL_RESIDUAL_ONLY'; },
    v => { v.residual_evaluation.policy.observation_only = false; },
    v => { v.residual_evaluation.policy.no_accuracy_claim = false; },
    v => { v.residual_evaluation.policy.accuracy_verified = true; },
    v => { v.residual_evaluation.original_policy.max_rmse_m = .10; },
    v => { v.residual_evaluation.rmse_m = .05; },
    v => { v.residual_evaluation.residual_passed = false; },
    v => { v.residual_evaluation.original_residual_passed = true; },
    v => { v.residual_evaluation.overall_candidate_acceptance_evaluated = true; },
    v => { v.residual_evaluation.overall_candidate_accepted = true; },
    v => { v.provisional = false; }, v => { v.candidate_kind = 'BODY_POSE'; },
    v => { v.tracking_verified = true; }, v => { v.body_pose = {}; },
    v => { v.body_pose_verified = true; }, v => { v.body_extrinsic_verified = true; },
    v => { v.absolute_accuracy_m = .10; }, v => { v.original_assessment.max_rmse_m = .10; },
    v => { v.original_assessment.status = 'CANDIDATE'; v.original_assessment.reason = 'CANDIDATE'; },
    v => { v.original_assessment.reason = 'NOT_CONVERGED'; },
    v => { v.gate_reasons = ['NOT_CONVERGED']; }, v => { v.gate_reasons = null; },
  ];
  for (const mutate of mutations) {
    const { model } = setup(); model.registrationEnabled = true;
    const originalAnchor = model.anchor.T_map_odom, value = provisionalResult(model); mutate(value);
    assert.equal(model.applyAlignment(value, model.generation), false);
    assert.equal(model.registration.reason, 'RESULT_POLICY_MISMATCH');
    assert.equal(model.snapshot().pose, null); assert.equal(model.anchor.T_map_odom, originalAnchor);
  }
});

test('provisional residual pass cannot bypass nonresidual numeric gates', () => {
  for (const mutate of [
    v => { v.metrics.converged = false; }, v => { v.metrics.overlap_ratio = .59; },
    v => { v.metrics.geometry_min_max_eigen_ratio = .001; },
    v => { v.metrics.matched_geometry_min_max_eigen_ratio = .001; },
    v => { v.metrics.geometry_min_max_eigen_ratio = 1.1; },
    v => { v.metrics.inlier_count = 59; }, v => { v.metrics.inlier_count = 101; },
    v => { v.metrics.inlier_count = 60.5; }, v => { delete v.metrics.inlier_count; },
    v => { v.query_points = 59; }, v => { v.query_points = 513; },
    v => { v.correspondence_gate_m = .10; },
  ]) {
    const { model } = setup(); model.registrationEnabled = true;
    const value = provisionalResult(model); mutate(value);
    assert.equal(model.applyAlignment(value, model.generation), false);
    assert.equal(model.registration.reason, 'RESULT_GATE_MISMATCH');
    assert.equal(model.snapshot().pose, null);
  }
  const { model } = setup(); model.registrationEnabled = true;
  const rejected = provisionalResult(model); rejected.status = 'REJECTED'; rejected.reason = 'NOT_CONVERGED';
  rejected.metrics.converged = false; rejected.gate_reasons = ['NOT_CONVERGED'];
  // Original geometry can be the highest-priority original reason while the
  // separate 10cm residual passes. Keep that historical decision visible.
  rejected.original_assessment.reason = 'DEGENERATE_MATCHED_GEOMETRY';
  assert.equal(model.applyAlignment(rejected, model.generation), false);
  assert.equal(model.registration.reason, 'NOT_CONVERGED'); assert.equal(model.snapshot().pose, null);
  assert.match(observationRegistrationText(model.registration), /잠정 10cm 잔차 통과.*DEGENERATE_MATCHED_GEOMETRY/);
});

test('provisional results retain map, epoch, generation, timeout, freshness and jump fences', () => {
  for (const mutate of [
    v => { v.map_revision = 'e'.repeat(64); }, v => { v.source.cloud_epoch = 'e'.repeat(32); },
    v => { v.source.pose_epoch = 'e'.repeat(32); }, v => { v.source.observer_id = 'e'.repeat(32); },
  ]) {
    const { model } = setup(); model.registrationEnabled = true;
    const value = provisionalResult(model); mutate(value);
    assert.equal(model.applyAlignment(value, model.generation), false);
    assert.equal(model.registration.reason, 'RESULT_IDENTITY_MISMATCH');
  }
  const { model, setNow } = setup(); model.registrationEnabled = true;
  const value = provisionalResult(model), generation = model.generation;
  setNow(1001); model.ingestPose(pose(2)); model.ingestCloud(cloud(2));
  assert.equal(model.applyAlignment(value, generation, 0), false); assert.equal(model.registration.reason, 'RESULT_STALE');
  model.setAnchor(guess, true); model.registrationEnabled = true;
  assert.equal(model.applyAlignment(value, generation), false); assert.equal(model.registration, null);
  const fresh = provisionalResult(model); fresh.T_map_odom = fresh.T_map_odom.map(row => [...row]); fresh.T_map_odom[0][3] += 2;
  assert.equal(model.applyAlignment(fresh, model.generation), false); assert.equal(model.reason, 'ALIGNMENT_JUMP');
  const f = setup(); f.model.registrationEnabled = true;
  assert.equal(f.model.applyAlignment(provisionalResult(f.model), f.model.generation), true);
  f.setNow(1001); assert.equal(f.model.snapshot().pose, null); assert.equal(f.model.anchor, null); assert.equal(f.model.registration, null);
});

test('FAST-LIO continuous display uses independent fixed-frame points and current IMU pose', () => {
  let now = 0;
  const model = new LiveMapObservation(() => now);
  model.enable(true); model.setMap(map, {revision: map.revision, frame_id: 'camera_init', points: [1,2,3]});
  model.setContinuousEstimate(true);
  const p = pose(1, {topic: '/Odometry', frame_id: 'camera_init', child_frame_id: 'body'});
  model.ingestPose(p); model.ingestCloud(cloud(1, {frame_id: 'camera_init'}));
  model.setAnchor(guess, true);
  const initial = model.snapshot();
  assert.equal(initial.pose_reference, 'FASTLIO_IMU');
  assert.equal(initial.tracked_frame, 'body');
  assert.equal(initial.pair_method, 'REGISTERED_FRAME_INDEPENDENT_CURRENT_POSE');
  assert.equal(initial.body_pose, null);
  for (const k of ['x','y','z','roll','pitch','yaw']) close(initial.pose[k], guess[k]);
  model.registrationEnabled = true;
  model.alignmentFailed('HIGH_RESIDUAL', model.generation);
  model.ingestPose({...p, seq: 2, position: {...p.position, x: 2.1}, observation: observation(2, 'f')});
  const current = model.snapshot();
  assert.equal(current.status, 'SAME_START_ODOMETRY_ESTIMATE');
  assert.notEqual(current.pose.x, initial.pose.x);
  assert.equal(current.source_stamp_ns, String(stamp + 2n));
  // No cloud-time transform is needed for already registered fixed-frame points.
  model.ingestCloud(cloud(3, {frame_id: 'camera_init'}));
  assert.ok(model.snapshot().pose);
  assert.equal(model.snapshot().source_delta_ns, '-1');
  assert.deepEqual(model.pair().pointsToOdom, [[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]);
  model.continuousEstimate = false;
  assert.throws(() => model.pair(), /WAITING_PAIRED_POSE/);
  model.continuousEstimate = true;
  now = 1001;
  assert.equal(model.snapshot().pose, null);
  assert.equal(model.anchor, null);
});

test('explicit continuous estimate propagates a retained correction through fresh same-generation odometry only', () => {
  const {model, setNow} = setup();
  model.setContinuousEstimate(true); model.setAnchor(guess, true); model.registrationEnabled = true;
  assert.equal(model.applyAlignment(result(model), model.generation), true);
  assert.equal(model.snapshot().status, 'MAP_CORRECTED_ESTIMATE_ACCURACY_UNVERIFIED');
  model.alignmentFailed('NOT_CONVERGED', model.generation);
  assert.equal(model.snapshot().status, 'MAP_CORRECTION_UNAVAILABLE_ODOMETRY_CONTINUING');
  for (let seq = 2; seq <= 25; seq++) {
    setNow(seq * 100);
    model.ingestPose(pose(seq, {observation: observation(seq, 'f', 10 + seq / 10)}));
    model.ingestCloud(cloud(seq, {observation: observation(seq, 'c', 10 + seq / 10)}));
  }
  assert.ok(model.snapshot().pose);
  assert.equal(model.snapshot().source_stamp_ns, String(stamp + 25n));
  model.ingestPose(pose(26, {observation: observation(26, 'e', 12.6)}));
  assert.equal(model.snapshot().pose, null);
  assert.equal(model.anchor, null);
});

test('continuous estimate retains the existing map, stale-result and source-time fences', () => {
  const {model, setNow} = setup();
  model.setContinuousEstimate(true); model.setAnchor(guess, true); model.registrationEnabled = true;
  const historical = result(model), generation = model.generation;
  setNow(1001);
  model.ingestPose(pose(2)); model.ingestCloud(cloud(2));
  assert.equal(model.applyAlignment(historical, generation, 0), false);
  assert.equal(model.anchor.accepted_registration, false);
  model.setMap({...map, revision:'e'.repeat(64)}, {revision:'e'.repeat(64), frame_id:'map', points:[1,2,3]});
  assert.equal(model.snapshot().pose, null);
});

function imuConnection() {
  let now = 0;
  const model = new LiveMapObservation(() => now);
  model.enable(true);
  model.setMap(map, { revision: map.revision, frame_id: 'map', points: [1, 2, 3] });
  model.setProvenanceMode('subscription_observation'); model.setContinuousEstimate(true, { resumeSameSession: true });
  const p = (seq, changes = {}) => subscription(pose(seq, {
    topic: '/Odometry', frame_id: 'camera_init', child_frame_id: 'body', ...changes,
  }), 'pose');
  const c = (seq, changes = {}) => subscription(cloud(seq, { frame_id: 'camera_init', ...changes }), 'cloud');
  model.ingestPose(p(1)); model.ingestCloud(c(1)); model.setAnchor(guess, true);
  return { model, p, c, setNow: value => { now = value; } };
}

test('continuous IMU observation hides stale output and resumes only after both same-source inputs advance', () => {
  const { model, p, c, setNow } = imuConnection();
  model.registrationEnabled = true;
  const pending = result(model), oldGeneration = model.generation;
  assert.equal(model.applyAlignment(pending, oldGeneration), true);
  const transform = structuredClone(model.anchor.T_map_odom);
  model.snapshot(); setNow(1001);
  const stale = model.snapshot();
  assert.equal(stale.status, 'STALE'); assert.equal(stale.anchor, null);
  assert.equal(stale.pose, null); assert.equal(stale.points, null);
  assert.deepEqual(model.exportRecord().samples, []);
  assert.throws(() => model.alignmentRequest(), /STALE/);
  model.ingestPose(p(1)); model.ingestCloud(c(1));
  assert.equal(model.snapshot().pose, null);
  model.ingestPose(p(2, { position: { x: 2.2, y: 3, z: .5 } }));
  assert.equal(model.snapshot().pose, null);
  model.ingestCloud(c(2));
  const resumed = model.snapshot();
  assert.ok(resumed.pose); assert.equal(resumed.anchor, model.anchor);
  assert.deepEqual(model.anchor.T_map_odom, transform);
  assert.equal(resumed.status, 'RECOVERED_APPROXIMATE_ODOMETRY_ESTIMATE');
  assert.equal(model.anchor.accepted_registration, false);
  assert.equal(resumed.source_stamp_ns, String(stamp + 2n));
  assert.equal(resumed.trail.length, 1); // Do not draw across the unseen interval.
  assert.equal(model.exportRecord().samples.length, 1);
  assert.equal(model.applyAlignment(pending, oldGeneration, 0), false);
  assert.equal(model.registration, null); assert.equal(model.suspendedAnchor, null);
  assert.equal(model.applyAlignment(result(model), model.generation), true);
  assert.equal(model.snapshot().status, 'MAP_CORRECTED_ESTIMATE_ACCURACY_UNVERIFIED');
});

test('resume requires newer source stamps as well as newer sequence numbers', () => {
  const { model, p, c, setNow } = imuConnection();
  setNow(1001); model.snapshot();
  model.ingestPose(p(2, { observation: observation(1, 'f') }));
  model.ingestCloud(c(2, { observation: observation(1) }));
  assert.equal(model.snapshot().pose, null); assert.equal(model.anchor, null);
  model.ingestPose(p(3)); model.ingestCloud(c(3));
  assert.ok(model.snapshot().pose);
});

test('a suspended connection cannot survive source changes, reversal, jump, map change or explicit reset', () => {
  const mutations = [
    (m,p,c) => m.ingestPose(p(2, { observation: observation(2, 'e') })),
    (m,p,c) => m.ingestCloud(c(2, { observation: observation(2, 'e') })),
    (m,p,c) => m.ingestPose(p(2, { observation: { ...observation(2, 'f'), source_stamp_ns: '1' } })),
    (m,p,c) => m.ingestCloud(c(2, { observation: { ...observation(2), source_stamp_ns: '1' } })),
    (m,p) => m.ingestPose(p(2, { position: { x: 5, y: 3, z: .5 } })),
    m => m.setMap({ ...map, revision: 'e'.repeat(64) }, { revision: 'e'.repeat(64), frame_id: 'map', points: [1,2,3] }),
    m => m.invalidate('CLEARED'), m => m.resetInputs('VIEW_SUSPENDED'),
    m => m.setContinuousEstimate(false), m => m.enable(false),
    m => m.setProvenanceMode('native_publisher'),
  ];
  for (const mutate of mutations) {
    const { model, p, c, setNow } = imuConnection();
    setNow(1001); model.snapshot(); assert.ok(model.suspendedAnchor);
    mutate(model,p,c); assert.equal(model.suspendedAnchor, null);
    model.ingestPose(p(3)); model.ingestCloud(c(3));
    assert.equal(model.snapshot().pose, null); assert.equal(model.anchor, null);
  }
});

test('stale graph and explicit invalid sensor data discard a suspended connection', () => {
  for (const mutate of [
    (m,p) => m.ingestPose(p(2, { state: 'stale', age_s: 2 })),
    (m,p,c) => m.ingestCloud(c(2, { points: [] })),
    (m,p,c) => { const v=p(2); v.observation.subscription_evidence.graph.observed_monotonic_s-=4; m.ingestPose(v); },
  ]) {
    const { model, p, c, setNow } = imuConnection();
    setNow(1001); model.snapshot(); mutate(model,p,c);
    assert.equal(model.suspendedAnchor, null);
    model.ingestPose(p(3)); model.ingestCloud(c(3));
    assert.equal(model.snapshot().pose, null);
  }
});

test('default and non-IMU observation still require an explicit anchor after stale input', () => {
  for (const continuous of [false,true]) {
    const { model, setNow } = setup();
    model.setContinuousEstimate(continuous); model.setAnchor(guess,true);
    setNow(1001); model.snapshot();
    assert.equal(model.suspendedAnchor,null);
    model.ingestPose(pose(2)); model.ingestCloud(cloud(2));
    assert.equal(model.snapshot().pose,null);
  }
  const { model, p, c, setNow } = imuConnection();
  model.setContinuousEstimate(true); model.setAnchor(guess,true);
  setNow(1001); model.snapshot();
  assert.equal(model.suspendedAnchor,null);
  model.ingestPose(p(2)); model.ingestCloud(c(2));
  assert.equal(model.snapshot().pose,null);
});


test('relative height follows vertical odometry and survives map correction without claiming body pose', () => {
  const {model} = setup();
  model.ingestPose(pose(2, {position:{x:2,y:3,z:.38}})); model.ingestCloud(cloud(2));
  assert.ok(Math.abs(model.snapshot().relative_height_m + .12) < 1e-9);
  model.registrationEnabled = true;
  const transform = model.anchor.T_map_odom.map(row => row.slice()); transform[2][3] += .05;
  assert.equal(model.applyAlignment(result(model, {T_map_odom:transform}), model.generation), true);
  assert.ok(Math.abs(model.snapshot().relative_height_m + .12) < 1e-9, 'correction is not body motion');
  assert.equal(model.snapshot().body_pose, null); assert.equal(model.exportRecord().body_pose_verified, false);
  model.registrationEnabled = false; model.setAnchor(guess, true); assert.equal(model.snapshot().relative_height_m, 0);
  model.ingestPose(pose(3, {observation:observation(3,'e')}));
  assert.equal(model.snapshot().relative_height_m, undefined);
});

test('seed readiness does not flicker when sampled FAST-LIO stamps differ, but freshness still fences it', () => {
  let now=0; const model=new LiveMapObservation(()=>now);
  model.enable(true); model.setMap(map,{revision:map.revision,frame_id:'camera_init',points:[1,2,3]});
  model.ingestPose(pose(2,{topic:'/Odometry',frame_id:'camera_init',child_frame_id:'body'}));
  model.ingestCloud(cloud(1,{frame_id:'camera_init'}));
  assert.throws(()=>model.ready(),/WAITING_PAIRED_POSE/);
  assert.equal(model.canInitialize(),true);
  assert.equal(model.anchor,null);
  model.setAnchor(guess,true,{continuousEstimate:true});
  assert.ok(model.snapshot().pose);
  now=1001; assert.equal(model.canInitialize(),false); assert.equal(model.snapshot().pose,null);
  model.ingestPose(pose(3,{topic:'/Odometry',frame_id:'camera_init',child_frame_id:'body'}));
  assert.equal(model.snapshot().pose,null);
  model.ingestCloud(cloud(4,{frame_id:'camera_init'}));
  assert.ok(model.snapshot().pose);
  assert.equal(model.snapshot().status,'RECOVERED_APPROXIMATE_ODOMETRY_ESTIMATE');
  model.setMap({...map,revision:'e'.repeat(64)},{revision:'e'.repeat(64),frame_id:'camera_init',points:[1,2,3]});
  assert.equal(model.snapshot().pose,null);
});

test('fresh input after a lost default anchor asks for reconnection instead of retaining STALE', () => {
  const {model,setNow}=setup(); setNow(1001); assert.equal(model.snapshot().status,'STALE');
  model.ingestPose(pose(2));model.ingestCloud(cloud(2));
  assert.equal(model.snapshot().status,'ANCHOR_RECONNECT_REQUIRED');
  assert.equal(model.snapshot().pose,null);
  assert.match(observationAvailabilityText(model.snapshot()),/수신.*회복.*기준점/);
});


test('default source permission prefers native inputs and only falls back for absent message identity', () => {
  const preference = new ObservationSourcePreference();
  assert.equal(preference.select('pose', pose(), 'native_publisher', true), 'native_publisher');
  assert.equal(preference.select('cloud', cloud(), 'native_publisher', true), 'native_publisher');
  assert.equal(preference.select('pose', subscription(pose(2), 'pose'), 'native_publisher', true), 'subscription_observation');
  assert.equal(preference.select('cloud', subscription(cloud(2), 'cloud'), 'subscription_observation', true), 'subscription_observation');
  assert.equal(preference.select('pose', pose(3), 'subscription_observation', true), 'subscription_observation');
  assert.equal(preference.select('cloud', cloud(3), 'subscription_observation', true), 'native_publisher');
  for (const change of [
    o => { o.publisher_count = 2; },
    o => { o.invalidated = true; },
    o => { o.publisher_gid = 'a'.repeat(32); },
    o => { o.subscription_evidence.graph.endpoint_count = 2; },
    o => { o.subscription_evidence.graph.observed_monotonic_s -= 4; },
  ]) {
    preference.reset();
    const value = subscription(pose(4), 'pose'); change(value.observation);
    assert.equal(preference.select('pose', value, 'subscription_observation', true), 'native_publisher');
  }
  assert.equal(preference.select('pose', subscription(pose(5), 'pose'), 'subscription_observation', false), 'native_publisher');
});


test('late opposite-mode frames cannot erase the current source sequence fence', () => {
  const preference = new ObservationSourcePreference();
  assert.equal(preference.select('pose', pose(10), 'native_publisher', true), 'native_publisher');
  assert.equal(preference.select('pose', subscription(pose(9), 'pose'), 'native_publisher', true), null);
  const next = subscription(pose(11), 'pose');
  assert.equal(preference.select('pose', next, 'native_publisher', true), 'subscription_observation');
  assert.equal(preference.select('pose', pose(10), 'subscription_observation', true), null);
  const oldEpoch = subscription(pose(1), 'pose'); oldEpoch.observation.publisher_epoch = 'e'.repeat(32);
  assert.equal(preference.select('pose', oldEpoch, 'subscription_observation', true), null);
});


test('source preference forwards same-receipt invalidation and stale metadata without switching mode', () => {
  for (const mode of ['native_publisher','subscription_observation']) {
    for (const degrade of [p=>{p.observation.invalidated=true;},p=>{p.observation.publisher_count=2;},p=>{p.state='stale';},p=>{p.age_s=2;}]) {
      const preference=new ObservationSourcePreference(), model=new LiveMapObservation(()=>0);
      model.enable(true); model.setProvenanceMode(mode);
      const value=mode==='native_publisher'?pose(10):subscription(pose(10),'pose');
      preference.select('pose',value,mode,true); model.ingestPose(value);
      const next=structuredClone(value);degrade(next);
      assert.equal(preference.select('pose',next,mode,true),mode);
      model.ingestPose(next);assert.equal(model.pose,null);
    }
  }
});
