// Software-only DOM and HTTP fixtures. No ROS, robot or hardware consumer runs.
import { expect, test } from '@playwright/test';

const sourceId = 'a'.repeat(24), sourceRevision = 'b'.repeat(64);
const navId = 'c'.repeat(24), navRevision = 'd'.repeat(64);
const missionId = 'e'.repeat(32), confirmation = 'f'.repeat(32);
const sourceSeed = {
  map: { id: sourceId, revision: sourceRevision, frame: 'map' },
  pose: { x: 1.25, y: -2.5, z: .3, roll: .1, pitch: -.2, yaw: .4 },
  course: { map_id: sourceId, map_revision: sourceRevision, map_frame: 'map',
    polygon: [[0, 0], [3, 0], [3, 3]], outside_weight: .5, confirmed: true, units: 'm' },
};

async function blank(page) {
  await page.route('**/operational-software-fixture.html', route => route.fulfill({
    contentType: 'text/html', body: '<!doctype html><title>SOFTWARE FIXTURE · no robot</title><main id="fixture"></main>',
  }));
  await page.goto('/operational-software-fixture.html');
}

async function mapsFixture(page, { seed = sourceSeed, calibration = true } = {}) {
  const writes = [], state = { selected: null, calibration_available: calibration, runtime: null, runtime_fresh: false };
  const initial = { map_id: navId, map_revision: navRevision, pose: { x: 1.5, y: -2.5, yaw: .4 } };
  let rejectSelection = false;
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname, method = request.method();
    if (method !== 'GET') writes.push({ path, method, body: request.postDataJSON() });
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (path === '/api/v1/saved-maps') return json({ maps: [
      { id: sourceId, revision: sourceRevision, name: 'SOFTWARE 3D edited PCD', kind: 'pointcloud3d', manageable: true },
      { id: navId, revision: navRevision, name: 'SOFTWARE validated 2D map', kind: 'occupancy2d', manageable: true },
      { id: '9'.repeat(24), revision: '8'.repeat(64), name: 'Read-only unrelated map', kind: 'occupancy2d', manageable: false },
    ] });
    if (path === '/api/v1/navigation/initial-pose') return json({ accepted: true });
    if (path === '/api/v1/navigation/operational-3d') {
      if (method === 'POST') {
        if (rejectSelection) return json({ detail: 'DEVICE_BODY_MAP_ALIGNMENT_READBACK_REQUIRED' }, 409);
        state.selected = { navigation_2d: { map_id: navId, revision: navRevision }, generation: 'SOFTWARE_ONLY' };
        state.initial_pose_confirmation = initial;
      }
      if (method === 'DELETE') { state.selected = null; state.initial_pose_confirmation = null; }
      return json(state);
    }
    return json({ detail: 'Unexpected software fixture endpoint' }, 404);
  });
  await blank(page);
  await page.evaluate(async seedValue => {
    const { initializeOperationalNavigation } = await import('/features/maps/operational_navigation.js');
    window.softwareSeed = seedValue;
    window.operationalView = initializeOperationalNavigation({ host: document.querySelector('#fixture'), getSeed: () => window.softwareSeed });
  }, seed);
  await page.getByText('3D 위치추정을 주행에 사용', { exact: true }).click();
  await expect(page.getByLabel('3D 위치추정에 연결할 2D 지도')).toHaveValue(navId);
  return { writes, state, initial, rejectSelection() { rejectSelection = true; } };
}

test('3D selection pins the matched source and 2D revision, with separate explicit initialization and rollback', async ({ page }) => {
  const fixture = await mapsFixture(page);
  await expect(page.getByLabel('3D 위치추정에 연결할 2D 지도').locator('option')).toHaveCount(1);
  const confirm = page.getByRole('button', { name: '현재 정지 위치 확인 · 정합 시작' });
  await expect(confirm).toBeDisabled();
  await page.getByRole('button', { name: '이 3D 지도로 위치추정 준비' }).click();
  await expect(confirm).toBeEnabled();
  expect(fixture.writes).toEqual([{
    path: '/api/v1/navigation/operational-3d', method: 'POST',
    body: { map_id: sourceId, map_revision: sourceRevision, navigation_map_id: navId,
      navigation_map_revision: navRevision, seed_pose: sourceSeed.pose, course_region: sourceSeed.course },
  }]);
  await confirm.click();
  await expect(page.getByRole('status')).toContainText('정지 위치 확인 요청됨');
  expect(fixture.writes[1]).toEqual({ path: '/api/v1/navigation/initial-pose', method: 'POST', body: fixture.initial });
  await page.getByRole('button', { name: '기존 2D 위치 모드 선택' }).click();
  await expect(confirm).toBeDisabled();
  expect(fixture.writes[2]).toEqual({ path: '/api/v1/navigation/operational-3d', method: 'DELETE', body: null });
  expect(fixture.writes).toHaveLength(3);
});

test('missing current match keeps source selection disabled and calibration rejection stays visible', async ({ page }) => {
  const fixture = await mapsFixture(page, { seed: null, calibration: false });
  const prepare = page.getByRole('button', { name: '이 3D 지도로 위치추정 준비' });
  await expect(prepare).toBeDisabled();
  await expect(page.getByRole('status')).toContainText('장비 연결 후');
  expect(fixture.writes).toHaveLength(0);
  fixture.rejectSelection();
  await page.evaluate(seed => { window.softwareSeed = seed; window.operationalView.render(); }, sourceSeed);
  await prepare.click();
  await expect(page.getByRole('status')).toHaveText('DEVICE_BODY_MAP_ALIGNMENT_READBACK_REQUIRED');
  await expect(page.getByRole('button', { name: '현재 정지 위치 확인 · 정합 시작' })).toBeDisabled();
  expect(fixture.writes).toHaveLength(1);
});

test('operational status identifies stale runtime separately from a selected reference', async ({ page }) => {
  const fixture = await mapsFixture(page);
  fixture.state.runtime = { state: 'MAP_CORRECTION_STALE', correction_sequence: 7, reference_sha256: '1'.repeat(64) };
  await page.getByRole('button', { name: '지도·상태 새로고침' }).click();
  await expect(page.getByRole('status')).toContainText('연결 오래됨 · MAP_CORRECTION_STALE');
  expect(fixture.writes).toHaveLength(0);
});

function mission(state = 'paused') {
  return { id: missionId, label: 'SOFTWARE stop-and-go fixture', state,
    map_id: navId, map_revision: navRevision, annotation_revision: '3'.repeat(64),
    current_index: 0, completed_count: 0, remaining_count: 2, elapsed_seconds: 4,
    ownership_active: true, phase: 'after_arrival_confirmation', confirmation_token: confirmation,
    operator_test_required: true, operator_test: { source: 'OPERATOR_TEST', ready: true,
      stop_generation: 4, completion_profile: 'NAV_STOP_POINT_TEST', reason: '' },
    waypoints: [{ annotation_id: '4'.repeat(24), visit_id: '5'.repeat(32), label: 'Stop 1', status: 'running', hold_seconds: 2, after_arrival_confirmation: true },
      { annotation_id: '6'.repeat(24), visit_id: '7'.repeat(32), label: 'Stop 2', status: 'pending', hold_seconds: 2, after_arrival_confirmation: true }],
    logs: [] };
}

async function missionFixture(page, initial = mission()) {
  const fixture = { current: initial, offline: false, writes: [] };
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (fixture.offline) return json({ detail: 'SOFTWARE runtime disconnected' }, 503);
    if (request.method() === 'GET' && path === '/api/v1/missions') return json({ available: true, active_mission_id: missionId, missions: [fixture.current] });
    fixture.writes.push({ path, body: request.postDataJSON() });
    if (path.endsWith('/operator-test-enable')) {
      fixture.current = { ...fixture.current, operator_test_required: true,
        operator_test: { source: 'OPERATOR_TEST', ready: false, stop_generation: 0,
          completion_profile: 'NAV_STOP_POINT_TEST', reason: 'WAITING_MEASURED_STOP_DWELL' } };
      return json({ mission: fixture.current });
    }
    if (path.endsWith('/operator-test-green')) {
      await new Promise(resolve => setTimeout(resolve, 50));
      fixture.current = { ...fixture.current, state: 'running', phase: 'navigating', current_index: 1, confirmation_token: null,
        operator_test: { ...fixture.current.operator_test, ready: false, reason: 'WAITING_MEASURED_STOP_DWELL' } };
      return json({ mission: fixture.current, event: { source: 'OPERATOR_TEST', kind: 'GREEN_RELEASE_REQUEST' } });
    }
    return json({ detail: 'Unexpected software fixture mutation' }, 409);
  });
  await blank(page);
  await page.evaluate(async () => {
    const { createMissionClient } = await import('/features/cockpit/mission_client.js');
    const { createMissionPanel } = await import('/features/cockpit/panels/mission_panel.js');
    const api = async (path, options = {}) => {
      const response = await fetch(path, { ...options, headers: { 'Content-Type': 'application/json' } });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail);
      return body;
    };
    window.missionFixtureClient = createMissionClient({ api, setInterval() { return 0; }, clearInterval() {} });
    window.missionFixtureView = createMissionPanel({ document, client: window.missionFixtureClient,
      authoring: true, navigationAdapter: { requestTakeover() {} }, getContext: () => ({}) });
    window.missionFixtureView.mount(document.querySelector('#fixture'));
    window.missionFixtureView.activate();
  });
  await expect(page.getByRole('button', { name: '정지점 녹색 버튼 시험 설정' })).toBeVisible();
  return fixture;
}

test('test-mode setup uses its explicit mission action and leaves release disabled until measured arrival', async ({ page }) => {
  const value = { ...mission('ready'), phase: 'ready', ownership_active: false,
    operator_test_required: false, operator_test: null };
  const fixture = await missionFixture(page, value);
  const green = page.getByRole('button', { name: '시험용 녹색 · 현재 정지점 출발 허가' });
  await expect(green).toBeHidden();
  await page.getByRole('button', { name: '정지점 녹색 버튼 시험 설정' }).click();
  await expect(green).toBeVisible();
  await expect(green).toBeDisabled();
  await expect(page.getByRole('button', { name: '정지점 녹색 버튼 시험 설정' })).toBeDisabled();
  expect(fixture.writes).toEqual([{ path: `/api/v1/missions/${missionId}/operator-test-enable`, body: {} }]);
});

test('one current stop button submits one operator permission with no perception GREEN write', async ({ page }) => {
  const fixture = await missionFixture(page);
  const green = page.getByRole('button', { name: '시험용 녹색 · 현재 정지점 출발 허가' });
  await expect(green).toBeEnabled();
  await green.evaluate(button => { button.click(); button.click(); });
  await expect(green).toBeDisabled();
  await expect.poll(() => fixture.current.current_index).toBe(1);
  expect(fixture.writes).toHaveLength(1);
  const request = fixture.writes[0];
  expect(request.path).toBe(`/api/v1/missions/${missionId}/operator-test-green`);
  expect(request.body).toMatchObject({ confirmation_token: confirmation, stop_generation: 4 });
  expect(request.body.request_id).toMatch(/^[a-f0-9-]{36}$/);
  expect(Object.keys(request.body).sort()).toEqual(['confirmation_token', 'request_id', 'stop_generation']);
  expect(JSON.stringify(request.body)).not.toContain('GREEN');
  await green.evaluate(button => button.click());
  expect(fixture.writes).toHaveLength(1);
});

test('approach, dwell and stale localization keep the test button disabled without queued releases', async ({ page }) => {
  const value = mission('running'); value.phase = 'navigating';
  const fixture = await missionFixture(page, value);
  const green = page.getByRole('button', { name: '시험용 녹색 · 현재 정지점 출발 허가' });
  await expect(green).toBeDisabled();
  await green.evaluate(button => button.click());
  fixture.current = { ...mission('running'), phase: 'holding', operator_test: { ...mission().operator_test, ready: false, reason: 'WAITING_MEASURED_STOP_DWELL' } };
  await page.evaluate(() => window.missionFixtureClient.refresh());
  await expect(green).toBeDisabled();
  fixture.current = { ...mission(), operator_test: { ...mission().operator_test, ready: false, reason: 'LIVE_3D_LOCALIZATION_REQUIRED' } };
  await page.evaluate(() => window.missionFixtureClient.refresh());
  await expect(green).toBeDisabled();
  await expect(green).toHaveAttribute('title', 'LIVE_3D_LOCALIZATION_REQUIRED');
  fixture.current = mission();
  await page.evaluate(() => window.missionFixtureClient.refresh());
  await expect(green).toBeEnabled();
  expect(fixture.writes).toHaveLength(0);
});

test('connection loss removes the old stop permission and restored old tokens are not sent automatically', async ({ page }) => {
  const fixture = await missionFixture(page);
  const green = page.getByRole('button', { name: '시험용 녹색 · 현재 정지점 출발 허가' });
  await expect(green).toBeEnabled();
  fixture.offline = true;
  await page.evaluate(() => window.missionFixtureClient.refresh());
  await expect(green).toBeHidden();
  fixture.offline = false;
  fixture.current = { ...mission(), confirmation_token: '0'.repeat(32), operator_test: { ...mission().operator_test, stop_generation: 5 } };
  await page.evaluate(() => window.missionFixtureClient.refresh());
  await expect(green).toBeEnabled();
  expect(fixture.writes).toHaveLength(0);
});
