import test from 'node:test';
import assert from 'node:assert/strict';
import { LiveMapObservation, inverseRigid, rpyMatrix } from '../robot_dashboard/static/features/maps/live_observation_contract.js';
import { observationAvailabilityText, observationTelemetryText } from '../robot_dashboard/static/features/maps/live_observation.js';
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
