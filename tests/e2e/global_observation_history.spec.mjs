// Synthetic HTTP/WebSocket fixtures only. This never contacts a robot or a native worker.
import { expect, test } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { installDashboardBackend } from './dashboard_backend.mjs';

test.use({ viewport: { width: 1500, height: 1900 } });
const ROOT = '/api/v1/observations/global-jobs';
const ID = 'c'.repeat(24), OTHER = 'd'.repeat(24);
const map = { id: 'a'.repeat(24), revision: 'b'.repeat(64), frame_id: 'camera_init', kind: 'pointcloud3d',
  name: 'SYNTHETIC retained 3D map', format: 'pcd-binary', file_name: 'synthetic-retained.pcd', point_count: 5, size_bytes: 1000 };
const flags = { historical_only: true, current_result: null, body_pose: null, tracking_verified: false,
  body_pose_verified: false, body_extrinsic_verified: false, operational_application: 'NOT_RUN', absolute_accuracy_m: null };
const capture = { map_id: map.id, map_revision: map.revision, map_frame: map.frame_id,
  source_frame: 'hesai_lidar', observer_id: 'synthetic', observer_epoch: 'synthetic-epoch',
  source_stamp_ns: '1792678892357536793', source_clock: 'UNVERIFIED', source_pipeline_stage: 'converted' };
function completed(id = ID, generation = 1) {
  return { schema: 'robot-scope.raw-global-observation-job.v1', job_id: id, generation,
    request_id: `synthetic-${id}`, state: 'succeeded', worker_active: false, capture_age_s: 7200,
    captured_context: structuredClone(capture), ...flags, result: {
      schema: 'robot-scope.raw-global-observation-result.v1', job_id: id, generation,
      captured_context: structuredClone(capture), ...flags, observation: { status: 'OBSERVATION_ONLY_UNVERIFIED',
        selected_candidate: 0, rejection_reasons: ['AMBIGUOUS_ALTERNATIVES'], candidates: [
          { rmse_m: .230319, overlap: .90325, inlier_count: 14452, gate_reasons: ['AMBIGUOUS_ALTERNATIVES'],
            map_from_scan: [[1,0,0,2],[0,1,0,3],[0,0,1,0],[0,0,0,1]] }] } } };
}

async function fixture(page) {
  const state = { latest: completed(), generation: 1, detailFailure: null, detail: completed() };
  const reads = [], writes = [], errors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {
    const path = new URL(request.url()).pathname;
    if (request.method() !== 'GET') writes.push({ path, method: request.method() });
    else if (path.startsWith(ROOT)) reads.push(path);
  });
  const backend = await installDashboardBackend(page);
  backend.on('/api/v1/saved-maps', ({ json }) => json({ maps: [map], total_size_bytes: 1000 }));
  backend.on(`/api/v1/saved-maps/${map.id}/data`, ({ json }) => json({ ...map, map_id: map.id,
    seq: 1, points: [-2,-2,0,2,-2,0,2,2,0,-2,2,0,0,0,1], units: 'm', source_points: 5 }));
  backend.on(ROOT, ({ json }) => json({ schema: 'robot-scope.raw-global-observations.v1',
    provider: { available: true, backend_id: 'SYNTHETIC_HISTORY_FIXTURE' }, generation: state.generation,
    closed: false, active: null, latest: state.latest, ...flags }));
  for (const id of [ID, OTHER]) backend.on(`${ROOT}/${id}`, ({ route, json }) => {
    if (state.detailFailure === 'network') return route.abort('connectionfailed');
    if (state.detailFailure === 'missing') return json({ detail: 'synthetic job not found' }, 404);
    return json(state.detail);
  });
  await page.goto('/#maps'); await selectMap(page);
  return { state, reads, writes, errors };
}
async function selectMap(page) {
  await page.locator('.saved-map-item').filter({ hasText: map.name }).click();
  await expect(page.locator('#savedGlobalProvider')).toContainText('SYNTHETIC_HISTORY_FIXTURE');
  await expect(page.locator('#savedGlobalHistory')).toHaveValue(ID);
}
async function openListed(page) {
  await page.locator('#savedGlobalHistory').selectOption(ID);
  await page.locator('#savedGlobalHistoryOpen').click();
  await expect(page.locator('#savedGlobalSummary')).toContainText('AMBIGUOUS_ALTERNATIVES');
}

test('explicit saved-result open survives a page reload without any mutation or automatic tracking', async ({ page }, testInfo) => {
  const { reads, writes, errors } = await fixture(page);
  await expect(page.locator('#savedGlobalRecord')).toHaveText('');
  await expect(page.locator('#savedGlobalExport')).toBeDisabled();
  expect(reads.filter(path => path === `${ROOT}/${ID}`)).toEqual([]);
  await openListed(page);
  await expect(page.locator('#savedGlobalHistoryStatus')).toContainText(ID);
  await expect(page.locator('#savedGlobalState')).toContainText('HISTORICAL_ONLY');
  await expect(page.locator('#savedGlobalCapture')).toContainText('7200.000 s (원본 시계 신선도 아님)');
  await expect(page.locator('#savedGlobalCapture')).toContainText(capture.source_stamp_ns);
  await expect(page.locator('#savedGlobalSummary')).toContainText('현재 pose·본체 pose·추적으로 적용하지 않습니다');
  await page.locator('#savedGlobalDetails').evaluate(element => { element.open = true; });
  await expect(page.locator('#savedGlobalRecord')).toContainText('0.230319');
  await expect(page.locator('#savedGlobalRecord')).toContainText('0.90325');
  await expect(page.locator('#savedGlobalObservation')).toContainText('본체 변환·추적·정밀 정확도는 미검증입니다');
  const download = page.waitForEvent('download'); await page.locator('#savedGlobalExport').click();
  const file = await download, exported = JSON.parse(await readFile(await file.path(), 'utf8'));
  expect(exported.job_id).toBe(ID); expect(exported.historical_only).toBe(true);
  expect(exported.current_result).toBeNull(); expect(exported.body_pose).toBeNull();
  await page.reload(); await selectMap(page);
  await expect(page.locator('#savedGlobalRecord')).toHaveText('');
  await openListed(page);
  await page.locator('#savedGlobalObservation').screenshot({ path: testInfo.outputPath('synthetic-history-reopened.png') });
  expect(reads.filter(path => path === `${ROOT}/${ID}`)).toHaveLength(2);
  expect(writes).toEqual([]); expect(errors).toEqual([]);
});

test('typed historical ID and refresh only read; changed input clears previous output before a missing result', async ({ page }) => {
  const { state, reads, writes, errors } = await fixture(page);
  await openListed(page);
  const beforeRefresh = reads.filter(path => path === ROOT).length;
  await page.locator('#savedGlobalHistoryRefresh').click();
  await expect.poll(() => reads.filter(path => path === ROOT).length).toBeGreaterThan(beforeRefresh);
  await page.locator('#savedGlobalHistoryId').fill(OTHER);
  await expect(page.locator('#savedGlobalRecord')).toHaveText('');
  await expect(page.locator('#savedGlobalExport')).toBeDisabled();
  expect(reads.filter(path => path === `${ROOT}/${OTHER}`)).toHaveLength(0);
  state.detailFailure = 'missing';
  await page.locator('#savedGlobalHistoryOpen').click();
  await expect(page.locator('#savedGlobalState')).toContainText('synthetic job not found');
  await expect(page.locator('#savedGlobalRecord')).toHaveText('');
  await expect(page.locator('#savedGlobalSummary')).toHaveText('');
  await expect(page.locator('#savedGlobalExport')).toBeDisabled();
  expect(reads.filter(path => path === `${ROOT}/${OTHER}`)).toHaveLength(1);
  expect(writes).toEqual([]); expect(errors).toEqual([]);
});

test('old generation remains historical display only and mismatched context cannot reappear after refresh', async ({ page }) => {
  const { state, writes, errors } = await fixture(page);
  state.generation = 2;
  await openListed(page);
  await expect(page.locator('#savedGlobalHistoryStatus')).toContainText('현재 서버 세대와 다름');
  state.detail = completed(); state.detail.result.captured_context.map_revision = 'e'.repeat(64);
  await page.locator('#savedGlobalHistoryId').fill(ID);
  await page.locator('#savedGlobalHistoryOpen').click();
  await expect(page.locator('#savedGlobalState')).toContainText('CONTRACT_MISMATCH');
  await expect(page.locator('#savedGlobalRecord')).toHaveText('');
  await page.locator('#savedGlobalHistoryRefresh').click();
  await expect(page.locator('#savedGlobalRecord')).toHaveText('');
  await expect(page.locator('#savedGlobalSummary')).toHaveText('');
  expect(writes).toEqual([]); expect(errors).toEqual([]);
});

test('a saved failed terminal job displays its original reason without exporting a result or starting work', async ({ page }) => {
  const { state, writes, errors } = await fixture(page);
  state.detail = { ...completed(), state: 'failed', result: null, reason: 'SYNTHETIC_CAPTURE_FAILED' };
  state.latest = structuredClone(state.detail);
  await page.locator('#savedGlobalHistoryRefresh').click();
  await expect(page.locator('#savedGlobalHistory option')).toContainText('FAILED');
  await page.locator('#savedGlobalHistoryOpen').click();
  await expect(page.locator('#savedGlobalState')).toContainText('FAILED');
  await expect(page.locator('#savedGlobalHistoryStatus')).toContainText(ID);
  await expect(page.locator('#savedGlobalObservation')).toContainText('SYNTHETIC_CAPTURE_FAILED');
  await expect(page.locator('#savedGlobalRecord')).toHaveText('');
  await expect(page.locator('#savedGlobalExport')).toBeDisabled();
  expect(writes).toEqual([]); expect(errors).toEqual([]);
});
