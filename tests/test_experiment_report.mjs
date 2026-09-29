import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import {
  compareExperimentReports, poseMatrix, transformPreview, validateExperimentReport,
} from '../robot_dashboard/static/features/experiments/report.js';

const matrix = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]];
const sha = 'a'.repeat(64);
const result = () => ({
  schema: 'robot-scope.experimental-se3-result.v1', experimental: true,
  status: 'CANDIDATE', reason: 'CANDIDATE', method: 'bounded-point-to-point-se3-icp',
  target_frame: 'map', source_frame: 'camera_init', query_stamp_ns: 1_000_000_000,
  transform_convention: 'T_target_source',
  pose: { x: 0, y: 0, z: 0, roll_rad: 0, pitch_rad: 0, yaw_rad: 0, quaternion_xyzw: [0, 0, 0, 1] },
  metrics: { converged: true, iterations: 2, overlap_ratio: 1, rmse_m: 0,
    geometry_min_max_eigen_ratio: 0.1, weak_geometry_direction_target: [0, 0, 1], runtime_ms: 12 },
});
const report = () => ({
  schema: 'robot-scope.experimental-se3-benchmark.v1', experimental: true,
  generated_at: '2026-09-30T00:00:00Z', data_kind: 'SYNTHETIC', source_commit: 'b'.repeat(40),
  manifest_sha256: sha, module_sha256: sha, benchmark_sha256: sha,
  source_tree_dirty: false, case_count: 1, candidate_count: 1, false_candidate_count: 0,
  expected_status_mismatch_count: 0, peak_rss_platform_units: 1024, platform: 'unit-test',
  cases: [{ id: 'tilted-query', data_kind: 'SYNTHETIC', expected_status: 'CANDIDATE', target_sha256: sha,
    source_sha256: 'c'.repeat(64), initial_t_target_source: structuredClone(matrix),
    target_preview_points: [[0, 0, 0], [1, 0, 0]], source_preview_points: [[0, 0, 0]],
    truth_t_target_source: structuredClone(matrix), se3_position_error_m: 0, se3_rotation_error_deg: 0, se3: result() }],
});
const now = Date.parse('2026-09-30T12:00:00Z');

test('read-only synthetic report validates and aligns a same-input baseline', () => {
  const before = validateExperimentReport(report(), now);
  const after = validateExperimentReport(report(), now);
  assert.equal(compareExperimentReports(before, after), true);
  assert.deepEqual(transformPreview([[1, 2, 3]], poseMatrix(before.cases[0].se3.pose)), [[1, 2, 3]]);
});

test('live label, stale artifact, malformed points and truth-less accuracy fail closed', () => {
  const live = report(); live.data_kind = 'LIVE_VERIFIED';
  assert.throws(() => validateExperimentReport(live, now), /지원되지/);
  assert.throws(() => validateExperimentReport(report(), now + 31 * 86400_000), /오래된/);
  const malformed = report(); malformed.cases[0].target_preview_points[0][0] = Number.NaN;
  assert.throws(() => validateExperimentReport(malformed, now), /잘못/);
  const noTruth = report(); delete noTruth.cases[0].truth_t_target_source;
  assert.throws(() => validateExperimentReport(noTruth, now), /잘못/);
});

test('different target revision, query, seed or manifest cannot be compared', () => {
  const baseline = validateExperimentReport(report(), now);
  for (const change of [
    (value) => { value.manifest_sha256 = 'd'.repeat(64); },
    (value) => { value.cases[0].target_sha256 = 'd'.repeat(64); },
    (value) => { value.cases[0].source_sha256 = 'd'.repeat(64); },
    (value) => { value.cases[0].initial_t_target_source[0][3] = 1; },
  ]) {
    const candidate = report(); change(candidate);
    assert.throws(() => compareExperimentReports(baseline, validateExperimentReport(candidate, now)));
  }
});

test('experiment page is local-file-only and separate from control and cockpit', () => {
  const html = readFileSync(new URL('../robot_dashboard/static/experiments.html', import.meta.url), 'utf8');
  const view = readFileSync(new URL('../robot_dashboard/static/features/experiments/view.js', import.meta.url), 'utf8');
  const index = readFileSync(new URL('../robot_dashboard/static/index.html', import.meta.url), 'utf8');
  assert.match(index, /href="\/static\/experiments\.html"/);
  assert.match(html, /OFFLINE EXPERIMENTS · READ ONLY/);
  assert.match(html, /ACTUAL_NAV2_NOT_RUN/);
  assert.match(view, /await file\.text\(\)/);
  assert.doesNotMatch(view, /fetch\(|XMLHttpRequest|WebSocket|\/api\/|initialpose|cmd_vel|MissionCoordinator|lease|ARM|deadman/);
  assert.doesNotMatch(html, /<button/);
});
