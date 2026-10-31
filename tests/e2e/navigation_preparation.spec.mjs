// DOM and HTTP fixtures only: no ROS, control bridge or robot consumer.
import { expect, test } from '@playwright/test';

const cloud = { id: 'a'.repeat(24), revision: 'b'.repeat(64), kind: 'pointcloud3d', name: 'map1' };
const grid = { id: 'c'.repeat(24), revision: 'd'.repeat(64), kind: 'occupancy2d', name: 'map1_2D', frame_id: 'map' };

async function fixture(page) {
  const state = { selected: null, pair: null, runtime: null }, writes = [];
  let reject = false, failingReads = 0, heldWrites = null, releaseWrite = null;
  await page.route('**/software-preparation.html', route => route.fulfill({ contentType: 'text/html', body: `<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="/styles.css"><main style="padding:24px"><label>3D 위치추정 지도<select id="cloud"></select></label><label>2D 경로 계산 지도<select id="grid"><option>${grid.name}</option></select></label><article class="panel navigation-preparation-panel" id="host"></article></main>` }));
  await page.route('**/api/v1/navigation/operational-3d**', async route => {
    const path = new URL(route.request().url()).pathname, method = route.request().method();
    const body = route.request().postDataJSON();
    const json = (value, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(value) });
    if (method !== 'GET') writes.push({ path, method, body });
    if (method === 'GET' && failingReads > 0) { failingReads--; return json({ detail: 'SYNTHETIC_READ_TIMEOUT' }, 503); }
    if (method !== 'GET' && heldWrites) await heldWrites;
    if (reject && method !== 'GET') return json({ detail: 'PAIR_COORDINATE_RELATION_UNVERIFIED' }, 409);
    if (path.endsWith('/pair')) {
      state.selected = { workflow: 'staged_navigation_pair', generation: 'pairgen',
        localization_3d: { map_id: cloud.id, revision: cloud.revision }, navigation_2d: { map_id: grid.id, revision: grid.revision },
        calibration: { verified: true }, seed_geometry: null };
      state.pair = { can_start: false };
    }
    if (path.endsWith('/seed-geometry')) { state.selected.seed_geometry = { ...body, source: 'USER_CONFIRMED_NAV_BASE', confirmed_at: 1793444400 }; state.pair.can_start = true; }
    if (method === 'DELETE') { state.selected = null; state.pair = null; }
    return json(state);
  });
  await page.goto('/software-preparation.html');
  await page.evaluate(async ({ cloud, grid }) => {
    const { initializeNavigationPreparation } = await import('/features/navigation/preparation.js');
    window.fixtureContext = { maps: [cloud, grid], map: grid, navigation: { pipeline: { state: 'idle' }, goal: { state: 'idle' } } };
    window.fixtureActions = [];
    window.preparation = initializeNavigationPreparation({ host: document.querySelector('#host'), map3dSelect: document.querySelector('#cloud'), map2dSelect: document.querySelector('#grid'),
      api: async (path, options) => { const response = await fetch(path, options); const value = await response.json(); if (!response.ok) throw new Error(value.detail); return value; },
      context: () => window.fixtureContext, onChange: () => {},
      actions: Object.fromEntries(['start', 'initial', 'goal', 'refresh'].map(key => [key, () => window.fixtureActions.push(key)])) });
    window.preparation.render(); await window.preparation.refresh(true);
  }, { cloud, grid });
  return { state, writes, reject(value) { reject = value; }, failReads(count) { failingReads = count; },
    holdWrites() { heldWrites = new Promise(resolve => { releaseWrite = resolve; }); },
    releaseWrites() { releaseWrite?.(); heldWrites = null; releaseWrite = null; } };
}

test('map selection is passive, missing geometry is explicit, retry resumes without repeated pair application', async ({ page }) => {
  const f = await fixture(page);
  await page.getByLabel('3D 위치추정 지도').selectOption(cloud.id);
  expect(f.writes).toHaveLength(0);
  expect(await page.evaluate(() => window.fixtureActions)).toEqual([]);
  await page.getByRole('button', { name: '① 지도 연결 확인·적용' }).click();
  await expect(page.getByRole('region', { name: '준비 상태·해결할 항목' })).toContainText('초기 높이·기울기 미확인');
  await expect(page.getByRole('button', { name: 'Nav2 시작', exact: true })).toBeDisabled();
  await page.getByText('② 초기 높이·기울기 입력', { exact: true }).click();
  await page.getByRole('button', { name: '초기 높이·기울기 저장' }).click();
  await expect(page.getByRole('region', { name: '준비 상태·해결할 항목' })).toContainText('빈 값은 0으로 처리하지 않습니다');
  expect(f.writes).toHaveLength(1);
  await page.getByLabel('높이 z (m)').fill('0.34');
  await page.getByLabel('roll (rad)', { exact: true }).fill('0.01');
  await page.getByLabel('pitch (rad)', { exact: true }).fill('-0.02');
  await page.getByRole('button', { name: '초기 높이·기울기 저장' }).click();
  await expect(page.getByRole('button', { name: 'Nav2 시작', exact: true })).toBeEnabled();
  expect(f.writes.map(value => value.path)).toEqual(['/api/v1/navigation/operational-3d/pair', '/api/v1/navigation/operational-3d/seed-geometry']);
  expect(f.writes[1].body).toEqual({ generation: 'pairgen', z: .34, roll: .01, pitch: -.02 });
  expect(await page.evaluate(() => window.fixtureActions)).toEqual([]);
  await page.getByRole('button', { name: 'Nav2 시작', exact: true }).click();
  expect(await page.evaluate(() => window.fixtureActions)).toEqual(['start']);
});

test('server rejection stays visible and exact pair can be rechecked; active runtime locks maps', async ({ page }) => {
  const f = await fixture(page);
  await page.getByLabel('3D 위치추정 지도').selectOption(cloud.id);
  f.reject(true);
  await page.getByRole('button', { name: '① 지도 연결 확인·적용' }).click();
  await expect(page.getByRole('region', { name: '준비 상태·해결할 항목' })).toContainText('PAIR_COORDINATE_RELATION_UNVERIFIED');
  f.reject(false);
  await page.getByRole('button', { name: '① 지도 연결 확인·적용' }).click();
  await expect(page.locator('[data-prep="selected"]')).toContainText('서버 준비 구성: map1 / map1_2D');
  await page.evaluate(() => { window.fixtureContext.navigation.pipeline.state = 'running'; window.preparation.render(); });
  await expect(page.getByLabel('3D 위치추정 지도')).toBeDisabled();
  await expect(page.getByRole('button', { name: '① 지도 연결 확인·적용' })).toBeDisabled();
  await expect(page.getByRole('button', { name: '기존 2D 모드로 복구' })).toBeDisabled();
  await page.evaluate(() => { window.fixtureContext.navigation.pipeline.state = 'idle'; window.preparation.render(); });
  await page.getByRole('button', { name: '기존 2D 모드로 복구' }).click();
  await expect(page.getByLabel('3D 위치추정 지도')).toHaveValue('');
  expect(f.writes.at(-1).method).toBe('DELETE');
});

test('initial receipt requires explicit match and ready receipt never sends a goal; stale remains visible', async ({ page }) => {
  const f = await fixture(page);
  await page.getByLabel('3D 위치추정 지도').selectOption(cloud.id);
  await page.getByRole('button', { name: '① 지도 연결 확인·적용' }).click();
  f.state.selected.seed_geometry = { z: .34, roll: 0, pitch: 0, source: 'operator', confirmed_at: 1793444400 };
  f.state.pair.can_start = true;
  await page.evaluate(() => window.preparation.refresh(true));
  await page.evaluate(({ cloud, grid }) => {
    const pin = { map_id: grid.id, map_revision: grid.revision, localization_map_id: cloud.id, localization_map_revision: cloud.revision,
      bundle_generation: 'pairgen', localization_generation: 2, runtime_instance_generation: 'process',
      pose: { x: 1, y: 2, z: .34, roll: 0, pitch: 0, yaw: 1 }, stamp_ns: '123' };
    Object.assign(window.fixtureContext.navigation, { map: grid, pipeline: { state: 'running', job_id: 'job' },
      safety: { can_set_initial_pose: true, can_send_goal: false }, operational_localization: {
        ...pin, source: 'STORED_PCD_FASTLIO', fresh: true, ready: false, state: 'WAITING_EXPLICIT_MAP_MATCH', correction_sequence: 0,
        accepted_initial_pose: { ...pin, accepted: true } } });
    window.preparation.render();
  }, { cloud, grid });
  await expect(page.getByRole('button', { name: '정합 시작', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: '정합 시작', exact: true }).click();
  expect(f.writes.at(-1).body).toEqual({ map_id: grid.id, map_revision: grid.revision, bundle_generation: 'pairgen', localization_generation: 2, initial_pose_stamp_ns: '123' });
  await page.evaluate(() => {
    const nav = window.fixtureContext.navigation, source = nav.operational_localization;
    source.estimated_pose = { ...source.accepted_initial_pose, pose: { ...source.accepted_initial_pose.pose, x: 1.04 }, stale: false };
    source.state = 'MAP_TRACKING'; source.ready = true; source.correction_sequence = 4;
    nav.safety.can_send_goal = true; window.preparation.render();
  });
  await expect(page.getByRole('button', { name: 'GOAL POSE 지정' })).toBeEnabled();
  expect(await page.evaluate(() => window.fixtureActions)).toEqual([]);
  await page.evaluate(() => { const source = window.fixtureContext.navigation.operational_localization; source.ready = false; source.estimated_pose.stale = true; source.state = 'MAP_CORRECTION_STALE'; window.preparation.render(); });
  await expect(page.getByRole('button', { name: 'GOAL POSE 지정' })).toBeDisabled();
  await expect(page.locator('[data-prep="steps"]')).toContainText('마지막 추정 위치');
  await page.locator('#host').screenshot({ path: 'test-results/navigation-preparation-stale.png' });
  expect(f.writes.filter(write => write.path.endsWith('/goal'))).toHaveLength(0);
});

test('server checks invalidate only their dependent stages and current execution ignores a previous success', async ({ page }) => {
  const f = await fixture(page);
  await page.getByLabel('3D 위치추정 지도').selectOption(cloud.id);
  await page.getByRole('button', { name: '① 지도 연결 확인·적용' }).click();
  f.state.pair = { valid: false, can_start: false, restart_from_step: 1,
    checks: [{ code: 'MAP_PAIR_LINEAGE_CHANGED', current: '변환 계보가 변경됨', required: '현재 연결 검증', remedy: '①부터 다시 확인' }] };
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="issues"]')).toContainText('변환 계보가 변경됨');
  await expect(page.locator('[data-prep="steps"] > li').nth(0)).toHaveAttribute('data-state', '오류');
  f.state.selected.seed_geometry = { z: .34, roll: 0, pitch: 0 };
  f.state.pair = { valid: true, can_start: false, restart_from_step: 2,
    checks: [{ code: 'INITIAL_GEOMETRY_RECONFIRM_REQUIRED', current: '이전 실행에서 사용한 높이', required: '현재 값', remedy: '②에서 재확인' }] };
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="steps"] > li').nth(0)).toHaveAttribute('data-state', '완료');
  await expect(page.locator('[data-prep="steps"] > li').nth(1)).toHaveAttribute('data-state', '사용자 입력 필요');
  await expect(page.locator('[data-prep="issues"]')).toContainText('이전 실행에서 사용한 높이');
  await page.evaluate(({ grid }) => {
    const nav = window.fixtureContext.navigation;
    nav.pipeline = { state: 'running', job_id: 'new-job' }; nav.map = grid;
    nav.goal = { state: 'succeeded', goal_id: 'previous', precision_evidence: { goal_id: 'previous', context: { job_id: 'old-job', map_id: grid.id, map_revision: grid.revision } } };
    window.preparation.render();
  }, { grid });
  await expect(page.locator('[data-prep="steps"] > li').nth(6)).toHaveAttribute('data-state', '미시작');
  expect(f.writes).toHaveLength(1);
});

test('automatic fresh status clears a recovered read failure without losing the current preparation step', async ({ page }) => {
  const f = await fixture(page);
  await page.getByLabel('3D 위치추정 지도').selectOption(cloud.id);
  await page.getByRole('button', { name: '① 지도 연결 확인·적용' }).click();
  await expect(page.locator('[data-prep="current"]')).toContainText('현재 단계: 2.');
  f.failReads(1);
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="issues"]')).toContainText('상태 확인 실패: SYNTHETIC_READ_TIMEOUT');
  // The dashboard calls this same refresh from its periodic navigation reads.
  // There is no operator click, pose input, or write retry after the failure.
  await page.evaluate(() => { window.fixturePolling = setInterval(() => window.preparation.refresh(), 100); });
  await expect(page.locator('[data-prep="issues"]')).not.toContainText('상태 확인 실패');
  await expect(page.locator('[data-prep="issues"]')).not.toContainText('현재 준비 상태 수신 실패');
  await expect(page.locator('[data-prep="current"]')).toContainText('현재 단계: 2.');
  await expect(page.locator('[data-prep="current"]')).toContainText('사용자 입력 필요');
  await expect(page.getByRole('button', { name: 'Nav2 시작', exact: true })).toBeDisabled();
  expect(f.writes).toHaveLength(1);
  expect(await page.evaluate(() => window.fixtureActions)).toEqual([]);
  await page.evaluate(() => clearInterval(window.fixturePolling));
});

test('pending apply visibly checks its step and later fresh reads retain action rejection evidence', async ({ page }) => {
  const f = await fixture(page);
  await page.getByLabel('3D 위치추정 지도').selectOption(cloud.id);
  f.holdWrites();
  await page.getByRole('button', { name: '① 지도 연결 확인·적용' }).click();
  await expect(page.locator('[data-prep="current"]')).toHaveText('현재 단계: 1. 지도 선택·연결 확인 · 확인 중');
  await expect(page.getByRole('button', { name: '① 지도 연결 확인·적용' })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Nav2 시작', exact: true })).toBeDisabled();
  expect(await page.evaluate(() => window.preparation.canStart())).toBe(false);
  f.reject(true); f.releaseWrites();
  await expect(page.locator('[data-prep="issues"]')).toContainText('PAIR_COORDINATE_RELATION_UNVERIFIED');
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="issues"]')).toContainText('PAIR_COORDINATE_RELATION_UNVERIFIED');
  expect(f.writes).toHaveLength(1);
  expect(await page.evaluate(() => window.fixtureActions)).toEqual([]);
});
