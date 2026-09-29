import { expect, test } from '@playwright/test';

const identity = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]];
const hash = 'a'.repeat(64);
function report() {
  return {
    schema: 'robot-scope.experimental-se3-benchmark.v1', experimental: true,
    generated_at: new Date().toISOString().replace(/\.\d{3}Z$/, 'Z'),
    data_kind: 'SYNTHETIC', source_commit: 'b'.repeat(40), source_tree_dirty: false,
    manifest_sha256: hash, module_sha256: hash, benchmark_sha256: hash,
    case_count: 1, candidate_count: 1, false_candidate_count: 0,
    expected_status_mismatch_count: 0, peak_rss_platform_units: 1024, platform: 'test-browser',
    cases: [{
      id: 'tilted-query', data_kind: 'SYNTHETIC', expected_status: 'CANDIDATE',
      target_sha256: hash, source_sha256: 'c'.repeat(64),
      initial_t_target_source: identity, truth_t_target_source: identity,
      target_preview_points: [[0, 0, 0], [1, 0, 0], [0, 1, 1]],
      source_preview_points: [[0, 0, 0], [1, 0, 0], [0, 1, 1]],
      se3_position_error_m: 0, se3_rotation_error_deg: 0,
      se3: {
        schema: 'robot-scope.experimental-se3-result.v1', experimental: true,
        status: 'CANDIDATE', reason: 'CANDIDATE', method: 'bounded-point-to-point-se3-icp',
        target_frame: 'map', source_frame: 'camera_init', query_stamp_ns: 1_000_000_000,
        transform_convention: 'T_target_source',
        pose: { x: 0, y: 0, z: 0, roll_rad: 0, pitch_rad: 0, yaw_rad: 0, quaternion_xyzw: [0, 0, 0, 1] },
        metrics: { converged: true, iterations: 2, overlap_ratio: 1, rmse_m: 0,
          geometry_min_max_eigen_ratio: 0.1, weak_geometry_direction_target: [0, 0, 1], runtime_ms: 12 },
      },
    }],
  };
}

function upload(page, id, value) {
  return page.locator(id).setInputFiles({ name: 'synthetic.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(value)) });
}

test('offline experiment viewer shows synthetic provenance and no control actions', async ({ page }) => {
  const failures = [];
  page.on('pageerror', (error) => failures.push(error.message));
  await page.goto('/static/experiments.html');
  await upload(page, '#candidateFile', report());
  await expect(page.locator('#experimentContent')).toBeVisible();
  await expect(page.locator('#dataKind')).toContainText('SYNTHETIC');
  await expect(page.locator('#caseDecision')).toContainText('CANDIDATE');
  await expect(page.locator('#truthError')).toContainText('동일 지도 합성 정답');
  await expect(page.getByText('ACTUAL_NAV2_NOT_RUN')).toBeVisible();
  await expect(page.locator('canvas')).toHaveCount(2);
  await upload(page, '#baselineFile', report());
  await expect(page.locator('#baselineMetric')).toContainText('Δ');
  expect(failures).toEqual([]);
});

test('viewer rejects a mismatched map digest and stale result', async ({ page }) => {
  await page.goto('/static/experiments.html');
  await upload(page, '#candidateFile', report());
  const other = report();
  other.cases[0].target_sha256 = 'd'.repeat(64);
  await upload(page, '#baselineFile', other);
  await expect(page.locator('#experimentStatus')).toContainText('지도 revision');
  await expect(page.locator('#experimentContent')).toBeHidden();
  const stale = report(); stale.generated_at = '2020-01-01T00:00:00Z';
  await upload(page, '#candidateFile', stale);
  await expect(page.locator('#experimentStatus')).toContainText('오래된');
});
