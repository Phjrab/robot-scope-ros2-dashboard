// Synthetic backend only. No camera, registration worker, or robot is contacted.
import { expect, test } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { installDashboardBackend } from './dashboard_backend.mjs';

test.use({ viewport: { width: 1500, height: 1900 } });
const root = '/api/v1/observations/global-jobs';
const map = { id: 'a'.repeat(24), revision: 'b'.repeat(64), frame_id: 'map', kind: 'pointcloud3d',
  name: 'SYNTHETIC global reference', format: 'pcd-binary', file_name: 'synthetic.pcd', point_count: 5, size_bytes: 1000 };
const second = { ...map, id: 'd'.repeat(24), revision: 'e'.repeat(64), name: 'SYNTHETIC second map' };
const flags = { historical_only: true, current_result: null, body_pose: null, tracking_verified: false,
  body_pose_verified: false, body_extrinsic_verified: false, operational_application: 'NOT_RUN', absolute_accuracy_m: null };
const context = { map_id: map.id, map_revision: map.revision, map_frame: 'map', source_frame: 'hesai_lidar',
  source_stamp_ns: '1792309179130175352', source_clock: 'UNVERIFIED', observer_id: 'synthetic', observer_epoch: 'synthetic-epoch' };
const baseJob = { schema: 'robot-scope.raw-global-observation-job.v1', job_id: 'c'.repeat(24), generation: 1,
  state: 'running', captured_context: context, worker_active: true, result: null, ...flags };
const result = { schema: 'robot-scope.raw-global-observation-result.v1', job_id: baseJob.job_id,
  generation: 1, captured_context: context, ...flags, observation: { status: 'OBSERVATION_ONLY_UNVERIFIED',
    selected_candidate: null, rejection_reasons: ['REFINEMENT_NOT_STATIONARY'], candidates: [
      { rmse_m: .07, overlap: .95, inlier_count: 15200, gate_reasons: ['RMSE_ABOVE_0.05M', 'REFINEMENT_NOT_STATIONARY'],
        map_from_scan: [[1,0,0,2],[0,1,0,3],[0,0,1,0],[0,0,0,1]] }],
    residual_comparison_scope: 'STORED_RMSE_ONLY_NO_GLOBAL_RESELECTION', residual_comparisons: [{ candidate_index: 0,
      evaluation: { rmse_m: .07, residual_passed: true, original_residual_passed: false,
        policy: { unit: 'm', max_rmse_m: .10 }, original_policy: { max_rmse_m: .05 },
        overall_candidate_acceptance_evaluated: false, overall_candidate_accepted: null } }] } };

async function fixture(page, { available = true, delay = false } = {}) {
  const state = { available, job: null, completed: false, cancelCount: 0, release: null }, writes = [], errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('request', r => { if (r.method() !== 'GET') writes.push({ path: new URL(r.url()).pathname, body: r.postDataJSON() }); });
  const backend = await installDashboardBackend(page);
  backend.on('/api/v1/saved-maps', ({ json }) => json({ maps: [map, second], total_size_bytes: 2000 }));
  for (const item of [map, second]) backend.on(`/api/v1/saved-maps/${item.id}/data`, ({ json }) => json({ ...item,
    map_id: item.id, seq: 1, points: [-2,-2,0,2,-2,0,2,2,0,-2,2,0,0,0,1], units: 'm', source_points: 5 }));
  const snapshot = () => {
    if (state.completed && state.job) state.job = { ...state.job, state: 'succeeded', worker_active: false, result, capture_age_s: 8.3 };
    return { schema: 'robot-scope.raw-global-observations.v1', provider: { available: state.available,
      reason: state.available ? null : 'TRUSTED_LOCAL_RUNNER_UNAVAILABLE', backend_id: 'SYNTHETIC_FIXTURE' }, generation: state.job?.generation || 0,
      active: state.job?.worker_active ? state.job : null, latest: state.job, ...flags };
  };
  backend.on(root, async ({ json, body, method }) => {
    if (method === 'POST') {
      state.job = { ...baseJob, request_id: body.request_id };
      if (delay) await new Promise(resolve => { state.release = resolve; });
      return json(state.job, 202);
    }
    return json(snapshot());
  });
  backend.on(`${root}/${baseJob.job_id}`, ({ json }) => { snapshot(); return json(state.job); });
  backend.on(`${root}/${baseJob.job_id}/cancel`, ({ json }) => {
    state.cancelCount++; state.completed = false; state.job = { ...state.job, state: 'cancelled', worker_active: false, result: null };
    return json(state.job);
  });
  await page.goto('/#maps');
  await page.evaluate(() => {
    const original = window.RobotScene3D.prototype.setPointCloud;
    window.RobotScene3D.prototype.setPointCloud = function (...args) {
      if (this.canvas.id === 'savedSceneCanvas') window.globalSavedScene = this;
      return original.apply(this, args);
    };
  });
  await page.locator('.saved-map-item').filter({ hasText: map.name }).click();
  await expect(page.locator('#savedGlobalProvider')).toContainText(available ? 'SYNTHETIC_FIXTURE' : 'TRUSTED_LOCAL_RUNNER_UNAVAILABLE');
  return { state, writes, errors };
}

test('provider absence is explicit and never starts a job', async ({ page }) => {
  const { writes, errors } = await fixture(page, { available: false });
  await expect(page.locator('#savedGlobalStart')).toBeDisabled();
  await expect(page.locator('#savedGlobalProvider')).toContainText('실행 불가');
  expect(writes).toEqual([]); expect(errors).toEqual([]);
});

test('synthetic historical result exports complete gates without changing the live scene', async ({ page }, testInfo) => {
  const { state, writes, errors } = await fixture(page);
  const before = await page.evaluate(() => ({ points: Array.from(window.globalSavedScene.cloud.points),
    pose: window.globalSavedScene.robotPose, overlay: window.globalSavedScene.pointCloudOverlay }));
  await page.locator('#savedGlobalStart').click();
  await expect(page.locator('#savedGlobalState')).toContainText('RUNNING');
  state.completed = true;
  await expect(page.locator('#savedGlobalSummary')).toContainText('원본 선택 후보 없음');
  await expect(page.locator('#savedGlobalSummary')).toContainText('REFINEMENT_NOT_STATIONARY');
  await expect(page.locator('#savedGlobalResidual')).toContainText('원본 5cm 미통과 · 잠정 10cm 통과');
  await expect(page.locator('#savedGlobalCapture')).toContainText('1792309179130175352 ns');
  await expect(page.locator('#savedGlobalCapture')).toContainText('8.300 s (원본 시계 신선도 아님)');
  const after = await page.evaluate(() => ({ points: Array.from(window.globalSavedScene.cloud.points),
    pose: window.globalSavedScene.robotPose, overlay: window.globalSavedScene.pointCloudOverlay }));
  expect(after).toEqual(before);
  const download = page.waitForEvent('download'); await page.locator('#savedGlobalExport').click();
  const file = await download, exported = JSON.parse(await readFile(await file.path(), 'utf8'));
  expect(exported.body_pose).toBeNull(); expect(exported.current_result).toBeNull();
  expect(exported.result.observation.candidates[0].gate_reasons).toContain('REFINEMENT_NOT_STATIONARY');
  expect(exported.result.observation.selected_candidate).toBeNull();
  await page.locator('#savedGlobalObservation').screenshot({ path: testInfo.outputPath('synthetic-historical-global.png') });
  expect(writes.map(w => w.path)).toEqual([root]); expect(errors).toEqual([]);
});

test('changing maps before a start response cancels late work and discards its result', async ({ page }) => {
  const { state, writes, errors } = await fixture(page, { delay: true });
  await page.locator('#savedGlobalStart').click(); await expect.poll(() => Boolean(state.release)).toBe(true);
  await page.locator('.saved-map-item').filter({ hasText: second.name }).click(); state.release();
  await expect.poll(() => state.cancelCount).toBe(1);
  await expect(page.locator('#savedGlobalExport')).toBeDisabled();
  await expect(page.locator('#savedGlobalRecord')).toHaveText('');
  expect(writes.map(w => w.path)).toEqual([root, `${root}/${baseJob.job_id}/cancel`]); expect(errors).toEqual([]);
});

test('capture details stay optional while historical limits and rejection remain visible', async ({ page }) => {
  const { state, writes, errors } = await fixture(page);
  const panel = page.locator('#savedGlobalObservation');
  const captureDetails = panel.locator('.saved-global-capture-details');
  await expect(panel.getByRole('heading', { name: '저장 3D 지도 · 전역 관측' })).toBeVisible();
  await expect(panel.getByText('과거 관측 · 운영 적용 없음', { exact: true })).toBeVisible();
  await expect(panel.locator('.saved-global-intro')).toContainText('본체 변환·추적·정밀 정확도는 미검증');
  await page.locator('#savedGlobalStart').click();
  await expect(page.locator('#savedGlobalState')).toContainText('RUNNING');
  await expect(page.locator('#savedGlobalCapture')).not.toBeVisible();
  await captureDetails.locator('summary').focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('#savedGlobalCapture')).toBeVisible();
  state.completed = true;
  await expect(page.locator('#savedGlobalCapture')).toContainText('8.300 s');
  await expect(captureDetails).toHaveAttribute('open', '');
  await captureDetails.locator('summary').focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('#savedGlobalCapture')).not.toBeVisible();
  await expect(page.locator('#savedGlobalSummary')).toBeVisible();
  await expect(page.locator('#savedGlobalSummary')).toContainText('REFINEMENT_NOT_STATIONARY');
  await expect(panel.locator('.saved-global-safety-note')).toBeVisible();
  await expect(panel.locator('.saved-global-safety-note')).toContainText('현재 위치·본체 pose·추적으로 적용하지 않습니다');
  for (const [theme, width] of [['dark', 1440], ['light', 390]]) {
    await page.setViewportSize({ width, height: 900 });
    await page.evaluate(value => document.documentElement.dataset.theme = value, theme);
    const geometry = await panel.evaluate(element => ({
      width: element.clientWidth, scroll: element.scrollWidth,
      noteColor: getComputedStyle(element.querySelector('.saved-global-safety-note')).color,
      muted: getComputedStyle(element).getPropertyValue('--muted').trim(),
    }));
    expect(geometry.scroll).toBeLessThanOrEqual(geometry.width + 1);
    const mutedColor = await page.evaluate(color => {
      const probe = document.createElement('span'); probe.style.color = color; document.body.append(probe);
      const rendered = getComputedStyle(probe).color; probe.remove(); return rendered;
    }, geometry.muted);
    expect(geometry.noteColor).toBe(mutedColor);
  }
  expect(writes.map(w => w.path)).toEqual([root]); expect(errors).toEqual([]);
});
