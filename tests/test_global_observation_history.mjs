// Synthetic contract tests only: no network, sensors, or native registration.
import test from 'node:test';
import assert from 'node:assert/strict';
import { GlobalObservationController } from '../robot_dashboard/static/features/maps/global_observation_contract.js';

const ROOT = '/api/v1/observations/global-jobs';
const ID = 'c'.repeat(24), OTHER = 'd'.repeat(24);
const map = { id: 'a'.repeat(24), revision: 'b'.repeat(64), frame_id: 'camera_init', kind: 'pointcloud3d' };
const flags = { historical_only: true, current_result: null, body_pose: null, tracking_verified: false,
  body_pose_verified: false, body_extrinsic_verified: false, operational_application: 'NOT_RUN', absolute_accuracy_m: null };
const source = { topic: '/velodyne_points', frame_id: 'hesai_lidar',
  observation: { observer_id: 'synthetic-observer', publisher_epoch: 'synthetic-epoch' } };
const capture = { map_id: map.id, map_revision: map.revision, map_frame: map.frame_id,
  source_topic: source.topic, source_frame: source.frame_id, observer_id: source.observation.observer_id,
  observer_epoch: source.observation.publisher_epoch, source_stamp_ns: '1792678892357536793',
  source_clock: 'UNVERIFIED', profile: { id: 'synthetic-profile', size: [640, 480], enabled: true } };
const clone = value => structuredClone(value);
const response = (value, code = 200) => ({ ok: code >= 200 && code < 300, status: code, json: async () => clone(value) });
function completed(id = ID, generation = 1) {
  return { schema: 'robot-scope.raw-global-observation-job.v1', job_id: id, generation,
    request_id: `synthetic-${id}`, state: 'succeeded', worker_active: false, capture_age_s: 7200,
    captured_context: clone(capture), ...flags, result: {
      schema: 'robot-scope.raw-global-observation-result.v1', job_id: id, generation,
      captured_context: clone(capture), ...flags, observation: { status: 'OBSERVATION_ONLY_UNVERIFIED',
        selected_candidate: 0, rejection_reasons: ['AMBIGUOUS_ALTERNATIVES'],
        candidates: [{ rmse_m: .230319, overlap: .90325, inlier_count: 14452,
          gate_reasons: ['AMBIGUOUS_ALTERNATIVES'] }] } } };
}
function status(latest = completed(), generation = latest?.generation ?? 0) {
  return { schema: 'robot-scope.raw-global-observations.v1', provider: { available: true, backend_id: 'SYNTHETIC' },
    generation, closed: false, active: latest?.worker_active ? latest : null, latest, ...flags };
}
function controller(handler, { liveSource = source, canChangeHistory = () => true } = {}) {
  const calls = [];
  const model = new GlobalObservationController({ canChangeHistory, request: async (url, options = {}) => {
    calls.push({ url, method: options.method || 'GET', body: options.body }); return handler(url, options, calls);
  } });
  model.setMap(map, null); if (liveSource) model.ingestCloud(liveSource);
  return { model, calls };
}
function fixture(value = completed(), state = status(value)) {
  return controller(async url => response(url === ROOT ? state : value));
}
function readOnly(calls) { assert.ok(calls.every(call => call.method === 'GET'), JSON.stringify(calls)); }
function cleared(model) {
  const snapshot = model.snapshot();
  assert.equal(snapshot.record, null);
  assert.equal(snapshot.displayRecord, null);
  assert.equal(snapshot.historicalSelection, null);
  assert.equal(snapshot.historyBusy, false);
}
function deferred() { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; }

test('status discovers terminal history but requires explicit GET detail and status before displaying it', async () => {
  const value = completed(), { model, calls } = fixture(value);
  await model.poll();
  assert.deepEqual(model.snapshot().history.map(item => item.job_id), [ID]);
  assert.equal(model.snapshot().record, null); assert.equal(model.snapshot().displayRecord, null);
  assert.equal(model.pending, null);
  await model.openHistorical(ID);
  assert.deepEqual(calls.map(call => call.url), [ROOT, `${ROOT}/${ID}`, ROOT]);
  assert.deepEqual(model.snapshot().displayRecord, value);
  assert.deepEqual(model.snapshot().displayJob, value);
  assert.equal(model.snapshot().historicalSelection, ID);
  assert.equal(model.snapshot().record?.job_id, ID);
  assert.equal(model.snapshot().record.current_result, null);
  assert.equal(model.snapshot().record.body_pose, null);
  assert.equal(model.pending, null); readOnly(calls);
});

test('a fresh controller can explicitly restore the same server-retained historical result after reload', async () => {
  for (let pageLoad = 0; pageLoad < 2; pageLoad++) {
    const { model, calls } = fixture();
    await model.poll(); assert.equal(model.snapshot().displayRecord, null);
    await model.openHistorical(ID);
    assert.equal(model.snapshot().displayRecord.job_id, ID);
    assert.equal(model.snapshot().displayRecord.capture_age_s, 7200);
    assert.equal(model.snapshot().displayRecord.result.observation.rejection_reasons[0], 'AMBIGUOUS_ALTERNATIVES');
    assert.equal(model.pending, null); readOnly(calls);
  }
});

test('older server generations remain display-only and ordinary polling cannot promote them to tracking input', async () => {
  const value = completed(), state = status(completed(OTHER, 2), 2), { model, calls } = fixture(value, state);
  await model.poll(); await model.openHistorical(ID);
  assert.equal(model.snapshot().displayRecord?.job_id, ID);
  assert.equal(model.snapshot().historicalCurrentGeneration, false);
  assert.equal(model.snapshot().record, null);
  await model.poll();
  assert.equal(model.snapshot().displayRecord?.job_id, ID);
  assert.equal(model.snapshot().record, null); assert.equal(model.pending, null); readOnly(calls);
});

test('server generation change preserves the explicit historical display and clears current-generation record', async () => {
  let state = status();
  const { model, calls } = controller(async url => response(url === ROOT ? state : completed()));
  await model.openHistorical(ID); assert.equal(model.snapshot().record?.job_id, ID);
  state = status(completed(OTHER, 2), 2); await model.poll();
  assert.equal(model.snapshot().record, null);
  assert.equal(model.snapshot().displayRecord?.job_id, ID);
  assert.equal(model.snapshot().historicalCurrentGeneration, false); readOnly(calls);
});

test('exact historical contract accepts object key reordering while keeping all nested values and array positions', async () => {
  const value = completed();
  const reverse = data => Array.isArray(data) ? data.map(reverse) : data !== null && typeof data === 'object'
    ? Object.fromEntries(Object.entries(data).reverse().map(([key, item]) => [key, reverse(item)])) : data;
  value.result.captured_context = reverse(value.captured_context);
  const { model, calls } = fixture(value); await model.openHistorical(ID);
  assert.deepEqual(model.snapshot().displayRecord, value); readOnly(calls);
});

test('historical restore rejects id, schema, map, revision, frame, epoch and nested context mismatches', async t => {
  const mutations = [
    ['requested job id', value => { value.job_id = OTHER; value.result.job_id = OTHER; }],
    ['job schema', value => { value.schema = 'unknown'; }],
    ['result schema', value => { value.result.schema = 'unknown'; }],
    ['map id', value => { value.captured_context.map_id = OTHER; value.result.captured_context.map_id = OTHER; }],
    ['map revision', value => { value.captured_context.map_revision = 'e'.repeat(64); value.result.captured_context.map_revision = 'e'.repeat(64); }],
    ['top-level map id', value => { value.map_id = OTHER; }],
    ['top-level map revision', value => { value.map_revision = 'e'.repeat(64); }],
    ['map frame', value => { value.captured_context.map_frame = 'odom'; value.result.captured_context.map_frame = 'odom'; }],
    ['source frame', value => { value.captured_context.source_frame = 'other'; value.result.captured_context.source_frame = 'other'; }],
    ['epoch', value => { value.captured_context.observer_epoch = 'other'; value.result.captured_context.observer_epoch = 'other'; }],
    ['stamp primitive type', value => { value.captured_context.source_stamp_ns = Number(capture.source_stamp_ns); value.result.captured_context.source_stamp_ns = Number(capture.source_stamp_ns); }],
    ['nested primitive type', value => { value.result.captured_context.profile.enabled = 'true'; }],
    ['nested missing key', value => { delete value.result.captured_context.profile.id; }],
    ['nested added key', value => { value.result.captured_context.profile.extra = 0; }],
    ['array order', value => { value.result.captured_context.profile.size.reverse(); }],
    ['result generation', value => { value.result.generation++; }],
    ['unsafe body pose', value => { value.result.body_pose = { x: 0 }; }],
  ];
  for (const [label, mutate] of mutations) await t.test(label, async () => {
    const value = completed(); mutate(value);
    const { model, calls } = fixture(value); await model.openHistorical(ID);
    cleared(model); assert.ok(model.snapshot().error, label); readOnly(calls);
  });
});

test('active and terminal-worker-cleanup jobs cannot be restored as completed history', async t => {
  for (const [name, mutate] of [
    ['running', value => { value.state = 'running'; value.result = null; value.worker_active = true; }],
    ['terminal worker cleanup', value => { value.worker_active = true; }],
  ]) await t.test(name, async () => {
    const value = completed(); mutate(value); const { model, calls } = fixture(value);
    await model.poll(); assert.equal(model.snapshot().history.length, 0);
    await model.openHistorical(ID); cleared(model); readOnly(calls);
  });
});

test('failed or missing restore clears an earlier selected result without submitting work', async t => {
  for (const [name, fail] of [
    ['missing', async () => response({ detail: 'job not found' }, 404)],
    ['network', async () => { throw new Error('synthetic disconnect'); }],
    ['invalid json schema', async () => response({ schema: 'invalid' })],
  ]) await t.test(name, async () => {
    const { model, calls } = controller(async url => url === `${ROOT}/${OTHER}` ? fail()
      : response(url === ROOT ? status() : completed()));
    await model.openHistorical(ID); assert.ok(model.snapshot().displayRecord);
    const pending = model.openHistorical(OTHER);
    assert.equal(model.snapshot().displayRecord, null); assert.equal(model.snapshot().record, null);
    await pending; cleared(model); assert.ok(model.snapshot().error); readOnly(calls);
  });
});

test('valid failed and cancelled jobs display their terminal status without a result or tracking input', async t => {
  for (const state of ['failed', 'cancelled']) await t.test(state, async () => {
    const value = { ...completed(), state, result: null, reason: 'SYNTHETIC_CAPTURE_FAILED' };
    const { model, calls } = fixture(value); await model.openHistorical(ID);
    assert.equal(model.snapshot().historicalSelection, ID);
    assert.equal(model.snapshot().displayJob.state, state);
    assert.equal(model.snapshot().displayRecord, null); assert.equal(model.snapshot().record, null);
    assert.equal(model.snapshot().error, ''); readOnly(calls);
  });
});

test('history identity changes between list/detail or detail/status are rejected without fallback', async t => {
  for (const stage of ['list-detail', 'detail-status']) await t.test(stage, async () => {
    let reads = 0;
    const value = completed(), replaced = completed(); replaced.request_id = 'synthetic-replaced-request';
    const { model, calls } = controller(async url => {
      if (url !== ROOT) return response(stage === 'list-detail' ? replaced : value);
      reads++; return response(status(stage === 'detail-status' && reads > 1 ? replaced : value));
    });
    await model.poll(); await model.openHistorical(ID);
    cleared(model); assert.match(model.snapshot().error, /IDENTITY_CHANGED/); readOnly(calls);
  });
});

test('invalid status after a valid detail cannot retain or promote the result', async t => {
  for (const invalid of [null, { ...status(), schema: 'unknown' }, { ...status(), generation: '1' }, { ...status(), body_pose: {} }]) {
    await t.test(JSON.stringify(invalid?.schema ?? null), async () => {
      const { model, calls } = fixture(completed(), invalid); await model.openHistorical(ID);
      cleared(model); assert.ok(model.snapshot().error); readOnly(calls);
    });
  }
});

test('selection change immediately clears the previous result and invalidates an in-flight detail response', async () => {
  const delay = deferred();
  const { model, calls } = controller(async url => url === `${ROOT}/${OTHER}` ? delay.promise
    : response(url === ROOT ? status() : completed()));
  await model.openHistorical(ID); assert.ok(model.snapshot().displayRecord);
  model.clearHistoricalSelection(); cleared(model);
  const task = model.openHistorical(OTHER);
  assert.equal(model.snapshot().historyBusy, true);
  model.clearHistoricalSelection(); delay.resolve(response(completed(OTHER))); await task;
  cleared(model); assert.equal(model.pending, null); readOnly(calls);
});

test('late history responses cannot cross map, source, explicit-context or disposed-view fences', async t => {
  const changes = [
    ['map revision', model => model.setMap({ ...map, revision: 'e'.repeat(64) }, null)],
    ['source epoch', model => model.ingestCloud({ ...source, observation: { ...source.observation, publisher_epoch: 'new-epoch' } })],
    ['explicit context reset', model => model.invalidate('CONTEXT_CHANGED')],
    ['disposed view', model => model.destroy()],
  ];
  for (const [label, change] of changes) await t.test(label, async () => {
    const delay = deferred();
    const { model, calls } = controller(async url => url === ROOT ? response(status()) : delay.promise);
    const task = model.openHistorical(ID); change(model); delay.resolve(response(completed())); await task;
    cleared(model); assert.equal(model.pending, null); readOnly(calls);
  });
});

test('late status responses cannot restore the result after the user changes context', async () => {
  const delay = deferred();
  const { model, calls } = controller(async url => url === ROOT ? delay.promise : response(completed()));
  const task = model.openHistorical(ID);
  await new Promise(resolve => setImmediate(resolve));
  model.setMap({ ...map, revision: 'e'.repeat(64) }, null);
  delay.resolve(response(status())); await task;
  cleared(model); assert.equal(model.pending, null); readOnly(calls);
});

test('invalid typed id never issues a request and never creates a pending start', async () => {
  const { model, calls } = fixture();
  for (const id of ['', '../cancel', 'g'.repeat(24), ID.slice(1)]) await model.openHistorical(id);
  assert.equal(calls.length, 0); cleared(model); assert.equal(model.pending, null);
});

test('closed server retains the historical display but cannot hand its record to tracking', async () => {
  let state = { ...status(), closed: true };
  const { model, calls } = controller(async url => response(url === ROOT ? state : completed()));
  await model.openHistorical(ID);
  assert.equal(model.snapshot().historicalSelection, ID);
  assert.equal(model.snapshot().displayRecord?.job_id, ID);
  assert.equal(model.snapshot().record, null);
  assert.equal(model.snapshot().historicalCurrentGeneration, true);
  assert.equal(model.snapshot().historicalTrackingEligible, false);
  state = { ...status(), closed: false }; await model.clearHistoricalSelection(); await model.openHistorical(ID);
  assert.equal(model.snapshot().record?.job_id, ID);
  assert.equal(model.snapshot().historicalTrackingEligible, true);
  state = { ...status(), closed: true }; await model.poll();
  assert.equal(model.snapshot().displayRecord?.job_id, ID);
  assert.equal(model.snapshot().historicalCurrentGeneration, true);
  assert.equal(model.snapshot().historicalTrackingEligible, false);
  assert.equal(model.snapshot().record, null); readOnly(calls);
});

test('an occupied active slot blocks tracking handoff even when its worker_active flag is false', async () => {
  let state = { ...status(), active: { ...completed(OTHER), worker_active: false } };
  const { model, calls } = controller(async url => response(url === ROOT ? state : completed()));
  await model.openHistorical(ID);
  assert.equal(model.snapshot().displayRecord?.job_id, ID);
  assert.equal(model.snapshot().historicalCurrentGeneration, true);
  assert.equal(model.snapshot().historicalTrackingEligible, false);
  assert.equal(model.snapshot().record, null);
  state = status(); await model.poll(); model.clearHistoricalSelection(); await model.openHistorical(ID);
  assert.equal(model.snapshot().record?.job_id, ID);
  state = { ...status(), active: { ...completed(OTHER), worker_active: false } }; await model.poll();
  assert.equal(model.snapshot().displayRecord?.job_id, ID);
  assert.equal(model.snapshot().record, null);
  assert.equal(model.snapshot().historicalTrackingEligible, false); readOnly(calls);
});

test('the first live source arriving during history detail or status wait is checked before restore', async t => {
  for (const phase of ['detail', 'status']) for (const kind of ['matching', 'changed-frame', 'changed-epoch']) {
    await t.test(`${phase}: ${kind}`, async () => {
      const delay = deferred();
      const { model, calls } = controller(async url => {
        if (phase === 'detail' && url !== ROOT || phase === 'status' && url === ROOT) return delay.promise;
        return response(url === ROOT ? status() : completed());
      }, { liveSource: null });
      const pending = model.openHistorical(ID);
      if (phase === 'status') await new Promise(resolve => setImmediate(resolve));
      const arriving = clone(source);
      if (kind === 'changed-frame') arriving.frame_id = 'different-sensor';
      if (kind === 'changed-epoch') arriving.observation.publisher_epoch = 'different-epoch';
      model.ingestCloud(arriving);
      delay.resolve(response(phase === 'detail' ? completed() : status())); await pending;
      if (kind === 'matching') {
        assert.equal(model.snapshot().displayRecord?.job_id, ID);
        assert.equal(model.snapshot().record?.job_id, ID);
        assert.equal(model.snapshot().historicalTrackingEligible, true);
      } else {
        cleared(model); assert.ok(model.snapshot().error, `${phase}: ${kind}`);
      }
      assert.equal(model.pending, null); readOnly(calls);
    });
  }
});

test('history guard locks entry and preserves an existing selection while another owner consumes it', async t => {
  for (const locked of ['false', 'throw']) await t.test(locked, async () => {
    let allowed = true;
    const { model, calls } = controller(async url => response(url === ROOT ? status() : completed()), {
      canChangeHistory: () => { if (allowed) return true; if (locked === 'throw') throw new Error('synthetic owner unknown'); return false; },
    });
    await model.openHistorical(ID);
    const before = model.snapshot(), count = calls.length;
    assert.equal(before.historyLocked, false); assert.equal(before.record?.job_id, ID);
    allowed = false;
    assert.equal(model.snapshot().historyLocked, true);
    assert.equal(model.snapshot().canOpenHistorical, false);
    model.clearHistoricalSelection(); await model.openHistorical(OTHER);
    assert.equal(model.snapshot().historicalSelection, ID);
    assert.deepEqual(model.snapshot().displayRecord, before.displayRecord);
    assert.deepEqual(model.snapshot().record, before.record);
    assert.equal(calls.length, count); assert.equal(model.pending, null); readOnly(calls);
    allowed = true; model.clearHistoricalSelection(); cleared(model);
  });
});

test('history guard becoming false during a detail or status read prevents late adoption', async t => {
  for (const phase of ['detail', 'status']) await t.test(phase, async () => {
    let allowed = true;
    const delay = deferred();
    const { model, calls } = controller(async url => {
      if (phase === 'detail' && url !== ROOT || phase === 'status' && url === ROOT) return delay.promise;
      return response(url === ROOT ? status() : completed());
    }, { canChangeHistory: () => allowed });
    const pending = model.openHistorical(ID);
    if (phase === 'status') await new Promise(resolve => setImmediate(resolve));
    allowed = false;
    delay.resolve(response(phase === 'detail' ? completed() : status())); await pending;
    cleared(model); assert.equal(model.snapshot().historyLocked, true);
    assert.match(model.snapshot().error, /HISTORY_SELECTION_IN_USE/);
    assert.equal(model.pending, null); readOnly(calls);
  });
});
