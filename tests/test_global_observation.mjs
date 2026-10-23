import test from 'node:test';
import assert from 'node:assert/strict';
import { GlobalObservationController, globalMapIdentity, validateGlobalJob } from '../robot_dashboard/static/features/maps/global_observation_contract.js';
import { globalObservationSummary, globalResidualText } from '../robot_dashboard/static/features/maps/global_observation.js';

const map = { id: 'a'.repeat(24), revision: 'b'.repeat(64), frame_id: 'map', kind: 'pointcloud3d' };
const flags = { historical_only: true, current_result: null, body_pose: null, tracking_verified: false,
  body_pose_verified: false, body_extrinsic_verified: false, operational_application: 'NOT_RUN', absolute_accuracy_m: null };
const capture = { map_id: map.id, map_revision: map.revision, map_frame: 'map', source_frame: 'hesai_lidar',
  source_topic: '/velodyne_points', observer_id: 'observer', observer_epoch: 'epoch', source_stamp_ns: '1792309179130175352' };
const source = { topic: '/velodyne_points', frame_id: 'hesai_lidar', observation: { observer_id: 'observer', publisher_epoch: 'epoch' } };
const response = value => ({ ok: true, json: async () => value });
function job(changes = {}) { return { schema: 'robot-scope.raw-global-observation-job.v1', job_id: 'c'.repeat(24), request_id: 'request-1',
  generation: 1, state: 'running', captured_context: capture, result: null, worker_active: true, ...flags, ...changes }; }
function completed(changes = {}) {
  return job({ state: 'succeeded', worker_active: false, result: {
    schema: 'robot-scope.raw-global-observation-result.v1', job_id: 'c'.repeat(24), generation: 1,
    captured_context: capture, observation: { status: 'OBSERVATION_ONLY_UNVERIFIED', selected_candidate: null,
      rejection_reasons: ['REFINEMENT_NOT_STATIONARY'], candidates: [{ rmse_m: .07, gate_reasons: ['RMSE_ABOVE_0.05M'] }] }, ...flags }, ...changes });
}
function completedWithContexts(captured, resultCaptured) {
  const value = completed();
  return { ...value, captured_context: captured, result: { ...value.result, captured_context: resultCaptured } };
}
function reorderObjectKeys(value) {
  if (Array.isArray(value)) return value.map(reorderObjectKeys);
  return value !== null && typeof value === 'object'
    ? Object.fromEntries(Object.entries(value).reverse().map(([key, item]) => [key, reorderObjectKeys(item)]))
    : value;
}
function nestedCapture() {
  return { ...capture, profile: { id: 'synthetic-profile', stream: { width: 640, height: 480, fps: 30 },
    channels: [{ name: 'left', enabled: true }, { name: 'right', enabled: false }], optional: null } };
}
function status(value = null, available = true) { return { schema: 'robot-scope.raw-global-observations.v1', generation: value?.generation || 0,
  provider: { available, reason: available ? null : 'TRUSTED_LOCAL_RUNNER_UNAVAILABLE', backend_id: 'synthetic' },
  active: value?.worker_active ? value : null, latest: value, ...flags }; }
function controller(handler) {
  const calls = [], model = new GlobalObservationController({ requestId: () => 'request-1', request: async (url, options = {}) => {
    calls.push({ url, ...options }); return handler(url, options, calls);
  } });
  model.setMap(map, null); model.ingestCloud(source); return { model, calls };
}
function deferred() { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; }

test('unavailable provider cannot start and loaded map revision/frame is required', async () => {
  const { model, calls } = controller(async () => response(status(null, false)));
  await model.poll(); await model.start(); assert.equal(calls.length, 1);
  assert.equal(model.snapshot().canStart, false);
  assert.equal(globalMapIdentity(map, { frame_id: 'different' }), null);
  assert.equal(globalMapIdentity(map, { frame_id: 'map', revision: 'd'.repeat(64) }), null);
});

test('double start is single-flight, completion stays historical and exact source stamp is preserved', async () => {
  const start = deferred(); let finished = false;
  const { model, calls } = controller(async (_url, options) => options.method === 'POST' ? start.promise : response(status(finished ? completed() : null)));
  await model.poll(); const pending = model.start(); await model.start();
  assert.equal(calls.filter(c => c.method === 'POST').length, 1);
  start.resolve(response(job())); await pending; finished = true; await model.poll();
  const record = model.snapshot().record;
  assert.equal(record.captured_context.source_stamp_ns, capture.source_stamp_ns);
  assert.equal(record.current_result, null); assert.equal(record.body_pose, null); assert.equal(record.tracking_verified, false);
  assert.match(globalObservationSummary(record), /원본 선택 후보 없음/);
  assert.match(globalObservationSummary(record), /과거 가설/);
  assert.equal(model.snapshot().canStart, true);
});

test('lost start response is recovered by request id without another POST', async () => {
  let submitted = false;
  const { model, calls } = controller(async (_url, options) => {
    if (options.method === 'POST') { submitted = true; throw new Error('response lost'); }
    return response(status(submitted ? job() : null));
  });
  await model.poll(); await model.start(); assert.equal(model.snapshot().uncertain, true);
  await model.poll(); assert.equal(model.job.job_id, 'c'.repeat(24));
  assert.equal(calls.filter(c => c.method === 'POST').length, 1);
});

test('uncertain explicit retry preserves exactly the request id and map identity', async () => {
  let attempts = 0;
  const { model, calls } = controller(async (_url, options) => {
    if (options.method === 'POST') { if (++attempts === 1) throw new Error('lost'); return response(job()); }
    return response(status());
  });
  await model.poll(); await model.start(); await model.start();
  const posts = calls.filter(c => c.method === 'POST'); assert.equal(posts.length, 2); assert.equal(posts[0].body, posts[1].body);
});

test('map change during delayed start cancels returned job and never renders the late result', async () => {
  const start = deferred(); let cancelled = false;
  const { model, calls } = controller(async (url, options) => {
    if (url.endsWith('/cancel')) { cancelled = true; return response(job({ state: 'cancelled' })); }
    if (options.method === 'POST') return start.promise;
    return response(status(cancelled ? job({ state: 'cancelled' }) : null));
  });
  await model.poll(); const task = model.start(); model.setMap({ ...map, revision: 'd'.repeat(64) }, null);
  start.resolve(response(job())); await task; await model.poll(); await model.poll();
  assert.equal(cancelled, true); assert.equal(model.record, null); assert.equal(model.snapshot().canStart, false);
  assert.equal(calls.filter(c => c.url.endsWith('/cancel')).length, 1);
});

test('epoch/frame reset and explicit cancel fence late successful result while cleanup owns slot', async () => {
  let last = job();
  const { model } = controller(async (url, options) => {
    if (url.endsWith('/cancel')) return response(job({ state: 'cancelled' }));
    if (options.method === 'POST') return response(last);
    return response(status(model?.pending ? last : null));
  });
  await model.poll(); await model.start();
  model.ingestCloud({ ...source, observation: { ...source.observation, publisher_epoch: 'new' } });
  await new Promise(resolve => setImmediate(resolve));
  last = completed({ worker_active: true }); await model.poll();
  assert.equal(model.record, null); assert.equal(model.snapshot().canStart, false);
  last = job({ state: 'cancelled', worker_active: false }); await model.poll();
  assert.equal(model.record, null); assert.equal(model.snapshot().canStart, true);
});

test('job contract rejects unsafe current/body results and mismatched map, frame, epoch, numeric timestamps', () => {
  const identity = globalMapIdentity(map);
  assert.equal(validateGlobalJob(completed(), identity), true);
  for (const change of [{ current_result: {} }, { tracking_verified: true }, { body_pose: {} }, { historical_only: false }])
    assert.equal(validateGlobalJob(completed(change), identity), false);
  for (const change of [{ map_revision: 'd'.repeat(64) }, { map_frame: 'odom' }, { source_stamp_ns: Number(capture.source_stamp_ns) }]) {
    assert.equal(validateGlobalJob(completed({ captured_context: { ...capture, ...change } }), identity), false);
  }
  assert.equal(validateGlobalJob(completed(), identity, { observer_epoch: 'changed' }), false);
});

test('captured contexts accept recursively reordered object keys without changing array order', () => {
  const captured = nestedCapture(), resultCaptured = reorderObjectKeys(captured);
  assert.notEqual(JSON.stringify(captured), JSON.stringify(resultCaptured));
  assert.equal(validateGlobalJob(completedWithContexts(captured, resultCaptured), globalMapIdentity(map)), true);
});

test('captured contexts still reject changed values, types, missing/extra keys and reordered arrays', () => {
  const captured = nestedCapture();
  const changes = [
    ['frame', value => { value.source_frame = 'other_sensor'; }],
    ['epoch', value => { value.observer_epoch = 'other_epoch'; }],
    ['stamp', value => { value.source_stamp_ns = '1792309179130175353'; }],
    ['profile', value => { value.profile.id = 'other-profile'; }],
    ['unknown key', value => { value.unknown = { source: 'unexpected' }; }],
    ['missing key', value => { delete value.profile; }],
    ['nested missing key', value => { delete value.profile.stream.fps; }],
    ['nested extra key', value => { value.profile.stream.format = 'unexpected'; }],
    ['array order', value => { value.profile.channels.reverse(); }],
    ['primitive type', value => { value.profile.stream.width = '640'; }],
    ['array/object type', value => { value.profile.channels = { 0: value.profile.channels[0], 1: value.profile.channels[1] }; }],
    ['null/object type', value => { value.profile.optional = {}; }],
  ];
  for (const [label, change] of changes) {
    const resultCaptured = reorderObjectKeys(captured);
    change(resultCaptured);
    assert.equal(validateGlobalJob(completedWithContexts(captured, resultCaptured), globalMapIdentity(map)), false, label);
  }
});

test('controller adopts a completed historical record whose captured context object keys were reordered', async () => {
  const captured = nestedCapture(), value = completedWithContexts(captured, reorderObjectKeys(captured));
  let finished = false;
  const { model, calls } = controller(async (_url, options) => options.method === 'POST'
    ? response(job({ captured_context: captured })) : response(status(finished ? value : null)));
  await model.poll(); await model.start(); finished = true; await model.poll();
  assert.equal(model.snapshot().error, '');
  assert.deepEqual(model.snapshot().record, value);
  assert.equal(model.snapshot().record.historical_only, true);
  assert.equal(model.snapshot().record.current_result, null);
  assert.equal(model.pending, null);
  assert.equal(calls.filter(call => call.method === 'POST').length, 1);
});

test('a later server generation clears export without promoting a historical result', async () => {
  let state = status();
  const { model } = controller(async (_url, options) => response(options.method === 'POST' ? completed() : state));
  await model.poll(); await model.start(); assert.ok(model.record);
  state = { ...status(), generation: 2 }; await model.poll(); assert.equal(model.record, null);
});

test('residual sidecar remains separate from original selection and all gates', () => {
  const record = completed(), observation = record.result.observation;
  observation.residual_comparisons = [{ candidate_index: 0, evaluation: { rmse_m: .07, original_residual_passed: false, residual_passed: true,
    policy: { unit: 'm', max_rmse_m: .10 }, original_policy: { max_rmse_m: .05 },
    overall_candidate_acceptance_evaluated: false, overall_candidate_accepted: null } }];
  assert.match(globalResidualText(observation), /원본 5cm 미통과 · 잠정 10cm 통과/);
  assert.match(globalObservationSummary(record), /원본 선택 후보 없음.*REFINEMENT_NOT_STATIONARY/);
  observation.residual_comparisons[0].evaluation.policy.unit = 'cm';
  assert.match(globalResidualText(observation), /잔차 비교 미검증/);
});
