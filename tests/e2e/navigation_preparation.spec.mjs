// DOM and HTTP fixtures only: no ROS, control bridge or robot consumer.
import { expect, test } from '@playwright/test';

const cloud = { id: 'a'.repeat(24), revision: 'b'.repeat(64), kind: 'pointcloud3d', name: 'map1' };
const grid = { id: 'c'.repeat(24), revision: 'd'.repeat(64), kind: 'occupancy2d', name: 'map1_2D', frame_id: 'map' };

async function fixture(page) {
  const state = { selected: null, pair: null, runtime: null }, writes = [], reads = [];
  const observation = { state: 'STOPPED', active: false, can_start: true, can_stop: false, reason: '정지' };
  const inputs = { schema: 'robot-scope.navigation-preparation-inputs.v1', pair: null, observation, start_blockers: { items: [], advisory: true },
    evidence: { valid: false, reason: 'OBSERVATION_INACTIVE', cloud: null, pose: null, calibration_sha256: null }, reference_pose: null,
    candidates: Object.fromEntries(['z', 'roll', 'pitch'].map(key => [key, { value: null, frame: 'map', available: false, reason: 'OBSERVATION_INACTIVE', provenance: null }])) };
  let reject = false, failingReads = 0, heldWrites = null, releaseWrite = null;
  let rejectObservation = false;
  let invalidOperationalState = false;
  let proposalState = 'ready', proposalReason = null, proposalRejected = false, wrongProposalSource = false, proposalReads = null, releaseProposalReads = null;
  let proposalCleanup = { state: 'SETTLED', cancellation_requested: false, worker_active: false, terminal_state: 'succeeded' };
  await page.route('**/api/v1/observations/fastlio/**', async route => {
    const path = new URL(route.request().url()).pathname, body = route.request().postDataJSON();
    writes.push({ path, method: route.request().method(), body });
    if (rejectObservation) return route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: '다른 작업을 먼저 종료하세요: control_bridge_not_inactive' }) });
    if (path.endsWith('/start')) Object.assign(observation, { state: 'READY', active: true, can_start: false, can_stop: true, session_id: 'a'.repeat(32), reason: '입력 준비 완료' });
    else Object.assign(observation, { state: 'STOPPED', active: false, can_start: true, can_stop: false, session_id: null });
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify(observation) });
  });
  await page.route('**/software-preparation.html', route => route.fulfill({ contentType: 'text/html', body: `<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="/styles.css"><main style="padding:24px"><label>3D 위치추정 지도<select id="cloud"></select></label><label>2D 경로 계산 지도<select id="grid"><option>${grid.name}</option></select></label><article class="panel navigation-preparation-panel" id="host"></article></main>` }));
  await page.route('**/api/v1/navigation/operational-3d**', async route => {
    const path = new URL(route.request().url()).pathname, method = route.request().method();
    const body = route.request().postDataJSON();
    const json = (value, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(value) });
    if (method === 'GET') reads.push(path);
    if (path.endsWith('/preparation-inputs')) {
      if (failingReads > 0) { failingReads--; return json({ detail: 'SYNTHETIC_READ_TIMEOUT' }, 503); }
      if (invalidOperationalState) return json({ ...inputs, operational_state: null, operational_state_error: 'CONTEXT_CHANGED' });
      return json({ ...inputs, operational_state: { ...state, pair: state.pair && { ...state.pair, generation: state.selected?.generation }, activation: state.selected ? 'NEXT_NAVIGATION_START' : 'LEGACY_2D' }, operational_state_error: null });
    }
    if (method !== 'GET') writes.push({ path, method, body });
    if (path.includes('/initialization-proposals')) {
      if (method === 'POST' && proposalRejected) return json({ detail: 'GLOBAL_BACKEND_UNAVAILABLE' }, 503);
      if (method === 'GET' && proposalReads) await proposalReads;
      const pose = { x: 1, y: 2, z: .4, roll: .1, pitch: .2, yaw: .3 };
      const result = { schema: 'robot-scope.navigation-initialization-proposal.v1', proposal_id: 'f'.repeat(24),
        state: method === 'POST' ? 'capturing' : proposalState, reason: proposalReason,
        pair: inputs.pair, observation_session_id: observation.session_id, operational_application: 'NOT_RUN', absolute_accuracy_m: null,
        imu_hypothesis: method === 'GET' && proposalState === 'ready' ? { frame: 'camera_init', pose_reference: 'FASTLIO_IMU', units: 'metres_degrees', pose, approximate_only: true, requires_reanchor: true } : null,
        body_candidate: method === 'GET' && proposalState === 'ready' ? { frame: 'camera_init', pose_reference: 'base_link', units: 'metres_radians', pose, qualification: 'INFORMATIONAL_LOCALIZATION_MAP_ONLY' } : null,
        quality: method === 'GET' && proposalState === 'ready' ? { overlap: .7, rmse_m: .1, hypothesis_overlap_min: .6, operational_initial_overlap_min: .85, ambiguity_unresolved: false, residual_selection_gate_enabled: false, qualification: 'GLOBAL_HYPOTHESIS_ONLY_NOT_OPERATIONAL_QUALITY' } : null,
        provenance: method === 'GET' && proposalState === 'ready' ? { pose_age_s: 0, capture_age_s: 15, source_contract: { observer_id: '1'.repeat(32), cloud_epoch: (wrongProposalSource ? '4' : '2').repeat(32), pose_epoch: '3'.repeat(32) } } : null,
        cleanup: method === 'POST' ? { state: 'MONITORING', cancellation_requested: false } : proposalCleanup };
      return json(result, method === 'POST' ? 202 : 200);
    }
    if (method === 'GET' && failingReads > 0) { failingReads--; return json({ detail: 'SYNTHETIC_READ_TIMEOUT' }, 503); }
    if (method !== 'GET' && heldWrites) await heldWrites;
    if (reject && method !== 'GET') return json({ detail: 'PAIR_COORDINATE_RELATION_UNVERIFIED' }, 409);
    if (path.endsWith('/pair')) {
      state.selected = { workflow: 'staged_navigation_pair', generation: 'pairgen',
        localization_3d: { map_id: cloud.id, revision: cloud.revision }, navigation_2d: { map_id: grid.id, revision: grid.revision },
        calibration: { verified: true }, seed_geometry: null };
      state.pair = { can_start: false };
      inputs.pair = { generation: 'pairgen', valid: true, localization_3d: state.selected.localization_3d, navigation_2d: state.selected.navigation_2d };
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
    window.fixtureScrolls = 0;
    window.scrollTo = () => { window.fixtureScrolls++; };
    Element.prototype.scrollIntoView = () => { window.fixtureScrolls++; };
    window.preparation = initializeNavigationPreparation({ host: document.querySelector('#host'), map3dSelect: document.querySelector('#cloud'), map2dSelect: document.querySelector('#grid'),
      api: async (path, options) => { const response = await fetch(path, options); const value = await response.json(); if (!response.ok) throw new Error(value.detail); return value; },
      context: () => window.fixtureContext, onChange: () => {},
      actions: Object.fromEntries(['start', 'initial', 'goal', 'refresh'].map(key => [key, () => window.fixtureActions.push(key)])) });
    window.preparation.render(); await window.preparation.refresh(true);
  }, { cloud, grid });
  return { state, inputs, observation, writes, reads, reject(value) { reject = value; }, rejectObservation(value) { rejectObservation = value; }, failReads(count) { failingReads = count; }, invalidStatus(value) { invalidOperationalState = value; },
    proposalStatus(value, reason = null) { proposalState = value; proposalReason = reason; }, rejectProposal(value) { proposalRejected = value; }, wrongProposalSource(value) { wrongProposalSource = value; },
    cleanup(value) { proposalCleanup = value; },
    holdProposalReads() { proposalReads = new Promise(resolve => { releaseProposalReads = resolve; }); },
    releaseProposalReads() { releaseProposalReads?.(); proposalReads = null; releaseProposalReads = null; },
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
  expect(await page.evaluate(() => window.preparation.canStart())).toBe(false);
  await page.getByText('② 초기 높이·기울기 입력', { exact: true }).click();
  await page.getByRole('button', { name: '초기 높이·기울기 저장' }).click();
  await expect(page.getByRole('region', { name: '준비 상태·해결할 항목' })).toContainText('빈 값은 0으로 처리하지 않습니다');
  expect(f.writes).toHaveLength(1);
  await page.getByLabel('높이 z (m)').fill('0.34');
  await page.getByLabel('roll (rad)', { exact: true }).fill('0.01');
  await page.getByLabel('pitch (rad)', { exact: true }).fill('-0.02');
  await page.getByRole('button', { name: '초기 높이·기울기 저장' }).click();
  await expect.poll(() => page.evaluate(() => window.preparation.canStart())).toBe(true);
  expect(f.writes.map(value => value.path)).toEqual(['/api/v1/navigation/operational-3d/pair', '/api/v1/navigation/operational-3d/seed-geometry']);
  expect(f.writes[1].body).toEqual({ generation: 'pairgen', z: .34, roll: .01, pitch: -.02 });
  expect(await page.evaluate(() => window.fixtureActions)).toEqual([]);
  await expect(page.locator('[data-prep="steps"]')).toContainText('아래 주행 조작부에서 Nav2를 시작하세요.');
  for (const name of ['Nav2 시작', 'INITIAL POSE 지정', 'GOAL POSE 지정']) await expect(page.locator('#host').getByRole('button', { name, exact: true })).toHaveCount(0);
  await page.evaluate(() => { window.preparation.render(); window.preparation.render(); });
  expect(await page.evaluate(() => window.fixtureScrolls)).toBe(0);
  expect(await page.evaluate(() => window.fixtureActions)).toEqual([]);
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
  expect(await page.evaluate(() => window.preparation.permitsGoal())).toBe(true);
  await expect(page.locator('[data-prep="steps"]')).toContainText('아래 지도 조작부에서 GOAL POSE를 지정·전송하세요.');
  expect(await page.evaluate(() => window.fixtureActions)).toEqual([]);
  await page.evaluate(() => { const source = window.fixtureContext.navigation.operational_localization; source.ready = false; source.estimated_pose.stale = true; source.state = 'MAP_CORRECTION_STALE'; window.preparation.render(); });
  expect(await page.evaluate(() => window.preparation.permitsGoal())).toBe(false);
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
  await expect(page.locator('[data-prep="issues"]')).toContainText('상태 확인 실패');
  await expect(page.locator('[data-prep="details"]')).toContainText('SYNTHETIC_READ_TIMEOUT');
  // The dashboard calls this same refresh from its periodic navigation reads.
  // There is no operator click, pose input, or write retry after the failure.
  await page.evaluate(() => { window.fixturePolling = setInterval(() => window.preparation.refresh(), 100); });
  await expect(page.locator('[data-prep="issues"]')).not.toContainText('상태 확인 실패');
  await expect(page.locator('[data-prep="issues"]')).not.toContainText('현재 준비 상태 수신 실패');
  await expect(page.locator('[data-prep="current"]')).toContainText('현재 단계: 2.');
  await expect(page.locator('[data-prep="current"]')).toContainText('사용자 입력 필요');
  expect(await page.evaluate(() => window.preparation.canStart())).toBe(false);
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
  expect(await page.evaluate(() => window.preparation.canStart())).toBe(false);
  expect(await page.evaluate(() => window.preparation.canStart())).toBe(false);
  f.reject(true); f.releaseWrites();
  await expect(page.locator('[data-prep="issues"]')).toContainText('PAIR_COORDINATE_RELATION_UNVERIFIED');
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="issues"]')).toContainText('PAIR_COORDINATE_RELATION_UNVERIFIED');
  expect(f.writes).toHaveLength(1);
  expect(await page.evaluate(() => window.fixtureActions)).toEqual([]);
});

test('sensor evidence and individual candidates are descriptive and never applied automatically', async ({ page }) => {
  const f = await fixture(page);
  await page.getByLabel('3D 위치추정 지도').selectOption(cloud.id);
  await page.getByRole('button', { name: '① 지도 연결 확인·적용' }).click();
  await expect(page.locator('[data-prep="observation-status"]')).toContainText('관측 상태: 정지');
  await expect(page.getByRole('button', { name: '센서 관측 시작' })).toBeEnabled();
  await expect(page.locator('[data-prep="candidates"]')).toContainText('센서 관측이 실행 중이 아닙니다');
  f.inputs.candidates.z.reason = 'MAP_ABSOLUTE_Z_UNVERIFIED';
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="candidates"]')).toContainText('지도 기준 본체 높이가 확인되지 않았습니다');
  await page.getByRole('button', { name: '센서 관측 시작' }).click();
  await expect(page.getByRole('button', { name: '센서 관측 종료' })).toBeEnabled();
  expect(f.writes.at(-1)).toEqual({ path: '/api/v1/observations/fastlio/start', method: 'POST', body: { confirmed: true } });
  f.inputs.evidence = { valid: true, reason: null, calibration_sha256: 'calibration',
    cloud: { topic: '/cloud_registered', frame_id: 'camera_init', source_stamp_ns: '1234567890123456789', received_monotonic_s: 10, publisher_epoch: 'epoch' },
    pose: { topic: '/Odometry', frame_id: 'camera_init', source_stamp_ns: '1234567890123456789', received_monotonic_s: 10, publisher_epoch: 'epoch' } };
  f.inputs.reference_pose = { frame: 'camera_init', child_frame: 'base_link', source_stamp_ns: '1234567890123456789', position: { z: 1 }, orientation: { roll: 0.1 }, qualification: 'REFERENCE_ONLY' };
  f.inputs.candidates = { z: { value: .34, frame: 'map', available: true, reason: null, provenance: { source: 'validated', source_stamp_ns: '1234567890123456789', age_s: 0,
    map_id: grid.id, map_revision: grid.revision, localization_map_id: cloud.id, localization_map_revision: cloud.revision,
    bundle_generation: 'pairgen', runtime_instance_generation: 'process', localization_generation: 2, correction_sequence: 4 } },
    roll: { value: null, frame: 'map', available: false, reason: 'MAP_GRAVITY_ALIGNMENT_UNVERIFIED' }, pitch: { value: null, frame: 'map', available: false, reason: 'NEW_SERVER_REASON' } };
  await page.evaluate(({ cloud, grid }) => {
    const pin = { map_id: grid.id, map_revision: grid.revision, localization_map_id: cloud.id, localization_map_revision: cloud.revision,
      bundle_generation: 'pairgen', localization_generation: 2, runtime_instance_generation: 'process', correction_sequence: 4,
      pose: { x: 1, y: 2, z: .34, roll: 0, pitch: 0, yaw: 1 }, stale: false };
    Object.assign(window.fixtureContext.navigation, { map: grid, pipeline: { state: 'running', job_id: 'job' }, safety: { can_send_goal: true },
      operational_localization: { ...pin, source: 'STORED_PCD_FASTLIO', fresh: true, ready: true, estimated_pose: pin } });
  }, { cloud, grid });
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="evidence"]')).toContainText('/Odometry');
  await expect(page.locator('[data-prep="evidence"]')).toContainText('센서 시각 기록됨');
  await expect(page.locator('[data-prep="evidence"]')).not.toContainText('1234567890123456789');
  await expect(page.locator('[data-prep="evidence"]')).toContainText('지도 초기값 아님');
  await expect(page.locator('[data-prep="candidates"]')).toContainText('z: 자동 후보 0.34');
  await expect(page.locator('[data-prep="candidates"]')).toContainText('roll: 부족 · 지도 기준 기울기가 확인되지 않았습니다');
  await expect(page.locator('[data-prep="candidates"]')).toContainText('pitch: 부족 · 상세 원인을 확인하지 못했습니다');
  await expect(page.locator('[data-prep="candidates"]')).not.toContainText('NEW_SERVER_REASON');
  await expect(page.locator('[data-prep="details"]')).toContainText('1234567890123456789');
  await expect(page.locator('[data-prep="details"]')).toContainText('NEW_SERVER_REASON');
  await expect(page.locator('[data-prep="details"]')).toContainText('calibration');
  await page.evaluate(() => { window.fixtureContext.navigation.operational_localization.runtime_instance_generation = 'restarted'; window.preparation.render(); });
  await expect(page.locator('[data-prep="candidates"]')).not.toContainText('자동 후보');
  await expect(page.locator('[data-prep="candidates"]')).toContainText('후보 신선도 만료 또는 미확인');
  await expect(page.locator('[data-prep="evidence"]')).toContainText(/조회 요청 후 [1-9]\d*\.\d초 경과/);
  await page.getByText('② 초기 높이·기울기 입력', { exact: true }).click();
  await expect(page.getByLabel('높이 z (m)')).toHaveValue('');
  expect(f.writes.map(write => write.path)).toEqual(['/api/v1/navigation/operational-3d/pair', '/api/v1/observations/fastlio/start']);
  f.inputs.pair.generation = 'other';
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="candidates"]')).not.toContainText('자동 후보');
  await page.getByRole('button', { name: '센서 관측 종료' }).click();
  await expect(page.locator('[data-prep="observation-status"]')).toContainText('관측 입력 확인 실패');
  await expect(page.locator('[data-prep="details"]')).toContainText('"state": "STOPPED"');
  await expect(page.getByRole('button', { name: '센서 관측 시작' })).toBeDisabled();
  expect(f.writes.at(-1).body).toEqual({ confirmed: true, session_id: 'a'.repeat(32) });
});

test('observation rejection exposes bridge reason and does not retry or bypass the server', async ({ page }) => {
  const f = await fixture(page);
  await page.getByLabel('3D 위치추정 지도').selectOption(cloud.id);
  await page.getByRole('button', { name: '① 지도 연결 확인·적용' }).click();
  f.inputs.start_blockers.items = ['CONTROL_BRIDGE_NOT_INACTIVE', 'OWNER_BUSY:navigation'];
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="observation-status"]')).toContainText('제어 bridge가 비활성 상태가 아닙니다');
  await expect(page.locator('[data-prep="observation-status"]')).toContainText('주행이 센서를 사용 중입니다');
  await expect(page.locator('[data-prep="details"]')).toContainText('CONTROL_BRIDGE_NOT_INACTIVE');
  await expect(page.getByRole('button', { name: '센서 관측 시작' })).toBeDisabled();
  expect(f.writes.filter(write => write.path.includes('/observations/'))).toHaveLength(0);
  f.inputs.start_blockers.items = [];
  await page.evaluate(() => window.preparation.refresh(true));
  f.rejectObservation(true);
  await page.getByRole('button', { name: '센서 관측 시작' }).click();
  await expect(page.locator('[data-prep="observation-error"]')).toContainText('제어 bridge가 비활성 상태가 아닙니다');
  await expect(page.locator('[data-prep="details"]')).toContainText('control_bridge_not_inactive');
  expect(f.writes.filter(write => write.path.includes('/observations/'))).toHaveLength(1);
  expect(f.writes.filter(write => /seed-geometry|\/match|\/goal/.test(write.path))).toHaveLength(0);
});

async function proposalFixture(page) {
  const f = await fixture(page);
  await page.getByLabel('3D 위치추정 지도').selectOption(cloud.id);
  await page.getByRole('button', { name: '① 지도 연결 확인·적용' }).click();
  await page.getByRole('button', { name: '센서 관측 시작' }).click();
  await expect(page.getByRole('button', { name: '센서 관측 종료' })).toBeEnabled();
  f.state.selected.generation = 'b'.repeat(32);
  f.state.selected.localization_3d.frame = 'camera_init';
  f.inputs.pair.generation = 'b'.repeat(32);
  f.inputs.pair.calibration_sha256 = 'c'.repeat(64);
  f.inputs.evidence = { valid: true, reason: null,
    cloud: { topic: '/cloud_registered', frame_id: 'camera_init', observer_id: '1'.repeat(32), publisher_epoch: '2'.repeat(32), source_stamp_ns: '123' },
    pose: { topic: '/Odometry', frame_id: 'camera_init', observer_id: '1'.repeat(32), publisher_epoch: '3'.repeat(32), source_stamp_ns: '123' } };
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.getByRole('button', { name: '초기 위치 제안 계산' })).toBeEnabled();
  return f;
}

test('explicit proposal is read-only, distinguishes IMU and body units, and invalidates when the source changes', async ({ page }) => {
  const f = await proposalFixture(page);
  expect(f.writes.filter(value => value.path.endsWith('/initialization-proposals'))).toHaveLength(0);
  await page.getByRole('button', { name: '초기 위치 제안 계산' }).click();
  const proposalWrite = f.writes.filter(value => value.path.endsWith('/initialization-proposals'));
  expect(proposalWrite).toHaveLength(1);
  expect(proposalWrite[0].body).toEqual({ request_id: expect.stringMatching(/^[a-f0-9]{32}$/), bundle_generation: 'b'.repeat(32), observation_session_id: 'a'.repeat(32) });
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('FAST-LIO IMU 가설 (이력·근사값)');
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('위치 m, 각도 도');
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('원본 스캔 15.0초 전');
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('본체 위치 후보 (정보성)');
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('위치 m, 각도 rad');
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('운영 초기 기준 0.85는 별도');
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('운영 잔차 검사를 통과한 결과나 실제 위치 정확도가 아닙니다');
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('운영 보정 위치·Nav2 준비·TF 적용 결과가 아닙니다');
  await page.getByText('② 초기 높이·기울기 입력', { exact: true }).click();
  await expect(page.getByLabel('높이 z (m)')).toHaveValue('');
  await expect(page.getByLabel('roll (rad)', { exact: true })).toHaveValue('');
  await expect(page.getByLabel('pitch (rad)', { exact: true })).toHaveValue('');
  expect(f.writes.filter(value => /seed-geometry|\/match|\/goal/.test(value.path))).toHaveLength(0);
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('제안 관측이 오래됐거나 신선도를 확인하지 못했습니다');
  await expect(page.locator('[data-prep="proposal-result"]')).not.toContainText('본체 위치 후보 (정보성)');
  f.inputs.evidence.cloud.publisher_epoch = 'd'.repeat(32);
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('이전 제안을 사용할 수 없습니다');
  await expect(page.locator('[data-prep="proposal-result"]')).not.toContainText('본체 위치 후보 (정보성)');
  expect(f.writes.filter(value => value.path.endsWith('/initialization-proposals'))).toHaveLength(1);
});

test('proposal rejection and late result never retry or restore invalid data', async ({ page }) => {
  const f = await proposalFixture(page);
  f.rejectProposal(true);
  await page.getByRole('button', { name: '초기 위치 제안 계산' }).click();
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('전역 위치 제안 기능을 사용할 수 없습니다');
  await expect(page.locator('[data-prep="details"]')).toContainText('GLOBAL_BACKEND_UNAVAILABLE');
  expect(f.writes.filter(value => value.path.endsWith('/initialization-proposals'))).toHaveLength(1);
  f.rejectProposal(false); f.holdProposalReads();
  await page.getByRole('button', { name: '초기 위치 제안 계산' }).click();
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('현재 관측과 지도 문맥을 다시 확인 중');
  f.observation.state = 'STOPPED'; f.observation.active = false;
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('이전 제안을 사용할 수 없습니다');
  f.releaseProposalReads();
  await expect(page.locator('[data-prep="proposal-result"]')).not.toContainText('본체 위치 후보 (정보성)');
  expect(f.writes.filter(value => value.path.endsWith('/initialization-proposals'))).toHaveLength(2);
  expect(f.writes.filter(value => /seed-geometry|\/match|\/goal/.test(value.path))).toHaveLength(0);
});

test('one combined read clears prior readiness when its operational state is invalid', async ({ page }) => {
  const f = await fixture(page);
  await page.getByLabel('3D 위치추정 지도').selectOption(cloud.id);
  await page.getByRole('button', { name: '① 지도 연결 확인·적용' }).click();
  await expect(page.locator('[data-prep="selected"]')).toContainText('서버 준비 구성: map1 / map1_2D');
  f.state.selected.seed_geometry = { z: .34, roll: 0, pitch: 0 };
  f.state.pair.can_start = true;
  await page.evaluate(() => window.preparation.refresh(true));
  expect(await page.evaluate(() => window.preparation.canStart())).toBe(true);
  expect(f.reads.filter(path => path === '/api/v1/navigation/operational-3d')).toHaveLength(0);
  const readCount = f.reads.filter(path => path.endsWith('/preparation-inputs')).length;
  f.invalidStatus(true);
  await page.evaluate(() => window.preparation.refresh(true));
  expect(f.reads.filter(path => path.endsWith('/preparation-inputs'))).toHaveLength(readCount + 1);
  expect(await page.evaluate(() => window.preparation.canStart())).toBe(false);
  expect(await page.evaluate(() => window.preparation.permitsGoal())).toBe(false);
  expect(await page.evaluate(() => window.preparation.state())).toBe(null);
  await expect(page.locator('[data-prep="issues"]')).toContainText('조회 중 지도 또는 관측 실행이 바뀌었습니다');
  await expect(page.locator('[data-prep="details"]')).toContainText('CONTEXT_CHANGED');
  f.invalidStatus(false);
  await page.evaluate(() => window.preparation.refresh(true));
  expect(await page.evaluate(() => window.preparation.canStart())).toBe(true);
});

test('a proposal with different publisher identity is invalidated even if the session is unchanged', async ({ page }) => {
  const f = await proposalFixture(page);
  f.wrongProposalSource(true);
  await page.getByRole('button', { name: '초기 위치 제안 계산' }).click();
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('제안의 센서 출처가 현재 관측과 달라 사용할 수 없습니다');
  await expect(page.locator('[data-prep="proposal-result"]')).not.toContainText('본체 위치 후보 (정보성)');
  expect(f.writes.filter(value => value.path.endsWith('/initialization-proposals'))).toHaveLength(1);
  expect(f.writes.filter(value => /seed-geometry|\/match|\/goal/.test(value.path))).toHaveLength(0);
});

test('cleanup delay and failure remain blocked across context changes until settled and ownership clears', async ({ page }) => {
  const f = await proposalFixture(page);
  f.proposalStatus('stale', 'OBSERVATION_SESSION_CHANGED');
  f.cleanup({ state: 'CANCELLING', cancellation_requested: true, worker_active: true });
  await page.getByRole('button', { name: '초기 위치 제안 계산' }).click();
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('취소 요청 처리 중 · 작업 종료 미확인');
  await expect(page.getByRole('button', { name: '초기 위치 제안 계산' })).toBeDisabled();
  f.inputs.evidence.cloud.publisher_epoch = 'd'.repeat(32);
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('이전 제안을 사용할 수 없습니다');
  f.cleanup({ state: 'CANCEL_PENDING', cancellation_requested: true, worker_active: true });
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('취소 후 종료 확인 지연');
  await expect(page.getByRole('button', { name: '초기 위치 제안 계산' })).toBeDisabled();
  f.cleanup({ state: 'CANCEL_FAILED', cancellation_requested: false, worker_active: true });
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('취소 요청 실패 · 작업 종료 미확인');
  await expect(page.getByRole('button', { name: '초기 위치 제안 계산' })).toBeDisabled();
  f.cleanup({ state: 'CLEANUP_UNCONFIRMED', cancellation_requested: true });
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('작업 정리 상태 미확인');
  await expect(page.getByRole('button', { name: '초기 위치 제안 계산' })).toBeDisabled();
  f.cleanup({ state: 'SETTLED', cancellation_requested: true, worker_active: true, terminal_state: 'cancelled' });
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('작업 종료 상태를 확인하지 못했습니다');
  await expect(page.getByRole('button', { name: '초기 위치 제안 계산' })).toBeDisabled();
  f.inputs.start_blockers.items = ['OWNER_BUSY:global_observation'];
  await page.evaluate(() => window.preparation.refresh(true));
  f.cleanup({ state: 'SETTLED', cancellation_requested: true, worker_active: false, terminal_state: 'cancelled' });
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('작업 종료 확인');
  await expect(page.locator('[data-prep="proposal-result"]')).toContainText('전역 관측 작업이 사용 중입니다');
  await expect(page.getByRole('button', { name: '초기 위치 제안 계산' })).toBeDisabled();
  await expect(page.locator('[data-prep="proposal-result"]')).not.toContainText('본체 위치 후보 (정보성)');
  f.inputs.start_blockers.items = [];
  await page.evaluate(() => window.preparation.refresh(true));
  await expect(page.getByRole('button', { name: '초기 위치 제안 계산' })).toBeEnabled();
  await expect(page.locator('[data-prep="proposal-result"]')).not.toContainText('본체 위치 후보 (정보성)');
  expect(f.writes.filter(value => value.path.endsWith('/initialization-proposals'))).toHaveLength(1);
  expect(f.writes.filter(value => /seed-geometry|\/match|\/goal/.test(value.path))).toHaveLength(0);
});
