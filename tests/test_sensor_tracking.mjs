import test from 'node:test';
import assert from 'node:assert/strict';
import { SensorTrackingController, selectedGlobalObservation, validateSensorTrackingSnapshot } from '../robot_dashboard/static/features/maps/sensor_tracking_contract.js';
import { sensorTrackingStateText, sensorTrackingDetailText, sensorSceneReserved } from '../robot_dashboard/static/features/maps/sensor_tracking.js';

const T = [[1, 0, 0, 2], [0, 1, 0, 3], [0, 0, 1, 1], [0, 0, 0, 1]];
const meta = { id: 'a'.repeat(24), revision: 'b'.repeat(64), frame_id: 'map', kind: 'pointcloud3d' };
const map = { map_id: meta.id, map_revision: meta.revision, map_frame: 'map' };
const jobId = 'c'.repeat(24);
const policy = { schema: 'robot-scope.global-provisional-selection.v2',
  adapter: 'dashboard-v031-observation-no-rmse-gate-v1', original_max_rmse_m: .05,
  provisional_max_rmse_m: .10, rmse_thresholds_purpose: 'COMPARISON_ONLY',
  rmse_selection_gate_enabled: false, scoring: 'UNCHANGED_ORIGINAL_REFERENCE_POPULATION',
  scope: 'PROVISIONAL_OBSERVATION_ONLY', original_selection_replayed: false };
const globalRecord = () => ({ state: 'succeeded', worker_active: false, job_id: jobId, generation: 5,
  captured_context: { ...map }, historical_only: true, tracking_verified: false,
  result: { observation: { status: 'OBSERVATION_ONLY_UNVERIFIED', selection_policy: { ...policy },
    selected_candidate: 0, gate_reasons: [], candidates: [{ map_from_scan: T, gate_reasons: [],
      refinement_stationary: true, rmse_m: .144, overlap: .95 }] } } });
const safe = { globally_verified: false, body_pose: null, tracking_verified: false,
  source_clock_verified: false, body_extrinsic_verified: false, operational_application: 'NOT_RUN' };
const source = { topic: '/velodyne_points', frame_id: 'hesai_lidar', observer_id: 'observer',
  observer_epoch: 'epoch-1', source_stamp_ns: '1792309179130175352', received_monotonic_s: 123.4, age_s: .04 };
const snapshot = (changes = {}) => ({ schema: 'robot-scope.sensor-tracking.v1', state: 'SENSOR_CANDIDATE',
  reason: null, generation: 7, worker_active: true,
  source_global_job: { job_id: jobId, generation: 5, selected_candidate: 0 },
  map: { ...map, frame_id: 'map', source_sha256: 'd'.repeat(64), xyz_sha256: 'e'.repeat(64) },
  source, sensor_pose: { T_map_sensor: T, source_stamp_ns: source.source_stamp_ns,
    received_monotonic_s: source.received_monotonic_s, map_frame: 'map', source_frame: 'hesai_lidar',
    rmse_m: .144, overlap: .95 },
  trail: [{ source_stamp_ns: source.source_stamp_ns, received_monotonic_s: source.received_monotonic_s,
    T_map_sensor: T }], temporal_consistency_confirmed: true, ...safe, ...changes });
const reply = value => ({ ok: true, json: async () => value });
const model = (request, now = () => 100) => {
  const instance = new SensorTrackingController({ request, requestId: () => 'sensor-test-id', now });
  instance.setMap(meta, null); instance.setGlobalRecord(globalRecord()); return instance;
};

test('comparison-only global selection admits >10 cm for observation start when independent gates pass', () => {
  assert.equal(selectedGlobalObservation(globalRecord(), map)?.job_id, jobId);
  const rejected = globalRecord(); rejected.result.observation.gate_reasons = ['AMBIGUOUS_ALTERNATIVES'];
  assert.equal(selectedGlobalObservation(rejected, map), null);
  rejected.result.observation.gate_reasons = [];
  rejected.result.observation.candidates[0].refinement_stationary = false;
  assert.equal(selectedGlobalObservation(rejected, map), null);
  rejected.result.observation.candidates[0].refinement_stationary = true;
  rejected.result.observation.selection_policy.rmse_selection_gate_enabled = true;
  assert.equal(selectedGlobalObservation(rejected, map), null);
});

test('snapshot contract preserves sensor-only marker, frame, source stamp and body restrictions', () => {
  assert.equal(validateSensorTrackingSnapshot(snapshot(), map), true);
  assert.match(sensorTrackingStateText({ value: snapshot(), state: 'SENSOR_CANDIDATE', error: '' }), /본체 자세\/운영 추적 미검증/);
  assert.match(sensorTrackingDetailText({ value: snapshot() }), /14|0\.14400 m/);
  for (const changed of [{ body_pose: {} }, { tracking_verified: true },
    { map: { ...snapshot().map, frame_id: 'odom' } },
    { sensor_pose: { ...snapshot().sensor_pose, source_stamp_ns: '1' } },
    { source: { ...source, age_s: 1.2 } },
    { trail: [{ T_map_sensor: [[0, 0, 0, 0]] }] },
    { state: 'STALE' }]) assert.equal(validateSensorTrackingSnapshot(snapshot(changed), map), false);
  assert.equal(validateSensorTrackingSnapshot(snapshot({ state: 'STALE', sensor_pose: null,
    trail: [], source: null, temporal_consistency_confirmed: false }), map), true);
});

test('GET is read-only; explicit start sends only job identity and stop clears displayed candidate', async () => {
  const calls = [], queue = [snapshot({ state: 'WAITING_GLOBAL', source_global_job: null, map: null,
    source: null, sensor_pose: null, trail: [], temporal_consistency_confirmed: false }),
    snapshot({ state: 'INITIALIZING', source: null, sensor_pose: null, trail: [], temporal_consistency_confirmed: false }),
    snapshot(), snapshot({ state: 'STOPPED', source: null, sensor_pose: null,
      trail: [], temporal_consistency_confirmed: false })];
  const controller = model(async (path, options = {}) => { calls.push({ path, ...options }); return reply(queue.shift()); });
  await controller.poll(); assert.equal(calls[0].method, undefined);
  assert.equal(controller.snapshot().canStart, true);
  await controller.start();
  assert.deepEqual(JSON.parse(calls[1].body), { global_job_id: jobId, request_id: 'sensor-test-id' });
  await controller.poll(); assert.equal(controller.snapshot().state, 'SENSOR_CANDIDATE');
  await controller.stop(); assert.equal(controller.snapshot().state, 'STOPPED');
  assert.equal(calls[3].path, '/api/v1/observations/sensor-tracking/stop');
  controller.destroy();
});

test('client freshness countdown hides sensor and trail without waiting for another GET', async () => {
  let now = 100;
  const controller = model(async () => reply(snapshot()), () => now);
  await controller.poll(); assert.equal(controller.snapshot().value.sensor_pose.T_map_sensor, T);
  now = 100.90;
  assert.equal(controller.snapshot().state, 'SENSOR_CANDIDATE');
  now = 100.97;
  assert.equal(controller.snapshot().state, 'STALE');
  assert.equal(controller.snapshot().value.sensor_pose, null);
  assert.deepEqual(controller.snapshot().value.trail, []);
  controller.destroy();
});

test('generation, source epoch and source time reversal fail closed', async () => {
  let current = snapshot();
  const controller = model(async () => reply(current));
  await controller.poll(); assert.equal(controller.snapshot().state, 'SENSOR_CANDIDATE');
  current = snapshot({ generation: 6 }); await controller.poll();
  assert.equal(controller.snapshot().value, null);
  assert.equal(controller.snapshot().error, 'TRACKING_GENERATION_REVERSED');
  current = snapshot({ source: { ...source, observer_epoch: 'epoch-2' } }); await controller.poll();
  assert.equal(controller.snapshot().error, 'TRACKING_SOURCE_OR_TIME_REVERSED');
  current = snapshot({ source: { ...source, source_stamp_ns: '1792309179130175351' },
    sensor_pose: { ...snapshot().sensor_pose, source_stamp_ns: '1792309179130175351' } });
  await controller.poll(); assert.equal(controller.snapshot().error, 'TRACKING_SOURCE_OR_TIME_REVERSED');
  controller.destroy();
});

test('attempted tracking keeps the generic GO2 preview hidden after epoch and network errors until explicit stop succeeds', async () => {
  const inactive = state => snapshot({ state, source: null, sensor_pose: null,
    trail: [], temporal_consistency_confirmed: false });
  let current = inactive('INITIALIZING'), failRead = false, failStop = true;
  const controller = model(async (path, options = {}) => {
    if (path.endsWith('/stop')) {
      if (failStop) throw new Error('stop response lost');
      return reply(inactive('STOPPED'));
    }
    if (failRead && options.method !== 'POST') throw new Error('status unavailable');
    return reply(current);
  });
  await controller.start();
  assert.equal(controller.snapshot().previewSuppressed, true);
  current = snapshot(); await controller.poll();
  current = snapshot({ source: { ...source, observer_epoch: 'epoch-2' } });
  await controller.poll();
  assert.equal(controller.snapshot().error, 'TRACKING_SOURCE_OR_TIME_REVERSED');
  assert.equal(controller.snapshot().value, null);
  assert.equal(sensorSceneReserved(controller.snapshot(), controller.pending, controller.writing), true);
  failRead = true; await controller.poll();
  assert.equal(controller.snapshot().error, 'TRACKING_STATUS_UNAVAILABLE');
  assert.equal(sensorSceneReserved(controller.snapshot(), controller.pending, controller.writing), true);
  await controller.stop();
  assert.equal(controller.snapshot().error, 'STOP_RESULT_UNCERTAIN');
  assert.equal(controller.snapshot().previewSuppressed, true);
  assert.equal(sensorSceneReserved(controller.snapshot(), controller.pending, controller.writing), true);
  failStop = false; await controller.stop();
  assert.equal(controller.snapshot().state, 'STOPPED');
  assert.equal(controller.snapshot().previewSuppressed, false);
  assert.equal(sensorSceneReserved(controller.snapshot(), controller.pending, controller.writing), false);
  controller.destroy();
});

test('late active GET cannot restore preview suppression after explicit stop confirmation', async () => {
  let releaseGet;
  const lateGet = new Promise(resolve => { releaseGet = resolve; });
  const inactive = state => snapshot({ state, source: null, sensor_pose: null,
    trail: [], temporal_consistency_confirmed: false });
  let reads = 0;
  const controller = model(async (path, options = {}) => {
    if (path.endsWith('/stop')) return reply(inactive('STOPPED'));
    if (options.method === 'POST') return reply(inactive('INITIALIZING'));
    return reads++ ? lateGet : reply(snapshot());
  });
  await controller.start(); await controller.poll();
  const pendingGet = controller.poll();
  await controller.stop();
  assert.equal(controller.snapshot().previewSuppressed, false);
  releaseGet(reply(snapshot())); await pendingGet;
  assert.equal(controller.snapshot().state, 'STOPPED');
  assert.equal(sensorSceneReserved(controller.snapshot(), controller.pending, controller.writing), false);
  await controller.poll();
  assert.equal(controller.snapshot().state, 'STOPPED', 'same-session active reply after stop is fenced');
  assert.equal(controller.snapshot().previewSuppressed, false);
  controller.destroy();
});

test('invalidated historical global selection immediately removes displayed sensor candidate', async () => {
  const controller = model(async () => reply(snapshot()));
  await controller.poll(); assert.equal(controller.snapshot().state, 'SENSOR_CANDIDATE');
  controller.setGlobalRecord(null);
  assert.equal(controller.snapshot().value, null);
  assert.equal(controller.snapshot().error, 'GLOBAL_SELECTION_CHANGED');
  controller.destroy();
});

test('map change fences delayed start response and clears candidate immediately', async () => {
  let release; const pending = new Promise(resolve => { release = resolve; });
  const calls = [];
  const controller = model(async (path, options = {}) => {
    calls.push(path); return path.endsWith('/stop') ? reply(snapshot({ state: 'STOPPED', source: null,
      sensor_pose: null, trail: [], temporal_consistency_confirmed: false })) : pending;
  });
  const start = controller.start();
  assert.equal(calls.length, 1);
  assert.equal(controller.snapshot().previewSuppressed, true);
  controller.setMap({ ...meta, revision: 'f'.repeat(64) }, null);
  assert.equal(controller.snapshot().previewSuppressed, false);
  release(reply(snapshot({ state: 'INITIALIZING', source: null, sensor_pose: null,
    trail: [], temporal_consistency_confirmed: false })));
  await start; assert.equal(controller.snapshot().value, null);
  assert.equal(controller.snapshot().previewSuppressed, false);
  assert.ok(calls.some(path => path.endsWith('/stop')));
  controller.destroy();
});

test('duplicate start is single flight and uncertain response reuses the request id', async () => {
  const calls = []; let fail = true;
  const controller = model(async (_path, options = {}) => {
    calls.push(options);
    if (fail) { fail = false; throw new Error('lost response'); }
    return reply(snapshot({ state: 'INITIALIZING', source: null, sensor_pose: null,
      trail: [], temporal_consistency_confirmed: false }));
  });
  const first = controller.start(), duplicate = controller.start();
  await Promise.all([first, duplicate]);
  assert.equal(calls.length, 1); assert.equal(controller.snapshot().canRetry, true);
  await controller.start();
  assert.equal(calls.length, 2);
  assert.equal(JSON.parse(calls[0].body).request_id, JSON.parse(calls[1].body).request_id);
  controller.destroy();
});

test('explicit stop hides late candidate GET while stop response is pending', async () => {
  let release;
  const stopResponse = new Promise(resolve => { release = resolve; });
  const controller = model(async (path) => path.endsWith('/stop') ? stopResponse : reply(snapshot()));
  await controller.poll(); assert.equal(controller.snapshot().state, 'SENSOR_CANDIDATE');
  const stopping = controller.stop();
  await controller.poll();
  assert.equal(controller.snapshot().value, null);
  assert.equal(controller.snapshot().error, 'STOP_PENDING');
  assert.equal(controller.snapshot().canStart, false);
  release(reply(snapshot({ state: 'STOPPED', source: null, sensor_pose: null,
    trail: [], temporal_consistency_confirmed: false })));
  await stopping; assert.equal(controller.snapshot().state, 'STOPPED');
  controller.destroy();
});

test('known start rejection reports bounded reason rather than a successful candidate', async () => {
  const controller = model(async () => ({ ok: false, status: 409,
    json: async () => ({ detail: 'GLOBAL_CANDIDATE_NOT_ADMISSIBLE' }) }));
  await controller.start();
  assert.equal(controller.snapshot().value, null);
  assert.equal(controller.snapshot().error, 'START_REJECTED_HTTP_409_GLOBAL_CANDIDATE_NOT_ADMISSIBLE');
  controller.destroy();
});

test('new selected global job fences active sensor trail and sends one stop; same selection poll does not', async () => {
  const calls = [], stopped = snapshot({ state: 'STOPPED', source: null, sensor_pose: null,
    trail: [], temporal_consistency_confirmed: false });
  const controller = model(async (path, options = {}) => {
    calls.push({ path, method: options.method });
    if (path.endsWith('/stop')) return reply(stopped);
    if (options.method === 'POST') return reply(snapshot({ state: 'INITIALIZING', source: null,
      sensor_pose: null, trail: [], temporal_consistency_confirmed: false }));
    return reply(snapshot());
  });
  await controller.start(); await controller.poll();
  assert.equal(controller.snapshot().state, 'SENSOR_CANDIDATE');
  controller.setGlobalRecord(globalRecord());
  assert.equal(calls.filter(call => call.path.endsWith('/stop')).length, 0);
  const replacement = globalRecord(); replacement.job_id = 'd'.repeat(24); replacement.generation = 6;
  controller.setGlobalRecord(replacement);
  assert.equal(controller.snapshot().value, null);
  assert.equal(controller.snapshot().stopRequested, true);
  assert.equal(calls.filter(call => call.path.endsWith('/stop')).length, 1);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(controller.snapshot().state, 'STOPPED');
  assert.equal(controller.snapshot().canStart, true);
  controller.destroy();
});

test('selection change with uncertain stop keeps old marker fenced and cleanup retry available', async () => {
  const stopError = new Error('network lost'); let stops = 0;
  const controller = model(async (path, options = {}) => {
    if (path.endsWith('/stop')) {
      stops++;
      if (stops === 1) throw stopError;
      return reply(snapshot({ state: 'STOPPED', source: null, sensor_pose: null,
        trail: [], temporal_consistency_confirmed: false }));
    }
    return reply(options.method === 'POST'
      ? snapshot({ state: 'INITIALIZING', source: null, sensor_pose: null,
        trail: [], temporal_consistency_confirmed: false }) : snapshot());
  });
  await controller.start(); await controller.poll();
  const replacement = globalRecord(); replacement.job_id = 'd'.repeat(24); replacement.generation = 6;
  controller.setGlobalRecord(replacement);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(controller.snapshot().value, null);
  assert.equal(controller.snapshot().stopRequested, true);
  assert.equal(controller.snapshot().error, 'STOP_RESULT_UNCERTAIN');
  assert.equal(controller.snapshot().canStart, false);
  assert.equal(controller.snapshot().canStop, true);
  await controller.stop(); assert.equal(stops, 2);
  assert.equal(controller.snapshot().state, 'STOPPED');
  controller.destroy();
});

test('replacement fences a late GET while old start and cleanup POST are still pending', async () => {
  let releaseStart, releaseStop;
  const startResponse = new Promise(resolve => { releaseStart = resolve; });
  const stopResponse = new Promise(resolve => { releaseStop = resolve; });
  const calls = [];
  const controller = model(async (path, options = {}) => {
    calls.push(path);
    if (path.endsWith('/stop')) return stopResponse;
    if (options.method === 'POST') return startResponse;
    return reply(snapshot());
  });
  const starting = controller.start();
  const replacement = globalRecord(); replacement.job_id = 'd'.repeat(24); replacement.generation = 6;
  controller.setGlobalRecord(replacement);
  assert.equal(controller.snapshot().value, null);
  assert.equal(controller.snapshot().canStart, false);
  await controller.poll(); assert.equal(controller.snapshot().value, null);
  releaseStop(reply(snapshot({ state: 'STOPPED', source: null, sensor_pose: null,
    trail: [], temporal_consistency_confirmed: false })));
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(controller.snapshot().canStart, false, 'old start remains in flight');
  releaseStart(reply(snapshot({ state: 'INITIALIZING', source: null, sensor_pose: null,
    trail: [], temporal_consistency_confirmed: false })));
  await starting;
  assert.equal(controller.snapshot().value?.sensor_pose ?? null, null);
  assert.ok(calls.filter(path => path.endsWith('/stop')).length >= 1);
  controller.destroy();
});
