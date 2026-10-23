import test from 'node:test';
import assert from 'node:assert/strict';
import { GlobalObservationController, globalMapIdentity, validateGlobalJob, validatedAmbiguityOverride } from '../robot_dashboard/static/features/maps/global_observation_contract.js';
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

test('verified provisional policy is labelled historical and actual backend gate reasons remain visible', () => {
  const record = completed(), observation = record.result.observation;
  observation.gate_reasons = ['AMBIGUOUS_ALTERNATIVES'];
  observation.rejection_reasons = ['LEGACY_REASON'];
  observation.selection_policy = { schema: 'robot-scope.global-provisional-selection.v1',
    adapter: 'dashboard-v031-residual-gate-v1', original_max_rmse_m: .05,
    provisional_max_rmse_m: .10, scoring: 'UNCHANGED_ORIGINAL_REFERENCE_POPULATION',
    scope: 'PROVISIONAL_OBSERVATION_ONLY', original_selection_replayed: false };
  const summary = globalObservationSummary(record);
  assert.match(summary, /잠정 10cm 선택 후보 없음/);
  assert.match(summary, /AMBIGUOUS_ALTERNATIVES/);
  assert.doesNotMatch(summary, /LEGACY_REASON/);
  assert.match(summary, /과거 가설/);
  observation.selection_policy.scope = 'OPERATIONAL';
  assert.match(globalObservationSummary(record), /선택 정책 미검증/);
  assert.doesNotMatch(globalObservationSummary(record), /잠정 10cm 선택 후보/);
});

test('v2 selected candidate is historical and residual thresholds are labelled comparison only', () => {
  const record = completed(), observation = record.result.observation;
  observation.selection_policy = { schema: 'robot-scope.global-provisional-selection.v2',
    adapter: 'dashboard-v031-observation-no-rmse-gate-v1', original_max_rmse_m: .05,
    provisional_max_rmse_m: .10, rmse_thresholds_purpose: 'COMPARISON_ONLY',
    rmse_selection_gate_enabled: false, scoring: 'UNCHANGED_ORIGINAL_REFERENCE_POPULATION',
    scope: 'PROVISIONAL_OBSERVATION_ONLY', original_selection_replayed: false };
  observation.selected_candidate = 0;
  observation.gate_reasons = [];
  observation.candidates = [{ rmse_m: .144, gate_reasons: [], map_from_scan: [[1,0,0,1],[0,1,0,2],[0,0,1,0],[0,0,0,1]] }];
  observation.residual_comparison_policy = {
    schema: 'robot-scope.residual-comparison-policy.v1', candidate_index_basis: 'CANDIDATE_ARRAY_INDEX',
    comparison_fields: ['residual_passed', 'original_residual_passed'],
    policy: { unit: 'm', max_rmse_m: .10 }, original_policy: { max_rmse_m: .05 },
    overall_candidate_acceptance_evaluated: false, overall_candidate_accepted: null };
  observation.residual_comparisons = [[false, false]];
  assert.match(globalObservationSummary(record), /잔차 문턱 없는 잠정 관측 후보 0/);
  assert.match(globalObservationSummary(record), /과거 가설/);
  assert.match(globalObservationSummary(record), /후보 선택 문턱으로 사용하지 않/);
  assert.match(globalResidualText(observation), /원본 5cm 비교 초과 · 잠정 10cm 비교 초과/);
  assert.doesNotMatch(globalResidualText(observation), /통과/);
  observation.selection_policy.rmse_selection_gate_enabled = true;
  assert.match(globalObservationSummary(record), /선택 정책 미검증/);
});

test('ambiguous opt-in labels a historical unverified estimate and preserves original gates and alternatives', () => {
  const record = completed(), observation = record.result.observation;
  observation.selection_policy = { schema: 'robot-scope.global-provisional-selection.v2',
    adapter: 'dashboard-v031-observation-no-rmse-gate-v1', original_max_rmse_m: .05,
    provisional_max_rmse_m: .10, rmse_thresholds_purpose: 'COMPARISON_ONLY',
    rmse_selection_gate_enabled: false, scoring: 'UNCHANGED_ORIGINAL_REFERENCE_POPULATION',
    scope: 'PROVISIONAL_OBSERVATION_ONLY', original_selection_replayed: false };
  observation.gate_reasons = ['AMBIGUOUS_ALTERNATIVES'];
  observation.ambiguity_override = { enabled: true, applied: true,
    selection_rule: 'LOWEST_RMSE_M_THEN_ORIGINAL_INDEX', original_selected_candidate: null,
    original_gate_reasons: ['AMBIGUOUS_ALTERNATIVES'] };
  observation.estimate_label = 'AMBIGUOUS_UNVERIFIED_ESTIMATE';
  const candidate = rmse_m => ({ gate_reasons: ['AMBIGUOUS_ALTERNATIVES'], refinement_stationary: true,
    rmse_m, full_scan_rmse_m: .21, capped_full_rmse_m: .19, overlap: .95,
    geometry_min_max_eigen_ratio: .02, inlier_geometry_min_max_eigen_ratio: .02,
    scan_count: 600, inlier_count: 560, distinct_inlier_voxel_count: 140,
    map_from_scan: [[1,0,0,1],[0,1,0,2],[0,0,1,0],[0,0,0,1]] });
  observation.candidates = [candidate(.144), candidate(.151)];
  observation.selected_candidate = 0;
  assert.equal(validatedAmbiguityOverride(observation), true);
  const summary = globalObservationSummary(record);
  assert.match(summary, /모호한 미검증 추정 후보 0/);
  assert.match(summary, /AMBIGUOUS_ALTERNATIVES/);
  assert.match(summary, /대안 1개/);
  assert.match(summary, /RMSE 최저, 동률이면 원본 인덱스/);
  assert.match(summary, /과거 가설/);
  observation.candidates[1].rmse_m = .140;
  assert.equal(validatedAmbiguityOverride(observation), false);
  assert.match(globalObservationSummary(record), /모호성 예외 검증 실패/);
  observation.candidates[1].rmse_m = .151;
  observation.candidates[0].gate_reasons.push('LOW_OVERLAP');
  assert.equal(validatedAmbiguityOverride(observation), false);
  observation.candidates[0].gate_reasons.pop();
  observation.ambiguity_override.enabled = false;
  assert.equal(validatedAmbiguityOverride(observation), false);
});

test('edited full-source reference warns that its residual cannot demonstrate parent-map improvement', () => {
  const record = completed();
  const reference = { map_id: map.id, map_revision: map.revision, frame_id: 'map',
    reference_provenance: { asset_role: 'EDITED_FULL_SOURCE', scoring_population: 'THIS_EDITED_MAP_COMPLETE_XYZ',
      parent_score_comparable: false, direct_parent: { map_id: 'd'.repeat(24), revision: 'e'.repeat(64), sha256: 'f'.repeat(64) } } };
  record.captured_context = { ...capture, map: reference };
  record.result.captured_context = record.captured_context;
  assert.equal(validateGlobalJob(record, globalMapIdentity(map)), true);
  const summary = globalObservationSummary(record);
  assert.match(summary, /선택한 편집 지도의 전체 XYZ로 채점/);
  assert.match(summary, /부모 원본 지도와 RMSE를 직접 비교할 수 없/);
  assert.match(summary, /낮은 잔차가 원본 대비 정확도 개선을 뜻하지 않/);
  assert.match(summary, /과거 가설/);
  assert.equal(record.current_result, null); assert.equal(record.tracking_verified, false);
  reference.reference_provenance.parent_score_comparable = true;
  assert.doesNotMatch(globalObservationSummary(record), /부모 원본 지도와 RMSE/);
  reference.reference_provenance.parent_score_comparable = false;
  reference.map_revision = '0'.repeat(64);
  assert.doesNotMatch(globalObservationSummary(record), /부모 원본 지도와 RMSE/);
  assert.doesNotMatch(globalObservationSummary(completed()), /부모 원본 지도와 RMSE/);
});

test('compact indexed residual sidecar uses stored candidate RMSE and rejects malformed comparisons', () => {
  const observation = completed().result.observation;
  observation.candidates = [{ rmse_m: .07, gate_reasons: ['REFINEMENT_NOT_STATIONARY'] },
    { rmse_m: .11, gate_reasons: ['RMSE_ABOVE_0.10M'] }];
  observation.residual_comparison_policy = {
    schema: 'robot-scope.residual-comparison-policy.v1', candidate_index_basis: 'CANDIDATE_ARRAY_INDEX',
    comparison_fields: ['residual_passed', 'original_residual_passed'],
    policy: { unit: 'm', max_rmse_m: .10 }, original_policy: { max_rmse_m: .05 },
    overall_candidate_acceptance_evaluated: false, overall_candidate_accepted: null };
  observation.residual_comparisons = [[true, false], [false, false]];
  const text = globalResidualText(observation);
  assert.match(text, /후보 0: RMSE 0\.07000 m · 원본 5cm 미통과 · 잠정 10cm 통과/);
  assert.match(text, /후보 1: RMSE 0\.11000 m · 원본 5cm 미통과 · 잠정 10cm 미통과/);
  observation.residual_comparisons[0] = null;
  assert.match(globalResidualText(observation), /후보 0: 잔차 비교 미검증/);
  observation.residual_comparisons[0] = [true, true];
  assert.match(globalResidualText(observation), /후보 0: 잔차 비교 미검증/);
  observation.residual_comparison_policy.candidate_index_basis = 'UNVERIFIED';
  assert.equal(globalResidualText(observation), '원본 5cm / 잠정 10cm 잔차 비교 미검증');
});
