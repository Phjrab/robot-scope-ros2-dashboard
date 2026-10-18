import assert from 'node:assert/strict';
import test from 'node:test';
import { recordedFixture } from './recorded_se3_fixture.mjs';
import { createRecordedLoader, identity, isRigidTransform, matrixPose, recordedState, replayGeometry, validateRecordedReport } from '../robot_dashboard/static/features/experiments/recorded_report.js';
import { validateExperimentReport } from '../robot_dashboard/static/features/experiments/report.js';

test('recorded diagnostic accepts rejected results without upgrading postmetric', () => {
  const r = validateRecordedReport(recordedFixture());
  assert.equal(r.result.status, 'REJECTED');
  assert.equal(r.result.full_reference_metrics.rmse_m, .03);
  assert.throws(() => validateExperimentReport(r));
  assert.equal(recordedState(r), 'ARCHIVED_NOT_LIVE');
  assert.equal(recordedState(null), 'NO_DATA');
  r.result = null; assert.equal(recordedState(validateRecordedReport(r)), 'NO_RESULT');
});
test('candidate gates and frame/time/coordinate contracts are independent of visualization', () => {
  const changes = [
    r => { r.source.stamp_ns = Number(r.source.stamp_ns); },
    r => { r.source.session_id = r.target.session_id; },
    r => { r.source.point_semantics = 'RAW_SENSOR'; },
    r => { r.trajectory.frame_id = 'base_link'; },
    r => { r.trajectory.session_id = 'different'; },
    r => { r.source.points[0][2] = NaN; },
    r => { r.result.T_target_source[0][0] = 2; },
    r => { r.result.full_reference_metrics.reference_points = 999; },
    r => { r.result.status = 'CANDIDATE'; r.result.reason = 'CANDIDATE'; },
    r => { r.live_verification = 'PASS'; },
    r => { r.absolute_accuracy_m = .03; },
  ];
  for (const change of changes) { const r = recordedFixture(); change(r); assert.throws(() => validateRecordedReport(r)); }
  const c = recordedFixture(); c.result.status = c.result.reason = 'CANDIDATE'; c.result.solver_metrics.rmse_m = .04;
  assert.equal(validateRecordedReport(c).result.status, 'CANDIDATE');
  c.result.converged = false; assert.throws(() => validateRecordedReport(c));
});
test('before/after use source transform once and compose body relation in the right order', () => {
  const r = recordedFixture();
  assert.deepEqual(replayGeometry(r, false).query, r.source.points);
  assert.equal(replayGeometry(r).poseKind, 'QUERY_ORIGIN_REFERENCE');
  assert.deepEqual(replayGeometry(r).query[0], r.target.points[0]);
  r.result.T_target_source = [[0, -1, 0, 1], [1, 0, 0, 2], [0, 0, 1, 3], [0, 0, 0, 1]];
  r.body_relation = { verified: false, source_frame: r.source.frame_id, source_session: r.source.session_id,
    body_frame: 'base_link', provenance: 'synthetic offset, not calibration', T_source_body: identity() };
  r.body_relation.T_source_body[0][3] = .25;
  const g = replayGeometry(validateRecordedReport(r));
  assert.equal(g.poseKind, 'UNVERIFIED_BODY_CANDIDATE');
  assert.deepEqual([g.pose.x, g.pose.y, g.pose.z], [1, 2.25, 3]);
  assert.equal(g.pose.yaw, Math.PI / 2);
  r.body_relation.verified = true; assert.throws(() => validateRecordedReport(r));
});
test('archive age follows capture time, cannot be refreshed by rewriting report time', () => {
  const r = recordedFixture(); r.captured_at = '2020-01-01T00:00:00Z';
  assert.equal(recordedState(validateRecordedReport(r)), 'STALE_RECORDING');
  r.generated_at = 'invalid'; assert.throws(() => validateRecordedReport(r));
});
test('6DoF matrix conversion retains roll and pitch, rejects reflected/scaled matrices', () => {
  const m = [[0, 0, 1, 1], [0, 1, 0, 2], [-1, 0, 0, 3], [0, 0, 0, 1]];
  assert.equal(isRigidTransform(m), true);
  assert.equal(matrixPose(m, 'map').pitch, Math.PI / 2);
  const roll = [[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]];
  assert.equal(matrixPose(roll, 'map').roll, Math.PI / 2);
  m[0][2] = -1; assert.equal(isRigidTransform(m), false);
});
test('new input clears previous results; late success/failure cannot resurrect or erase newer input', async () => {
  let finish, fail;
  const changes = [];
  const load = createRecordedLoader((...args) => changes.push(args));
  const a = load({ size: 10, text: () => new Promise(resolve => { finish = resolve; }) });
  const b = load({ size: 10, text: () => new Promise((_, reject) => { fail = reject; }) });
  await load({ size: 10, text: async () => JSON.stringify(recordedFixture()) });
  assert.equal(changes.at(-1)[0].result.status, 'REJECTED');
  finish(JSON.stringify(recordedFixture())); await a;
  fail(new Error('old failure')); await b;
  assert.equal(changes.length, 4);
  await load({ size: 10, text: async () => '{' });
  assert.equal(changes.at(-1)[1], 'INVALID'); assert.equal(changes.at(-1)[0], null);
  await load(null); assert.equal(changes.at(-1)[1], 'NO_DATA');
});
